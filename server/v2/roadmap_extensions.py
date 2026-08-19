from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from shapely.geometry import LineString, Point, shape

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.equipment import save_device
from server.modules.extension_store import (
    extension_record_by_id,
    extension_record_by_idempotency_key,
    list_extension_records,
    save_extension_record,
    utc_now,
)
from server.modules.forest_blocks import block_by_code, require_target_block_allowed
from server.modules.labor import list_jobs
from server.v2.iot import get_device


router = APIRouter(tags=["v2-roadmap-extensions"])
TELEMETRY = "iot-telemetry"
COMMANDS = "iot-commands"
DEVICE_LIFECYCLE = "iot-device-lifecycle"
IOT_WORK_ORDERS = "iot-alert-work-orders"
ADAPTERS = "integration-adapters"
ROUTES = "drone-routes"
NO_FLY_ZONES = "drone-no-fly-zones"
PILOTS = "drone-pilots"
BATTERIES = "drone-batteries"
STREAM_SESSIONS = "video-stream-sessions"
MODEL_RELEASES = "ai-model-releases"
DEPLOYMENTS = "ai-deployments"
EVALUATIONS = "ai-evaluations"
DATASETS = "ai-datasets"
ANNOTATIONS = "ai-annotations"
TRAINING_JOBS = "ai-training-jobs"
LABOR_COMPANIES = "labor-companies"
CONTRACT_TEMPLATES = "labor-contract-templates"
HELMET_BINDINGS = "labor-helmet-bindings"
ATTENDANCE_VERIFICATIONS = "labor-attendance-verifications"
TRAINING_COURSES = "labor-training-courses"
QUESTION_BANK = "labor-training-questions"
EXAMS = "labor-training-exams"
CERTIFICATES = "labor-certificates"
HARVEST_ALLOCATIONS = "harvest-quota-allocations"
HARVEST_CHECKS = "harvest-compliance-checks"


def new_record(context: AuthContext, payload: dict[str, Any], *, idempotency_key: str = "", area_code: str = "") -> dict[str, Any]:
    now = utc_now()
    return {
        "id": str(uuid.uuid4()), **payload, "areaCode": area_code, "idempotencyKey": idempotency_key,
        "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
    }


def visible_areas(context: AuthContext) -> set[str]:
    return set(context.areas or {"*"})


def items(collection: str, context: AuthContext, **filters: str) -> dict[str, Any]:
    records = list_extension_records(collection, area_codes=visible_areas(context))
    for key, value in filters.items():
        if value:
            records = [record for record in records if str(record.get(key) or "") == value]
    return {"items": records, "total": len(records)}


def device_area_code(device: dict[str, Any]) -> str:
    for link in device.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block and block.get("countyCode"):
            return str(block["countyCode"])
    return ""


class AdapterPayload(BaseModel):
    adapterType: Literal["mqtt", "http", "onvif", "rtsp", "gb28181", "flight-control", "model-runtime"]
    name: str = Field(min_length=1, max_length=160)
    endpoint: str = Field(min_length=1, max_length=500)
    credentialRef: str = Field(default="", max_length=255)
    vendor: str = Field(default="", max_length=160)
    enabled: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)


