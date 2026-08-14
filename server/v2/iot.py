from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import has_permission, require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.equipment import (
    add_maintenance,
    device_by_id,
    device_by_code,
    list_devices,
    restore_device,
    save_device,
    soft_delete_device,
    utc_now,
)
from server.modules.drone import create_mission, list_missions, timeline_entry
from server.modules.forest_blocks import block_by_code, require_target_block_allowed


router = APIRouter(prefix="/iot", tags=["v2-iot"])
DEVICE_TYPES = {"drone", "helmet", "sensor", "camera", "machinery", "gateway", "other"}
DEVICE_STATUSES = {"active", "maintenance", "retired"}
CONNECTIVITY_STATUSES = {"online", "offline", "unknown"}
MAINTENANCE_TYPES = {"inspection", "repair", "calibration", "firmware", "battery", "other"}
SITUATION_KINDS = {"camera", "helmet", "dock"}


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    deviceType: str = "sensor"
    vendor: str = Field(default="", max_length=160)
    model: str = Field(default="", max_length=160)
    serialNo: str = Field(default="", max_length=160)
    status: str = "active"
    connectivityStatus: str = "unknown"
    ownerUnit: str = Field(default="", max_length=255)
    custodian: str = Field(default="", max_length=128)
    firmwareVersion: str = Field(default="", max_length=96)
    installedAt: str = ""
    lastSeenAt: str = ""
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    locationText: str = Field(default="", max_length=500)
    linkedBlockCodes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DevicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    deviceType: str | None = None
    vendor: str | None = Field(default=None, max_length=160)
    model: str | None = Field(default=None, max_length=160)
    serialNo: str | None = Field(default=None, max_length=160)
    status: str | None = None
    connectivityStatus: str | None = None
    ownerUnit: str | None = Field(default=None, max_length=255)
    custodian: str | None = Field(default=None, max_length=128)
    firmwareVersion: str | None = Field(default=None, max_length=96)
    installedAt: str | None = None
    lastSeenAt: str | None = None
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    locationText: str | None = Field(default=None, max_length=500)
    linkedBlockCodes: list[str] | None = None
    metadata: dict[str, Any] | None = None


class MaintenanceCreate(BaseModel):
    maintenanceType: str = "inspection"
    scheduledAt: str = ""
    completedAt: str = ""
    assigneeName: str = Field(default="", max_length=128)
    description: str = Field(min_length=1, max_length=5000)
    result: str = Field(default="", max_length=5000)


