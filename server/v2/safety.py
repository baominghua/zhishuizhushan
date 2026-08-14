from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.equipment import device_by_code
from server.modules.forest_blocks import block_by_code, require_target_block_allowed
from server.modules.safety_events import (
    alert_by_id,
    create_alert,
    create_event,
    event_by_id,
    list_alerts,
    list_events,
    set_event_deleted,
    timeline_entry,
    update_alert,
    update_event,
    utc_now,
)


router = APIRouter(prefix="/safety", tags=["v2-safety"])
EVENT_STATUSES = {"new", "triaged", "assigned", "handling", "resolved", "verified", "closed"}
EVENT_TYPES = {"fire", "pest", "theft", "geofence", "sos", "equipment", "weather", "other"}
SEVERITIES = {"low", "medium", "high", "critical"}
ALERT_STATUSES = {"new", "converted", "merged", "ignored"}
SOURCE_TYPES = {"manual", "device", "patrol", "harvest", "ai", "system", "alert"}
OPEN_EVENT_STATUSES = EVENT_STATUSES - {"closed"}


class SafetyEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    eventType: str = "other"
    severity: str = "medium"
    sourceType: str = "manual"
    sourceRef: str = Field(default="", max_length=128)
    locationText: str = Field(default="", max_length=500)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    description: str = Field(default="", max_length=5000)
    linkedBlockCodes: list[str] = Field(min_length=1)


class SafetyAlertCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    alertType: str = Field(min_length=1, max_length=64)
    severity: str = "medium"
    sourceType: str = "device"
    sourceRef: str = Field(default="", max_length=128)
    deviceCode: str = Field(default="", max_length=128)
    locationText: str = Field(default="", max_length=500)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    description: str = Field(default="", max_length=5000)
    linkedBlockCodes: list[str] = Field(default_factory=list)
    occurredAt: str = ""
    rawPayload: dict[str, Any] = Field(default_factory=dict)


class SafetyAction(BaseModel):
    note: str = Field(default="", max_length=2000)
    title: str = Field(default="", max_length=255)
    eventType: str = ""
    severity: str = ""
    responsibilityUnit: str = Field(default="", max_length=255)
    assigneeName: str = Field(default="", max_length=128)
    deadlineAt: str = ""
    resolutionSummary: str = Field(default="", max_length=5000)
    evidenceUrls: list[str] = Field(default_factory=list)
    eventId: str = ""
    linkedBlockCodes: list[str] = Field(default_factory=list)


def event_number() -> str:
    return f"SJ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def alert_number() -> str:
    return f"GJ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def validate_enum(value: str, allowed: set[str], label: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise HTTPException(status_code=422, detail=f"不支持的{label}。")
    return normalized


def parse_timestamp(value: str, label: str, *, required: bool = False) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        if required:
            raise HTTPException(status_code=422, detail=f"{label}不能为空。")
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{label}格式不正确。") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def validated_blocks(codes: list[str], context: AuthContext, *, required: bool = True) -> list[dict[str, Any]]:
    normalized = list(dict.fromkeys(str(code).strip() for code in codes if str(code).strip()))
    if required and not normalized:
        raise HTTPException(status_code=422, detail="安全事件至少需要关联一个正式林班。")
    blocks: list[dict[str, Any]] = []
    for code in normalized:
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"林班 {code} 不存在或已删除。")
        require_target_block_allowed(context, block)
        blocks.append(block)
    return blocks


def require_event_scope(record: dict[str, Any], context: AuthContext) -> None:
    for link in record.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block:
            require_target_block_allowed(context, block)


def require_alert_scope(record: dict[str, Any], context: AuthContext) -> None:
    for code in record.get("linkedBlockCodes") or []:
        block = block_by_code(str(code))
        if block:
            require_target_block_allowed(context, block)


def get_scoped_event(event_id: str, context: AuthContext, *, include_deleted: bool = False) -> dict[str, Any]:
    record = event_by_id(event_id, include_deleted=include_deleted)
    if not record:
        raise HTTPException(status_code=404, detail="安全事件不存在。")
    require_event_scope(record, context)
    return record


