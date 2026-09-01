from __future__ import annotations

import hashlib
import io
import csv
import json
import math
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, has_admin_role, request_context
from server.modules.database import mobile_evidence_dir, mobile_upload_chunks_dir
from server.modules.forest_blocks import block_by_code, require_target_block_allowed
from server.modules.forest_subcompartments import (
    ForestSubcompartmentFilters,
    list_forest_subcompartments,
    list_forest_subcompartment_versions,
)
from server.modules.harvest import list_applications
from server.modules.mobile_sync import (
    begin_operation,
    complete_operation,
    evidence_by_id,
    list_evidence,
    list_operations,
    operation_by_id,
    operation_ledger,
    save_evidence,
    save_track,
    save_upload_session,
    track_ledger,
    update_upload_session,
    upload_session_by_id,
    upload_session_ledger,
    utc_now,
)
from server.modules.mobile_devices import list_mobile_devices, mobile_device_by_id, restore_mobile_device, revoke_mobile_device, upsert_mobile_device
from server.v2.labor import LaborAction, apply_job_action, job_detail, job_ledger
from server.v2.patrol import PatrolAction, apply_patrol_action, get_patrol_task, list_patrol_tasks
from server.v2.safety import SafetyEventCreate, add_safety_event, safety_event_ledger


router = APIRouter(prefix="/mobile", tags=["v2-mobile-field"])
SAFE_FILE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
ALLOWED_CONTENT_PREFIXES = ("image/", "video/")
MAX_EVIDENCE_BYTES = 50 * 1024 * 1024
MAX_RESUMABLE_EVIDENCE_BYTES = 500 * 1024 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024


class MobileSyncOperation(BaseModel):
    clientOperationId: str = Field(min_length=8, max_length=128)
    entityType: Literal["patrol", "labor", "safety"]
    entityId: str = Field(default="", max_length=128)
    action: str = Field(min_length=1, max_length=64)
    baseVersion: str = Field(default="", max_length=128)
    occurredAt: str
    payload: dict[str, Any] = Field(default_factory=dict)


class MobileSyncBatch(BaseModel):
    operations: list[MobileSyncOperation] = Field(min_length=1, max_length=100)


class MobileConflictResolution(BaseModel):
    strategy: Literal["retry", "discard"]
    note: str = Field(min_length=2, max_length=500)


