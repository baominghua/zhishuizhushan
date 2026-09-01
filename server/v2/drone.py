from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission
from server.modules.attachments import (
    AttachmentLinkIn,
    create_attachment_link,
    linked_attachments,
    sync_attachment_links,
)
from server.modules.auth import AuthContext, request_context
from server.modules.drone import (
    create_mission,
    list_missions,
    mission_by_id,
    restore_mission,
    soft_delete_mission,
    timeline_entry,
    update_mission,
    utc_now,
)
from server.modules.equipment import device_by_id
from server.modules.forest_blocks import block_by_code, require_target_block_allowed


router = APIRouter(prefix="/drone", tags=["v2-drone"])
MISSION_TYPES = {"survey", "patrol", "mapping", "pest", "fire", "delivery", "other"}
MISSION_STATUSES = {"planned", "assigned", "flying", "processing", "reviewed", "completed", "cancelled"}


class MissionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    missionType: str = "survey"
    droneDeviceId: str
    plannedStartAt: str
    plannedEndAt: str
    linkedBlockCodes: list[str] = Field(min_length=1)
    objective: str = Field(default="", max_length=5000)


class MissionPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    missionType: str | None = None
    droneDeviceId: str | None = None
    plannedStartAt: str | None = None
    plannedEndAt: str | None = None
    linkedBlockCodes: list[str] | None = None
    objective: str | None = Field(default=None, max_length=5000)


class MissionAction(BaseModel):
    note: str = Field(default="", max_length=2000)
    pilotName: str = Field(default="", max_length=128)
    routeName: str = Field(default="", max_length=255)
    resultAssetUrls: list[str] = Field(default_factory=list)
    resultAttachmentIds: list[str] = Field(default_factory=list)
    flightDurationMinutes: float | None = Field(default=None, ge=0)
    flightDistanceKm: float | None = Field(default=None, ge=0)
    coverageAreaMu: float | None = Field(default=None, ge=0)
    reviewNote: str = Field(default="", max_length=2000)


def record_number() -> str:
    return f"WRJ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def validate_enum(value: str, allowed: set[str], label: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise HTTPException(status_code=422, detail=f"不支持的{label}。")
    return normalized


def parse_timestamp(value: str, label: str, *, required: bool = True) -> str | None:
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


def compact(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def validated_blocks(codes: list[str], context: AuthContext) -> list[dict[str, Any]]:
    normalized = compact(codes)
    if not normalized:
        raise HTTPException(status_code=422, detail="无人机任务至少需要关联一个正式林班。")
    blocks: list[dict[str, Any]] = []
    for code in normalized:
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"林班 {code} 不存在或已删除。")
        require_target_block_allowed(context, block)
        blocks.append(block)
    return blocks


def validated_drone(device_id: str, context: AuthContext) -> dict[str, Any]:
    device = device_by_id(device_id)
    if not device or device.get("deviceType") != "drone":
        raise HTTPException(status_code=422, detail="请选择设备台账中有效的无人机设备。")
    if device.get("status") != "active":
        raise HTTPException(status_code=422, detail="当前无人机设备不可执行任务。")
    for link in device.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block:
            require_target_block_allowed(context, block)
    return device


def require_mission_scope(record: dict[str, Any], context: AuthContext) -> None:
    for link in record.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block:
            require_target_block_allowed(context, block)


def get_mission(mission_id: str, context: AuthContext) -> dict[str, Any]:
    record = mission_by_id(mission_id, include_deleted=True)
    if not record:
        raise HTTPException(status_code=404, detail="无人机任务不存在。")
    require_mission_scope(record, context)
    return record


def mission_view(record: dict[str, Any]) -> dict[str, Any]:
    return {
        **record,
        "resultAttachments": linked_attachments("drone_mission", str(record["id"]), "result"),
    }


