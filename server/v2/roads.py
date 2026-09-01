from __future__ import annotations

import csv
import io
import math
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from shapely.geometry import shape

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.extension_store import (
    extension_record_by_id,
    list_extension_records,
    save_extension_record,
    soft_delete_extension_record,
    utc_now,
)
from server.modules.forest_blocks import block_by_code, require_target_block_allowed


router = APIRouter(prefix="/roads", tags=["v2-roads"])
ROAD_COLLECTION = "forest-roads"
MAINTENANCE_COLLECTION = "forest-road-maintenance"


def validate_line_geometry(value: dict[str, Any]) -> dict[str, Any]:
    try:
        geometry = shape(value)
    except Exception as error:
        raise ValueError("道路空间线不是有效 GeoJSON") from error
    if geometry.geom_type not in {"LineString", "MultiLineString"} or geometry.is_empty or not geometry.is_valid:
        raise ValueError("道路空间线必须是有效的 LineString 或 MultiLineString")
    return value


def line_length_km(geometry: dict[str, Any]) -> float:
    shaped = shape(geometry)
    lines = [shaped] if shaped.geom_type == "LineString" else list(shaped.geoms)
    total = 0.0
    for line in lines:
        coordinates = list(line.coords)
        for left, right in zip(coordinates, coordinates[1:]):
            lon1, lat1, lon2, lat2 = map(math.radians, (left[0], left[1], right[0], right[1]))
            delta_lon, delta_lat = lon2 - lon1, lat2 - lat1
            value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
            total += 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(value)))
    return round(total, 3)


class RoadPayload(BaseModel):
    roadCode: str = Field(min_length=1, max_length=96)
    name: str = Field(min_length=1, max_length=255)
    roadClass: Literal["main", "branch", "operation", "firebreak", "footpath", "other"] = "operation"
    surfaceType: Literal["paved", "gravel", "earth", "boardwalk", "other"] = "earth"
    condition: Literal["good", "fair", "poor", "closed"] = "fair"
    widthM: float | None = Field(default=None, ge=0, le=100)
    lengthKm: float | None = Field(default=None, ge=0)
    linkedBlockCodes: list[str] = Field(min_length=1)
    responsibleUnit: str = Field(default="", max_length=255)
    lastInspectedOn: str = Field(default="", max_length=32)
    notes: str = Field(default="", max_length=2000)
    geometry: dict[str, Any]

    @field_validator("geometry")
    @classmethod
    def geometry_is_line(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_line_geometry(value)

    @field_validator("linkedBlockCodes")
    @classmethod
    def unique_blocks(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(code.strip() for code in value if code.strip()))
        if not normalized:
            raise ValueError("林区道路至少关联一个正式林班")
        return normalized


class RoadPatch(BaseModel):
    expectedVersion: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    roadClass: Literal["main", "branch", "operation", "firebreak", "footpath", "other"] | None = None
    surfaceType: Literal["paved", "gravel", "earth", "boardwalk", "other"] | None = None
    condition: Literal["good", "fair", "poor", "closed"] | None = None
    widthM: float | None = Field(default=None, ge=0, le=100)
    lengthKm: float | None = Field(default=None, ge=0)
    linkedBlockCodes: list[str] | None = None
    responsibleUnit: str | None = Field(default=None, max_length=255)
    lastInspectedOn: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=2000)
    geometry: dict[str, Any] | None = None

    @field_validator("linkedBlockCodes")
    @classmethod
    def unique_blocks(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = list(dict.fromkeys(code.strip() for code in value if code.strip()))
        if not normalized:
            raise ValueError("林区道路至少关联一个正式林班")
        return normalized

    @field_validator("geometry")
    @classmethod
    def geometry_is_line(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_line_geometry(value) if value is not None else None


class MaintenancePayload(BaseModel):
    maintenanceType: Literal["inspection", "repair", "clearing", "drainage", "closure", "reopen"]
    occurredOn: str = Field(min_length=1, max_length=32)
    conditionAfter: Literal["good", "fair", "poor", "closed"] | None = None
    costYuan: float | None = Field(default=None, ge=0)
    responsibleUnit: str = Field(default="", max_length=255)
    note: str = Field(default="", max_length=2000)


def blocks_for_write(codes: list[str], context: AuthContext) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for code in codes:
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"关联林班不存在：{code}")
        require_target_block_allowed(context, block)
        blocks.append(block)
    county_codes = {str(block.get("countyCode") or "") for block in blocks}
    if len(county_codes) != 1 or "" in county_codes:
        raise HTTPException(status_code=422, detail="同一道路关联的林班必须属于同一县级行政区")
    return blocks


def road_for_context(record_id: str, context: AuthContext, *, include_deleted: bool = False) -> dict[str, Any]:
    record = extension_record_by_id(ROAD_COLLECTION, record_id, include_deleted=include_deleted)
    if not record:
        raise HTTPException(status_code=404, detail="道路记录不存在")
    for code in record.get("linkedBlockCodes") or []:
        block = block_by_code(str(code), include_deleted=True)
        if block:
            require_target_block_allowed(context, block)
    return record


@router.get("")
def list_roads(
    q: str = "", road_class: str = Query(default="", alias="roadClass"), condition: str = "",
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.roads.view")
    if include_deleted:
        require_permission(context, "forest.roads.manage")
    records = list_extension_records(ROAD_COLLECTION, include_deleted=include_deleted, area_codes=set(context.areas or {"*"}))
    query = q.strip().lower()
    if query:
        records = [item for item in records if query in " ".join(str(item.get(key) or "") for key in ("roadCode", "name", "responsibleUnit", "notes")).lower()]
    if road_class:
        records = [item for item in records if item.get("roadClass") == road_class]
    if condition:
        records = [item for item in records if item.get("condition") == condition]
    return {"items": records[offset:offset + limit], "total": len(records), "limit": limit, "offset": offset}


@router.get("/map.geojson")
def road_map(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.roads.view")
    records = list_extension_records(ROAD_COLLECTION, area_codes=set(context.areas or {"*"}))
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature", "id": item["id"], "geometry": item["geometry"],
        "properties": {key: item.get(key) for key in ("id", "roadCode", "name", "roadClass", "surfaceType", "condition", "widthM", "lengthKm", "linkedBlockCodes")},
    } for item in records]}


