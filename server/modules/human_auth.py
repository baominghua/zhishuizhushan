from __future__ import annotations

import hmac
import ipaddress
import os
import threading
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import admin_users
from .auth import AuthContext, enforce_human_session_policy
from .auth_store import (
    CredentialConflict,
    change_password_if_current,
    complete_login,
    credential_for_user,
    iso_utc,
    parse_utc,
    record_failed_login,
    revoke_session,
    session_for_token,
    token_hash,
    touch_session,
    utc_now,
)
from .passwords import hash_password, needs_rehash, password_errors, verify_password
from .settings import PRODUCTION_MODES, get_settings


router = APIRouter(prefix="/api/auth", tags=["human-authentication"])

PASSWORD_VERIFY_CONCURRENCY = 4
_PASSWORD_VERIFY_SLOTS = threading.BoundedSemaphore(PASSWORD_VERIFY_CONCURRENCY)
_USERNAME_LOCKS_GUARD = threading.Lock()
_USERNAME_LOCKS: dict[str, tuple[threading.RLock, int]] = {}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)

    model_config = {"extra": "forbid"}


class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=256)
    newPassword: str = Field(min_length=1, max_length=256)

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


def trusted_client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        candidate = request.headers.get("X-Real-IP", "").strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    return request.client.host if request.client else ""


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


def _save_user_audit(user: dict[str, Any], action: str, client_ip: str | None = None) -> None:
    admin_users.append_auth_audit_event(
        str(user.get("id") or ""),
        action,
        str(user.get("username") or ""),
        client_ip=client_ip,
    )


class PasswordVerificationBusy(RuntimeError):
    pass


@contextmanager
def _username_verification_guard(username: str, *, blocking: bool = True):
    canonical = admin_users.canonical_username(username)
    with _USERNAME_LOCKS_GUARD:
        current = _USERNAME_LOCKS.get(canonical)
        lock = current[0] if current else threading.RLock()
        _USERNAME_LOCKS[canonical] = (lock, (current[1] if current else 0) + 1)
    acquired = lock.acquire(blocking=blocking)
    if not acquired:
        with _USERNAME_LOCKS_GUARD:
            current = _USERNAME_LOCKS.get(canonical)
            if current is not None and current[0] is lock:
                if current[1] <= 1:
                    _USERNAME_LOCKS.pop(canonical, None)
                else:
                    _USERNAME_LOCKS[canonical] = (lock, current[1] - 1)
        raise PasswordVerificationBusy("Password verification capacity is busy")
    try:
        yield
    finally:
        lock.release()
        with _USERNAME_LOCKS_GUARD:
            current = _USERNAME_LOCKS.get(canonical)
            if current is not None and current[0] is lock:
                if current[1] <= 1:
                    _USERNAME_LOCKS.pop(canonical, None)
                else:
                    _USERNAME_LOCKS[canonical] = (lock, current[1] - 1)


def _verify_password_bounded(
    username: str,
    password_hash: str,
    password: str,
) -> bool:
    with _username_verification_guard(username, blocking=False):
        if not _PASSWORD_VERIFY_SLOTS.acquire(blocking=False):
            raise PasswordVerificationBusy("Password verification capacity is busy")
        try:
            return verify_password(password_hash, password)
        finally:
            _PASSWORD_VERIFY_SLOTS.release()


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
    if not touch_session(session):
        return None
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


def _csrf_cookie_name() -> str:
    return f"{get_settings().session_cookie_name}_csrf"


def _set_csrf_cookie(response: Response, csrf_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=_csrf_cookie_name(),
        value=csrf_token,
        max_age=settings.session_absolute_seconds,
        httponly=False,
        samesite="strict",
        secure=settings.session_cookie_secure,
        path="/",
    )


