from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission
from server.modules.attachments import get_attachment, linked_attachments, sync_attachment_links
from server.modules.ai_findings import (
    create_finding,
    finding_by_id,
    list_findings,
    restore_finding,
    soft_delete_finding,
    timeline_entry,
    update_finding,
    utc_now,
)
from server.modules.auth import AuthContext, request_context
from server.modules.drone import mission_by_id
from server.modules.equipment import device_by_id
from server.modules.forest_blocks import block_by_code, require_target_block_allowed
from server.modules.safety_events import create_alert


router = APIRouter(prefix="/ai", tags=["v2-ai"])
FINDING_TYPES = {"pest", "fire", "disease", "illegal-cutting", "road-damage", "tree-fall", "other"}
FINDING_STATUSES = {"pending", "confirmed", "converted", "ignored"}
SEVERITIES = {"low", "medium", "high", "critical"}


class FindingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    findingType: str = "other"
    modelCode: str = Field(min_length=1, max_length=128)
    modelVersion: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0, le=1)
    sourceAssetUrl: str = Field(default="", max_length=2000)
    sourceAttachmentId: str = ""
    droneMissionId: str = ""
    deviceId: str = ""
    locationText: str = Field(default="", max_length=500)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    linkedBlockCodes: list[str] = Field(default_factory=list)
    occurredAt: str = ""
    result: dict[str, Any] = Field(default_factory=dict)


class FindingAction(BaseModel):
    note: str = Field(default="", max_length=2000)
    title: str = Field(default="", max_length=255)
    severity: str = ""


class FindingPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    findingType: str | None = None
    modelCode: str | None = Field(default=None, min_length=1, max_length=128)
    modelVersion: str | None = Field(default=None, min_length=1, max_length=64)
    confidence: float | None = Field(default=None, ge=0, le=1)
    sourceAssetUrl: str | None = Field(default=None, max_length=2000)
    sourceAttachmentId: str | None = None
    droneMissionId: str | None = None
    deviceId: str | None = None
    locationText: str | None = Field(default=None, max_length=500)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    linkedBlockCodes: list[str] | None = None
    occurredAt: str | None = None
    result: dict[str, Any] | None = None


def finding_number() -> str:
    return f"AI-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def alert_number() -> str:
    return f"GJ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def validate_enum(value: str, allowed: set[str], label: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise HTTPException(status_code=422, detail=f"不支持的{label}。")
    return normalized


def parse_timestamp(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="识别时间格式不正确。") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def compact(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def validated_blocks(codes: list[str], context: AuthContext) -> list[dict[str, Any]]:
    normalized = compact(codes)
    if not normalized:
        raise HTTPException(status_code=422, detail="AI 识别结果至少需要关联一个正式林班。")
    blocks: list[dict[str, Any]] = []
    for code in normalized:
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"林班 {code} 不存在或已删除。")
        require_target_block_allowed(context, block)
        blocks.append(block)
    return blocks


def require_finding_scope(record: dict[str, Any], context: AuthContext) -> None:
    for link in record.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block:
            require_target_block_allowed(context, block)


def get_finding(finding_id: str, context: AuthContext) -> dict[str, Any]:
    record = finding_by_id(finding_id, include_deleted=True)
    if not record:
        raise HTTPException(status_code=404, detail="AI 识别结果不存在。")
    require_finding_scope(record, context)
    return record


def finding_view(record: dict[str, Any]) -> dict[str, Any]:
    attachments = linked_attachments("ai_finding", str(record["id"]), "source")
    return {
        **record,
        "sourceAttachmentId": str(attachments[0]["id"]) if attachments else "",
        "sourceAttachments": attachments,
    }