def record_number(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def validate_enum(value: str, allowed: set[str], label: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise HTTPException(status_code=422, detail=f"不支持的{label}。")
    return normalized


def parse_timestamp(value: str | None, label: str) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
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
    blocks: list[dict[str, Any]] = []
    for code in compact(codes):
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"林班 {code} 不存在或已删除。")
        require_target_block_allowed(context, block)
        blocks.append(block)
    return blocks


def require_device_scope(record: dict[str, Any], context: AuthContext) -> None:
    for link in record.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block:
            require_target_block_allowed(context, block)


def get_device(device_id: str, context: AuthContext, *, include_deleted: bool = False) -> dict[str, Any]:
    record = device_by_id(device_id, include_deleted=include_deleted)
    if not record:
        raise HTTPException(status_code=404, detail="设备不存在。")
    require_device_scope(record, context)
    return record


def situation_parameters(record: dict[str, Any]) -> list[list[str]]:
    metadata = record.get("metadata") or {}
    values = [
        ["设备编号", str(record.get("deviceCode") or "-")],
        ["规格型号", " / ".join(filter(None, [record.get("vendor"), record.get("model")])) or "待补充"],
        ["归属单位", str(record.get("ownerUnit") or "待补充")],
        ["责任人", str(record.get("custodian") or "待补充")],
        ["安装位置", str(record.get("locationText") or "待补充")],
    ]
    for label, key in (("电量", "battery"), ("网络状态", "network"), ("当前任务", "currentTask")):
        if metadata.get(key):
            values.append([label, str(metadata[key])])
    return values


@router.get("/situation-assets")
def situation_assets(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.view")
    items: list[dict[str, Any]] = []
    for record in list_devices(status="active"):
        metadata = record.get("metadata") or {}
        if not metadata.get("displayOnDashboard") or record.get("connectivityStatus") == "offline":
            continue
        try:
            require_device_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        kind = str(metadata.get("situationKind") or record.get("deviceType") or "")
        if kind not in SITUATION_KINDS:
            continue
        block_code = str((record.get("blocks") or [{}])[0].get("code") or "")
        if not block_code and (record.get("longitude") is None or record.get("latitude") is None):
            continue
        items.append({
            "id": str(record["id"]), "sourceType": "device", "kind": kind,
            "name": str(record.get("name") or record.get("deviceCode") or "设备"),
            "subtitle": f"{record.get('deviceCode')} · {record.get('locationText') or '位置待补'}",
            "status": "在线" if record.get("connectivityStatus") == "online" else "状态未知",
            "blockCode": block_code, "longitude": record.get("longitude"), "latitude": record.get("latitude"),
            "parameters": situation_parameters(record), "managementPath": "/v2/iot/devices",
        })
    if has_permission(context, "drone.missions.view"):
        for mission in list_missions():
            if mission.get("status") not in {"assigned", "flying", "processing"}:
                continue
            try:
                for link in mission.get("blocks") or []:
                    block = block_by_code(str(link.get("code") or ""))
                    if block:
                        require_target_block_allowed(context, block)
            except HTTPException as exc:
                if exc.status_code == 403:
                    continue
                raise
            block_code = str((mission.get("blocks") or [{}])[0].get("code") or "")
            if not block_code:
                continue
            summary = mission.get("flightSummary") or {}
            items.append({
                "id": str(mission["id"]), "sourceType": "mission", "kind": "mission",
                "name": str(mission.get("title") or mission.get("missionNo") or "无人机任务"),
                "subtitle": f"{mission.get('missionNo')} · 关联林班 {block_code}",
                "status": {"assigned": "待执行", "flying": "飞行中", "processing": "成果处理中"}.get(str(mission.get("status")), "执行中"),
                "blockCode": block_code, "longitude": None, "latitude": None,
                "parameters": [
                    ["执行无人机", str(mission.get("deviceName") or "待安排")],
                    ["飞手", str(mission.get("pilotName") or "待安排")],
                    ["航线", str(mission.get("routeName") or "待规划")],
                    ["飞行距离", f"{summary.get('flightDistanceKm')} km" if summary.get("flightDistanceKm") is not None else "回传中"],
                ],
                "managementPath": "/v2/drone/missions",
            })
    return {"items": items, "total": len(items), "source": "device-and-mission-ledgers"}


@router.post("/situation-assets/seed")
def seed_situation_assets(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.manage")
    require_permission(context, "drone.missions.create")
    definitions = [
        ("DEMO-CAM-HK-01", "camera", "camera", "黄坑镇新峰村高位卡口", "35078410620204107030", "双光谱云台", "PTZ-4K", {"network": "5G 专网 / 38 ms"}),
        ("DEMO-CAM-MS-02", "camera", "camera", "麻沙镇溪头村高位卡口", "35078410521800709060", "低照度球机", "IPC-8M", {"network": "光纤 / 22 ms"}),
        ("DEMO-HELMET-H07", "helmet", "helmet", "巡护员陈建平安全帽", "35078410620204207040", "竹山智联", "H07", {"battery": "76%", "currentTask": "新峰村林班巡查"}),
        ("DEMO-HELMET-H12", "helmet", "helmet", "护林员林志强安全帽", "35078410521800120020", "竹山智联", "H12", {"battery": "64%", "currentTask": "溪头村边界核查"}),
        ("DEMO-DOCK-HK-01", "gateway", "dock", "黄坑镇新峰村无人机机巢 01", "35078410620204403070", "竹山低空", "D-300", {"battery": "92%", "network": "专网在线"}),
        ("DEMO-UAV-MS-01", "drone", "", "麻沙镇巡检无人机 01", "35078410521800411040", "DJI", "M300 RTK", {"battery": "88%"}),
    ]
    created: list[str] = []
    existing: list[str] = []
    skipped: list[str] = []
    drone: dict[str, Any] | None = None
    now = utc_now()
    for code, device_type, situation_kind, name, block_code, vendor, model, extra in definitions:
        current = device_by_code(code)
        if current:
            existing.append(code)
            if device_type == "drone":
                drone = current
            continue
        block = block_by_code(block_code)
        if not block:
            skipped.append(code)
            continue
        require_target_block_allowed(context, block)
        metadata = {"demoData": True, "notes": "测试环境示范记录", **extra}
        if situation_kind:
            metadata.update({"displayOnDashboard": True, "situationKind": situation_kind})
        record = {
            "id": str(uuid.uuid4()), "deviceCode": code, "name": name, "deviceType": device_type,
            "vendor": vendor, "model": model, "serialNo": code, "status": "active", "connectivityStatus": "online",
            "ownerUnit": "智慧竹山测试运营中心", "custodian": "平台测试管理员", "firmwareVersion": "demo-1.0",
            "installedAt": now, "lastSeenAt": now, "longitude": None, "latitude": None,
            "locationText": f"关联林班 {block_code}", "metadata": metadata, "createdBy": context.user,
            "createdAt": now, "updatedAt": now, "deletedAt": None,
            "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"])}], "maintenance": [],
        }
        saved = save_device(record, create=True)
        created.append(code)
        if device_type == "drone":
            drone = saved
    mission_no = "DEMO-MISSION-MS-009"
    mission_exists = next((item for item in list_missions(query=mission_no, include_deleted=True) if item.get("missionNo") == mission_no), None)
    if drone and not mission_exists:
        block = block_by_code("35078410521800411040")
        if block:
            start = datetime.now(timezone.utc)
            mission = {
                "id": str(uuid.uuid4()), "missionNo": mission_no, "title": "麻沙镇溪头村正射巡检任务",
                "missionType": "mapping", "status": "flying", "droneDeviceId": drone["id"],
                "deviceCode": drone["deviceCode"], "deviceName": drone["name"], "pilotName": "示范飞手",
                "routeName": "溪头村正射航线", "objective": "测试环境大屏联动示范任务",
                "plannedStartAt": start.isoformat(), "plannedEndAt": (start + timedelta(hours=1)).isoformat(),
                "actualStartAt": start.isoformat(), "actualEndAt": None,
                "flightSummary": {"flightDistanceKm": 6.8, "progress": 68}, "resultAssetUrls": [],
                "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now,
                "closedAt": None, "deletedAt": None,
                "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"])}],
            }
            create_mission(mission, timeline_entry("seed", "", "flying", context.user, "测试环境示范任务已装载。"))
            created.append(mission_no)
    elif mission_exists:
        existing.append(mission_no)
    return {"ok": True, "created": created, "existing": existing, "skipped": skipped}


