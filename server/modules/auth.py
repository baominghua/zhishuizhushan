from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from . import settings as platform_settings


@dataclass(frozen=True)
class AuthContext:
    user: str
    roles: set[str]
    projects: set[str]
    areas: set[str]


router = APIRouter(prefix="/api/auth", tags=["authentication"])


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


def role_data_scope_values(context: AuthContext, key: str) -> set[str]:
    try:
        from .admin_roles import data_scopes_for_roles, role_codes_for_context
    except Exception:
        return set()
    role_codes = sorted(context.roles) if context.areas else role_codes_for_context(context)
    scopes = data_scopes_for_roles(role_codes)
    try:
        from .admin_users import data_scopes_for_user

        if context.areas:
            return split_header_list(scopes.get(key))
        user_scopes = data_scopes_for_user(context.user)
        values = split_header_list(scopes.get(key))
        values.update(split_header_list(user_scopes.get(key)))
        return values
    except Exception:
        return split_header_list(scopes.get(key))


def effective_areas(context: AuthContext) -> set[str]:
    request_areas = set(context.areas)
    if has_admin_role(context):
        return request_areas

    role_areas = role_data_scope_values(context, "areas")
    if not role_areas:
        return request_areas
    if "*" in role_areas:
        return request_areas or {"*"}
    if not request_areas or "*" in request_areas:
        return role_areas
    return role_areas & request_areas


def has_effective_area_scope(context: AuthContext) -> bool:
    request_scoped = bool(context.areas) and "*" not in context.areas
    if has_admin_role(context):
        return request_scoped

    role_areas = role_data_scope_values(context, "areas")
    role_scoped = bool(role_areas) and "*" not in role_areas
    return role_scoped or request_scoped


def effective_data_scope_values(context: AuthContext, key: str) -> set[str]:
    if has_admin_role(context):
        return set()
    return role_data_scope_values(context, key)


def has_effective_data_scope(context: AuthContext, key: str) -> bool:
    values = effective_data_scope_values(context, key)
    return bool(values) and "*" not in values


def data_scope_value_allowed(context: AuthContext, key: str, value: str | None) -> bool:
    values = effective_data_scope_values(context, key)
    if not values or "*" in values:
        return True
    if not value:
        return False
    return str(value) in values


def require_write_access(context: AuthContext) -> None:
    if has_admin_role(context) or "operator" in context.roles or "gis-admin" in context.roles:
        return
    if not context.roles:
        return
    raise HTTPException(status_code=403, detail="Write access denied")


def area_allowed(context: AuthContext, area_code: str | None) -> bool:
    scoped = has_effective_area_scope(context)
    areas = effective_areas(context)
    if not area_code:
        return not scoped
    if not scoped or "*" in areas:
        return True
    return area_code in areas


@router.get("/config")
def auth_config() -> dict[str, Any]:
    return {
        "required": platform_settings.get_settings().auth_required,
        "scheme": "bearer",
    }


@router.get("/me")
def auth_me(
    request: Request,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    from .admin_roles import (
        effective_data_scopes_for_context,
        effective_menu_modules_for_context,
        effective_permissions_for_context,
        invalid_role_entries,
        module_catalog_by_key,
        permission_implications_payload,
        role_codes_for_context,
        unknown_role_entries,
    )

    roles = role_codes_for_context(context)
    permissions = effective_permissions_for_context(context)
    menu_modules = effective_menu_modules_for_context(context)
    modules_by_key = module_catalog_by_key()
    return {
        "authenticated": bool(bearer_token(request)),
        "user": context.user,
        "roles": roles,
        "permissions": permissions,
        "menuModules": menu_modules,
        "visibleMenuModules": [modules_by_key[key] for key in menu_modules if key in modules_by_key],
        "dataScopes": effective_data_scopes_for_context(context),
        "permissionImplications": permission_implications_payload(),
        "unknownRoles": unknown_role_entries(roles),
        "invalidRoles": invalid_role_entries(roles),
    }
