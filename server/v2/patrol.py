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
from server.modules.business import (
    ManagedFilters,
    ManagedRecordIn,
    ManagedRecordPatch,
    create_business_record,
    delete_business_record,
    get_business_record,
    list_business_records,
    patch_business_record,
    permission_for_business_module,
    restore_business_record,
)
from server.modules.forest_blocks import (
    block_by_code,
    require_target_block_allowed,
)


router = APIRouter(prefix="/patrol", tags=["v2-patrol"])
MODULE_KEY = "maintenance-tasks"
TRANSITIONS = {
    "assign": ({"planned"}, "assigned", "任务已派发"),
    "accept": ({"assigned"}, "accepted", "责任人已接单"),
    "start": ({"accepted"}, "patrolling", "开始现场巡护"),
    "report": ({"patrolling"}, "reported", "现场结果已上报"),
    "resolve": ({"reported"}, "resolved", "问题处置已完成"),
    "verify": ({"reported", "resolved"}, "verified", "巡护结果已复核"),
    "return": ({"reported", "resolved"}, "patrolling", "退回继续巡护"),
    "close": ({"verified"}, "closed", "任务已归档"),
}


class PatrolTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    priority: str = "normal"
    plannedStartAt: str
    plannedEndAt: str
    assigneeName: str = ""
    linkedBlockCodes: list[str] = Field(min_length=1)
    instructions: str = ""


class PatrolTaskPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    priority: str | None = None
    plannedStartAt: str | None = None
    plannedEndAt: str | None = None
    assigneeName: str | None = None
    linkedBlockCodes: list[str] | None = None
    instructions: str | None = None


class PatrolAction(BaseModel):
    assigneeName: str = ""
    note: str = ""
    summary: str = ""
    issueType: str = ""
    issueLevel: str = ""
    locationText: str = ""
    attachmentIds: list[str] = Field(default_factory=list)
    dispositionSummary: str = ""
    dispositionResult: str = ""
    trackPoints: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    distanceKm: float | None = Field(default=None, ge=0, le=10000)
    durationSeconds: int | None = Field(default=None, ge=0, le=604800)
    clientOperationId: str = Field(default="", max_length=128)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def patrol_number() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"XH-{today}-{uuid.uuid4().hex[:6].upper()}"


def validate_schedule(start: str, end: str) -> tuple[str, str]:
    try:
        start_at = datetime.fromisoformat(start)
        end_at = datetime.fromisoformat(end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="计划时间格式不正确。") from exc
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="计划结束时间必须晚于开始时间。")
    return start_at.isoformat(), end_at.isoformat()


def validate_priority(value: str) -> str:
    priority = str(value or "normal").strip()
    if priority not in {"low", "normal", "high", "urgent"}:
        raise HTTPException(status_code=422, detail="不支持的任务优先级。")
    return priority


def validate_blocks(codes: list[str], context: AuthContext) -> list[str]:
    normalized = list(dict.fromkeys(str(code).strip() for code in codes if str(code).strip()))
    if not normalized:
        raise HTTPException(status_code=422, detail="巡护任务至少需要关联一个林班。")
    for code in normalized:
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"林班 {code} 不存在或已删除。")
        require_target_block_allowed(context, block)
    return normalized


def timeline_entry(action: str, label: str, status: str, context: AuthContext, note: str = "") -> dict[str, str]:
    return {
        "id": str(uuid.uuid4()),
        "action": action,
        "label": label,
        "status": status,
        "actor": context.user,
        "at": now_iso(),
        "note": str(note or "").strip(),
    }


def serialize_task(record: Any) -> dict[str, Any]:
    data = record.model_dump(mode="json") if hasattr(record, "model_dump") else dict(record)
    properties = dict(data.get("properties") or {})
    task_id = str(data.get("id") or "")
    attachments = linked_attachments("patrol_task", task_id) if task_id else []
    return {
        "id": data.get("id"),
        "patrolNo": data.get("recordCode"),
        "name": data.get("name"),
        "status": data.get("status"),
        "priority": properties.get("priority") or "normal",
        "plannedStartAt": properties.get("plannedStartAt") or "",
        "plannedEndAt": properties.get("plannedEndAt") or "",
        "assigneeName": properties.get("assigneeName") or "",
        "instructions": properties.get("instructions") or "",
        "linkedBlockCodes": list(data.get("linkedBlockCodes") or []),
        "report": dict(properties.get("report") or {}),
        "disposition": dict(properties.get("disposition") or {}),
        "attachments": attachments,
        "attachmentIds": [item["id"] for item in attachments],
        "timeline": list(properties.get("timeline") or []),
        "deletedAt": data.get("deletedAt"),
        "createdAt": data.get("createdAt"),
        "updatedAt": data.get("updatedAt"),
    }


