from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.extension_store import (
    extension_record_by_id,
    extension_record_by_idempotency_key,
    list_extension_records,
    save_extension_record,
    utc_now,
)
from server.modules.forest_blocks import block_by_code, require_target_area_allowed, require_target_block_allowed
from server.modules.labor import list_jobs


router = APIRouter(prefix="/costs", tags=["v2-costs"])
RATE_COLLECTION = "cost-rates"
MATERIAL_COLLECTION = "cost-materials"
RECEIPT_COLLECTION = "cost-material-receipts"
ISSUE_COLLECTION = "cost-material-issues"
ENTRY_COLLECTION = "cost-entries"
PERIOD_COLLECTION = "cost-periods"
BUDGET_COLLECTION = "cost-budgets"
ALERT_COLLECTION = "cost-alerts"


def money_cents(value: Decimal | str | int | float) -> int:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(amount * 100)


def quantity_value(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def page(items: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    return {"items": items[offset:offset + limit], "total": len(items), "limit": limit, "offset": offset}


def base_record(context: AuthContext, *, idempotency_key: str = "", area_code: str = "") -> dict[str, Any]:
    now = utc_now()
    return {
        "id": str(uuid.uuid4()), "version": 1, "areaCode": area_code,
        "idempotencyKey": idempotency_key, "createdBy": context.user,
        "createdAt": now, "updatedAt": now, "deletedAt": None,
    }


def visible_areas(context: AuthContext) -> set[str]:
    return set(context.areas or {"*"})


def validate_block(block_code: str, context: AuthContext) -> dict[str, Any]:
    block = block_by_code(block_code)
    if not block:
        raise HTTPException(status_code=422, detail="成本必须关联正式小班或林班。")
    require_target_block_allowed(context, block)
    return block


def require_record_visible(record: dict[str, Any], context: AuthContext) -> None:
    if record.get("areaCode"):
        require_target_area_allowed(context, str(record["areaCode"]))


def validate_period(period: str) -> str:
    normalized = str(period or "").strip()
    try:
        datetime.strptime(normalized, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="核算期间必须使用 YYYY-MM 格式。") from exc
    return normalized


def ensure_open_period(period: str) -> None:
    record = next((item for item in list_extension_records(PERIOD_COLLECTION) if item.get("period") == period), None)
    if record and record.get("status") == "closed":
        raise HTTPException(status_code=409, detail="核算期间已关账，不能新增或重算成本。")


class RatePayload(BaseModel):
    workType: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    unit: Literal["hour", "day", "mu", "ton", "job"] = "hour"
    rate: Decimal = Field(ge=0)
    effectiveFrom: date
    effectiveTo: date | None = None
    areaCode: str = Field(default="", max_length=32)
    notes: str = Field(default="", max_length=1000)


class MaterialPayload(BaseModel):
    materialCode: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=32)
    openingQuantity: Decimal = Field(default=Decimal("0"), ge=0)
    openingUnitCost: Decimal = Field(default=Decimal("0"), ge=0)
    areaCode: str = Field(default="", max_length=32)


class MaterialReceiptPayload(BaseModel):
    quantity: Decimal = Field(gt=0)
    unitCost: Decimal = Field(ge=0)
    receivedAt: datetime
    documentNo: str = Field(min_length=1, max_length=96)
    note: str = Field(default="", max_length=1000)


class MaterialIssuePayload(BaseModel):
    materialId: str
    blockCode: str = Field(min_length=1, max_length=128)
    quantity: Decimal = Field(gt=0)
    occurredOn: date
    sourceTaskId: str = Field(default="", max_length=36)
    harvestApplicationId: str = Field(default="", max_length=36)
    documentNo: str = Field(min_length=1, max_length=96)
    note: str = Field(default="", max_length=1000)


class CostEntryPayload(BaseModel):
    costType: Literal["labor", "material", "adjustment"]
    blockCode: str = Field(min_length=1, max_length=128)
    amount: Decimal
    occurredOn: date
    sourceType: str = Field(min_length=1, max_length=64)
    sourceId: str = Field(min_length=1, max_length=128)
    sourceVersion: int = Field(default=1, ge=1)
    taskId: str = Field(default="", max_length=36)
    harvestApplicationId: str = Field(default="", max_length=36)
    note: str = Field(default="", max_length=1000)
    reversesEntryId: str = Field(default="", max_length=36)


class PeriodPayload(BaseModel):
    period: str
    action: Literal["open", "close", "reopen", "recalculate"] = "open"


class BudgetPayload(BaseModel):
    period: str
    blockCode: str = Field(min_length=1, max_length=128)
    amount: Decimal = Field(ge=0)
    yellowThresholdPct: Decimal = Field(default=Decimal("15"), ge=0)
    redThresholdPct: Decimal = Field(default=Decimal("30"), ge=0)


@router.get("/rates")
def rates(
    q: str = "", limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "costs.view")
    items = list_extension_records(RATE_COLLECTION, area_codes=visible_areas(context))
    needle = q.strip().lower()
    if needle:
        items = [item for item in items if needle in f"{item.get('workType')} {item.get('name')}".lower()]
    return page(items, limit, offset)


@router.post("/rates", status_code=201)
def create_rate(payload: RatePayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "costs.manage")
    if payload.areaCode.strip():
        require_target_area_allowed(context, payload.areaCode.strip())
    if payload.effectiveTo and payload.effectiveTo < payload.effectiveFrom:
        raise HTTPException(status_code=422, detail="工价失效日期不能早于生效日期。")
    record = {
        **base_record(context, area_code=payload.areaCode.strip()), **payload.model_dump(mode="json"),
        "rateCents": money_cents(payload.rate), "status": "active",
    }
    record.pop("rate", None)
    return save_extension_record(RATE_COLLECTION, record, create=True)


@router.get("/materials")
def materials(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "costs.view")
    items = list_extension_records(MATERIAL_COLLECTION, area_codes=visible_areas(context))
    return {"items": items, "total": len(items)}


@router.post("/materials", status_code=201)
def create_material(payload: MaterialPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "costs.manage")
    if payload.areaCode.strip():
        require_target_area_allowed(context, payload.areaCode.strip())
    if any(item.get("materialCode") == payload.materialCode for item in list_extension_records(MATERIAL_COLLECTION)):
        raise HTTPException(status_code=409, detail="物料编码已存在。")
    quantity = quantity_value(payload.openingQuantity)
    unit_cost = money_cents(payload.openingUnitCost)
    record = {
        **base_record(context, area_code=payload.areaCode.strip()),
        "materialCode": payload.materialCode.strip(), "name": payload.name.strip(), "unit": payload.unit.strip(),
        "stockQuantity": str(quantity), "stockValueCents": int(quantity * unit_cost),
        "movingAverageUnitCostCents": unit_cost if quantity else 0, "status": "active",
    }
    return save_extension_record(MATERIAL_COLLECTION, record, create=True)


@router.post("/materials/{material_id}/receipts", status_code=201)
def receive_material(
    material_id: str, payload: MaterialReceiptPayload,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "costs.manage")
    existing = extension_record_by_idempotency_key(RECEIPT_COLLECTION, idempotency_key)
    if existing:
        require_record_visible(existing, context)
        return existing
    material = extension_record_by_id(MATERIAL_COLLECTION, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="物料不存在。")
    require_record_visible(material, context)
    quantity = quantity_value(payload.quantity)
    unit_cost = money_cents(payload.unitCost)
    old_quantity = quantity_value(material.get("stockQuantity") or 0)
    old_value = int(material.get("stockValueCents") or 0)
    new_quantity = old_quantity + quantity
    new_value = old_value + int(quantity * unit_cost)
    material.update({
        "stockQuantity": str(new_quantity), "stockValueCents": new_value,
        "movingAverageUnitCostCents": int(Decimal(new_value) / new_quantity) if new_quantity else 0,
        "version": int(material.get("version") or 1) + 1, "updatedAt": utc_now(),
    })
    save_extension_record(MATERIAL_COLLECTION, material, create=False)
    record = {
        **base_record(context, idempotency_key=idempotency_key, area_code=str(material.get("areaCode") or "")),
        **payload.model_dump(mode="json"), "materialId": material_id, "quantity": str(quantity),
        "unitCostCents": unit_cost, "amountCents": int(quantity * unit_cost),
        "stockQuantityAfter": str(new_quantity), "movingAverageUnitCostCentsAfter": material["movingAverageUnitCostCents"],
    }
    record.pop("unitCost", None)
    return save_extension_record(RECEIPT_COLLECTION, record, create=True)


@router.post("/material-issues", status_code=201)
def issue_material(
    payload: MaterialIssuePayload,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "costs.manage")
    existing = extension_record_by_idempotency_key(ISSUE_COLLECTION, idempotency_key)
    if existing:
        require_record_visible(existing, context)
        return existing
    material = extension_record_by_id(MATERIAL_COLLECTION, payload.materialId)
    if not material:
        raise HTTPException(status_code=404, detail="物料不存在。")
    require_record_visible(material, context)
    block = validate_block(payload.blockCode, context)
    quantity = quantity_value(payload.quantity)
    stock_quantity = quantity_value(material.get("stockQuantity") or 0)
    if quantity > stock_quantity:
        raise HTTPException(status_code=409, detail="库存数量不足。")
    period = validate_period(payload.occurredOn.strftime("%Y-%m"))
    ensure_open_period(period)
    unit_cost = int(material.get("movingAverageUnitCostCents") or 0)
    amount = int(quantity * unit_cost)
    issue = {
        **base_record(context, idempotency_key=idempotency_key, area_code=str(block.get("countyCode") or "")),
        **payload.model_dump(mode="json"), "quantity": str(quantity), "unitCostCents": unit_cost,
        "amountCents": amount, "period": period, "sourceVersion": int(material.get("version") or 1),
    }
    saved_issue = save_extension_record(ISSUE_COLLECTION, issue, create=True)
    entry = {
        **base_record(context, idempotency_key=f"material-issue:{saved_issue['id']}", area_code=issue["areaCode"]),
        "costType": "material", "blockCode": payload.blockCode, "amountCents": amount,
        "occurredOn": payload.occurredOn.isoformat(), "period": period, "sourceType": "material-issue",
        "sourceId": saved_issue["id"], "sourceVersion": issue["sourceVersion"], "taskId": payload.sourceTaskId,
        "harvestApplicationId": payload.harvestApplicationId, "note": payload.note, "reversesEntryId": "",
    }
    save_extension_record(ENTRY_COLLECTION, entry, create=True)
    remaining = stock_quantity - quantity
    material.update({
        "stockQuantity": str(remaining), "stockValueCents": int(material.get("stockValueCents") or 0) - amount,
        "version": int(material.get("version") or 1) + 1, "updatedAt": utc_now(),
    })
    save_extension_record(MATERIAL_COLLECTION, material, create=False)
    return saved_issue


@router.get("/entries")
def entries(
    period: str = "", blockCode: str = "", costType: str = "",
    limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "costs.view")
    items = list_extension_records(ENTRY_COLLECTION, area_codes=visible_areas(context))
    if period:
        items = [item for item in items if item.get("period") == validate_period(period)]
    if blockCode:
        items = [item for item in items if item.get("blockCode") == blockCode]
    if costType:
        items = [item for item in items if item.get("costType") == costType]
    return page(items, limit, offset)


@router.post("/entries", status_code=201)
def create_entry(
    payload: CostEntryPayload,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "costs.manage")
    existing = extension_record_by_idempotency_key(ENTRY_COLLECTION, idempotency_key)
    if existing:
        require_record_visible(existing, context)
        return existing
    block = validate_block(payload.blockCode, context)
    period = validate_period(payload.occurredOn.strftime("%Y-%m"))
    ensure_open_period(period)
    amount = money_cents(payload.amount)
    if payload.reversesEntryId:
        source = extension_record_by_id(ENTRY_COLLECTION, payload.reversesEntryId)
        if not source:
            raise HTTPException(status_code=422, detail="被冲销成本分录不存在。")
        require_record_visible(source, context)
        if any(item.get("reversesEntryId") == source["id"] for item in list_extension_records(ENTRY_COLLECTION, area_codes=visible_areas(context))):
            raise HTTPException(status_code=409, detail="该成本分录已经冲销。")
        amount = -int(source.get("amountCents") or 0)
    record = {
        **base_record(context, idempotency_key=idempotency_key, area_code=str(block.get("countyCode") or "")),
        **payload.model_dump(mode="json"), "amountCents": amount, "period": period,
    }
    record.pop("amount", None)
    return save_extension_record(ENTRY_COLLECTION, record, create=True)


def applicable_rate(work_type: str, work_date: str, area_code: str) -> dict[str, Any] | None:
    candidates = [
        item for item in list_extension_records(RATE_COLLECTION)
        if item.get("workType") == work_type
        and str(item.get("effectiveFrom") or "") <= work_date
        and (not item.get("effectiveTo") or str(item.get("effectiveTo")) >= work_date)
        and (not item.get("areaCode") or item.get("areaCode") == area_code)
    ]
    return sorted(candidates, key=lambda item: str(item.get("effectiveFrom") or ""), reverse=True)[0] if candidates else None


def recalculate_labor(period: str, context: AuthContext) -> dict[str, Any]:
    created = 0
    skipped = 0
    for job in list_jobs():
        block_code = str(((job.get("blocks") or [{}])[0]).get("code") or "")
        if not block_code:
            continue
        block = validate_block(block_code, context)
        area_code = str(block.get("countyCode") or "")
        for attendance in job.get("attendance") or []:
            work_date = str(attendance.get("workDate") or "")
            if not work_date.startswith(period) or str(attendance.get("status") or "") not in {"present", "verified"}:
                continue
            key = f"labor-attendance:{job['id']}:{attendance.get('workerId')}:{work_date}"
            if extension_record_by_idempotency_key(ENTRY_COLLECTION, key, area_codes=visible_areas(context)):
                skipped += 1
                continue
            rate = applicable_rate(str(job.get("workType") or "other"), work_date, area_code)
            if not rate:
                skipped += 1
                continue
            hours = quantity_value(attendance.get("workHours") or 0)
            if rate.get("unit") == "day":
                amount = int((hours / Decimal("8")) * int(rate.get("rateCents") or 0))
            else:
                amount = int(hours * int(rate.get("rateCents") or 0))
            record = {
                **base_record(context, idempotency_key=key, area_code=area_code),
                "costType": "labor", "blockCode": block_code, "amountCents": amount,
                "occurredOn": work_date, "period": period, "sourceType": "labor-attendance",
                "sourceId": str(attendance.get("id") or key), "sourceVersion": int(job.get("version") or 1),
                "taskId": job["id"], "harvestApplicationId": "", "rateId": rate["id"],
                "workHours": str(hours), "note": "按有效工时和适用工价自动归集", "reversesEntryId": "",
            }
            save_extension_record(ENTRY_COLLECTION, record, create=True)
            created += 1
    return {"created": created, "skipped": skipped}


def budget_alerts(period: str, context: AuthContext) -> list[dict[str, Any]]:
    totals: dict[str, int] = defaultdict(int)
    for entry in list_extension_records(ENTRY_COLLECTION, area_codes=visible_areas(context)):
        if entry.get("period") == period:
            totals[str(entry.get("blockCode") or "")] += int(entry.get("amountCents") or 0)
    alerts: list[dict[str, Any]] = []
    for budget in list_extension_records(BUDGET_COLLECTION, area_codes=visible_areas(context)):
        if budget.get("period") != period:
            continue
        actual = totals.get(str(budget.get("blockCode") or ""), 0)
        amount = int(budget.get("amountCents") or 0)
        variance_pct = Decimal("0") if amount == 0 else (Decimal(actual - amount) / Decimal(amount) * 100)
        red = Decimal(str(budget.get("redThresholdPct") or 30))
        yellow = Decimal(str(budget.get("yellowThresholdPct") or 15))
        level = "red" if variance_pct >= red else "yellow" if variance_pct >= yellow else "normal"
        alerts.append({
            "budgetId": budget["id"], "period": period, "blockCode": budget["blockCode"],
            "budgetCents": amount, "actualCents": actual, "varianceCents": actual - amount,
            "variancePct": float(variance_pct.quantize(Decimal("0.01"))), "level": level,
        })
    return alerts


@router.get("/periods")
def periods(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "costs.view")
    items = list_extension_records(PERIOD_COLLECTION)
    return {"items": items, "total": len(items)}


@router.post("/periods/actions")
def period_action(payload: PeriodPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "costs.manage")
    period = validate_period(payload.period)
    current = next((item for item in list_extension_records(PERIOD_COLLECTION) if item.get("period") == period), None)
    if payload.action == "recalculate":
        ensure_open_period(period)
        result = recalculate_labor(period, context)
        return {"period": period, "action": payload.action, **result, "alerts": budget_alerts(period, context)}
    if payload.action == "close" and not current:
        raise HTTPException(status_code=409, detail="请先打开核算期间。")
    now = utc_now()
    status = "closed" if payload.action == "close" else "open"
    record = current or {**base_record(context), "period": period}
    record.update({
        "status": status, "updatedAt": now, "version": int(record.get("version") or 0) + (1 if current else 0),
        "closedAt": now if status == "closed" else None, "closedBy": context.user if status == "closed" else "",
    })
    return save_extension_record(PERIOD_COLLECTION, record, create=current is None)


@router.get("/budgets")
def budgets(period: str = "", context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "costs.view")
    items = list_extension_records(BUDGET_COLLECTION, area_codes=visible_areas(context))
    if period:
        items = [item for item in items if item.get("period") == validate_period(period)]
    return {"items": items, "total": len(items), "alerts": budget_alerts(period, context) if period else []}


@router.post("/budgets", status_code=201)
def create_budget(payload: BudgetPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "costs.manage")
    period = validate_period(payload.period)
    block = validate_block(payload.blockCode, context)
    existing = next((
        item for item in list_extension_records(BUDGET_COLLECTION, area_codes=visible_areas(context))
        if item.get("period") == period and item.get("blockCode") == payload.blockCode
    ), None)
    record = existing or base_record(context, area_code=str(block.get("countyCode") or ""))
    record.update({
        "period": period, "blockCode": payload.blockCode, "amountCents": money_cents(payload.amount),
        "yellowThresholdPct": str(payload.yellowThresholdPct), "redThresholdPct": str(payload.redThresholdPct),
        "updatedAt": utc_now(), "version": int(record.get("version") or 0) + (1 if existing else 0),
    })
    return save_extension_record(BUDGET_COLLECTION, record, create=existing is None)


def report_payload(period: str, context: AuthContext) -> dict[str, Any]:
    entries = [
        item for item in list_extension_records(ENTRY_COLLECTION, area_codes=visible_areas(context))
        if item.get("period") == period
    ]
    groups: dict[str, dict[str, Any]] = {}
    for entry in entries:
        code = str(entry.get("blockCode") or "未关联")
        group = groups.setdefault(code, {"blockCode": code, "laborCents": 0, "materialCents": 0, "adjustmentCents": 0, "totalCents": 0, "entryCount": 0})
        amount = int(entry.get("amountCents") or 0)
        key = f"{entry.get('costType')}Cents"
        if key in group:
            group[key] += amount
        group["totalCents"] += amount
        group["entryCount"] += 1
    items = sorted(groups.values(), key=lambda item: item["blockCode"])
    return {
        "period": period, "asOf": utc_now(), "currency": "CNY", "amountScale": 2,
        "items": items, "total": len(items), "grandTotalCents": sum(item["totalCents"] for item in items),
        "alerts": budget_alerts(period, context),
    }


@router.get("/reports/monthly")
def monthly_report(period: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "costs.view")
    return report_payload(validate_period(period), context)


@router.get("/reports/annual")
def annual_report(year: int = Query(ge=2000, le=2100), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "costs.view")
    monthly = [report_payload(f"{year}-{month:02d}", context) for month in range(1, 13)]
    return {"year": year, "asOf": utc_now(), "months": monthly, "grandTotalCents": sum(item["grandTotalCents"] for item in monthly)}


@router.get("/reports/harvest-cycle")
def harvest_cycle_report(
    harvestApplicationId: str, context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "costs.view")
    records = [
        item for item in list_extension_records(ENTRY_COLLECTION, area_codes=visible_areas(context))
        if item.get("harvestApplicationId") == harvestApplicationId
    ]
    grouped: dict[str, dict[str, Any]] = {}
    for entry in records:
        code = str(entry.get("blockCode") or "未关联")
        row = grouped.setdefault(code, {"blockCode": code, "laborCents": 0, "materialCents": 0, "adjustmentCents": 0, "totalCents": 0, "entryCount": 0})
        amount = int(entry.get("amountCents") or 0)
        type_key = f"{entry.get('costType')}Cents"
        if type_key in row:
            row[type_key] += amount
        row["totalCents"] += amount
        row["entryCount"] += 1
    result = sorted(grouped.values(), key=lambda item: item["blockCode"])
    return {
        "harvestApplicationId": harvestApplicationId, "asOf": utc_now(), "currency": "CNY",
        "items": result, "total": len(result), "grandTotalCents": sum(item["totalCents"] for item in result),
        "sourceVersions": sorted({f"{item.get('sourceType')}:{item.get('sourceId')}@{item.get('sourceVersion')}" for item in records}),
    }


@router.get("/reports/monthly.csv")
def export_monthly_report(period: str, context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "costs.export")
    report = report_payload(validate_period(period), context)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["核算期间", "小班/林班", "人工成本(元)", "物料成本(元)", "调整(元)", "总成本(元)", "分录数"])
    for item in report["items"]:
        writer.writerow([
            period, item["blockCode"], Decimal(item["laborCents"]) / 100,
            Decimal(item["materialCents"]) / 100, Decimal(item["adjustmentCents"]) / 100,
            Decimal(item["totalCents"]) / 100, item["entryCount"],
        ])
    return Response(
        content="\ufeff" + stream.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="cost-report-{period}.csv"'},
    )
