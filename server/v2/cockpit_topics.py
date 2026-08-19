from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.drone import list_missions
from server.modules.equipment import list_devices
from server.modules.extension_store import list_extension_records
from server.modules.forest_blocks import ForestBlockFilters, block_by_code, forest_block_summary, require_target_block_allowed
from server.modules.harvest import list_applications, list_quotas
from server.modules.safety_events import list_alerts, list_events


router = APIRouter(prefix="/cockpit", tags=["v2-cockpit-topics"])


def scoped_records(records: list[dict[str, Any]], context: AuthContext) -> list[dict[str, Any]]:
    visible: list[dict[str, Any]] = []
    for record in records:
        codes = {
            str(link.get("code") or "") for link in record.get("blocks") or [] if link.get("code")
        }
        for key in ("blockCode", "forestBlockCode"):
            if record.get(key):
                codes.add(str(record[key]))
        try:
            for code in codes:
                block = block_by_code(code)
                if block:
                    require_target_block_allowed(context, block)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        visible.append(record)
    return visible


def metric(
    key: str, label: str, value: float | int | None, unit: str, source: str, drilldown: str,
    *, definition: str, available: bool = True,
) -> dict[str, Any]:
    return {
        "key": key, "label": label, "value": value if available else None, "unit": unit,
        "available": available, "source": source, "definition": definition, "drilldown": drilldown,
    }


@router.get("/topics")
def cockpit_topics(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "cockpit.leadership.view")
    as_of = datetime.now(timezone.utc).isoformat()
    blocks = forest_block_summary(ForestBlockFilters(limit=1), context)
    events = scoped_records(list_events(), context)
    alerts = scoped_records(list_alerts(), context)
    harvest = scoped_records(list_applications(), context)
    quotas = scoped_records(list_quotas(active_only=True), context)
    drones = scoped_records(list_missions(), context)
    devices = scoped_records(list_devices(), context)
    area_codes = set(context.areas or {"*"})
    cost_entries = list_extension_records("cost-entries", area_codes=area_codes)
    budgets = list_extension_records("cost-budgets", area_codes=area_codes)
    budget_alerts: list[dict[str, Any]] = []
    for budget in budgets:
        actual = sum(int(entry.get("amountCents") or 0) for entry in cost_entries if entry.get("period") == budget.get("period") and entry.get("blockCode") == budget.get("blockCode"))
        amount = int(budget.get("amountCents") or 0)
        percent = 0 if amount == 0 else (actual - amount) / amount * 100
        if percent >= float(budget.get("yellowThresholdPct") or 15):
            budget_alerts.append({"budgetId": budget["id"], "blockCode": budget["blockCode"], "period": budget["period"], "variancePct": round(percent, 2), "level": "red" if percent >= float(budget.get("redThresholdPct") or 30) else "yellow"})
    online_devices = [device for device in devices if device.get("connectivityStatus") == "online"]
    active_events = [event for event in events if event.get("status") not in {"closed", "resolved"}]
    active_alerts = [alert for alert in alerts if alert.get("status") not in {"closed", "resolved", "dismissed"}]
    active_harvest = [item for item in harvest if item.get("status") in {"approved", "operating", "submitted"}]
    active_drones = [item for item in drones if item.get("status") in {"assigned", "accepted", "flying", "processing"}]
    integration_adapters = list_extension_records("integration-adapters")
    video_ready = any(item.get("enabled") and item.get("adapterType") in {"rtsp", "gb28181", "onvif"} for item in integration_adapters)
    topics = [
        {
            "key": "overview", "label": "综合态势", "available": True, "asOf": as_of,
            "metrics": [
                metric("forestBlockCount", "林班数量", int(blocks.get("total") or 0), "个", "林班台账", "/v2/resources/forest-blocks", definition="当前数据范围内未删除林班数量"),
                metric("forestAreaMu", "经营面积", round(float(blocks.get("totalAreaMu") or 0), 2), "亩", "林班台账", "/v2/map", definition="当前数据范围内林班面积合计"),
                metric("onlineDeviceCount", "在线设备", len(online_devices), "台", "设备台账+遥测", "/v2/iot/devices", definition="最近状态为在线的未报废设备数量"),
            ],
        },
        {
            "key": "emergency", "label": "灾害应急", "available": True, "asOf": as_of,
            "metrics": [
                metric("activeEventCount", "处置中事件", len(active_events), "起", "安全事件台账", "/v2/safety/events", definition="未关闭且未解决的安全事件"),
                metric("activeAlertCount", "活动预警", len(active_alerts), "条", "安全告警台账", "/v2/safety/events", definition="未关闭、未解决、未忽略的告警"),
            ],
            "featureGates": {"videoConference": video_ready, "reason": "需启用 ONVIF、RTSP 或 GB28181 适配器" if not video_ready else "视频协议已配置"},
        },
        {
            "key": "harvest", "label": "采伐监管", "available": True, "asOf": as_of,
            "metrics": [
                metric("activeHarvestCount", "在办采伐", len(active_harvest), "项", "采伐申请台账", "/v2/operations/harvest", definition="已批准、作业中或待验收采伐申请"),
                metric("activeQuotaCount", "有效额度", len(quotas), "项", "采伐额度台账", "/v2/operations/harvest", definition="当前有效采伐额度记录数量"),
                metric("nonCompliantCount", "不合规核验", len([item for item in list_extension_records("harvest-compliance-checks", area_codes=area_codes) if item.get("status") == "non-compliant"]), "项", "采伐影像核验", "/v2/integrations", definition="边界、数量或龄级至少一项未通过的核验"),
            ],
        },
        {
            "key": "drone", "label": "无人机运营", "available": True, "asOf": as_of,
            "metrics": [
                metric("activeMissionCount", "执行中任务", len(active_drones), "架次", "无人机任务台账", "/v2/drone/missions", definition="已派发、已接收、飞行中或成果处理中任务"),
                metric("registeredDroneCount", "登记无人机", len([device for device in devices if device.get("deviceType") == "drone"]), "架", "设备台账", "/v2/iot/devices", definition="设备台账中类型为无人机的未删除设备"),
            ],
        },
        {
            "key": "cost", "label": "成本效益", "available": True, "asOf": as_of,
            "metrics": [
                metric("costTotal", "累计经营成本", round(sum(int(item.get("amountCents") or 0) for item in cost_entries) / 100, 2), "元", "成本分录", "/v2/operations/costs", definition="当前数据范围内所有有效成本分录合计"),
                metric("budgetAlertCount", "预算预警", len(budget_alerts), "条", "预算与成本分录", "/v2/operations/costs", definition="实际成本超过预算15%黄线或30%红线的记录"),
            ],
            "alerts": budget_alerts,
        },
    ]
    return {
        "source": "live", "asOf": as_of, "scope": {"user": context.user, "roles": sorted(context.roles), "areas": sorted(context.areas)},
        "topics": topics, "metricPolicy": "每项指标必须提供口径、数据源、更新时间和明细入口；无真实数据时返回0或不可用，不使用固定演示数字。",
    }
