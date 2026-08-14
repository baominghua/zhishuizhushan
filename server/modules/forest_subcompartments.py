from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from shapely.geometry import shape
from shapely.validation import explain_validity

from .admin_roles import require_permission
from .auth import AuthContext, effective_areas, effective_data_scope_values, has_effective_data_scope
from .database import (
    forest_subcompartment_versions_json_path,
    forest_subcompartments_json_path,
    json_transaction,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
    use_postgis,
)
from .forest_blocks import (
    FOREST_BLOCK_FINE_SCOPE_FIELDS,
    block_allowed,
    context_has_scoped_areas,
    datetime_to_iso,
    decimal_to_float,
    find_block,
    find_block_any_state,
    iter_geometry_points,
    json_value,
    mysql_datetime,
    normalize_geometry_for_storage,
    now_iso,
    postgis_connect,
    serializable_json,
)


class ForestSubcompartmentBase(BaseModel):
    subcompartmentCode: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    forestBlockId: str = Field(min_length=1)
    areaMu: float | None = Field(default=None, ge=0)
    landCategory: str | None = None
    forestCategory: str | None = None
    origin: str | None = None
    ageGroup: str | None = None
    bambooSpecies: str | None = None
    slopeDegree: float | None = Field(default=None, ge=0, le=90)
    aspect: str | None = None
    elevationM: float | None = None
    qualityGrade: str | None = None
    healthStatus: str | None = None
    riskLevel: str | None = None
    managementStatus: str | None = None
    tags: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any] | None = None
    sourceBatchId: str | None = None

    @field_validator("geometry")
    @classmethod
    def validate_geometry(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        normalized = normalize_geometry_for_storage(value)
        if normalized is None:
            raise ValueError("geometry must be a Polygon or MultiPolygon")
        if not iter_geometry_points(normalized):
            raise ValueError("geometry must contain coordinates")
        return normalized


class ForestSubcompartmentIn(ForestSubcompartmentBase):
    model_config = {"extra": "forbid"}


class ForestSubcompartmentPatch(BaseModel):
    expectedVersion: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    forestBlockId: str | None = Field(default=None, min_length=1)
    areaMu: float | None = Field(default=None, ge=0)
    landCategory: str | None = None
    forestCategory: str | None = None
    origin: str | None = None
    ageGroup: str | None = None
    bambooSpecies: str | None = None
    slopeDegree: float | None = Field(default=None, ge=0, le=90)
    aspect: str | None = None
    elevationM: float | None = None
    qualityGrade: str | None = None
    healthStatus: str | None = None
    riskLevel: str | None = None
    managementStatus: str | None = None
    tags: list[str] | None = None
    properties: dict[str, Any] | None = None
    geometry: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}

    @field_validator("geometry")
    @classmethod
    def validate_geometry(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return ForestSubcompartmentBase.validate_geometry(value)


class ForestSubcompartmentRollbackRequest(BaseModel):
    versionId: str = Field(min_length=1)
    expectedVersion: int = Field(ge=1)

    model_config = {"extra": "forbid"}


class ForestSubcompartmentOut(ForestSubcompartmentBase):
    id: str
    forestBlockCode: str
    forestBlockName: str
    countyCode: str | None = None
    countyName: str | None = None
    townCode: str | None = None
    townName: str | None = None
    villageCode: str | None = None
    villageName: str | None = None
    version: int
    createdBy: str | None = None
    createdAt: str
    updatedAt: str
    deletedAt: str | None = None


class ForestSubcompartmentFilters(BaseModel):
    q: str = ""
    forestBlockId: str = ""
    countyCode: str = ""
    townCode: str = ""
    villageCode: str = ""
    managementStatus: str = ""
    riskLevel: str = ""
    includeDeleted: bool = False
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


SUBCOMPARTMENT_DB_FIELDS = (
    ("id", "id"),
    ("subcompartment_code", "subcompartmentCode"),
    ("name", "name"),
    ("forest_block_id", "forestBlockId"),
    ("area_mu", "areaMu"),
    ("land_category", "landCategory"),
    ("forest_category", "forestCategory"),
    ("origin", "origin"),
    ("age_group", "ageGroup"),
    ("bamboo_species", "bambooSpecies"),
    ("slope_degree", "slopeDegree"),
    ("aspect", "aspect"),
    ("elevation_m", "elevationM"),
    ("quality_grade", "qualityGrade"),
    ("health_status", "healthStatus"),
    ("risk_level", "riskLevel"),
    ("management_status", "managementStatus"),
    ("tags", "tags"),
    ("properties", "properties"),
    ("source_batch_id", "sourceBatchId"),
    ("version", "version"),
    ("created_by", "createdBy"),
    ("created_at", "createdAt"),
    ("updated_at", "updatedAt"),
    ("deleted_at", "deletedAt"),
)
SUBCOMPARTMENT_COLUMNS = [item[0] for item in SUBCOMPARTMENT_DB_FIELDS]
PARENT_FIELDS = (
    ("block_code", "forestBlockCode"),
    ("block_name", "forestBlockName"),
    ("county_code", "countyCode"),
    ("county_name", "countyName"),
    ("town_code", "townCode"),
    ("town_name", "townName"),
    ("village_code", "villageCode"),
    ("village_name", "villageName"),
)


def normalize_record(payload: dict[str, Any], context: AuthContext, *, version: int = 1) -> dict[str, Any]:
    timestamp = now_iso()
    record = dict(payload)
    record.setdefault("id", str(uuid.uuid4()))
    record.setdefault("createdAt", timestamp)
    record.setdefault("createdBy", context.user)
    record["updatedAt"] = timestamp
    record.setdefault("deletedAt", None)
    record.setdefault("tags", [])
    record.setdefault("properties", {})
    record["version"] = version
    record["geometry"] = normalize_geometry_for_storage(record.get("geometry"))
    return record


def hydrate_parent(record: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    return {
        **record,
        "forestBlockCode": str(parent.get("blockCode") or ""),
        "forestBlockName": str(parent.get("name") or ""),
        "countyCode": parent.get("countyCode"),
        "countyName": parent.get("countyName"),
        "townCode": parent.get("townCode"),
        "townName": parent.get("townName"),
        "villageCode": parent.get("villageCode"),
        "villageName": parent.get("villageName"),
    }


def parent_for_write(forest_block_id: str, context: AuthContext) -> dict[str, Any]:
    parent = find_block(forest_block_id, context)
    if not block_allowed(context, parent):
        raise HTTPException(status_code=403, detail="Forest block access denied")
    return parent


def validate_spatial_relationship(
    geometry: dict[str, Any] | None,
    parent: dict[str, Any],
) -> None:
    if geometry is None:
        return
    parent_geometry = normalize_geometry_for_storage(parent.get("geometry"))
    if parent_geometry is None:
        raise HTTPException(
            status_code=422,
            detail="请先补充父林班空间边界，再绘制或导入小班边界",
        )
    child_shape = shape(geometry)
    parent_shape = shape(parent_geometry)
    if child_shape.is_empty or not child_shape.is_valid:
        raise HTTPException(
            status_code=422,
            detail=f"小班边界无效：{explain_validity(child_shape)}",
        )
    if parent_shape.is_empty or not parent_shape.is_valid:
        raise HTTPException(status_code=422, detail="父林班空间边界无效，请先修复林班边界")
    if not parent_shape.covers(child_shape):
        raise HTTPException(status_code=422, detail="小班边界必须完整落在所属林班边界内")


def normalize_sql_row(row: Any, *, mysql: bool) -> dict[str, Any]:
    names = [item[0] for item in SUBCOMPARTMENT_DB_FIELDS]
    names.extend(["geometry", *(item[0] for item in PARENT_FIELDS)])
    source = dict(zip(names, row))
    result: dict[str, Any] = {}
    for db_field, api_field in SUBCOMPARTMENT_DB_FIELDS:
        value = source.get(db_field)
        if db_field == "tags":
            value = json_value(value, [])
        elif db_field == "properties":
            value = json_value(value, {})
        elif db_field in {"created_at", "updated_at", "deleted_at"}:
            value = datetime_to_iso(value)
        else:
            value = decimal_to_float(value)
        result[api_field] = value
    result["geometry"] = json_value(source.get("geometry"), None)
    for db_field, api_field in PARENT_FIELDS:
        result[api_field] = source.get(db_field)
    result["version"] = int(result.get("version") or 1)
    return result


def sql_where(
    filters: ForestSubcompartmentFilters,
    context: AuthContext,
    *,
    record_id: str = "",
    record_code: str = "",
    mysql: bool,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not filters.includeDeleted:
        clauses.append("s.deleted_at IS NULL")
    if record_id:
        clauses.append("s.id = %s")
        params.append(record_id)
    if record_code:
        clauses.append("s.subcompartment_code = %s")
        params.append(record_code)
    if filters.forestBlockId:
        clauses.append("s.forest_block_id = %s")
        params.append(filters.forestBlockId)
    for value, field in (
        (filters.countyCode, "county_code"),
        (filters.townCode, "town_code"),
        (filters.villageCode, "village_code"),
        (filters.managementStatus, "management_status"),
        (filters.riskLevel, "risk_level"),
    ):
        if value:
            alias = "b" if field.endswith("_code") and field in {"county_code", "town_code", "village_code"} else "s"
            clauses.append(f"{alias}.{field} = %s")
            params.append(value)
    if context_has_scoped_areas(context):
        areas = sorted(effective_areas(context))
        if not areas:
            clauses.append("FALSE")
        elif "*" not in areas:
            placeholders = ", ".join(["%s"] * len(areas))
            clauses.append(f"(b.county_code IS NULL OR b.county_code IN ({placeholders}))")
            params.extend(areas)
    for scope_key, _api_field, db_field in FOREST_BLOCK_FINE_SCOPE_FIELDS:
        if not has_effective_data_scope(context, scope_key):
            continue
        values = sorted(effective_data_scope_values(context, scope_key))
        if not values:
            clauses.append("FALSE")
        elif "*" not in values:
            placeholders = ", ".join(["%s"] * len(values))
            clauses.append(f"b.{db_field} IN ({placeholders})")
            params.extend(values)
    if filters.q:
        pattern = f"%{filters.q}%"
        operator = "LIKE" if mysql else "ILIKE"
        properties = "CAST(s.properties AS CHAR)" if mysql else "s.properties::text"
        clauses.append(
            f"(s.subcompartment_code {operator} %s OR s.name {operator} %s OR "
            f"s.bamboo_species {operator} %s OR b.block_code {operator} %s OR "
            f"b.name {operator} %s OR {properties} {operator} %s)"
        )
        params.extend([pattern] * 6)
    return (" WHERE " + " AND ".join(clauses), params) if clauses else ("", params)


def sql_select(mysql: bool) -> str:
    record_columns = ", ".join(f"s.{column}" for column in SUBCOMPARTMENT_COLUMNS)
    geometry = "ST_AsGeoJSON(g.geometry)" if mysql else "ST_AsGeoJSON(s.geometry)"
    geometry_join = (
        "LEFT JOIN forest_subcompartment_geometries g ON g.forest_subcompartment_id = s.id"
        if mysql else ""
    )
    id_column = "s.id" if mysql else "s.id::text"
    record_columns = record_columns.replace("s.id", id_column, 1)
    return (
        f"SELECT {record_columns}, {geometry}, b.block_code, b.name, b.county_code, "
        "b.county_name, b.town_code, b.town_name, b.village_code, b.village_name "
        "FROM forest_subcompartments s "
        f"{geometry_join} JOIN forest_blocks b ON b.id = s.forest_block_id"
    )


def fetch_sql(
    filters: ForestSubcompartmentFilters,
    context: AuthContext,
    *,
    record_id: str = "",
    record_code: str = "",
) -> tuple[list[dict[str, Any]], int]:
    mysql = use_mysql()
    where, params = sql_where(filters, context, record_id=record_id, record_code=record_code, mysql=mysql)
    count_sql = (
        "SELECT COUNT(*) FROM forest_subcompartments s "
        "JOIN forest_blocks b ON b.id = s.forest_block_id" + where
    )
    select_sql = sql_select(mysql) + where + " ORDER BY s.updated_at DESC LIMIT %s OFFSET %s"
    connection = mysql_connect() if mysql else postgis_connect()
    with connection as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, tuple(params))
            total = int((cur.fetchone() or [0])[0])
            cur.execute(select_sql, tuple([*params, filters.limit, filters.offset]))
            rows = cur.fetchall()
    return [normalize_sql_row(row, mysql=mysql) for row in rows], total


def json_visible_records(filters: ForestSubcompartmentFilters, context: AuthContext) -> list[dict[str, Any]]:
    visible: list[dict[str, Any]] = []
    query = filters.q.lower()
    for record in load_json_records(forest_subcompartments_json_path()):
        if record.get("deletedAt") and not filters.includeDeleted:
            continue
        if filters.forestBlockId and record.get("forestBlockId") != filters.forestBlockId:
            continue
        if filters.managementStatus and record.get("managementStatus") != filters.managementStatus:
            continue
        if filters.riskLevel and record.get("riskLevel") != filters.riskLevel:
            continue
        try:
            parent = find_block_any_state(str(record.get("forestBlockId") or ""), context)
        except HTTPException:
            continue
        if not block_allowed(context, parent):
            continue
        hydrated = hydrate_parent(record, parent)
        if filters.countyCode and hydrated.get("countyCode") != filters.countyCode:
            continue
        if filters.townCode and hydrated.get("townCode") != filters.townCode:
            continue
        if filters.villageCode and hydrated.get("villageCode") != filters.villageCode:
            continue
        if query:
            haystack = " ".join(
                str(hydrated.get(key) or "")
                for key in ("subcompartmentCode", "name", "bambooSpecies", "forestBlockCode", "forestBlockName")
            ).lower()
            if query not in haystack and query not in json.dumps(record.get("properties") or {}, ensure_ascii=False).lower():
                continue
        visible.append(hydrated)
    return sorted(visible, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)


def spatial_children_for_parent(forest_block_id: str, context: AuthContext) -> list[dict[str, Any]]:
    """Return active child boundaries without imposing an extra UI permission check."""
    filters = ForestSubcompartmentFilters(forestBlockId=forest_block_id, limit=200)
    if not (use_mysql() or use_postgis()):
        return [item for item in json_visible_records(filters, context) if item.get("geometry")]
    children: list[dict[str, Any]] = []
    offset = 0
    while True:
        page_filters = filters.model_copy(update={"offset": offset})
        items, total = fetch_sql(page_filters, context)
        children.extend(item for item in items if item.get("geometry"))
        offset += len(items)
        if not items or offset >= total:
            return children


def list_forest_subcompartments(
    filters: ForestSubcompartmentFilters,
    context: AuthContext,
) -> dict[str, Any]:
    require_permission(context, "forest.subcompartments.view")
    if filters.includeDeleted:
        require_permission(context, "forest.subcompartments.manage")
    if use_mysql() or use_postgis():
        items, total = fetch_sql(filters, context)
    else:
        records = json_visible_records(filters, context)
        total = len(records)
        items = records[filters.offset : filters.offset + filters.limit]
    return {"items": items, "total": total, "limit": filters.limit, "offset": filters.offset}


def get_forest_subcompartment(record_id: str, context: AuthContext) -> ForestSubcompartmentOut:
    require_permission(context, "forest.subcompartments.view")
    filters = ForestSubcompartmentFilters(limit=1)
    if use_mysql() or use_postgis():
        items, _ = fetch_sql(filters, context, record_id=record_id)
    else:
        items = [item for item in json_visible_records(filters, context) if item.get("id") == record_id]
    if not items:
        raise HTTPException(status_code=404, detail="Forest subcompartment not found")
    return ForestSubcompartmentOut.model_validate(items[0])


def code_exists(code: str) -> bool:
    if use_mysql() or use_postgis():
        connection = mysql_connect() if use_mysql() else postgis_connect()
        with connection as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM forest_subcompartments WHERE subcompartment_code = %s LIMIT 1",
                    (code,),
                )
                return cur.fetchone() is not None
    return any(item.get("subcompartmentCode") == code for item in load_json_records(forest_subcompartments_json_path()))


def record_values(record: dict[str, Any]) -> tuple[Any, ...]:
    values: dict[str, Any] = {db: record.get(api) for db, api in SUBCOMPARTMENT_DB_FIELDS}
    values["tags"] = serializable_json(record.get("tags"), [])
    values["properties"] = serializable_json(record.get("properties"), {})
    values["created_at"] = mysql_datetime(record.get("createdAt"))
    values["updated_at"] = mysql_datetime(record.get("updatedAt"))
    values["deleted_at"] = mysql_datetime(record.get("deletedAt"))
    return tuple(values.get(column) for column in SUBCOMPARTMENT_COLUMNS)


def geometry_values(record: dict[str, Any]) -> tuple[Any, ...] | None:
    geometry = normalize_geometry_for_storage(record.get("geometry"))
    points = iter_geometry_points(geometry)
    if not geometry or not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (
        record["id"],
        json.dumps(geometry, ensure_ascii=False),
        f"POINT({(min(xs) + max(xs)) / 2:.15g} {(min(ys) + max(ys)) / 2:.15g})",
        min(xs), min(ys), max(xs), max(ys), len(points), mysql_datetime(record["updatedAt"]),
    )


def version_record(record: dict[str, Any], change_type: str, context: AuthContext) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "forestSubcompartmentId": record["id"],
        "changeType": change_type,
        "version": int(record["version"]),
        "snapshot": json.loads(json.dumps(record, ensure_ascii=False, default=str)),
        "createdBy": context.user,
        "createdAt": now_iso(),
    }