class TrackPoint(BaseModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    capturedAt: str
    accuracyMeters: float | None = Field(default=None, ge=0, le=10000)
    altitudeMeters: float | None = Field(default=None, ge=-500, le=10000)


class MobileTrackBatch(BaseModel):
    clientTrackId: str = Field(min_length=8, max_length=128)
    taskType: Literal["patrol", "labor"]
    taskId: str = Field(min_length=1, max_length=128)
    status: Literal["recording", "completed"] = "completed"
    points: list[TrackPoint] = Field(min_length=2, max_length=5000)


class UploadSessionCreate(BaseModel):
    fileName: str = Field(min_length=1, max_length=255)
    contentType: str = Field(min_length=3, max_length=128)
    totalBytes: int = Field(gt=0, le=MAX_RESUMABLE_EVIDENCE_BYTES)
    totalChunks: int = Field(gt=0, le=10000)
    sha256: str = Field(default="", max_length=64)
    taskType: str = Field(default="", max_length=64)
    taskId: str = Field(default="", max_length=128)


class MobileDeviceRegistration(BaseModel):
    deviceId: str = Field(min_length=8, max_length=128)
    deviceName: str = Field(default="", max_length=128)
    platform: Literal["android", "ios", "web"]
    appVersion: str = Field(min_length=1, max_length=32)
    osVersion: str = Field(default="", max_length=64)
    pushToken: str = Field(default="", max_length=512)
    capabilities: list[str] = Field(default_factory=list, max_length=32)


class MobileDeviceRevocation(BaseModel):
    note: str = Field(min_length=2, max_length=500)


def client_policy() -> dict[str, Any]:
    return {
        "minimumVersions": {
            "android": os.getenv("SMART_BAMBOO_ANDROID_MIN_VERSION", "1.0.0"),
            "ios": os.getenv("SMART_BAMBOO_IOS_MIN_VERSION", "1.0.0"),
            "web": os.getenv("SMART_BAMBOO_WEB_MIN_VERSION", "1.0.0"),
        },
        "latestVersions": {
            "android": os.getenv("SMART_BAMBOO_ANDROID_LATEST_VERSION", "1.0.0"),
            "ios": os.getenv("SMART_BAMBOO_IOS_LATEST_VERSION", "1.0.0"),
            "web": os.getenv("SMART_BAMBOO_WEB_LATEST_VERSION", "1.0.0"),
        },
        "updateUrls": {
            "android": os.getenv("SMART_BAMBOO_ANDROID_UPDATE_URL", ""),
            "ios": os.getenv("SMART_BAMBOO_IOS_UPDATE_URL", ""),
        },
    }


def parse_timestamp(value: str, label: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{label}格式不正确。") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def task_overdue(due_at: str, status: str) -> bool:
    if status in {"closed", "settled", "completed"} or not due_at:
        return False
    try:
        due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due < datetime.now(timezone.utc)
    except ValueError:
        return False


def mobile_patrol_task(record: dict[str, Any]) -> dict[str, Any]:
    due_at = str(record.get("plannedEndAt") or "")
    return {
        "id": record["id"],
        "taskType": "patrol",
        "taskNo": record.get("patrolNo") or "",
        "title": record.get("name") or "巡护任务",
        "status": record.get("status") or "planned",
        "priority": record.get("priority") or "normal",
        "assigneeName": record.get("assigneeName") or "",
        "plannedStartAt": record.get("plannedStartAt") or "",
        "dueAt": due_at,
        "linkedBlockCodes": list(record.get("linkedBlockCodes") or []),
        "instructions": record.get("instructions") or "",
        "version": str(record.get("updatedAt") or ""),
        "overdue": task_overdue(due_at, str(record.get("status") or "")),
        "detail": record,
    }


def mobile_labor_task(record: dict[str, Any]) -> dict[str, Any]:
    due_at = str(record.get("plannedEndAt") or "")
    return {
        "id": record["id"],
        "taskType": "labor",
        "taskNo": record.get("jobNo") or "",
        "title": record.get("title") or "劳务工单",
        "status": record.get("status") or "draft",
        "priority": "normal",
        "assigneeName": record.get("teamName") or "",
        "plannedStartAt": record.get("plannedStartAt") or "",
        "dueAt": due_at,
        "linkedBlockCodes": [str(item.get("code")) for item in record.get("blocks") or []],
        "instructions": record.get("instructions") or "",
        "version": str(record.get("version") or 0),
        "overdue": task_overdue(due_at, str(record.get("status") or "")),
        "detail": record,
    }


def mobile_safety_task(record: dict[str, Any]) -> dict[str, Any]:
    due_at = str(record.get("deadlineAt") or "")
    return {
        "id": record["id"],
        "taskType": "safety",
        "taskNo": record.get("incidentNo") or "",
        "title": record.get("title") or "安全处置",
        "status": record.get("status") or "new",
        "priority": record.get("severity") or "medium",
        "assigneeName": record.get("assigneeName") or "",
        "plannedStartAt": record.get("createdAt") or "",
        "dueAt": due_at,
        "linkedBlockCodes": [str(item.get("code")) for item in record.get("blocks") or []],
        "instructions": record.get("description") or "",
        "version": str(record.get("version") or 0),
        "overdue": task_overdue(due_at, str(record.get("status") or "")),
        "detail": record,
    }


def visible_to_worker(task: dict[str, Any], context: AuthContext) -> bool:
    assignee = str(task.get("assigneeName") or "").strip()
    return has_admin_role(context) or not assignee or assignee == context.user


@router.get("/bootstrap")
def mobile_bootstrap(
    limit: int = Query(default=100, ge=1, le=200),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    domain_access = {"patrol": False, "labor": False, "safety": False}

    try:
        patrol = list_patrol_tasks(
            q="", status="", linkedBlockCode="", includeDeleted=False,
            limit=limit, offset=0, context=context
        )
        domain_access["patrol"] = True
        tasks.extend(mobile_patrol_task(item) for item in patrol["items"])
    except HTTPException as exc:
        if exc.status_code != 403:
            raise

    try:
        labor = job_ledger(
            q="", status="", linked_block_code="", include_deleted=False,
            limit=limit, offset=0, context=context
        )
        domain_access["labor"] = True
        tasks.extend(mobile_labor_task(item) for item in labor["items"])
    except HTTPException as exc:
        if exc.status_code != 403:
            raise

    try:
        safety = safety_event_ledger(
            q="", status="", severity="", linked_block_code="", overdue_only=False,
            include_deleted=False, limit=limit, offset=0, context=context,
        )
        domain_access["safety"] = True
        tasks.extend(
            mobile_safety_task(item)
            for item in safety["items"]
            if item.get("status") not in {"verified", "closed"}
        )
    except HTTPException as exc:
        if exc.status_code != 403:
            raise

    tasks = [task for task in tasks if visible_to_worker(task, context)]
    tasks.sort(
        key=lambda item: (
            not bool(item.get("overdue")),
            0 if item.get("priority") in {"urgent", "critical", "high"} else 1,
            str(item.get("dueAt") or "9999"),
        )
    )
    operations = list_operations(context.user, 50)
    conflicts = [item for item in operations if item.get("status") == "conflict"]
    messages = [
        {
            "id": f"conflict:{item['id']}",
            "type": "sync-conflict",
            "title": "现场数据需要人工确认",
            "body": f"{item.get('entityType')} {item.get('entityId')} 的服务器数据已更新。",
            "createdAt": item.get("completedAt") or item.get("receivedAt"),
            "operationId": item["id"],
        }
        for item in conflicts[:20]
    ]
    linked_block_codes = sorted({
        str(code) for task in tasks for code in task.get("linkedBlockCodes") or [] if str(code)
    })
    offline_subcompartments: list[dict[str, Any]] = []
    offline_history: dict[str, list[dict[str, Any]]] = {}
    for block_code in linked_block_codes:
        block = block_by_code(block_code)
        if not block:
            continue
        try:
            require_target_block_allowed(context, block)
            page = list_forest_subcompartments(
                ForestSubcompartmentFilters(forestBlockId=str(block["id"]), limit=200), context,
            )
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        offline_subcompartments.extend(page["items"])
        for subcompartment in page["items"]:
            try:
                versions = list_forest_subcompartment_versions(str(subcompartment["id"]), context)
                offline_history[str(subcompartment["id"])] = list(versions.get("items") or [])[:20]
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
    harvest_forms: list[dict[str, Any]] = []
    try:
        for application in list_applications():
            codes = [str(link.get("code") or "") for link in application.get("blocks") or []]
            if not set(codes).intersection(linked_block_codes) or application.get("status") not in {"approved", "operating", "submitted"}:
                continue
            harvest_forms.append({
                "applicationId": application["id"], "applicationNo": application.get("applicationNo"),
                "status": application.get("status"), "linkedBlockCodes": codes,
                "approvedQuantity": application.get("approvedQuantity"), "approvedGeometry": application.get("approvedGeometry"),
                "requiredEvidence": ["现场边界", "定位轨迹", "作业前照片", "作业后照片"],
                "idempotencyScope": f"mobile-harvest:{application['id']}",
            })
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
    return {
        "serverTime": utc_now(),
        "principal": {
            "user": context.user,
            "roles": sorted(context.roles),
            "areas": sorted(context.areas),
        },
        "domainAccess": domain_access,
        "tasks": tasks,
        "operations": operations,
        "messages": messages,
        "offlineResources": {
            "subcompartments": offline_subcompartments,
            "subcompartmentHistory": offline_history,
            "harvestBoundaryForms": harvest_forms,
            "eventForm": {
                "fields": ["title", "severity", "description", "longitude", "latitude", "evidenceIds"],
                "supportsOffline": True, "syncEntityType": "safety", "syncAction": "sos",
            },
        },
        "syncCursor": operations[0]["receivedAt"] if operations else "",
        "clientPolicy": client_policy(),
    }


@router.post("/devices/register")
def register_mobile_device(payload: MobileDeviceRegistration, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    now = utc_now()
    existing = mobile_device_by_id(payload.deviceId)
    if existing and existing.get("status") == "revoked":
        raise HTTPException(status_code=403, detail="该设备已被管理员远程注销，请联系管理员恢复绑定。")
    record = {
        **(existing or {}), **payload.model_dump(mode="json"), "userId": context.user,
        "status": "active", "registeredAt": (existing or {}).get("registeredAt") or now,
        "lastSeenAt": now, "revokedAt": "", "revokedBy": "", "revocationNote": "",
    }
    return {"device": upsert_mobile_device(record), "clientPolicy": client_policy()}


@router.get("/devices")
def mobile_device_ledger(
    q: str = Query(default=""), status: str = Query(default=""), user_id: str = Query(default="", alias="userId"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "mobile.operations.view")
    if status and status not in {"active", "revoked"}:
        raise HTTPException(status_code=422, detail="设备状态不正确。")
    records = list_mobile_devices(q, status, user_id)
    items = [{**item, "pushTokenRegistered": bool(item.get("pushToken")), "pushToken": ""} for item in records[offset:offset + limit]]
    return {"items": items, "total": len(records), "limit": limit, "offset": offset, "clientPolicy": client_policy()}


@router.post("/devices/{device_id}/revoke")
def revoke_registered_mobile_device(device_id: str, payload: MobileDeviceRevocation, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "mobile.operations.manage")
    record = revoke_mobile_device(device_id, utc_now(), context.user, payload.note.strip())
    if not record:
        raise HTTPException(status_code=404, detail="移动设备不存在。")
    return record


@router.post("/devices/{device_id}/restore")
def restore_registered_mobile_device(device_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "mobile.operations.manage")
    record = restore_mobile_device(device_id, utc_now(), context.user)
    if not record:
        raise HTTPException(status_code=404, detail="移动设备不存在。")
    return record


@router.get("/offline-package")
def mobile_offline_package(
    limit: int = Query(default=100, ge=1, le=200),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    payload = mobile_bootstrap(limit=limit, context=context)
    manifest = json.dumps(
        {
            "tasks": [{"id": item["id"], "version": item["version"]} for item in payload["tasks"]],
            "subcompartments": [
                {"id": item["id"], "version": item.get("version")}
                for item in payload.get("offlineResources", {}).get("subcompartments", [])
            ],
            "harvestForms": [
                {"id": item["applicationId"], "status": item.get("status")}
                for item in payload.get("offlineResources", {}).get("harvestBoundaryForms", [])
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    package_version = hashlib.sha256(manifest.encode("utf-8")).hexdigest()
    return {
        **payload,
        "packageId": f"offline:{context.user}:{package_version[:16]}",
        "packageVersion": package_version,
        "generatedAt": utc_now(),
        "expiresAt": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "downloadPolicy": "replace-when-version-changes",
    }


def haversine_meters(first: TrackPoint, second: TrackPoint) -> float:
    radius = 6_371_000.0
    lat1, lat2 = math.radians(first.latitude), math.radians(second.latitude)
    d_lat = lat2 - lat1
    d_lon = math.radians(second.longitude - first.longitude)
    value = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


@router.post("/tracks")
def upload_mobile_track(
    payload: MobileTrackBatch,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    if payload.taskType == "patrol":
        get_patrol_task(payload.taskId, context)
    else:
        job_detail(payload.taskId, context)
    points = [
        {**point.model_dump(mode="json"), "capturedAt": parse_timestamp(point.capturedAt, "轨迹采样时间")}
        for point in payload.points
    ]
    distance = sum(
        haversine_meters(payload.points[index - 1], payload.points[index])
        for index in range(1, len(payload.points))
    )
    record, created = save_track(
        {
            "id": str(uuid.uuid4()), "clientTrackId": payload.clientTrackId, "userId": context.user,
            "taskType": payload.taskType, "taskId": payload.taskId, "status": payload.status,
            "points": points, "pointCount": len(points), "distanceMeters": round(distance, 3),
            "startedAt": points[0]["capturedAt"], "endedAt": points[-1]["capturedAt"],
            "createdAt": utc_now(), "deletedAt": None,
        }
    )
    return {**record, "replayed": not created}


def current_entity_version(operation: MobileSyncOperation, context: AuthContext) -> str:
    if operation.entityType == "patrol":
        return str(get_patrol_task(operation.entityId, context).get("updatedAt") or "")
    if operation.entityType == "labor":
        return str(job_detail(operation.entityId, context).get("version") or 0)
    return ""


def execute_operation(operation: MobileSyncOperation, context: AuthContext) -> dict[str, Any]:
    if operation.entityType == "patrol":
        if operation.action not in {"accept", "start", "report"}:
            raise HTTPException(status_code=422, detail="移动端不支持该巡护操作。")
        patrol_payload = {**operation.payload, "clientOperationId": operation.clientOperationId}
        return apply_patrol_action(
            operation.entityId,
            operation.action,
            PatrolAction.model_validate(patrol_payload),
            context,
        )
    if operation.entityType == "labor":
        if operation.action not in {"start", "attendance", "submit"}:
            raise HTTPException(status_code=422, detail="移动端不支持该劳务操作。")
        return apply_job_action(
            operation.entityId,
            operation.action,
            LaborAction.model_validate(operation.payload),
            context,
        )
    if operation.entityType == "safety" and operation.action == "sos":
        payload = dict(operation.payload)
        block_codes = list(payload.get("linkedBlockCodes") or [])
        return add_safety_event(
            SafetyEventCreate.model_validate(
                {
                    "title": payload.get("title") or f"{context.user} 现场 SOS",
                    "eventType": "sos",
                    "severity": "critical",
                    "sourceType": "manual",
                    "sourceRef": operation.clientOperationId,
                    "locationText": payload.get("locationText") or "移动现场端 SOS",
                    "longitude": payload.get("longitude"),
                    "latitude": payload.get("latitude"),
                    "description": payload.get("description") or "现场人员触发紧急求助，请立即联系并处置。",
                    "linkedBlockCodes": block_codes,
                }
            ),
            context,
        )
    raise HTTPException(status_code=422, detail="不支持的移动同步操作。")


def sync_one(operation: MobileSyncOperation, context: AuthContext) -> dict[str, Any]:
    occurred_at = parse_timestamp(operation.occurredAt, "现场发生时间")
    received_at = utc_now()
    receipt, created = begin_operation(
        {
            "id": str(uuid.uuid4()),
            "clientOperationId": operation.clientOperationId,
            "userId": context.user,
            "entityType": operation.entityType,
            "entityId": operation.entityId,
            "action": operation.action,
            "baseVersion": operation.baseVersion,
            "status": "processing",
            "request": operation.model_dump(mode="json"),
            "result": {},
            "errorCode": "",
            "occurredAt": occurred_at,
            "receivedAt": received_at,
            "completedAt": None,
        }
    )
    if not created:
        return {**receipt, "replayed": True}

    try:
        if operation.baseVersion and operation.entityType in {"patrol", "labor"}:
            server_version = current_entity_version(operation, context)
            if server_version != operation.baseVersion:
                return complete_operation(
                    receipt["id"],
                    status="conflict",
                    error_code="version_conflict",
                    result={
                        "serverVersion": server_version,
                        "clientVersion": operation.baseVersion,
                        "message": "服务器数据已更新，请查看差异后重新提交。",
                    },
                )
        result = execute_operation(operation, context)
        return complete_operation(
            receipt["id"],
            status="completed",
            result={"entity": result, "serverVersion": str(result.get("version") or result.get("updatedAt") or "")},
        )
    except HTTPException as exc:
        return complete_operation(
            receipt["id"],
            status="failed",
            error_code=f"http_{exc.status_code}",
            result={"message": str(exc.detail)},
        )
    except Exception:
        complete_operation(
            receipt["id"],
            status="failed",
            error_code="internal_error",
            result={"message": "现场数据同步失败，请稍后重试。"},
        )
        raise


@router.post("/sync")
def mobile_sync(
    payload: MobileSyncBatch,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    results = [sync_one(operation, context) for operation in payload.operations]
    return {
        "serverTime": utc_now(),
        "results": results,
        "completed": sum(item.get("status") == "completed" for item in results),
        "conflicts": sum(item.get("status") == "conflict" for item in results),
        "failed": sum(item.get("status") == "failed" for item in results),
    }


@router.get("/operations")
def mobile_operation_ledger(
    q: str = Query(default="", max_length=128),
    status: str = Query(default="", max_length=32),
    userId: str = Query(default="", max_length=128),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "mobile.operations.view")
    return operation_ledger(q=q.strip(), status=status.strip(), user_id=userId.strip(), limit=limit, offset=offset)


@router.post("/operations/{operation_id}/resolve")
def resolve_mobile_conflict(
    operation_id: str,
    payload: MobileConflictResolution,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "mobile.operations.manage")
    operation = operation_by_id(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail="同步操作不存在。")
    if operation.get("status") != "conflict":
        raise HTTPException(status_code=409, detail="只有版本冲突记录可以办理。")

    if payload.strategy == "discard":
        resolved = complete_operation(
            operation_id,
            status="discarded",
            result={
                **(operation.get("result") or {}),
                "resolution": "discard",
                "resolutionNote": payload.note,
                "resolvedBy": context.user,
                "resolvedAt": utc_now(),
            },
        )
        return {"operation": resolved, "retryOperation": None}

    original = MobileSyncOperation.model_validate(operation.get("request") or {})
    current_version = current_entity_version(original, context)
    retry_operation = original.model_copy(
        update={
            "clientOperationId": f"{original.clientOperationId[:88]}-retry-{uuid.uuid4().hex[:8]}",
            "baseVersion": current_version,
            "occurredAt": utc_now(),
        }
    )
    retry_result = sync_one(retry_operation, context)
    resolved = complete_operation(
        operation_id,
        status="resolved",
        result={
            **(operation.get("result") or {}),
            "resolution": "retry",
            "resolutionNote": payload.note,
            "resolvedBy": context.user,
            "resolvedAt": utc_now(),
            "retryOperationId": retry_result.get("id") or "",
            "retryStatus": retry_result.get("status") or "",
        },
    )
    return {"operation": resolved, "retryOperation": retry_result}


@router.get("/operations-export.csv")
def mobile_operation_export(
    q: str = Query(default="", max_length=128), status: str = Query(default="", max_length=32),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "mobile.operations.view")
    records = operation_ledger(q=q.strip(), status=status.strip(), limit=10000, offset=0)["items"]
    stream = io.StringIO(); writer = csv.writer(stream)
    writer.writerow(["客户端操作号", "人员", "业务类型", "业务记录", "动作", "状态", "错误代码", "现场时间", "接收时间"])
    for item in records:
        writer.writerow([item["clientOperationId"], item["userId"], item["entityType"], item["entityId"], item["action"], item["status"], item["errorCode"], item["occurredAt"], item["receivedAt"]])
    return Response("\ufeff" + stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="mobile-sync-operations.csv"'})


@router.get("/tracks")
def mobile_track_ledger(
    q: str = Query(default="", max_length=128), status: str = Query(default="", max_length=32),
    userId: str = Query(default="", max_length=128), limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0), context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "mobile.operations.view")
    return track_ledger(q=q.strip(), status=status.strip(), user_id=userId.strip(), limit=limit, offset=offset)


@router.get("/evidence")
def mobile_evidence_ledger(
    q: str = Query(default="", max_length=128), userId: str = Query(default="", max_length=128),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "mobile.operations.view")
    return list_evidence(q=q.strip(), user_id=userId.strip(), limit=limit, offset=offset)


def require_upload_owner(record: dict[str, Any] | None, context: AuthContext) -> dict[str, Any]:
    if not record:
        raise HTTPException(status_code=404, detail="上传会话不存在。")
    if record.get("userId") != context.user and not has_admin_role(context):
        raise HTTPException(status_code=403, detail="无权访问该上传会话。")
    return record


@router.post("/uploads")
def create_mobile_upload_session(
    payload: UploadSessionCreate,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    content_type = payload.contentType.lower().strip()
    if not content_type.startswith(ALLOWED_CONTENT_PREFIXES):
        raise HTTPException(status_code=415, detail="现场证据仅支持图片或视频。")
    expected_hash = payload.sha256.lower().strip()
    if expected_hash and not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
        raise HTTPException(status_code=422, detail="SHA-256 格式不正确。")
    now = datetime.now(timezone.utc)
    record = {
        "id": str(uuid.uuid4()), "userId": context.user, "taskType": payload.taskType.strip(),
        "taskId": payload.taskId.strip(), "fileName": SAFE_FILE_NAME.sub("-", Path(payload.fileName).name).strip(".-") or "evidence",
        "contentType": content_type, "totalBytes": payload.totalBytes, "totalChunks": payload.totalChunks,
        "expectedSha256": expected_hash, "receivedChunks": [], "status": "uploading", "evidenceId": "",
        "createdAt": now.isoformat(), "updatedAt": now.isoformat(), "expiresAt": (now + timedelta(days=2)).isoformat(), "deletedAt": None,
    }
    save_upload_session(record)
    return record


@router.get("/uploads/{session_id}")
def mobile_upload_status(session_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    return require_upload_owner(upload_session_by_id(session_id), context)


@router.get("/uploads")
def mobile_upload_ledger(
    q: str = Query(default="", max_length=128),
    status: str = Query(default="", max_length=32),
    userId: str = Query(default="", max_length=128),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "mobile.operations.view")
    return upload_session_ledger(
        q=q.strip(),
        status=status.strip(),
        user_id=userId.strip(),
        include_deleted=includeDeleted,
        limit=limit,
        offset=offset,
    )


def clear_upload_chunks(session_id: str) -> None:
    directory = mobile_upload_chunks_dir() / session_id
    if not directory.is_dir():
        return
    for path in directory.iterdir():
        if path.is_file():
            path.unlink()
    directory.rmdir()


@router.delete("/uploads/{session_id}")
def cancel_mobile_upload(
    session_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    record = require_upload_owner(upload_session_by_id(session_id), context)
    if record.get("status") == "completed":
        raise HTTPException(status_code=409, detail="已完成的证据不能从上传会话中取消。")
    clear_upload_chunks(session_id)
    return update_upload_session(
        session_id,
        status="cancelled",
        receivedChunks=[],
        deletedAt=utc_now(),
    )


@router.post("/uploads/{session_id}/restore")
def restore_mobile_upload(
    session_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "mobile.operations.manage")
    record = upload_session_by_id(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="上传会话不存在。")
    if not record.get("deletedAt"):
        return record
    return update_upload_session(
        session_id,
        status="uploading",
        receivedChunks=[],
        deletedAt=None,
    )


@router.put("/uploads/{session_id}/chunks/{chunk_index}")
async def upload_mobile_chunk(
    session_id: str, chunk_index: int, file: UploadFile = File(...),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    record = require_upload_owner(upload_session_by_id(session_id), context)
    if record["status"] != "uploading":
        raise HTTPException(status_code=409, detail="上传会话已结束。")
    if chunk_index < 0 or chunk_index >= int(record["totalChunks"]):
        raise HTTPException(status_code=422, detail="分片序号超出范围。")
    directory = mobile_upload_chunks_dir() / session_id; directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f"{chunk_index}.part.tmp"; final_path = directory / f"{chunk_index}.part"
    size = 0
    try:
        with temporary.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_CHUNK_BYTES:
                    raise HTTPException(status_code=413, detail="单个分片不能超过 8 MB。")
                handle.write(chunk)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, final_path)
    finally:
        if temporary.exists(): temporary.unlink()
        await file.close()
    received = sorted(set([*record.get("receivedChunks", []), chunk_index]))
    updated = update_upload_session(session_id, receivedChunks=received)
    return {**updated, "chunkIndex": chunk_index, "chunkBytes": size}


@router.post("/uploads/{session_id}/complete")
def complete_mobile_upload(session_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    record = require_upload_owner(upload_session_by_id(session_id), context)
    if record["status"] == "completed":
        return record
    expected = list(range(int(record["totalChunks"])))
    if record.get("receivedChunks") != expected:
        raise HTTPException(status_code=409, detail="仍有分片未上传完成。")
    directory = mobile_upload_chunks_dir() / session_id
    evidence_id = str(uuid.uuid4()); suffix = Path(record["fileName"]).suffix.lower()[:12]
    stored_name = f"{evidence_id}{suffix}"; final_path = mobile_evidence_dir() / stored_name
    final_path.parent.mkdir(parents=True, exist_ok=True); temporary = final_path.with_suffix(final_path.suffix + ".part")
    digest = hashlib.sha256(); size = 0
    try:
        with temporary.open("wb") as output:
            for index in expected:
                path = directory / f"{index}.part"
                if not path.is_file(): raise HTTPException(status_code=409, detail=f"分片 {index} 缺失。")
                with path.open("rb") as source:
                    while chunk := source.read(1024 * 1024): digest.update(chunk); size += len(chunk); output.write(chunk)
            output.flush(); os.fsync(output.fileno())
        if size != int(record["totalBytes"]): raise HTTPException(status_code=422, detail="合并文件大小与声明不一致。")
        actual_hash = digest.hexdigest()
        if record.get("expectedSha256") and actual_hash != record["expectedSha256"]:
            raise HTTPException(status_code=422, detail="合并文件 SHA-256 校验失败。")
        os.replace(temporary, final_path)
    finally:
        if temporary.exists(): temporary.unlink()
    evidence = {
        "id": evidence_id, "evidenceNo": f"ZJ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
        "userId": context.user, "taskType": record.get("taskType") or "", "taskId": record.get("taskId") or "",
        "fileName": record["fileName"], "storedName": stored_name, "contentType": record["contentType"],
        "byteSize": size, "sha256": digest.hexdigest(), "capturedAt": None, "longitude": None, "latitude": None,
        "createdAt": utc_now(),
    }
    save_evidence(evidence)
    for path in directory.glob("*.part"): path.unlink()
    directory.rmdir()
    return update_upload_session(session_id, status="completed", evidenceId=evidence_id)


@router.post("/evidence")
async def upload_mobile_evidence(
    file: UploadFile = File(...),
    taskType: str = Form(default=""),
    taskId: str = Form(default=""),
    capturedAt: str = Form(default=""),
    longitude: float | None = Form(default=None),
    latitude: float | None = Form(default=None),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    content_type = str(file.content_type or "application/octet-stream").lower()
    if not content_type.startswith(ALLOWED_CONTENT_PREFIXES):
        raise HTTPException(status_code=415, detail="现场证据仅支持图片或视频。")
    captured_at = parse_timestamp(capturedAt, "拍摄时间") if capturedAt else None
    suffix = Path(file.filename or "evidence.bin").suffix.lower()[:12]
    evidence_id = str(uuid.uuid4())
    safe_name = SAFE_FILE_NAME.sub("-", Path(file.filename or "evidence").name).strip(".-") or "evidence"
    stored_name = f"{evidence_id}{suffix}"
    final_path = mobile_evidence_dir() / stored_name
    temporary = final_path.with_suffix(final_path.suffix + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_EVIDENCE_BYTES:
                    raise HTTPException(status_code=413, detail="单个现场证据不能超过 50 MB。")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, final_path)
    finally:
        if temporary.exists():
            temporary.unlink()
        await file.close()
    now = utc_now()
    record = {
        "id": evidence_id,
        "evidenceNo": f"ZJ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
        "userId": context.user,
        "taskType": taskType.strip(),
        "taskId": taskId.strip(),
        "fileName": safe_name,
        "storedName": stored_name,
        "contentType": content_type,
        "byteSize": size,
        "sha256": digest.hexdigest(),
        "capturedAt": captured_at,
        "longitude": longitude,
        "latitude": latitude,
        "createdAt": now,
    }
    save_evidence(record)
    return {
        **record,
        "url": f"/api/v2/mobile/evidence/{evidence_id}/content",
    }


@router.get("/evidence/{evidence_id}/content")
def mobile_evidence_content(
    evidence_id: str,
    context: AuthContext = Depends(request_context),
) -> FileResponse:
    record = evidence_by_id(evidence_id)
    if not record:
        raise HTTPException(status_code=404, detail="现场证据不存在。")
    if record.get("userId") != context.user and not has_admin_role(context):
        raise HTTPException(status_code=403, detail="无权查看该现场证据。")
    path = mobile_evidence_dir() / str(record["storedName"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="现场证据文件不存在。")
    return FileResponse(path, media_type=str(record["contentType"]), filename=str(record["fileName"]))
