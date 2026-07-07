from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import AuthContext, area_allowed, request_context, require_write_access
from .database import forest_blocks_json_path, load_json_records, save_json_records, use_postgis
from .settings import get_settings


router = APIRouter(prefix="/api", tags=["forest-blocks"])

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
    ownershipStatus: str | None = None
    managementStatus: str | None = None
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


class ForestBlockIn(ForestBlockBase):
    pass


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
    ownershipStatus: str | None = None
    managementStatus: str | None = None
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


class ForestBlockOut(ForestBlockBase):
    id: str
    createdAt: str
    updatedAt: str
    deletedAt: str | None = None


class ForestBlockFilters(BaseModel):
    q: str = ""
    countyCode: str = ""
    townCode: str = ""
    baseType: str = ""
    operationType: str = ""
    qualityGrade: str = ""
    healthStatus: str = ""
    riskLevel: str = ""
    bbox: str = ""
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
        placeholders = ", ".join(["%s"] * len(context.areas))
        clauses.append(f"(county_code IS NULL OR county_code IN ({placeholders}))")
        params.extend(sorted(context.areas))

    if filters:
        exact_filters = {
            "countyCode": "county_code",
            "townCode": "town_code",
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
                "(block_code ILIKE %s OR name ILIKE %s OR county_name ILIKE %s OR town_name ILIKE %s OR village_name ILIKE %s)"
            )
            params.extend([pattern] * 5)

        bbox = parse_bbox(filters.bbox)
        if bbox:
            clauses.append("geometry && ST_MakeEnvelope(%s, %s, %s, %s, 4326)")
            params.extend(bbox)

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def fetch_blocks_postgis(
    *,
    filters: ForestBlockFilters | None = None,
    context: AuthContext | None = None,
    include_deleted: bool = False,
    limit: int | None = None,
    offset: int = 0,
    block_id: str | None = None,
    block_code: str | None = None,
) -> list[dict[str, Any]]:
    where_sql, params = postgis_where(
        filters=filters,
        context=context,
        include_deleted=include_deleted,
        block_id=block_id,
        block_code=block_code,
    )
    sql = f"{POSTGIS_SELECT_SQL}{where_sql} ORDER BY updated_at DESC, block_code"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_row(row) for row in cur.fetchall()]


def count_blocks_postgis(filters: ForestBlockFilters, context: AuthContext) -> int:
    where_sql, params = postgis_where(filters=filters, context=context)
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM forest_blocks{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


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


def upsert_block_postgis(block: dict[str, Any]) -> None:
    upsert_blocks_postgis([block])


def save_block(block: dict[str, Any]) -> None:
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
    if use_postgis():
        return first_block_postgis(block_code=block_code, include_deleted=include_deleted)

    for block in load_all_blocks():
        if block.get("blockCode") == block_code and (include_deleted or not block.get("deletedAt")):
            return block
    return None


def load_all_blocks() -> list[dict[str, Any]]:
    if use_postgis():
        return fetch_blocks_postgis(include_deleted=True)
    return load_json_records(forest_blocks_json_path())


def load_blocks() -> list[dict[str, Any]]:
    if use_postgis():
        return fetch_blocks_postgis()
    return [item for item in load_all_blocks() if not item.get("deletedAt")]


def save_blocks(blocks: list[dict[str, Any]]) -> None:
    if use_postgis():
        upsert_blocks_postgis(blocks)
        return
    save_json_records(forest_blocks_json_path(), blocks)


def context_has_scoped_areas(context: AuthContext) -> bool:
    return bool(context.areas) and "*" not in context.areas


def require_target_area_allowed(context: AuthContext, county_code: str | None) -> None:
    if context_has_scoped_areas(context) and not county_code:
        raise HTTPException(status_code=403, detail="Area access denied")
    if not area_allowed(context, county_code):
        raise HTTPException(status_code=403, detail="Area access denied")


def text_matches(block: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        str(block.get(key) or "")
        for key in ("blockCode", "name", "countyName", "townName", "villageName")
    ).lower()
    return query.lower() in haystack


def block_matches_filters(
    block: dict[str, Any], filters: ForestBlockFilters, context: AuthContext
) -> bool:
    if not area_allowed(context, block.get("countyCode")):
        return False
    if filters.countyCode and block.get("countyCode") != filters.countyCode:
        return False
    if filters.townCode and block.get("townCode") != filters.townCode:
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
    if use_postgis():
        items = fetch_blocks_postgis(
            filters=filters,
            context=context,
            limit=filters.limit,
            offset=filters.offset,
        )
        return {
            "items": items,
            "total": count_blocks_postgis(filters, context),
            "limit": filters.limit,
            "offset": filters.offset,
        }

    blocks = [block for block in load_blocks() if block_matches_filters(block, filters, context)]
    items = blocks[filters.offset : filters.offset + filters.limit]
    return {
        "items": items,
        "total": len(blocks),
        "limit": filters.limit,
        "offset": filters.offset,
    }


def forest_block_feature_collection(filters: ForestBlockFilters, context: AuthContext) -> dict[str, Any]:
    if use_postgis():
        blocks = fetch_blocks_postgis(filters=filters, context=context)
    else:
        blocks = [block for block in load_blocks() if block_matches_filters(block, filters, context)]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": block["id"],
                "geometry": block.get("geometry"),
                "properties": {key: value for key, value in block.items() if key != "geometry"},
            }
            for block in blocks
        ],
    }