def update_finding_view(record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    return finding_view(update_finding(record, event))


def mission_context(mission_id: str, context: AuthContext) -> dict[str, Any] | None:
    if not mission_id:
        return None
    mission = mission_by_id(mission_id)
    if not mission:
        raise HTTPException(status_code=422, detail="关联的无人机任务不存在或已删除。")
    for link in mission.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block:
            require_target_block_allowed(context, block)
    return mission


def device_context(device_id: str, context: AuthContext) -> dict[str, Any] | None:
    if not device_id:
        return None
    device = device_by_id(device_id)
    if not device:
        raise HTTPException(status_code=422, detail="关联的设备不存在或已删除。")
    for link in device.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block:
            require_target_block_allowed(context, block)
    return device


@router.get("/findings")
def finding_ledger(
    q: str = Query(default=""), status: str = Query(default=""),
    finding_type: str = Query(default="", alias="findingType"),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "ai.findings.view")
    if status:
        validate_enum(status, FINDING_STATUSES, "识别状态")
    if finding_type:
        validate_enum(finding_type, FINDING_TYPES, "识别类型")
    scoped: list[dict[str, Any]] = []
    for record in list_findings(q, status, finding_type, linked_block_code, include_deleted=include_deleted):
        try:
            require_finding_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(finding_view(record))
    return {"items": scoped[offset:offset + limit], "total": len(scoped), "limit": limit, "offset": offset}


@router.get("/findings-export.csv")
def export_findings(
    q: str = Query(default=""), status: str = Query(default=""),
    finding_type: str = Query(default="", alias="findingType"),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "ai.findings.view")
    rows = []
    for record in list_findings(q, status, finding_type, linked_block_code):
        try:
            require_finding_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        rows.append(record)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["识别编号", "标题", "类型", "状态", "模型", "版本", "置信度", "来源任务", "设备编号", "林班", "位置", "识别时间", "源资产", "更新时间"])
    for record in rows:
        writer.writerow([
            record["findingNo"], record["title"], record["findingType"], record["status"], record["modelCode"],
            record["modelVersion"], record["confidence"], record.get("droneMissionId") or "", record.get("deviceCode") or "",
            "、".join(str(item.get("code") or "") for item in record.get("blocks") or []), record.get("locationText") or "",
            record.get("occurredAt") or "", "、".join(item["originalName"] for item in linked_attachments("ai_finding", str(record["id"]), "source")) or record.get("sourceAssetUrl") or "", record.get("updatedAt") or "",
        ])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ai-findings.csv"'})


@router.post("/findings")
def ingest_finding(payload: FindingCreate, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.findings.ingest")
    source_attachment_id = payload.sourceAttachmentId.strip()
    source_attachment = get_attachment(source_attachment_id, context) if source_attachment_id else None
    source_asset_url = payload.sourceAssetUrl.strip() or str((source_attachment or {}).get("downloadUrl") or "")
    if not source_attachment and not source_asset_url:
        raise HTTPException(status_code=422, detail="请选择附件中心中的识别源资产。")
    mission = mission_context(payload.droneMissionId.strip(), context)
    resolved_device_id = payload.deviceId.strip() or str((mission or {}).get("droneDeviceId") or "")
    device = device_context(resolved_device_id, context)
    block_codes = compact(payload.linkedBlockCodes)
    if not block_codes and mission:
        block_codes = [str(link.get("code") or "") for link in mission.get("blocks") or []]
    if not block_codes and device:
        block_codes = [str(link.get("code") or "") for link in device.get("blocks") or []]
    blocks = validated_blocks(block_codes, context)
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), "findingNo": finding_number(), "title": payload.title.strip(),
        "findingType": validate_enum(payload.findingType, FINDING_TYPES, "识别类型"), "status": "pending",
        "modelCode": payload.modelCode.strip(), "modelVersion": payload.modelVersion.strip(),
        "confidence": payload.confidence, "sourceAssetUrl": source_asset_url,
        "droneMissionId": str((mission or {}).get("id") or ""), "deviceId": str((device or {}).get("id") or ""),
        "deviceCode": str((device or {}).get("deviceCode") or ""), "locationText": payload.locationText.strip(),
        "longitude": payload.longitude, "latitude": payload.latitude,
        "result": {**payload.result, "humanConfirmed": False}, "review": {}, "safetyAlertId": "",
        "occurredAt": parse_timestamp(payload.occurredAt), "createdBy": context.user,
        "createdAt": now, "updatedAt": now, "deletedAt": None,
        "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks],
    }
    created = create_finding(record, timeline_entry("ingest", "", "pending", context.user, "AI 识别结果已进入人工复核队列。", {"modelCode": record["modelCode"], "modelVersion": record["modelVersion"], "confidence": record["confidence"], "sourceAttachmentId": source_attachment_id}))
    if source_attachment_id:
        sync_attachment_links("ai_finding", str(created["id"]), [source_attachment_id], context, relation_type="source")
    return finding_view(created)


