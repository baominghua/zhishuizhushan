from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request


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


def request_context(request: Request) -> AuthContext:
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
