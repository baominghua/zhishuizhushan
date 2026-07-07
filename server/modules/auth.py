from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

from . import settings as platform_settings


@dataclass(frozen=True)
class AuthContext:
    user: str
    roles: set[str]
    projects: set[str]
    areas: set[str]


def split_header(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.replace(";", ",").split(",") if item.strip()}


def bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    return (
        request.headers.get("X-RS-Token", "").strip()
        or request.query_params.get("token", "").strip()
    )


def parse_token_profile(raw_profile: Any, token: str) -> AuthContext:
    if isinstance(raw_profile, str):
        return AuthContext(user=raw_profile or token, roles={"admin"}, projects={"*"}, areas={"*"})
    if not isinstance(raw_profile, dict):
        return AuthContext(user=token, roles={"admin"}, projects={"*"}, areas={"*"})

    return AuthContext(
        user=str(raw_profile.get("user") or raw_profile.get("username") or token).strip(),
        roles=split_header_list(raw_profile.get("roles")) or {"viewer"},
        projects=split_header_list(raw_profile.get("projects")),
        areas=split_header_list(raw_profile.get("areas") or raw_profile.get("areaCodes")),
    )


def split_header_list(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return split_header(value)
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return {str(value).strip()} if str(value).strip() else set()


def token_profiles() -> dict[str, AuthContext]:
    raw_tokens = os.environ.get("REMOTE_SENSING_API_TOKENS", "").strip()
    if not raw_tokens:
        return {}

    try:
        parsed = json.loads(raw_tokens)
    except json.JSONDecodeError:
        parsed = None

    profiles: dict[str, AuthContext] = {}
    if isinstance(parsed, dict):
        for token, profile in parsed.items():
            token_value = str(token).strip()
            if token_value:
                profiles[token_value] = parse_token_profile(profile, token_value)
        return profiles

    for token in split_header(raw_tokens):
        profiles[token] = AuthContext(user=token, roles={"admin"}, projects={"*"}, areas={"*"})
    return profiles


def request_context(request: Request) -> AuthContext:
    if platform_settings.get_settings().auth_required:
        token = bearer_token(request)
        profile = token_profiles().get(token)
        if not token or profile is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return profile

    return AuthContext(
        user=request.headers.get("X-RS-User", "").strip(),
        roles=split_header(request.headers.get("X-RS-Roles")),
        projects=split_header(request.headers.get("X-RS-Projects")),
        areas=split_header(request.headers.get("X-RS-Areas")),
    )


def has_admin_role(context: AuthContext) -> bool:
    return "*" in context.roles or "admin" in context.roles or "platform-admin" in context.roles


def require_write_access(context: AuthContext) -> None:
    if has_admin_role(context) or "operator" in context.roles or "gis-admin" in context.roles:
        return
    if not context.roles:
        return
    raise HTTPException(status_code=403, detail="Write access denied")


def area_allowed(context: AuthContext, area_code: str | None) -> bool:
    if not area_code or not context.areas or "*" in context.areas:
        return True
    return area_code in context.areas
