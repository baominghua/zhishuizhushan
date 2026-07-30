from __future__ import annotations

import json
import hashlib
import math
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

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
    forest_block_versions_json_path,
    forest_blocks_json_path,
    get_data_dir,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
    use_postgis,
)
from .settings import get_settings


router = APIRouter(prefix="/api", tags=["forest-blocks"])


def positive_env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return max(minimum, default)
    try:
        value = int(raw_value)
    except ValueError:
        return max(minimum, default)
    return max(minimum, value)

POSTGIS_SELECT_COLUMNS = [
    "id",
    "block_code",
    "name",
    "county_code",
    "county_name",
    "town_code",
    "town_name",
    "village_code",
    "village_name",
    "base_type",
    "operation_type",
    "forest_type",
    "area_mu",
    "slope_degree",
    "ownership_status",
    "management_status",
    "quality_grade",
    "health_status",
    "risk_level",
    "bamboo_age",
    "avg_dbh_cm",
    "avg_height_m",
    "standing_density",
    "carbon_estimate_tco2e",
    "yield_estimate",
    "tags",
    "properties",
    "geometry",
    "source_batch_id",
    "created_at",
    "updated_at",
    "deleted_at",
]

POSTGIS_SELECT_SQL = """
    SELECT
        id::text,
        block_code,
        name,
        county_code,
        county_name,
        town_code,
        town_name,
        village_code,
        village_name,
        base_type,
        operation_type,
        forest_type,
        area_mu,
        slope_degree,
        ownership_status,
        management_status,
        quality_grade,
        health_status,
        risk_level,
        bamboo_age,
        avg_dbh_cm,
        avg_height_m,
        standing_density,
        carbon_estimate_tco2e,
        COALESCE(yield_estimate, '{}'::jsonb),
        COALESCE(tags, '[]'::jsonb),
        COALESCE(properties, '{}'::jsonb),
        CASE WHEN geometry IS NULL THEN NULL ELSE ST_AsGeoJSON(geometry)::json END,
        source_batch_id::text,
        created_at,
        updated_at,
        deleted_at
    FROM forest_blocks
"""
POSTGIS_SIMPLIFIED_SELECT_SQL = POSTGIS_SELECT_SQL.replace(
    "ST_AsGeoJSON(geometry)",
    "ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry, %s))",
)
MYSQL_SELECT_SQL = """
    SELECT
        b.id,
        b.block_code,
        b.name,
        b.county_code,
        b.county_name,
        b.town_code,
        b.town_name,
        b.village_code,
        b.village_name,
        b.base_type,
        b.operation_type,
        b.forest_type,
        b.area_mu,
        b.slope_degree,
        b.ownership_status,
        b.management_status,
        b.quality_grade,
        b.health_status,
        b.risk_level,
        b.bamboo_age,
        b.avg_dbh_cm,
        b.avg_height_m,
        b.standing_density,
        b.carbon_estimate_tco2e,
        COALESCE(b.yield_estimate, JSON_OBJECT()),
        COALESCE(b.tags, JSON_ARRAY()),
        COALESCE(b.properties, JSON_OBJECT()),
        CASE WHEN g.geometry IS NULL THEN NULL ELSE ST_AsGeoJSON(g.geometry) END,
        b.source_batch_id,
        b.created_at,
        b.updated_at,
        b.deleted_at
    FROM forest_blocks b
    LEFT JOIN forest_block_geometries g ON g.forest_block_id = b.id
"""


def mysql_select_sql_for_filters(*, has_bbox: bool = False) -> str:
    if not has_bbox:
        return MYSQL_SELECT_SQL
    return MYSQL_SELECT_SQL.replace(
        "FROM forest_blocks b\n    LEFT JOIN forest_block_geometries g ON g.forest_block_id = b.id",
        "FROM forest_block_geometries g FORCE INDEX (idx_forest_block_geometry)\n"
        "    STRAIGHT_JOIN forest_blocks b ON b.id = g.forest_block_id",
    )

DB_TO_API_FIELD = {
    "id": "id",
    "block_code": "blockCode",
    "name": "name",
    "county_code": "countyCode",
    "county_name": "countyName",
    "town_code": "townCode",
    "town_name": "townName",
    "village_code": "villageCode",
    "village_name": "villageName",
    "base_type": "baseType",
    "operation_type": "operationType",
    "forest_type": "forestType",
    "area_mu": "areaMu",
    "slope_degree": "slopeDegree",
    "ownership_status": "ownershipStatus",
    "management_status": "managementStatus",
    "quality_grade": "qualityGrade",
    "health_status": "healthStatus",
    "risk_level": "riskLevel",
    "bamboo_age": "bambooAge",
    "avg_dbh_cm": "avgDbhCm",
    "avg_height_m": "avgHeightM",
    "standing_density": "standingDensity",
    "carbon_estimate_tco2e": "carbonEstimateTco2e",
    "yield_estimate": "yieldEstimate",
    "tags": "tags",
    "properties": "properties",
    "geometry": "geometry",
    "source_batch_id": "sourceBatchId",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "deleted_at": "deletedAt",
}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


FOREST_BLOCK_LEGAL_FIELDS = {"ownershipStatus", "managementStatus"}
RIGHTS_ARCHIVE_BLOCK_CODE_PREFIXES = ("BAMBOO-RIGHTS-",)

FOREST_BLOCK_FACETS = [
    {"key": "countyCode", "labelKey": "countyName", "dbField": "county_code", "dbLabelField": "county_name"},
    {"key": "townCode", "labelKey": "townName", "dbField": "town_code", "dbLabelField": "town_name"},
    {"key": "villageCode", "labelKey": "villageName", "dbField": "village_code", "dbLabelField": "village_name"},
    {"key": "baseType", "dbField": "base_type"},
    {"key": "operationType", "dbField": "operation_type"},
    {"key": "qualityGrade", "dbField": "quality_grade"},
    {"key": "healthStatus", "dbField": "health_status"},
    {"key": "riskLevel", "dbField": "risk_level"},
]
FOREST_BLOCK_AGGREGATE_FIELDS = {
    "county": ("countyCode", "countyName", "county_code", "county_name"),
    "town": ("townCode", "townName", "town_code", "town_name"),
    "village": ("villageCode", "villageName", "village_code", "village_name"),
}
RISK_LEVEL_ALIASES = {
    "high": {"high", "high-risk", "high_risk", "高", "高风险"},
    "medium": {"medium", "middle", "medium-risk", "medium_risk", "中", "中风险"},
    "low": {"low", "low-risk", "low_risk", "低", "低风险"},
}
QUALITY_LEVELS = {"A", "B", "C"}
FOREST_BLOCK_FINE_SCOPE_FIELDS = (
    ("towns", "townCode", "town_code"),
    ("villages", "villageCode", "village_code"),
    ("blockCodes", "blockCode", "block_code"),
)
FOREST_VECTOR_TILE_CACHE_TTL_SECONDS = positive_env_int(
    "SMART_BAMBOO_VECTOR_TILE_CACHE_TTL_SECONDS", 300, minimum=30
)
FOREST_VECTOR_TILE_CACHE_MAX_BYTES = positive_env_int(
    "SMART_BAMBOO_VECTOR_TILE_CACHE_MAX_BYTES", 2 * 1024 * 1024 * 1024, minimum=1024 * 1024
)
FOREST_VECTOR_TILE_CACHE_MAX_AGE_SECONDS = positive_env_int(
    "SMART_BAMBOO_VECTOR_TILE_CACHE_MAX_AGE_SECONDS", 24 * 60 * 60, minimum=60
)
FOREST_VECTOR_TILE_CACHE_PRUNE_INTERVAL_SECONDS = positive_env_int(
    "SMART_BAMBOO_VECTOR_TILE_CACHE_PRUNE_INTERVAL_SECONDS", 60, minimum=5
)
FOREST_BLOCK_MYSQL_WRITE_BATCH_SIZE = positive_env_int(
    "SMART_BAMBOO_MYSQL_WRITE_BATCH_SIZE", 500, minimum=1
)
FOREST_BLOCK_IDENTITY_LOOKUP_BATCH_SIZE = positive_env_int(
    "SMART_BAMBOO_IDENTITY_LOOKUP_BATCH_SIZE", 500, minimum=1
)
FOREST_VECTOR_TILE_CACHE_PRUNE_LOCK = threading.Lock()
FOREST_VECTOR_TILE_CACHE_LAST_PRUNE = 0.0
FOREST_VECTOR_TILE_EXTENT = 4096
FOREST_VECTOR_TILE_BUFFER_PIXELS = 64
FOREST_VECTOR_TILE_PROPERTY_FIELDS = (
    "id",
    "blockCode",
    "name",
    "countyCode",
    "countyName",
    "townCode",
    "townName",
    "villageCode",
    "villageName",
    "baseType",
    "operationType",
    "forestType",
    "areaMu",
    "qualityGrade",
    "healthStatus",
    "riskLevel",
    "managementStatus",
    "ownershipStatus",
)
HEALTHY_STATUS_VALUES = {"normal", "good", "healthy", "良好", "健康", "巡护中"}
POSTGIS_HEALTHY_STATUS_VALUES = ["normal", "good", "healthy", "良好", "健康", "巡护中"]


def sanitize_block_for_ledger(block: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(block)
    for field in FOREST_BLOCK_LEGAL_FIELDS:
        sanitized.pop(field, None)
    properties = dict(sanitized.get("properties") or {})
    properties.pop("rights", None)
    sanitized["properties"] = properties
    return sanitized


def is_rights_archive_like_block(block: dict[str, Any]) -> bool:
    block_code = str(block.get("blockCode") or "").strip().upper()
    name = str(block.get("name") or "").strip()
    return (
        any(block_code.startswith(prefix) for prefix in RIGHTS_ARCHIVE_BLOCK_CODE_PREFIXES)
        or ("林权" in name and "档案" in name)
        or name.endswith("竹林档案")
    )


class ForestBlockBase(BaseModel):
    blockCode: str = Field(min_length=1)
    name: str = Field(min_length=1)
    countyCode: str | None = None
    countyName: str | None = None
    townCode: str | None = None
    townName: str | None = None
    villageCode: str | None = None
    villageName: str | None = None
    baseType: str | None = None
    operationType: str | None = None
    forestType: str | None = None
    areaMu: float | None = None
    slopeDegree: float | None = None
    qualityGrade: str | None = None
    healthStatus: str | None = None
    riskLevel: str | None = None
    bambooAge: str | None = None
    avgDbhCm: float | None = None
    avgHeightM: float | None = None
    standingDensity: float | None = None
    carbonEstimateTco2e: float | None = None
    yieldEstimate: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any] | None = None
    sourceBatchId: str | None = None


class ForestBlockIn(ForestBlockBase):
    model_config = {"extra": "forbid"}


class ForestBlockPatch(BaseModel):
    name: str | None = None
    countyCode: str | None = None
    countyName: str | None = None
    townCode: str | None = None
    townName: str | None = None
    villageCode: str | None = None
    villageName: str | None = None
    baseType: str | None = None
    operationType: str | None = None
    forestType: str | None = None
    areaMu: float | None = None
    slopeDegree: float | None = None
    qualityGrade: str | None = None
    healthStatus: str | None = None
    riskLevel: str | None = None
    bambooAge: str | None = None
    avgDbhCm: float | None = None
    avgHeightM: float | None = None
    standingDensity: float | None = None
    carbonEstimateTco2e: float | None = None
    yieldEstimate: dict[str, Any] | None = None
    tags: list[str] | None = None
    properties: dict[str, Any] | None = None
    geometry: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}


