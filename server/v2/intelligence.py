from __future__ import annotations

import io
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.extension_store import (
    extension_record_by_id,
    extension_record_by_idempotency_key,
    list_extension_records,
    save_extension_record,
    utc_now,
)
from server.modules.forest_blocks import block_by_code, require_target_block_allowed
from server.modules.forest_subcompartments import (
    ForestSubcompartmentFilters,
    ForestSubcompartmentPatch,
    get_forest_subcompartment,
    list_forest_subcompartments,
    patch_forest_subcompartment,
)
from server.modules.labor import list_teams, list_workers


router = APIRouter(prefix="/intelligence", tags=["v2-intelligence"])
CHANGE_COLLECTION = "resource-change-jobs"
GROWTH_COLLECTION = "growth-observations"
FORECAST_COLLECTION = "pest-risk-forecasts"
ASSESSMENT_COLLECTION = "operation-effect-assessments"
DISPATCH_COLLECTION = "patrol-dispatch-decisions"


def visible_areas(context: AuthContext) -> set[str]:
    return set(context.areas or {"*"})


def target_area_code(target: Any) -> str:
    value = target.get("countyCode") if isinstance(target, dict) else getattr(target, "countyCode", "")
    return str(value or "")


def all_subcompartments(context: AuthContext) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        result = list_forest_subcompartments(ForestSubcompartmentFilters(limit=200, offset=offset), context)
        items.extend(result["items"])
        offset += len(result["items"])
        if not result["items"] or offset >= result["total"]:
            return items


def slope_bucket(value: Any) -> str:
    try:
        slope = float(value)
    except (TypeError, ValueError):
        return "未标注"
    if slope < 15:
        return "缓坡(<15°)"
    if slope < 25:
        return "斜坡(15–25°)"
    if slope < 35:
        return "陡坡(25–35°)"
    return "险坡(≥35°)"


@router.get("/resources/statistics")
def resource_statistics(
    bambooSpecies: str = "", ageGroup: str = "", slopeMin: float | None = None, slopeMax: float | None = None,
    countyCode: str = "", townCode: str = "", groupBy: Literal["bambooSpecies", "ageGroup", "slope", "town"] = "bambooSpecies",
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.subcompartments.view")
    records = all_subcompartments(context)
    if bambooSpecies:
        records = [item for item in records if item.get("bambooSpecies") == bambooSpecies]
    if ageGroup:
        records = [item for item in records if item.get("ageGroup") == ageGroup]
    if countyCode:
        records = [item for item in records if item.get("countyCode") == countyCode]
    if townCode:
        records = [item for item in records if item.get("townCode") == townCode]
    if slopeMin is not None:
        records = [item for item in records if item.get("slopeDegree") is not None and float(item["slopeDegree"]) >= slopeMin]
    if slopeMax is not None:
        records = [item for item in records if item.get("slopeDegree") is not None and float(item["slopeDegree"]) <= slopeMax]
    key_getters = {
        "bambooSpecies": lambda item: item.get("bambooSpecies") or "未标注竹种",
        "ageGroup": lambda item: item.get("ageGroup") or "未标注龄级",
        "slope": lambda item: slope_bucket(item.get("slopeDegree")),
        "town": lambda item: item.get("townName") or "未标注乡镇",
    }
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "areaMu": 0.0})
    for record in records:
        key = str(key_getters[groupBy](record))
        grouped[key]["count"] += 1
        grouped[key]["areaMu"] += float(record.get("areaMu") or 0)
    items = [
        {"name": key, "count": value["count"], "areaMu": round(value["areaMu"], 4)}
        for key, value in grouped.items()
    ]
    items.sort(key=lambda item: (-item["areaMu"], item["name"]))
    return {
        "source": "forest-subcompartment-ledger", "asOf": utc_now(), "groupBy": groupBy,
        "filters": {"bambooSpecies": bambooSpecies, "ageGroup": ageGroup, "slopeMin": slopeMin, "slopeMax": slopeMax, "countyCode": countyCode, "townCode": townCode},
        "items": items, "total": len(records), "totalAreaMu": round(sum(float(item.get("areaMu") or 0) for item in records), 4),
    }