def normalize_version_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
        values = (
            source.get("id"),
            source.get("forest_subcompartment_id"),
            source.get("change_type"),
            source.get("version"),
            source.get("snapshot"),
            source.get("created_by"),
            source.get("created_at"),
        )
    else:
        values = row
    version_id, record_id, change_type, version, snapshot, created_by, created_at = values
    return {
        "id": str(version_id or ""),
        "forestSubcompartmentId": str(record_id or ""),
        "changeType": str(change_type or ""),
        "version": int(version or 1),
        "snapshot": json_value(snapshot, {}) if isinstance(snapshot, str) else (snapshot or {}),
        "createdBy": str(created_by or ""),
        "createdAt": datetime_to_iso(created_at) or "",
    }


def load_versions(record_id: str) -> list[dict[str, Any]]:
    if use_mysql() or use_postgis():
        connection = mysql_connect() if use_mysql() else postgis_connect()
        with connection as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, forest_subcompartment_id, change_type, version, snapshot, "
                    "created_by, created_at FROM forest_subcompartment_versions "
                    "WHERE forest_subcompartment_id = %s ORDER BY version DESC, created_at DESC",
                    (record_id,),
                )
                return [normalize_version_row(row) for row in cur.fetchall()]
    records = [
        item
        for item in load_json_records(forest_subcompartment_versions_json_path())
        if str(item.get("forestSubcompartmentId") or "") == record_id
    ]
    return sorted(
        records,
        key=lambda item: (int(item.get("version") or 1), str(item.get("createdAt") or "")),
        reverse=True,
    )


