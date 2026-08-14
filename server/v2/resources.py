from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, Query, Response

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.forest_blocks import (
    ForestBlockFilters,
    ForestBlockIn,
    ForestBlockOut,
    ForestBlockPatch,
    create_forest_block,
    delete_forest_block,
    get_forest_block,
    list_forest_blocks,
    list_forest_block_versions,
    patch_forest_block,
    rollback_forest_block,
    ForestBlockRollbackRequest,
)
from server.modules.forest_rights import (
    ForestRightFilters,
    ForestRightIn,
    ForestRightOut,
    ForestRightPatch,
    create_forest_right,
    delete_forest_right,
    get_forest_right,
    list_forest_rights,
    patch_forest_right,
)
from server.modules.forest_subcompartments import (
    ForestSubcompartmentFilters,
    ForestSubcompartmentIn,
    ForestSubcompartmentOut,
    ForestSubcompartmentPatch,
    ForestSubcompartmentRollbackRequest,
    create_forest_subcompartment,
    delete_forest_subcompartment,
    get_forest_subcompartment,
    list_forest_subcompartments,
    list_forest_subcompartment_versions,
    patch_forest_subcompartment,
    rollback_forest_subcompartment,
)
from server.modules.resource_surveys import (
    ResourceSnapshotIn,
    ResourceSnapshotPatch,
    ResourceSurveyIn,
    ResourceSurveyPatch,
    create_resource_snapshot,
    create_resource_survey,
    delete_resource_snapshot,
    delete_resource_survey,
    get_resource_snapshot,
    get_resource_survey,
    list_resource_snapshots,
    list_resource_surveys,
    patch_resource_snapshot,
    patch_resource_survey,
    resource_snapshot_comparison,
    resource_snapshot_versions,
)


router = APIRouter(prefix="/resources", tags=["v2-resources"])


def forest_block_filter_facets(context: AuthContext) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list_forest_blocks(ForestBlockFilters(limit=200, offset=offset), context)
        items = list(page.get("items") or [])
        records.extend(items)
        offset += len(items)
        if not items or offset >= int(page.get("total") or 0):
            break

    def divisions(code_key: str, name_key: str) -> list[dict[str, str]]:
        values: dict[str, str] = {}
        for record in records:
            code = str(record.get(code_key) or "").strip()
            name = str(record.get(name_key) or "").strip()
            if code and name:
                values.setdefault(code, name)
        return [
            {"code": code, "name": name}
            for code, name in sorted(values.items(), key=lambda value: (value[1], value[0]))
        ]

    def values(key: str) -> list[str]:
        return sorted({str(record.get(key) or "").strip() for record in records if str(record.get(key) or "").strip()})

    towns: dict[tuple[str, str], str] = {}
    for record in records:
        code = str(record.get("townCode") or "").strip()
        name = str(record.get("townName") or "").strip()
        county_code = str(record.get("countyCode") or "").strip()
        if code and name:
            towns.setdefault((county_code, code), name)

    return {
        "total": len(records),
        "counties": divisions("countyCode", "countyName"),
        "towns": [
            {"code": code, "name": name, "countyCode": county_code}
            for (county_code, code), name in sorted(
                towns.items(), key=lambda value: (value[1], value[0][1])
            )
        ],
        "qualityGrades": values("qualityGrade"),
        "healthStatuses": values("healthStatus"),
        "riskLevels": values("riskLevel"),
        "baseTypes": values("baseType"),
        "operationTypes": values("operationType"),
    }