@router.get("/integrations/adapters")
def integration_adapters(adapterType: str = "", context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.view")
    return items(ADAPTERS, context, adapterType=adapterType)


@router.post("/integrations/adapters", status_code=201)
def create_integration_adapter(payload: AdapterPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.manage")
    record = new_record(context, payload.model_dump())
    record["status"] = "configured" if payload.enabled else "disabled"
    record["lastHealthCheckAt"] = None
    record["lastHealthStatus"] = "not-checked"
    return save_extension_record(ADAPTERS, record, create=True)


class TelemetryPayload(BaseModel):
    deviceId: str
    collectedAt: datetime
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    batteryPct: float | None = Field(default=None, ge=0, le=100)
    signalDbm: float | None = None
    sequence: int | None = Field(default=None, ge=0)
    metrics: dict[str, Any] = Field(default_factory=dict)
    rawMessageRef: str = Field(default="", max_length=500)
    protocol: Literal["mqtt", "http", "device-sdk"] = "http"


@router.post("/iot/telemetry", status_code=202)
def ingest_telemetry(
    payload: TelemetryPayload,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "iot.devices.manage")
    existing = extension_record_by_idempotency_key(TELEMETRY, idempotency_key)
    if existing:
        get_device(str(existing.get("deviceId") or ""), context)
        return {**existing, "duplicate": True}
    device = get_device(payload.deviceId, context)
    previous = next((record for record in list_extension_records(TELEMETRY) if record.get("deviceId") == payload.deviceId), None)
    quality_flags: list[str] = []
    if previous and str(previous.get("collectedAt") or "") > payload.collectedAt.isoformat():
        quality_flags.append("out-of-order")
    if previous and payload.sequence is not None and previous.get("sequence") is not None and payload.sequence <= int(previous["sequence"]):
        quality_flags.append("sequence-regression")
    if payload.longitude is None or payload.latitude is None:
        quality_flags.append("location-missing")
    record = new_record(
        context, payload.model_dump(mode="json"), idempotency_key=idempotency_key,
        area_code=device_area_code(device),
    )
    record.update({"qualityStatus": "warning" if quality_flags else "valid", "qualityFlags": quality_flags, "duplicate": False})
    saved = save_extension_record(TELEMETRY, record, create=True)
    alert_code = str(payload.metrics.get("alertCode") or "")
    geofence_alert = device.get("deviceType") == "helmet" and payload.metrics.get("insideGeofence") is False
    if alert_code or geofence_alert:
        save_extension_record(
            IOT_WORK_ORDERS,
            new_record(
                context,
                {
                    "workOrderNo": f"IOT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
                    "deviceId": payload.deviceId, "telemetryId": saved["id"],
                    "alertCode": alert_code or "helmet-geofence-exit", "status": "open", "priority": "high" if geofence_alert else "normal",
                    "location": {"longitude": payload.longitude, "latitude": payload.latitude},
                    "metrics": payload.metrics, "timeline": [{"action": "created-from-telemetry", "at": utc_now(), "actor": context.user}],
                },
                idempotency_key=f"telemetry-alert:{saved['id']}",
                area_code=device_area_code(device),
            ),
            create=True,
        )
    device.update({
        "lastSeenAt": payload.collectedAt.isoformat(), "connectivityStatus": "online",
        "longitude": payload.longitude if payload.longitude is not None else device.get("longitude"),
        "latitude": payload.latitude if payload.latitude is not None else device.get("latitude"),
        "updatedAt": utc_now(),
        "metadata": {**(device.get("metadata") or {}), "batteryPct": payload.batteryPct, "signalDbm": payload.signalDbm, "lastTelemetryId": saved["id"]},
    })
    save_device(device, create=False)
    return saved


class DeviceLifecyclePayload(BaseModel):
    eventType: Literal["purchased", "received", "installed", "assigned", "maintained", "retired", "disposed"]
    occurredAt: datetime
    documentNo: str = Field(default="", max_length=96)
    ownerUnit: str = Field(default="", max_length=255)
    custodian: str = Field(default="", max_length=128)
    note: str = Field(default="", max_length=2000)


@router.get("/iot/devices/{device_id}/lifecycle")
def device_lifecycle(device_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.view")
    get_device(device_id, context, include_deleted=True)
    records = [record for record in list_extension_records(DEVICE_LIFECYCLE) if record.get("deviceId") == device_id]
    return {"items": records, "total": len(records)}


@router.post("/iot/devices/{device_id}/lifecycle", status_code=201)
def add_device_lifecycle_event(
    device_id: str, payload: DeviceLifecyclePayload, context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "iot.devices.manage")
    device = get_device(device_id, context, include_deleted=True)
    record = save_extension_record(
        DEVICE_LIFECYCLE,
        new_record(context, {**payload.model_dump(mode="json"), "deviceId": device_id}, area_code=device_area_code(device)),
        create=True,
    )
    if payload.eventType in {"retired", "disposed"} and not device.get("deletedAt"):
        device.update({"status": "retired", "connectivityStatus": "offline", "updatedAt": utc_now()})
        save_device(device, create=False)
    elif payload.eventType == "assigned":
        device.update({"ownerUnit": payload.ownerUnit or device.get("ownerUnit"), "custodian": payload.custodian or device.get("custodian"), "updatedAt": utc_now()})
        save_device(device, create=False)
    return record


@router.get("/iot/work-orders")
def iot_work_orders(status: str = "", context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.view")
    return items(IOT_WORK_ORDERS, context, status=status)


@router.get("/iot/telemetry")
def telemetry_ledger(
    deviceId: str = "", qualityStatus: str = "", limit: int = Query(default=200, ge=1, le=1000),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "iot.devices.view")
    records = list_extension_records(TELEMETRY, area_codes=visible_areas(context))
    if deviceId:
        records = [record for record in records if record.get("deviceId") == deviceId]
    if qualityStatus:
        records = [record for record in records if record.get("qualityStatus") == qualityStatus]
    return {"items": records[:limit], "total": len(records)}


class CommandPayload(BaseModel):
    deviceId: str
    commandType: Literal["reboot", "return-home", "start-stream", "stop-stream", "set-parameter", "firmware-upgrade"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    expiresAt: datetime


class CommandReceipt(BaseModel):
    status: Literal["acknowledged", "failed"]
    receiptCode: str = Field(default="", max_length=128)
    message: str = Field(default="", max_length=1000)
    receivedAt: datetime


@router.post("/iot/commands", status_code=202)
def send_command(payload: CommandPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.manage")
    device = get_device(payload.deviceId, context)
    expires_at = payload.expiresAt
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="命令过期时间必须晚于当前时间。")
    record = new_record(context, payload.model_dump(mode="json"), area_code=device_area_code(device))
    record.update({"status": "sent", "sentAt": utc_now(), "receiptAt": None, "deliveryMode": "outbox", "attempts": 1})
    return save_extension_record(COMMANDS, record, create=True)


@router.get("/iot/commands")
def command_ledger(deviceId: str = "", status: str = "", context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.view")
    records = list_extension_records(COMMANDS, area_codes=visible_areas(context))
    now = datetime.now(timezone.utc)
    for record in records:
        if record.get("status") == "sent" and datetime.fromisoformat(str(record["expiresAt"]).replace("Z", "+00:00")) < now:
            record.update({"status": "timed_out", "updatedAt": utc_now(), "version": int(record.get("version") or 1) + 1})
            save_extension_record(COMMANDS, record, create=False)
    if deviceId:
        records = [record for record in records if record.get("deviceId") == deviceId]
    if status:
        records = [record for record in records if record.get("status") == status]
    return {"items": records, "total": len(records)}


@router.post("/iot/commands/{command_id}/receipt")
def receive_command_receipt(command_id: str, payload: CommandReceipt, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.manage")
    record = extension_record_by_id(COMMANDS, command_id)
    if not record:
        raise HTTPException(status_code=404, detail="控制命令不存在。")
    get_device(str(record.get("deviceId") or ""), context)
    if record.get("status") not in {"sent", "timed_out"}:
        raise HTTPException(status_code=409, detail="控制命令已完成回执。")
    record.update({
        "status": payload.status, "receiptCode": payload.receiptCode, "receiptMessage": payload.message,
        "receiptAt": payload.receivedAt.isoformat(), "updatedAt": utc_now(), "version": int(record.get("version") or 1) + 1,
    })
    return save_extension_record(COMMANDS, record, create=False)


class NoFlyZonePayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    geometry: dict[str, Any]
    reason: str = Field(default="", max_length=1000)
    effectiveFrom: datetime | None = None
    effectiveTo: datetime | None = None


class DroneRoutePayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    routeType: Literal["DOM", "DEM", "inspection", "emergency"] = "DOM"
    blockCodes: list[str] = Field(min_length=1)
    waypoints: list[dict[str, float]] = Field(min_length=2, max_length=5000)
    altitudeM: float = Field(gt=0, le=1000)
    overlapPct: float | None = Field(default=None, ge=0, le=100)


@router.post("/drone/no-fly-zones", status_code=201)
def create_no_fly_zone(payload: NoFlyZonePayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.manage")
    try:
        geometry = shape(payload.geometry)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="禁飞区几何无效。") from exc
    if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise HTTPException(status_code=422, detail="禁飞区必须是有效面范围。")
    return save_extension_record(NO_FLY_ZONES, new_record(context, payload.model_dump(mode="json")), create=True)


@router.get("/drone/no-fly-zones")
def no_fly_zones(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.view")
    return items(NO_FLY_ZONES, context)


@router.post("/drone/routes", status_code=201)
def create_drone_route(payload: DroneRoutePayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.manage")
    area_code = ""
    for code in payload.blockCodes:
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"林班 {code} 不存在。")
        require_target_block_allowed(context, block)
        area_code = area_code or str(block.get("countyCode") or "")
    try:
        route = LineString([(float(point["longitude"]), float(point["latitude"])) for point in payload.waypoints])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="航点必须包含 longitude 和 latitude。") from exc
    conflicts = []
    for zone in list_extension_records(NO_FLY_ZONES):
        if route.intersects(shape(zone["geometry"])):
            conflicts.append({"zoneId": zone["id"], "name": zone["name"], "reason": zone.get("reason")})
    if conflicts:
        raise HTTPException(status_code=409, detail={"message": "航线穿越禁飞区，请调整航点。", "conflicts": conflicts})
    distance = 0.0
    coordinates = list(route.coords)
    for index in range(1, len(coordinates)):
        distance += Point(coordinates[index - 1]).distance(Point(coordinates[index])) * 111.0
    record = new_record(context, payload.model_dump(), area_code=area_code)
    record.update({"status": "validated", "distanceKmEstimate": round(distance, 3), "noFlyConflictCount": 0})
    return save_extension_record(ROUTES, record, create=True)


@router.get("/drone/routes")
def drone_routes(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.view")
    return items(ROUTES, context)


class VideoSessionPayload(BaseModel):
    deviceIds: list[str] = Field(min_length=1, max_length=8)
    protocol: Literal["rtsp", "gb28181", "onvif"]
    layout: Literal["1", "4", "6", "8"] = "4"


@router.post("/iot/video-sessions", status_code=201)
def create_video_session(payload: VideoSessionPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "iot.devices.view")
    devices = [get_device(device_id, context) for device_id in payload.deviceIds]
    adapter = next((item for item in list_extension_records(ADAPTERS) if item.get("adapterType") == payload.protocol and item.get("enabled")), None)
    record = new_record(context, payload.model_dump(), area_code=device_area_code(devices[0]))
    record.update({
        "status": "ready" if adapter else "waiting-adapter", "adapterId": adapter["id"] if adapter else "",
        "streamCount": len(payload.deviceIds), "playbackUrls": [],
    })
    return save_extension_record(STREAM_SESSIONS, record, create=True)


class PilotPayload(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    mobile: str = Field(default="", max_length=32)
    certificateNo: str = Field(min_length=1, max_length=96)
    certificateExpiresOn: date
    qualificationType: str = Field(min_length=1, max_length=96)


class BatteryPayload(BaseModel):
    batteryCode: str = Field(min_length=1, max_length=96)
    model: str = Field(default="", max_length=160)
    cycleCount: int = Field(default=0, ge=0)
    healthPct: float = Field(default=100, ge=0, le=100)
    purchasedOn: date | None = None
    expiresOn: date | None = None


@router.get("/drone/pilots")
def pilots(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.view")
    return items(PILOTS, context)


@router.post("/drone/pilots", status_code=201)
def create_pilot(payload: PilotPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.manage")
    return save_extension_record(PILOTS, new_record(context, payload.model_dump(mode="json")), create=True)


@router.get("/drone/batteries")
def batteries(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.view")
    return items(BATTERIES, context)


@router.post("/drone/batteries", status_code=201)
def create_battery(payload: BatteryPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.manage")
    return save_extension_record(BATTERIES, new_record(context, payload.model_dump(mode="json")), create=True)


@router.get("/drone/expiry-alerts")
def drone_expiry_alerts(days: int = Query(default=30, ge=0, le=365), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "drone.missions.view")
    today = date.today()
    records = []
    for collection, field, kind in ((PILOTS, "certificateExpiresOn", "pilot-certificate"), (BATTERIES, "expiresOn", "battery")):
        for record in list_extension_records(collection):
            if record.get(field):
                remaining = (date.fromisoformat(str(record[field])) - today).days
                if remaining <= days:
                    records.append({"kind": kind, "recordId": record["id"], "name": record.get("name") or record.get("batteryCode"), "expiresOn": record[field], "daysRemaining": remaining, "level": "expired" if remaining < 0 else "warning"})
    return {"items": records, "total": len(records)}


class ModelReleasePayload(BaseModel):
    modelAssetId: str
    capability: Literal["resource-recognition", "growth-yield", "pest-risk", "carbon", "harvest-compliance", "dispatch"]
    version: str = Field(min_length=1, max_length=64)
    artifactUri: str = Field(min_length=1, max_length=1000)
    checksum: str = Field(min_length=8, max_length=128)
    runtime: str = Field(default="", max_length=96)
    metrics: dict[str, float] = Field(default_factory=dict)


@router.get("/ai/lifecycle/releases")
def model_releases(capability: str = "", context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.view")
    return items(MODEL_RELEASES, context, capability=capability)


@router.post("/ai/lifecycle/releases", status_code=201)
def create_model_release(payload: ModelReleasePayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    if any(item.get("modelAssetId") == payload.modelAssetId and item.get("version") == payload.version for item in list_extension_records(MODEL_RELEASES)):
        raise HTTPException(status_code=409, detail="模型发布版本已存在。")
    record = new_record(context, payload.model_dump())
    record.update({"status": "registered", "immutable": True})
    return save_extension_record(MODEL_RELEASES, record, create=True)


class DeploymentPayload(BaseModel):
    releaseId: str
    environment: Literal["test", "staging", "production"] = "test"
    strategy: Literal["full", "canary", "shadow"] = "canary"
    trafficPct: int = Field(default=10, ge=0, le=100)


class DeploymentAction(BaseModel):
    action: Literal["promote", "rollback", "pause"]
    targetReleaseId: str = ""
    note: str = Field(default="", max_length=1000)
    expectedVersion: int = Field(ge=1)


@router.get("/ai/lifecycle/deployments")
def deployments(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.view")
    return items(DEPLOYMENTS, context)


@router.post("/ai/lifecycle/deployments", status_code=201)
def create_deployment(payload: DeploymentPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    release = extension_record_by_id(MODEL_RELEASES, payload.releaseId)
    if not release:
        raise HTTPException(status_code=422, detail="模型发布版本不存在。")
    record = new_record(context, payload.model_dump())
    record.update({"capability": release["capability"], "status": "active", "previousReleaseId": "", "timeline": [{"action": "deploy", "at": utc_now(), "actor": context.user}]})
    return save_extension_record(DEPLOYMENTS, record, create=True)


@router.post("/ai/lifecycle/deployments/{deployment_id}/actions")
def deployment_action(deployment_id: str, payload: DeploymentAction, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    record = extension_record_by_id(DEPLOYMENTS, deployment_id)
    if not record:
        raise HTTPException(status_code=404, detail="模型部署不存在。")
    if int(record.get("version") or 1) != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="模型部署已更新，请刷新后重试。")
    if payload.action == "rollback":
        target = payload.targetReleaseId or record.get("previousReleaseId")
        if not target or not extension_record_by_id(MODEL_RELEASES, str(target)):
            raise HTTPException(status_code=422, detail="缺少有效的回滚目标版本。")
        record["previousReleaseId"] = record["releaseId"]
        record["releaseId"] = target
        record["status"] = "active"
    elif payload.action == "promote":
        record.update({"strategy": "full", "trafficPct": 100, "status": "active"})
    else:
        record["status"] = "paused"
    record.setdefault("timeline", []).append({"action": payload.action, "at": utc_now(), "actor": context.user, "note": payload.note})
    record.update({"version": int(record.get("version") or 1) + 1, "updatedAt": utc_now()})
    return save_extension_record(DEPLOYMENTS, record, create=False)


class EvaluationPayload(BaseModel):
    releaseId: str
    sampleSize: int = Field(gt=0)
    reviewedCount: int = Field(ge=0)
    metrics: dict[str, float]
    baselineMetrics: dict[str, float] = Field(default_factory=dict)
    minimumMetrics: dict[str, float] = Field(default_factory=dict)
    evaluatedAt: datetime


@router.post("/ai/lifecycle/evaluations", status_code=201)
def create_evaluation(payload: EvaluationPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    if not extension_record_by_id(MODEL_RELEASES, payload.releaseId):
        raise HTTPException(status_code=422, detail="模型发布版本不存在。")
    alerts = [
        {"metric": metric, "actual": payload.metrics.get(metric), "minimum": minimum, "level": "warning"}
        for metric, minimum in payload.minimumMetrics.items()
        if payload.metrics.get(metric) is None or payload.metrics[metric] < minimum
    ]
    record = new_record(context, payload.model_dump(mode="json"))
    record.update({"status": "degraded" if alerts else "passed", "alerts": alerts})
    return save_extension_record(EVALUATIONS, record, create=True)


class DatasetPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    capability: str = Field(min_length=1, max_length=64)
    taskType: Literal["bounding-box", "classification"]
    sourceUri: str = Field(min_length=1, max_length=1000)
    labelSchema: dict[str, Any] = Field(default_factory=dict)


class AnnotationPayload(BaseModel):
    datasetId: str
    imageRef: str = Field(min_length=1, max_length=1000)
    annotationType: Literal["bounding-box", "classification"]
    labels: list[dict[str, Any]] = Field(min_length=1)
    status: Literal["draft", "submitted", "approved", "rejected"] = "submitted"


class TrainingPayload(BaseModel):
    datasetId: str
    baseReleaseId: str = ""
    capability: str = Field(min_length=1, max_length=64)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)


@router.get("/ai/lifecycle/datasets")
def datasets(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.view")
    return items(DATASETS, context)


@router.post("/ai/lifecycle/datasets", status_code=201)
def create_dataset(payload: DatasetPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    record = new_record(context, payload.model_dump())
    record.update({"status": "labeling", "annotationCount": 0})
    return save_extension_record(DATASETS, record, create=True)


@router.post("/ai/lifecycle/annotations", status_code=201)
def create_annotation(payload: AnnotationPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    dataset = extension_record_by_id(DATASETS, payload.datasetId)
    if not dataset:
        raise HTTPException(status_code=422, detail="标注数据集不存在。")
    record = save_extension_record(ANNOTATIONS, new_record(context, payload.model_dump()), create=True)
    dataset.update({"annotationCount": int(dataset.get("annotationCount") or 0) + 1, "updatedAt": utc_now(), "version": int(dataset.get("version") or 1) + 1})
    save_extension_record(DATASETS, dataset, create=False)
    return record


@router.post("/ai/lifecycle/training-jobs", status_code=201)
def create_training_job(payload: TrainingPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    dataset = extension_record_by_id(DATASETS, payload.datasetId)
    if not dataset or int(dataset.get("annotationCount") or 0) == 0:
        raise HTTPException(status_code=422, detail="训练数据集不存在或尚无标注。")
    record = new_record(context, payload.model_dump())
    record.update({"status": "queued", "progressPct": 0, "logs": [], "outputReleaseId": ""})
    return save_extension_record(TRAINING_JOBS, record, create=True)


@router.get("/ai/lifecycle/training-jobs")
def training_jobs(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.view")
    return items(TRAINING_JOBS, context)


class TrainingJobAction(BaseModel):
    status: Literal["running", "succeeded", "failed", "cancelled"]
    progressPct: int = Field(default=0, ge=0, le=100)
    log: str = Field(default="", max_length=4000)
    outputReleaseId: str = ""
    expectedVersion: int = Field(ge=1)


@router.post("/ai/lifecycle/training-jobs/{job_id}/actions")
def update_training_job(
    job_id: str, payload: TrainingJobAction, context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    record = extension_record_by_id(TRAINING_JOBS, job_id)
    if not record:
        raise HTTPException(status_code=404, detail="微调训练任务不存在。")
    if int(record.get("version") or 1) != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="训练任务已更新，请刷新后重试。")
    transitions = {"queued": {"running", "cancelled"}, "running": {"succeeded", "failed", "cancelled"}}
    if payload.status not in transitions.get(str(record.get("status")), set()):
        raise HTTPException(status_code=409, detail="训练任务状态不可执行该变更。")
    if payload.status == "succeeded" and (not payload.outputReleaseId or not extension_record_by_id(MODEL_RELEASES, payload.outputReleaseId)):
        raise HTTPException(status_code=422, detail="训练成功时必须关联已登记的产出模型版本。")
    record.setdefault("logs", []).append({"at": utc_now(), "actor": context.user, "message": payload.log, "status": payload.status})
    record.update({
        "status": payload.status, "progressPct": 100 if payload.status == "succeeded" else payload.progressPct,
        "outputReleaseId": payload.outputReleaseId or record.get("outputReleaseId") or "",
        "finishedAt": utc_now() if payload.status in {"succeeded", "failed", "cancelled"} else None,
        "version": int(record.get("version") or 1) + 1, "updatedAt": utc_now(),
    })
    return save_extension_record(TRAINING_JOBS, record, create=False)


class LaborCompanyPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    unifiedCreditCode: str = Field(min_length=1, max_length=64)
    contactName: str = Field(default="", max_length=128)
    contactPhone: str = Field(default="", max_length=32)
    licenseExpiresOn: date | None = None


class ContractTemplatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    templateVersion: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=50000)
    effectiveFrom: date
    effectiveTo: date | None = None


class HelmetBindingPayload(BaseModel):
    workerId: str
    deviceId: str
    effectiveFrom: datetime
    effectiveTo: datetime | None = None


@router.get("/labor/companies")
def labor_companies(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.view")
    return items(LABOR_COMPANIES, context)


@router.post("/labor/companies", status_code=201)
def create_labor_company(payload: LaborCompanyPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.manage")
    return save_extension_record(LABOR_COMPANIES, new_record(context, payload.model_dump(mode="json")), create=True)


@router.get("/labor/contract-templates")
def contract_templates(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.view")
    return items(CONTRACT_TEMPLATES, context)


@router.post("/labor/contract-templates", status_code=201)
def create_contract_template(payload: ContractTemplatePayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.manage")
    if payload.effectiveTo and payload.effectiveTo < payload.effectiveFrom:
        raise HTTPException(status_code=422, detail="模板失效日期不能早于生效日期。")
    return save_extension_record(CONTRACT_TEMPLATES, new_record(context, payload.model_dump(mode="json")), create=True)


@router.post("/labor/helmet-bindings", status_code=201)
def bind_helmet(payload: HelmetBindingPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.workers.manage")
    device = get_device(payload.deviceId, context)
    if device.get("deviceType") != "helmet":
        raise HTTPException(status_code=422, detail="绑定设备必须是已登记的安全帽。")
    active = [record for record in list_extension_records(HELMET_BINDINGS) if record.get("deviceId") == payload.deviceId and not record.get("effectiveTo")]
    if active:
        raise HTTPException(status_code=409, detail="安全帽已绑定其他人员。")
    record = new_record(context, payload.model_dump(mode="json"), area_code=device_area_code(device))
    record.update({"qrCode": f"worker:{payload.workerId}", "status": "active"})
    return save_extension_record(HELMET_BINDINGS, record, create=True)


class AttendanceReviewPayload(BaseModel):
    action: Literal["confirm", "reject"]
    note: str = Field(min_length=2, max_length=1000)
    expectedVersion: int = Field(ge=1)


@router.get("/labor/attendance-verifications")
def attendance_verifications(
    reviewStatus: str = "", context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "labor.view")
    return items(ATTENDANCE_VERIFICATIONS, context, reviewStatus=reviewStatus)


@router.post("/labor/attendance-verifications/{verification_id}/actions")
def review_attendance_verification(
    verification_id: str, payload: AttendanceReviewPayload,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "labor.jobs.operate")
    record = extension_record_by_id(ATTENDANCE_VERIFICATIONS, verification_id)
    if not record:
        raise HTTPException(status_code=404, detail="考勤核验记录不存在。")
    if int(record.get("version") or 1) != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="考勤核验记录已更新，请刷新后重试。")
    if record.get("reviewStatus") != "pending":
        raise HTTPException(status_code=409, detail="仅待复核异常可以处理。")
    record.update({
        "reviewStatus": "confirmed" if payload.action == "confirm" else "rejected",
        "reviewNote": payload.note, "reviewedBy": context.user, "reviewedAt": utc_now(),
        "version": int(record.get("version") or 1) + 1, "updatedAt": utc_now(),
    })
    return save_extension_record(ATTENDANCE_VERIFICATIONS, record, create=False)


class TrainingCoursePayload(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=96)
    durationMinutes: int = Field(gt=0)
    passingScore: float = Field(default=80, ge=0, le=100)
    validityMonths: int = Field(default=12, ge=1, le=120)
    contentUri: str = Field(default="", max_length=1000)


class TrainingQuestionPayload(BaseModel):
    courseId: str
    questionType: Literal["single-choice", "multiple-choice", "true-false"]
    stem: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(min_length=2, max_length=10)
    answers: list[int] = Field(min_length=1)
    score: float = Field(gt=0, le=100)


class ExamPayload(BaseModel):
    courseId: str
    workerId: str
    answers: dict[str, list[int]]


@router.get("/labor/training/courses")
def training_courses(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.view")
    return items(TRAINING_COURSES, context)


@router.post("/labor/training/courses", status_code=201)
def create_training_course(payload: TrainingCoursePayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.manage")
    record = new_record(context, payload.model_dump())
    record.update({"status": "published"})
    return save_extension_record(TRAINING_COURSES, record, create=True)


@router.post("/labor/training/questions", status_code=201)
def create_training_question(payload: TrainingQuestionPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.manage")
    if not extension_record_by_id(TRAINING_COURSES, payload.courseId):
        raise HTTPException(status_code=422, detail="培训课程不存在。")
    if any(answer < 0 or answer >= len(payload.options) for answer in payload.answers):
        raise HTTPException(status_code=422, detail="题目答案索引超出选项范围。")
    return save_extension_record(QUESTION_BANK, new_record(context, payload.model_dump()), create=True)


@router.post("/labor/training/exams", status_code=201)
def submit_exam(payload: ExamPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.manage")
    course = extension_record_by_id(TRAINING_COURSES, payload.courseId)
    if not course:
        raise HTTPException(status_code=422, detail="培训课程不存在。")
    questions = [record for record in list_extension_records(QUESTION_BANK) if record.get("courseId") == payload.courseId]
    if not questions:
        raise HTTPException(status_code=409, detail="课程尚未配置题库。")
    score = sum(float(question.get("score") or 0) for question in questions if sorted(payload.answers.get(question["id"], [])) == sorted(question.get("answers") or []))
    total = sum(float(question.get("score") or 0) for question in questions)
    percentage = round(score / total * 100, 2) if total else 0
    passed = percentage >= float(course.get("passingScore") or 80)
    exam = new_record(context, {**payload.model_dump(), "score": percentage, "passed": passed, "submittedAt": utc_now()})
    saved = save_extension_record(EXAMS, exam, create=True)
    if passed:
        validity_months = int(course.get("validityMonths") or 12)
        certificate = new_record(context, {
            "courseId": payload.courseId, "workerId": payload.workerId, "examId": saved["id"],
            "certificateNo": f"CERT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
            "issuedOn": date.today().isoformat(), "expiresOn": (date.today() + timedelta(days=validity_months * 30)).isoformat(),
            "validityMonths": validity_months, "status": "valid",
        })
        save_extension_record(CERTIFICATES, certificate, create=True)
        saved["certificateId"] = certificate["id"]
    return saved


@router.get("/labor/training/certificates")
def certificates(workerId: str = "", context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.view")
    return items(CERTIFICATES, context, workerId=workerId)


@router.get("/labor/expiry-alerts")
def labor_expiry_alerts(days: int = Query(default=30, ge=0, le=365), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.view")
    today = date.today()
    alerts: list[dict[str, Any]] = []
    sources = [
        (LABOR_COMPANIES, "licenseExpiresOn", "company-license", "name"),
        (CERTIFICATES, "expiresOn", "training-certificate", "certificateNo"),
    ]
    for collection, field, kind, label_field in sources:
        for record in list_extension_records(collection):
            if not record.get(field):
                continue
            remaining = (date.fromisoformat(str(record[field])) - today).days
            if remaining <= days:
                alerts.append({"kind": kind, "recordId": record["id"], "label": record.get(label_field), "expiresOn": record[field], "daysRemaining": remaining, "level": "expired" if remaining < 0 else "warning"})
    for job in list_jobs():
        if not job.get("contractEndAt"):
            continue
        expires = datetime.fromisoformat(str(job["contractEndAt"]).replace("Z", "+00:00")).date()
        remaining = (expires - today).days
        if remaining <= days:
            alerts.append({"kind": "labor-contract", "recordId": job["id"], "label": job.get("contractNo") or job.get("jobNo"), "expiresOn": expires.isoformat(), "daysRemaining": remaining, "level": "expired" if remaining < 0 else "warning"})
    return {"items": alerts, "total": len(alerts)}


class HarvestAllocationPayload(BaseModel):
    fiscalYear: int = Field(ge=2000, le=2100)
    level: Literal["city", "county", "town", "village", "block"]
    targetCode: str = Field(min_length=1, max_length=128)
    parentAllocationId: str = ""
    assignedQuantity: float = Field(ge=0)
    carryOverQuantity: float = Field(default=0, ge=0)
    recommendedQuantity: float | None = Field(default=None, ge=0)


@router.get("/harvest/quota-allocations")
def harvest_allocations(fiscalYear: int | None = None, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.harvest.view")
    records = list_extension_records(HARVEST_ALLOCATIONS, area_codes=visible_areas(context))
    if fiscalYear:
        records = [record for record in records if record.get("fiscalYear") == fiscalYear]
    for record in records:
        children = [child for child in records if child.get("parentAllocationId") == record["id"]]
        record["distributedQuantity"] = round(sum(float(child.get("assignedQuantity") or 0) for child in children), 4)
        record["availableQuantity"] = round(float(record.get("assignedQuantity") or 0) + float(record.get("carryOverQuantity") or 0) - record["distributedQuantity"], 4)
    return {"items": records, "total": len(records)}


@router.post("/harvest/quota-allocations", status_code=201)
def create_harvest_allocation(payload: HarvestAllocationPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.harvest.quota")
    area_code = ""
    if payload.level == "county":
        if "*" not in visible_areas(context) and payload.targetCode not in visible_areas(context):
            raise HTTPException(status_code=403, detail="Area access denied")
        area_code = payload.targetCode
    elif payload.level == "block":
        block = block_by_code(payload.targetCode)
        if not block:
            raise HTTPException(status_code=422, detail="额度下达必须关联正式林班。")
        require_target_block_allowed(context, block)
        area_code = str(block.get("countyCode") or "")
    elif payload.level in {"town", "village"} and not payload.parentAllocationId:
        raise HTTPException(status_code=422, detail="乡镇或村级额度必须关联上级额度。")
    if payload.parentAllocationId:
        parent = extension_record_by_id(HARVEST_ALLOCATIONS, payload.parentAllocationId)
        if not parent:
            raise HTTPException(status_code=422, detail="上级额度不存在。")
        parent_area = str(parent.get("areaCode") or "")
        if parent_area and "*" not in visible_areas(context) and parent_area not in visible_areas(context):
            raise HTTPException(status_code=403, detail="Area access denied")
        siblings = [record for record in list_extension_records(HARVEST_ALLOCATIONS) if record.get("parentAllocationId") == parent["id"]]
        available = float(parent.get("assignedQuantity") or 0) + float(parent.get("carryOverQuantity") or 0) - sum(float(record.get("assignedQuantity") or 0) for record in siblings)
        if payload.assignedQuantity > available:
            raise HTTPException(status_code=409, detail="下达额度超过上级可用余额。")
        area_code = area_code or str(parent.get("areaCode") or "")
    record = new_record(context, payload.model_dump(), area_code=area_code)
    record.update({"status": "active", "usedQuantity": 0.0})
    return save_extension_record(HARVEST_ALLOCATIONS, record, create=True)


class HarvestCompliancePayload(BaseModel):
    harvestApplicationId: str
    blockCode: str
    actualQuantity: float = Field(ge=0)
    approvedQuantity: float = Field(ge=0)
    actualGeometry: dict[str, Any]
    approvedGeometry: dict[str, Any]
    actualAgeGroup: str = ""
    approvedAgeGroups: list[str] = Field(default_factory=list)
    beforeSceneId: str = ""
    afterSceneId: str = ""


@router.post("/harvest/compliance-checks", status_code=201)
def create_harvest_compliance(payload: HarvestCompliancePayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.harvest.verify")
    block = block_by_code(payload.blockCode)
    if not block:
        raise HTTPException(status_code=422, detail="采伐核验必须关联正式林班。")
    require_target_block_allowed(context, block)
    try:
        actual = shape(payload.actualGeometry)
        approved = shape(payload.approvedGeometry)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="采伐核验边界无效。") from exc
    outside_area = actual.difference(approved).area
    checks = {
        "boundary": "failed" if outside_area > 0 else "passed",
        "quantity": "failed" if payload.actualQuantity > payload.approvedQuantity else "passed",
        "ageGroup": "failed" if payload.approvedAgeGroups and payload.actualAgeGroup not in payload.approvedAgeGroups else "passed",
    }
    record = new_record(context, payload.model_dump(), area_code=str(block.get("countyCode") or ""))
    record.update({"checks": checks, "status": "non-compliant" if "failed" in checks.values() else "compliant", "outsideGeometryArea": outside_area})
    return save_extension_record(HARVEST_CHECKS, record, create=True)


@router.get("/harvest/compliance-checks")
def harvest_compliance_checks(status: str = "", context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.harvest.view")
    return items(HARVEST_CHECKS, context, status=status)