def csv_response(filename: str, headers: list[str], rows: list[list[Any]]) -> Response:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        content="\ufeff" + stream.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def get_scoped_alert(alert_id: str, context: AuthContext) -> dict[str, Any]:
    record = alert_by_id(alert_id)
    if not record:
        raise HTTPException(status_code=404, detail="安全告警不存在。")
    require_alert_scope(record, context)
    return record


def build_event_record(
    payload: dict[str, Any],
    blocks: list[dict[str, Any]],
    actor: str,
    *,
    source_type: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "id": str(uuid.uuid4()),
        "incidentNo": event_number(),
        "title": str(payload["title"]).strip(),
        "eventType": validate_enum(str(payload.get("eventType") or "other"), EVENT_TYPES, "事件类型"),
        "severity": validate_enum(str(payload.get("severity") or "medium"), SEVERITIES, "事件等级"),
        "status": "new",
        "sourceType": validate_enum(source_type or str(payload.get("sourceType") or "manual"), SOURCE_TYPES, "事件来源"),
        "sourceRef": source_ref if source_ref is not None else str(payload.get("sourceRef") or "").strip(),
        "locationText": str(payload.get("locationText") or "").strip(),
        "longitude": payload.get("longitude"),
        "latitude": payload.get("latitude"),
        "responsibilityUnit": "",
        "assigneeName": "",
        "deadlineAt": None,
        "description": str(payload.get("description") or "").strip(),
        "resolution": {},
        "review": {},
        "version": 1,
        "createdBy": actor,
        "createdAt": now,
        "updatedAt": now,
        "closedAt": None,
        "deletedAt": None,
        "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks],
    }