def save_sql(record: dict[str, Any], change_type: str, context: AuthContext) -> None:
    version = version_record(record, change_type, context)
    if use_mysql():
        columns = ", ".join(SUBCOMPARTMENT_COLUMNS)
        placeholders = ", ".join(["%s"] * len(SUBCOMPARTMENT_COLUMNS))
        updates = ", ".join(f"{column}=VALUES({column})" for column in SUBCOMPARTMENT_COLUMNS if column not in {"id", "subcompartment_code"})
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"INSERT INTO forest_subcompartments ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}", record_values(record))
                values = geometry_values(record)
                if values:
                    cur.execute(
                        """
                        INSERT INTO forest_subcompartment_geometries (
                            forest_subcompartment_id, geometry, centroid,
                            min_longitude, min_latitude, max_longitude, max_latitude,
                            vertex_count, updated_at
                        ) VALUES (%s, ST_GeomFromGeoJSON(%s, 1, 4326),
                            ST_GeomFromText(%s, 4326, 'axis-order=long-lat'), %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE geometry=VALUES(geometry), centroid=VALUES(centroid),
                            min_longitude=VALUES(min_longitude), min_latitude=VALUES(min_latitude),
                            max_longitude=VALUES(max_longitude), max_latitude=VALUES(max_latitude),
                            vertex_count=VALUES(vertex_count), updated_at=VALUES(updated_at)
                        """,
                        values,
                    )
                else:
                    cur.execute("DELETE FROM forest_subcompartment_geometries WHERE forest_subcompartment_id = %s", (record["id"],))
                cur.execute(
                    "INSERT INTO forest_subcompartment_versions (id, forest_subcompartment_id, change_type, version, snapshot, created_by, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (version["id"], version["forestSubcompartmentId"], change_type, version["version"], serializable_json(version["snapshot"], {}), context.user, mysql_datetime(version["createdAt"])),
                )
            conn.commit()
        return
    geometry = normalize_geometry_for_storage(record.get("geometry"))
    columns = ", ".join(SUBCOMPARTMENT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(SUBCOMPARTMENT_COLUMNS))
    updates = ", ".join(f"{column}=EXCLUDED.{column}" for column in SUBCOMPARTMENT_COLUMNS if column not in {"id", "subcompartment_code"})
    pg_values = list(record_values(record))
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"INSERT INTO forest_subcompartments ({columns}) VALUES ({placeholders}) ON CONFLICT (id) DO UPDATE SET {updates}", tuple(pg_values))
            cur.execute(
                "UPDATE forest_subcompartments SET geometry = CASE WHEN %s IS NULL THEN NULL ELSE ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) END, centroid = CASE WHEN %s IS NULL THEN NULL ELSE ST_Centroid(ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))) END WHERE id = %s",
                (json.dumps(geometry) if geometry else None, json.dumps(geometry) if geometry else None, json.dumps(geometry) if geometry else None, json.dumps(geometry) if geometry else None, record["id"]),
            )
            cur.execute(
                "INSERT INTO forest_subcompartment_versions (id, forest_subcompartment_id, change_type, version, snapshot, created_by, created_at) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)",
                (version["id"], version["forestSubcompartmentId"], change_type, version["version"], serializable_json(version["snapshot"], {}), context.user, version["createdAt"]),
            )
        conn.commit()


