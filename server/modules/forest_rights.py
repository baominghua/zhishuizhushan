from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from .admin_roles import require_permission
from .auth import (
    AuthContext,
    area_allowed,
    data_scope_value_allowed,
    effective_areas,
    effective_data_scope_values,
    has_effective_area_scope,
    has_effective_data_scope,
    request_context,
)
from .database import (
    forest_right_versions_json_path,
    forest_rights_json_path,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
    use_postgis,
)
from .settings import get_settings


router = APIRouter(prefix="/api", tags=["forest-rights"])

POSTGIS_SELECT_COLUMNS = [
    "id",
    "archive_code",
    "certificate_no",
    "holder",
    "certificate_type",
    "right_type",
    "ownership_type",
    "right_start",
    "right_end",
    "contract_no",
    "circulation_status",
    "archive_status",
    "registrar",
    "missing_items",
    "area_mu",
    "county_code",
    "county_name",
    "town_code",
    "town_name",
    "village_code",
    "village_name",
    "linked_block_ids",
    "linked_block_codes",
    "documents",
    "properties",
    "created_at",
    "updated_at",
    "deleted_at",
]

POSTGIS_SELECT_SQL = """
    SELECT
        id::text,
        archive_code,
        certificate_no,
        holder,
        certificate_type,
        right_type,
        ownership_type,
        right_start,
        right_end,
        contract_no,
        circulation_status,
        archive_status,
        registrar,
        missing_items,
        area_mu,
        county_code,
        county_name,
        town_code,
        town_name,
        village_code,
        village_name,
        COALESCE(linked_block_ids, '[]'::jsonb),
        COALESCE(linked_block_codes, '[]'::jsonb),
        COALESCE(documents, '[]'::jsonb),
        COALESCE(properties, '{}'::jsonb),
        created_at,
        updated_at,
        deleted_at
    FROM forest_rights
"""
MYSQL_SELECT_SQL = """
    SELECT
        r.id,
        r.archive_code,
        r.certificate_no,
        r.holder,
        r.certificate_type,
        r.right_type,
        r.ownership_type,
        r.right_start,
        r.right_end,
        r.contract_no,
        r.circulation_status,
        r.archive_status,
        r.registrar,
        r.missing_items,
        r.area_mu,
        r.county_code,
        r.county_name,
        r.town_code,
        r.town_name,
        r.village_code,
        r.village_name,
        COALESCE((
            SELECT JSON_ARRAYAGG(l.forest_block_id)
            FROM forest_right_block_links l
            WHERE l.forest_right_id = r.id
        ), JSON_ARRAY()),
        COALESCE((
            SELECT JSON_ARRAYAGG(b.block_code)
            FROM forest_right_block_links l
            JOIN forest_blocks b ON b.id = l.forest_block_id
            WHERE l.forest_right_id = r.id
        ), JSON_ARRAY()),
        COALESCE(r.documents, JSON_ARRAY()),
        COALESCE(r.properties, JSON_OBJECT()),
        r.created_at,
        r.updated_at,
        r.deleted_at
    FROM forest_rights r
"""
MYSQL_SUMMARY_SELECT_SQL = """
    SELECT
        r.id,
        r.archive_code,
        r.certificate_no,
        r.holder,
        r.certificate_type,
        r.right_type,
        r.ownership_type,
        r.right_start,
        r.right_end,
        r.contract_no,
        r.circulation_status,
        r.archive_status,
        r.registrar,
        r.missing_items,
        r.area_mu,
        r.county_code,
        r.county_name,
        r.town_code,
        r.town_name,
        r.village_code,
        r.village_name,
        JSON_ARRAY(),
        JSON_ARRAY(),
        COALESCE(r.documents, JSON_ARRAY()),
        JSON_SET(
            COALESCE(r.properties, JSON_OBJECT()),
            '$.linkedBlockCount', (
                SELECT COUNT(*) FROM forest_right_block_links links WHERE links.forest_right_id = r.id
            ),
            '$.linkedTargetsTruncated', (
                (SELECT COUNT(*) FROM forest_right_block_links links WHERE links.forest_right_id = r.id) > 0
            )
        ),
        r.created_at,
        r.updated_at,
        r.deleted_at
    FROM forest_rights r
"""

FOREST_RIGHT_FINE_SCOPE_FIELDS = (
    ("towns", "townCode", "town_code"),
    ("villages", "villageCode", "village_code"),
)
RIGHT_ARCHIVE_LOOKUP_BATCH_SIZE = 500

DB_TO_API_FIELD = {
    "id": "id",
    "archive_code": "archiveCode",
    "certificate_no": "certificateNo",
    "holder": "holder",
    "certificate_type": "certificateType",
    "right_type": "rightType",
    "ownership_type": "ownershipType",
    "right_start": "rightStart",
    "right_end": "rightEnd",
    "contract_no": "contractNo",
    "circulation_status": "circulationStatus",
    "archive_status": "archiveStatus",
    "registrar": "registrar",
    "missing_items": "missingItems",
    "area_mu": "areaMu",
    "county_code": "countyCode",
    "county_name": "countyName",
    "town_code": "townCode",
    "town_name": "townName",
    "village_code": "villageCode",
    "village_name": "villageName",
    "linked_block_ids": "linkedBlockIds",
    "linked_block_codes": "linkedBlockCodes",
    "documents": "documents",
    "properties": "properties",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "deleted_at": "deletedAt",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def postgis_connect():
    try:
        import psycopg
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"forest rights PostGIS database requires psycopg. {exc}") from exc

    try:
        return psycopg.connect(get_settings().database_url)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="forest rights PostGIS database is unavailable") from exc