@router.get("/export.csv")
def export_roads(context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "forest.roads.export")
    records = list_extension_records(ROAD_COLLECTION, area_codes=set(context.areas or {"*"}))
    stream = io.StringIO(); writer = csv.writer(stream)
    writer.writerow(["道路编号", "道路名称", "等级", "路面", "路况", "长度(km)", "宽度(m)", "关联林班", "责任单位", "最近巡检", "更新时间"])
    for item in records:
        writer.writerow([item.get("roadCode"), item.get("name"), item.get("roadClass"), item.get("surfaceType"), item.get("condition"), item.get("lengthKm"), item.get("widthM"), "、".join(item.get("linkedBlockCodes") or []), item.get("responsibleUnit"), item.get("lastInspectedOn"), item.get("updatedAt")])
    return Response(content="\ufeff" + stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="forest-roads.csv"'})


@router.post("", status_code=201)
def create_road(payload: RoadPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.roads.create")
    if any(item.get("roadCode") == payload.roadCode for item in list_extension_records(ROAD_COLLECTION, include_deleted=True)):
        raise HTTPException(status_code=409, detail="道路编号已存在")
    blocks = blocks_for_write(payload.linkedBlockCodes, context)
    now = utc_now(); values = payload.model_dump()
    values["lengthKm"] = payload.lengthKm if payload.lengthKm is not None else line_length_km(payload.geometry)
    record = {"id": str(uuid.uuid4()), **values, "areaCode": str(blocks[0].get("countyCode") or "") if blocks else "", "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None}
    return save_extension_record(ROAD_COLLECTION, record, create=True)


@router.get("/{record_id}")
def get_road(record_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.roads.view")
    record = road_for_context(record_id, context, include_deleted=True)
    record["maintenance"] = [item for item in list_extension_records(MAINTENANCE_COLLECTION) if item.get("roadId") == record_id]
    return record


@router.patch("/{record_id}")
def patch_road(record_id: str, payload: RoadPatch, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.roads.update")
    record = road_for_context(record_id, context)
    if int(record.get("version") or 1) != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="道路记录已被其他用户修改，请刷新后重试")
    changes = payload.model_dump(exclude_unset=True); changes.pop("expectedVersion", None)
    if "linkedBlockCodes" in changes:
        blocks = blocks_for_write(changes["linkedBlockCodes"], context)
        record["areaCode"] = str(blocks[0].get("countyCode") or "") if blocks else ""
    record.update(changes)
    if "geometry" in changes and "lengthKm" not in changes:
        record["lengthKm"] = line_length_km(changes["geometry"])
    record.update({"version": int(record.get("version") or 1) + 1, "updatedAt": utc_now()})
    return save_extension_record(ROAD_COLLECTION, record, create=False)


@router.delete("/{record_id}")
def delete_road(record_id: str, expected_version: int = Query(alias="expectedVersion", ge=1), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.roads.delete")
    road_for_context(record_id, context)
    try:
        return soft_delete_extension_record(ROAD_COLLECTION, record_id, expected_version=expected_version) or {}
    except ValueError as error:
        raise HTTPException(status_code=409, detail="道路记录已被其他用户修改，请刷新后重试") from error


@router.post("/{record_id}/restore")
def restore_road(record_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.roads.manage")
    record = road_for_context(record_id, context, include_deleted=True)
    record.update({"deletedAt": None, "version": int(record.get("version") or 1) + 1, "updatedAt": utc_now()})
    return save_extension_record(ROAD_COLLECTION, record, create=False)


@router.post("/{record_id}/maintenance", status_code=201)
def add_maintenance(record_id: str, payload: MaintenancePayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.roads.maintain")
    road = road_for_context(record_id, context)
    now = utc_now()
    event = {"id": str(uuid.uuid4()), "roadId": record_id, **payload.model_dump(), "areaCode": road.get("areaCode") or "", "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None}
    saved = save_extension_record(MAINTENANCE_COLLECTION, event, create=True)
    road.update({"lastInspectedOn": payload.occurredOn, "condition": payload.conditionAfter or road.get("condition"), "version": int(road.get("version") or 1) + 1, "updatedAt": now})
    save_extension_record(ROAD_COLLECTION, road, create=False)
    return saved
