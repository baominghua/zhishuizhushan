from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.forest_blocks import ForestBlockFilters, list_forest_blocks
from server.modules.forest_rights import ForestRightFilters, list_forest_rights
from server.modules.forest_subcompartments import (
    ForestSubcompartmentFilters,
    list_forest_subcompartments,
)


router = APIRouter(prefix="/entities", tags=["v2-entities"])


def location_label(record: dict[str, Any]) -> str:
    return " / ".join(
        str(record.get(field) or "").strip()
        for field in ("countyName", "townName", "villageName")
        if str(record.get(field) or "").strip()
    )


@router.get("/forest-blocks")
def forest_block_selector(
    q: str = Query(default=""),
    county_code: str = Query(default="", alias="countyCode"),
    town_code: str = Query(default="", alias="townCode"),
    quality_grade: str = Query(default="", alias="qualityGrade"),
    health_status: str = Query(default="", alias="healthStatus"),
    risk_level: str = Query(default="", alias="riskLevel"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.blocks.view")
    result = list_forest_blocks(
        ForestBlockFilters(
            q=q,
            countyCode=county_code,
            townCode=town_code,
            qualityGrade=quality_grade,
            healthStatus=health_status,
            riskLevel=risk_level,
            limit=limit,
            offset=offset,
        ),
        context,
    )
    return {
        "kind": "forest-block",
        "items": [
            {
                "id": item.get("id"),
                "code": item.get("blockCode"),
                "name": item.get("name"),
                "location": location_label(item),
                "areaMu": item.get("areaMu"),
                "hasGeometry": bool(item.get("geometry")),
                "riskLevel": item.get("riskLevel"),
            }
            for item in result.get("items") or []
        ],
        "total": int(result.get("total") or 0),
        "limit": limit,
        "offset": offset,
    }


@router.get("/forest-subcompartments")
def forest_subcompartment_selector(
    q: str = Query(default=""),
    forest_block_id: str = Query(default="", alias="forestBlockId"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    result = list_forest_subcompartments(
        ForestSubcompartmentFilters(
            q=q,
            forestBlockId=forest_block_id,
            limit=limit,
            offset=offset,
        ),
        context,
    )
    return {
        "kind": "forest-subcompartment",
        "items": [
            {
                "id": item.get("id"),
                "code": item.get("subcompartmentCode"),
                "name": item.get("name"),
                "forestBlockId": item.get("forestBlockId"),
                "forestBlockCode": item.get("forestBlockCode"),
                "forestBlockName": item.get("forestBlockName"),
                "location": location_label(item),
                "areaMu": item.get("areaMu"),
                "hasGeometry": bool(item.get("geometry")),
                "riskLevel": item.get("riskLevel"),
            }
            for item in result.get("items") or []
        ],
        "total": int(result.get("total") or 0),
        "limit": limit,
        "offset": offset,
    }


@router.get("/forest-rights")
def forest_right_selector(
    q: str = Query(default=""),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.rights.view")
    result = list_forest_rights(
        ForestRightFilters(
            q=q,
            linkedBlockCode=linked_block_code,
            limit=limit,
            offset=offset,
        ),
        context,
    )
    return {
        "kind": "forest-right",
        "items": [
            {
                "id": item.get("id"),
                "code": item.get("archiveCode"),
                "certificateNo": item.get("certificateNo"),
                "holder": item.get("holder"),
                "status": item.get("archiveStatus"),
                "linkedBlockCodes": list(item.get("linkedBlockCodes") or []),
            }
            for item in result.get("items") or []
        ],
        "total": int(result.get("total") or 0),
        "limit": limit,
        "offset": offset,
    }