@router.get("/resources/statistics.xlsx")
def export_resource_statistics(
    groupBy: Literal["bambooSpecies", "ageGroup", "slope", "town"] = "bambooSpecies",
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "forest.subcompartments.export")
    from openpyxl import Workbook

    result = resource_statistics(groupBy=groupBy, context=context)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "资源专题统计"
    sheet.append(["统计维度", "小班数量", "面积(亩)"])
    for item in result["items"]:
        sheet.append([item["name"], item["count"], item["areaMu"]])
    sheet.freeze_panes = "A2"
    stream = io.BytesIO()
    workbook.save(stream)
    return Response(
        content=stream.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="resource-statistics.xlsx"'},
    )


@router.get("/resources/statistics.pdf")
def export_resource_statistics_pdf(
    groupBy: Literal["bambooSpecies", "ageGroup", "slope", "town"] = "bambooSpecies",
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "forest.subcompartments.export")
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="PDF 导出组件尚未安装。") from exc
    result = resource_statistics(groupBy=groupBy, context=context)
    stream = io.BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    document = SimpleDocTemplate(stream, pagesize=A4, title="智慧竹山资源专题统计")
    rows = [["统计维度", "小班数量", "面积(亩)"]] + [[item["name"], item["count"], item["areaMu"]] for item in result["items"]]
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEFE7")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9BB7AA")), ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    document.build([table])
    return Response(content=stream.getvalue(), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="resource-statistics.pdf"'})


class ChangeJobPayload(BaseModel):
    subcompartmentId: str
    baselineSceneId: str = Field(min_length=1, max_length=160)
    comparisonSceneId: str = Field(min_length=1, max_length=160)
    changeType: Literal["boundary", "cover", "harvest", "disaster"] = "boundary"
    changedAreaMu: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    proposedGeometry: dict[str, Any] | None = None
    evidenceUrls: list[str] = Field(default_factory=list)
    idempotencyKey: str = Field(default="", max_length=191)


class ReviewPayload(BaseModel):
    action: Literal["accept", "reject", "apply"]
    note: str = Field(default="", max_length=2000)
    expectedVersion: int = Field(ge=1)


@router.get("/resources/change-jobs")
def change_jobs(status: str = "", context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.subcompartments.view")
    items = list_extension_records(CHANGE_COLLECTION, area_codes=visible_areas(context))
    if status:
        items = [item for item in items if item.get("status") == status]
    return {"items": items, "total": len(items)}


@router.post("/resources/change-jobs", status_code=201)
def create_change_job(payload: ChangeJobPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.subcompartments.manage")
    target = get_forest_subcompartment(payload.subcompartmentId, context)
    existing = extension_record_by_idempotency_key(CHANGE_COLLECTION, payload.idempotencyKey)
    if existing:
        if existing.get("subcompartmentId") != payload.subcompartmentId:
            raise HTTPException(status_code=409, detail="幂等键已被其他变化检测任务使用。")
        return existing
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), **payload.model_dump(), "subcompartmentCode": target.subcompartmentCode,
        "areaCode": target_area_code(target),
        "sourceSubcompartmentVersion": target.version, "status": "pending-review", "reviewedBy": "", "reviewedAt": None,
        "appliedAt": None, "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
    }
    return save_extension_record(CHANGE_COLLECTION, record, create=True)


@router.post("/resources/change-jobs/{job_id}/actions")
def review_change_job(job_id: str, payload: ReviewPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.subcompartments.manage")
    record = extension_record_by_id(CHANGE_COLLECTION, job_id)
    if not record:
        raise HTTPException(status_code=404, detail="变化检测任务不存在。")
    if int(record.get("version") or 1) != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="变化检测任务已被更新，请刷新后重试。")
    get_forest_subcompartment(str(record["subcompartmentId"]), context)
    if payload.action in {"accept", "reject"}:
        if record.get("status") != "pending-review":
            raise HTTPException(status_code=409, detail="仅待核查任务可以审核。")
        record.update({
            "status": "accepted" if payload.action == "accept" else "rejected", "reviewNote": payload.note,
            "reviewedBy": context.user, "reviewedAt": utc_now(),
        })
    else:
        if record.get("status") != "accepted":
            raise HTTPException(status_code=409, detail="变化图斑必须人工核查通过后才能更新小班版本。")
        if not record.get("proposedGeometry"):
            raise HTTPException(status_code=422, detail="变化任务没有可应用的边界成果。")
        target = get_forest_subcompartment(str(record["subcompartmentId"]), context)
        if target.version != int(record.get("sourceSubcompartmentVersion") or 0):
            raise HTTPException(status_code=409, detail="小班版本已变化，请重新执行变化检测。")
        updated = patch_forest_subcompartment(
            target.id,
            ForestSubcompartmentPatch(expectedVersion=target.version, geometry=record["proposedGeometry"]),
            context,
        )
        record.update({"status": "applied", "appliedAt": utc_now(), "appliedBy": context.user, "resultVersion": updated.version})
    record.update({"version": int(record.get("version") or 1) + 1, "updatedAt": utc_now()})
    return save_extension_record(CHANGE_COLLECTION, record, create=False)


class GrowthPayload(BaseModel):
    subcompartmentId: str
    observedOn: date
    ndvi: float | None = Field(default=None, ge=-1, le=1)
    lai: float | None = Field(default=None, ge=0)
    sourceSceneId: str = Field(default="", max_length=160)
    qualityScore: float | None = Field(default=None, ge=0, le=1)
    anomaly: bool = False
    anomalyReason: str = Field(default="", max_length=1000)
    idempotencyKey: str = Field(default="", max_length=191)


@router.get("/growth/observations")
def growth_observations(month: str = "", anomalyOnly: bool = False, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.surveys.view")
    items = list_extension_records(GROWTH_COLLECTION, area_codes=visible_areas(context))
    if month:
        items = [item for item in items if str(item.get("observedOn") or "").startswith(month)]
    if anomalyOnly:
        items = [item for item in items if item.get("anomaly")]
    return {"items": items, "total": len(items)}


@router.post("/growth/observations", status_code=201)
def create_growth_observation(payload: GrowthPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "forest.surveys.manage")
    target = get_forest_subcompartment(payload.subcompartmentId, context)
    existing = extension_record_by_idempotency_key(GROWTH_COLLECTION, payload.idempotencyKey)
    if existing:
        if existing.get("subcompartmentId") != payload.subcompartmentId:
            raise HTTPException(status_code=409, detail="幂等键已被其他长势观测使用。")
        return existing
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), **payload.model_dump(mode="json"), "subcompartmentCode": target.subcompartmentCode,
        "areaCode": target_area_code(target),
        "forestBlockCode": target.forestBlockCode, "status": "anomaly" if payload.anomaly else "normal",
        "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
    }
    return save_extension_record(GROWTH_COLLECTION, record, create=True)