@router.get("/events")
def safety_event_ledger(
    q: str = Query(default=""),
    status: str = Query(default=""),
    severity: str = Query(default=""),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    overdue_only: bool = Query(default=False, alias="overdueOnly"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "safety.events.view")
    if status:
        validate_enum(status, EVENT_STATUSES, "事件状态")
    if severity:
        validate_enum(severity, SEVERITIES, "事件等级")
    records = list_events(query=q, status=status, severity=severity, block_code=linked_block_code, overdue_only=overdue_only, include_deleted=include_deleted)
    scoped: list[dict[str, Any]] = []
    for record in records:
        try:
            require_event_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(record)
    return {"items": scoped[offset:offset + limit], "total": len(scoped), "limit": limit, "offset": offset}


@router.post("/events")
def add_safety_event(
    payload: SafetyEventCreate,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "safety.events.create")
    blocks = validated_blocks(payload.linkedBlockCodes, context)
    record = build_event_record(payload.model_dump(), blocks, context.user)
    return create_event(record, timeline_entry("report", "", "new", context.user, "安全事件已上报。"))


@router.get("/events-export.csv")
def export_safety_events(
    q: str = Query(default=""), status: str = Query(default=""), severity: str = Query(default=""),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "safety.events.view")
    records = list_events(query=q, status=status, severity=severity, block_code=linked_block_code)
    scoped = []
    for record in records:
        try:
            require_event_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(record)
    return csv_response(
        "safety-events.csv",
        ["事件编号", "标题", "类型", "等级", "状态", "来源", "位置", "责任单位", "负责人", "截止时间", "关联林班", "更新时间"],
        [[item["incidentNo"], item["title"], item["eventType"], item["severity"], item["status"], item["sourceType"],
          item.get("locationText") or "", item.get("responsibilityUnit") or "", item.get("assigneeName") or "",
          item.get("deadlineAt") or "", "、".join(block["code"] for block in item.get("blocks") or []), item["updatedAt"]]
         for item in scoped],
    )


@router.get("/events/{event_id}")
def safety_event_detail(
    event_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "safety.events.view")
    return get_scoped_event(event_id, context)


@router.patch("/events/{event_id}")
def edit_safety_event(event_id: str, payload: SafetyEventCreate, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "safety.events.create")
    record = get_scoped_event(event_id, context)
    if record.get("status") != "new":
        raise HTTPException(status_code=409, detail="只有未分级的安全事件可以编辑。")
    blocks = validated_blocks(payload.linkedBlockCodes, context)
    updated = {
        **record, "title": payload.title.strip(),
        "eventType": validate_enum(payload.eventType, EVENT_TYPES, "事件类型"),
        "severity": validate_enum(payload.severity, SEVERITIES, "事件等级"),
        "sourceType": validate_enum(payload.sourceType, SOURCE_TYPES, "事件来源"),
        "sourceRef": payload.sourceRef.strip(), "locationText": payload.locationText.strip(),
        "longitude": payload.longitude, "latitude": payload.latitude, "description": payload.description.strip(),
        "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks],
    }
    return update_event(updated, timeline_entry("edit", "new", "new", context.user, "安全事件上报信息已修改。"))


@router.delete("/events/{event_id}")
def delete_safety_event(event_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "safety.events.create")
    get_scoped_event(event_id, context)
    try:
        return set_event_deleted(event_id, deleted=True, actor=context.user)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/events/{event_id}/restore")
def restore_safety_event(event_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "safety.events.create")
    get_scoped_event(event_id, context, include_deleted=True)
    try:
        return set_event_deleted(event_id, deleted=False, actor=context.user)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/events/{event_id}/actions/{action}")
def apply_safety_event_action(
    event_id: str,
    action: str,
    payload: SafetyAction,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    permission = {
        "triage": "safety.events.triage",
        "assign": "safety.events.assign",
        "accept": "safety.events.handle",
        "progress": "safety.events.handle",
        "resolve": "safety.events.handle",
        "return": "safety.events.verify",
        "verify": "safety.events.verify",
        "close": "safety.events.verify",
        "escalate": "safety.events.command",
        "reopen": "safety.events.command",
    }.get(action)
    if not permission:
        raise HTTPException(status_code=404, detail="不支持的安全事件操作。")
    require_permission(context, permission)
    record = get_scoped_event(event_id, context)
    status = str(record["status"])
    note = payload.note.strip()

    if action == "triage":
        if status not in {"new", "triaged"}:
            raise HTTPException(status_code=409, detail="只有新上报事件可以进行分级。")
        event_type = validate_enum(payload.eventType or str(record["eventType"]), EVENT_TYPES, "事件类型")
        severity = validate_enum(payload.severity or str(record["severity"]), SEVERITIES, "事件等级")
        unit = payload.responsibilityUnit.strip()
        if not unit:
            raise HTTPException(status_code=422, detail="分级时必须明确责任单位。")
        data = {"eventType": event_type, "severity": severity, "responsibilityUnit": unit}
        return update_event(
            {**record, "status": "triaged", "eventType": event_type, "severity": severity, "responsibilityUnit": unit},
            timeline_entry("triage", status, "triaged", context.user, note or "事件类型、等级和责任单位已确认。", data),
        )
    if action == "assign":
        if status != "triaged":
            raise HTTPException(status_code=409, detail="事件完成分级后才能派单。")
        assignee = payload.assigneeName.strip()
        if not assignee:
            raise HTTPException(status_code=422, detail="派单时必须填写责任人。")
        deadline = parse_timestamp(payload.deadlineAt, "办理时限", required=True)
        data = {"assigneeName": assignee, "deadlineAt": deadline}
        return update_event(
            {**record, "status": "assigned", "assigneeName": assignee, "deadlineAt": deadline},
            timeline_entry("assign", status, "assigned", context.user, note or f"事件已派给 {assignee}。", data),
        )
    if action == "accept":
        if status != "assigned":
            raise HTTPException(status_code=409, detail="只有已派单事件可以接单处置。")
        return update_event(
            {**record, "status": "handling"},
            timeline_entry("accept", status, "handling", context.user, note or "责任人已接单，开始处置。"),
        )
    if action == "progress":
        if status != "handling":
            raise HTTPException(status_code=409, detail="当前事件不在处置中。")
        if not note:
            raise HTTPException(status_code=422, detail="请填写处置进展。")
        return update_event(record, timeline_entry("progress", status, status, context.user, note))
    if action == "resolve":
        if status != "handling":
            raise HTTPException(status_code=409, detail="当前事件不在处置中。")
        summary = payload.resolutionSummary.strip() or note
        evidence = [str(item).strip() for item in payload.evidenceUrls if str(item).strip()]
        if not summary:
            raise HTTPException(status_code=422, detail="提交处置结果时必须填写结果说明。")
        resolution = {"summary": summary, "evidenceUrls": evidence, "resolvedBy": context.user, "resolvedAt": utc_now()}
        return update_event(
            {**record, "status": "resolved", "resolution": resolution},
            timeline_entry("resolve", status, "resolved", context.user, summary, resolution),
        )
    if action == "return":
        if status != "resolved":
            raise HTTPException(status_code=409, detail="当前事件不在复核环节。")
        if not note:
            raise HTTPException(status_code=422, detail="退回处置时必须填写原因。")
        review = {"decision": "returned", "reviewedBy": context.user, "reviewedAt": utc_now(), "note": note}
        return update_event(
            {**record, "status": "handling", "review": review},
            timeline_entry("return", status, "handling", context.user, note, review),
        )
    if action == "verify":
        if status != "resolved":
            raise HTTPException(status_code=409, detail="处置结果提交后才能复核。")
        review = {"decision": "verified", "reviewedBy": context.user, "reviewedAt": utc_now(), "note": note}
        return update_event(
            {**record, "status": "verified", "review": review},
            timeline_entry("verify", status, "verified", context.user, note or "处置结果复核通过。", review),
        )
    if action == "close":
        if status != "verified":
            raise HTTPException(status_code=409, detail="复核通过后才能关闭事件。")
        closed_at = utc_now()
        return update_event(
            {**record, "status": "closed", "closedAt": closed_at},
            timeline_entry("close", status, "closed", context.user, note or "事件已关闭并归档。", {"closedAt": closed_at}),
        )
    if action == "reopen":
        if status != "closed":
            raise HTTPException(status_code=409, detail="只有已关闭事件可以重新打开。")
        if not note:
            raise HTTPException(status_code=422, detail="重新打开时必须填写原因。")
        return update_event(
            {**record, "status": "triaged", "closedAt": None, "assigneeName": "", "deadlineAt": None},
            timeline_entry("reopen", status, "triaged", context.user, note),
        )
    if action == "escalate":
        if status not in {"triaged", "assigned", "handling"}:
            raise HTTPException(status_code=409, detail="当前状态不能升级事件。")
        severity = validate_enum(payload.severity, SEVERITIES, "事件等级")
        rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        if rank[severity] <= rank[str(record["severity"])]:
            raise HTTPException(status_code=422, detail="升级后的等级必须高于当前等级。")
        if not note:
            raise HTTPException(status_code=422, detail="升级事件时必须填写原因。")
        return update_event(
            {**record, "severity": severity},
            timeline_entry("escalate", status, status, context.user, note, {"severity": severity}),
        )
    raise HTTPException(status_code=404, detail="不支持的安全事件操作。")


@router.get("/alerts")
def safety_alert_ledger(
    q: str = Query(default=""),
    status: str = Query(default=""),
    severity: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "safety.alerts.view")
    if status:
        validate_enum(status, ALERT_STATUSES, "告警状态")
    if severity:
        validate_enum(severity, SEVERITIES, "告警等级")
    records = list_alerts(query=q, status=status, severity=severity)
    scoped: list[dict[str, Any]] = []
    for record in records:
        try:
            require_alert_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(record)
    return {"items": scoped[offset:offset + limit], "total": len(scoped), "limit": limit, "offset": offset}


@router.post("/alerts")
def ingest_safety_alert(
    payload: SafetyAlertCreate,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "safety.alerts.ingest")
    severity = validate_enum(payload.severity, SEVERITIES, "告警等级")
    source_type = validate_enum(payload.sourceType, SOURCE_TYPES - {"manual", "alert"}, "告警来源")
    source_device = None
    if source_type == "device":
        if not payload.deviceCode.strip():
            raise HTTPException(status_code=422, detail="设备来源告警必须选择设备台账记录。")
        source_device = device_by_code(payload.deviceCode)
        if not source_device:
            raise HTTPException(status_code=422, detail="来源设备不存在、已删除或未纳入设备台账。")
        for link in source_device.get("blocks") or []:
            block = block_by_code(str(link.get("code") or ""))
            if block:
                require_target_block_allowed(context, block)
    linked_codes = payload.linkedBlockCodes
    if source_device and not linked_codes:
        linked_codes = [str(link.get("code") or "") for link in source_device.get("blocks") or []]
    blocks = validated_blocks(linked_codes, context, required=False)
    now = utc_now()
    occurred_at = parse_timestamp(payload.occurredAt, "告警发生时间") or now
    record = {
        "id": str(uuid.uuid4()), "alertNo": alert_number(), "title": payload.title.strip(),
        "alertType": payload.alertType.strip(), "severity": severity, "status": "new",
        "sourceType": source_type, "sourceRef": payload.sourceRef.strip(),
        "deviceCode": str(source_device["deviceCode"]) if source_device else payload.deviceCode.strip(),
        "locationText": payload.locationText.strip() or (str(source_device.get("locationText") or "") if source_device else ""),
        "longitude": payload.longitude if payload.longitude is not None else (source_device.get("longitude") if source_device else None),
        "latitude": payload.latitude if payload.latitude is not None else (source_device.get("latitude") if source_device else None),
        "description": payload.description.strip(), "linkedBlockCodes": [str(block["blockCode"]) for block in blocks],
        "rawPayload": payload.rawPayload, "review": {}, "eventId": "", "occurredAt": occurred_at,
        "createdAt": now, "updatedAt": now,
    }
    return create_alert(record)


@router.post("/alerts/{alert_id}/actions/{action}")
def apply_safety_alert_action(
    alert_id: str,
    action: str,
    payload: SafetyAction,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "safety.alerts.review")
    alert = get_scoped_alert(alert_id, context)
    if alert["status"] != "new":
        raise HTTPException(status_code=409, detail="该告警已经处理。")
    if action == "ignore":
        if not payload.note.strip():
            raise HTTPException(status_code=422, detail="忽略告警时必须填写原因。")
        review = {"decision": "ignored", "reviewedBy": context.user, "reviewedAt": utc_now(), "note": payload.note.strip()}
        return update_alert(alert_id, status="ignored", review=review)
    if action == "merge":
        event = get_scoped_event(payload.eventId, context)
        if event["status"] not in OPEN_EVENT_STATUSES:
            raise HTTPException(status_code=409, detail="只能合并到未关闭事件。")
        updated = update_event(
            event,
            timeline_entry("merge-alert", event["status"], event["status"], context.user, payload.note or f"合并告警 {alert['alertNo']}。", {"alertId": alert_id, "alertNo": alert["alertNo"]}),
        )
        review = {"decision": "merged", "reviewedBy": context.user, "reviewedAt": utc_now(), "note": payload.note.strip() or f"合并到事件 {updated['incidentNo']}。"}
        update_alert(alert_id, status="merged", event_id=updated["id"], review=review)
        return {"alert": alert_by_id(alert_id), "event": updated}
    if action == "convert":
        block_codes = payload.linkedBlockCodes or list(alert.get("linkedBlockCodes") or [])
        blocks = validated_blocks(block_codes, context)
        event_payload = {
            "title": payload.title.strip() or alert["title"],
            "eventType": payload.eventType.strip() or (alert["alertType"] if alert["alertType"] in EVENT_TYPES else "other"),
            "severity": payload.severity.strip() or alert["severity"],
            "locationText": alert.get("locationText") or "",
            "longitude": alert.get("longitude"), "latitude": alert.get("latitude"),
            "description": alert.get("description") or alert["title"],
        }
        record = build_event_record(event_payload, blocks, context.user, source_type="alert", source_ref=alert_id)
        event = create_event(
            record,
            timeline_entry("convert-alert", "", "new", context.user, payload.note or f"告警 {alert['alertNo']} 已确认并转为事件。", {"alertId": alert_id, "alertNo": alert["alertNo"]}),
        )
        review = {"decision": "converted", "reviewedBy": context.user, "reviewedAt": utc_now(), "note": payload.note.strip() or "告警已确认并转为事件。"}
        update_alert(alert_id, status="converted", event_id=event["id"], review=review)
        return {"alert": alert_by_id(alert_id), "event": event}
    raise HTTPException(status_code=404, detail="不支持的安全告警操作。")
