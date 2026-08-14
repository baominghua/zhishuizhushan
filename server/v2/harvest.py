from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission
from server.modules.attachments import linked_attachments, sync_attachment_links
from server.modules.auth import AuthContext, request_context
from server.modules.forest_blocks import block_by_code, record_block_version, require_target_block_allowed
from server.modules.forest_rights import right_by_id, require_target_right_allowed
from server.modules.harvest import (
    application_by_id,
    create_application,
    create_quota,
    event_payload,
    list_applications,
    list_quotas,
    list_subjects,
    quota_by_id,
    replace_draft_application,
    restore_application,
    reserve_quota_and_approve,
    soft_delete_application,
    subject_by_identity,
    update_application,
    utc_now,
)
from server.modules.safety_events import create_alert as create_safety_alert


router = APIRouter(prefix="/harvest", tags=["v2-harvest"])
STATUS_ORDER = ["draft", "submitted", "quota_check", "approving", "approved", "operating", "verifying", "completed"]


class HarvestQuotaCreate(BaseModel):
    quotaYear: int = Field(ge=2020, le=2200)
    authorityName: str = Field(min_length=1, max_length=255)
    forestType: str = Field(default="", max_length=64)
    blockCode: str = Field(default="", max_length=128)
    quotaAreaMu: float = Field(gt=0)
    quotaQuantityTon: float = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=1000)


class HarvestApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    applicantType: str
    applicantId: str
    harvestType: str
    requestedAreaMu: float = Field(gt=0)
    requestedQuantityTon: float = Field(default=0, ge=0)
    quotaId: str
    workStartAt: str
    workEndAt: str
    purpose: str = Field(default="", max_length=1000)
    linkedBlockCodes: list[str] = Field(min_length=1)
    linkedRightIds: list[str] = Field(min_length=1)


class HarvestApplicationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    applicantType: str | None = None
    applicantId: str | None = None
    harvestType: str | None = None
    requestedAreaMu: float | None = Field(default=None, gt=0)
    requestedQuantityTon: float | None = Field(default=None, ge=0)
    quotaId: str | None = None
    workStartAt: str | None = None
    workEndAt: str | None = None
    purpose: str | None = Field(default=None, max_length=1000)
    linkedBlockCodes: list[str] | None = None
    linkedRightIds: list[str] | None = None


class HarvestAction(BaseModel):
    note: str = ""
    actualAreaMu: float | None = Field(default=None, gt=0)
    actualQuantityTon: float | None = Field(default=None, ge=0)
    evidenceUrls: list[str] = Field(default_factory=list)
    attachmentIds: list[str] = Field(default_factory=list)
    alertType: str = ""
    alertLevel: str = ""
    alertMessage: str = ""
    locationText: str = ""
    deviceCode: str = ""


def application_number() -> str:
    return f"CF-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def batch_number() -> str:
    return f"PC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


def parse_schedule(start: str, end: str) -> tuple[str, str]:
    try:
        start_at = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        end_at = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="采伐作业时间格式不正确。") from exc
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="作业结束时间必须晚于开始时间。")
    return start_at.isoformat(), end_at.isoformat()


def validate_harvest_type(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in {"timber", "shoot", "tending"}:
        raise HTTPException(status_code=422, detail="不支持的采伐类型。")
    return normalized


def validated_blocks(codes: list[str], context: AuthContext) -> list[dict[str, Any]]:
    normalized = list(dict.fromkeys(str(code).strip() for code in codes if str(code).strip()))
    if not normalized:
        raise HTTPException(status_code=422, detail="采伐申请至少需要选择一个林班。")
    blocks: list[dict[str, Any]] = []
    for code in normalized:
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"林班 {code} 不存在或已删除。")
        require_target_block_allowed(context, block)
        blocks.append(block)
    return blocks


