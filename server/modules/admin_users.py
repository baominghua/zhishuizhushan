from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from .admin_roles import (
    csv_download_response,
    json_download_response,
    require_any_permission,
    require_permission,
    role_effective_permission_coverage,
    safe_download_stem,
)
from .auth import AuthContext, request_context, split_header_list
from . import database
from .auth_store import (
    credential_for_user,
    iso_utc,
    mysql_credential_for_user,
    new_credential,
    revoke_user_sessions,
    revoke_user_sessions_mysql,
    save_credential,
    utc_now,
    write_mysql_credential,
)
from .database import (
    admin_credentials_json_path,
    admin_sessions_json_path,
    admin_users_json_path,
    json_transaction,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
    use_postgis,
)
from .settings import get_settings
from .passwords import (
    MAX_PASSWORD_CHARACTERS,
    PasswordOperationBusy,
    hash_password,
    hash_password_bounded,
    password_errors,
    validate_password_input,
)


router = APIRouter(prefix="/api/admin", tags=["admin-users"])

POSTGIS_SELECT_COLUMNS = [
    "id",
    "username",
    "display_name",
    "status",
    "roles",
    "data_scopes",
    "properties",
    "created_at",
    "updated_at",
    "deleted_at",
]

POSTGIS_SELECT_SQL = """
    SELECT
        id::text,
        username,
        display_name,
        status,
        COALESCE(roles, '[]'::jsonb),
        COALESCE(data_scopes, '{}'::jsonb),
        COALESCE(properties, '{}'::jsonb),
        created_at,
        updated_at,
        deleted_at
    FROM admin_users
"""
MYSQL_SELECT_SQL = """
    SELECT
        au.id,
        au.username,
        au.display_name,
        au.status,
        COALESCE((
            SELECT JSON_ARRAYAGG(ar.role_code)
            FROM admin_user_roles aur
            JOIN admin_roles ar ON ar.id = aur.admin_role_id
            WHERE aur.admin_user_id = au.id
        ), JSON_ARRAY()),
        COALESCE(au.data_scopes, JSON_OBJECT()),
        COALESCE(au.properties, JSON_OBJECT()),
        au.created_at,
        au.updated_at,
        au.deleted_at
    FROM admin_users au
"""

DB_TO_API_FIELD = {
    "id": "id",
    "username": "username",
    "display_name": "displayName",
    "status": "status",
    "roles": "roles",
    "data_scopes": "dataScopes",
    "properties": "properties",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "deleted_at": "deletedAt",
}

USER_AUDIT_EVENT_LIMIT = 100


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def postgis_connect():
    try:
        import psycopg
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"admin users PostGIS database requires psycopg. {exc}") from exc

    try:
        return psycopg.connect(get_settings().database_url)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="admin users PostGIS database is unavailable") from exc


def datetime_to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def serializable_json(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, ensure_ascii=False)