def csv_response(filename: str, headers: list[str], rows: list[list[Any]]) -> Response:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        content="\ufeff" + stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/forest-blocks")
def forest_block_ledger(
    q: str = Query(default=""),
    county_code: str = Query(default="", alias="countyCode"),
    town_code: str = Query(default="", alias="townCode"),
    village_code: str = Query(default="", alias="villageCode"),
    base_type: str = Query(default="", alias="baseType"),
    operation_type: str = Query(default="", alias="operationType"),
    quality_grade: str = Query(default="", alias="qualityGrade"),
    health_status: str = Query(default="", alias="healthStatus"),
    risk_level: str = Query(default="", alias="riskLevel"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.blocks.view")
    if include_deleted:
        require_permission(context, "forest.blocks.manage")
    return list_forest_blocks(
        ForestBlockFilters(
            q=q,
            countyCode=county_code,
            townCode=town_code,
            villageCode=village_code,
            baseType=base_type,
            operationType=operation_type,
            qualityGrade=quality_grade,
            healthStatus=health_status,
            riskLevel=risk_level,
            includeDeleted=include_deleted,
            limit=limit,
            offset=offset,
        ),
        context,
    )


@router.get("/forest-blocks-facets")
def forest_block_facets(
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.blocks.view")
    return forest_block_filter_facets(context)


@router.get("/forest-blocks-export.csv")
def export_forest_blocks(
    q: str = Query(default=""),
    base_type: str = Query(default="", alias="baseType"),
    operation_type: str = Query(default="", alias="operationType"),
    risk_level: str = Query(default="", alias="riskLevel"),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "forest.blocks.export")
    require_permission(context, "forest.blocks.view")
    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list_forest_blocks(
            ForestBlockFilters(
                q=q,
                baseType=base_type,
                operationType=operation_type,
                riskLevel=risk_level,
                limit=200,
                offset=offset,
            ),
            context,
        )
        records.extend(page["items"])
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            break
    return csv_response(
        "forest-blocks.csv",
        ["林班编号", "林班名称", "区县", "乡镇", "村", "面积(亩)", "竹种/林种", "基地类型", "经营类型", "质量等级", "健康状态", "风险等级", "边界状态", "更新时间"],
        [[
            item.get("blockCode", ""), item.get("name", ""), item.get("countyName", ""),
            item.get("townName", ""), item.get("villageName", ""), item.get("areaMu", ""),
            item.get("forestType", ""), item.get("baseType", ""), item.get("operationType", ""),
            item.get("qualityGrade", ""), item.get("healthStatus", ""), item.get("riskLevel", ""),
            "有边界" if item.get("geometry") else "待补图", item.get("updatedAt", ""),
        ] for item in records],
    )


@router.post("/forest-blocks", response_model=ForestBlockOut)
def create_v2_forest_block(
    payload: ForestBlockIn,
    context: AuthContext = Depends(request_context),
) -> ForestBlockOut:
    return create_forest_block(payload, context)


@router.get("/forest-blocks/{block_id}", response_model=ForestBlockOut)
def get_v2_forest_block(
    block_id: str,
    context: AuthContext = Depends(request_context),
) -> ForestBlockOut:
    require_permission(context, "forest.blocks.view")
    return get_forest_block(block_id, context)


@router.patch("/forest-blocks/{block_id}", response_model=ForestBlockOut)
def patch_v2_forest_block(
    block_id: str,
    payload: ForestBlockPatch,
    context: AuthContext = Depends(request_context),
) -> ForestBlockOut:
    return patch_forest_block(block_id, payload, context)


@router.get("/forest-blocks/{block_id}/versions")
def get_v2_forest_block_versions(
    block_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return list_forest_block_versions(block_id, context)


@router.post("/forest-blocks/{block_id}/rollback")
def rollback_v2_forest_block(
    block_id: str,
    payload: ForestBlockRollbackRequest,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return rollback_forest_block(block_id, payload, context)


@router.delete("/forest-blocks/{block_id}")
def delete_v2_forest_block(
    block_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return delete_forest_block(block_id, context)


@router.get("/forest-subcompartments")
def forest_subcompartment_ledger(
    q: str = Query(default=""),
    forest_block_id: str = Query(default="", alias="forestBlockId"),
    county_code: str = Query(default="", alias="countyCode"),
    town_code: str = Query(default="", alias="townCode"),
    village_code: str = Query(default="", alias="villageCode"),
    management_status: str = Query(default="", alias="managementStatus"),
    risk_level: str = Query(default="", alias="riskLevel"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return list_forest_subcompartments(
        ForestSubcompartmentFilters(
            q=q,
            forestBlockId=forest_block_id,
            countyCode=county_code,
            townCode=town_code,
            villageCode=village_code,
            managementStatus=management_status,
            riskLevel=risk_level,
            includeDeleted=include_deleted,
            limit=limit,
            offset=offset,
        ),
        context,
    )


@router.get("/forest-subcompartments-export.csv")
def export_forest_subcompartments(
    q: str = Query(default=""),
    forest_block_id: str = Query(default="", alias="forestBlockId"),
    management_status: str = Query(default="", alias="managementStatus"),
    risk_level: str = Query(default="", alias="riskLevel"),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "forest.subcompartments.export")
    require_permission(context, "forest.subcompartments.view")
    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list_forest_subcompartments(
            ForestSubcompartmentFilters(
                q=q,
                forestBlockId=forest_block_id,
                managementStatus=management_status,
                riskLevel=risk_level,
                limit=200,
                offset=offset,
            ),
            context,
        )
        records.extend(page["items"])
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            break
    return csv_response(
        "forest-subcompartments.csv",
        ["小班编号", "小班名称", "所属林班编号", "所属林班名称", "区县", "乡镇", "村", "面积(亩)", "竹种", "林种", "起源", "龄组", "质量等级", "经营状态", "风险等级", "边界状态", "更新时间"],
        [[
            item.get("subcompartmentCode", ""), item.get("name", ""), item.get("forestBlockCode", ""),
            item.get("forestBlockName", ""), item.get("countyName", ""), item.get("townName", ""),
            item.get("villageName", ""), item.get("areaMu", ""), item.get("bambooSpecies", ""),
            item.get("forestCategory", ""), item.get("origin", ""), item.get("ageGroup", ""),
            item.get("qualityGrade", ""), item.get("managementStatus", ""), item.get("riskLevel", ""),
            "有边界" if item.get("geometry") else "待补图", item.get("updatedAt", ""),
        ] for item in records],
    )


@router.post("/forest-subcompartments", response_model=ForestSubcompartmentOut)
def create_v2_forest_subcompartment(
    payload: ForestSubcompartmentIn,
    context: AuthContext = Depends(request_context),
) -> ForestSubcompartmentOut:
    return create_forest_subcompartment(payload, context)


@router.get("/forest-subcompartments/{record_id}", response_model=ForestSubcompartmentOut)
def get_v2_forest_subcompartment(
    record_id: str,
    context: AuthContext = Depends(request_context),
) -> ForestSubcompartmentOut:
    return get_forest_subcompartment(record_id, context)


@router.patch("/forest-subcompartments/{record_id}", response_model=ForestSubcompartmentOut)
def patch_v2_forest_subcompartment(
    record_id: str,
    payload: ForestSubcompartmentPatch,
    context: AuthContext = Depends(request_context),
) -> ForestSubcompartmentOut:
    return patch_forest_subcompartment(record_id, payload, context)


@router.get("/forest-subcompartments/{record_id}/versions")
def get_v2_forest_subcompartment_versions(
    record_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return list_forest_subcompartment_versions(record_id, context)


@router.post("/forest-subcompartments/{record_id}/rollback")
def rollback_v2_forest_subcompartment(
    record_id: str,
    payload: ForestSubcompartmentRollbackRequest,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return rollback_forest_subcompartment(record_id, payload, context)


@router.delete("/forest-subcompartments/{record_id}")
def delete_v2_forest_subcompartment(
    record_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return delete_forest_subcompartment(record_id, context)


@router.get("/resource-surveys")
def resource_survey_ledger(
    q: str = Query(default=""),
    status: str = Query(default=""),
    survey_type: str = Query(default="", alias="surveyType"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return list_resource_surveys(
        q=q,
        status=status,
        survey_type=survey_type,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
        context=context,
    )


@router.post("/resource-surveys")
def create_v2_resource_survey(
    payload: ResourceSurveyIn,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return create_resource_survey(payload, context)


@router.get("/resource-surveys/{survey_id}")
def get_v2_resource_survey(
    survey_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return get_resource_survey(survey_id, context)


@router.patch("/resource-surveys/{survey_id}")
def patch_v2_resource_survey(
    survey_id: str,
    payload: ResourceSurveyPatch,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return patch_resource_survey(survey_id, payload, context)


@router.delete("/resource-surveys/{survey_id}")
def delete_v2_resource_survey(
    survey_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return delete_resource_survey(survey_id, context)


@router.get("/resource-surveys/{survey_id}/snapshots")
def resource_snapshot_ledger(
    survey_id: str,
    q: str = Query(default=""),
    subcompartment_id: str = Query(default="", alias="forestSubcompartmentId"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    get_resource_survey(survey_id, context)
    return list_resource_snapshots(
        survey_id=survey_id,
        subcompartment_id=subcompartment_id,
        q=q,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
        context=context,
    )


@router.post("/resource-surveys/{survey_id}/snapshots")
def create_v2_resource_snapshot(
    survey_id: str,
    payload: ResourceSnapshotIn,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return create_resource_snapshot(survey_id, payload, context)


@router.get("/resource-snapshots/{snapshot_id}")
def get_v2_resource_snapshot(
    snapshot_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return get_resource_snapshot(snapshot_id, context)


@router.patch("/resource-snapshots/{snapshot_id}")
def patch_v2_resource_snapshot(
    snapshot_id: str,
    payload: ResourceSnapshotPatch,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return patch_resource_snapshot(snapshot_id, payload, context)


@router.delete("/resource-snapshots/{snapshot_id}")
def delete_v2_resource_snapshot(
    snapshot_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return delete_resource_snapshot(snapshot_id, context)


@router.get("/resource-snapshots/{snapshot_id}/versions")
def get_v2_resource_snapshot_versions(
    snapshot_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return resource_snapshot_versions(snapshot_id, context)


@router.get("/resource-snapshots/{snapshot_id}/comparison")
def compare_v2_resource_snapshot(
    snapshot_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return resource_snapshot_comparison(snapshot_id, context)


@router.get("/forest-rights")
def forest_right_ledger(
    q: str = Query(default=""),
    archive_status: str = Query(default="", alias="archiveStatus"),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.rights.view")
    if include_deleted:
        require_permission(context, "forest.rights.manage")
    return list_forest_rights(
        ForestRightFilters(
            q=q,
            archiveStatus=archive_status,
            linkedBlockCode=linked_block_code,
            includeDeleted=include_deleted,
            limit=limit,
            offset=offset,
        ),
        context,
    )


@router.post("/forest-rights", response_model=ForestRightOut)
def create_v2_forest_right(
    payload: ForestRightIn,
    context: AuthContext = Depends(request_context),
) -> ForestRightOut:
    return create_forest_right(payload, context)


@router.get("/forest-rights/{right_id}", response_model=ForestRightOut)
def get_v2_forest_right(
    right_id: str,
    context: AuthContext = Depends(request_context),
) -> ForestRightOut:
    require_permission(context, "forest.rights.view")
    return get_forest_right(right_id, context)


@router.patch("/forest-rights/{right_id}", response_model=ForestRightOut)
def patch_v2_forest_right(
    right_id: str,
    payload: ForestRightPatch,
    context: AuthContext = Depends(request_context),
) -> ForestRightOut:
    return patch_forest_right(right_id, payload, context)


@router.delete("/forest-rights/{right_id}")
def delete_v2_forest_right(
    right_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return delete_forest_right(right_id, context)