@router.get("/devices")
def device_ledger(
    q: str = Query(default=""), status: str = Query(default=""),
    device_type: str = Query(default="", alias="deviceType"),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "iot.devices.view")
    if status:
        validate_enum(status, DEVICE_STATUSES, "设备状态")
    if device_type:
        validate_enum(device_type, DEVICE_TYPES, "设备类型")
    scoped: list[dict[str, Any]] = []
    for record in list_devices(q, status, device_type, linked_block_code, include_deleted=include_deleted):
        try:
            require_device_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(record)
    return {"items": scoped[offset:offset + limit], "total": len(scoped), "limit": limit, "offset": offset}


@router.get("/devices/options")
def device_options(
    q: str = Query(default=""), device_type: str = Query(default="", alias="deviceType"),
    limit: int = Query(default=50, ge=1, le=200),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "iot.devices.view")
    if device_type:
        validate_enum(device_type, DEVICE_TYPES, "设备类型")
    records = []
    for record in list_devices(q, "active", device_type):
        try:
            require_device_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        records.append(record)
    return {"items": records[:limit], "total": len(records)}


def csv_response(filename: str, rows: list[list[Any]]) -> Response:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["设备编号", "设备名称", "设备类型", "台账状态", "连接状态", "厂商", "型号", "序列号", "归属单位", "责任人", "安装位置", "关联林班", "最后在线", "更新时间"])
    writer.writerows(rows)
    return Response(
        content="\ufeff" + stream.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/devices-export.csv")
def export_devices(
    q: str = Query(default=""), status: str = Query(default=""),
    device_type: str = Query(default="", alias="deviceType"),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "iot.devices.view")
    if status:
        validate_enum(status, DEVICE_STATUSES, "设备状态")
    if device_type:
        validate_enum(device_type, DEVICE_TYPES, "设备类型")
    scoped: list[dict[str, Any]] = []
    for record in list_devices(q, status, device_type, linked_block_code):
        try:
            require_device_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(record)
    return csv_response("iot-devices.csv", [[
        item["deviceCode"], item["name"], item["deviceType"], item["status"], item["connectivityStatus"],
        item.get("vendor") or "", item.get("model") or "", item.get("serialNo") or "",
        item.get("ownerUnit") or "", item.get("custodian") or "", item.get("locationText") or "",
        "、".join(block["code"] for block in item.get("blocks") or []), item.get("lastSeenAt") or "", item["updatedAt"],
    ] for item in scoped])


@router.post("/devices")
def create_device(payload: DeviceCreate, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.manage")
    blocks = validated_blocks(payload.linkedBlockCodes, context)
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), "deviceCode": record_number("SB"), "name": payload.name.strip(),
        "deviceType": validate_enum(payload.deviceType, DEVICE_TYPES, "设备类型"),
        "vendor": payload.vendor.strip(), "model": payload.model.strip(), "serialNo": payload.serialNo.strip(),
        "status": validate_enum(payload.status, DEVICE_STATUSES, "设备状态"),
        "connectivityStatus": validate_enum(payload.connectivityStatus, CONNECTIVITY_STATUSES, "在线状态"),
        "ownerUnit": payload.ownerUnit.strip(), "custodian": payload.custodian.strip(),
        "firmwareVersion": payload.firmwareVersion.strip(), "installedAt": parse_timestamp(payload.installedAt, "安装时间"),
        "lastSeenAt": parse_timestamp(payload.lastSeenAt, "最后在线时间"), "longitude": payload.longitude,
        "latitude": payload.latitude, "locationText": payload.locationText.strip(), "metadata": payload.metadata,
        "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
        "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks],
        "maintenance": [],
    }
    return save_device(record, create=True)