def mysql_datetime(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value or None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def normalize_postgis_user_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
    else:
        source = dict(zip(POSTGIS_SELECT_COLUMNS, row))

    user: dict[str, Any] = {}
    for db_field, api_field in DB_TO_API_FIELD.items():
        value = source.get(db_field)
        if db_field == "roles":
            value = json_value(value, [])
        elif db_field in {"data_scopes", "properties"}:
            value = json_value(value, {})
        elif db_field in {"created_at", "updated_at", "deleted_at"}:
            value = datetime_to_iso(value)
        user[api_field] = value
    user.setdefault("roles", [])
    user.setdefault("dataScopes", {})
    user.setdefault("properties", {})
    return user


def compact_list(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def canonical_username(value: str | None) -> str:
    return str(value or "").strip().lower()


class AdminUserBase(BaseModel):
    username: str = Field(min_length=1)
    displayName: str = Field(min_length=1)
    status: str | None = "active"
    roles: list[str] = Field(default_factory=list)
    dataScopes: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("username", mode="after")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = canonical_username(value)
        if not normalized:
            raise ValueError("username must not be blank")
        return normalized

    @field_validator("roles", mode="after")
    @classmethod
    def normalize_roles(cls, values: list[str]) -> list[str]:
        return compact_list(values)


class AdminUserIn(AdminUserBase):
    model_config = {"extra": "forbid"}


class AdminUserPatch(BaseModel):
    displayName: str | None = None
    status: str | None = None
    roles: list[str] | None = None
    dataScopes: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None

    @field_validator("roles", mode="after")
    @classmethod
    def normalize_patch_roles(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else compact_list(values)

    model_config = {"extra": "forbid"}


class TemporaryPasswordIn(BaseModel):
    temporaryPassword: str = Field(min_length=1, max_length=MAX_PASSWORD_CHARACTERS)

    @field_validator("temporaryPassword", mode="after")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        return validate_password_input(value)

    model_config = {"extra": "forbid"}


class AdminUserEffectivePreviewIn(BaseModel):
    username: str | None = ""
    status: str | None = "active"
    roles: list[str] = Field(default_factory=list)
    dataScopes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("roles", mode="after")
    @classmethod
    def normalize_preview_roles(cls, values: list[str]) -> list[str]:
        return compact_list(values)

    model_config = {"extra": "forbid"}


class AdminUserOut(AdminUserBase):
    id: str
    createdAt: str
    updatedAt: str
    deletedAt: str | None = None


class UserFilters(BaseModel):
    q: str = ""
    status: str = ""
    role: str = ""
    includeDeleted: bool = False
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


def filter_params(
    q: str = Query(default=""),
    status: str = Query(default=""),
    role: str = Query(default=""),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> UserFilters:
    return UserFilters(q=q, status=status, role=role, includeDeleted=includeDeleted, limit=limit, offset=offset)


def properties_without_audit(properties: dict[str, Any] | None) -> dict[str, Any]:
    clean = dict(properties or {})
    clean.pop("auditEvents", None)
    return clean


def user_snapshot(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": user.get("username") or "",
        "displayName": user.get("displayName") or "",
        "status": user.get("status") or "active",
        "roles": list(user.get("roles") or []),
        "dataScopes": dict(user.get("dataScopes") or {}),
        "properties": properties_without_audit(user.get("properties") or {}),
        "deletedAt": user.get("deletedAt"),
    }


def user_changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_snapshot = user_snapshot(before)
    after_snapshot = user_snapshot(after)
    fields = ["displayName", "status", "roles", "dataScopes", "properties", "deletedAt"]
    return sorted(field for field in fields if before_snapshot.get(field) != after_snapshot.get(field))


def existing_user_audit_events(*users: dict[str, Any] | None) -> list[dict[str, Any]]:
    for user in users:
        properties = user.get("properties") if isinstance(user, dict) else {}
        events = properties.get("auditEvents") if isinstance(properties, dict) else None
        if isinstance(events, list):
            return [event for event in events if isinstance(event, dict)]
    return []


def append_user_audit_event(
    user: dict[str, Any],
    action: str,
    context: AuthContext,
    *,
    before: dict[str, Any] | None = None,
    changed_fields: list[str] | None = None,
    client_ip: str | None = None,
) -> dict[str, Any]:
    updated = dict(user)
    properties = dict(updated.get("properties") or {})
    events = existing_user_audit_events(before, updated)
    event: dict[str, Any] = {
        "at": now_iso(),
        "action": action,
        "actor": context.user,
        "username": updated.get("username") or "",
        "changedFields": changed_fields or [],
        "after": user_snapshot(updated),
    }
    if client_ip:
        event["clientIp"] = client_ip
    if before is not None:
        event["before"] = user_snapshot(before)
    events.append(event)
    properties["auditEvents"] = events[-USER_AUDIT_EVENT_LIMIT:]
    updated["properties"] = properties
    return updated


def append_auth_audit_event(
    user_id: str,
    action: str,
    actor_username: str,
    *,
    client_ip: str | None = None,
) -> dict[str, Any] | None:
    """Append an authentication event without writing a stale user snapshot."""
    context = AuthContext(
        user=actor_username,
        roles=set(),
        projects=set(),
        areas=set(),
    )
    if use_mysql():
        with mysql_connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"{MYSQL_SELECT_SQL} WHERE au.id = %s FOR UPDATE",
                        (user_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        conn.rollback()
                        return None
                    current = normalize_postgis_user_row(row)
                    updated = append_user_audit_event(
                        current,
                        action,
                        context,
                        client_ip=client_ip,
                    )
                    cur.execute(
                        "UPDATE admin_users SET properties = %s WHERE id = %s",
                        (
                            serializable_json(updated.get("properties"), {}),
                            user_id,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return updated

    if use_postgis():
        with postgis_connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"{POSTGIS_SELECT_SQL} WHERE id = %s FOR UPDATE",
                        (user_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        conn.rollback()
                        return None
                    current = normalize_postgis_user_row(row)
                    updated = append_user_audit_event(
                        current,
                        action,
                        context,
                        client_ip=client_ip,
                    )
                    cur.execute(
                        "UPDATE admin_users SET properties = %s::jsonb WHERE id = %s",
                        (
                            serializable_json(updated.get("properties"), {}),
                            user_id,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return updated

    with database.JSON_STORE_LOCK:
        users = load_json_records(admin_users_json_path())
        for index, current in enumerate(users):
            if str(current.get("id")) != str(user_id):
                continue
            updated = append_user_audit_event(
                current,
                action,
                context,
                client_ip=client_ip,
            )
            users[index] = {
                **current,
                "properties": updated.get("properties") or {},
            }
            save_json_records(admin_users_json_path(), users)
            return users[index]
    return None


def user_event_record(user: dict[str, Any], event: dict[str, Any], index: int) -> dict[str, Any]:
    after = event.get("after") if isinstance(event.get("after"), dict) else {}
    before = event.get("before") if isinstance(event.get("before"), dict) else {}
    changed_fields = event.get("changedFields") if isinstance(event.get("changedFields"), list) else []
    username = str(event.get("username") or user.get("username") or after.get("username") or "")
    roles = after.get("roles") if isinstance(after.get("roles"), list) else []
    data_scopes = after.get("dataScopes") if isinstance(after.get("dataScopes"), dict) else {}
    summary_bits = [str(event.get("action") or "-"), username]
    if changed_fields:
        summary_bits.append(", ".join(str(item) for item in changed_fields))
    if roles:
        summary_bits.append(", ".join(str(item) for item in roles))
    return {
        "eventId": f"{user.get('id') or username}:{index}",
        "userId": str(user.get("id") or ""),
        "username": username,
        "displayName": str(after.get("displayName") or user.get("displayName") or ""),
        "action": str(event.get("action") or ""),
        "actor": str(event.get("actor") or ""),
        "at": event.get("at") or "",
        "changedFields": [str(item) for item in changed_fields],
        "roles": [str(item) for item in roles],
        "dataScopes": data_scopes,
        "before": before,
        "after": after,
        "summary": " | ".join(item for item in summary_bits if item),
    }


def user_event_matches(
    record: dict[str, Any],
    q: str = "",
    action: str = "",
    username: str = "",
) -> bool:
    if action and str(record.get("action") or "") != action:
        return False
    if username and str(record.get("username") or "") != username:
        return False
    keyword = q.strip().lower()
    if not keyword:
        return True
    haystack = " ".join(
        [
            str(record.get("eventId") or ""),
            str(record.get("userId") or ""),
            str(record.get("username") or ""),
            str(record.get("displayName") or ""),
            str(record.get("action") or ""),
            str(record.get("actor") or ""),
            " ".join(record.get("changedFields") or []),
            " ".join(record.get("roles") or []),
            json.dumps(record.get("dataScopes") or {}, ensure_ascii=False),
            str(record.get("summary") or ""),
        ]
    ).lower()
    return keyword in haystack


def list_user_event_records(q: str = "", action: str = "", username: str = "") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for user in load_all_users():
        properties = user.get("properties") if isinstance(user, dict) else {}
        audit_events = properties.get("auditEvents") if isinstance(properties, dict) else []
        for index, event in enumerate(audit_events or [], start=1):
            if isinstance(event, dict):
                records.append(user_event_record(user, event, index))
    matched = [
        record
        for record in records
        if user_event_matches(record, q=q, action=action, username=username)
    ]
    return sorted(
        matched,
        key=lambda item: (str(item.get("at") or ""), str(item.get("eventId") or "")),
        reverse=True,
    )


def normalize_user(payload: dict[str, Any]) -> dict[str, Any]:
    user = dict(payload)
    timestamp = now_iso()
    user.setdefault("id", str(uuid.uuid4()))
    user.setdefault("createdAt", timestamp)
    user["updatedAt"] = timestamp
    user.setdefault("deletedAt", None)
    user["username"] = canonical_username(user.get("username"))
    user["roles"] = compact_list(user.get("roles"))
    user.setdefault("status", "active")
    user.setdefault("dataScopes", {})
    user.setdefault("properties", {})
    return user


def postgis_where(
    *,
    filters: UserFilters | None = None,
    include_deleted: bool = False,
    user_id: str | None = None,
    username: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    if user_id:
        clauses.append("id = %s")
        params.append(user_id)
    if username:
        clauses.append("LOWER(username) = %s")
        params.append(canonical_username(username))
    if filters:
        if filters.status:
            clauses.append("status = %s")
            params.append(filters.status)
        if filters.role:
            clauses.append("roles ? %s")
            params.append(filters.role)
        if filters.q:
            query_text = f"%{filters.q}%"
            clauses.append(
                """
                (
                    username ILIKE %s
                    OR display_name ILIKE %s
                    OR roles::text ILIKE %s
                    OR data_scopes::text ILIKE %s
                    OR properties::text ILIKE %s
                )
                """
            )
            params.extend([query_text, query_text, query_text, query_text, query_text])
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def fetch_users_postgis(
    *,
    filters: UserFilters | None = None,
    include_deleted: bool = False,
    user_id: str | None = None,
    username: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where_sql, params = postgis_where(
        filters=filters,
        include_deleted=include_deleted,
        user_id=user_id,
        username=username,
    )
    sql = f"{POSTGIS_SELECT_SQL}{where_sql} ORDER BY updated_at DESC, username"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_user_row(row) for row in cur.fetchall()]


def count_users_postgis(filters: UserFilters) -> int:
    where_sql, params = postgis_where(filters=filters, include_deleted=filters.includeDeleted)
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM admin_users{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def first_user_postgis(
    *,
    user_id: str | None = None,
    username: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    items = fetch_users_postgis(user_id=user_id, username=username, include_deleted=include_deleted, limit=1)
    return items[0] if items else None


def postgis_user_values(user: dict[str, Any]) -> tuple[Any, ...]:
    return (
        user.get("id"),
        user.get("username"),
        user.get("displayName"),
        user.get("status"),
        serializable_json(user.get("roles"), []),
        serializable_json(user.get("dataScopes"), {}),
        serializable_json(user.get("properties"), {}),
        user.get("createdAt"),
        user.get("updatedAt"),
        user.get("deletedAt"),
    )


def execute_upsert_user_postgis(cur: Any, user: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO admin_users (
            id,
            username,
            display_name,
            status,
            roles,
            data_scopes,
            properties,
            created_at,
            updated_at,
            deleted_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s::jsonb,
            %s::jsonb,
            %s::jsonb,
            %s,
            %s,
            %s
        )
        ON CONFLICT (id) DO UPDATE SET
            username = EXCLUDED.username,
            display_name = EXCLUDED.display_name,
            status = EXCLUDED.status,
            roles = EXCLUDED.roles,
            data_scopes = EXCLUDED.data_scopes,
            properties = EXCLUDED.properties,
            updated_at = EXCLUDED.updated_at,
            deleted_at = EXCLUDED.deleted_at
        """,
        postgis_user_values(user),
    )


def upsert_users_postgis(users: list[dict[str, Any]]) -> None:
    if not users:
        return
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            for user in users:
                execute_upsert_user_postgis(cur, user)
        conn.commit()


def mysql_where(
    *,
    filters: UserFilters | None = None,
    include_deleted: bool = False,
    user_id: str | None = None,
    username: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_deleted:
        clauses.append("au.deleted_at IS NULL")
    if user_id:
        clauses.append("au.id = %s")
        params.append(user_id)
    if username:
        clauses.append("LOWER(au.username) = %s")
        params.append(canonical_username(username))
    if filters:
        if filters.status:
            clauses.append("au.status = %s")
            params.append(filters.status)
        if filters.role:
            clauses.append(
                "EXISTS (SELECT 1 FROM admin_user_roles aur "
                "JOIN admin_roles ar ON ar.id = aur.admin_role_id "
                "WHERE aur.admin_user_id = au.id AND ar.role_code = %s)"
            )
            params.append(filters.role)
        if filters.q:
            query_text = f"%{filters.q}%"
            clauses.append(
                "(au.username LIKE %s OR au.display_name LIKE %s "
                "OR CAST(au.data_scopes AS CHAR) LIKE %s OR CAST(au.properties AS CHAR) LIKE %s "
                "OR EXISTS (SELECT 1 FROM admin_user_roles aur "
                "JOIN admin_roles ar ON ar.id = aur.admin_role_id "
                "WHERE aur.admin_user_id = au.id AND ar.role_code LIKE %s))"
            )
            params.extend([query_text] * 5)
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def fetch_users_mysql(
    *,
    filters: UserFilters | None = None,
    include_deleted: bool = False,
    user_id: str | None = None,
    username: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where_sql, params = mysql_where(
        filters=filters,
        include_deleted=include_deleted,
        user_id=user_id,
        username=username,
    )
    sql = f"{MYSQL_SELECT_SQL}{where_sql} ORDER BY au.updated_at DESC, au.username"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_user_row(row) for row in cur.fetchall()]


def count_users_mysql(filters: UserFilters) -> int:
    where_sql, params = mysql_where(filters=filters, include_deleted=filters.includeDeleted)
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM admin_users au{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def first_user_mysql(
    *,
    user_id: str | None = None,
    username: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    items = fetch_users_mysql(
        user_id=user_id,
        username=username,
        include_deleted=include_deleted,
        limit=1,
    )
    return items[0] if items else None


def execute_upsert_user_mysql(cur: Any, user: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO admin_users (
            id, username, display_name, status, data_scopes, properties,
            created_at, updated_at, deleted_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            username = VALUES(username),
            display_name = VALUES(display_name),
            status = VALUES(status),
            data_scopes = VALUES(data_scopes),
            properties = VALUES(properties),
            updated_at = VALUES(updated_at),
            deleted_at = VALUES(deleted_at)
        """,
        (
            user.get("id"),
            user.get("username"),
            user.get("displayName"),
            user.get("status"),
            serializable_json(user.get("dataScopes"), {}),
            serializable_json(user.get("properties"), {}),
            mysql_datetime(user.get("createdAt")),
            mysql_datetime(user.get("updatedAt")),
            mysql_datetime(user.get("deletedAt")),
        ),
    )
    user_id = str(user.get("id") or "")
    cur.execute("DELETE FROM admin_user_roles WHERE admin_user_id = %s", (user_id,))
    role_codes = compact_list(user.get("roles"))
    if role_codes:
        placeholders = ", ".join(["%s"] * len(role_codes))
        cur.execute(
            "INSERT IGNORE INTO admin_user_roles (admin_user_id, admin_role_id) "
            f"SELECT %s, id FROM admin_roles WHERE role_code IN ({placeholders})",
            tuple([user_id, *role_codes]),
        )


def upsert_users_mysql(users: list[dict[str, Any]]) -> None:
    if not users:
        return
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            for user in users:
                execute_upsert_user_mysql(cur, user)
        conn.commit()


def load_all_users() -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_users_mysql(include_deleted=True)
    if use_postgis():
        return fetch_users_postgis(include_deleted=True)
    return load_json_records(admin_users_json_path())


def load_users() -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_users_mysql()
    if use_postgis():
        return fetch_users_postgis()
    return [user for user in load_all_users() if not user.get("deletedAt")]


def save_users(users: list[dict[str, Any]]) -> None:
    if use_mysql():
        upsert_users_mysql(users)
        return
    if use_postgis():
        upsert_users_postgis(users)
        return
    with database.JSON_STORE_LOCK:
        save_json_records(admin_users_json_path(), users)


def save_user(user: dict[str, Any]) -> None:
    if use_mysql() or use_postgis():
        save_users([user])
        return
    users = load_all_users()
    for index, existing in enumerate(users):
        if str(existing.get("id")) == str(user.get("id")):
            users[index] = user
            break
    else:
        users.append(user)
    save_users(users)


def text_matches(user: dict[str, Any], q: str) -> bool:
    if not q:
        return True
    haystack = " ".join(
        [
            str(user.get("username") or ""),
            str(user.get("displayName") or ""),
            " ".join(user.get("roles") or []),
            json.dumps(user.get("dataScopes") or {}, ensure_ascii=False),
            json.dumps(user.get("properties") or {}, ensure_ascii=False),
        ]
    ).lower()
    return q.lower() in haystack


def user_matches(user: dict[str, Any], filters: UserFilters) -> bool:
    if filters.status and user.get("status") != filters.status:
        return False
    if filters.role and filters.role not in (user.get("roles") or []):
        return False
    return text_matches(user, filters.q)


def find_user(user_id: str) -> dict[str, Any] | None:
    if use_mysql():
        return first_user_mysql(user_id=user_id)
    if use_postgis():
        return first_user_postgis(user_id=user_id)
    for user in load_users():
        if str(user.get("id")) == str(user_id):
            return user
    return None


def user_by_username(username: str) -> dict[str, Any] | None:
    normalized = canonical_username(username)
    if not normalized:
        return None
    if use_mysql():
        return first_user_mysql(username=normalized)
    if use_postgis():
        return first_user_postgis(username=normalized)
    for user in load_users():
        if canonical_username(user.get("username")) == normalized:
            return user
    return None


def roles_for_user(username: str) -> list[str]:
    user = user_by_username(username)
    if user is None or user.get("status") not in ("active", None, ""):
        return []
    return compact_list(user.get("roles") or [])


def data_scopes_for_user(username: str) -> dict[str, list[str]]:
    user = user_by_username(username)
    if user is None or user.get("status") not in ("active", None, ""):
        return {}
    scopes = user.get("dataScopes") or {}
    if not isinstance(scopes, dict):
        return {}
    return {str(key): sorted(split_header_list(value)) for key, value in scopes.items() if split_header_list(value)}


@router.get("/users")
def list_users(filters: UserFilters = Depends(filter_params), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.users.view")
    if filters.includeDeleted:
        require_permission(context, "system.users.restore")
    if use_mysql():
        return {
            "items": fetch_users_mysql(
                filters=filters,
                include_deleted=filters.includeDeleted,
                limit=filters.limit,
                offset=filters.offset,
            ),
            "total": count_users_mysql(filters),
            "limit": filters.limit,
            "offset": filters.offset,
        }
    if use_postgis():
        return {
            "items": fetch_users_postgis(
                filters=filters,
                include_deleted=filters.includeDeleted,
                limit=filters.limit,
                offset=filters.offset,
            ),
            "total": count_users_postgis(filters),
            "limit": filters.limit,
            "offset": filters.offset,
        }
    source_users = load_all_users() if filters.includeDeleted else load_users()
    users = [user for user in source_users if user_matches(user, filters)]
    return {
        "items": users[filters.offset : filters.offset + filters.limit],
        "total": len(users),
        "limit": filters.limit,
        "offset": filters.offset,
    }


@router.post("/users")
def create_user(payload: AdminUserIn, context: AuthContext = Depends(request_context)) -> AdminUserOut:
    require_permission(context, "system.users.create")
    if user_by_username(payload.username):
        raise HTTPException(status_code=409, detail="username already exists")
    user = normalize_user(payload.model_dump())
    user = append_user_audit_event(
        user,
        "create",
        context,
        changed_fields=["username", "displayName", "status", "roles", "dataScopes", "properties"],
    )
    if use_mysql() or use_postgis():
        save_users([user])
        return AdminUserOut.model_validate(user)
    users = load_all_users()
    users.append(user)
    save_users(users)
    return AdminUserOut.model_validate(user)


@router.get("/users/events")
def list_user_events(
    q: str = Query(default=""),
    action: str = Query(default=""),
    username: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.users.view")
    records = list_user_event_records(q=q, action=action, username=username)
    page = records[offset : offset + limit]
    return {
        "items": page,
        "total": len(records),
        "limit": limit,
        "offset": offset,
    }


@router.get("/users/events.csv")
def export_user_events_csv(
    q: str = Query(default=""),
    action: str = Query(default=""),
    username: str = Query(default=""),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "system.users.export")
    records = list_user_event_records(q=q, action=action, username=username)
    return csv_download_response(
        "user-events.csv",
        ["eventId", "userId", "username", "displayName", "action", "actor", "at", "changedFields", "roles", "dataScopes", "summary"],
        records,
    )


def merge_preview_data_scopes(role_scopes: dict[str, list[str]], user_scopes: dict[str, Any]) -> dict[str, list[str]]:
    from .admin_roles import merge_scope_values

    merged = {str(key): list(values or []) for key, values in role_scopes.items()}
    if not isinstance(user_scopes, dict):
        return merged
    for key, value in user_scopes.items():
        scope_key = str(key)
        merged.setdefault(scope_key, [])
        merged[scope_key] = merge_scope_values(merged[scope_key], value)
    return {key: value for key, value in merged.items() if value}


def user_effective_permissions_preview(
    *,
    user_id: str = "",
    username: str = "",
    status: str = "active",
    roles: list[str] | None = None,
    data_scopes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .admin_roles import (
        ADMIN_MENU_MODULES,
        data_scopes_for_roles,
        direct_permission_codes,
        expand_permission_codes,
        invalid_role_entries,
        menu_modules_allowed_by_permissions,
        module_catalog_by_key,
        permission_catalog,
        permission_satisfied_by,
        permissions_for_roles,
        role_by_code,
        union_ordered,
        unknown_role_entries,
    )

    role_codes = compact_list(roles or [])
    built_in_operator = "operator" in role_codes or "gis-admin" in role_codes
    permissions = [item["code"] for item in permission_catalog()] if built_in_operator else permissions_for_roles(role_codes)
    direct_permissions = direct_permission_codes(role_codes)
    union_ordered(permissions, direct_permissions)
    permissions = expand_permission_codes(permissions)
    modules_by_key = module_catalog_by_key()

    configured_menu_modules: list[str] = [module["key"] for module in ADMIN_MENU_MODULES] if built_in_operator else []
    for role_code in role_codes:
        role = role_by_code(role_code)
        if role is None or role.get("status") not in ("active", None, ""):
            continue
        union_ordered(configured_menu_modules, role.get("menuModules") or [])
    if direct_permissions:
        direct_permission_set = set(expand_permission_codes(direct_permissions))
        union_ordered(
            configured_menu_modules,
            [
                module["key"]
                for module in ADMIN_MENU_MODULES
                if permission_satisfied_by(direct_permission_set, str(module.get("permission") or ""))
            ],
        )

    menu_modules = menu_modules_allowed_by_permissions(configured_menu_modules, permissions)
    effective_keys = set(menu_modules)
    permission_set = set(permissions)
    blocked_menu_modules = []
    for key in configured_menu_modules:
        if key in effective_keys:
            continue
        module = modules_by_key.get(key)
        if not module:
            continue
        required_permission = str(module.get("permission") or "")
        blocked_menu_modules.append(
            {
                **module,
                "missingEntryPermission": required_permission if required_permission and not permission_satisfied_by(permission_set, required_permission) else "",
            }
        )

    return {
        "userId": user_id,
        "user": username,
        "status": status or "active",
        "roles": role_codes,
        "permissions": permissions,
        "configuredMenuModules": configured_menu_modules,
        "menuModules": menu_modules,
        "visibleMenuModules": [modules_by_key[key] for key in menu_modules if key in modules_by_key],
        "blockedMenuModules": blocked_menu_modules,
        "dataScopes": merge_preview_data_scopes(data_scopes_for_roles(role_codes), data_scopes or {}),
        "unknownRoles": unknown_role_entries(role_codes),
        "invalidRoles": invalid_role_entries(role_codes),
    }


def user_access_receipt(user: dict[str, Any]) -> dict[str, Any]:
    username = str(user.get("username") or "")
    effective_access = user_effective_permissions_preview(
        user_id=str(user.get("id") or ""),
        username=username,
        status=str(user.get("status") or "active"),
        roles=compact_list(user.get("roles") or []),
        data_scopes=user.get("dataScopes") or {},
    )
    return {
        "receiptType": "user-effective-access",
        "exportedAt": now_iso(),
        "user": AdminUserOut.model_validate(user).model_dump(mode="json"),
        "effectiveAccess": effective_access,
        "effectivePermissionCoverage": role_effective_permission_coverage(
            effective_access.get("configuredMenuModules") or [],
            effective_access.get("permissions") or [],
        ),
    }


USER_OPERATION_QUEUE_STAGES = [
    {
        "key": "blocked_users",
        "label": "角色阻断账号",
        "description": "账号绑定了未知、停用或已删除角色，实际后台入口会被阻断。",
        "tone": "danger",
        "requiredPermission": "system.users.update",
        "primaryActionLabel": "修复账号",
    },
    {
        "key": "review_users",
        "label": "待授权账号",
        "description": "账号尚未绑定角色或账号状态需要复核，不能形成稳定权限边界。",
        "tone": "warning",
        "requiredPermission": "system.users.update",
        "primaryActionLabel": "分配角色",
    },
    {
        "key": "empty_scope_users",
        "label": "待补数据范围",
        "description": "账号已有有效角色，但角色与账号都没有配置可见区域、项目或林班范围。",
        "tone": "review",
        "requiredPermission": "system.users.update",
        "primaryActionLabel": "配置范围",
    },
    {
        "key": "ready_users",
        "label": "已闭环账号",
        "description": "账号角色有效，数据范围已落位，可导出账号权限回执。",
        "tone": "ready",
        "requiredPermission": "system.users.export",
        "primaryActionLabel": "查看回执",
    },
]


def user_operation_stage_by_key(key: str) -> dict[str, str]:
    return next((stage for stage in USER_OPERATION_QUEUE_STAGES if stage["key"] == key), USER_OPERATION_QUEUE_STAGES[-1])


def data_scope_value_count(data_scopes: dict[str, Any] | None) -> int:
    if not isinstance(data_scopes, dict):
        return 0
    return sum(len(split_header_list(value)) for value in data_scopes.values())


def user_operation_stage_key(user: dict[str, Any], effective_access: dict[str, Any]) -> str:
    role_codes = compact_list(user.get("roles") or [])
    status = str(user.get("status") or "active")
    if effective_access.get("unknownRoles") or effective_access.get("invalidRoles"):
        return "blocked_users"
    if not role_codes or status not in ("active", ""):
        return "review_users"
    if data_scope_value_count(effective_access.get("dataScopes") or {}) == 0:
        return "empty_scope_users"
    return "ready_users"


def user_operation_admin_href(user: dict[str, Any], lane_key: str) -> str:
    username = str(user.get("username") or "")
    user_id = str(user.get("id") or "")
    return f"admin-users.html?userQueue={quote(lane_key)}&username={quote(username)}&userId={quote(user_id)}"


def user_operation_risk_level(stage_key: str) -> str:
    if stage_key == "blocked_users":
        return "error"
    if stage_key == "ready_users":
        return "ready"
    return "warning"


def user_operation_summary(user: dict[str, Any], effective_access: dict[str, Any], stage_key: str) -> str:
    if stage_key == "blocked_users":
        return (
            f"未知角色 {len(effective_access.get('unknownRoles') or [])} 个，"
            f"失效角色 {len(effective_access.get('invalidRoles') or [])} 个"
        )
    if stage_key == "review_users":
        if not compact_list(user.get("roles") or []):
            return "账号尚未绑定任何角色"
        return f"账号状态为 {user.get('status') or 'active'}，需要复核是否启用"
    if stage_key == "empty_scope_users":
        return "有效权限已生成，但没有区域、项目、村镇或林班数据范围"
    return (
        f"有效菜单 {len(effective_access.get('menuModules') or [])} 个，"
        f"有效权限 {len(effective_access.get('permissions') or [])} 项，"
        f"数据范围 {data_scope_value_count(effective_access.get('dataScopes') or {})} 项"
    )


def user_operation_queue_item(user: dict[str, Any], effective_access: dict[str, Any], lane: dict[str, str]) -> dict[str, Any]:
    lane_key = str(lane.get("key") or "")
    data_scope_count = data_scope_value_count(effective_access.get("dataScopes") or {})
    return {
        "itemType": "user",
        "userId": user.get("id"),
        "username": user.get("username") or "",
        "displayName": user.get("displayName") or user.get("username") or "",
        "status": user.get("status") or "active",
        "riskLevel": user_operation_risk_level(lane_key),
        "summary": user_operation_summary(user, effective_access, lane_key),
        "roleCount": len(compact_list(user.get("roles") or [])),
        "unknownRoleCount": len(effective_access.get("unknownRoles") or []),
        "invalidRoleCount": len(effective_access.get("invalidRoles") or []),
        "menuModuleCount": len(effective_access.get("menuModules") or []),
        "permissionCount": len(effective_access.get("permissions") or []),
        "dataScopeValueCount": data_scope_count,
        "updatedAt": user.get("updatedAt") or user.get("createdAt") or "",
        "adminHref": user_operation_admin_href(user, lane_key),
        "requiredPermission": lane.get("requiredPermission") or "system.users.view",
    }


def user_operation_queue_lane(stage: dict[str, str], lane_items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    return {
        "key": stage["key"],
        "label": stage["label"],
        "description": stage["description"],
        "tone": stage["tone"],
        "requiredPermission": stage["requiredPermission"],
        "primaryActionLabel": stage["primaryActionLabel"],
        "count": len(lane_items),
        "items": lane_items[:limit],
    }


def user_operation_queue(limit: int = 5) -> dict[str, Any]:
    lanes: dict[str, list[dict[str, Any]]] = {stage["key"]: [] for stage in USER_OPERATION_QUEUE_STAGES}
    for user in load_users():
        effective_access = user_effective_permissions_preview(
            user_id=str(user.get("id") or ""),
            username=str(user.get("username") or ""),
            status=str(user.get("status") or "active"),
            roles=compact_list(user.get("roles") or []),
            data_scopes=user.get("dataScopes") or {},
        )
        stage_key = user_operation_stage_key(user, effective_access)
        stage = user_operation_stage_by_key(stage_key)
        lanes[stage_key].append(user_operation_queue_item(user, effective_access, stage))

    for lane_items in lanes.values():
        lane_items.sort(key=lambda item: (str(item.get("updatedAt") or ""), str(item.get("username") or "")), reverse=True)

    items = [user_operation_queue_lane(stage, lanes[stage["key"]], limit) for stage in USER_OPERATION_QUEUE_STAGES]
    blocked_total = len(lanes["blocked_users"])
    review_total = len(lanes["review_users"])
    empty_scope_total = len(lanes["empty_scope_users"])
    ready_total = len(lanes["ready_users"])
    actionable_total = blocked_total + review_total + empty_scope_total
    summary = {
        "blockedUserTotal": blocked_total,
        "reviewUserTotal": review_total,
        "emptyScopeUserTotal": empty_scope_total,
        "readyUserTotal": ready_total,
        "actionableQueueTotal": actionable_total,
        "operationQueueTotal": actionable_total + ready_total,
    }
    return {
        "items": items,
        "operationQueue": items,
        "summary": summary,
        "limit": limit,
    }


@router.get("/users/operation-queue")
def get_user_operation_queue(
    limit: int = Query(default=5, ge=1, le=20),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.users.view")
    return user_operation_queue(limit=limit)


@router.post("/users/effective-permissions/preview")
def preview_user_effective_permissions(payload: AdminUserEffectivePreviewIn, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_any_permission(context, ["system.users.create", "system.users.update"])
    return user_effective_permissions_preview(
        username=str(payload.username or ""),
        status=str(payload.status or "active"),
        roles=payload.roles,
        data_scopes=payload.dataScopes,
    )


@router.get("/users/{user_id}/access-receipt.json")
def export_user_access_receipt(user_id: str, context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "system.users.export")
    user = find_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    username = safe_download_stem(str(user.get("username") or user_id), "user")
    return json_download_response(
        f"user-access-receipt-{username}.json",
        user_access_receipt(user),
    )


@router.get("/users/{user_id}/effective-permissions")
def get_user_effective_permissions(user_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.users.view")
    user = find_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    username = str(user.get("username") or "")
    return user_effective_permissions_preview(
        user_id=str(user.get("id") or ""),
        username=username,
        status=str(user.get("status") or "active"),
        roles=compact_list(user.get("roles") or []),
        data_scopes=user.get("dataScopes") or {},
    )


@router.get("/users/{user_id}")
def get_user(user_id: str, context: AuthContext = Depends(request_context)) -> AdminUserOut:
    require_permission(context, "system.users.view")
    user = find_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserOut.model_validate(user)


def patched_user(
    user: dict[str, Any],
    user_id: str,
    payload: AdminUserPatch,
    context: AuthContext,
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    updated = normalize_user(
        {
            **user,
            **changes,
            "id": user_id,
            "username": user.get("username"),
            "createdAt": user.get("createdAt", now_iso()),
            "deletedAt": user.get("deletedAt"),
        }
    )
    changed_fields = user_changed_fields(user, updated)
    return append_user_audit_event(
        updated,
        "update",
        context,
        before=user,
        changed_fields=changed_fields,
    )


@router.patch("/users/{user_id}")
def patch_user(user_id: str, payload: AdminUserPatch, context: AuthContext = Depends(request_context)) -> AdminUserOut:
    require_permission(context, "system.users.update")
    if use_mysql():
        with mysql_connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"{MYSQL_SELECT_SQL} WHERE au.id = %s AND au.deleted_at IS NULL FOR UPDATE",
                        (user_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        conn.rollback()
                        raise HTTPException(status_code=404, detail="User not found")
                    updated = patched_user(
                        normalize_postgis_user_row(row),
                        user_id,
                        payload,
                        context,
                    )
                    execute_upsert_user_mysql(cur, updated)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AdminUserOut.model_validate(updated)
    if use_postgis():
        with postgis_connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"{POSTGIS_SELECT_SQL} WHERE id = %s AND deleted_at IS NULL FOR UPDATE",
                        (user_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        conn.rollback()
                        raise HTTPException(status_code=404, detail="User not found")
                    updated = patched_user(
                        normalize_postgis_user_row(row),
                        user_id,
                        payload,
                        context,
                    )
                    execute_upsert_user_postgis(cur, updated)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AdminUserOut.model_validate(updated)
    with database.JSON_STORE_LOCK:
        users = load_json_records(admin_users_json_path())
        for index, user in enumerate(users):
            if str(user.get("id")) != str(user_id) or user.get("deletedAt"):
                continue
            updated = patched_user(user, user_id, payload, context)
            users[index] = updated
            save_json_records(admin_users_json_path(), users)
            return AdminUserOut.model_validate(updated)
    raise HTTPException(status_code=404, detail="User not found")


def set_temporary_password(user: dict[str, Any], temporary_password: str) -> None:
    errors = password_errors(temporary_password)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    credential = temporary_password_credential(
        user,
        hash_password(temporary_password),
        credential_for_user(str(user["id"])),
    )
    save_credential(credential)


def temporary_password_credential(
    user: dict[str, Any],
    temporary_password_hash: str,
    credential: dict[str, Any] | None,
) -> dict[str, Any]:
    now = utc_now()
    if credential is None:
        credential = new_credential(str(user["id"]), temporary_password_hash)
    else:
        credential["passwordHash"] = temporary_password_hash
        credential["credentialVersion"] += 1
    credential["passwordChangedAt"] = iso_utc(now)
    credential["mustChangePassword"] = True
    credential["failedLoginCount"] = 0
    credential["lockedUntil"] = None
    credential["updatedAt"] = iso_utc(now)
    return credential


def security_audit_fields(include_password: bool) -> list[str]:
    fields = ["sessions"]
    if include_password:
        fields = [
            "passwordHash", "passwordChangedAt", "mustChangePassword", "failedLoginCount",
            "lockedUntil", "credentialVersion", *fields,
        ]
    return fields


def mysql_user_for_update(cur: Any, user_id: str) -> dict[str, Any] | None:
    cur.execute(
        f"{MYSQL_SELECT_SQL} WHERE au.id = %s AND au.deleted_at IS NULL FOR UPDATE",
        (user_id,),
    )
    row = cur.fetchone()
    return normalize_postgis_user_row(row) if row is not None else None


def apply_account_security_action(
    user_id: str,
    context: AuthContext,
    *,
    temporary_password_hash: str | None = None,
) -> int:
    include_password = temporary_password_hash is not None
    action = "set_password" if include_password else "revoke_sessions"
    if use_mysql():
        with mysql_connect() as conn:
            try:
                with conn.cursor() as cur:
                    user = mysql_user_for_update(cur, user_id)
                    if user is None:
                        raise HTTPException(status_code=404, detail="User not found")
                    if include_password:
                        credential = mysql_credential_for_user(cur, user_id, lock=True)
                        write_mysql_credential(
                            cur,
                            temporary_password_credential(
                                user, temporary_password_hash, credential
                            ),
                        )
                    revoked = revoke_user_sessions_mysql(cur, user_id)
                    audited = append_user_audit_event(
                        user, action, context, changed_fields=security_audit_fields(include_password)
                    )
                    execute_upsert_user_mysql(cur, audited)
                conn.commit()
                return revoked
            except Exception:
                conn.rollback()
                raise
    if use_postgis():
        raise HTTPException(
            status_code=501,
            detail="Human credential administration requires MySQL or JSON development storage",
        )
    with json_transaction([admin_users_json_path(), admin_credentials_json_path(), admin_sessions_json_path()]):
        users = load_json_records(admin_users_json_path())
        user_index = next(
            (
                index
                for index, candidate in enumerate(users)
                if str(candidate.get("id")) == user_id and not candidate.get("deletedAt")
            ),
            None,
        )
        if user_index is None:
            raise HTTPException(status_code=404, detail="User not found")
        user = users[user_index]
        if include_password:
            credential = next(
                (
                    item
                    for item in load_json_records(admin_credentials_json_path())
                    if str(item.get("userId")) == user_id
                ),
                None,
            )
            save_credential(
                temporary_password_credential(
                    user, temporary_password_hash, credential
                )
            )
        revoked = revoke_user_sessions(user_id)
        audited = append_user_audit_event(
            user, action, context, changed_fields=security_audit_fields(include_password)
        )
        users[user_index] = audited
        save_json_records(admin_users_json_path(), users)
        return revoked


@router.post("/users/{user_id}/set-password")
def set_user_password(
    user_id: str,
    payload: TemporaryPasswordIn,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.users.setPassword")
    if use_postgis():
        raise HTTPException(status_code=501, detail="Human credential administration requires MySQL or JSON development storage")
    errors = password_errors(payload.temporaryPassword)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    try:
        temporary_password_hash = hash_password_bounded(payload.temporaryPassword)
    except PasswordOperationBusy as exc:
        raise HTTPException(
            status_code=429,
            detail="Password processing is busy; retry shortly",
        ) from exc
    apply_account_security_action(
        user_id,
        context,
        temporary_password_hash=temporary_password_hash,
    )
    return {"ok": True, "mustChangePassword": True}


@router.post("/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.users.revokeSessions")
    if use_postgis():
        raise HTTPException(status_code=501, detail="Human credential administration requires MySQL or JSON development storage")
    revoked = apply_account_security_action(user_id, context)
    return {"ok": True, "revoked": revoked}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.users.delete")
    if use_mysql() or use_postgis():
        user = find_user(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        deleted_at = now_iso()
        deleted_user = {**user, "deletedAt": deleted_at, "updatedAt": deleted_at}
        deleted_user = append_user_audit_event(
            deleted_user,
            "delete",
            context,
            before=user,
            changed_fields=["deletedAt"],
        )
        save_users([deleted_user])
        return {"ok": True, "deleted": user_id}
    users = load_all_users()
    for index, user in enumerate(users):
        if str(user.get("id")) != str(user_id) or user.get("deletedAt"):
            continue
        deleted_at = now_iso()
        deleted_user = {**user, "deletedAt": deleted_at, "updatedAt": deleted_at}
        deleted_user = append_user_audit_event(
            deleted_user,
            "delete",
            context,
            before=user,
            changed_fields=["deletedAt"],
        )
        users[index] = deleted_user
        save_users(users)
        return {"ok": True, "deleted": user_id}
    raise HTTPException(status_code=404, detail="User not found")


@router.post("/users/{user_id}/restore")
def restore_user(user_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.users.restore")
    if use_mysql() or use_postgis():
        user = (
            first_user_mysql(user_id=user_id, include_deleted=True)
            if use_mysql()
            else first_user_postgis(user_id=user_id, include_deleted=True)
        )
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if not user.get("deletedAt"):
            raise HTTPException(status_code=409, detail="User is not deleted")
        duplicate = (
            first_user_mysql(username=str(user.get("username") or ""))
            if use_mysql()
            else first_user_postgis(username=str(user.get("username") or ""))
        )
        if duplicate is not None and str(duplicate.get("id")) != str(user_id):
            raise HTTPException(status_code=409, detail="username already exists")
        restored_at = now_iso()
        restored = {**user, "deletedAt": None, "updatedAt": restored_at}
        restored = append_user_audit_event(
            restored,
            "restore",
            context,
            before=user,
            changed_fields=["deletedAt"],
        )
        save_users([restored])
        return {"ok": True, "restored": user_id, "user": restored}
    users = load_all_users()
    for index, user in enumerate(users):
        if str(user.get("id")) != str(user_id):
            continue
        if not user.get("deletedAt"):
            raise HTTPException(status_code=409, detail="User is not deleted")
        duplicate = next(
            (
                item
                for item in users
                if str(item.get("id")) != str(user_id)
                and not item.get("deletedAt")
                and str(item.get("username") or "") == str(user.get("username") or "")
            ),
            None,
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="username already exists")
        restored_at = now_iso()
        restored = {**user, "deletedAt": None, "updatedAt": restored_at}
        restored = append_user_audit_event(
            restored,
            "restore",
            context,
            before=user,
            changed_fields=["deletedAt"],
        )
        users[index] = restored
        save_users(users)
        return {"ok": True, "restored": user_id, "user": restored}
    raise HTTPException(status_code=404, detail="User not found")
