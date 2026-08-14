from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

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
)
from server.modules.forest_blocks import block_by_code, require_target_block_allowed


router = APIRouter(prefix="/carbon", tags=["v2-carbon"])
MODULE_KEY = "carbon-estimates"
ACCOUNTING_TYPES = {"stock", "increment", "project"}
VERIFICATION_STATUSES = {"calculating", "review", "verified", "rejected"}


class CarbonEstimatePayload(BaseModel):
    projectCode: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    accountingType: str = "project"
    verificationStatus: str = "calculating"
    projectBoundary: str = Field(min_length=1, max_length=1000)
    methodology: str = Field(default="", max_length=500)
    accountingStartDate: str = ""
    accountingEndDate: str = ""
    accountingAreaMu: float | None = Field(default=None, ge=0)
    carbonStock: float | None = Field(default=None, ge=0)
    annualSequestration: float | None = Field(default=None, ge=0)
    verifiedAmount: float | None = Field(default=None, ge=0)
    carbonPrice: float | None = Field(default=None, ge=0)
    estimatedRevenue: float | None = Field(default=None, ge=0)
    verificationAgency: str = Field(default="", max_length=255)
    verificationDate: str = ""
    beneficiary: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=5000)
    linkedBlockCodes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_domain_rules(self) -> "CarbonEstimatePayload":
        if self.accountingType not in ACCOUNTING_TYPES:
            raise ValueError("核算类型无效。")
        if self.verificationStatus not in VERIFICATION_STATUSES:
            raise ValueError("核证状态无效。")
        if self.accountingStartDate and self.accountingEndDate and self.accountingEndDate < self.accountingStartDate:
            raise ValueError("核算结束日期不能早于开始日期。")
        if self.verificationStatus == "verified" and self.verifiedAmount is None:
            raise ValueError("已核证项目必须填写核证减排量。")
        return self


def validated_block_codes(codes: list[str], context: AuthContext) -> list[str]:
    normalized = list(dict.fromkeys(str(code).strip() for code in codes if str(code).strip()))
    if not normalized:
        raise HTTPException(status_code=422, detail="至少关联一个正式林班。")
    for code in normalized:
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"关联林班不存在：{code}")
        require_target_block_allowed(context, block)
    return normalized


def properties_from_payload(payload: CarbonEstimatePayload) -> dict[str, Any]:
    data = payload.model_dump(exclude={"projectCode", "name", "linkedBlockCodes"})
    return {key: value for key, value in data.items() if value not in (None, "")}


def carbon_record(record: Any) -> dict[str, Any]:
    raw = record.model_dump(mode="json") if hasattr(record, "model_dump") else dict(record)
    properties = dict(raw.get("properties") or {})
    return {
        "id": str(raw.get("id") or ""),
        "projectCode": str(raw.get("recordCode") or ""),
        "name": str(raw.get("name") or ""),
        "accountingType": str(properties.get("accountingType") or "project"),
        "verificationStatus": str(properties.get("verificationStatus") or raw.get("status") or "calculating"),
        "projectBoundary": str(properties.get("projectBoundary") or ""),
        "methodology": str(properties.get("methodology") or ""),
        "accountingStartDate": str(properties.get("accountingStartDate") or ""),
        "accountingEndDate": str(properties.get("accountingEndDate") or ""),
        "accountingAreaMu": properties.get("accountingAreaMu"),
        "carbonStock": properties.get("carbonStock"),
        "annualSequestration": properties.get("annualSequestration"),
        "verifiedAmount": properties.get("verifiedAmount"),
        "carbonPrice": properties.get("carbonPrice"),
        "estimatedRevenue": properties.get("estimatedRevenue"),
        "verificationAgency": str(properties.get("verificationAgency") or ""),
        "verificationDate": str(properties.get("verificationDate") or ""),
        "beneficiary": str(properties.get("beneficiary") or ""),
        "notes": str(properties.get("notes") or ""),
        "linkedBlockCodes": list(raw.get("linkedBlockCodes") or []),
        "createdAt": str(raw.get("createdAt") or ""),
        "updatedAt": str(raw.get("updatedAt") or ""),
        "deletedAt": raw.get("deletedAt"),
    }


@router.get("/estimates")
def carbon_estimate_ledger(
    q: str = Query(default=""),
    verification_status: str = Query(default="", alias="verificationStatus"),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    common_filters = {
        "q": q,
        "linkedBlockCode": linked_block_code,
        "fieldKey": "verificationStatus" if verification_status else "",
        "fieldValue": verification_status,
    }
    result = list_business_records(
        MODULE_KEY,
        ManagedFilters(**common_filters, limit=limit, offset=offset),
        context,
    )
    items = [carbon_record(item) for item in result.get("items") or []]
    summary_result = result
    if result.get("total", 0) > len(items):
        summary_result = list_business_records(
            MODULE_KEY,
            ManagedFilters(**common_filters, limit=1000, offset=0),
            context,
        )
    summary_items = [carbon_record(item) for item in summary_result.get("items") or []]
    return {**result, "items": items, "summary": {
        "accountingAreaMu": sum(float(item.get("accountingAreaMu") or 0) for item in summary_items),
        "annualSequestration": sum(float(item.get("annualSequestration") or 0) for item in summary_items),
        "verifiedAmount": sum(float(item.get("verifiedAmount") or 0) for item in summary_items),
        "estimatedRevenue": sum(float(item.get("estimatedRevenue") or 0) for item in summary_items),
    }}


@router.get("/estimates/{record_id}")
def carbon_estimate_detail(record_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    return carbon_record(get_business_record(MODULE_KEY, record_id, context))


@router.post("/estimates")
def create_carbon_estimate(payload: CarbonEstimatePayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    codes = validated_block_codes(payload.linkedBlockCodes, context)
    created = create_business_record(MODULE_KEY, ManagedRecordIn.model_validate({
        "recordCode": payload.projectCode.strip(), "name": payload.name.strip(),
        "status": payload.verificationStatus, "linkedBlockCodes": codes,
        "properties": properties_from_payload(payload), "formVersion": 2,
    }), context)
    return carbon_record(created)


@router.patch("/estimates/{record_id}")
def update_carbon_estimate(record_id: str, payload: CarbonEstimatePayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    codes = validated_block_codes(payload.linkedBlockCodes, context)
    updated = patch_business_record(MODULE_KEY, record_id, ManagedRecordPatch.model_validate({
        "recordCode": payload.projectCode.strip(), "name": payload.name.strip(),
        "status": payload.verificationStatus, "linkedBlockCodes": codes,
        "properties": properties_from_payload(payload), "formVersion": 2,
    }), context)
    return carbon_record(updated)


@router.delete("/estimates/{record_id}")
def remove_carbon_estimate(record_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    return delete_business_record(MODULE_KEY, record_id, context)