def save_json(record: dict[str, Any], change_type: str, context: AuthContext) -> None:
    records_path = forest_subcompartments_json_path()
    versions_path = forest_subcompartment_versions_json_path()
    with json_transaction([records_path, versions_path]):
        records = load_json_records(records_path)
        match = next((index for index, item in enumerate(records) if item.get("id") == record["id"]), None)
        if match is None:
            records.append(record)
        else:
            records[match] = record
        versions = load_json_records(versions_path)
        versions.append(version_record(record, change_type, context))
        save_json_records(records_path, records)
        save_json_records(versions_path, versions)


def save_record(record: dict[str, Any], change_type: str, context: AuthContext) -> None:
    if use_mysql() or use_postgis():
        save_sql(record, change_type, context)
    else:
        save_json(record, change_type, context)


def create_forest_subcompartment(payload: ForestSubcompartmentIn, context: AuthContext) -> ForestSubcompartmentOut:
    require_permission(context, "forest.subcompartments.create")
    if code_exists(payload.subcompartmentCode):
        raise HTTPException(status_code=409, detail="subcompartmentCode already exists")
    parent = parent_for_write(payload.forestBlockId, context)
    validate_spatial_relationship(payload.geometry, parent)
    record = normalize_record(payload.model_dump(), context)
    save_record(record, "create", context)
    return ForestSubcompartmentOut.model_validate(hydrate_parent(record, parent))


