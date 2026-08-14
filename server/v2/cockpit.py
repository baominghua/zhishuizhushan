from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from server.modules.admin_roles import effective_permissions_for_context, require_permission
from server.modules.auth import AuthContext, has_admin_role, request_context
from server.modules.business import ManagedFilters, business_core_value, list_business_records
from server.modules.drone import list_missions
from server.modules.forest_blocks import ForestBlockFilters, forest_block_summary, list_forest_blocks
from server.modules.safety_events import list_events


router = APIRouter(prefix="/cockpit", tags=["v2-cockpit"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def can(context: AuthContext, permission: str) -> bool:
    permissions = set(effective_permissions_for_context(context))
    if has_admin_role(context) or "*" in permissions or permission in permissions:
        return True
    return f"{permission.rsplit('.', 1)[0]}.manage" in permissions


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def business_records(module_key: str, context: AuthContext) -> tuple[list[dict[str, Any]], bool]:
    permission = f"business.{''.join(part.title() if index else part for index, part in enumerate(module_key.split('-')))}.view"
    if not can(context, permission):
        return [], False
    try:
        page = list_business_records(module_key, ManagedFilters(limit=1000, offset=0), context)
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            return [], False
        raise
    return [dict(item) for item in page.get("items") or []], True


def aggregate(records: list[dict[str, Any]], field: str) -> float:
    return round(sum(number(business_core_value(record, field)) for record in records), 2)


def count_status(records: list[dict[str, Any]], statuses: set[str], field: str = "@status") -> int:
    return sum(1 for record in records if str(business_core_value(record, field) or "") in statuses)


def metric(value: float | int | None, unit: str, available: bool, source: str) -> dict[str, Any]:
    return {"value": value if available else None, "unit": unit, "available": available, "source": source}


def carbon_trend(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for record in records:
        period = str(
            business_core_value(record, "verificationDate")
            or business_core_value(record, "accountingEndDate")
            or record.get("updatedAt")
            or ""
        )[:7]
        price = number(business_core_value(record, "carbonPrice"))
        if len(period) == 7 and price > 0:
            buckets[period].append(price)
    return [
        {"period": period, "price": round(sum(values) / len(values), 2)}
        for period, values in sorted(buckets.items())[-12:]
    ]


def district_ranking(
    records: list[dict[str, Any]],
    blocks_by_code: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        linked = [str(code) for code in record.get("linkedBlockCodes") or [] if str(code)]
        block = next((blocks_by_code.get(code) for code in linked if blocks_by_code.get(code)), None)
        district = str((block or {}).get("countyName") or (block or {}).get("townName") or "区划待补充")
        bucket = grouped.setdefault(district, {"name": district, "projects": 0, "annualSequestration": 0.0, "verifiedAmount": 0.0})
        bucket["projects"] += 1
        bucket["annualSequestration"] += number(business_core_value(record, "annualSequestration"))
        bucket["verifiedAmount"] += number(business_core_value(record, "verifiedAmount"))
    items = [
        {
            **item,
            "annualSequestration": round(item["annualSequestration"], 2),
            "verifiedAmount": round(item["verifiedAmount"], 2),
        }
        for item in grouped.values()
    ]
    return sorted(items, key=lambda item: (-item["annualSequestration"], item["name"]))


@router.get("/leadership")
def leadership_cockpit(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "cockpit.leadership.view")

    block_filters = ForestBlockFilters(limit=1000, offset=0)
    block_summary = forest_block_summary(block_filters, context)
    block_page = list_forest_blocks(block_filters, context)
    blocks = [dict(item) for item in block_page.get("items") or []]
    blocks_by_code = {str(block.get("blockCode") or ""): block for block in blocks}

    carbon, carbon_available = business_records("carbon-estimates", context)
    enterprises, enterprises_available = business_records("enterprises", context)
    farmers, farmers_available = business_records("farmers", context)
    forecasts, forecasts_available = business_records("yield-forecasts", context)
    harvest_plans, harvest_available = business_records("harvest-plans", context)
    income, income_available = business_records("income-estimates", context)
    trades, trades_available = business_records("trade-matches", context)

    carbon_trades = [
        record for record in trades
        if "碳" in str(business_core_value(record, "tradeType") or business_core_value(record, "productName") or "")
    ]
    safety_available = can(context, "safety.events.view")
    drone_available = can(context, "drone.missions.view")
    safety_events = list_events() if safety_available else []
    drone_missions = list_missions() if drone_available else []
    open_safety = [event for event in safety_events if str(event.get("status") or "") not in {"closed", "resolved"}]
    active_drones = [mission for mission in drone_missions if str(mission.get("status") or "") in {"assigned", "accepted", "operating", "flying"}]

    verified_projects = [record for record in carbon if str(business_core_value(record, "verificationStatus") or record.get("status") or "") == "verified"]
    trade_volume_available = trades_available and bool(carbon_trades)
    trade_amount = aggregate(carbon_trades, "amount") or aggregate(carbon_trades, "totalAmount")

    return {
        "source": "live",
        "asOf": now_iso(),
        "scope": {
            "user": context.user,
            "roles": sorted(context.roles),
            "areas": sorted(context.areas),
        },
        "overview": {
            "forestBlockCount": metric(int(block_summary.get("total") or 0), "个", True, "林班台账"),
            "forestAreaMu": metric(number(block_summary.get("totalAreaMu")), "亩", True, "林班台账"),
            "annualOutputValue": metric(aggregate(income, "expectedIncome"), "元", income_available, "收益测算"),
            "annualYieldTons": metric(aggregate(forecasts, "forecastYield"), "吨", forecasts_available, "产量预测"),
            "plannedHarvestTons": metric(aggregate(harvest_plans, "plannedQuantity"), "吨", harvest_available, "采挖计划"),
            "enterpriseCount": metric(len(enterprises), "家", enterprises_available, "竹企台账"),
            "practitionerCount": metric(len(farmers), "户", farmers_available, "竹农台账"),
            "carbonStock": metric(aggregate(carbon, "carbonStock"), "tCO2e", carbon_available, "碳汇项目"),
            "annualSequestration": metric(aggregate(carbon, "annualSequestration"), "tCO2e", carbon_available, "碳汇项目"),
        },
        "carbon": {
            "projectCount": metric(len(carbon), "个", carbon_available, "碳汇项目"),
            "verifiedProjectCount": metric(len(verified_projects), "个", carbon_available, "碳汇项目"),
            "accountingAreaMu": metric(aggregate(carbon, "accountingAreaMu"), "亩", carbon_available, "碳汇项目"),
            "totalCarbonStock": metric(aggregate(carbon, "carbonStock"), "tCO2e", carbon_available, "碳汇项目"),
            "annualSequestration": metric(aggregate(carbon, "annualSequestration"), "tCO2e", carbon_available, "碳汇项目"),
            "ccerRegisteredAmount": metric(aggregate(verified_projects, "verifiedAmount"), "tCO2e", carbon_available, "核证项目"),
            "estimatedRevenue": metric(aggregate(carbon, "estimatedRevenue"), "元", carbon_available, "碳汇项目"),
            "tradeVolume": metric(aggregate(carbon_trades, "quantity"), "tCO2e", trade_volume_available, "交易撮合"),
            "tradeAmount": metric(trade_amount, "元", trade_volume_available, "交易撮合"),
            "priceTrend": carbon_trend(carbon),
            "districtRanking": district_ranking(carbon, blocks_by_code),
            "statusDistribution": [
                {"status": status, "count": count_status(carbon, {status}, "verificationStatus")}
                for status in ("calculating", "review", "verified", "rejected")
            ],
        },
        "operations": {
            "openSafetyEvents": metric(len(open_safety), "起", safety_available, "事件中心"),
            "activeDroneMissions": metric(len(active_drones), "项", drone_available, "无人机任务"),
        },
        "availability": {
            "carbon": carbon_available,
            "enterprises": enterprises_available,
            "farmers": farmers_available,
            "yieldForecasts": forecasts_available,
            "harvestPlans": harvest_available,
            "incomeEstimates": income_available,
            "carbonTrades": trade_volume_available,
            "safetyEvents": safety_available,
            "droneMissions": drone_available,
        },
    }