@router.get("/devices/{device_id}")
def device_detail(device_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.view")
    return get_device(device_id, context)


@router.patch("/devices/{device_id}")
def edit_device(device_id: str, payload: DevicePatch, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.manage")
    record = get_device(device_id, context)
    changes = payload.model_dump(exclude_unset=True)
    if "deviceType" in changes:
        changes["deviceType"] = validate_enum(changes["deviceType"], DEVICE_TYPES, "设备类型")
    if "status" in changes:
        changes["status"] = validate_enum(changes["status"], DEVICE_STATUSES, "设备状态")
    if "connectivityStatus" in changes:
        changes["connectivityStatus"] = validate_enum(changes["connectivityStatus"], CONNECTIVITY_STATUSES, "在线状态")
    for key, label in (("installedAt", "安装时间"), ("lastSeenAt", "最后在线时间")):
        if key in changes:
            changes[key] = parse_timestamp(changes[key], label)
    if "linkedBlockCodes" in changes:
        blocks = validated_blocks(changes.pop("linkedBlockCodes"), context)
        changes["blocks"] = [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks]
    return save_device({**record, **changes, "updatedAt": utc_now()}, create=False)


@router.delete("/devices/{device_id}")
def delete_device(device_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.manage")
    record = get_device(device_id, context)
    if not soft_delete_device(device_id):
        raise HTTPException(status_code=404, detail="设备不存在。")
    return {"ok": True, "deleted": record["deviceCode"]}


@router.post("/devices/{device_id}/restore")
def restore_deleted_device(device_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.manage")
    record = get_device(device_id, context, include_deleted=True)
    if not record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="设备未处于回收站。")
    restored = restore_device(device_id)
    if not restored:
        raise HTTPException(status_code=404, detail="设备不存在。")
    return restored


@router.post("/devices/{device_id}/maintenance")
def create_maintenance(device_id: str, payload: MaintenanceCreate, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.maintain")
    get_device(device_id, context)
    maintenance_type = validate_enum(payload.maintenanceType, MAINTENANCE_TYPES, "维护类型")
    now = utc_now()
    completed_at = parse_timestamp(payload.completedAt, "完成时间")
    record = {
        "id": str(uuid.uuid4()), "workOrderNo": record_number("WX"), "maintenanceType": maintenance_type,
        "status": "completed" if completed_at else "planned", "scheduledAt": parse_timestamp(payload.scheduledAt, "计划时间"),
        "completedAt": completed_at, "assigneeName": payload.assigneeName.strip(),
        "description": payload.description.strip(), "result": payload.result.strip(),
        "createdBy": context.user, "createdAt": now, "updatedAt": now,
    }
    add_maintenance(device_id, record)
    return get_device(device_id, context)
