from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .auth import AuthContext, area_allowed, request_context, require_write_access
from .database import forest_blocks_json_path, load_json_records, save_json_records


router = APIRouter(prefix="/api", tags=["forest-blocks"])


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


def load_all_blocks() -> list[dict[str, Any]]:
    return load_json_records(forest_blocks_json_path())


def load_blocks() -> list[dict[str, Any]]:
    return [item for item in load_all_blocks() if not item.get("deletedAt")]


def save_blocks(blocks: list[dict[str, Any]]) -> None:
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
    blocks = [block for block in load_blocks() if block_matches_filters(block, filters, context)]
    items = blocks[filters.offset : filters.offset + filters.limit]
    return {
        "items": items,
        "total": len(blocks),
        "limit": filters.limit,
        "offset": filters.offset,
    }


def forest_block_feature_collection(filters: ForestBlockFilters, context: AuthContext) -> dict[str, Any]:
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
    blocks = [block for block in load_blocks() if block_matches_filters(block, filters, context)]
    summary: dict[str, Any] = {
        "total": len(blocks),
        "riskLevel": {},
        "qualityGrade": {},
        "baseType": {},
    }
    for block in blocks:
        for key in ("riskLevel", "qualityGrade", "baseType"):
            value = block.get(key)
            if not value:
                continue
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