@router.get("/tasks")
def list_patrol_tasks(
    q: str = Query(default=""),
    status: str = Query(default=""),
    linkedBlockCode: str = Query(default=""),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    result = list_business_records(
        MODULE_KEY,
        ManagedFilters(
            q=q,
            status=status,
            linkedBlockCode=linkedBlockCode,
            includeDeleted=includeDeleted,
            limit=limit,
            offset=offset,
        ),
        context,
    )
    return {
        "items": [serialize_task(item) for item in result["items"]],
        "total": result["total"],
        "limit": result["limit"],
        "offset": result["offset"],
    }


@router.post("/tasks")
def create_patrol_task(
    payload: PatrolTaskCreate,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    start, end = validate_schedule(payload.plannedStartAt, payload.plannedEndAt)
    blocks = validate_blocks(payload.linkedBlockCodes, context)
    priority = validate_priority(payload.priority)
    status = "assigned" if payload.assigneeName.strip() else "planned"
    label = "任务已建立并派发" if status == "assigned" else "巡护计划已建立"
    properties = {
        "taskType": "patrol",
        "priority": priority,
        "plannedStartAt": start,
        "plannedEndAt": end,
        "closureStatus": "pending",
        "assigneeName": payload.assigneeName.strip(),
        "instructions": payload.instructions.strip(),
        "report": {},
        "timeline": [timeline_entry("create", label, status, context)],
    }
    created = create_business_record(
        MODULE_KEY,
        ManagedRecordIn.model_validate(
            {
                "recordCode": patrol_number(),
                "name": payload.name.strip(),
                "status": status,
                "linkedBlockCodes": blocks,
                "properties": properties,
                "formVersion": 1,
            }
        ),
        context,
    )
    return serialize_task(created)


@router.get("/tasks/{task_id}")
def get_patrol_task(
    task_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    return serialize_task(get_business_record(MODULE_KEY, task_id, context))


@router.patch("/tasks/{task_id}")
def patch_patrol_task(
    task_id: str,
    payload: PatrolTaskPatch,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    record = get_business_record(MODULE_KEY, task_id, context)
    current = str(record.status or "planned")
    if current not in {"planned", "assigned"}:
        raise HTTPException(status_code=409, detail="任务接单后不能修改计划信息，请通过办理动作留痕。")
    changes = payload.model_dump(exclude_unset=True, mode="json")
    properties = dict(record.properties or {})
    name = changes.pop("name", None)
    linked_codes = changes.pop("linkedBlockCodes", None)
    priority = changes.pop("priority", None)
    planned_start = changes.pop("plannedStartAt", None)
    planned_end = changes.pop("plannedEndAt", None)
    if priority is not None:
        properties["priority"] = validate_priority(priority)
    if planned_start is not None or planned_end is not None:
        start, end = validate_schedule(
            planned_start or str(properties.get("plannedStartAt") or ""),
            planned_end or str(properties.get("plannedEndAt") or ""),
        )
        properties["plannedStartAt"] = start
        properties["plannedEndAt"] = end
    for key in ("assigneeName", "instructions"):
        if key in changes:
            properties[key] = str(changes[key] or "").strip()
    next_status = "assigned" if str(properties.get("assigneeName") or "").strip() else "planned"
    timeline = list(properties.get("timeline") or [])
    timeline.append(timeline_entry("edit", "任务计划已修改", next_status, context))
    properties["timeline"] = timeline
    updated = patch_business_record(
        MODULE_KEY,
        task_id,
        ManagedRecordPatch(
            name=str(name).strip() if name is not None else None,
            status=next_status,
            linkedBlockCodes=validate_blocks(linked_codes, context) if linked_codes is not None else None,
            properties=properties,
        ),
        context,
    )
    return serialize_task(updated)


@router.delete("/tasks/{task_id}")
def delete_patrol_task(
    task_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    record = get_business_record(MODULE_KEY, task_id, context)
    if str(record.status or "planned") not in {"planned", "assigned"}:
        raise HTTPException(status_code=409, detail="任务接单后不能删除，请先完成或保留业务留痕。")
    return delete_business_record(MODULE_KEY, task_id, context)


@router.post("/tasks/{task_id}/restore")
def restore_patrol_task(
    task_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    result = restore_business_record(MODULE_KEY, task_id, context)
    return serialize_task(result["item"])


@router.get("/tasks-export.csv")
def export_patrol_tasks(
    q: str = Query(default=""),
    status: str = Query(default=""),
    linkedBlockCode: str = Query(default=""),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, permission_for_business_module(MODULE_KEY, "export"))
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list_business_records(
            MODULE_KEY,
            ManagedFilters(q=q, status=status, linkedBlockCode=linkedBlockCode, limit=1000, offset=offset),
            context,
        )
        rows.extend(serialize_task(item) for item in page["items"])
        offset += len(page["items"])
        if offset >= page["total"] or not page["items"]:
            break
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["任务编号", "任务名称", "状态", "优先级", "责任人", "计划开始", "计划结束", "关联林班", "巡护结论", "问题类型", "处置结果", "更新时间"])
    for item in rows:
        writer.writerow([
            item["patrolNo"], item["name"], item["status"], item["priority"], item["assigneeName"],
            item["plannedStartAt"], item["plannedEndAt"], "、".join(item["linkedBlockCodes"]),
            item["report"].get("summary", ""), item["report"].get("issueType", ""),
            item["disposition"].get("result", ""), item["updatedAt"],
        ])
    return Response(
        content="\ufeff" + stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="patrol-tasks.csv"'},
    )


@router.post("/tasks/{task_id}/actions/{action}")
def apply_patrol_action(
    task_id: str,
    action: str,
    payload: PatrolAction,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    transition = TRANSITIONS.get(action)
    if not transition:
        raise HTTPException(status_code=404, detail="不支持的巡护任务操作。")
    record = get_business_record(MODULE_KEY, task_id, context)
    current = str(record.status or "planned")
    allowed, next_status, label = transition
    if current not in allowed:
        raise HTTPException(status_code=409, detail=f"任务当前状态不能执行“{label}”。")

    properties = dict(record.properties or {})
    note = payload.note.strip()
    if action == "assign":
        assignee = payload.assigneeName.strip()
        if not assignee:
            raise HTTPException(status_code=422, detail="派发任务时必须指定责任人。")
        properties["assigneeName"] = assignee
        note = note or f"派发给 {assignee}"
    if action == "report":
        summary = payload.summary.strip()
        if not summary:
            raise HTTPException(status_code=422, detail="提交现场结果时必须填写巡护结论。")
        properties["report"] = {
            "summary": summary,
            "issueType": payload.issueType.strip(),
            "issueLevel": payload.issueLevel.strip(),
            "locationText": payload.locationText.strip(),
            "attachmentIds": list(dict.fromkeys(payload.attachmentIds)),
            "trackPoints": [dict(item) for item in payload.trackPoints],
            "distanceKm": payload.distanceKm,
            "durationSeconds": payload.durationSeconds,
            "clientOperationId": payload.clientOperationId.strip(),
            "reportedAt": now_iso(),
            "reportedBy": context.user,
        }
        sync_attachment_links("patrol_task", task_id, payload.attachmentIds, context)
        note = note or summary
    if action == "resolve":
        report = dict(properties.get("report") or {})
        if str(report.get("issueType") or "none") in {"", "none"}:
            raise HTTPException(status_code=409, detail="未发现问题的巡护报告不需要处置，可直接复核。")
        summary = payload.dispositionSummary.strip()
        result = payload.dispositionResult.strip()
        if not summary or not result:
            raise HTTPException(status_code=422, detail="完成问题处置时必须填写处置说明和结果。")
        existing_attachment_ids = [item["id"] for item in linked_attachments("patrol_task", task_id)]
        combined_attachment_ids = list(dict.fromkeys([*existing_attachment_ids, *payload.attachmentIds]))
        properties["disposition"] = {
            "summary": summary,
            "result": result,
            "attachmentIds": list(dict.fromkeys(payload.attachmentIds)),
            "resolvedAt": now_iso(),
            "resolvedBy": context.user,
        }
        sync_attachment_links("patrol_task", task_id, combined_attachment_ids, context)
        note = note or summary
    if action == "verify":
        report = dict(properties.get("report") or {})
        if current == "reported" and str(report.get("issueType") or "none") not in {"", "none"}:
            raise HTTPException(status_code=409, detail="发现问题的巡护报告必须先完成处置，再进行复核。")
        properties["closureStatus"] = "verified"
    elif action == "close":
        properties["closureStatus"] = "completed"
    elif action == "return":
        if not note:
            raise HTTPException(status_code=422, detail="退回时必须填写原因。")
        properties["closureStatus"] = "in-progress"
    elif action in {"accept", "start", "report", "resolve"}:
        properties["closureStatus"] = "in-progress"

    timeline = list(properties.get("timeline") or [])
    timeline.append(timeline_entry(action, label, next_status, context, note))
    properties["timeline"] = timeline
    updated = patch_business_record(
        MODULE_KEY,
        task_id,
        ManagedRecordPatch(status=next_status, properties=properties),
        context,
    )
    return serialize_task(updated)