def patch_forest_subcompartment(
    record_id: str,
    payload: ForestSubcompartmentPatch,
    context: AuthContext,
) -> ForestSubcompartmentOut:
    require_permission(context, "forest.subcompartments.update")
    current = get_forest_subcompartment(record_id, context).model_dump()
    if int(current["version"]) != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="Forest subcompartment was updated by another user")
    changes = payload.model_dump(exclude_unset=True, exclude={"expectedVersion"})
    parent_id = str(changes.get("forestBlockId") or current["forestBlockId"])
    parent = parent_for_write(parent_id, context)
    validate_spatial_relationship(changes.get("geometry", current.get("geometry")), parent)
    updated = normalize_record(
        {**current, **changes, "id": record_id, "subcompartmentCode": current["subcompartmentCode"], "forestBlockId": parent_id, "createdAt": current["createdAt"], "createdBy": current.get("createdBy"), "deletedAt": current.get("deletedAt")},
        context,
        version=int(current["version"]) + 1,
    )
    for key in ("forestBlockCode", "forestBlockName", "countyCode", "countyName", "townCode", "townName", "villageCode", "villageName"):
        updated.pop(key, None)
    save_record(updated, "update", context)
    return ForestSubcompartmentOut.model_validate(hydrate_parent(updated, parent))