def flight_record_view(record: dict[str, Any]) -> dict[str, Any]:
    summary = dict(record.get("flightSummary") or {})
    origin = "trajectory" if summary.get("recordOrigin") == "trajectory-auto-import" else "mission"
    missing_fields = [str(item) for item in summary.get("missingFields") or [] if str(item)]
    attachments = linked_attachments("drone_mission", str(record["id"]), "result")
    return {
        "id": str(record["id"]),
        "missionId": str(record["id"]),
        "missionNo": str(record.get("missionNo") or ""),
        "title": str(record.get("title") or ""),
        "origin": origin,
        "status": str(record.get("status") or ""),
        "deviceCode": str(record.get("deviceCode") or ""),
        "deviceName": str(record.get("deviceName") or ""),
        "pilotName": str(record.get("pilotName") or ""),
        "routeName": str(record.get("routeName") or ""),
        "actualStartAt": record.get("actualStartAt"),
        "actualEndAt": record.get("actualEndAt"),
        "durationMinutes": summary.get("durationMinutes"),
        "distanceKm": summary.get("distanceKm"),
        "coverageAreaMu": summary.get("coverageAreaMu"),
        "trajectoryPath": str(summary.get("trajectoryPath") or ""),
        "trajectoryFormats": [str(item) for item in summary.get("trajectoryFormats") or []],
        "trajectoryFileCount": int(summary.get("trajectoryFileCount") or 0),
        "trajectorySizeBytes": int(summary.get("trajectorySizeBytes") or 0),
        "sourceSceneIds": [str(item) for item in summary.get("sourceSceneIds") or []],
        # Preserve the older external-result URLs in the historical ledger
        # while preferring controlled attachment relations for new missions.
        "resultAttachmentCount": (
            len(attachments)
            or len(record.get("resultAssetUrls") or [])
            or int(summary.get("resultAttachmentCount") or 0)
        ),
        "missingFields": missing_fields,
        "completeness": "incomplete" if missing_fields else "complete",
        "blocks": list(record.get("blocks") or []),
        "updatedAt": str(record.get("updatedAt") or ""),
    }