def _set_session_cookies(
    response: Response,
    raw_token: str,
    csrf_token: str,
) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_absolute_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
    _set_csrf_cookie(response, csrf_token)


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    enforce_human_session_policy(request)
    settings = get_settings()
    if not settings.human_auth_enabled:
        raise HTTPException(status_code=404, detail="Human authentication is disabled")
    if _https_is_required() and not _request_is_https(request):
        raise HTTPException(status_code=426, detail="HTTPS is required for password login")

    client_ip = trusted_client_ip(request)
    username = admin_users.canonical_username(payload.username)
    user = admin_users.user_by_username(username)
    if not _is_active_user(user):
        if user is not None:
            _save_user_audit(user, "login_failure", client_ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    credential = credential_for_user(user["id"])
    if credential is None:
        _save_user_audit(user, "login_failure", client_ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    now = utc_now()
    locked_until = parse_utc(credential["lockedUntil"])
    if locked_until is not None and locked_until > now:
        _save_user_audit(user, "login_locked", client_ip)
        raise HTTPException(status_code=423, detail="Account temporarily locked")
    try:
        password_matches = _verify_password_bounded(
            username, credential["passwordHash"], payload.password
        )
    except PasswordVerificationBusy as exc:
        raise HTTPException(
            status_code=429,
            detail="Password verification is busy; retry shortly",
        ) from exc
    if not password_matches:
        try:
            updated_credential = record_failed_login(
                user["id"],
                now,
                expected_version=credential["credentialVersion"],
                expected_password_hash=credential["passwordHash"],
            )
        except CredentialConflict as exc:
            raise HTTPException(
                status_code=409,
                detail="Credential changed during login",
            ) from exc
        _save_user_audit(user, "login_failure", client_ip)
        updated_locked_until = parse_utc(updated_credential["lockedUntil"])
        if updated_locked_until is not None and updated_locked_until > now:
            _save_user_audit(user, "login_locked", client_ip)
            raise HTTPException(status_code=423, detail="Account temporarily locked")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    current_user = admin_users.find_user(user["id"])
    if not _is_active_user(current_user):
        raise HTTPException(status_code=409, detail="Account changed during login")
    rehashed_password = (
        hash_password(payload.password)
        if needs_rehash(credential["passwordHash"])
        else None
    )
    try:
        raw_token, csrf_token, _session, credential = complete_login(
            user["id"],
            credential["credentialVersion"],
            credential["passwordHash"],
            rehashed_password_hash=rehashed_password,
            now=now,
            ip_address=client_ip,
            user_agent=request.headers.get("User-Agent", ""),
            expires_at=_session_expiry(now, now, settings),
        )
    except CredentialConflict as exc:
        raise HTTPException(
            status_code=409,
            detail="Credential changed during login",
        ) from exc
    user = current_user
    _save_user_audit(user, "login_success", client_ip)
    _set_session_cookies(response, raw_token, csrf_token)
    return {**_profile(user, credential), "csrfToken": csrf_token}


@router.get("/session")
def session(request: Request) -> dict[str, Any]:
    context, stored_session, _raw_token = _require_human_session(request)
    credential = credential_for_user(stored_session["userId"])
    if credential is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    csrf_token = request.cookies.get(_csrf_cookie_name(), "")
    if not csrf_token or not hmac.compare_digest(
        token_hash(csrf_token), stored_session["csrfTokenHash"]
    ):
        raise HTTPException(status_code=401, detail="Authentication required")
    return {
        "authenticated": True,
        "user": context.user,
        "roles": sorted(context.roles),
        "mustChangePassword": bool(credential["mustChangePassword"]),
        "csrfToken": csrf_token,
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
    response.delete_cookie(key=_csrf_cookie_name(), path="/")
    return {"ok": True}


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, request: Request) -> dict[str, Any]:
    context, stored_session, _raw_token = _require_human_session(request)
    _require_csrf(request, stored_session)
    if payload.currentPassword == payload.newPassword:
        raise HTTPException(
            status_code=422,
            detail="New password must be different from the current password",
        )
    errors = password_errors(payload.newPassword)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    credential = credential_for_user(stored_session["userId"])
    if credential is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        password_matches = _verify_password_bounded(
            context.user,
            credential["passwordHash"],
            payload.currentPassword,
        )
    except PasswordVerificationBusy as exc:
        raise HTTPException(
            status_code=429,
            detail="Password verification is busy; retry shortly",
        ) from exc
    if not password_matches:
        raise HTTPException(status_code=401, detail="Invalid current password")
    now = utc_now()
    issued_at = parse_utc(stored_session["issuedAt"]) or now
    try:
        credential = change_password_if_current(
            stored_session["userId"],
            stored_session,
            credential["credentialVersion"],
            credential["passwordHash"],
            new_password_hash=hash_password(payload.newPassword),
            now=now,
            expires_at=_session_expiry(now, issued_at, get_settings()),
        )
    except CredentialConflict as exc:
        raise HTTPException(
            status_code=409,
            detail="Credential changed during password update",
        ) from exc
    stored_session["credentialVersion"] = credential["credentialVersion"]
    user = admin_users.find_user(credential["userId"])
    if user is not None:
        _save_user_audit(user, "password_change")
    return {"ok": True, "mustChangePassword": False}