def forest_block_summary(filters: ForestBlockFilters, context: AuthContext) -> dict[str, Any]:
    if use_postgis():
        blocks = fetch_blocks_postgis(filters=filters, context=context)
    else:
        blocks = [block for block in load_blocks() if block_matches_filters(block, filters, context)]
    summary: dict[str, Any] = {
        "total": len(blocks),
        "riskLevel": {},
        "qualityGrade": {},
        "baseType": {},
    }
    for block in blocks:
        for key in ("riskLevel", "qualityGrade", "baseType"):
            value = block.get(key) or "unknown"
            summary[key][value] = summary[key].get(value, 0) + 1
    return summary


def filter_params(
    q: str = Query(default=""),
    countyCode: str = Query(default=""),
    townCode: str = Query(default=""),
    baseType: str = Query(default=""),
    operationType: str = Query(default=""),
    qualityGrade: str = Query(default=""),
    healthStatus: str = Query(default=""),
    riskLevel: str = Query(default=""),
    bbox: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> ForestBlockFilters:
    return ForestBlockFilters(
        q=q,
        countyCode=countyCode,
        townCode=townCode,
        baseType=baseType,
        operationType=operationType,
        qualityGrade=qualityGrade,
        healthStatus=healthStatus,
        riskLevel=riskLevel,
        bbox=bbox,
        limit=limit,
        offset=offset,
    )


def find_block(block_id: str, context: AuthContext) -> dict[str, Any]:
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


@router.get("/forest-blocks")
def list_forest_blocks_route(
    filters: ForestBlockFilters = Depends(filter_params),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return list_forest_blocks(filters, context)


@router.post("/forest-blocks")
def create_forest_block(
    payload: ForestBlockIn,
    context: AuthContext = Depends(request_context),
) -> ForestBlockOut:
    require_write_access(context)
    require_target_area_allowed(context, payload.countyCode)
    if use_postgis():
        if block_by_code(payload.blockCode, include_deleted=True):
            raise HTTPException(status_code=409, detail="blockCode already exists")
        block = normalize_block(payload.model_dump())
        save_block(block)
        return ForestBlockOut.model_validate(block)

    blocks = load_all_blocks()
    if any(item.get("blockCode") == payload.blockCode for item in blocks):
        raise HTTPException(status_code=409, detail="blockCode already exists")
    block = normalize_block(payload.model_dump())
    blocks.append(block)
    save_blocks(blocks)
    return ForestBlockOut.model_validate(block)


@router.get("/forest-blocks/{block_id}")
def get_forest_block(
    block_id: str,
    context: AuthContext = Depends(request_context),
) -> ForestBlockOut:
    return ForestBlockOut.model_validate(find_block(block_id, context))


@router.patch("/forest-blocks/{block_id}")
def patch_forest_block(
    block_id: str,
    payload: ForestBlockPatch,
    context: AuthContext = Depends(request_context),
) -> ForestBlockOut:
    require_write_access(context)
    if use_postgis():
        block = find_block(block_id, context)
        changes = payload.model_dump(exclude_unset=True)
        updated = normalize_block(
            {
                **block,
                **changes,
                "id": block_id,
                "createdAt": block.get("createdAt", now_iso()),
                "deletedAt": block.get("deletedAt"),
            }
        )
        require_target_area_allowed(context, updated.get("countyCode"))
        save_block(updated)
        return ForestBlockOut.model_validate(updated)

    blocks = load_all_blocks()
    for index, block in enumerate(blocks):
        if block.get("id") != block_id:
            continue
        if block.get("deletedAt"):
            raise HTTPException(status_code=404, detail="Forest block not found")
        if not area_allowed(context, block.get("countyCode")):
            raise HTTPException(status_code=404, detail="Forest block not found")
        changes = payload.model_dump(exclude_unset=True)
        updated = normalize_block(
            {
                **block,
                **changes,
                "id": block_id,
                "createdAt": block.get("createdAt", now_iso()),
                "deletedAt": block.get("deletedAt"),
            }
        )
        require_target_area_allowed(context, updated.get("countyCode"))
        blocks[index] = updated
        save_blocks(blocks)
        return ForestBlockOut.model_validate(updated)
    raise HTTPException(status_code=404, detail="Forest block not found")


@router.delete("/forest-blocks/{block_id}")
def delete_forest_block(
    block_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_write_access(context)
    if use_postgis():
        block = find_block(block_id, context)
        block["deletedAt"] = now_iso()
        block["updatedAt"] = block["deletedAt"]
        save_block(block)
        return {"ok": True, "deleted": block_id}

    blocks = load_all_blocks()
    for block in blocks:
        if block.get("id") != block_id:
            continue
        if block.get("deletedAt"):
            raise HTTPException(status_code=404, detail="Forest block not found")
        if not area_allowed(context, block.get("countyCode")):
            raise HTTPException(status_code=404, detail="Forest block not found")
        block["deletedAt"] = now_iso()
        block["updatedAt"] = block["deletedAt"]
        save_blocks(blocks)
        return {"ok": True, "deleted": block_id}
    raise HTTPException(status_code=404, detail="Forest block not found")


@router.get("/map/forest-blocks.geojson")
def forest_blocks_geojson(
    filters: ForestBlockFilters = Depends(filter_params),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return forest_block_feature_collection(filters, context)


@router.get("/map/forest-blocks/summary")
def forest_blocks_summary(
    filters: ForestBlockFilters = Depends(filter_params),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return forest_block_summary(filters, context)