def datetime_to_iso(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


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


def mysql_date(value: Any) -> Any:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def decimal_to_float(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
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


def normalize_postgis_right_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
    else:
        source = dict(zip(POSTGIS_SELECT_COLUMNS, row))

    right: dict[str, Any] = {}
    for db_field, api_field in DB_TO_API_FIELD.items():
        value = source.get(db_field)
        if db_field in {"linked_block_ids", "linked_block_codes", "documents"}:
            value = json_value(value, [])
        elif db_field == "properties":
            value = json_value(value, {})
        elif db_field in {"created_at", "updated_at", "deleted_at"}:
            value = datetime_to_iso(value)
        else:
            value = decimal_to_float(value)
        right[api_field] = value
    right.setdefault("linkedBlockIds", [])
    right.setdefault("linkedBlockCodes", [])
    right.setdefault("documents", [])
    right.setdefault("properties", {})
    return right


class ForestRightBase(BaseModel):
    archiveCode: str | None = None
    certificateNo: str | None = None
    holder: str = Field(min_length=1)
    certificateType: str | None = None
    rightType: str | None = None
    ownershipType: str | None = None
    rightStart: str | None = None
    rightEnd: str | None = None
    contractNo: str | None = None
    circulationStatus: str | None = None
    archiveStatus: str | None = None
    registrar: str | None = None
    missingItems: str | None = None
    areaMu: float | None = None
    countyCode: str | None = None
    countyName: str | None = None
    townCode: str | None = None
    townName: str | None = None
    villageCode: str | None = None
    villageName: str | None = None
    linkedBlockIds: list[str] = Field(default_factory=list)
    linkedBlockCodes: list[str] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ensure_archive_code(self) -> "ForestRightBase":
        if not self.archiveCode:
            self.archiveCode = self.certificateNo or self.contractNo
        if not self.archiveCode:
            raise ValueError("archiveCode, certificateNo, or contractNo is required")
        return self


class ForestRightIn(ForestRightBase):
    pass


class ForestRightPatch(BaseModel):
    archiveCode: str | None = None
    certificateNo: str | None = None
    holder: str | None = None
    certificateType: str | None = None
    rightType: str | None = None
    ownershipType: str | None = None
    rightStart: str | None = None
    rightEnd: str | None = None
    contractNo: str | None = None
    circulationStatus: str | None = None
    archiveStatus: str | None = None
    registrar: str | None = None
    missingItems: str | None = None
    areaMu: float | None = None
    countyCode: str | None = None
    countyName: str | None = None
    townCode: str | None = None
    townName: str | None = None
    villageCode: str | None = None
    villageName: str | None = None
    linkedBlockIds: list[str] | None = None
    linkedBlockCodes: list[str] | None = None
    documents: list[dict[str, Any]] | None = None
    properties: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}


class ForestRightRollbackRequest(BaseModel):
    versionId: str = Field(min_length=1)

    model_config = {"extra": "forbid"}


class ForestRightOut(ForestRightBase):
    id: str
    createdAt: str
    updatedAt: str
    deletedAt: str | None = None


class ForestRightFilters(BaseModel):
    q: str = ""
    archiveStatus: str = ""
    linkedBlockCode: str = ""
    includeDeleted: bool = False
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


def compact_list(values: list[Any] | None) -> list[str]:
    return sorted({str(value).strip() for value in values or [] if str(value).strip()})


def normalize_right(payload: dict[str, Any]) -> dict[str, Any]:
    right = dict(payload)
    timestamp = now_iso()
    right.setdefault("id", str(uuid.uuid4()))
    right.setdefault("createdAt", timestamp)
    right["updatedAt"] = timestamp
    right.setdefault("deletedAt", None)
    right["archiveCode"] = str(right.get("archiveCode") or right.get("certificateNo") or right.get("contractNo") or "").strip()
    right["holder"] = str(right.get("holder") or "").strip()
    right["linkedBlockIds"] = compact_list(right.get("linkedBlockIds"))
    right["linkedBlockCodes"] = compact_list(right.get("linkedBlockCodes"))
    right.setdefault("documents", [])
    right.setdefault("properties", {})
    if not right["archiveCode"]:
        raise HTTPException(status_code=400, detail="archiveCode, certificateNo, or contractNo is required")
    if not right["holder"]:
        raise HTTPException(status_code=400, detail="holder is required")
    if not right.get("archiveStatus"):
        right["archiveStatus"] = "complete" if right.get("certificateNo") else "partial"
    return right


def clean_snapshot(right: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(right, ensure_ascii=False, default=str))


def normalize_version_record(
    right: dict[str, Any],
    change_type: str,
    context: AuthContext,
    *,
    source_version_id: str = "",
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "id": str(uuid.uuid4()),
        "forestRightId": str(right.get("id") or ""),
        "archiveCode": str(right.get("archiveCode") or ""),
        "changeType": change_type,
        "snapshot": clean_snapshot(right),
        "createdBy": context.user,
        "createdAt": timestamp,
        "sourceVersionId": source_version_id,
    }


def normalize_postgis_version_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
        version_id = source.get("id")
        right_id = source.get("forest_right_id")
        change_type = source.get("change_type")
        snapshot = source.get("snapshot")
        source_version_id = source.get("source_version_id")
        created_by = source.get("created_by")
        created_at = source.get("created_at")
    else:
        version_id, right_id, change_type, snapshot, source_version_id, created_by, created_at = row
    snapshot = json_value(snapshot, {}) if isinstance(snapshot, str) else (snapshot or {})
    return {
        "id": str(version_id or ""),
        "forestRightId": str(right_id or ""),
        "archiveCode": str(snapshot.get("archiveCode") or "") if isinstance(snapshot, dict) else "",
        "changeType": str(change_type or ""),
        "snapshot": snapshot,
        "createdBy": str(created_by or ""),
        "createdAt": datetime_to_iso(created_at) or "",
        "sourceVersionId": str(source_version_id or ""),
    }


def save_right_version(version: dict[str, Any]) -> None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO forest_right_versions (
                        id, forest_right_id, change_type, snapshot,
                        source_version_id, created_by, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        version["id"],
                        version["forestRightId"],
                        version["changeType"],
                        serializable_json(version.get("snapshot"), {}),
                        version.get("sourceVersionId") or None,
                        version.get("createdBy"),
                        mysql_datetime(version.get("createdAt")),
                    ),
                )
            conn.commit()
        return
    if use_postgis():
        with postgis_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO forest_right_versions (
                        id,
                        forest_right_id,
                        change_type,
                        snapshot,
                        source_version_id,
                        created_by,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
                    """,
                    (
                        version["id"],
                        version["forestRightId"],
                        version["changeType"],
                        serializable_json(version.get("snapshot"), {}),
                        version.get("sourceVersionId") or None,
                        version.get("createdBy"),
                        version.get("createdAt"),
                    ),
                )
            conn.commit()
        return

    records = load_json_records(forest_right_versions_json_path())
    records.append(version)
    save_json_records(forest_right_versions_json_path(), records)


def record_right_version(
    right: dict[str, Any],
    change_type: str,
    context: AuthContext,
    *,
    source_version_id: str = "",
) -> dict[str, Any]:
    version = normalize_version_record(
        right,
        change_type,
        context,
        source_version_id=source_version_id,
    )
    save_right_version(version)
    return version


def load_right_versions(right_id: str) -> list[dict[str, Any]]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, forest_right_id, change_type, snapshot,
                           source_version_id, created_by, created_at
                    FROM forest_right_versions
                    WHERE forest_right_id = %s
                    ORDER BY created_at DESC, id DESC
                    """,
                    (right_id,),
                )
                return [normalize_postgis_version_row(row) for row in cur.fetchall()]
    if use_postgis():
        with postgis_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id::text,
                        forest_right_id::text,
                        change_type,
                        snapshot,
                        source_version_id::text,
                        created_by,
                        created_at
                    FROM forest_right_versions
                    WHERE forest_right_id = %s
                    ORDER BY created_at DESC, id DESC
                    """,
                    (right_id,),
                )
                return [normalize_postgis_version_row(row) for row in cur.fetchall()]

    records = [
        record
        for record in load_json_records(forest_right_versions_json_path())
        if str(record.get("forestRightId") or "") == str(right_id)
    ]
    return sorted(
        records,
        key=lambda item: (str(item.get("createdAt") or ""), str(item.get("id") or "")),
        reverse=True,
    )


def find_right_version(right_id: str, version_id: str) -> dict[str, Any] | None:
    return next(
        (
            version
            for version in load_right_versions(right_id)
            if str(version.get("id") or "") == str(version_id)
        ),
        None,
    )


def postgis_where(
    *,
    filters: ForestRightFilters | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
    right_id: str | None = None,
    archive_code: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    if right_id:
        clauses.append("id = %s")
        params.append(right_id)
    if archive_code:
        clauses.append("archive_code = %s")
        params.append(archive_code)

    if context and context_has_scoped_areas(context):
        scoped_areas = sorted(effective_areas(context))
        if not scoped_areas:
            clauses.append("FALSE")
        elif "*" not in scoped_areas:
            placeholders = ", ".join(["%s"] * len(scoped_areas))
            clauses.append(f"county_code IN ({placeholders})")
            params.extend(scoped_areas)
    if context:
        for scope_key, _api_field, db_field in FOREST_RIGHT_FINE_SCOPE_FIELDS:
            if not has_effective_data_scope(context, scope_key):
                continue
            scoped_values = sorted(effective_data_scope_values(context, scope_key))
            if not scoped_values:
                clauses.append("FALSE")
            elif "*" not in scoped_values:
                placeholders = ", ".join(["%s"] * len(scoped_values))
                clauses.append(f"{db_field} IN ({placeholders})")
                params.extend(scoped_values)
        if has_effective_data_scope(context, "blockCodes"):
            scoped_block_codes = sorted(effective_data_scope_values(context, "blockCodes"))
            if not scoped_block_codes:
                clauses.append("FALSE")
            elif "*" not in scoped_block_codes:
                clauses.append(
                    "(" + " OR ".join(["linked_block_codes ? %s"] * len(scoped_block_codes)) + ")"
                )
                params.extend(scoped_block_codes)

    if filters:
        if filters.archiveStatus:
            clauses.append("archive_status = %s")
            params.append(filters.archiveStatus)
        if filters.linkedBlockCode:
            clauses.append("linked_block_codes ? %s")
            params.append(filters.linkedBlockCode)
        if filters.q:
            pattern = f"%{filters.q}%"
            clauses.append(
                "(archive_code ILIKE %s OR certificate_no ILIKE %s OR holder ILIKE %s OR contract_no ILIKE %s OR linked_block_codes::text ILIKE %s OR properties::text ILIKE %s)"
            )
            params.extend([pattern] * 6)

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def mysql_where(
    *,
    filters: ForestRightFilters | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
    right_id: str | None = None,
    archive_code: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_deleted:
        clauses.append("r.deleted_at IS NULL")
    if right_id:
        clauses.append("r.id = %s")
        params.append(right_id)
    if archive_code:
        clauses.append("r.archive_code = %s")
        params.append(archive_code)

    if context and context_has_scoped_areas(context):
        scoped_areas = sorted(effective_areas(context))
        if not scoped_areas:
            clauses.append("FALSE")
        elif "*" not in scoped_areas:
            placeholders = ", ".join(["%s"] * len(scoped_areas))
            clauses.append(f"r.county_code IN ({placeholders})")
            params.extend(scoped_areas)
    if context:
        for scope_key, _api_field, db_field in FOREST_RIGHT_FINE_SCOPE_FIELDS:
            if not has_effective_data_scope(context, scope_key):
                continue
            scoped_values = sorted(effective_data_scope_values(context, scope_key))
            if not scoped_values:
                clauses.append("FALSE")
            elif "*" not in scoped_values:
                placeholders = ", ".join(["%s"] * len(scoped_values))
                clauses.append(f"r.{db_field} IN ({placeholders})")
                params.extend(scoped_values)
        if has_effective_data_scope(context, "blockCodes"):
            scoped_block_codes = sorted(effective_data_scope_values(context, "blockCodes"))
            if not scoped_block_codes:
                clauses.append("FALSE")
            elif "*" not in scoped_block_codes:
                placeholders = ", ".join(["%s"] * len(scoped_block_codes))
                clauses.append(
                    "EXISTS (SELECT 1 FROM forest_right_block_links l "
                    "JOIN forest_blocks b ON b.id = l.forest_block_id "
                    f"WHERE l.forest_right_id = r.id AND b.block_code IN ({placeholders}))"
                )
                params.extend(scoped_block_codes)

    if filters:
        if filters.archiveStatus:
            clauses.append("r.archive_status = %s")
            params.append(filters.archiveStatus)
        if filters.linkedBlockCode:
            clauses.append(
                "EXISTS (SELECT 1 FROM forest_right_block_links l "
                "JOIN forest_blocks b ON b.id = l.forest_block_id "
                "WHERE l.forest_right_id = r.id AND b.block_code = %s)"
            )
            params.append(filters.linkedBlockCode)
        if filters.q:
            pattern = f"%{filters.q}%"
            clauses.append(
                "(r.archive_code LIKE %s OR r.certificate_no LIKE %s OR r.holder LIKE %s "
                "OR r.contract_no LIKE %s OR CAST(r.properties AS CHAR) LIKE %s "
                "OR EXISTS (SELECT 1 FROM forest_right_block_links l "
                "JOIN forest_blocks b ON b.id = l.forest_block_id "
                "WHERE l.forest_right_id = r.id AND b.block_code LIKE %s))"
            )
            params.extend([pattern] * 6)
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def fetch_rights_mysql(
    *,
    filters: ForestRightFilters | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
    limit: int | None = None,
    offset: int = 0,
    right_id: str | None = None,
    archive_code: str | None = None,
    include_targets: bool = True,
) -> list[dict[str, Any]]:
    where_sql, params = mysql_where(
        filters=filters,
        context=context,
        include_deleted=include_deleted,
        right_id=right_id,
        archive_code=archive_code,
    )
    select_sql = MYSQL_SELECT_SQL if include_targets else MYSQL_SUMMARY_SELECT_SQL
    sql = f"{select_sql}{where_sql} ORDER BY r.updated_at DESC, r.archive_code"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_right_row(row) for row in cur.fetchall()]


def fetch_rights_by_archive_codes_mysql(archive_codes: list[str]) -> list[dict[str, Any]]:
    codes = list(dict.fromkeys(str(code).strip() for code in archive_codes if str(code).strip()))
    if not codes:
        return []
    records: list[dict[str, Any]] = []
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            for start in range(0, len(codes), RIGHT_ARCHIVE_LOOKUP_BATCH_SIZE):
                batch = codes[start : start + RIGHT_ARCHIVE_LOOKUP_BATCH_SIZE]
                placeholders = ", ".join(["%s"] * len(batch))
                cur.execute(
                    f"{MYSQL_SELECT_SQL} WHERE r.archive_code IN ({placeholders})",
                    tuple(batch),
                )
                records.extend(normalize_postgis_right_row(row) for row in cur.fetchall())
    return records


def fetch_rights_by_archive_codes_postgis(archive_codes: list[str]) -> list[dict[str, Any]]:
    codes = list(dict.fromkeys(str(code).strip() for code in archive_codes if str(code).strip()))
    if not codes:
        return []
    records: list[dict[str, Any]] = []
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            for start in range(0, len(codes), RIGHT_ARCHIVE_LOOKUP_BATCH_SIZE):
                batch = codes[start : start + RIGHT_ARCHIVE_LOOKUP_BATCH_SIZE]
                placeholders = ", ".join(["%s"] * len(batch))
                cur.execute(
                    f"{POSTGIS_SELECT_SQL} WHERE archive_code IN ({placeholders})",
                    tuple(batch),
                )
                records.extend(normalize_postgis_right_row(row) for row in cur.fetchall())
    return records


def count_rights_mysql(filters: ForestRightFilters, context: AuthContext | None = None) -> int:
    where_sql, params = mysql_where(
        filters=filters,
        context=context,
        include_deleted=filters.includeDeleted,
    )
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM forest_rights r{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def list_right_block_targets_mysql(
    right_id: str,
    *,
    q: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    clauses = ["links.forest_right_id = %s", "blocks.deleted_at IS NULL"]
    params: list[Any] = [right_id]
    query = q.strip()
    if query:
        like = f"%{query}%"
        clauses.append("(blocks.block_code LIKE %s OR blocks.name LIKE %s)")
        params.extend([like, like])
    from_sql = (
        " FROM forest_right_block_links links "
        "JOIN forest_blocks blocks ON blocks.id = links.forest_block_id "
    )
    where_sql = " WHERE " + " AND ".join(clauses)
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*){from_sql}{where_sql}", tuple(params))
            count_row = cur.fetchone()
            total = int(count_row[0] if count_row else 0)
            cur.execute(
                "SELECT blocks.id, blocks.block_code, blocks.name, blocks.county_name, "
                "blocks.town_name, blocks.village_name"
                f"{from_sql}{where_sql} ORDER BY blocks.block_code LIMIT %s OFFSET %s",
                tuple([*params, limit, offset]),
            )
            rows = cur.fetchall()
    return {
        "kind": "blocks",
        "items": [
            {
                "id": str(row[0]),
                "blockCode": row[1] or "",
                "name": row[2] or "",
                "countyName": row[3] or "",
                "townName": row[4] or "",
                "villageName": row[5] or "",
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def first_right_mysql(
    *,
    right_id: str | None = None,
    archive_code: str | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
    include_targets: bool = True,
) -> dict[str, Any] | None:
    items = fetch_rights_mysql(
        right_id=right_id,
        archive_code=archive_code,
        context=context,
        include_deleted=include_deleted,
        limit=1,
        include_targets=include_targets,
    )
    return items[0] if items else None


MYSQL_RIGHT_COLUMNS = [
    "id",
    "archive_code",
    "certificate_no",
    "holder",
    "certificate_type",
    "right_type",
    "ownership_type",
    "right_start",
    "right_end",
    "contract_no",
    "circulation_status",
    "archive_status",
    "registrar",
    "missing_items",
    "area_mu",
    "county_code",
    "county_name",
    "town_code",
    "town_name",
    "village_code",
    "village_name",
    "documents",
    "properties",
    "created_at",
    "updated_at",
    "deleted_at",
]


def mysql_right_values(right: dict[str, Any]) -> tuple[Any, ...]:
    values = {
        db_field: right.get(api_field)
        for db_field, api_field in DB_TO_API_FIELD.items()
        if db_field in MYSQL_RIGHT_COLUMNS
    }
    values["right_start"] = mysql_date(right.get("rightStart"))
    values["right_end"] = mysql_date(right.get("rightEnd"))
    values["documents"] = serializable_json(right.get("documents"), [])
    values["properties"] = serializable_json(right.get("properties"), {})
    values["created_at"] = mysql_datetime(right.get("createdAt"))
    values["updated_at"] = mysql_datetime(right.get("updatedAt"))
    values["deleted_at"] = mysql_datetime(right.get("deletedAt"))
    return tuple(values.get(column) for column in MYSQL_RIGHT_COLUMNS)


def execute_upsert_right_scalar_mysql(cur: Any, right: dict[str, Any]) -> None:
    columns_sql = ", ".join(MYSQL_RIGHT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(MYSQL_RIGHT_COLUMNS))
    update_sql = ", ".join(
        f"{column} = VALUES({column})" for column in MYSQL_RIGHT_COLUMNS if column != "id"
    )
    cur.execute(
        f"INSERT INTO forest_rights ({columns_sql}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_sql}",
        mysql_right_values(right),
    )



def sync_right_links_mysql(cur: Any, right: dict[str, Any], *, batch_size: int = 500) -> None:
    right_id = str(right.get("id") or "")
    linked_at = mysql_datetime(right.get("updatedAt"))
    size = max(1, int(batch_size))
    cur.execute("DELETE FROM forest_right_block_links WHERE forest_right_id = %s", (right_id,))

    linked_block_ids = compact_list(right.get("linkedBlockIds"))
    for start in range(0, len(linked_block_ids), size):
        batch = linked_block_ids[start : start + size]
        id_placeholders = ", ".join(["%s"] * len(batch))
        cur.execute(
            "INSERT IGNORE INTO forest_right_block_links "
            "(forest_right_id, forest_block_id, link_status, linked_at) "
            f"SELECT %s, id, 'active', %s FROM forest_blocks WHERE id IN ({id_placeholders})",
            tuple([right_id, linked_at, *batch]),
        )

    linked_block_codes = compact_list(right.get("linkedBlockCodes"))
    for start in range(0, len(linked_block_codes), size):
        batch = linked_block_codes[start : start + size]
        code_placeholders = ", ".join(["%s"] * len(batch))
        cur.execute(
            "INSERT IGNORE INTO forest_right_block_links "
            "(forest_right_id, forest_block_id, link_status, linked_at) "
            f"SELECT %s, id, 'active', %s FROM forest_blocks WHERE block_code IN ({code_placeholders})",
            tuple([right_id, linked_at, *batch]),
        )


def execute_upsert_right_mysql(cur: Any, right: dict[str, Any]) -> None:
    execute_upsert_right_scalar_mysql(cur, right)
    sync_right_links_mysql(cur, right)


def upsert_right_mysql(
    right: dict[str, Any],
    *,
    sync_links: bool = True,
    connection_factory: Any = mysql_connect,
) -> None:
    with connection_factory() as conn:
        with conn.cursor() as cur:
            execute_upsert_right_scalar_mysql(cur, right)
            if sync_links:
                sync_right_links_mysql(cur, right)
        conn.commit()


def upsert_rights_mysql(rights: list[dict[str, Any]]) -> None:
    if not rights:
        return
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            for right in rights:
                execute_upsert_right_mysql(cur, right)
        conn.commit()


def fetch_rights_postgis(
    *,
    filters: ForestRightFilters | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
    limit: int | None = None,
    offset: int = 0,
    right_id: str | None = None,
    archive_code: str | None = None,
) -> list[dict[str, Any]]:
    where_sql, params = postgis_where(
        filters=filters,
        context=context,
        include_deleted=include_deleted,
        right_id=right_id,
        archive_code=archive_code,
    )
    sql = f"{POSTGIS_SELECT_SQL}{where_sql} ORDER BY updated_at DESC, archive_code"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_right_row(row) for row in cur.fetchall()]


def count_rights_postgis(filters: ForestRightFilters, context: AuthContext | None = None) -> int:
    where_sql, params = postgis_where(
        filters=filters,
        context=context,
        include_deleted=filters.includeDeleted,
    )
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM forest_rights{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def first_right_postgis(
    *,
    right_id: str | None = None,
    archive_code: str | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    items = fetch_rights_postgis(
        right_id=right_id,
        archive_code=archive_code,
        context=context,
        include_deleted=include_deleted,
        limit=1,
    )
    return items[0] if items else None


def postgis_right_values(right: dict[str, Any]) -> tuple[Any, ...]:
    return (
        right.get("id"),
        right.get("archiveCode"),
        right.get("certificateNo"),
        right.get("holder"),
        right.get("certificateType"),
        right.get("rightType"),
        right.get("ownershipType"),
        right.get("rightStart"),
        right.get("rightEnd"),
        right.get("contractNo"),
        right.get("circulationStatus"),
        right.get("archiveStatus"),
        right.get("registrar"),
        right.get("missingItems"),
        right.get("areaMu"),
        right.get("countyCode"),
        right.get("countyName"),
        right.get("townCode"),
        right.get("townName"),
        right.get("villageCode"),
        right.get("villageName"),
        serializable_json(right.get("linkedBlockIds"), []),
        serializable_json(right.get("linkedBlockCodes"), []),
        serializable_json(right.get("documents"), []),
        serializable_json(right.get("properties"), {}),
        right.get("createdAt"),
        right.get("updatedAt"),
        right.get("deletedAt"),
    )


def execute_upsert_right_postgis(cur: Any, right: dict[str, Any]) -> None:
    cur.execute(
        """
                INSERT INTO forest_rights (
                    id,
                    archive_code,
                    certificate_no,
                    holder,
                    certificate_type,
                    right_type,
                    ownership_type,
                    right_start,
                    right_end,
                    contract_no,
                    circulation_status,
                    archive_status,
                    registrar,
                    missing_items,
                    area_mu,
                    county_code,
                    county_name,
                    town_code,
                    town_name,
                    village_code,
                    village_name,
                    linked_block_ids,
                    linked_block_codes,
                    documents,
                    properties,
                    created_at,
                    updated_at,
                    deleted_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s,
                    %s::jsonb,
                    %s::jsonb,
                    %s::jsonb,
                    %s::jsonb,
                    %s, %s, %s
                )
                ON CONFLICT (id) DO UPDATE SET
                    archive_code = EXCLUDED.archive_code,
                    certificate_no = EXCLUDED.certificate_no,
                    holder = EXCLUDED.holder,
                    certificate_type = EXCLUDED.certificate_type,
                    right_type = EXCLUDED.right_type,
                    ownership_type = EXCLUDED.ownership_type,
                    right_start = EXCLUDED.right_start,
                    right_end = EXCLUDED.right_end,
                    contract_no = EXCLUDED.contract_no,
                    circulation_status = EXCLUDED.circulation_status,
                    archive_status = EXCLUDED.archive_status,
                    registrar = EXCLUDED.registrar,
                    missing_items = EXCLUDED.missing_items,
                    area_mu = EXCLUDED.area_mu,
                    county_code = EXCLUDED.county_code,
                    county_name = EXCLUDED.county_name,
                    town_code = EXCLUDED.town_code,
                    town_name = EXCLUDED.town_name,
                    village_code = EXCLUDED.village_code,
                    village_name = EXCLUDED.village_name,
                    linked_block_ids = EXCLUDED.linked_block_ids,
                    linked_block_codes = EXCLUDED.linked_block_codes,
                    documents = EXCLUDED.documents,
                    properties = EXCLUDED.properties,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    deleted_at = EXCLUDED.deleted_at
                """,
        postgis_right_values(right),
    )


def upsert_rights_postgis(rights: list[dict[str, Any]]) -> None:
    if not rights:
        return
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            for right in rights:
                execute_upsert_right_postgis(cur, right)
        conn.commit()


def save_right(right: dict[str, Any]) -> None:
    if use_mysql():
        upsert_rights_mysql([right])
        return
    if use_postgis():
        upsert_rights_postgis([right])
        return

    rights = load_all_rights()
    for index, existing in enumerate(rights):
        if existing.get("id") == right.get("id"):
            rights[index] = right
            save_rights(rights)
            return
    rights.append(right)
    save_rights(rights)


def load_all_rights() -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_rights_mysql(include_deleted=True)
    if use_postgis():
        return fetch_rights_postgis(include_deleted=True)
    return load_json_records(forest_rights_json_path())


def load_rights() -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_rights_mysql()
    if use_postgis():
        return fetch_rights_postgis()
    return [right for right in load_all_rights() if not right.get("deletedAt")]


def save_rights(rights: list[dict[str, Any]]) -> None:
    if use_mysql():
        upsert_rights_mysql(rights)
        return
    if use_postgis():
        upsert_rights_postgis(rights)
        return
    save_json_records(forest_rights_json_path(), rights)


def right_by_id(right_id: str) -> dict[str, Any] | None:
    if use_mysql():
        return first_right_mysql(right_id=right_id)
    if use_postgis():
        return first_right_postgis(right_id=right_id)
    for right in load_rights():
        if str(right.get("id")) == str(right_id):
            return right
    return None


def context_has_scoped_areas(context: AuthContext) -> bool:
    return has_effective_area_scope(context)


def require_target_area_allowed(context: AuthContext, county_code: str | None) -> None:
    if county_code and not area_allowed(context, county_code):
        raise HTTPException(status_code=403, detail="Area access denied")


def linked_block_scope_allowed(context: AuthContext, right: dict[str, Any]) -> bool:
    scoped_block_codes = effective_data_scope_values(context, "blockCodes")
    if not scoped_block_codes or "*" in scoped_block_codes:
        return True
    linked_block_codes = {
        str(value).strip()
        for value in right.get("linkedBlockCodes") or []
        if str(value).strip()
    }
    return bool(linked_block_codes & scoped_block_codes)


def right_allowed(context: AuthContext, right: dict[str, Any]) -> bool:
    if not area_allowed(context, right.get("countyCode")):
        return False
    for scope_key, api_field, _db_field in FOREST_RIGHT_FINE_SCOPE_FIELDS:
        if not data_scope_value_allowed(context, scope_key, right.get(api_field)):
            return False
    return linked_block_scope_allowed(context, right)


def require_target_right_allowed(context: AuthContext, right: dict[str, Any]) -> None:
    require_target_area_allowed(context, right.get("countyCode"))
    for scope_key, api_field, _db_field in FOREST_RIGHT_FINE_SCOPE_FIELDS:
        if not data_scope_value_allowed(context, scope_key, right.get(api_field)):
            raise HTTPException(status_code=403, detail="Area access denied")
    if not linked_block_scope_allowed(context, right):
        raise HTTPException(status_code=403, detail="Area access denied")


def require_target_right_scalar_allowed(context: AuthContext, right: dict[str, Any]) -> None:
    require_target_area_allowed(context, right.get("countyCode"))
    for scope_key, api_field, _db_field in FOREST_RIGHT_FINE_SCOPE_FIELDS:
        if not data_scope_value_allowed(context, scope_key, right.get(api_field)):
            raise HTTPException(status_code=403, detail="Area access denied")


def find_right(right_id: str, context: AuthContext) -> dict[str, Any]:
    if use_mysql():
        right = first_right_mysql(right_id=right_id, context=context)
        if right is not None:
            return right
        raise HTTPException(status_code=404, detail="Forest right archive not found")
    if use_postgis():
        right = first_right_postgis(right_id=right_id, context=context)
        if right is not None:
            return right
        raise HTTPException(status_code=404, detail="Forest right archive not found")

    for right in load_rights():
        if str(right.get("id")) == str(right_id) and right_allowed(context, right):
            return right
    raise HTTPException(status_code=404, detail="Forest right archive not found")


def find_right_any_state(right_id: str, context: AuthContext | None = None) -> dict[str, Any]:
    if use_mysql():
        right = first_right_mysql(right_id=right_id, context=context, include_deleted=True)
        if right is None:
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        return right
    if use_postgis():
        right = first_right_postgis(right_id=right_id, context=context, include_deleted=True)
        if right is None:
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        return right

    for right in load_all_rights():
        if str(right.get("id")) == str(right_id):
            if context is not None and not right_allowed(context, right):
                raise HTTPException(status_code=404, detail="Forest right archive not found")
            return right
    raise HTTPException(status_code=404, detail="Forest right archive not found")


def right_by_archive_code(archive_code: str) -> dict[str, Any] | None:
    if use_mysql():
        return first_right_mysql(archive_code=archive_code)
    if use_postgis():
        return first_right_postgis(archive_code=archive_code)
    for right in load_rights():
        if str(right.get("archiveCode")) == str(archive_code):
            return right
    return None


def text_matches(right: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    properties_text = json.dumps(right.get("properties") or {}, ensure_ascii=False)
    haystack = " ".join(
        [
            str(right.get("archiveCode") or ""),
            str(right.get("certificateNo") or ""),
            str(right.get("holder") or ""),
            str(right.get("contractNo") or ""),
            " ".join(right.get("linkedBlockCodes") or []),
            properties_text,
        ]
    ).lower()
    return query.lower() in haystack


def right_matches_filters(
    right: dict[str, Any],
    filters: ForestRightFilters,
    context: AuthContext | None = None,
) -> bool:
    if context is not None and not right_allowed(context, right):
        return False
    if filters.archiveStatus and right.get("archiveStatus") != filters.archiveStatus:
        return False
    if filters.linkedBlockCode and filters.linkedBlockCode not in (right.get("linkedBlockCodes") or []):
        return False
    return text_matches(right, filters.q)


def is_rights_archive_like_block(block: dict[str, Any]) -> bool:
    block_code = str(block.get("blockCode") or "").strip().upper()
    name = str(block.get("name") or "").strip()
    return (
        block_code.startswith("BAMBOO-RIGHTS-")
        or ("林权" in name and "档案" in name)
        or name.endswith("竹林档案")
    )


def list_forest_rights(
    filters: ForestRightFilters,
    context: AuthContext | None = None,
) -> dict[str, Any]:
    if use_mysql():
        return {
            "items": fetch_rights_mysql(
                filters=filters,
                context=context,
                include_deleted=filters.includeDeleted,
                limit=filters.limit,
                offset=filters.offset,
                include_targets=False,
            ),
            "total": count_rights_mysql(filters, context),
            "limit": filters.limit,
            "offset": filters.offset,
        }
    if use_postgis():
        return {
            "items": fetch_rights_postgis(
                filters=filters,
                context=context,
                include_deleted=filters.includeDeleted,
                limit=filters.limit,
                offset=filters.offset,
            ),
            "total": count_rights_postgis(filters, context),
            "limit": filters.limit,
            "offset": filters.offset,
        }

    source_rights = load_all_rights() if filters.includeDeleted else load_rights()
    rights = [right for right in source_rights if right_matches_filters(right, filters, context)]
    return {
        "items": rights[filters.offset : filters.offset + filters.limit],
        "total": len(rights),
        "limit": filters.limit,
        "offset": filters.offset,
    }


def merge_right_links(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = {
        **existing,
        **{key: value for key, value in incoming.items() if value not in (None, "", [], {})},
        "id": existing["id"],
        "createdAt": existing.get("createdAt", now_iso()),
        "deletedAt": existing.get("deletedAt"),
    }
    merged["linkedBlockIds"] = compact_list((existing.get("linkedBlockIds") or []) + (incoming.get("linkedBlockIds") or []))
    merged["linkedBlockCodes"] = compact_list((existing.get("linkedBlockCodes") or []) + (incoming.get("linkedBlockCodes") or []))
    merged["properties"] = {
        **(existing.get("properties") or {}),
        **(incoming.get("properties") or {}),
    }
    return normalize_right(merged)


def upsert_right_archive(payload: dict[str, Any]) -> dict[str, Any]:
    incoming = normalize_right(payload)
    rights = load_all_rights()
    for index, existing in enumerate(rights):
        if existing.get("deletedAt"):
            continue
        if existing.get("archiveCode") == incoming["archiveCode"]:
            rights[index] = merge_right_links(existing, incoming)
            save_rights(rights)
            return rights[index]
    rights.append(incoming)
    save_rights(rights)
    return incoming


def upsert_right_archives_from_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    incoming = [payload for block in blocks if (payload := archive_payload_from_block(block)) is not None]
    if not incoming:
        return []

    archive_codes = [str(payload.get("archiveCode") or "") for payload in incoming]
    database_backed = use_mysql() or use_postgis()
    if use_mysql():
        existing_rights = fetch_rights_by_archive_codes_mysql(archive_codes)
    elif use_postgis():
        existing_rights = fetch_rights_by_archive_codes_postgis(archive_codes)
    else:
        existing_rights = load_all_rights()

    existing_by_code = {
        str(right.get("archiveCode") or ""): right
        for right in existing_rights
        if right.get("archiveCode") and not right.get("deletedAt")
    }
    changed: list[dict[str, Any]] = []
    for payload in incoming:
        normalized = normalize_right(payload)
        archive_code = str(normalized.get("archiveCode") or "")
        existing = existing_by_code.get(archive_code)
        merged = merge_right_links(existing, normalized) if existing else normalized
        existing_by_code[archive_code] = merged
        changed.append(merged)

    if database_backed:
        save_rights(changed)
    else:
        changed_codes = {str(right.get("archiveCode") or "") for right in changed}
        untouched = [
            right
            for right in existing_rights
            if str(right.get("archiveCode") or "") not in changed_codes
        ]
        save_rights([*untouched, *changed])
    return changed


def archive_payload_from_block(block: dict[str, Any]) -> dict[str, Any] | None:
    properties = block.get("properties") or {}
    rights = properties.get("rights") or {}
    holder = rights.get("holder") or properties.get("FBF") or properties.get("LMSHIYQRMC")
    if not holder and not rights.get("certificateNo") and not rights.get("contractNo"):
        return None
    archive_like = is_rights_archive_like_block(block)
    archive_code = (
        block.get("blockCode")
        if archive_like and block.get("blockCode")
        else rights.get("certificateNo") or rights.get("contractNo") or f"RIGHT-{block.get('blockCode')}"
    )
    archive_properties = {
        "source": properties.get("source") or {},
        "rawAttributes": properties.get("rawAttributes") or {},
    }
    if archive_like:
        archive_properties["legacyBlockCode"] = block.get("blockCode")
        archive_properties["spatialSnapshot"] = {
            "name": block.get("name"),
            "geometry": block.get("geometry"),
            "baseType": block.get("baseType"),
            "operationType": block.get("operationType"),
            "forestType": block.get("forestType"),
            "qualityGrade": block.get("qualityGrade"),
            "healthStatus": block.get("healthStatus"),
            "riskLevel": block.get("riskLevel"),
        }
    return {
        "archiveCode": archive_code,
        "certificateNo": rights.get("certificateNo"),
        "holder": holder or "未填写权利人",
        "certificateType": rights.get("certificateType"),
        "rightType": rights.get("rightType"),
        "rightStart": rights.get("rightStart"),
        "rightEnd": rights.get("rightEnd"),
        "contractNo": rights.get("contractNo"),
        "circulationStatus": rights.get("circulationStatus"),
        "archiveStatus": rights.get("archiveStatus") or ("complete" if rights.get("certificateNo") else "partial"),
        "registrar": rights.get("registrar"),
        "missingItems": rights.get("missingItems"),
        "areaMu": block.get("areaMu"),
        "countyCode": block.get("countyCode"),
        "countyName": block.get("countyName"),
        "townCode": block.get("townCode"),
        "townName": block.get("townName"),
        "villageCode": block.get("villageCode"),
        "villageName": block.get("villageName"),
        "linkedBlockIds": [] if archive_like else ([block.get("id")] if block.get("id") else []),
        "linkedBlockCodes": [] if archive_like else ([block.get("blockCode")] if block.get("blockCode") else []),
        "properties": archive_properties,
    }


def upsert_right_archive_from_block(block: dict[str, Any]) -> dict[str, Any] | None:
    updated = upsert_right_archives_from_blocks([block])
    return updated[0] if updated else None


def filter_params(
    q: str = Query(default=""),
    archiveStatus: str = Query(default=""),
    linkedBlockCode: str = Query(default=""),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> ForestRightFilters:
    return ForestRightFilters(
        q=q,
        archiveStatus=archiveStatus,
        linkedBlockCode=linkedBlockCode,
        includeDeleted=includeDeleted,
        limit=limit,
        offset=offset,
    )


@router.get("/forest-rights")
def list_forest_rights_route(
    filters: ForestRightFilters = Depends(filter_params),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    if filters.includeDeleted:
        require_permission(context, "forest.rights.manage")
    return list_forest_rights(filters, context)


@router.post("/forest-rights")
def create_forest_right(
    payload: ForestRightIn,
    context: AuthContext = Depends(request_context),
) -> ForestRightOut:
    require_permission(context, "forest.rights.create")
    normalized = normalize_right(payload.model_dump())
    require_target_right_allowed(context, normalized)
    if right_by_archive_code(normalized["archiveCode"]):
        raise HTTPException(status_code=409, detail="archiveCode already exists")
    save_right(normalized)
    record_right_version(normalized, "create", context)
    return ForestRightOut.model_validate(normalized)


@router.get("/forest-rights/{right_id}/targets")
def list_forest_right_targets(
    right_id: str,
    q: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.rights.view")
    if use_mysql():
        right = first_right_mysql(
            right_id=right_id,
            context=context,
            include_targets=False,
        )
        if right is None:
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        return list_right_block_targets_mysql(right_id, q=q, limit=limit, offset=offset)
    right = find_right(right_id, context)
    query = q.strip().lower()
    values = compact_list(right.get("linkedBlockCodes"))
    if query:
        values = [value for value in values if query in value.lower()]
    return {
        "kind": "blocks",
        "items": [{"blockCode": value} for value in values[offset : offset + limit]],
        "total": len(values),
        "limit": limit,
        "offset": offset,
    }


@router.get("/forest-rights/{right_id}")
def get_forest_right(
    right_id: str,
    context: AuthContext = Depends(request_context),
) -> ForestRightOut:
    if use_mysql():
        right = first_right_mysql(right_id=right_id, context=context, include_targets=False)
        if right is None:
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        return ForestRightOut.model_validate(right)
    return ForestRightOut.model_validate(find_right(right_id, context))


@router.get("/forest-rights/{right_id}/versions")
def list_forest_right_versions(
    right_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.rights.view")
    find_right_any_state(right_id, context)
    versions = load_right_versions(right_id)
    return {
        "items": versions,
        "total": len(versions),
        "limit": len(versions),
        "offset": 0,
    }


@router.post("/forest-rights/{right_id}/rollback")
def rollback_forest_right(
    right_id: str,
    payload: ForestRightRollbackRequest,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.rights.rollback")
    current = find_right_any_state(right_id, context)
    version = find_right_version(right_id, payload.versionId)
    if version is None:
        raise HTTPException(status_code=404, detail="Forest right version not found")
    snapshot = version.get("snapshot")
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=409, detail="Forest right version has no snapshot")
    snapshot_properties = snapshot.get("properties") if isinstance(snapshot.get("properties"), dict) else {}
    if snapshot_properties.get("linkedTargetsTruncated"):
        snapshot = {
            **snapshot,
            "linkedBlockIds": list(current.get("linkedBlockIds") or []),
            "linkedBlockCodes": list(current.get("linkedBlockCodes") or []),
        }
    rolled_back = normalize_right(
        {
            **snapshot,
            "id": right_id,
            "archiveCode": current.get("archiveCode") or snapshot.get("archiveCode"),
            "createdAt": snapshot.get("createdAt") or current.get("createdAt") or now_iso(),
        }
    )
    require_target_right_allowed(context, rolled_back)
    save_right(rolled_back)
    rollback_version = record_right_version(
        rolled_back,
        "rollback",
        context,
        source_version_id=payload.versionId,
    )
    return {
        "ok": True,
        "rolledBack": right_id,
        "sourceVersionId": payload.versionId,
        "right": ForestRightOut.model_validate(rolled_back).model_dump(),
        "version": rollback_version,
    }


@router.patch("/forest-rights/{right_id}")
def patch_forest_right(
    right_id: str,
    payload: ForestRightPatch,
    context: AuthContext = Depends(request_context),
) -> ForestRightOut:
    require_permission(context, "forest.rights.update")
    if use_mysql():
        changes = payload.model_dump(exclude_unset=True)
        relation_update = bool({"linkedBlockIds", "linkedBlockCodes"} & set(changes))
        right = first_right_mysql(
            right_id=right_id,
            context=context,
            include_targets=relation_update,
        )
        if right is None:
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        updated = normalize_right(
            {
                **right,
                **changes,
                "id": right_id,
                "createdAt": right.get("createdAt", now_iso()),
                "deletedAt": right.get("deletedAt"),
            }
        )
        if relation_update:
            require_target_right_allowed(context, updated)
        else:
            require_target_right_scalar_allowed(context, updated)
        upsert_right_mysql(updated, sync_links=relation_update)
        record_right_version(updated, "update", context)
        return ForestRightOut.model_validate(updated)
    if use_postgis():
        right = find_right(right_id, context)
        changes = payload.model_dump(exclude_unset=True)
        updated = normalize_right(
            {
                **right,
                **changes,
                "id": right_id,
                "createdAt": right.get("createdAt", now_iso()),
                "deletedAt": right.get("deletedAt"),
            }
        )
        require_target_right_allowed(context, updated)
        save_right(updated)
        record_right_version(updated, "update", context)
        return ForestRightOut.model_validate(updated)

    rights = load_all_rights()
    for index, right in enumerate(rights):
        if str(right.get("id")) != str(right_id) or right.get("deletedAt"):
            continue
        if not right_allowed(context, right):
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        changes = payload.model_dump(exclude_unset=True)
        updated = normalize_right(
            {
                **right,
                **changes,
                "id": right_id,
                "createdAt": right.get("createdAt", now_iso()),
                "deletedAt": right.get("deletedAt"),
            }
        )
        require_target_right_allowed(context, updated)
        rights[index] = updated
        save_rights(rights)
        record_right_version(updated, "update", context)
        return ForestRightOut.model_validate(updated)
    raise HTTPException(status_code=404, detail="Forest right archive not found")


@router.delete("/forest-rights/{right_id}")
def delete_forest_right(
    right_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.rights.delete")
    if use_mysql():
        right = first_right_mysql(right_id=right_id, context=context, include_targets=False)
        if right is None:
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        right["deletedAt"] = now_iso()
        right["updatedAt"] = right["deletedAt"]
        upsert_right_mysql(right, sync_links=False)
        record_right_version(right, "delete", context)
        return {"ok": True, "deleted": right_id}
    if use_postgis():
        right = find_right(right_id, context)
        right["deletedAt"] = now_iso()
        right["updatedAt"] = right["deletedAt"]
        save_right(right)
        record_right_version(right, "delete", context)
        return {"ok": True, "deleted": right_id}

    rights = load_all_rights()
    for right in rights:
        if str(right.get("id")) != str(right_id) or right.get("deletedAt"):
            continue
        if not right_allowed(context, right):
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        right["deletedAt"] = now_iso()
        right["updatedAt"] = right["deletedAt"]
        save_rights(rights)
        record_right_version(right, "delete", context)
        return {"ok": True, "deleted": right_id}
    raise HTTPException(status_code=404, detail="Forest right archive not found")


@router.post("/forest-rights/{right_id}/restore")
def restore_forest_right(
    right_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.rights.restore")
    if use_mysql():
        right = first_right_mysql(
            right_id=right_id,
            context=context,
            include_deleted=True,
            include_targets=False,
        )
        if right is None:
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        if not right.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Forest right archive is not deleted")
        right["deletedAt"] = None
        right["updatedAt"] = now_iso()
        upsert_right_mysql(right, sync_links=False)
        record_right_version(right, "restore", context)
        return {"ok": True, "restored": right_id, "right": ForestRightOut.model_validate(right).model_dump()}
    if use_postgis():
        right = first_right_postgis(right_id=right_id, context=context, include_deleted=True)
        if right is None:
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        if not right.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Forest right archive is not deleted")
        right["deletedAt"] = None
        right["updatedAt"] = now_iso()
        save_right(right)
        record_right_version(right, "restore", context)
        return {"ok": True, "restored": right_id, "right": ForestRightOut.model_validate(right).model_dump()}

    rights = load_all_rights()
    for right in rights:
        if str(right.get("id")) != str(right_id):
            continue
        if not right_allowed(context, right):
            raise HTTPException(status_code=404, detail="Forest right archive not found")
        if not right.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Forest right archive is not deleted")
        right["deletedAt"] = None
        right["updatedAt"] = now_iso()
        save_rights(rights)
        record_right_version(right, "restore", context)
        return {"ok": True, "restored": right_id, "right": ForestRightOut.model_validate(right).model_dump()}
    raise HTTPException(status_code=404, detail="Forest right archive not found")