def validated_rights(right_ids: list[str], block_codes: list[str], context: AuthContext) -> list[dict[str, Any]]:
    normalized = list(dict.fromkeys(str(value).strip() for value in right_ids if str(value).strip()))
    rights: list[dict[str, Any]] = []
    covered: set[str] = set()
    for right_id in normalized:
        right = right_by_id(right_id)
        if not right:
            raise HTTPException(status_code=422, detail="所选林权档案不存在或已删除。")
        require_target_right_allowed(context, right)
        archive_status = str(right.get("archiveStatus") or "").strip()
        if archive_status not in {"active", "approved", "valid", "complete"}:
            raise HTTPException(status_code=422, detail=f"林权档案 {right.get('archiveCode')} 当前不是有效状态。")
        linked = {str(code) for code in right.get("linkedBlockCodes") or []}
        covered.update(linked.intersection(block_codes))
        rights.append(right)
    missing = sorted(set(block_codes) - covered)
    if missing:
        raise HTTPException(status_code=422, detail=f"以下林班没有有效林权档案覆盖：{', '.join(missing)}。")
    return rights


def require_application_scope(record: dict[str, Any], context: AuthContext) -> None:
    for link in record.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block:
            require_target_block_allowed(context, block)


def get_scoped_application(application_id: str, context: AuthContext, *, include_deleted: bool = False) -> dict[str, Any]:
    record = application_by_id(application_id, include_deleted=include_deleted)
    if not record:
        raise HTTPException(status_code=404, detail="采伐申请不存在。")
    require_application_scope(record, context)
    return record


def serialize_application(record: dict[str, Any]) -> dict[str, Any]:
    data = dict(record)
    attachments = linked_attachments("harvest_application", str(data.get("id") or ""))
    data["quotaCheck"] = dict(data.get("quotaCheck") or {})
    data["approval"] = dict(data.get("approval") or {})
    data["operation"] = dict(data.get("operation") or {})
    data["verification"] = dict(data.get("verification") or {})
    data["blocks"] = list(data.get("blocks") or [])
    data["rights"] = list(data.get("rights") or [])
    data["timeline"] = list(data.get("timeline") or [])
    data["attachments"] = attachments
    data["attachmentIds"] = [item["id"] for item in attachments]
    return data


def quota_check(record: dict[str, Any]) -> dict[str, Any]:
    quota = quota_by_id(str(record.get("quotaId") or ""))
    reasons: list[str] = []
    if not quota or quota.get("status") != "active":
        reasons.append("采伐配额不存在或已停用")
    else:
        work_year = datetime.fromisoformat(str(record["workStartAt"])).year
        if int(quota["quotaYear"]) != work_year:
            reasons.append("配额年度与计划作业年度不一致")
        block_codes = [str(item.get("code") or "") for item in record.get("blocks") or []]
        if quota.get("blockCode") and quota["blockCode"] not in block_codes:
            reasons.append("该配额不适用于所选林班")
        remaining_area = float(quota["quotaAreaMu"]) - float(quota["usedAreaMu"])
        remaining_quantity = float(quota["quotaQuantityTon"]) - float(quota["usedQuantityTon"])
        if float(record["requestedAreaMu"]) > remaining_area + 1e-8:
            reasons.append("剩余采伐面积配额不足")
        if float(quota["quotaQuantityTon"]) > 0 and float(record["requestedQuantityTon"]) > remaining_quantity + 1e-8:
            reasons.append("剩余采伐数量配额不足")
    return {
        "passed": not reasons,
        "checkedAt": utc_now(),
        "reasons": reasons,
        "quotaId": str(record.get("quotaId") or ""),
        "requestedAreaMu": float(record["requestedAreaMu"]),
        "requestedQuantityTon": float(record["requestedQuantityTon"]),
        "remainingAreaMu": max(0, float(quota["quotaAreaMu"]) - float(quota["usedAreaMu"])) if quota else 0,
        "remainingQuantityTon": max(0, float(quota["quotaQuantityTon"]) - float(quota["usedQuantityTon"])) if quota else 0,
    }


def run_quota_check(record: dict[str, Any], context: AuthContext) -> dict[str, Any]:
    result = quota_check(record)
    target = "approving" if result["passed"] else "quota_check"
    updated = {**record, "status": target, "quotaCheck": result}
    event = event_payload(
        "quota-check",
        str(record["status"]),
        target,
        context.user,
        "配额校验通过，进入审批。" if result["passed"] else "；".join(result["reasons"]),
        result,
    )
    return update_application(updated, event)