def update_mission_view(record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    return mission_view(update_mission(record, event))


@router.get("/missions")
def mission_ledger(
    q: str = Query(default=""), status: str = Query(default=""),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    device_id: str = Query(default="", alias="deviceId"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "drone.missions.view")
    if status:
        validate_enum(status, MISSION_STATUSES, "任务状态")
    scoped: list[dict[str, Any]] = []
    for record in list_missions(q, status, linked_block_code, device_id, include_deleted=include_deleted):
        try:
            require_mission_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(mission_view(record))
    return {"items": scoped[offset:offset + limit], "total": len(scoped), "limit": limit, "offset": offset}


@router.get("/missions-export.csv")
def export_missions(
    q: str = Query(default=""), status: str = Query(default=""),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    device_id: str = Query(default="", alias="deviceId"),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "drone.missions.view")
    rows = []
    for record in list_missions(q, status, linked_block_code, device_id):
        try:
            require_mission_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        rows.append(record)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["任务编号", "任务名称", "任务类型", "状态", "无人机编号", "无人机名称", "飞手", "航线", "林班", "计划开始", "计划结束", "实际开始", "实际结束", "成果数量", "更新时间"])
    for record in rows:
        writer.writerow([
            record["missionNo"], record["title"], record["missionType"], record["status"],
            record.get("deviceCode") or "", record.get("deviceName") or "", record.get("pilotName") or "",
            record.get("routeName") or "", "、".join(str(item.get("code") or "") for item in record.get("blocks") or []),
            record.get("plannedStartAt") or "", record.get("plannedEndAt") or "", record.get("actualStartAt") or "",
            record.get("actualEndAt") or "", len(linked_attachments("drone_mission", str(record["id"]), "result")) or len(record.get("resultAssetUrls") or []), record.get("updatedAt") or "",
        ])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="drone-missions.csv"'})


@router.get("/flights")
def flight_ledger(
    q: str = Query(default=""), origin: str = Query(default=""),
    completeness: str = Query(default=""), limit: int = Query(default=50, ge=1, le=10000),
    offset: int = Query(default=0, ge=0), context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "drone.missions.view")
    if origin and origin not in {"mission", "trajectory"}:
        raise HTTPException(status_code=422, detail="不支持的飞行记录来源。")
    if completeness and completeness not in {"complete", "incomplete"}:
        raise HTTPException(status_code=422, detail="不支持的资料完整性条件。")
    keyword = q.strip().lower()
    rows: list[dict[str, Any]] = []
    for mission in list_missions(include_deleted=False):
        if not mission.get("actualStartAt") and (mission.get("flightSummary") or {}).get("recordOrigin") != "trajectory-auto-import":
            continue
        try:
            require_mission_scope(mission, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        row = flight_record_view(mission)
        if origin and row["origin"] != origin:
            continue
        if completeness and row["completeness"] != completeness:
            continue
        haystack = " ".join([
            row["missionNo"], row["title"], row["deviceCode"], row["deviceName"],
            row["pilotName"], row["routeName"], " ".join(item.get("code", "") for item in row["blocks"]),
        ]).lower()
        if keyword and keyword not in haystack:
            continue
        rows.append(row)
    rows.sort(key=lambda item: item.get("actualStartAt") or item.get("updatedAt") or "", reverse=True)
    return {
        "items": rows[offset:offset + limit],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "summary": {
            "trajectoryImported": sum(1 for row in rows if row["origin"] == "trajectory"),
            "incomplete": sum(1 for row in rows if row["completeness"] == "incomplete"),
            "linkedResults": sum(
                1
                for row in rows
                if int(row.get("resultAttachmentCount") or 0) > 0 or bool(row.get("sourceSceneIds"))
            ),
        },
    }


@router.get("/flights-export.csv")
def export_flights(context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "drone.missions.view")
    response = flight_ledger(q="", origin="", completeness="", limit=10000, offset=0, context=context)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["飞行记录", "任务编号", "任务名称", "来源", "资料完整性", "无人机", "飞手", "航线", "实际起飞", "实际结束", "时长(分钟)", "航程(km)", "覆盖面积(亩)", "轨迹格式", "轨迹文件数", "成果数", "林班", "待补资料"])
    for row in response["items"]:
        writer.writerow([
            row["id"], row["missionNo"], row["title"], row["origin"], row["completeness"],
            " · ".join(value for value in [row["deviceName"], row["deviceCode"]] if value), row["pilotName"],
            row["routeName"], row["actualStartAt"] or "", row["actualEndAt"] or "", row["durationMinutes"],
            row["distanceKm"], row["coverageAreaMu"], "/".join(row["trajectoryFormats"]), row["trajectoryFileCount"],
            row["resultAttachmentCount"], "、".join(item.get("code", "") for item in row["blocks"]),
            "、".join(row["missingFields"]),
        ])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="drone-flights.csv"'})


@router.post("/missions")
def add_mission(payload: MissionCreate, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.create")
    device = validated_drone(payload.droneDeviceId, context)
    blocks = validated_blocks(payload.linkedBlockCodes, context)
    start = parse_timestamp(payload.plannedStartAt, "计划开始时间")
    end = parse_timestamp(payload.plannedEndAt, "计划结束时间")
    if datetime.fromisoformat(str(end)) <= datetime.fromisoformat(str(start)):
        raise HTTPException(status_code=422, detail="计划结束时间必须晚于开始时间。")
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), "missionNo": record_number(), "title": payload.title.strip(),
        "missionType": validate_enum(payload.missionType, MISSION_TYPES, "任务类型"), "status": "planned",
        "droneDeviceId": device["id"], "deviceCode": device["deviceCode"], "deviceName": device["name"],
        "pilotName": "", "routeName": "", "objective": payload.objective.strip(),
        "plannedStartAt": start, "plannedEndAt": end, "actualStartAt": None, "actualEndAt": None,
        "flightSummary": {}, "resultAssetUrls": [], "version": 1, "createdBy": context.user,
        "createdAt": now, "updatedAt": now, "closedAt": None, "deletedAt": None,
        "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks],
    }
    return mission_view(create_mission(record, timeline_entry("create", "", "planned", context.user, "无人机任务计划已建立。")))