class EffectAssessmentPayload(BaseModel):
    operationType: Literal["tending", "fertilization", "pest-control", "harvest"]
    taskId: str = Field(min_length=1, max_length=36)
    subcompartmentId: str
    beforeObservedOn: date
    afterObservedOn: date
    beforeNdvi: float | None = Field(default=None, ge=-1, le=1)
    afterNdvi: float | None = Field(default=None, ge=-1, le=1)
    beforeLai: float | None = Field(default=None, ge=0)
    afterLai: float | None = Field(default=None, ge=0)
    outcome: Literal["improved", "stable", "declined", "pending-review"]
    evidenceUrls: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=2000)
    idempotencyKey: str = Field(default="", max_length=191)


@router.get("/operations/effect-assessments")
def operation_effect_assessments(
    taskId: str = "", context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.surveys.view")
    records = list_extension_records(ASSESSMENT_COLLECTION, area_codes=visible_areas(context))
    if taskId:
        records = [record for record in records if record.get("taskId") == taskId]
    return {"items": records, "total": len(records)}


@router.post("/operations/effect-assessments", status_code=201)
def create_operation_effect_assessment(
    payload: EffectAssessmentPayload, context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.surveys.manage")
    target = get_forest_subcompartment(payload.subcompartmentId, context)
    existing = extension_record_by_idempotency_key(ASSESSMENT_COLLECTION, payload.idempotencyKey)
    if existing:
        if existing.get("subcompartmentId") != payload.subcompartmentId:
            raise HTTPException(status_code=409, detail="幂等键已被其他效果评估使用。")
        return existing
    if payload.afterObservedOn <= payload.beforeObservedOn:
        raise HTTPException(status_code=422, detail="作业后观测日期必须晚于作业前观测日期。")
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), **payload.model_dump(mode="json"),
        "subcompartmentCode": target.subcompartmentCode, "forestBlockCode": target.forestBlockCode,
        "areaCode": target_area_code(target),
        "ndviDelta": None if payload.beforeNdvi is None or payload.afterNdvi is None else round(payload.afterNdvi - payload.beforeNdvi, 5),
        "laiDelta": None if payload.beforeLai is None or payload.afterLai is None else round(payload.afterLai - payload.beforeLai, 5),
        "status": "completed" if payload.outcome != "pending-review" else "pending-review",
        "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
    }
    return save_extension_record(ASSESSMENT_COLLECTION, record, create=True)