@router.get("/subjects")
def harvest_subjects(
    q: str = Query(default=""),
    subject_type: str = Query(default="", alias="subjectType"),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "operations.harvest.view")
    items = list_subjects(q, subject_type)
    return {"items": items, "total": len(items)}


@router.get("/quotas")
def harvest_quotas(
    year: int | None = Query(default=None),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "operations.harvest.view")
    items = list_quotas(year=year)
    return {"items": items, "total": len(items)}


@router.post("/quotas")
def add_harvest_quota(
    payload: HarvestQuotaCreate,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "operations.harvest.quota")
    if payload.blockCode:
        validated_blocks([payload.blockCode], context)
    return create_quota(payload.model_dump(), context.user)


@router.get("/applications")
def harvest_application_ledger(
    q: str = Query(default=""),
    status: str = Query(default=""),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "operations.harvest.view")
    records = list_applications(query=q, status=status, block_code=linked_block_code, include_deleted=include_deleted)
    scoped: list[dict[str, Any]] = []
    for record in records:
        try:
            require_application_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(serialize_application(record))
    return {"items": scoped[offset:offset + limit], "total": len(scoped), "limit": limit, "offset": offset}


@router.post("/applications")
def add_harvest_application(
    payload: HarvestApplicationCreate,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "operations.harvest.create")
    start, end = parse_schedule(payload.workStartAt, payload.workEndAt)
    harvest_type = validate_harvest_type(payload.harvestType)
    subject = subject_by_identity(payload.applicantType, payload.applicantId)
    if not subject:
        raise HTTPException(status_code=422, detail="经营主体不存在，请从正式主体台账选择。")
    blocks = validated_blocks(payload.linkedBlockCodes, context)
    block_codes = [str(block["blockCode"]) for block in blocks]
    rights = validated_rights(payload.linkedRightIds, block_codes, context)
    quota = quota_by_id(payload.quotaId)
    if not quota:
        raise HTTPException(status_code=422, detail="采伐配额不存在或已停用。")
    total_area = sum(float(block.get("areaMu") or 0) for block in blocks)
    if total_area > 0 and payload.requestedAreaMu > total_area + 1e-8:
        raise HTTPException(status_code=422, detail="申请采伐面积不能大于所选林班面积合计。")
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()),
        "applicationNo": application_number(),
        "name": payload.name.strip(),
        "applicantType": payload.applicantType,
        "applicantId": payload.applicantId,
        "applicantName": subject["name"],
        "status": "draft",
        "harvestType": harvest_type,
        "requestedAreaMu": payload.requestedAreaMu,
        "requestedQuantityTon": payload.requestedQuantityTon,
        "quotaId": payload.quotaId,
        "workStartAt": start,
        "workEndAt": end,
        "purpose": payload.purpose.strip(),
        "quotaCheck": {}, "approval": {}, "operation": {}, "verification": {},
        "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
        "blocks": [
            {"id": str(block["id"]), "code": str(block["blockCode"]), "declaredAreaMu": block.get("areaMu")}
            for block in blocks
        ],
        "rights": [
            {"id": str(right["id"]), "archiveCode": str(right["archiveCode"])}
            for right in rights
        ],
    }
    return serialize_application(create_application(record, event_payload("create", "", "draft", context.user, "采伐申请草稿已建立。")))


@router.get("/applications-export.csv")
def export_harvest_applications(
    q: str = Query(default=""),
    status: str = Query(default=""),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "operations.harvest.view")
    records = list_applications(query=q, status=status, block_code=linked_block_code)
    scoped: list[dict[str, Any]] = []
    for record in records:
        try:
            require_application_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(serialize_application(record))
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["申请编号", "申请名称", "申请主体", "采伐类型", "状态", "申请面积(亩)", "申请数量(吨)", "计划开始", "计划结束", "关联林班", "林权档案", "配额校验", "更新时间"])
    for item in scoped:
        writer.writerow([
            item["applicationNo"], item["name"], item["applicantName"], item["harvestType"], item["status"],
            item["requestedAreaMu"], item["requestedQuantityTon"], item["workStartAt"], item["workEndAt"],
            "、".join(link["code"] for link in item["blocks"]),
            "、".join(link["archiveCode"] for link in item["rights"]),
            "通过" if item["quotaCheck"].get("passed") else "未通过" if item["quotaCheck"].get("checkedAt") else "未校验",
            item["updatedAt"],
        ])
    return Response(
        content="\ufeff" + stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="harvest-applications.csv"'},
    )