@router.get("/missions/{mission_id}")
def mission_detail(mission_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.view")
    return mission_view(get_mission(mission_id, context))


@router.post("/missions/{mission_id}/restore")
def restore_deleted_mission(mission_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.create")
    record = get_mission(mission_id, context)
    if not record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="无人机任务未被删除。")
    if record["status"] not in {"planned", "cancelled"}:
        raise HTTPException(status_code=409, detail="已进入执行流程的任务不能从回收站恢复。")
    restore_mission(mission_id)
    return mission_view(mission_by_id(mission_id) or record)


@router.patch("/missions/{mission_id}")
def edit_mission(mission_id: str, payload: MissionPatch, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.create")
    record = get_mission(mission_id, context)
    if record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="已删除任务不能编辑。")
    if record["status"] != "planned":
        raise HTTPException(status_code=409, detail="只有待安排任务可以修改。")
    changes = payload.model_dump(exclude_unset=True)
    if "missionType" in changes:
        changes["missionType"] = validate_enum(changes["missionType"], MISSION_TYPES, "任务类型")
    if "droneDeviceId" in changes:
        device = validated_drone(changes["droneDeviceId"], context)
        changes.update({"droneDeviceId": device["id"], "deviceCode": device["deviceCode"], "deviceName": device["name"]})
    if "linkedBlockCodes" in changes:
        blocks = validated_blocks(changes.pop("linkedBlockCodes"), context)
        changes["blocks"] = [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks]
    start = parse_timestamp(str(changes.get("plannedStartAt") or record["plannedStartAt"]), "计划开始时间")
    end = parse_timestamp(str(changes.get("plannedEndAt") or record["plannedEndAt"]), "计划结束时间")
    if datetime.fromisoformat(str(end)) <= datetime.fromisoformat(str(start)):
        raise HTTPException(status_code=422, detail="计划结束时间必须晚于开始时间。")
    changes.update({"plannedStartAt": start, "plannedEndAt": end})
    return update_mission_view({**record, **changes}, timeline_entry("edit", "planned", "planned", context.user, "任务计划已修改。"))


@router.delete("/missions/{mission_id}")
def delete_mission(mission_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.create")
    record = get_mission(mission_id, context)
    if record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="无人机任务已经在回收站中。")
    if record["status"] not in {"planned", "cancelled"}:
        raise HTTPException(status_code=409, detail="已进入执行流程的任务不能删除，只能保留归档记录。")
    soft_delete_mission(mission_id)
    return {"ok": True, "deleted": record["missionNo"]}


@router.post("/missions/{mission_id}/actions/{action}")
def apply_mission_action(mission_id: str, action: str, payload: MissionAction, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    permission = {
        "assign": "drone.missions.dispatch", "start": "drone.missions.operate",
        "upload-result": "drone.missions.operate", "review": "drone.missions.review",
        "return": "drone.missions.review", "complete": "drone.missions.review",
        "cancel": "drone.missions.dispatch",
    }.get(action)
    if not permission:
        raise HTTPException(status_code=404, detail="不支持的无人机任务操作。")
    require_permission(context, permission)
    record = get_mission(mission_id, context)
    if record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="已删除任务不能执行流程操作。")
    status = str(record["status"])
    note = payload.note.strip()
    if action == "assign":
        if status != "planned":
            raise HTTPException(status_code=409, detail="只有待安排任务可以派发。")
        pilot = payload.pilotName.strip()
        route = payload.routeName.strip()
        if not pilot or not route:
            raise HTTPException(status_code=422, detail="派发时必须填写飞手和航线名称。")
        return update_mission_view({**record, "status": "assigned", "pilotName": pilot, "routeName": route}, timeline_entry(action, status, "assigned", context.user, note or f"任务已派给飞手 {pilot}。", {"pilotName": pilot, "routeName": route}))
    if action == "start":
        if status != "assigned":
            raise HTTPException(status_code=409, detail="只有已派发任务可以起飞。")
        device = validated_drone(str(record["droneDeviceId"]), context)
        if device.get("connectivityStatus") == "offline":
            raise HTTPException(status_code=409, detail="无人机当前离线，不能开始飞行。")
        started_at = utc_now()
        return update_mission_view({**record, "status": "flying", "actualStartAt": started_at}, timeline_entry(action, status, "flying", context.user, note or "无人机已起飞。", {"actualStartAt": started_at}))
    if action == "upload-result":
        if status != "flying":
            raise HTTPException(status_code=409, detail="只有飞行中的任务可以提交成果。")
        assets = compact(payload.resultAssetUrls)
        attachment_ids = compact(payload.resultAttachmentIds)
        if not attachment_ids and not assets:
            raise HTTPException(status_code=422, detail="至少需要从附件中心选择一个正式成果文件。")
        if attachment_ids:
            sync_attachment_links("drone_mission", mission_id, attachment_ids, context, relation_type="result")
            for block in record.get("blocks") or []:
                for attachment_id in attachment_ids:
                    create_attachment_link(AttachmentLinkIn(
                        attachmentId=attachment_id,
                        entityType="forest_block",
                        entityId=str(block["id"]),
                        relationType="drone_result",
                    ), context)
        ended_at = utc_now()
        summary = {
            "durationMinutes": payload.flightDurationMinutes,
            "distanceKm": payload.flightDistanceKm,
            "coverageAreaMu": payload.coverageAreaMu,
            "submittedBy": context.user,
            "submittedAt": ended_at,
            "resultAttachmentCount": len(attachment_ids),
        }
        return update_mission_view({**record, "status": "processing", "actualEndAt": ended_at, "flightSummary": summary, "resultAssetUrls": assets}, timeline_entry(action, status, "processing", context.user, note or "飞行成果已提交处理。", {**summary, "resultAttachmentIds": attachment_ids}))
    if action == "review":
        if status != "processing":
            raise HTTPException(status_code=409, detail="成果处理完成后才能复核。")
        review_note = payload.reviewNote.strip() or note
        return update_mission_view({**record, "status": "reviewed", "flightSummary": {**(record.get("flightSummary") or {}), "reviewedBy": context.user, "reviewedAt": utc_now(), "reviewNote": review_note}}, timeline_entry(action, status, "reviewed", context.user, review_note or "飞行成果复核通过。"))
    if action == "return":
        if status != "reviewed" or not note:
            raise HTTPException(status_code=409 if status != "reviewed" else 422, detail="当前任务不能退回，或尚未填写退回原因。")
        return update_mission_view({**record, "status": "processing"}, timeline_entry(action, status, "processing", context.user, note))
    if action == "complete":
        if status != "reviewed":
            raise HTTPException(status_code=409, detail="成果复核通过后才能归档。")
        closed_at = utc_now()
        return update_mission_view({**record, "status": "completed", "closedAt": closed_at}, timeline_entry(action, status, "completed", context.user, note or "无人机任务已归档。", {"closedAt": closed_at}))
    if status not in {"planned", "assigned"}:
        raise HTTPException(status_code=409, detail="当前任务已进入执行阶段，不能取消。")
    if not note:
        raise HTTPException(status_code=422, detail="取消任务时必须填写原因。")
    return update_mission_view({**record, "status": "cancelled", "closedAt": utc_now()}, timeline_entry(action, status, "cancelled", context.user, note))