class PestForecastPayload(BaseModel):
    subcompartmentId: str
    forecastFrom: date
    forecastDays: int = Field(ge=7, le=15)
    weatherSource: str = Field(min_length=1, max_length=160)
    imagerySource: str = Field(min_length=1, max_length=160)
    insectSource: str = Field(min_length=1, max_length=160)
    riskScore: float = Field(ge=0, le=100)
    modelAssetId: str = Field(min_length=1, max_length=36)
    modelVersion: str = Field(min_length=1, max_length=64)
    factors: dict[str, Any] = Field(default_factory=dict)
    idempotencyKey: str = Field(default="", max_length=191)


@router.post("/pest/forecasts", status_code=201)
def create_pest_forecast(payload: PestForecastPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.inference.operate")
    target = get_forest_subcompartment(payload.subcompartmentId, context)
    existing = extension_record_by_idempotency_key(FORECAST_COLLECTION, payload.idempotencyKey)
    if existing:
        if existing.get("subcompartmentId") != payload.subcompartmentId:
            raise HTTPException(status_code=409, detail="幂等键已被其他病虫害预测使用。")
        return existing
    level = "red" if payload.riskScore >= 80 else "orange" if payload.riskScore >= 60 else "yellow" if payload.riskScore >= 40 else "blue"
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), **payload.model_dump(mode="json"), "subcompartmentCode": target.subcompartmentCode,
        "areaCode": target_area_code(target),
        "forestBlockCode": target.forestBlockCode, "warningLevel": level, "status": "active",
        "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
    }
    return save_extension_record(FORECAST_COLLECTION, record, create=True)


@router.get("/pest/forecasts")
def pest_forecasts(level: str = "", context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.inference.view")
    items = list_extension_records(FORECAST_COLLECTION, area_codes=visible_areas(context))
    if level:
        items = [item for item in items if item.get("warningLevel") == level]
    return {"items": items, "total": len(items)}


class DispatchPayload(BaseModel):
    patrolTaskId: str = Field(min_length=1, max_length=36)
    blockCode: str = Field(min_length=1, max_length=128)
    requiredSkills: list[str] = Field(default_factory=list)
    assigneeType: Literal["worker", "team"] = "worker"
    assigneeId: str = Field(default="", max_length=36)
    mode: Literal["automatic", "manual"] = "automatic"
    note: str = Field(default="", max_length=1000)


@router.post("/patrol/dispatch", status_code=201)
def dispatch_patrol(payload: DispatchPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "business.maintenanceTasks.manage")
    block = block_by_code(payload.blockCode)
    if not block:
        raise HTTPException(status_code=422, detail="巡护派单必须关联正式林班。")
    require_target_block_allowed(context, block)
    candidates = list_workers() if payload.assigneeType == "worker" else list_teams()
    candidates = [item for item in candidates if item.get("employmentStatus", item.get("status")) in {"available", "active"}]
    required = set(payload.requiredSkills)
    ranked = sorted(
        candidates,
        key=lambda item: (-len(required.intersection(set(item.get("skillCodes") or []))), str(item.get("name") or "")),
    )
    selected = next((item for item in candidates if item.get("id") == payload.assigneeId), None) if payload.assigneeId else (ranked[0] if ranked else None)
    if not selected:
        raise HTTPException(status_code=409, detail="没有可用且符合数据范围的派单对象。")
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), **payload.model_dump(), "assigneeId": selected["id"], "assigneeName": selected.get("name"),
        "areaCode": str(block.get("countyCode") or ""),
        "candidateSnapshot": [{"id": item["id"], "name": item.get("name"), "skillCodes": item.get("skillCodes") or []} for item in ranked[:10]],
        "status": "assigned", "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
    }
    return save_extension_record(DISPATCH_COLLECTION, record, create=True)