@router.get("/findings/{finding_id}")
def finding_detail(finding_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.findings.view")
    return finding_view(get_finding(finding_id, context))


@router.patch("/findings/{finding_id}")
def edit_finding(finding_id: str, payload: FindingPatch, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.findings.ingest")
    record = get_finding(finding_id, context)
    if record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="已删除识别结果不能编辑。")
    if record["status"] != "pending":
        raise HTTPException(status_code=409, detail="只有待复核识别结果可以编辑。")
    changes = payload.model_dump(exclude_unset=True)
    source_attachment_supplied = "sourceAttachmentId" in changes
    source_attachment_id = str(changes.pop("sourceAttachmentId", "") or "").strip()
    if source_attachment_supplied and source_attachment_id:
        source_attachment = get_attachment(source_attachment_id, context)
        changes["sourceAssetUrl"] = str(source_attachment.get("downloadUrl") or "")
    if "findingType" in changes:
        changes["findingType"] = validate_enum(changes["findingType"], FINDING_TYPES, "识别类型")
    mission = mission_context(str(changes.get("droneMissionId", record.get("droneMissionId") or "")).strip(), context)
    resolved_device_id = str(changes.get("deviceId", record.get("deviceId") or "")).strip() or str((mission or {}).get("droneDeviceId") or "")
    device = device_context(resolved_device_id, context)
    if "droneMissionId" in changes:
        changes["droneMissionId"] = str((mission or {}).get("id") or "")
    if "deviceId" in changes or "droneMissionId" in changes:
        changes["deviceId"] = str((device or {}).get("id") or "")
        changes["deviceCode"] = str((device or {}).get("deviceCode") or "")
    if "linkedBlockCodes" in changes:
        blocks = validated_blocks(changes.pop("linkedBlockCodes"), context)
        changes["blocks"] = [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks]
    if "occurredAt" in changes:
        changes["occurredAt"] = parse_timestamp(changes["occurredAt"] or "")
    if "result" in changes:
        changes["result"] = {**changes["result"], "humanConfirmed": False}
    updated = {**record, **changes}
    if source_attachment_supplied and not source_attachment_id and not str(updated.get("sourceAssetUrl") or "").strip():
        raise HTTPException(status_code=422, detail="识别结果必须保留一个源资产。")
    saved = update_finding(updated, timeline_entry("edit", "pending", "pending", context.user, "AI 识别结果已修改。"))
    if source_attachment_supplied:
        sync_attachment_links("ai_finding", finding_id, [source_attachment_id] if source_attachment_id else [], context, relation_type="source")
    return finding_view(saved)


@router.delete("/findings/{finding_id}")
def delete_finding(finding_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.findings.ingest")
    record = get_finding(finding_id, context)
    if record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="AI 识别结果已经在回收站中。")
    if record["status"] != "pending":
        raise HTTPException(status_code=409, detail="只有待复核识别结果可以删除。")
    soft_delete_finding(finding_id)
    return {"ok": True, "deleted": record["findingNo"]}


@router.post("/findings/{finding_id}/restore")
def restore_deleted_finding(finding_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.findings.ingest")
    record = get_finding(finding_id, context)
    if not record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="AI 识别结果未被删除。")
    if record["status"] != "pending":
        raise HTTPException(status_code=409, detail="已完成复核的识别结果不能从回收站恢复。")
    restore_finding(finding_id)
    return finding_view(finding_by_id(finding_id) or record)


@router.post("/findings/{finding_id}/actions/{action}")
def apply_finding_action(finding_id: str, action: str, payload: FindingAction, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.findings.review")
    record = get_finding(finding_id, context)
    if record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="已删除识别结果不能复核。")
    status = str(record["status"])
    note = payload.note.strip()
    if action == "confirm":
        if status != "pending":
            raise HTTPException(status_code=409, detail="只有待复核结果可以确认。")
        review = {"decision": "confirmed", "reviewedBy": context.user, "reviewedAt": utc_now(), "note": note}
        return update_finding_view({**record, "status": "confirmed", "review": review, "result": {**(record.get("result") or {}), "humanConfirmed": True}}, timeline_entry(action, status, "confirmed", context.user, note or "AI 识别结果已人工确认。", review))
    if action == "ignore":
        if status not in {"pending", "confirmed"}:
            raise HTTPException(status_code=409, detail="当前识别结果不能忽略。")
        if not note:
            raise HTTPException(status_code=422, detail="忽略识别结果时必须填写原因。")
        review = {"decision": "ignored", "reviewedBy": context.user, "reviewedAt": utc_now(), "note": note}
        return update_finding_view({**record, "status": "ignored", "review": review}, timeline_entry(action, status, "ignored", context.user, note, review))
    if action != "convert-alert":
        raise HTTPException(status_code=404, detail="不支持的 AI 识别结果操作。")
    if status not in {"pending", "confirmed"}:
        raise HTTPException(status_code=409, detail="当前识别结果已经处理。")
    severity = validate_enum(payload.severity or "medium", SEVERITIES, "告警等级")
    finding_type = str(record["findingType"])
    alert_type = {"fire": "fire", "pest": "pest", "disease": "pest", "illegal-cutting": "theft"}.get(finding_type, "other")
    now = utc_now()
    alert = create_alert({
        "id": str(uuid.uuid4()), "alertNo": alert_number(), "title": payload.title.strip() or record["title"],
        "alertType": alert_type, "severity": severity, "status": "new", "sourceType": "ai",
        "sourceRef": record["id"], "deviceCode": record.get("deviceCode") or "",
        "locationText": record.get("locationText") or "", "longitude": record.get("longitude"),
        "latitude": record.get("latitude"), "description": note or f"AI 模型 {record['modelCode']} {record['modelVersion']} 识别结果，待安全事件中心复核。",
        "linkedBlockCodes": [str(link.get("code") or "") for link in record.get("blocks") or []],
        "rawPayload": {
            "findingId": record["id"], "findingNo": record["findingNo"], "findingType": finding_type,
            "modelCode": record["modelCode"], "modelVersion": record["modelVersion"],
            "confidence": record["confidence"], "sourceAssetUrl": record["sourceAssetUrl"],
            "sourceAttachmentId": finding_view(record)["sourceAttachmentId"],
            "droneMissionId": record.get("droneMissionId") or "", "result": record.get("result") or {},
        },
        "review": {}, "eventId": "", "occurredAt": record["occurredAt"], "createdAt": now, "updatedAt": now,
    })
    review = {"decision": "converted", "reviewedBy": context.user, "reviewedAt": now, "note": note, "safetyAlertId": alert["id"]}
    finding = update_finding_view({**record, "status": "converted", "review": review, "safetyAlertId": alert["id"]}, timeline_entry(action, status, "converted", context.user, note or "AI 识别结果已转为正式安全告警。", {"safetyAlertId": alert["id"], "alertNo": alert["alertNo"]}))
    return {"finding": finding, "alert": alert}
