from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from server.modules.admin_roles import effective_permissions_for_context, require_permission
from server.modules.ai_findings import list_findings
from server.modules.auth import AuthContext, has_admin_role, request_context
from server.modules.business import ManagedFilters, list_business_records
from server.modules.database import (
    JSON_STORE_LOCK,
    load_json_records,
    mysql_connect,
    operations_notification_reads_json_path,
    save_json_records,
    use_mysql,
)
from server.modules.drone import list_missions
from server.modules.harvest import list_applications
from server.modules.labor import list_jobs
from server.modules.safety_events import list_events

from .ai import require_finding_scope
from .drone import require_mission_scope
from .harvest import require_application_scope
from .labor import require_job_scope
from .patrol import MODULE_KEY as PATROL_MODULE_KEY, serialize_task
from .safety import require_event_scope


router = APIRouter(prefix="/operations-center", tags=["v2-operations-center"])

STATUS_LABELS = {
    "planned": "待安排", "assigned": "待接单", "accepted": "待开始", "patrolling": "巡护中",
    "reported": "待复核", "resolved": "待复核", "draft": "草稿", "submitted": "已提交",
    "quota_check": "配额校验", "approving": "待审批", "approved": "待开工", "operating": "作业中",
    "verifying": "待验收", "published": "待匹配", "matched": "待签约", "contracted": "待开工",
    "working": "作业中", "settled": "待归档", "new": "待分级", "triaged": "待派单",
    "handling": "处置中", "processing": "待复核", "reviewed": "待归档", "pending": "待复核",
    "confirmed": "待转办",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def can(context: AuthContext, permission: str) -> bool:
    permissions = set(effective_permissions_for_context(context))
    if has_admin_role(context) or "*" in permissions or permission in permissions:
        return True
    return f"{permission.rsplit('.', 1)[0]}.manage" in permissions


def scoped(records: list[dict[str, Any]], checker: Callable[[dict[str, Any], AuthContext], None], context: AuthContext) -> list[dict[str, Any]]:
    visible: list[dict[str, Any]] = []
    for record in records:
        try:
            checker(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        visible.append(record)
    return visible


def todo(record: dict[str, Any], *, module: str, module_label: str, number_key: str, path: str, due_key: str = "") -> dict[str, Any]:
    status = str(record.get("status") or "")
    blocks = record.get("blocks") or record.get("linkedBlockCodes") or []
    block_codes = [str(item.get("code") or "") if isinstance(item, dict) else str(item) for item in blocks]
    return {
        "id": f"{module}:{record.get('id')}",
        "recordId": str(record.get("id") or ""),
        "recordNo": str(record.get(number_key) or record.get("recordCode") or ""),
        "title": str(record.get("title") or record.get("name") or record.get(number_key) or "未命名事项"),
        "module": module,
        "moduleLabel": module_label,
        "status": status,
        "statusLabel": STATUS_LABELS.get(status, status or "待办理"),
        "priority": str(record.get("priority") or record.get("severity") or "normal"),
        "assigneeName": str(record.get("assigneeName") or ""),
        "dueAt": str(record.get(due_key) or "") if due_key else "",
        "updatedAt": str(record.get("updatedAt") or record.get("createdAt") or ""),
        "linkedBlockCodes": [code for code in block_codes if code],
        "targetPath": path,
    }


def collect_todos(context: AuthContext) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if can(context, "business.maintenanceTasks.view"):
        page = list_business_records(PATROL_MODULE_KEY, ManagedFilters(limit=200, offset=0), context)
        for raw in page["items"]:
            record = serialize_task(raw)
            if record.get("status") not in {"verified", "closed"}:
                items.append(todo(record, module="patrol", module_label="巡护办理", number_key="patrolNo", path="/operations/patrol", due_key="plannedEndAt"))
    sources = [
        ("operations.harvest.view", list_applications, require_application_scope, {"completed"}, "harvest", "采伐办理", "applicationNo", "/operations/harvest", "plannedEndAt"),
        ("labor.view", list_jobs, require_job_scope, {"closed"}, "labor", "劳务用工", "jobNo", "/operations/labor", "plannedEndAt"),
        ("safety.events.view", list_events, require_event_scope, {"closed"}, "safety", "事件中心", "incidentNo", "/safety/events", "deadlineAt"),
        ("drone.missions.view", list_missions, require_mission_scope, {"completed", "cancelled"}, "drone", "无人机任务", "missionNo", "/drone/missions", "plannedEndAt"),
        ("ai.findings.view", list_findings, require_finding_scope, {"converted", "ignored"}, "ai", "AI 识别复核", "findingNo", "/ai/reviews", "occurredAt"),
    ]
    for permission, loader, checker, closed, module, label, number_key, path, due_key in sources:
        if not can(context, permission):
            continue
        records = scoped(loader(), checker, context)
        for record in records:
            if str(record.get("status") or "") not in closed:
                items.append(todo(record, module=module, module_label=label, number_key=number_key, path=path, due_key=due_key))
    items.sort(key=lambda item: (item["dueAt"] or "9999", item["updatedAt"]), reverse=False)
    return items


def timeline_items(record: dict[str, Any], module: str, label: str, number_key: str, path: str) -> list[dict[str, Any]]:
    result = []
    for entry in record.get("timeline") or []:
        created_at = str(entry.get("createdAt") or entry.get("at") or "")
        event_id = str(entry.get("id") or f"{module}:{record.get('id')}:{created_at}:{entry.get('action')}")
        result.append({
            "id": event_id,
            "module": module,
            "moduleLabel": label,
            "recordId": str(record.get("id") or ""),
            "recordNo": str(record.get(number_key) or record.get("recordCode") or ""),
            "recordName": str(record.get("title") or record.get("name") or ""),
            "action": str(entry.get("action") or "update"),
            "actor": str(entry.get("actor") or ""),
            "fromStatus": str(entry.get("fromStatus") or ""),
            "toStatus": str(entry.get("toStatus") or entry.get("status") or ""),
            "message": str(entry.get("note") or entry.get("label") or "业务状态已更新"),
            "createdAt": created_at,
            "targetPath": path,
        })
    return result


def collect_audit(context: AuthContext) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if can(context, "business.maintenanceTasks.view"):
        page = list_business_records(PATROL_MODULE_KEY, ManagedFilters(limit=200, offset=0), context)
        for raw in page["items"]:
            events.extend(timeline_items(serialize_task(raw), "patrol", "巡护办理", "patrolNo", "/operations/patrol"))
    sources = [
        ("operations.harvest.view", list_applications, require_application_scope, "harvest", "采伐办理", "applicationNo", "/operations/harvest"),
        ("labor.view", list_jobs, require_job_scope, "labor", "劳务用工", "jobNo", "/operations/labor"),
        ("safety.events.view", list_events, require_event_scope, "safety", "事件中心", "incidentNo", "/safety/events"),
        ("drone.missions.view", list_missions, require_mission_scope, "drone", "无人机任务", "missionNo", "/drone/missions"),
        ("ai.findings.view", list_findings, require_finding_scope, "ai", "AI 识别复核", "findingNo", "/ai/reviews"),
    ]
    for permission, loader, checker, module, label, number_key, path in sources:
        if can(context, permission):
            for record in scoped(loader(), checker, context):
                events.extend(timeline_items(record, module, label, number_key, path))
    events.sort(key=lambda item: item["createdAt"], reverse=True)
    return events


def read_ids(user: str) -> set[str]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT notification_id FROM operations_notification_reads WHERE user_id = %s", (user,))
                return {str(row[0]) for row in cur.fetchall()}
    return {str(item.get("notificationId")) for item in load_json_records(operations_notification_reads_json_path()) if item.get("userId") == user}


def set_read(user: str, notification_id: str, value: bool) -> None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                if value:
                    cur.execute("INSERT INTO operations_notification_reads (user_id, notification_id, read_at) VALUES (%s, %s, UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE read_at = VALUES(read_at)", (user, notification_id))
                else:
                    cur.execute("DELETE FROM operations_notification_reads WHERE user_id = %s AND notification_id = %s", (user, notification_id))
            conn.commit()
        return
    with JSON_STORE_LOCK:
        records = load_json_records(operations_notification_reads_json_path())
        records = [item for item in records if not (item.get("userId") == user and item.get("notificationId") == notification_id)]
        if value:
            records.append({"userId": user, "notificationId": notification_id, "readAt": utc_now()})
        save_json_records(operations_notification_reads_json_path(), records)


def page(items: list[dict[str, Any]], q: str, module: str, limit: int, offset: int) -> dict[str, Any]:
    needle = q.strip().lower()
    filtered = [item for item in items if (not module or item.get("module") == module) and (not needle or needle in " ".join(str(value) for value in item.values()).lower())]
    return {"items": filtered[offset:offset + limit], "total": len(filtered), "limit": limit, "offset": offset}


def csv_response(filename: str, rows: list[dict[str, Any]], fields: list[tuple[str, str]]) -> Response:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([label for _, label in fields])
    for row in rows:
        writer.writerow([row.get(key, "") for key, _ in fields])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/todos")
def todos(q: str = "", module: str = "", limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.todos.view")
    return page(collect_todos(context), q, module, limit, offset)


@router.get("/notifications")
def notifications(q: str = "", module: str = "", unreadOnly: bool = False, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.notifications.view")
    reads = read_ids(context.user)
    items = [{**item, "read": item["id"] in reads} for item in collect_audit(context)]
    if unreadOnly:
        items = [item for item in items if not item["read"]]
    return page(items, q, module, limit, offset)


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.notifications.manage")
    if notification_id not in {item["id"] for item in collect_audit(context)}:
        raise HTTPException(status_code=404, detail="消息不存在或不在当前数据权限范围内。")
    set_read(context.user, notification_id, True)
    return {"ok": True, "notificationId": notification_id, "read": True}


@router.delete("/notifications/{notification_id}/read")
def mark_notification_unread(notification_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.notifications.manage")
    if notification_id not in {item["id"] for item in collect_audit(context)}:
        raise HTTPException(status_code=404, detail="消息不存在或不在当前数据权限范围内。")
    set_read(context.user, notification_id, False)
    return {"ok": True, "notificationId": notification_id, "read": False}


@router.post("/notifications/read-all")
def mark_all_notifications_read(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.notifications.manage")
    items = collect_audit(context)
    for item in items:
        set_read(context.user, item["id"], True)
    return {"ok": True, "updated": len(items)}


@router.get("/todos.csv")
def export_todos(q: str = "", module: str = "", context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "operations.todos.export")
    rows = page(collect_todos(context), q, module, 5000, 0)["items"]
    return csv_response("operations-todos.csv", rows, [("moduleLabel", "模块"), ("recordNo", "单号"), ("title", "事项"), ("statusLabel", "状态"), ("priority", "优先级"), ("assigneeName", "责任人"), ("dueAt", "办理时限"), ("updatedAt", "更新时间")])


@router.get("/notifications.csv")
def export_notifications(q: str = "", module: str = "", unreadOnly: bool = False, context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "operations.notifications.export")
    reads = read_ids(context.user)
    rows = [{**item, "readLabel": "已读" if item["id"] in reads else "未读"} for item in collect_audit(context)]
    if unreadOnly:
        rows = [item for item in rows if item["readLabel"] == "未读"]
    rows = page(rows, q, module, 5000, 0)["items"]
    return csv_response("operations-notifications.csv", rows, [("createdAt", "时间"), ("moduleLabel", "模块"), ("recordNo", "单号"), ("recordName", "名称"), ("message", "消息"), ("readLabel", "阅读状态")])


@router.get("/audit")
def audit(q: str = "", module: str = "", limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.audit.view")
    return page(collect_audit(context), q, module, limit, offset)


@router.get("/audit.csv")
def export_audit(q: str = "", module: str = "", context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "operations.audit.export")
    rows = page(collect_audit(context), q, module, 5000, 0)["items"]
    return csv_response("operations-audit.csv", rows, [("createdAt", "时间"), ("moduleLabel", "模块"), ("recordNo", "单号"), ("recordName", "名称"), ("action", "动作"), ("actor", "操作人"), ("fromStatus", "原状态"), ("toStatus", "新状态"), ("message", "说明")])