@router.get("/applications/{application_id}")
def harvest_application_detail(
    application_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "operations.harvest.view")
    return serialize_application(get_scoped_application(application_id, context))


@router.patch("/applications/{application_id}")
def patch_harvest_application(
    application_id: str,
    payload: HarvestApplicationPatch,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "operations.harvest.create")
    record = get_scoped_application(application_id, context)
    if str(record.get("status") or "") != "draft":
        raise HTTPException(status_code=409, detail="只有草稿申请可以编辑，提交后请通过办理动作留痕。")
    changes = payload.model_dump(exclude_unset=True, mode="json")
    applicant_type = str(changes.get("applicantType", record["applicantType"]))
    applicant_id = str(changes.get("applicantId", record["applicantId"]))
    subject = subject_by_identity(applicant_type, applicant_id)
    if not subject:
        raise HTTPException(status_code=422, detail="经营主体不存在，请从正式主体台账选择。")
    block_codes = changes.get("linkedBlockCodes")
    if block_codes is None:
        block_codes = [str(item.get("code") or "") for item in record.get("blocks") or []]
    blocks = validated_blocks(block_codes, context)
    normalized_block_codes = [str(block["blockCode"]) for block in blocks]
    right_ids = changes.get("linkedRightIds")
    if right_ids is None:
        right_ids = [str(item.get("id") or "") for item in record.get("rights") or []]
    rights = validated_rights(right_ids, normalized_block_codes, context)
    start, end = parse_schedule(
        str(changes.get("workStartAt", record["workStartAt"])),
        str(changes.get("workEndAt", record["workEndAt"])),
    )
    requested_area = float(changes.get("requestedAreaMu", record["requestedAreaMu"]))
    total_area = sum(float(block.get("areaMu") or 0) for block in blocks)
    if total_area > 0 and requested_area > total_area + 1e-8:
        raise HTTPException(status_code=422, detail="申请采伐面积不能大于所选林班面积合计。")
    quota_id = str(changes.get("quotaId", record["quotaId"]))
    if not quota_by_id(quota_id):
        raise HTTPException(status_code=422, detail="采伐配额不存在或已停用。")
    updated = {
        **record,
        "name": str(changes.get("name", record["name"])).strip(),
        "applicantType": applicant_type,
        "applicantId": applicant_id,
        "applicantName": subject["name"],
        "harvestType": validate_harvest_type(str(changes.get("harvestType", record["harvestType"]))),
        "requestedAreaMu": requested_area,
        "requestedQuantityTon": float(changes.get("requestedQuantityTon", record["requestedQuantityTon"])),
        "quotaId": quota_id,
        "workStartAt": start,
        "workEndAt": end,
        "purpose": str(changes.get("purpose", record.get("purpose") or "")).strip(),
        "quotaCheck": {},
        "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"]), "declaredAreaMu": block.get("areaMu")} for block in blocks],
        "rights": [{"id": str(right["id"]), "archiveCode": str(right["archiveCode"])} for right in rights],
    }
    try:
        result = replace_draft_application(updated, event_payload("edit", "draft", "draft", context.user, "采伐申请草稿已修改。"))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_application(result)


@router.delete("/applications/{application_id}")
def delete_harvest_application(
    application_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "operations.harvest.manage")
    get_scoped_application(application_id, context)
    try:
        result = soft_delete_application(application_id, context.user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="采伐申请不存在。") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_application(result)


@router.post("/applications/{application_id}/restore")
def restore_harvest_application(
    application_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "operations.harvest.manage")
    record = get_scoped_application(application_id, context, include_deleted=True)
    if not record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="采伐申请未删除。")
    try:
        result = restore_application(application_id, context.user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="采伐申请不存在。") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_application(result)