class ForestBlockRollbackRequest(BaseModel):
    versionId: str = Field(min_length=1)

    model_config = {"extra": "forbid"}


class ForestBlockOut(ForestBlockBase):
    id: str
    createdAt: str
    updatedAt: str
    deletedAt: str | None = None


class ForestBlockFilters(BaseModel):
    q: str = ""
    countyCode: str = ""
    townCode: str = ""
    villageCode: str = ""
    baseType: str = ""
    operationType: str = ""
    qualityGrade: str = ""
    healthStatus: str = ""
    riskLevel: str = ""
    bbox: str = ""
    includeDeleted: bool = False
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


def normalize_block(payload: dict[str, Any]) -> dict[str, Any]:
    block = dict(payload)
    timestamp = now_iso()
    block.setdefault("id", str(uuid.uuid4()))
    block.setdefault("createdAt", timestamp)
    block["updatedAt"] = timestamp
    block.setdefault("deletedAt", None)
    block.setdefault("yieldEstimate", {})
    block.setdefault("tags", [])
    block.setdefault("properties", {})
    return block


def clean_snapshot(block: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(sanitize_block_for_ledger(block), ensure_ascii=False, default=str))


def normalize_version_record(
    block: dict[str, Any],
    change_type: str,
    context: AuthContext,
    *,
    source_version_id: str = "",
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "id": str(uuid.uuid4()),
        "forestBlockId": str(block.get("id") or ""),
        "blockCode": str(block.get("blockCode") or ""),
        "changeType": change_type,
        "snapshot": clean_snapshot(block),
        "createdBy": context.user,
        "createdAt": timestamp,
        "sourceVersionId": source_version_id,
    }


def normalize_postgis_version_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
        version_id = source.get("id")
        block_id = source.get("forest_block_id")
        change_type = source.get("change_type")
        snapshot = source.get("snapshot")
        source_version_id = source.get("source_version_id")
        created_by = source.get("created_by")
        created_at = source.get("created_at")
    else:
        version_id, block_id, change_type, snapshot, source_version_id, created_by, created_at = row
    snapshot = json_value(snapshot, {}) if isinstance(snapshot, str) else (snapshot or {})
    return {
        "id": str(version_id or ""),
        "forestBlockId": str(block_id or ""),
        "blockCode": str(snapshot.get("blockCode") or "") if isinstance(snapshot, dict) else "",
        "changeType": str(change_type or ""),
        "snapshot": snapshot,
        "createdBy": str(created_by or ""),
        "createdAt": datetime_to_iso(created_at) or "",
        "sourceVersionId": str(source_version_id or ""),
    }


def save_block_version(version: dict[str, Any]) -> None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO forest_block_versions (
                        id, forest_block_id, change_type, snapshot,
                        source_version_id, created_by, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        version["id"],
                        version["forestBlockId"],
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
                    INSERT INTO forest_block_versions (
                        id,
                        forest_block_id,
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
                        version["forestBlockId"],
                        version["changeType"],
                        serializable_json(version.get("snapshot"), {}),
                        version.get("sourceVersionId") or None,
                        version.get("createdBy"),
                        version.get("createdAt"),
                    ),
                )
            conn.commit()
        return

    records = load_json_records(forest_block_versions_json_path())
    records.append(version)
    save_json_records(forest_block_versions_json_path(), records)


def record_block_version(
    block: dict[str, Any],
    change_type: str,
    context: AuthContext,
    *,
    source_version_id: str = "",
) -> dict[str, Any]:
    version = normalize_version_record(
        block,
        change_type,
        context,
        source_version_id=source_version_id,
    )
    save_block_version(version)
    return version


def load_block_versions(block_id: str) -> list[dict[str, Any]]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, forest_block_id, change_type, snapshot,
                           source_version_id, created_by, created_at
                    FROM forest_block_versions
                    WHERE forest_block_id = %s
                    ORDER BY created_at DESC, id DESC
                    """,
                    (block_id,),
                )
                return [normalize_postgis_version_row(row) for row in cur.fetchall()]
    if use_postgis():
        with postgis_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id::text,
                        forest_block_id::text,
                        change_type,
                        snapshot,
                        source_version_id::text,
                        created_by,
                        created_at
                    FROM forest_block_versions
                    WHERE forest_block_id = %s
                    ORDER BY created_at DESC, id DESC
                    """,
                    (block_id,),
                )
                return [normalize_postgis_version_row(row) for row in cur.fetchall()]

    records = [
        record
        for record in load_json_records(forest_block_versions_json_path())
        if str(record.get("forestBlockId") or "") == str(block_id)
    ]
    return sorted(
        records,
        key=lambda item: (str(item.get("createdAt") or ""), str(item.get("id") or "")),
        reverse=True,
    )


def find_block_version(block_id: str, version_id: str) -> dict[str, Any] | None:
    return next(
        (
            version
            for version in load_block_versions(block_id)
            if str(version.get("id") or "") == str(version_id)
        ),
        None,
    )


def iter_geometry_points(geometry: dict[str, Any] | None) -> list[tuple[float, float]]:
    if not geometry:
        return []
    coordinates = geometry.get("coordinates") or []
    points: list[tuple[float, float]] = []
    for polygon in coordinates:
        for ring in polygon:
            for point in ring:
                if len(point) >= 2:
                    points.append((float(point[0]), float(point[1])))
    return points


def bbox_intersects(geometry: dict[str, Any] | None, bbox: list[float] | None) -> bool:
    if bbox is None:
        return True
    points = iter_geometry_points(geometry)
    if not points:
        return False
    west, south, east, north = bbox
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return max(xs) >= west and min(xs) <= east and max(ys) >= south and min(ys) <= north


def parse_bbox(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        parts = [float(item.strip()) for item in value.split(",")]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox must be west,south,east,north") from exc
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be west,south,east,north")
    west, south, east, north = parts
    if west >= east or south >= north:
        raise HTTPException(status_code=400, detail="bbox must be west,south,east,north")
    return parts


def postgis_connect():
    try:
        import psycopg
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"forest blocks PostGIS database requires psycopg. {exc}") from exc

    try:
        return psycopg.connect(get_settings().database_url)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="forest blocks PostGIS database is unavailable") from exc


