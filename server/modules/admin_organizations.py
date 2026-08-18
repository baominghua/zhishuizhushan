from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from . import database
from .admin_roles import require_permission
from .auth import AuthContext, request_context, split_header_list
from .database import (
    admin_organizations_json_path,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
    use_postgis,
)
from .settings import get_settings


router = APIRouter(prefix="/api/admin", tags=["admin-organizations"])

ORGANIZATION_TYPES = {
    "platform",
    "government",
    "department",
    "town",
    "village",
    "enterprise",
    "cooperative",
    "project",
    "team",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact(value: str | None) -> str:
    return str(value or "").strip()


def json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def mysql_datetime(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value or None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


class OrganizationBase(BaseModel):
    organizationCode: str = Field(min_length=1, max_length=96)
    name: str = Field(min_length=1, max_length=200)
    shortName: str | None = None
    parentId: str | None = None
    organizationType: str = "department"
    status: str = "active"
    sortOrder: int = 0
    leader: str | None = None
    phone: str | None = None
    address: str | None = None
    administrativeDivisionCode: str | None = None
    dataScopes: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("organizationCode", "name", mode="after")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("organizationType", mode="after")
    @classmethod
    def valid_type(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in ORGANIZATION_TYPES:
            raise ValueError("unsupported organization type")
        return normalized


class OrganizationIn(OrganizationBase):
    model_config = {"extra": "forbid"}


class OrganizationPatch(BaseModel):
    name: str | None = None
    shortName: str | None = None
    parentId: str | None = None
    organizationType: str | None = None
    status: str | None = None
    sortOrder: int | None = None
    leader: str | None = None
    phone: str | None = None
    address: str | None = None
    administrativeDivisionCode: str | None = None
    dataScopes: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None

    @field_validator("organizationType", mode="after")
    @classmethod
    def valid_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized not in ORGANIZATION_TYPES:
            raise ValueError("unsupported organization type")
        return normalized

    model_config = {"extra": "forbid"}


class OrganizationOut(OrganizationBase):
    id: str
    createdAt: str
    updatedAt: str
    deletedAt: str | None = None
    userCount: int = 0
    childCount: int = 0


POSTGIS_SELECT = """
SELECT id::text, organization_code, name, short_name, parent_id::text,
       organization_type, status, sort_order, leader, phone, address,
       administrative_division_code, data_scopes, properties,
       created_at, updated_at, deleted_at
FROM admin_organizations
"""

MYSQL_SELECT = """
SELECT id, organization_code, name, short_name, parent_id,
       organization_type, status, sort_order, leader, phone, address,
       administrative_division_code, data_scopes, properties,
       created_at, updated_at, deleted_at
FROM admin_organizations
"""

COLUMNS = (
    "id", "organizationCode", "name", "shortName", "parentId",
    "organizationType", "status", "sortOrder", "leader", "phone", "address",
    "administrativeDivisionCode", "dataScopes", "properties",
    "createdAt", "updatedAt", "deletedAt",
)


def postgis_connect():
    try:
        import psycopg
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"organization database requires psycopg. {exc}") from exc
    return psycopg.connect(get_settings().database_url)


def row_to_organization(row: Any) -> dict[str, Any]:
    values = dict(row) if hasattr(row, "keys") else dict(zip(COLUMNS, row))
    result: dict[str, Any] = {}
    for key in COLUMNS:
        value = values.get(key)
        if key in {"dataScopes", "properties"}:
            value = json_value(value, {})
        elif key in {"createdAt", "updatedAt", "deletedAt"} and isinstance(value, datetime):
            value = value.isoformat()
        result[key] = value
    result["parentId"] = result.get("parentId") or None
    result["dataScopes"] = result.get("dataScopes") or {}
    result["properties"] = result.get("properties") or {}
    return result


def load_all_organizations() -> list[dict[str, Any]]:
    if use_mysql():
        with mysql_connect() as conn, conn.cursor() as cur:
            cur.execute(MYSQL_SELECT)
            return [row_to_organization(row) for row in cur.fetchall()]
    if use_postgis():
        with postgis_connect() as conn, conn.cursor() as cur:
            cur.execute(POSTGIS_SELECT)
            return [row_to_organization(row) for row in cur.fetchall()]
    return load_json_records(admin_organizations_json_path())


def data_scopes_for_organization_ids(organization_ids: list[str] | set[str]) -> dict[str, list[str]]:
    """Merge active organization scopes, including parent organizations."""
    records = {
        str(record.get("id")): record
        for record in load_all_organizations()
        if not record.get("deletedAt") and record.get("status") in ("active", None, "")
    }
    scopes: dict[str, list[str]] = {}
    visited: set[str] = set()
    pending = [str(item).strip() for item in organization_ids if str(item).strip()]
    while pending:
        organization_id = pending.pop()
        if organization_id in visited:
            continue
        visited.add(organization_id)
        organization = records.get(organization_id)
        if organization is None:
            continue
        for key, value in (organization.get("dataScopes") or {}).items():
            current = scopes.setdefault(str(key), [])
            for scope_value in sorted(split_header_list(value)):
                if scope_value not in current:
                    current.append(scope_value)
        parent_id = compact(organization.get("parentId"))
        if parent_id:
            pending.append(parent_id)
    return {key: value for key, value in scopes.items() if value}


def save_organization(record: dict[str, Any]) -> None:
    values = (
        record["id"], record["organizationCode"], record["name"], record.get("shortName"),
        record.get("parentId"), record.get("organizationType") or "department",
        record.get("status") or "active", int(record.get("sortOrder") or 0), record.get("leader"),
        record.get("phone"), record.get("address"), record.get("administrativeDivisionCode"),
        json.dumps(record.get("dataScopes") or {}, ensure_ascii=False),
        json.dumps(record.get("properties") or {}, ensure_ascii=False),
        record["createdAt"], record["updatedAt"], record.get("deletedAt"),
    )
    if use_mysql():
        db_values = values[:-3] + tuple(mysql_datetime(value) for value in values[-3:])
        with mysql_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO admin_organizations (
                    id, organization_code, name, short_name, parent_id, organization_type,
                    status, sort_order, leader, phone, address, administrative_division_code,
                    data_scopes, properties, created_at, updated_at, deleted_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE name=VALUES(name), short_name=VALUES(short_name),
                    parent_id=VALUES(parent_id), organization_type=VALUES(organization_type),
                    status=VALUES(status), sort_order=VALUES(sort_order), leader=VALUES(leader),
                    phone=VALUES(phone), address=VALUES(address),
                    administrative_division_code=VALUES(administrative_division_code),
                    data_scopes=VALUES(data_scopes), properties=VALUES(properties),
                    updated_at=VALUES(updated_at), deleted_at=VALUES(deleted_at)""",
                db_values,
            )
            conn.commit()
        return
    if use_postgis():
        with postgis_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO admin_organizations (
                    id, organization_code, name, short_name, parent_id, organization_type,
                    status, sort_order, leader, phone, address, administrative_division_code,
                    data_scopes, properties, created_at, updated_at, deleted_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, short_name=EXCLUDED.short_name,
                    parent_id=EXCLUDED.parent_id, organization_type=EXCLUDED.organization_type,
                    status=EXCLUDED.status, sort_order=EXCLUDED.sort_order, leader=EXCLUDED.leader,
                    phone=EXCLUDED.phone, address=EXCLUDED.address,
                    administrative_division_code=EXCLUDED.administrative_division_code,
                    data_scopes=EXCLUDED.data_scopes, properties=EXCLUDED.properties,
                    updated_at=EXCLUDED.updated_at, deleted_at=EXCLUDED.deleted_at""",
                values,
            )
            conn.commit()
        return
    records = load_json_records(admin_organizations_json_path())
    index = next((i for i, item in enumerate(records) if item.get("id") == record["id"]), None)
    if index is None:
        records.append(record)
    else:
        records[index] = record
    save_json_records(admin_organizations_json_path(), records)


def normalize_organization(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        **(existing or {}),
        **payload,
        "id": (existing or {}).get("id") or str(uuid.uuid4()),
        "organizationCode": compact(payload.get("organizationCode") or (existing or {}).get("organizationCode")),
        "name": compact(payload.get("name") or (existing or {}).get("name")),
        "parentId": compact(payload.get("parentId")) or None,
        "createdAt": (existing or {}).get("createdAt") or timestamp,
        "updatedAt": timestamp,
        "deletedAt": (existing or {}).get("deletedAt"),
        "dataScopes": dict(payload.get("dataScopes") or {}),
        "properties": dict(payload.get("properties") or {}),
    }


def user_organization_counts() -> dict[str, int]:
    from .admin_users import load_users

    counts: dict[str, int] = {}
    for user in load_users():
        properties = user.get("properties") if isinstance(user.get("properties"), dict) else {}
        ids = [properties.get("organizationId"), *(properties.get("organizationIds") or [])]
        for organization_id in set(compact(item) for item in ids if compact(item)):
            counts[organization_id] = counts.get(organization_id, 0) + 1
    return counts


def enrich(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    user_counts = user_organization_counts()
    child_counts: dict[str, int] = {}
    for record in records:
        parent_id = compact(record.get("parentId"))
        if parent_id and not record.get("deletedAt"):
            child_counts[parent_id] = child_counts.get(parent_id, 0) + 1
    return [
        {**record, "userCount": user_counts.get(str(record.get("id")), 0), "childCount": child_counts.get(str(record.get("id")), 0)}
        for record in records
    ]


def validate_parent(record: dict[str, Any], records: list[dict[str, Any]]) -> None:
    parent_id = record.get("parentId")
    if not parent_id:
        return
    active_by_id = {str(item.get("id")): item for item in records if not item.get("deletedAt")}
    if parent_id not in active_by_id:
        raise HTTPException(status_code=422, detail="Parent organization does not exist")
    cursor = parent_id
    visited = {str(record.get("id"))}
    while cursor:
        if cursor in visited:
            raise HTTPException(status_code=422, detail="Organization hierarchy cannot contain a cycle")
        visited.add(cursor)
        cursor = compact(active_by_id.get(cursor, {}).get("parentId"))


def organization_or_404(organization_id: str) -> dict[str, Any]:
    record = next((item for item in load_all_organizations() if str(item.get("id")) == organization_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return record


@router.get("/organizations")
def list_organizations(
    q: str = Query(default=""),
    status: str = Query(default=""),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.organizations.view")
    if includeDeleted:
        require_permission(context, "system.organizations.restore")
    query = q.strip().lower()
    records = [
        item for item in load_all_organizations()
        if (includeDeleted or not item.get("deletedAt"))
        and (not status or item.get("status") == status)
        and (not query or query in " ".join(str(item.get(key) or "") for key in ("organizationCode", "name", "shortName", "leader")).lower())
    ]
    records.sort(key=lambda item: (str(item.get("parentId") or ""), int(item.get("sortOrder") or 0), str(item.get("name") or "")))
    enriched = enrich(records)
    return {"items": enriched[offset : offset + limit], "total": len(enriched), "limit": limit, "offset": offset}


@router.post("/organizations")
def create_organization(payload: OrganizationIn, context: AuthContext = Depends(request_context)) -> OrganizationOut:
    require_permission(context, "system.organizations.create")
    records = load_all_organizations()
    if any(item.get("organizationCode") == payload.organizationCode and not item.get("deletedAt") for item in records):
        raise HTTPException(status_code=409, detail="organizationCode already exists")
    record = normalize_organization(payload.model_dump())
    validate_parent(record, records)
    save_organization(record)
    return OrganizationOut.model_validate(enrich([record])[0])


@router.get("/organizations/{organization_id}")
def get_organization(organization_id: str, context: AuthContext = Depends(request_context)) -> OrganizationOut:
    require_permission(context, "system.organizations.view")
    return OrganizationOut.model_validate(enrich([organization_or_404(organization_id)])[0])


@router.patch("/organizations/{organization_id}")
def update_organization(organization_id: str, payload: OrganizationPatch, context: AuthContext = Depends(request_context)) -> OrganizationOut:
    require_permission(context, "system.organizations.update")
    records = load_all_organizations()
    current = next((item for item in records if str(item.get("id")) == organization_id and not item.get("deletedAt")), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    changes = payload.model_dump(exclude_unset=True)
    record = normalize_organization({**current, **changes}, current)
    validate_parent(record, records)
    save_organization(record)
    return OrganizationOut.model_validate(enrich([record])[0])


@router.delete("/organizations/{organization_id}")
def delete_organization(organization_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.organizations.delete")
    records = load_all_organizations()
    current = next((item for item in records if str(item.get("id")) == organization_id and not item.get("deletedAt")), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if any(item.get("parentId") == organization_id and not item.get("deletedAt") for item in records):
        raise HTTPException(status_code=409, detail="Move or remove child organizations first")
    if user_organization_counts().get(organization_id, 0):
        raise HTTPException(status_code=409, detail="Move organization users first")
    current = {**current, "deletedAt": now_iso(), "updatedAt": now_iso()}
    save_organization(current)
    return {"ok": True, "deleted": organization_id}


@router.post("/organizations/{organization_id}/restore")
def restore_organization(organization_id: str, context: AuthContext = Depends(request_context)) -> OrganizationOut:
    require_permission(context, "system.organizations.restore")
    current = organization_or_404(organization_id)
    if not current.get("deletedAt"):
        raise HTTPException(status_code=409, detail="Organization is not deleted")
    parent_id = current.get("parentId")
    if parent_id:
        parent = next((item for item in load_all_organizations() if item.get("id") == parent_id and not item.get("deletedAt")), None)
        if parent is None:
            current["parentId"] = None
    current = {**current, "deletedAt": None, "updatedAt": now_iso()}
    save_organization(current)
    return OrganizationOut.model_validate(enrich([current])[0])