@router.post("/applications/{application_id}/actions/{action}")
def apply_harvest_action(
    application_id: str,
    action: str,
    payload: HarvestAction,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    permission = {
        "submit": "operations.harvest.create", "recheck": "operations.harvest.create",
        "approve": "operations.harvest.approve", "return": "operations.harvest.approve",
        "start": "operations.harvest.operate", "record-alert": "operations.harvest.operate",
        "report-complete": "operations.harvest.operate", "verify": "operations.harvest.verify",
        "return-operation": "operations.harvest.verify",
    }.get(action)
    if not permission:
        raise HTTPException(status_code=404, detail="不支持的采伐业务操作。")
    require_permission(context, permission)
    record = get_scoped_application(application_id, context)
    status = str(record["status"])
    note = payload.note.strip()

    if action == "submit":
        if status != "draft":
            raise HTTPException(status_code=409, detail="只有草稿申请可以提交。")
        submitted = update_application(
            {**record, "status": "submitted"},
            event_payload("submit", "draft", "submitted", context.user, note or "申请已提交，开始自动校验配额。"),
        )
        return serialize_application(run_quota_check(submitted, context))
    if action == "recheck":
        if status != "quota_check":
            raise HTTPException(status_code=409, detail="当前申请不需要重新校验配额。")
        return serialize_application(run_quota_check(record, context))
    if action == "return":
        if status != "approving":
            raise HTTPException(status_code=409, detail="当前申请不在审批环节。")
        if not note:
            raise HTTPException(status_code=422, detail="退回申请时必须填写原因。")
        return serialize_application(update_application(
            {**record, "status": "draft", "approval": {"decision": "returned", "reviewedBy": context.user, "reviewedAt": utc_now(), "note": note}},
            event_payload("return", status, "draft", context.user, note),
        ))
    if action == "approve":
        if status != "approving":
            raise HTTPException(status_code=409, detail="当前申请不在审批环节。")
        approved = {**record, "status": "approved", "approval": {"decision": "approved", "reviewedBy": context.user, "reviewedAt": utc_now(), "note": note}}
        try:
            return serialize_application(reserve_quota_and_approve(approved, event_payload("approve", status, "approved", context.user, note or "审批通过并锁定配额。")))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    if action == "start":
        if status != "approved":
            raise HTTPException(status_code=409, detail="审批通过后才能开始采伐作业。")
        operation = {
            "startedAt": utc_now(), "startedBy": context.user,
            "workWindow": {"startAt": record["workStartAt"], "endAt": record["workEndAt"]},
            "geofence": {"mode": "forest-block-boundary", "blockCodes": [item["code"] for item in record["blocks"]]},
            "alerts": [],
        }
        return serialize_application(update_application({**record, "status": "operating", "operation": operation}, event_payload("start", status, "operating", context.user, note or "作业围栏和许可时间窗已启用。", operation)))
    if action == "record-alert":
        if status != "operating":
            raise HTTPException(status_code=409, detail="只有正在作业的申请可以记录安全告警。")
        if not payload.alertType.strip() or not payload.alertMessage.strip():
            raise HTTPException(status_code=422, detail="告警类型和告警说明不能为空。")
        now = utc_now()
        severity = {
            "info": "low", "notice": "low", "warning": "medium",
            "error": "high", "danger": "high", "emergency": "critical",
        }.get(payload.alertLevel.strip().lower(), payload.alertLevel.strip().lower())
        if severity not in {"low", "medium", "high", "critical"}:
            severity = "medium"
        safety_alert_id = str(uuid.uuid4())
        source_alert_type = payload.alertType.strip()
        normalized_alert_type = "geofence" if "geofence" in source_alert_type.lower() else source_alert_type
        safety_alert = create_safety_alert({
            "id": safety_alert_id,
            "alertNo": f"GJ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
            "title": "采伐作业越界告警" if normalized_alert_type == "geofence" else "采伐作业安全告警",
            "alertType": normalized_alert_type,
            "severity": severity,
            "status": "new",
            "sourceType": "harvest",
            "sourceRef": record["id"],
            "deviceCode": payload.deviceCode.strip(),
            "locationText": payload.locationText.strip(),
            "longitude": None,
            "latitude": None,
            "description": payload.alertMessage.strip(),
            "linkedBlockCodes": [item["code"] for item in record["blocks"]],
            "rawPayload": {
                "harvestApplicationNo": record["applicationNo"],
                "alertType": source_alert_type,
                "alertLevel": payload.alertLevel.strip(),
            },
            "review": {},
            "eventId": "",
            "occurredAt": now,
            "createdAt": now,
            "updatedAt": now,
        })
        alert = {
            "id": str(uuid.uuid4()), "type": payload.alertType.strip(), "level": payload.alertLevel.strip() or "warning",
            "message": payload.alertMessage.strip(), "locationText": payload.locationText.strip(),
            "deviceCode": payload.deviceCode.strip(), "reportedBy": context.user, "reportedAt": now,
            "safetyAlertId": safety_alert["id"], "safetyAlertNo": safety_alert["alertNo"],
        }
        operation = dict(record.get("operation") or {})
        operation["alerts"] = [*(operation.get("alerts") or []), alert]
        return serialize_application(update_application({**record, "operation": operation}, event_payload("record-alert", status, status, context.user, alert["message"], alert)))
    if action == "report-complete":
        if status != "operating":
            raise HTTPException(status_code=409, detail="当前申请不在作业环节。")
        actual_area = payload.actualAreaMu or float(record["requestedAreaMu"])
        actual_quantity = payload.actualQuantityTon if payload.actualQuantityTon is not None else float(record["requestedQuantityTon"])
        if actual_area > float(record["requestedAreaMu"]) + 1e-8:
            raise HTTPException(status_code=422, detail="实际采伐面积不能超过批准面积。")
        verification = {
            "reportedAt": utc_now(), "reportedBy": context.user,
            "actualAreaMu": actual_area, "actualQuantityTon": actual_quantity,
            "evidenceUrls": [str(item).strip() for item in payload.evidenceUrls if str(item).strip()],
            "attachmentIds": list(dict.fromkeys(payload.attachmentIds)),
            "workSummary": note,
        }
        if payload.attachmentIds:
            sync_attachment_links("harvest_application", application_id, payload.attachmentIds, context)
        return serialize_application(update_application({**record, "status": "verifying", "verification": verification}, event_payload("report-complete", status, "verifying", context.user, note or "作业结果已提交验收。", verification)))
    if action == "return-operation":
        if status != "verifying":
            raise HTTPException(status_code=409, detail="当前申请不在验收环节。")
        if not note:
            raise HTTPException(status_code=422, detail="退回作业时必须填写原因。")
        return serialize_application(update_application({**record, "status": "operating"}, event_payload("return-operation", status, "operating", context.user, note)))
    if action == "verify":
        if status != "verifying":
            raise HTTPException(status_code=409, detail="当前申请不在验收环节。")
        verification = {**dict(record.get("verification") or {}), "decision": "accepted", "verifiedBy": context.user, "verifiedAt": utc_now(), "note": note}
        version_ids: list[str] = []
        for link in record.get("blocks") or []:
            block = block_by_code(str(link["code"]))
            if block:
                version = record_block_version(block, "harvest-verified", context)
                version_ids.append(str(version["id"]))
        batch_no = batch_number()
        batch = {
            "id": str(uuid.uuid4()), "batchNo": batch_no, "traceCode": f"ZS-{batch_no}-{uuid.uuid4().hex[:6].upper()}",
            "actualAreaMu": float(verification.get("actualAreaMu") or record["requestedAreaMu"]),
            "actualQuantityTon": float(verification.get("actualQuantityTon") or record["requestedQuantityTon"]),
            "blockCodes": [item["code"] for item in record.get("blocks") or []], "resourceVersionIds": version_ids,
            "createdBy": context.user, "createdAt": utc_now(),
        }
        return serialize_application(update_application({**record, "status": "completed", "verification": verification}, event_payload("verify", status, "completed", context.user, note or "验收通过，采伐批次和资源版本已归档。", {"batchNo": batch_no, "resourceVersionIds": version_ids}), batch=batch))

    raise HTTPException(status_code=404, detail="不支持的采伐业务操作。")