def normalize_geometry_for_storage(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not geometry:
        return None
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        return {"type": "MultiPolygon", "coordinates": [coordinates]}
    if geometry_type == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": coordinates}
    return None


def serializable_json(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, ensure_ascii=False)


def decimal_to_float(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


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


def normalize_postgis_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
    else:
        source = dict(zip(POSTGIS_SELECT_COLUMNS, row))

    block: dict[str, Any] = {}
    for db_field, api_field in DB_TO_API_FIELD.items():
        value = source.get(db_field)
        if db_field in {"yield_estimate", "properties"}:
            value = json_value(value, {})
        elif db_field == "tags":
            value = json_value(value, [])
        elif db_field in {"created_at", "updated_at", "deleted_at"}:
            value = datetime_to_iso(value)
        else:
            value = decimal_to_float(value)
        block[api_field] = value

    block.setdefault("yieldEstimate", {})
    block.setdefault("tags", [])
    block.setdefault("properties", {})
    return block


def normalize_mysql_row(row: Any) -> dict[str, Any]:
    block = normalize_postgis_row(row)
    block["geometry"] = json_value(block.get("geometry"), None)
    return block


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


def postgis_where(
    *,
    filters: ForestBlockFilters | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
    block_id: str | None = None,
    block_code: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    if block_id:
        clauses.append("id = %s")
        params.append(block_id)
    if block_code:
        clauses.append("block_code = %s")
        params.append(block_code)

    if context and context_has_scoped_areas(context):
        scoped_areas = sorted(effective_areas(context))
        if not scoped_areas:
            clauses.append("FALSE")
        elif "*" not in scoped_areas:
            placeholders = ", ".join(["%s"] * len(scoped_areas))
            clauses.append(f"(county_code IS NULL OR county_code IN ({placeholders}))")
            params.extend(scoped_areas)
    if context:
        for scope_key, _api_field, db_field in FOREST_BLOCK_FINE_SCOPE_FIELDS:
            if not has_effective_data_scope(context, scope_key):
                continue
            scoped_values = sorted(effective_data_scope_values(context, scope_key))
            if not scoped_values:
                clauses.append("FALSE")
            elif "*" not in scoped_values:
                placeholders = ", ".join(["%s"] * len(scoped_values))
                clauses.append(f"{db_field} IN ({placeholders})")
                params.extend(scoped_values)

    if filters:
        exact_filters = {
            "countyCode": "county_code",
            "townCode": "town_code",
            "villageCode": "village_code",
            "baseType": "base_type",
            "operationType": "operation_type",
            "qualityGrade": "quality_grade",
            "healthStatus": "health_status",
            "riskLevel": "risk_level",
        }
        for api_field, db_field in exact_filters.items():
            value = getattr(filters, api_field)
            if value:
                clauses.append(f"{db_field} = %s")
                params.append(value)

        if filters.q:
            pattern = f"%{filters.q}%"
            clauses.append(
                "(block_code ILIKE %s OR name ILIKE %s OR county_name ILIKE %s OR town_name ILIKE %s OR village_name ILIKE %s OR properties::text ILIKE %s)"
            )
            params.extend([pattern] * 6)

        bbox = parse_bbox(filters.bbox)
        if bbox:
            clauses.append("geometry && ST_MakeEnvelope(%s, %s, %s, %s, 4326)")
            params.extend(bbox)

    if not include_deleted:
        clauses.append(
            "NOT (block_code ILIKE %s OR (name LIKE %s AND name LIKE %s) OR name LIKE %s)"
        )
        params.extend(["BAMBOO-RIGHTS-%", "%林权%", "%档案%", "%竹林档案"])

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def mysql_where(
    *,
    filters: ForestBlockFilters | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
    block_id: str | None = None,
    block_code: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if not include_deleted:
        clauses.append("b.deleted_at IS NULL")
    if block_id:
        clauses.append("b.id = %s")
        params.append(block_id)
    if block_code:
        clauses.append("b.block_code = %s")
        params.append(block_code)

    if context and context_has_scoped_areas(context):
        scoped_areas = sorted(effective_areas(context))
        if not scoped_areas:
            clauses.append("FALSE")
        elif "*" not in scoped_areas:
            placeholders = ", ".join(["%s"] * len(scoped_areas))
            clauses.append(f"(b.county_code IS NULL OR b.county_code IN ({placeholders}))")
            params.extend(scoped_areas)
    if context:
        for scope_key, _api_field, db_field in FOREST_BLOCK_FINE_SCOPE_FIELDS:
            if not has_effective_data_scope(context, scope_key):
                continue
            scoped_values = sorted(effective_data_scope_values(context, scope_key))
            if not scoped_values:
                clauses.append("FALSE")
            elif "*" not in scoped_values:
                placeholders = ", ".join(["%s"] * len(scoped_values))
                clauses.append(f"b.{db_field} IN ({placeholders})")
                params.extend(scoped_values)

    bbox = None
    if filters:
        exact_filters = {
            "countyCode": "county_code",
            "townCode": "town_code",
            "villageCode": "village_code",
            "baseType": "base_type",
            "operationType": "operation_type",
            "qualityGrade": "quality_grade",
            "healthStatus": "health_status",
            "riskLevel": "risk_level",
        }
        for api_field, db_field in exact_filters.items():
            value = getattr(filters, api_field)
            if value:
                clauses.append(f"b.{db_field} = %s")
                params.append(value)
        if filters.q:
            pattern = f"%{filters.q}%"
            clauses.append(
                "(b.block_code LIKE %s OR b.name LIKE %s OR b.county_name LIKE %s OR "
                "b.town_name LIKE %s OR b.village_name LIKE %s OR CAST(b.properties AS CHAR) LIKE %s)"
            )
            params.extend([pattern] * 6)
        bbox = parse_bbox(filters.bbox)

    if not include_deleted:
        clauses.append(
            "NOT (b.block_code LIKE %s OR (b.name LIKE %s AND b.name LIKE %s) OR b.name LIKE %s)"
        )
        params.extend(["BAMBOO-RIGHTS-%", "%林权%", "%档案%", "%竹林档案"])

    if bbox:
        west, south, east, north = bbox
        envelope_wkt = (
            f"POLYGON(({west} {south},{east} {south},{east} {north},"
            f"{west} {north},{west} {south}))"
        )
        clauses.append(
            "MBRIntersects(g.geometry, ST_GeomFromText(%s, 4326, 'axis-order=long-lat'))"
        )
        params.append(envelope_wkt)

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def fetch_blocks_mysql(
    *,
    filters: ForestBlockFilters | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
    limit: int | None = None,
    offset: int = 0,
    block_id: str | None = None,
    block_code: str | None = None,
    geometry_tolerance: float = 0,
) -> list[dict[str, Any]]:
    where_sql, params = mysql_where(
        filters=filters,
        context=context,
        include_deleted=include_deleted,
        block_id=block_id,
        block_code=block_code,
    )
    has_bbox = bool(filters and parse_bbox(filters.bbox))
    select_sql = mysql_select_sql_for_filters(has_bbox=has_bbox)
    sql = f"{select_sql}{where_sql} ORDER BY b.updated_at DESC, b.block_code"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            blocks = [normalize_mysql_row(row) for row in cur.fetchall()]
    if geometry_tolerance > 0:
        for block in blocks:
            block["geometry"] = simplify_forest_geometry(block.get("geometry"), geometry_tolerance)
    return blocks


def count_blocks_mysql(filters: ForestBlockFilters, context: AuthContext) -> int:
    where_sql, params = mysql_where(
        filters=filters,
        context=context,
        include_deleted=filters.includeDeleted,
    )
    if parse_bbox(filters.bbox):
        from_sql = (
            "FROM forest_block_geometries g FORCE INDEX (idx_forest_block_geometry) "
            "STRAIGHT_JOIN forest_blocks b ON b.id = g.forest_block_id"
        )
    else:
        from_sql = (
            "FROM forest_blocks b "
            "LEFT JOIN forest_block_geometries g ON g.forest_block_id = b.id"
        )
    sql = f"SELECT COUNT(*) {from_sql}{where_sql}"
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


MYSQL_BLOCK_COLUMNS = [
    "id",
    "block_code",
    "name",
    "county_code",
    "county_name",
    "town_code",
    "town_name",
    "village_code",
    "village_name",
    "base_type",
    "operation_type",
    "forest_type",
    "area_mu",
    "slope_degree",
    "ownership_status",
    "management_status",
    "quality_grade",
    "health_status",
    "risk_level",
    "bamboo_age",
    "avg_dbh_cm",
    "avg_height_m",
    "standing_density",
    "carbon_estimate_tco2e",
    "yield_estimate",
    "tags",
    "properties",
    "source_batch_id",
    "created_at",
    "updated_at",
    "deleted_at",
]


def mysql_block_values(block: dict[str, Any]) -> tuple[Any, ...]:
    values: dict[str, Any] = {
        db_field: block.get(api_field)
        for db_field, api_field in DB_TO_API_FIELD.items()
        if db_field in MYSQL_BLOCK_COLUMNS
    }
    values["yield_estimate"] = serializable_json(block.get("yieldEstimate"), {})
    values["tags"] = serializable_json(block.get("tags"), [])
    values["properties"] = serializable_json(block.get("properties"), {})
    values["created_at"] = mysql_datetime(block.get("createdAt"))
    values["updated_at"] = mysql_datetime(block.get("updatedAt"))
    values["deleted_at"] = mysql_datetime(block.get("deletedAt"))
    return tuple(values.get(column) for column in MYSQL_BLOCK_COLUMNS)


def mysql_block_upsert_sql() -> str:
    columns_sql = ", ".join(MYSQL_BLOCK_COLUMNS)
    placeholders = ", ".join(["%s"] * len(MYSQL_BLOCK_COLUMNS))
    update_sql = ", ".join(
        f"{column} = VALUES({column})" for column in MYSQL_BLOCK_COLUMNS if column != "id"
    )
    return (
        f"INSERT INTO forest_blocks ({columns_sql}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_sql}"
    )


MYSQL_GEOMETRY_UPSERT_SQL = """
    INSERT INTO forest_block_geometries (
        forest_block_id, geometry, centroid,
        min_longitude, min_latitude, max_longitude, max_latitude,
        vertex_count, updated_at
    ) VALUES (
        %s,
        ST_GeomFromGeoJSON(%s, 1, 4326),
        ST_GeomFromText(%s, 4326, 'axis-order=long-lat'),
        %s, %s, %s, %s, %s, %s
    )
    ON DUPLICATE KEY UPDATE
        geometry = VALUES(geometry),
        centroid = VALUES(centroid),
        min_longitude = VALUES(min_longitude),
        min_latitude = VALUES(min_latitude),
        max_longitude = VALUES(max_longitude),
        max_latitude = VALUES(max_latitude),
        vertex_count = VALUES(vertex_count),
        updated_at = VALUES(updated_at)
"""


def mysql_geometry_values(block: dict[str, Any]) -> tuple[Any, ...] | None:
    geometry = normalize_geometry_for_storage(block.get("geometry"))
    points = iter_geometry_points(geometry)
    if not geometry or not points:
        return None
    geometry_json = json.dumps(geometry, ensure_ascii=False)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    center_x = (min(xs) + max(xs)) / 2
    center_y = (min(ys) + max(ys)) / 2
    return (
        block.get("id"),
        geometry_json,
        f"POINT({center_x:.15g} {center_y:.15g})",
        min(xs),
        min(ys),
        max(xs),
        max(ys),
        len(points),
        mysql_datetime(block.get("updatedAt")),
    )


def execute_upsert_block_mysql(cur: Any, block: dict[str, Any]) -> None:
    cur.execute(mysql_block_upsert_sql(), mysql_block_values(block))

    geometry_values = mysql_geometry_values(block)
    if geometry_values is None:
        cur.execute("DELETE FROM forest_block_geometries WHERE forest_block_id = %s", (block.get("id"),))
        return
    cur.execute(MYSQL_GEOMETRY_UPSERT_SQL, geometry_values)


def upsert_blocks_mysql(blocks: list[dict[str, Any]]) -> None:
    if not blocks:
        return
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            for start in range(0, len(blocks), FOREST_BLOCK_MYSQL_WRITE_BATCH_SIZE):
                batch = blocks[start : start + FOREST_BLOCK_MYSQL_WRITE_BATCH_SIZE]
                cur.executemany(mysql_block_upsert_sql(), [mysql_block_values(block) for block in batch])
                geometry_rows: list[tuple[Any, ...]] = []
                missing_geometry_ids: list[str] = []
                for block in batch:
                    geometry_values = mysql_geometry_values(block)
                    if geometry_values is None:
                        if block.get("id"):
                            missing_geometry_ids.append(str(block["id"]))
                    else:
                        geometry_rows.append(geometry_values)
                if geometry_rows:
                    cur.executemany(MYSQL_GEOMETRY_UPSERT_SQL, geometry_rows)
                if missing_geometry_ids:
                    placeholders = ", ".join(["%s"] * len(missing_geometry_ids))
                    cur.execute(
                        f"DELETE FROM forest_block_geometries WHERE forest_block_id IN ({placeholders})",
                        tuple(missing_geometry_ids),
                    )
        conn.commit()
    bump_forest_vector_tile_revision()


def block_identities_by_codes(block_codes: list[str]) -> dict[str, dict[str, Any]]:
    codes = list(dict.fromkeys(str(code).strip() for code in block_codes if str(code).strip()))
    if not codes:
        return {}

    if use_mysql() or use_postgis():
        connect = mysql_connect if use_mysql() else postgis_connect
        table_alias = "b" if use_mysql() else ""
        prefix = f"{table_alias}." if table_alias else ""
        identities: dict[str, dict[str, Any]] = {}
        with connect() as conn:
            with conn.cursor() as cur:
                for start in range(0, len(codes), FOREST_BLOCK_IDENTITY_LOOKUP_BATCH_SIZE):
                    batch = codes[start : start + FOREST_BLOCK_IDENTITY_LOOKUP_BATCH_SIZE]
                    placeholders = ", ".join(["%s"] * len(batch))
                    cur.execute(
                        f"SELECT {prefix}id, {prefix}block_code, {prefix}created_at, {prefix}deleted_at "
                        f"FROM forest_blocks {table_alias} WHERE {prefix}block_code IN ({placeholders})",
                        tuple(batch),
                    )
                    for row in cur.fetchall():
                        block_id, block_code, created_at, deleted_at = row
                        identities[str(block_code)] = {
                            "id": str(block_id),
                            "blockCode": str(block_code),
                            "createdAt": datetime_to_iso(created_at),
                            "deletedAt": datetime_to_iso(deleted_at),
                        }
        return identities

    return {
        str(block.get("blockCode")): {
            "id": block.get("id"),
            "blockCode": block.get("blockCode"),
            "createdAt": block.get("createdAt"),
            "deletedAt": block.get("deletedAt"),
        }
        for block in load_all_blocks()
        if block.get("blockCode")
    }


def first_block_mysql(
    *,
    block_id: str | None = None,
    block_code: str | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    items = fetch_blocks_mysql(
        block_id=block_id,
        block_code=block_code,
        context=context,
        include_deleted=include_deleted,
        limit=1,
    )
    return items[0] if items else None


def fetch_blocks_postgis(
    *,
    filters: ForestBlockFilters | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
    limit: int | None = None,
    offset: int = 0,
    block_id: str | None = None,
    block_code: str | None = None,
    geometry_tolerance: float = 0,
) -> list[dict[str, Any]]:
    where_sql, params = postgis_where(
        filters=filters,
        context=context,
        include_deleted=include_deleted,
        block_id=block_id,
        block_code=block_code,
    )
    select_sql = POSTGIS_SIMPLIFIED_SELECT_SQL if geometry_tolerance > 0 else POSTGIS_SELECT_SQL
    if geometry_tolerance > 0:
        params = [geometry_tolerance, *params]
    sql = f"{select_sql}{where_sql} ORDER BY updated_at DESC, block_code"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_row(row) for row in cur.fetchall()]


def count_blocks_postgis(filters: ForestBlockFilters, context: AuthContext) -> int:
    where_sql, params = postgis_where(filters=filters, context=context, include_deleted=filters.includeDeleted)
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM forest_blocks{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def summary_bucket_postgis(filters: ForestBlockFilters, context: AuthContext, db_field: str) -> dict[str, int]:
    where_sql, params = postgis_where(filters=filters, context=context, include_deleted=filters.includeDeleted)
    bucket_expr = f"COALESCE(NULLIF({db_field}, ''), 'unknown')"
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {bucket_expr} AS bucket, COUNT(*) FROM forest_blocks{where_sql} GROUP BY bucket",
                tuple(params),
            )
            rows = cur.fetchall()
    return {str(row[0] or "unknown"): int(row[1] or 0) for row in rows}


def forest_block_summary_postgis(filters: ForestBlockFilters, context: AuthContext) -> dict[str, Any]:
    where_sql, params = postgis_where(filters=filters, context=context, include_deleted=filters.includeDeleted)
    lower_healthy_values = [value for value in POSTGIS_HEALTHY_STATUS_VALUES if value.isascii()]
    literal_healthy_values = [value for value in POSTGIS_HEALTHY_STATUS_VALUES if not value.isascii()]
    lower_placeholders = ", ".join(["%s"] * len(lower_healthy_values))
    literal_placeholders = ", ".join(["%s"] * len(literal_healthy_values))
    healthy_sql_parts = []
    healthy_params: list[Any] = []
    if lower_healthy_values:
        healthy_sql_parts.append(f"LOWER(COALESCE(health_status, '')) IN ({lower_placeholders})")
        healthy_params.extend(lower_healthy_values)
    if literal_healthy_values:
        healthy_sql_parts.append(f"health_status IN ({literal_placeholders})")
        healthy_params.extend(literal_healthy_values)
    healthy_sql = " OR ".join(healthy_sql_parts) or "FALSE"
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                    SELECT
                        COUNT(*),
                        COALESCE(SUM(area_mu), 0),
                        COUNT(*) FILTER (WHERE {healthy_sql})
                    FROM forest_blocks{where_sql}
                """,
                tuple(params + healthy_params),
            )
            row = cur.fetchone()
    total = int(row[0] or 0) if row else 0
    total_area_mu = round(float(row[1] or 0), 2) if row else 0
    healthy_count = int(row[2] or 0) if row else 0
    return {
        "total": total,
        "totalAreaMu": total_area_mu,
        "healthyCount": healthy_count,
        "healthyRate": round((healthy_count / total) * 100) if total else 0,
        "riskLevel": summary_bucket_postgis(filters, context, "risk_level"),
        "qualityGrade": summary_bucket_postgis(filters, context, "quality_grade"),
        "baseType": summary_bucket_postgis(filters, context, "base_type"),
        "healthStatus": summary_bucket_postgis(filters, context, "health_status"),
    }


def summary_bucket_mysql(filters: ForestBlockFilters, context: AuthContext, db_field: str) -> dict[str, int]:
    where_sql, params = mysql_where(
        filters=filters,
        context=context,
        include_deleted=filters.includeDeleted,
    )
    bucket_expr = f"COALESCE(NULLIF(b.{db_field}, ''), 'unknown')"
    sql = (
        f"SELECT {bucket_expr} AS bucket, COUNT(*) FROM forest_blocks b "
        "LEFT JOIN forest_block_geometries g ON g.forest_block_id = b.id"
        f"{where_sql} GROUP BY bucket"
    )
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
    return {str(row[0] or "unknown"): int(row[1] or 0) for row in rows}


def forest_block_summary_mysql(filters: ForestBlockFilters, context: AuthContext) -> dict[str, Any]:
    where_sql, where_params = mysql_where(
        filters=filters,
        context=context,
        include_deleted=filters.includeDeleted,
    )
    healthy_values = list(POSTGIS_HEALTHY_STATUS_VALUES)
    placeholders = ", ".join(["%s"] * len(healthy_values))
    join_sql = " LEFT JOIN forest_block_geometries g ON g.forest_block_id = b.id" if filters.bbox else ""
    sql = f"""
        SELECT
            'summary' AS metric,
            '' AS bucket,
            COUNT(*) AS count_value,
            COALESCE(SUM(b.area_mu), 0) AS area_value,
            COALESCE(SUM(CASE WHEN LOWER(COALESCE(b.health_status, '')) IN ({placeholders}) THEN 1 ELSE 0 END), 0) AS healthy_value
        FROM forest_blocks b{join_sql}{where_sql}
        UNION ALL
        SELECT
            'riskLevel' AS metric,
            COALESCE(NULLIF(TRIM(b.risk_level), ''), 'unknown') AS bucket,
            COUNT(*) AS count_value,
            0 AS area_value,
            0 AS healthy_value
        FROM forest_blocks b{join_sql}{where_sql}
        GROUP BY bucket
        UNION ALL
        SELECT
            'qualityGrade' AS metric,
            COALESCE(NULLIF(TRIM(b.quality_grade), ''), 'unknown') AS bucket,
            COUNT(*) AS count_value,
            0 AS area_value,
            0 AS healthy_value
        FROM forest_blocks b{join_sql}{where_sql}
        GROUP BY bucket
        UNION ALL
        SELECT
            'baseType' AS metric,
            COALESCE(NULLIF(TRIM(b.base_type), ''), 'unknown') AS bucket,
            COUNT(*) AS count_value,
            0 AS area_value,
            0 AS healthy_value
        FROM forest_blocks b{join_sql}{where_sql}
        GROUP BY bucket
        UNION ALL
        SELECT
            'healthStatus' AS metric,
            COALESCE(NULLIF(TRIM(b.health_status), ''), 'unknown') AS bucket,
            COUNT(*) AS count_value,
            0 AS area_value,
            0 AS healthy_value
        FROM forest_blocks b{join_sql}{where_sql}
        GROUP BY bucket
    """
    params = healthy_values + where_params + (where_params * 4)
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

    total = 0
    total_area_mu = 0.0
    healthy_count = 0
    buckets: dict[str, dict[str, int]] = {
        "riskLevel": {},
        "qualityGrade": {},
        "baseType": {},
        "healthStatus": {},
    }
    for metric, bucket, count_value, area_value, healthy_value in rows:
        metric_key = str(metric or "")
        if metric_key == "summary":
            total = int(count_value or 0)
            total_area_mu = round(float(area_value or 0), 2)
            healthy_count = int(healthy_value or 0)
            continue
        if metric_key in buckets:
            buckets[metric_key][str(bucket or "unknown")] = int(count_value or 0)

    return {
        "total": total,
        "totalAreaMu": total_area_mu,
        "healthyCount": healthy_count,
        "healthyRate": round((healthy_count / total) * 100) if total else 0,
        **buckets,
    }


def first_block_postgis(
    *,
    block_id: str | None = None,
    block_code: str | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    items = fetch_blocks_postgis(
        block_id=block_id,
        block_code=block_code,
        context=context,
        include_deleted=include_deleted,
        limit=1,
    )
    return items[0] if items else None


def postgis_block_values(block: dict[str, Any]) -> tuple[Any, ...]:
    geometry = normalize_geometry_for_storage(block.get("geometry"))
    geometry_json = json.dumps(geometry, ensure_ascii=False) if geometry else None
    return (
        block.get("id"),
        block.get("blockCode"),
        block.get("name"),
        block.get("countyCode"),
        block.get("countyName"),
        block.get("townCode"),
        block.get("townName"),
        block.get("villageCode"),
        block.get("villageName"),
        block.get("baseType"),
        block.get("operationType"),
        block.get("forestType"),
        block.get("areaMu"),
        block.get("slopeDegree"),
        block.get("ownershipStatus"),
        block.get("managementStatus"),
        block.get("qualityGrade"),
        block.get("healthStatus"),
        block.get("riskLevel"),
        block.get("bambooAge"),
        block.get("avgDbhCm"),
        block.get("avgHeightM"),
        block.get("standingDensity"),
        block.get("carbonEstimateTco2e"),
        serializable_json(block.get("yieldEstimate"), {}),
        serializable_json(block.get("tags"), []),
        serializable_json(block.get("properties"), {}),
        geometry_json,
        geometry_json,
        geometry_json,
        geometry_json,
        block.get("createdAt"),
        block.get("updatedAt"),
        block.get("deletedAt"),
    )


def execute_upsert_block_postgis(cur: Any, block: dict[str, Any]) -> None:
    cur.execute(
        """
                INSERT INTO forest_blocks (
                    id,
                    block_code,
                    name,
                    county_code,
                    county_name,
                    town_code,
                    town_name,
                    village_code,
                    village_name,
                    base_type,
                    operation_type,
                    forest_type,
                    area_mu,
                    slope_degree,
                    ownership_status,
                    management_status,
                    quality_grade,
                    health_status,
                    risk_level,
                    bamboo_age,
                    avg_dbh_cm,
                    avg_height_m,
                    standing_density,
                    carbon_estimate_tco2e,
                    yield_estimate,
                    tags,
                    properties,
                    geometry,
                    centroid,
                    created_at,
                    updated_at,
                    deleted_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb,
                    %s::jsonb,
                    %s::jsonb,
                    CASE WHEN %s IS NULL THEN NULL ELSE ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) END,
                    CASE WHEN %s IS NULL THEN NULL ELSE ST_Centroid(ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))) END,
                    %s, %s, %s
                )
                ON CONFLICT (id) DO UPDATE SET
                    block_code = EXCLUDED.block_code,
                    name = EXCLUDED.name,
                    county_code = EXCLUDED.county_code,
                    county_name = EXCLUDED.county_name,
                    town_code = EXCLUDED.town_code,
                    town_name = EXCLUDED.town_name,
                    village_code = EXCLUDED.village_code,
                    village_name = EXCLUDED.village_name,
                    base_type = EXCLUDED.base_type,
                    operation_type = EXCLUDED.operation_type,
                    forest_type = EXCLUDED.forest_type,
                    area_mu = EXCLUDED.area_mu,
                    slope_degree = EXCLUDED.slope_degree,
                    ownership_status = EXCLUDED.ownership_status,
                    management_status = EXCLUDED.management_status,
                    quality_grade = EXCLUDED.quality_grade,
                    health_status = EXCLUDED.health_status,
                    risk_level = EXCLUDED.risk_level,
                    bamboo_age = EXCLUDED.bamboo_age,
                    avg_dbh_cm = EXCLUDED.avg_dbh_cm,
                    avg_height_m = EXCLUDED.avg_height_m,
                    standing_density = EXCLUDED.standing_density,
                    carbon_estimate_tco2e = EXCLUDED.carbon_estimate_tco2e,
                    yield_estimate = EXCLUDED.yield_estimate,
                    tags = EXCLUDED.tags,
                    properties = EXCLUDED.properties,
                    geometry = EXCLUDED.geometry,
                    centroid = EXCLUDED.centroid,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    deleted_at = EXCLUDED.deleted_at
                """,
        postgis_block_values(block),
    )


def upsert_blocks_postgis(blocks: list[dict[str, Any]]) -> None:
    if not blocks:
        return
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            for block in blocks:
                execute_upsert_block_postgis(cur, block)
        conn.commit()
    bump_forest_vector_tile_revision()


def upsert_block_postgis(block: dict[str, Any]) -> None:
    upsert_blocks_postgis([block])


def save_block(block: dict[str, Any]) -> None:
    if use_mysql():
        upsert_blocks_mysql([block])
        return
    if use_postgis():
        upsert_block_postgis(block)
        return

    blocks = load_all_blocks()
    for index, existing in enumerate(blocks):
        if existing.get("id") == block.get("id"):
            blocks[index] = block
            save_blocks(blocks)
            return
    blocks.append(block)
    save_blocks(blocks)


def block_by_code(block_code: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        return first_block_mysql(block_code=block_code, include_deleted=include_deleted)
    if use_postgis():
        return first_block_postgis(block_code=block_code, include_deleted=include_deleted)

    for block in load_all_blocks():
        if block.get("blockCode") == block_code and (include_deleted or not block.get("deletedAt")):
            return block
    return None


def load_all_blocks() -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_blocks_mysql(include_deleted=True)
    if use_postgis():
        return fetch_blocks_postgis(include_deleted=True)
    return load_json_records(forest_blocks_json_path())


def load_blocks() -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_blocks_mysql()
    if use_postgis():
        return fetch_blocks_postgis()
    return [
        item
        for item in load_all_blocks()
        if not item.get("deletedAt") and not is_rights_archive_like_block(item)
    ]


def save_blocks(blocks: list[dict[str, Any]]) -> None:
    if use_mysql():
        upsert_blocks_mysql(blocks)
        return
    if use_postgis():
        upsert_blocks_postgis(blocks)
        return
    save_json_records(forest_blocks_json_path(), blocks)
    bump_forest_vector_tile_revision()


def sync_blocks_administrative_divisions(blocks: list[dict[str, Any]]) -> None:
    try:
        from .dictionaries import sync_administrative_divisions_from_blocks

        sync_administrative_divisions_from_blocks(blocks)
    except Exception:
        # Startup seeding performs a complete repair pass if an optional sync fails.
        return


def sync_block_administrative_divisions(block: dict[str, Any]) -> None:
    sync_blocks_administrative_divisions([block])


def context_has_scoped_areas(context: AuthContext) -> bool:
    return has_effective_area_scope(context)


def require_target_area_allowed(context: AuthContext, county_code: str | None) -> None:
    if context_has_scoped_areas(context) and not county_code:
        raise HTTPException(status_code=403, detail="Area access denied")
    if not area_allowed(context, county_code):
        raise HTTPException(status_code=403, detail="Area access denied")


def block_allowed(context: AuthContext, block: dict[str, Any]) -> bool:
    if not area_allowed(context, block.get("countyCode")):
        return False
    return all(
        data_scope_value_allowed(context, scope_key, block.get(api_field))
        for scope_key, api_field, _db_field in FOREST_BLOCK_FINE_SCOPE_FIELDS
    )


def require_target_block_allowed(context: AuthContext, block: dict[str, Any]) -> None:
    require_target_area_allowed(context, block.get("countyCode"))
    for scope_key, api_field, _db_field in FOREST_BLOCK_FINE_SCOPE_FIELDS:
        if not data_scope_value_allowed(context, scope_key, block.get(api_field)):
            raise HTTPException(status_code=403, detail="Area access denied")


def text_matches(block: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    searchable_properties = dict(block.get("properties") or {})
    searchable_properties.pop("rights", None)
    properties_text = json.dumps(searchable_properties, ensure_ascii=False)
    haystack = " ".join(
        str(block.get(key) or "")
        for key in ("blockCode", "name", "countyName", "townName", "villageName")
    )
    haystack = f"{haystack} {properties_text}".lower()
    return query.lower() in haystack


def block_matches_filters(
    block: dict[str, Any], filters: ForestBlockFilters, context: AuthContext
) -> bool:
    if not block_allowed(context, block):
        return False
    if filters.countyCode and block.get("countyCode") != filters.countyCode:
        return False
    if filters.townCode and block.get("townCode") != filters.townCode:
        return False
    if filters.villageCode and block.get("villageCode") != filters.villageCode:
        return False
    if filters.baseType and block.get("baseType") != filters.baseType:
        return False
    if filters.operationType and block.get("operationType") != filters.operationType:
        return False
    if filters.qualityGrade and block.get("qualityGrade") != filters.qualityGrade:
        return False
    if filters.healthStatus and block.get("healthStatus") != filters.healthStatus:
        return False
    if filters.riskLevel and block.get("riskLevel") != filters.riskLevel:
        return False
    if not text_matches(block, filters.q):
        return False
    if not bbox_intersects(block.get("geometry"), parse_bbox(filters.bbox)):
        return False
    return True


def list_forest_blocks(filters: ForestBlockFilters, context: AuthContext) -> dict[str, Any]:
    if use_mysql():
        items = fetch_blocks_mysql(
            filters=filters,
            context=context,
            include_deleted=filters.includeDeleted,
            limit=filters.limit,
            offset=filters.offset,
        )
        return {
            "items": [sanitize_block_for_ledger(item) for item in items],
            "total": count_blocks_mysql(filters, context),
            "limit": filters.limit,
            "offset": filters.offset,
        }
    if use_postgis():
        items = fetch_blocks_postgis(
            filters=filters,
            context=context,
            include_deleted=filters.includeDeleted,
            limit=filters.limit,
            offset=filters.offset,
        )
        return {
            "items": [sanitize_block_for_ledger(item) for item in items],
            "total": count_blocks_postgis(filters, context),
            "limit": filters.limit,
            "offset": filters.offset,
        }

    source_blocks = load_all_blocks() if filters.includeDeleted else load_blocks()
    blocks = [
        block
        for block in source_blocks
        if not is_rights_archive_like_block(block) and block_matches_filters(block, filters, context)
    ]
    items = blocks[filters.offset : filters.offset + filters.limit]
    return {
        "items": [sanitize_block_for_ledger(item) for item in items],
        "total": len(blocks),
        "limit": filters.limit,
        "offset": filters.offset,
    }


def filtered_forest_blocks(
    filters: ForestBlockFilters,
    context: AuthContext,
    *,
    limit: int | None = None,
    geometry_tolerance: float = 0,
) -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_blocks_mysql(
            filters=filters,
            context=context,
            limit=limit,
            geometry_tolerance=geometry_tolerance,
        )
    if use_postgis():
        return fetch_blocks_postgis(
            filters=filters,
            context=context,
            limit=limit,
            geometry_tolerance=geometry_tolerance,
        )
    blocks = [block for block in load_blocks() if block_matches_filters(block, filters, context)]
    return blocks[:limit] if limit is not None else blocks


def forest_block_feature_collection(
    filters: ForestBlockFilters,
    context: AuthContext,
    *,
    max_features: int,
    zoom: float = 14,
) -> dict[str, Any]:
    tolerance = simplification_tolerance_for_zoom(zoom)
    if use_mysql():
        total = count_blocks_mysql(filters, context)
        blocks = filtered_forest_blocks(
            filters,
            context,
            limit=max_features,
            geometry_tolerance=tolerance,
        )
    elif use_postgis():
        total = count_blocks_postgis(filters, context)
        blocks = filtered_forest_blocks(
            filters,
            context,
            limit=max_features,
            geometry_tolerance=tolerance,
        )
    else:
        all_blocks = [block for block in load_blocks() if block_matches_filters(block, filters, context)]
        total = len(all_blocks)
        blocks = all_blocks[:max_features]
    return {
        "type": "FeatureCollection",
        "meta": {
            "total": total,
            "returned": len(blocks),
            "maxFeatures": max_features,
            "truncated": total > len(blocks),
            "zoom": zoom,
            "geometryMode": "simplified" if tolerance > 0 else "full",
            "simplificationTolerance": tolerance,
        },
        "features": [
            {
                "type": "Feature",
                "id": block["id"],
                "geometry": (
                    block.get("geometry")
                    if use_mysql() or use_postgis() or tolerance <= 0
                    else simplify_forest_geometry(block.get("geometry"), tolerance)
                ),
                "properties": {
                    key: value
                    for key, value in sanitize_block_for_ledger(block).items()
                    if key != "geometry"
                },
            }
            for block in blocks
        ],
    }


def forest_block_summary(filters: ForestBlockFilters, context: AuthContext) -> dict[str, Any]:
    if use_mysql():
        return forest_block_summary_mysql(filters, context)
    if use_postgis():
        return forest_block_summary_postgis(filters, context)
    blocks = filtered_forest_blocks(filters, context)
    total_area_mu = 0.0
    healthy_count = 0
    summary: dict[str, Any] = {
        "total": len(blocks),
        "totalAreaMu": 0,
        "healthyCount": 0,
        "healthyRate": 0,
        "riskLevel": {},
        "qualityGrade": {},
        "baseType": {},
        "healthStatus": {},
    }
    for block in blocks:
        try:
            total_area_mu += float(block.get("areaMu") or 0)
        except (TypeError, ValueError):
            pass
        health_status = str(block.get("healthStatus") or "").strip()
        if health_status.casefold() in HEALTHY_STATUS_VALUES or health_status in HEALTHY_STATUS_VALUES:
            healthy_count += 1
        for key in ("riskLevel", "qualityGrade", "baseType", "healthStatus"):
            value = block.get(key) or "unknown"
            summary[key][value] = summary[key].get(value, 0) + 1
    summary["totalAreaMu"] = round(total_area_mu, 2)
    summary["healthyCount"] = healthy_count
    summary["healthyRate"] = round((healthy_count / len(blocks)) * 100) if blocks else 0
    return summary


def normalize_risk_level(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    for level, aliases in RISK_LEVEL_ALIASES.items():
        if normalized in aliases:
            return level
    return "unknown"


def normalize_quality_level(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in QUALITY_LEVELS else "unknown"


def aggregate_risk_level(risk_counts: dict[str, int]) -> str:
    for level in ("high", "medium", "low"):
        if int(risk_counts.get(level) or 0) > 0:
            return level
    return "unknown"


def geometry_center(geometry: dict[str, Any] | None) -> list[float] | None:
    points = iter_geometry_points(geometry)
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2]


def simplification_tolerance_for_zoom(zoom: float) -> float:
    if zoom >= 15:
        return 0
    if zoom >= 14:
        return 0.00001
    if zoom >= 13:
        return 0.00003
    if zoom >= 12:
        return 0.00008
    return 0.00015


def forest_vector_tile_cache_dir() -> Path:
    return get_data_dir() / "map-cache" / "forest-block-tiles"


def forest_vector_tile_revision_path() -> Path:
    return forest_vector_tile_cache_dir() / "revision.txt"


def prune_forest_vector_tile_cache(*, now: float | None = None, force: bool = False) -> dict[str, Any]:
    global FOREST_VECTOR_TILE_CACHE_LAST_PRUNE

    current_time = float(now if now is not None else time.time())
    if (
        not force
        and current_time - FOREST_VECTOR_TILE_CACHE_LAST_PRUNE
        < FOREST_VECTOR_TILE_CACHE_PRUNE_INTERVAL_SECONDS
    ):
        return {"skipped": True, "deletedFiles": 0, "reclaimedBytes": 0, "remainingBytes": 0}

    with FOREST_VECTOR_TILE_CACHE_PRUNE_LOCK:
        if (
            not force
            and current_time - FOREST_VECTOR_TILE_CACHE_LAST_PRUNE
            < FOREST_VECTOR_TILE_CACHE_PRUNE_INTERVAL_SECONDS
        ):
            return {"skipped": True, "deletedFiles": 0, "reclaimedBytes": 0, "remainingBytes": 0}
        FOREST_VECTOR_TILE_CACHE_LAST_PRUNE = current_time
        cache_dir = forest_vector_tile_cache_dir()
        if not cache_dir.exists():
            return {"skipped": False, "deletedFiles": 0, "reclaimedBytes": 0, "remainingBytes": 0}

        candidates: list[tuple[Path, float, int]] = []
        for path in cache_dir.rglob("*.pbf"):
            try:
                stat = path.stat()
            except OSError:
                continue
            candidates.append((path, stat.st_mtime, stat.st_size))

        deleted_files = 0
        reclaimed_bytes = 0
        retained: list[tuple[Path, float, int]] = []
        for path, modified_at, size in candidates:
            if current_time - modified_at <= FOREST_VECTOR_TILE_CACHE_MAX_AGE_SECONDS:
                retained.append((path, modified_at, size))
                continue
            try:
                path.unlink()
            except OSError:
                retained.append((path, modified_at, size))
                continue
            deleted_files += 1
            reclaimed_bytes += size

        remaining_bytes = sum(size for _path, _modified_at, size in retained)
        if remaining_bytes > FOREST_VECTOR_TILE_CACHE_MAX_BYTES:
            for path, _modified_at, size in sorted(retained, key=lambda item: item[1]):
                if remaining_bytes <= FOREST_VECTOR_TILE_CACHE_MAX_BYTES:
                    break
                try:
                    path.unlink()
                except OSError:
                    continue
                deleted_files += 1
                reclaimed_bytes += size
                remaining_bytes -= size

        for directory in sorted(
            (path for path in cache_dir.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass

        return {
            "skipped": False,
            "deletedFiles": deleted_files,
            "reclaimedBytes": reclaimed_bytes,
            "remainingBytes": remaining_bytes,
        }


def bump_forest_vector_tile_revision() -> str:
    revision = str(time.time_ns())
    path = forest_vector_tile_revision_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(revision, encoding="ascii")
    return revision


def forest_vector_tile_revision() -> str:
    path = forest_vector_tile_revision_path()
    if path.exists():
        value = path.read_text(encoding="ascii").strip()
        if value:
            return value
    source_path = forest_blocks_json_path()
    return str(source_path.stat().st_mtime_ns) if source_path.exists() else "0"


def vector_tile_xyz_bounds(z: int, x: int, y: int) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    tile_count = 2**z
    if z < 0 or z > 22 or x < 0 or y < 0 or x >= tile_count or y >= tile_count:
        raise HTTPException(status_code=400, detail="Invalid vector tile coordinate")

    west = x / tile_count * 360.0 - 180.0
    east = (x + 1) / tile_count * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / tile_count))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / tile_count))))

    half_world = 20037508.342789244
    tile_span = (half_world * 2) / tile_count
    left = -half_world + x * tile_span
    right = left + tile_span
    top = half_world - y * tile_span
    bottom = top - tile_span
    return (west, south, east, north), (left, bottom, right, top)


def vector_tile_query_bounds(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    west, south, east, north = bounds
    ratio = FOREST_VECTOR_TILE_BUFFER_PIXELS / FOREST_VECTOR_TILE_EXTENT
    longitude_buffer = (east - west) * ratio
    latitude_buffer = (north - south) * ratio
    return (
        max(-180.0, west - longitude_buffer),
        max(-85.05112878, south - latitude_buffer),
        min(180.0, east + longitude_buffer),
        min(85.05112878, north + latitude_buffer),
    )


def wgs84_to_web_mercator(longitude: float, latitude: float) -> tuple[float, float]:
    bounded_latitude = max(-85.05112878, min(85.05112878, float(latitude)))
    x = float(longitude) * 20037508.342789244 / 180.0
    y = math.log(math.tan((90.0 + bounded_latitude) * math.pi / 360.0)) / (math.pi / 180.0)
    return x, y * 20037508.342789244 / 180.0


def vector_tile_scope_signature(context: AuthContext) -> dict[str, Any]:
    if context_has_scoped_areas(context):
        areas = sorted(effective_areas(context))
    else:
        areas = ["*"]
    fine_scopes = {}
    for scope_key, _api_field, _db_field in FOREST_BLOCK_FINE_SCOPE_FIELDS:
        fine_scopes[scope_key] = (
            sorted(effective_data_scope_values(context, scope_key))
            if has_effective_data_scope(context, scope_key)
            else ["*"]
        )
    return {
        "user": context.user,
        "roles": sorted(context.roles),
        "projects": sorted(context.projects),
        "areas": areas,
        "dataScopes": fine_scopes,
    }


def vector_tile_cache_path(
    z: int,
    x: int,
    y: int,
    filters: ForestBlockFilters,
    context: AuthContext,
) -> Path:
    filter_payload = filters.model_dump(
        include={
            "q",
            "countyCode",
            "townCode",
            "villageCode",
            "baseType",
            "operationType",
            "qualityGrade",
            "healthStatus",
            "riskLevel",
        }
    )
    cache_payload = {
        "revision": forest_vector_tile_revision(),
        "filters": filter_payload,
        "scope": vector_tile_scope_signature(context),
    }
    digest = hashlib.sha256(
        json.dumps(cache_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return forest_vector_tile_cache_dir() / str(z) / str(x) / f"{y}-{digest}.pbf"


def scalar_vector_tile_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def encode_forest_vector_tile(
    blocks: list[dict[str, Any]],
    mercator_bounds: tuple[float, float, float, float],
) -> bytes:
    try:
        from mapbox_vector_tile import encode
        from mapbox_vector_tile.encoder import on_invalid_geometry_make_valid
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Vector tile encoder is unavailable: {exc}") from exc

    features = []
    for block in blocks:
        geometry = block.get("geometry")
        if not geometry:
            continue
        properties = {
            field: scalar_vector_tile_value(block.get(field))
            for field in FOREST_VECTOR_TILE_PROPERTY_FIELDS
            if block.get(field) is not None
        }
        features.append({"geometry": geometry, "properties": properties})
    return encode(
        {"name": "forest_blocks", "features": features},
        default_options={
            "quantize_bounds": mercator_bounds,
            "transformer": wgs84_to_web_mercator,
            "extents": FOREST_VECTOR_TILE_EXTENT,
            "on_invalid_geometry": on_invalid_geometry_make_valid,
        },
    )


def forest_block_vector_tile(
    z: int,
    x: int,
    y: int,
    filters: ForestBlockFilters,
    context: AuthContext,
    *,
    max_features: int,
) -> tuple[bytes, str]:
    wgs84_bounds, mercator_bounds = vector_tile_xyz_bounds(z, x, y)
    cache_path = vector_tile_cache_path(z, x, y, filters, context)
    if cache_path.exists() and time.time() - cache_path.stat().st_mtime <= FOREST_VECTOR_TILE_CACHE_TTL_SECONDS:
        return cache_path.read_bytes(), "HIT"

    query_bounds = vector_tile_query_bounds(wgs84_bounds)
    tile_filters = filters.model_copy(
        update={
            "bbox": ",".join(f"{value:.8f}" for value in query_bounds),
            "includeDeleted": False,
            "limit": max_features,
            "offset": 0,
        }
    )
    blocks = filtered_forest_blocks(
        tile_filters,
        context,
        limit=max_features,
        geometry_tolerance=simplification_tolerance_for_zoom(float(z)),
    )
    content = encode_forest_vector_tile(blocks, mercator_bounds)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = cache_path.with_name(f"{cache_path.name}.{uuid.uuid4().hex}.tmp")
    temporary_path.write_bytes(content)
    temporary_path.replace(cache_path)
    prune_forest_vector_tile_cache()
    return content, "MISS"


def point_segment_distance(
    point: list[float] | tuple[float, ...],
    start: list[float] | tuple[float, ...],
    end: list[float] | tuple[float, ...],
) -> float:
    px, py = float(point[0]), float(point[1])
    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    dx, dy = ex - sx, ey - sy
    if dx == 0 and dy == 0:
        return ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5
    ratio = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)))
    nearest_x = sx + ratio * dx
    nearest_y = sy + ratio * dy
    return ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** 0.5


def simplify_coordinate_path(points: list[list[float]], tolerance: float) -> list[list[float]]:
    if len(points) <= 2:
        return list(points)
    max_distance = 0.0
    split_index = 0
    for index in range(1, len(points) - 1):
        distance = point_segment_distance(points[index], points[0], points[-1])
        if distance > max_distance:
            max_distance = distance
            split_index = index
    if max_distance <= tolerance:
        return [points[0], points[-1]]
    left = simplify_coordinate_path(points[: split_index + 1], tolerance)
    right = simplify_coordinate_path(points[split_index:], tolerance)
    return [*left[:-1], *right]


def simplify_coordinate_ring(ring: list[list[float]], tolerance: float) -> list[list[float]]:
    if len(ring) <= 4:
        return list(ring)
    points = list(ring[:-1] if ring[0][:2] == ring[-1][:2] else ring)
    if len(points) <= 3:
        return list(ring)
    candidates = {
        min(range(len(points)), key=lambda index: float(points[index][0])),
        max(range(len(points)), key=lambda index: float(points[index][0])),
        min(range(len(points)), key=lambda index: float(points[index][1])),
        max(range(len(points)), key=lambda index: float(points[index][1])),
    }
    start_index, end_index = max(
        ((first, second) for first in candidates for second in candidates if first != second),
        key=lambda pair: (
            (float(points[pair[0]][0]) - float(points[pair[1]][0])) ** 2
            + (float(points[pair[0]][1]) - float(points[pair[1]][1])) ** 2
        ),
    )
    if start_index > end_index:
        start_index, end_index = end_index, start_index
    first_arc = points[start_index : end_index + 1]
    second_arc = [*points[end_index:], *points[: start_index + 1]]
    simplified = [
        *simplify_coordinate_path(first_arc, tolerance)[:-1],
        *simplify_coordinate_path(second_arc, tolerance)[:-1],
    ]
    if len(simplified) < 3:
        return list(ring)
    simplified.append(simplified[0])
    return simplified


def simplify_geometry_coordinates(geometry: dict[str, Any], tolerance: float) -> dict[str, Any]:
    geometry_type = str(geometry.get("type") or "")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "Polygon":
        return {
            "type": "Polygon",
            "coordinates": [simplify_coordinate_ring(ring, tolerance) for ring in coordinates],
        }
    if geometry_type == "MultiPolygon":
        return {
            "type": "MultiPolygon",
            "coordinates": [
                [simplify_coordinate_ring(ring, tolerance) for ring in polygon]
                for polygon in coordinates
            ],
        }
    return geometry


def simplify_forest_geometry(
    geometry: dict[str, Any] | None,
    tolerance: float,
) -> dict[str, Any] | None:
    if not geometry or tolerance <= 0:
        return geometry
    try:
        from shapely.geometry import mapping, shape

        simplified = shape(geometry).simplify(tolerance, preserve_topology=True)
        if simplified.is_empty:
            return geometry
        return normalize_geometry_for_storage(mapping(simplified)) or geometry
    except Exception:
        return simplify_geometry_coordinates(geometry, tolerance)


def aggregate_item(
    *,
    code: Any,
    name: Any,
    block_count: Any,
    area_mu: Any,
    centroid: list[float] | None,
    risk_counts: dict[str, int],
    quality_counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "code": str(code or "unknown"),
        "name": str(name or code or "unknown"),
        "blockCount": int(block_count or 0),
        "areaMu": round(float(area_mu or 0), 2),
        "centroid": [round(float(value), 6) for value in centroid] if centroid else None,
        "riskLevel": aggregate_risk_level(risk_counts),
        "riskCounts": risk_counts,
        "qualityCounts": quality_counts,
    }


def forest_block_aggregates_postgis(
    level: Literal["county", "town", "village"],
    filters: ForestBlockFilters,
    context: AuthContext,
) -> dict[str, Any]:
    _api_code, _api_name, db_code, db_name = FOREST_BLOCK_AGGREGATE_FIELDS[level]
    where_sql, params = postgis_where(filters=filters, context=context, include_deleted=False)
    sql = f"""
        SELECT
            COALESCE(NULLIF({db_code}, ''), 'unknown') AS group_code,
            COALESCE(NULLIF({db_name}, ''), NULLIF({db_code}, ''), 'unknown') AS group_name,
            COUNT(*) AS block_count,
            COALESCE(SUM(area_mu), 0) AS area_mu,
            ST_X(ST_Centroid(ST_Collect(COALESCE(centroid, ST_PointOnSurface(geometry))))) AS longitude,
            ST_Y(ST_Centroid(ST_Collect(COALESCE(centroid, ST_PointOnSurface(geometry))))) AS latitude,
            COUNT(*) FILTER (WHERE LOWER(COALESCE(risk_level, '')) IN ('high', 'high-risk', 'high_risk', '高', '高风险')) AS high_risk_count,
            COUNT(*) FILTER (WHERE LOWER(COALESCE(risk_level, '')) IN ('medium', 'middle', 'medium-risk', 'medium_risk', '中', '中风险')) AS medium_risk_count,
            COUNT(*) FILTER (WHERE LOWER(COALESCE(risk_level, '')) IN ('low', 'low-risk', 'low_risk', '低', '低风险')) AS low_risk_count,
            COUNT(*) FILTER (WHERE UPPER(COALESCE(quality_grade, '')) = 'A') AS quality_a_count,
            COUNT(*) FILTER (WHERE UPPER(COALESCE(quality_grade, '')) = 'B') AS quality_b_count,
            COUNT(*) FILTER (WHERE UPPER(COALESCE(quality_grade, '')) = 'C') AS quality_c_count
        FROM forest_blocks{where_sql}
        GROUP BY {db_code}, {db_name}
        ORDER BY block_count DESC, group_name, group_code
    """
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        (
            code,
            name,
            block_count,
            area_mu,
            longitude,
            latitude,
            high_count,
            medium_count,
            low_count,
            quality_a_count,
            quality_b_count,
            quality_c_count,
        ) = row
        block_count = int(block_count or 0)
        risk_counts = {
            "high": int(high_count or 0),
            "medium": int(medium_count or 0),
            "low": int(low_count or 0),
        }
        risk_counts["unknown"] = max(0, block_count - sum(risk_counts.values()))
        quality_counts = {
            "A": int(quality_a_count or 0),
            "B": int(quality_b_count or 0),
            "C": int(quality_c_count or 0),
        }
        quality_counts["unknown"] = max(0, block_count - sum(quality_counts.values()))
        centroid = [float(longitude), float(latitude)] if longitude is not None and latitude is not None else None
        items.append(
            aggregate_item(
                code=code,
                name=name,
                block_count=block_count,
                area_mu=area_mu,
                centroid=centroid,
                risk_counts=risk_counts,
                quality_counts=quality_counts,
            )
        )
    return {
        "level": level,
        "totalGroups": len(items),
        "totalBlocks": sum(item["blockCount"] for item in items),
        "totalAreaMu": round(sum(item["areaMu"] for item in items), 2),
        "items": items,
    }


def forest_block_aggregates_mysql(
    level: Literal["county", "town", "village"],
    filters: ForestBlockFilters,
    context: AuthContext,
) -> dict[str, Any]:
    _api_code, _api_name, db_code, db_name = FOREST_BLOCK_AGGREGATE_FIELDS[level]
    where_sql, params = mysql_where(filters=filters, context=context, include_deleted=False)
    sql = f"""
        SELECT
            COALESCE(NULLIF(b.{db_code}, ''), 'unknown') AS group_code,
            COALESCE(NULLIF(b.{db_name}, ''), NULLIF(b.{db_code}, ''), 'unknown') AS group_name,
            COUNT(*) AS block_count,
            COALESCE(SUM(b.area_mu), 0) AS area_mu,
            AVG(ST_Longitude(g.centroid)) AS longitude,
            AVG(ST_Latitude(g.centroid)) AS latitude,
            SUM(CASE WHEN LOWER(COALESCE(b.risk_level, '')) IN ('high', 'high-risk', 'high_risk', '高', '高风险') THEN 1 ELSE 0 END) AS high_risk_count,
            SUM(CASE WHEN LOWER(COALESCE(b.risk_level, '')) IN ('medium', 'middle', 'medium-risk', 'medium_risk', '中', '中风险') THEN 1 ELSE 0 END) AS medium_risk_count,
            SUM(CASE WHEN LOWER(COALESCE(b.risk_level, '')) IN ('low', 'low-risk', 'low_risk', '低', '低风险') THEN 1 ELSE 0 END) AS low_risk_count,
            SUM(CASE WHEN UPPER(COALESCE(b.quality_grade, '')) = 'A' THEN 1 ELSE 0 END) AS quality_a_count,
            SUM(CASE WHEN UPPER(COALESCE(b.quality_grade, '')) = 'B' THEN 1 ELSE 0 END) AS quality_b_count,
            SUM(CASE WHEN UPPER(COALESCE(b.quality_grade, '')) = 'C' THEN 1 ELSE 0 END) AS quality_c_count
        FROM forest_blocks b
        LEFT JOIN forest_block_geometries g ON g.forest_block_id = b.id
        {where_sql}
        GROUP BY b.{db_code}, b.{db_name}
        ORDER BY block_count DESC, group_name, group_code
    """
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        (
            code,
            name,
            block_count,
            area_mu,
            longitude,
            latitude,
            high_count,
            medium_count,
            low_count,
            quality_a_count,
            quality_b_count,
            quality_c_count,
        ) = row
        block_count = int(block_count or 0)
        risk_counts = {
            "high": int(high_count or 0),
            "medium": int(medium_count or 0),
            "low": int(low_count or 0),
        }
        risk_counts["unknown"] = max(0, block_count - sum(risk_counts.values()))
        quality_counts = {
            "A": int(quality_a_count or 0),
            "B": int(quality_b_count or 0),
            "C": int(quality_c_count or 0),
        }
        quality_counts["unknown"] = max(0, block_count - sum(quality_counts.values()))
        centroid = [float(longitude), float(latitude)] if longitude is not None and latitude is not None else None
        items.append(
            aggregate_item(
                code=code,
                name=name,
                block_count=block_count,
                area_mu=area_mu,
                centroid=centroid,
                risk_counts=risk_counts,
                quality_counts=quality_counts,
            )
        )
    return {
        "level": level,
        "totalGroups": len(items),
        "totalBlocks": sum(item["blockCount"] for item in items),
        "totalAreaMu": round(sum(item["areaMu"] for item in items), 2),
        "items": items,
    }


def forest_block_aggregates(
    level: Literal["county", "town", "village"],
    filters: ForestBlockFilters,
    context: AuthContext,
) -> dict[str, Any]:
    if use_mysql():
        return forest_block_aggregates_mysql(level, filters, context)
    if use_postgis():
        return forest_block_aggregates_postgis(level, filters, context)

    api_code, api_name, _db_code, _db_name = FOREST_BLOCK_AGGREGATE_FIELDS[level]
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for block in filtered_forest_blocks(filters, context):
        code = str(block.get(api_code) or "unknown")
        name = str(block.get(api_name) or block.get(api_code) or "unknown")
        group = groups.setdefault(
            (code, name),
            {
                "code": code,
                "name": name,
                "blockCount": 0,
                "areaMu": 0.0,
                "riskCounts": {"high": 0, "medium": 0, "low": 0, "unknown": 0},
                "qualityCounts": {"A": 0, "B": 0, "C": 0, "unknown": 0},
                "longitudeWeight": 0.0,
                "latitudeWeight": 0.0,
                "centroidWeight": 0.0,
            },
        )
        group["blockCount"] += 1
        area_mu = float(block.get("areaMu") or 0)
        group["areaMu"] += area_mu
        group["riskCounts"][normalize_risk_level(block.get("riskLevel"))] += 1
        group["qualityCounts"][normalize_quality_level(block.get("qualityGrade"))] += 1
        center = geometry_center(block.get("geometry"))
        if center:
            weight = area_mu if area_mu > 0 else 1.0
            group["longitudeWeight"] += center[0] * weight
            group["latitudeWeight"] += center[1] * weight
            group["centroidWeight"] += weight

    items = []
    for group in groups.values():
        weight = float(group.pop("centroidWeight") or 0)
        longitude_weight = float(group.pop("longitudeWeight") or 0)
        latitude_weight = float(group.pop("latitudeWeight") or 0)
        centroid = [longitude_weight / weight, latitude_weight / weight] if weight else None
        items.append(
            aggregate_item(
                code=group["code"],
                name=group["name"],
                block_count=group["blockCount"],
                area_mu=group["areaMu"],
                centroid=centroid,
                risk_counts=group["riskCounts"],
                quality_counts=group["qualityCounts"],
            )
        )
    items.sort(key=lambda item: (-item["blockCount"], item["name"], item["code"]))
    return {
        "level": level,
        "totalGroups": len(items),
        "totalBlocks": sum(item["blockCount"] for item in items),
        "totalAreaMu": round(sum(item["areaMu"] for item in items), 2),
        "items": items,
    }


def forest_block_facet_items(
    blocks: list[dict[str, Any]],
    key: str,
    label_key: str | None = None,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for block in blocks:
        value = str(block.get(key) or "").strip()
        if not value:
            continue
        label = str(block.get(label_key) or value).strip() if label_key else value
        bucket = buckets.setdefault(value, {"value": value, "label": label or value, "count": 0})
        bucket["count"] += 1
        if bucket["label"] == value and label and label != value:
            bucket["label"] = label
    return sorted(buckets.values(), key=lambda item: (str(item["value"]), str(item["label"])))


def forest_block_facets_mysql(filters: ForestBlockFilters, context: AuthContext) -> dict[str, Any]:
    where_sql, where_params = mysql_where(
        filters=filters,
        context=context,
        include_deleted=filters.includeDeleted,
    )
    join_sql = (
        " LEFT JOIN forest_block_geometries g ON g.forest_block_id = b.id"
        if filters.bbox
        else ""
    )
    queries: list[str] = []
    params: list[Any] = []
    for facet in FOREST_BLOCK_FACETS:
        key = str(facet["key"])
        db_field = str(facet["dbField"])
        db_label_field = str(facet.get("dbLabelField") or "")
        value_expr = f"NULLIF(TRIM(b.{db_field}), '')"
        label_expr = (
            f"COALESCE(MAX(NULLIF(TRIM(b.{db_label_field}), '')), {value_expr})"
            if db_label_field
            else value_expr
        )
        value_filter = f"{value_expr} IS NOT NULL"
        branch_where = (
            f"{where_sql} AND {value_filter}"
            if where_sql
            else f" WHERE {value_filter}"
        )
        queries.append(
            f"SELECT '{key}' AS facet_key, {value_expr} AS facet_value, "
            f"{label_expr} AS facet_label, COUNT(*) AS facet_count "
            f"FROM forest_blocks b{join_sql}{branch_where} GROUP BY {value_expr}"
        )
        params.extend(where_params)

    sql = " UNION ALL ".join(queries) + " ORDER BY facet_key, facet_value, facet_label"
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

    facets = {str(facet["key"]): [] for facet in FOREST_BLOCK_FACETS}
    for facet_key, value, label, count in rows:
        key = str(facet_key or "")
        normalized_value = str(value or "").strip()
        if key not in facets or not normalized_value:
            continue
        facets[key].append(
            {
                "value": normalized_value,
                "label": str(label or normalized_value).strip() or normalized_value,
                "count": int(count or 0),
            }
        )
    return {
        "summary": forest_block_summary_mysql(filters, context),
        "facets": facets,
    }


def forest_block_facets(filters: ForestBlockFilters, context: AuthContext) -> dict[str, Any]:
    if use_mysql():
        return forest_block_facets_mysql(filters, context)
    blocks = filtered_forest_blocks(filters, context)
    return {
        "summary": forest_block_summary(filters, context),
        "facets": {
            facet["key"]: forest_block_facet_items(blocks, facet["key"], facet.get("labelKey"))
            for facet in FOREST_BLOCK_FACETS
        },
    }


def filter_params(
    q: str = Query(default=""),
    countyCode: str = Query(default=""),
    townCode: str = Query(default=""),
    villageCode: str = Query(default=""),
    baseType: str = Query(default=""),
    operationType: str = Query(default=""),
    qualityGrade: str = Query(default=""),
    healthStatus: str = Query(default=""),
    riskLevel: str = Query(default=""),
    bbox: str = Query(default=""),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> ForestBlockFilters:
    return ForestBlockFilters(
        q=q,
        countyCode=countyCode,
        townCode=townCode,
        villageCode=villageCode,
        baseType=baseType,
        operationType=operationType,
        qualityGrade=qualityGrade,
        healthStatus=healthStatus,
        riskLevel=riskLevel,
        bbox=bbox,
        includeDeleted=includeDeleted,
        limit=limit,
        offset=offset,
    )


def find_block(block_id: str, context: AuthContext) -> dict[str, Any]:
    if use_mysql():
        block = first_block_mysql(block_id=block_id, context=context)
        if block is not None:
            return block
        raise HTTPException(status_code=404, detail="Forest block not found")
    if use_postgis():
        block = first_block_postgis(block_id=block_id, context=context)
        if block is not None:
            return block
        raise HTTPException(status_code=404, detail="Forest block not found")

    visible = ForestBlockFilters(limit=1000)
    for block in load_blocks():
        if block.get("id") == block_id and block_matches_filters(block, visible, context):
            return block
    raise HTTPException(status_code=404, detail="Forest block not found")


def find_block_any_state(block_id: str, context: AuthContext) -> dict[str, Any]:
    if use_mysql():
        block = first_block_mysql(block_id=block_id, context=context, include_deleted=True)
        if block is not None:
            return block
        raise HTTPException(status_code=404, detail="Forest block not found")
    if use_postgis():
        block = first_block_postgis(block_id=block_id, context=context, include_deleted=True)
        if block is not None:
            return block
        raise HTTPException(status_code=404, detail="Forest block not found")

    for block in load_all_blocks():
        if block.get("id") != block_id:
            continue
        if not block_allowed(context, block):
            raise HTTPException(status_code=404, detail="Forest block not found")
        return block
    raise HTTPException(status_code=404, detail="Forest block not found")


@router.get("/forest-blocks")
def list_forest_blocks_route(
    filters: ForestBlockFilters = Depends(filter_params),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    if filters.includeDeleted:
        require_permission(context, "forest.blocks.manage")
    return list_forest_blocks(filters, context)


@router.post("/forest-blocks")
def create_forest_block(
    payload: ForestBlockIn,
    context: AuthContext = Depends(request_context),
) -> ForestBlockOut:
    require_permission(context, "forest.blocks.create")
    require_target_block_allowed(context, payload.model_dump())
    if use_mysql() or use_postgis():
        if block_by_code(payload.blockCode, include_deleted=True):
            raise HTTPException(status_code=409, detail="blockCode already exists")
        block = sanitize_block_for_ledger(normalize_block(payload.model_dump()))
        save_block(block)
        sync_block_administrative_divisions(block)
        record_block_version(block, "create", context)
        return ForestBlockOut.model_validate(block)

    blocks = load_all_blocks()
    if any(item.get("blockCode") == payload.blockCode for item in blocks):
        raise HTTPException(status_code=409, detail="blockCode already exists")
    block = sanitize_block_for_ledger(normalize_block(payload.model_dump()))
    blocks.append(block)
    save_blocks(blocks)
    sync_block_administrative_divisions(block)
    record_block_version(block, "create", context)
    return ForestBlockOut.model_validate(block)


@router.get("/forest-blocks/{block_id}")
def get_forest_block(
    block_id: str,
    context: AuthContext = Depends(request_context),
) -> ForestBlockOut:
    return ForestBlockOut.model_validate(sanitize_block_for_ledger(find_block(block_id, context)))


@router.get("/forest-blocks/{block_id}/versions")
def list_forest_block_versions(
    block_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.blocks.view")
    find_block_any_state(block_id, context)
    versions = load_block_versions(block_id)
    return {
        "items": versions,
        "total": len(versions),
        "limit": len(versions),
        "offset": 0,
    }


@router.post("/forest-blocks/{block_id}/rollback")
def rollback_forest_block(
    block_id: str,
    payload: ForestBlockRollbackRequest,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.blocks.rollback")
    current = find_block_any_state(block_id, context)
    version = find_block_version(block_id, payload.versionId)
    if version is None:
        raise HTTPException(status_code=404, detail="Forest block version not found")
    snapshot = version.get("snapshot")
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=409, detail="Forest block version has no snapshot")
    rolled_back = sanitize_block_for_ledger(
        normalize_block(
            {
                **snapshot,
                "id": block_id,
                "blockCode": current.get("blockCode") or snapshot.get("blockCode"),
                "createdAt": snapshot.get("createdAt") or current.get("createdAt") or now_iso(),
            }
        )
    )
    require_target_block_allowed(context, rolled_back)
    save_block(rolled_back)
    rollback_version = record_block_version(
        rolled_back,
        "rollback",
        context,
        source_version_id=payload.versionId,
    )
    return {
        "ok": True,
        "rolledBack": block_id,
        "sourceVersionId": payload.versionId,
        "block": ForestBlockOut.model_validate(rolled_back).model_dump(),
        "version": rollback_version,
    }


@router.patch("/forest-blocks/{block_id}")
def patch_forest_block(
    block_id: str,
    payload: ForestBlockPatch,
    context: AuthContext = Depends(request_context),
) -> ForestBlockOut:
    require_permission(context, "forest.blocks.update")
    if use_mysql() or use_postgis():
        block = find_block(block_id, context)
        changes = payload.model_dump(exclude_unset=True)
        updated = sanitize_block_for_ledger(normalize_block(
            {
                **block,
                **changes,
                "id": block_id,
                "createdAt": block.get("createdAt", now_iso()),
                "deletedAt": block.get("deletedAt"),
            }
        ))
        require_target_block_allowed(context, updated)
        save_block(updated)
        sync_block_administrative_divisions(updated)
        record_block_version(updated, "update", context)
        return ForestBlockOut.model_validate(updated)

    blocks = load_all_blocks()
    for index, block in enumerate(blocks):
        if block.get("id") != block_id:
            continue
        if block.get("deletedAt"):
            raise HTTPException(status_code=404, detail="Forest block not found")
        if not block_allowed(context, block):
            raise HTTPException(status_code=404, detail="Forest block not found")
        changes = payload.model_dump(exclude_unset=True)
        updated = sanitize_block_for_ledger(normalize_block(
            {
                **block,
                **changes,
                "id": block_id,
                "createdAt": block.get("createdAt", now_iso()),
                "deletedAt": block.get("deletedAt"),
            }
        ))
        require_target_block_allowed(context, updated)
        blocks[index] = updated
        save_blocks(blocks)
        sync_block_administrative_divisions(updated)
        record_block_version(updated, "update", context)
        return ForestBlockOut.model_validate(updated)
    raise HTTPException(status_code=404, detail="Forest block not found")


@router.delete("/forest-blocks/{block_id}")
def delete_forest_block(
    block_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.blocks.delete")
    if use_mysql() or use_postgis():
        block = find_block(block_id, context)
        block["deletedAt"] = now_iso()
        block["updatedAt"] = block["deletedAt"]
        save_block(block)
        record_block_version(block, "delete", context)
        return {"ok": True, "deleted": block_id}

    blocks = load_all_blocks()
    for block in blocks:
        if block.get("id") != block_id:
            continue
        if block.get("deletedAt"):
            raise HTTPException(status_code=404, detail="Forest block not found")
        if not block_allowed(context, block):
            raise HTTPException(status_code=404, detail="Forest block not found")
        block["deletedAt"] = now_iso()
        block["updatedAt"] = block["deletedAt"]
        save_blocks(blocks)
        record_block_version(block, "delete", context)
        return {"ok": True, "deleted": block_id}
    raise HTTPException(status_code=404, detail="Forest block not found")


@router.post("/forest-blocks/{block_id}/restore")
def restore_forest_block(
    block_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.blocks.restore")
    if use_mysql() or use_postgis():
        block = (
            first_block_mysql(block_id=block_id, context=context, include_deleted=True)
            if use_mysql()
            else first_block_postgis(block_id=block_id, context=context, include_deleted=True)
        )
        if block is None:
            raise HTTPException(status_code=404, detail="Forest block not found")
        if not block.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Forest block is not deleted")
        block["deletedAt"] = None
        block["updatedAt"] = now_iso()
        save_block(block)
        record_block_version(block, "restore", context)
        return {"ok": True, "restored": block_id, "block": ForestBlockOut.model_validate(sanitize_block_for_ledger(block)).model_dump()}

    blocks = load_all_blocks()
    for block in blocks:
        if block.get("id") != block_id:
            continue
        if not block_allowed(context, block):
            raise HTTPException(status_code=404, detail="Forest block not found")
        if not block.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Forest block is not deleted")
        block["deletedAt"] = None
        block["updatedAt"] = now_iso()
        save_blocks(blocks)
        record_block_version(block, "restore", context)
        return {"ok": True, "restored": block_id, "block": ForestBlockOut.model_validate(sanitize_block_for_ledger(block)).model_dump()}
    raise HTTPException(status_code=404, detail="Forest block not found")


@router.get("/map/forest-blocks.geojson")
def forest_blocks_geojson(
    filters: ForestBlockFilters = Depends(filter_params),
    maxFeatures: int = Query(default=2000, ge=1, le=10000),
    zoom: float = Query(default=14, ge=0, le=24),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return forest_block_feature_collection(filters, context, max_features=maxFeatures, zoom=zoom)


@router.get("/map/forest-blocks/tiles/{z}/{x}/{y}.pbf")
def forest_blocks_vector_tile(
    z: int,
    x: int,
    y: int,
    filters: ForestBlockFilters = Depends(filter_params),
    maxFeatures: int = Query(default=5000, ge=1, le=10000),
    context: AuthContext = Depends(request_context),
) -> Response:
    content, cache_status = forest_block_vector_tile(
        z,
        x,
        y,
        filters,
        context,
        max_features=maxFeatures,
    )
    return Response(
        content=content,
        media_type="application/vnd.mapbox-vector-tile",
        headers={
            "Cache-Control": f"private, max-age={min(60, FOREST_VECTOR_TILE_CACHE_TTL_SECONDS)}",
            "X-Vector-Tile-Cache": cache_status,
        },
    )


@router.get("/map/forest-blocks/aggregates")
def forest_blocks_aggregates(
    level: Literal["county", "town", "village"] = Query(default="town"),
    filters: ForestBlockFilters = Depends(filter_params),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return forest_block_aggregates(level, filters, context)


@router.get("/map/forest-blocks/summary")
def forest_blocks_summary(
    filters: ForestBlockFilters = Depends(filter_params),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return forest_block_summary(filters, context)


@router.get("/map/forest-blocks/facets")
def forest_blocks_facets(
    filters: ForestBlockFilters = Depends(filter_params),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return forest_block_facets(filters, context)
