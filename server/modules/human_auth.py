from __future__ import annotations

import hmac
import os
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from . import admin_users
from .auth import AuthContext, enforce_human_session_policy
from .auth_store import (
    credential_for_user,
    create_session,
    iso_utc,
    parse_utc,
    record_failed_login,
    reset_failed_login,
    revoke_session,
    revoke_user_sessions,
    save_credential,
    save_session,
    session_for_token,
    token_hash,
    utc_now,
)
from .passwords import hash_password, needs_rehash, password_errors, verify_password
from .settings import PRODUCTION_MODES, get_settings


router = APIRouter(prefix="/api/auth", tags=["human-authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str

    model_config = {"extra": "forbid"}


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str

    model_config = {"extra": "forbid"}


def _is_active_user(user: dict[str, Any] | None) -> bool:
    return bool(user) and not user.get("deletedAt") and user.get("status") in ("active", None, "")


def _request_is_https(request: Request) -> bool:
    settings = get_settings()
    if request.url.scheme == "https":
        return True
    if not settings.trust_proxy_headers:
        return False
    return request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower() == "https"


def _https_is_required() -> bool:
    mode = os.environ.get("SMART_BAMBOO_DEPLOYMENT_MODE", "development").strip().lower()
    if mode in PRODUCTION_MODES:
        return True
    return get_settings().auth_require_https


def _context_for_user(user: dict[str, Any]) -> AuthContext:
    username = str(user.get("username") or "")
    scopes = admin_users.data_scopes_for_user(username)
    return AuthContext(
        user=username,
        roles=set(admin_users.roles_for_user(username)),
        projects=set(scopes.get("projects") or []),
        areas=set(scopes.get("areas") or []),
    )


def _save_user_audit(user: dict[str, Any], action: str) -> None:
    updated = admin_users.append_user_audit_event(user, action, _context_for_user(user))
    if admin_users.use_mysql() or admin_users.use_postgis():
        admin_users.save_users([updated])
        return
    users = admin_users.load_all_users()
    for index, existing in enumerate(users):
        if str(existing.get("id")) == str(updated.get("id")):
            users[index] = updated
            admin_users.save_users(users)
            return


def _profile(user: dict[str, Any], credential: dict[str, Any]) -> dict[str, Any]:
    context = _context_for_user(user)
    return {
        "user": context.user,
        "roles": sorted(context.roles),
        "dataScopes": admin_users.data_scopes_for_user(context.user),
        "mustChangePassword": bool(credential["mustChangePassword"]),
    }


def _session_expiry(now, issued_at, settings) -> str:
    deadline = min(
        now + timedelta(seconds=settings.session_idle_seconds),
        issued_at + timedelta(seconds=settings.session_absolute_seconds),
    )
    return iso_utc(deadline)


def _human_session(request: Request) -> tuple[AuthContext, dict[str, Any], str] | None:
    settings = get_settings()
    if not settings.human_auth_enabled:
        return None
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None
    now = utc_now()
    session = session_for_token(raw_token, now)
    if session is None:
        return None
    user = admin_users.find_user(session["userId"])
    if not _is_active_user(user):
        return None
    credential = credential_for_user(session["userId"])
    if credential is None or credential["credentialVersion"] != session["credentialVersion"]:
        return None
    issued_at = parse_utc(session["issuedAt"])
    last_seen_at = parse_utc(session["lastSeenAt"])
    if issued_at is None or last_seen_at is None:
        return None
    if now >= issued_at + timedelta(seconds=settings.session_absolute_seconds):
        revoke_session(raw_token)
        return None
    if now >= last_seen_at + timedelta(seconds=settings.session_idle_seconds):
        revoke_session(raw_token)
        return None
    session["lastSeenAt"] = iso_utc(now)
    session["expiresAt"] = _session_expiry(now, issued_at, settings)
    save_session(session)
    return _context_for_user(user), session, raw_token


def human_session_context(request: Request) -> AuthContext | None:
    authenticated = _human_session(request)
    return authenticated[0] if authenticated is not None else None


def _require_human_session(request: Request) -> tuple[AuthContext, dict[str, Any], str]:
    authenticated = _human_session(request)
    if authenticated is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return authenticated


def _require_csrf(request: Request, session: dict[str, Any]) -> None:
    csrf_token = request.headers.get("X-CSRF-Token", "")
    if not csrf_token or not hmac.compare_digest(token_hash(csrf_token), session["csrfTokenHash"]):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def _set_session_cookie(response: Response, raw_token: str, request: Request) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_absolute_seconds,
        httponly=True,
        samesite="lax",
        secure=_request_is_https(request),
        path="/",
    )


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    enforce_human_session_policy(request)
    settings = get_settings()
    if not settings.human_auth_enabled:
        raise HTTPException(status_code=404, detail="Human authentication is disabled")
    if _https_is_required() and not _request_is_https(request):
        raise HTTPException(status_code=426, detail="HTTPS is required for password login")

    username = admin_users.canonical_username(payload.username)
    user = admin_users.user_by_username(username)
    if not _is_active_user(user):
        if user is not None:
            _save_user_audit(user, "login_failure")
        raise HTTPException(status_code=401, detail="Invalid username or password")
    credential = credential_for_user(user["id"])
    if credential is None:
        _save_user_audit(user, "login_failure")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    now = utc_now()
    locked_until = parse_utc(credential["lockedUntil"])
    if locked_until is not None and locked_until > now:
        _save_user_audit(user, "login_locked")
        raise HTTPException(status_code=423, detail="Account temporarily locked")
    if not verify_password(credential["passwordHash"], payload.password):
        updated_credential = record_failed_login(user["id"], now)
        _save_user_audit(user, "login_failure")
        updated_locked_until = parse_utc(updated_credential["lockedUntil"])
        if updated_locked_until is not None and updated_locked_until > now:
            _save_user_audit(user, "login_locked")
            raise HTTPException(status_code=423, detail="Account temporarily locked")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if needs_rehash(credential["passwordHash"]):
        credential["passwordHash"] = hash_password(payload.password)
        credential["updatedAt"] = iso_utc(now)
        save_credential(credential)
    credential = reset_failed_login(user["id"])
    raw_token, csrf_token, session = create_session(
        user["id"],
        credential["credentialVersion"],
        now,
        request.client.host if request.client else "",
        request.headers.get("User-Agent", ""),
    )
    session["expiresAt"] = _session_expiry(now, now, settings)
    save_session(session)
    _save_user_audit(user, "login_success")
    _set_session_cookie(response, raw_token, request)
    return {**_profile(user, credential), "csrfToken": csrf_token}


@router.get("/session")
def session(request: Request) -> dict[str, Any]:
    context, stored_session, _raw_token = _require_human_session(request)
    credential = credential_for_user(stored_session["userId"])
    if credential is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {
        "authenticated": True,
        "user": context.user,
        "roles": sorted(context.roles),
        "mustChangePassword": bool(credential["mustChangePassword"]),
    }


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    context, stored_session, raw_token = _require_human_session(request)
    _require_csrf(request, stored_session)
    revoke_session(raw_token)
    user = admin_users.find_user(stored_session["userId"])
    if user is not None:
        _save_user_audit(user, "logout")
    response.delete_cookie(key=get_settings().session_cookie_name, path="/")
    return {"ok": True}


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, request: Request) -> dict[str, Any]:
    _context, stored_session, _raw_token = _require_human_session(request)
    _require_csrf(request, stored_session)
    credential = credential_for_user(stored_session["userId"])
    if credential is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not verify_password(credential["passwordHash"], payload.currentPassword):
        raise HTTPException(status_code=401, detail="Invalid current password")
    errors = password_errors(payload.newPassword)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    now = utc_now()
    credential["passwordHash"] = hash_password(payload.newPassword)
    credential["passwordChangedAt"] = iso_utc(now)
    credential["mustChangePassword"] = False
    credential["failedLoginCount"] = 0
    credential["lockedUntil"] = None
    credential["credentialVersion"] += 1
    credential["updatedAt"] = iso_utc(now)
    save_credential(credential)
    revoke_user_sessions(credential["userId"], except_session_id=stored_session["id"])
    stored_session["credentialVersion"] = credential["credentialVersion"]
    stored_session["lastSeenAt"] = iso_utc(now)
    issued_at = parse_utc(stored_session["issuedAt"]) or now
    stored_session["expiresAt"] = _session_expiry(now, issued_at, get_settings())
    save_session(stored_session)
    user = admin_users.find_user(credential["userId"])
    if user is not None:
        _save_user_audit(user, "password_change")
    return {"ok": True, "mustChangePassword": False}