def list_forest_subcompartment_versions(record_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.subcompartments.view")
    get_forest_subcompartment(record_id, context)
    versions = load_versions(record_id)
    return {"items": versions, "total": len(versions), "limit": len(versions), "offset": 0}


def rollback_forest_subcompartment(
    record_id: str,
    payload: ForestSubcompartmentRollbackRequest,
    context: AuthContext,
) -> dict[str, Any]:
    require_permission(context, "forest.subcompartments.rollback")
    current = get_forest_subcompartment(record_id, context).model_dump()
    if int(current["version"]) != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="Forest subcompartment was updated by another user")
    version = next((item for item in load_versions(record_id) if item["id"] == payload.versionId), None)
    if version is None:
        raise HTTPException(status_code=404, detail="Forest subcompartment version not found")
    snapshot = version.get("snapshot")
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=409, detail="Forest subcompartment version has no snapshot")
    parent_id = str(snapshot.get("forestBlockId") or current["forestBlockId"])
    parent = parent_for_write(parent_id, context)
    geometry = normalize_geometry_for_storage(snapshot.get("geometry"))
    validate_spatial_relationship(geometry, parent)
    rolled_back = normalize_record(
        {
            **snapshot,
            "id": record_id,
            "subcompartmentCode": current["subcompartmentCode"],
            "forestBlockId": parent_id,
            "createdAt": current["createdAt"],
            "createdBy": current.get("createdBy"),
            "deletedAt": None,
            "geometry": geometry,
        },
        context,
        version=int(current["version"]) + 1,
    )
    for key in ("forestBlockCode", "forestBlockName", "countyCode", "countyName", "townCode", "townName", "villageCode", "villageName"):
        rolled_back.pop(key, None)
    save_record(rolled_back, "rollback", context)
    hydrated = ForestSubcompartmentOut.model_validate(hydrate_parent(rolled_back, parent))
    return {
        "ok": True,
        "rolledBack": record_id,
        "sourceVersionId": payload.versionId,
        "record": hydrated.model_dump(),
    }


def delete_forest_subcompartment(record_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.subcompartments.delete")
    current = get_forest_subcompartment(record_id, context).model_dump()
    parent = parent_for_write(current["forestBlockId"], context)
    deleted = normalize_record(
        {**current, "id": record_id, "subcompartmentCode": current["subcompartmentCode"], "createdAt": current["createdAt"], "createdBy": current.get("createdBy"), "deletedAt": now_iso()},
        context,
        version=int(current["version"]) + 1,
    )
    deleted["deletedAt"] = deleted["updatedAt"]
    for key in ("forestBlockCode", "forestBlockName", "countyCode", "countyName", "townCode", "townName", "villageCode", "villageName"):
        deleted.pop(key, None)
    save_record(deleted, "delete", context)
    return {"ok": True, "deleted": record_id, "version": deleted["version"], "forestBlockCode": parent.get("blockCode")}
