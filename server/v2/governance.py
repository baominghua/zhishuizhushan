from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission, role_permission_presets
from server.modules.auth import AuthContext, request_context
from server.modules.extension_store import extension_record_by_id, list_extension_records, save_extension_record, utc_now


router = APIRouter(prefix="/governance", tags=["v2-governance"])
ACCESS_REQUESTS = "governance-access-requests"
RETENTION_POLICIES = "governance-retention-policies"
ARCHIVE_TASKS = "governance-archive-tasks"


REQUIREMENT_PACKAGES: tuple[dict[str, Any], ...] = (
    {"key": "BASE-01", "priority": "P0", "delivery": "baseline", "status": "implemented", "reuse": ["采伐审批", "完工验收", "资源调查", "附件中心", "待办消息", "碳汇初版", "11类角色"]},
    {"key": "RES-01", "priority": "P1", "delivery": "software", "status": "implemented", "entry": "/v2/resources/intelligence"},
    {"key": "OPS-01", "priority": "P1/P3", "delivery": "software-and-model", "status": "integration-ready", "entry": "/v2/resources/intelligence"},
    {"key": "HAR-01", "priority": "P1/P3", "delivery": "software-and-device", "status": "integration-ready", "entry": "/v2/integrations"},
    {"key": "LAB-01", "priority": "P1/P3", "delivery": "software-and-device", "status": "integration-ready", "entry": "/v2/workforce"},
    {"key": "AI-01", "priority": "P3", "delivery": "model-integration", "status": "integration-ready", "entry": "/v2/integrations"},
    {"key": "IOT-01", "priority": "P3", "delivery": "supplier-integration", "status": "integration-ready", "entry": "/v2/integrations"},
    {"key": "COST-01", "priority": "P2", "delivery": "software", "status": "implemented", "entry": "/v2/operations/costs"},
    {"key": "MOB-01", "priority": "P1/P3", "delivery": "software-and-device", "status": "implemented", "entry": "/v2/field/mobile"},
    {"key": "COK-01", "priority": "P2", "delivery": "software", "status": "implemented", "entry": "/v2/cockpit/leadership"},
    {"key": "SYS-01", "priority": "P0/P1", "delivery": "software", "status": "implemented", "entry": "/v2/system/governance"},
)


@router.get("/requirements-baseline")
def requirements_baseline(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.roles.view")
    roles = [preset for preset in role_permission_presets() if str(preset.get("key") or "").startswith("spec-")]
    return {
        "baselineCommit": "4ae5d28", "scopeVersion": "2026-08-17", "packages": list(REQUIREMENT_PACKAGES),
        "roleCount": len(roles), "roleCodes": [preset.get("roleCode") for preset in roles],
        "nonDuplicateRule": "扩展现有资源、任务、设备、模型和审计台账，不创建平行业务主数据。",
        "externalAcceptanceDisclaimer": "集成就绪不等于供应商设备、真实码流、飞控或模型精度已经完成生产验收。",
    }


class AccessRequestPayload(BaseModel):
    requestedAreaCodes: list[str] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=5, max_length=2000)
    expiresAt: datetime
    dataCategories: list[str] = Field(default_factory=list, max_length=50)
    operations: list[Literal["view", "export"]] = Field(default_factory=lambda: ["view"])


class AccessReviewPayload(BaseModel):
    action: Literal["approve", "reject", "revoke"]
    note: str = Field(min_length=2, max_length=1000)
    expectedVersion: int = Field(ge=1)


@router.get("/access-requests")
def access_requests(status: str = "", context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.accessRequests.view")
    records = list_extension_records(ACCESS_REQUESTS)
    if "admin" not in context.roles and "super-admin" not in context.roles:
        records = [record for record in records if record.get("requestedBy") == context.user]
    if status:
        records = [record for record in records if record.get("status") == status]
    return {"items": records, "total": len(records)}


@router.post("/access-requests", status_code=201)
def create_access_request(payload: AccessRequestPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.accessRequests.create")
    expires_at = payload.expiresAt
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="跨区授权截止时间必须晚于当前时间。")
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), **payload.model_dump(mode="json"), "requestedAreaCodes": sorted(set(payload.requestedAreaCodes)),
        "requestedBy": context.user, "requesterCurrentAreas": sorted(context.areas), "status": "pending",
        "reviewedBy": "", "reviewedAt": None, "reviewNote": "", "version": 1,
        "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
    }
    return save_extension_record(ACCESS_REQUESTS, record, create=True)


@router.post("/access-requests/{request_id}/actions")
def review_access_request(request_id: str, payload: AccessReviewPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.accessRequests.approve")
    record = extension_record_by_id(ACCESS_REQUESTS, request_id)
    if not record:
        raise HTTPException(status_code=404, detail="跨区查询申请不存在。")
    if int(record.get("version") or 1) != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="申请已更新，请刷新后重试。")
    if payload.action in {"approve", "reject"} and record.get("status") != "pending":
        raise HTTPException(status_code=409, detail="仅待审批申请可以审批。")
    if payload.action == "revoke" and record.get("status") != "approved":
        raise HTTPException(status_code=409, detail="仅已批准授权可以撤销。")
    record.update({
        "status": {"approve": "approved", "reject": "rejected", "revoke": "revoked"}[payload.action],
        "reviewedBy": context.user, "reviewedAt": utc_now(), "reviewNote": payload.note,
        "version": int(record.get("version") or 1) + 1, "updatedAt": utc_now(),
    })
    return save_extension_record(ACCESS_REQUESTS, record, create=False)


class RetentionPolicyPayload(BaseModel):
    eventCategories: list[Literal["login", "query", "approval", "export", "model", "flight"]] = Field(min_length=1)
    retentionMonths: int = Field(default=6, ge=6, le=120)
    archiveStorageRef: str = Field(min_length=1, max_length=500)
    enabled: bool = True


@router.get("/audit-retention")
def audit_retention(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.audit.view")
    records = list_extension_records(RETENTION_POLICIES)
    return {"items": records, "total": len(records), "minimumRetentionMonths": 6}


@router.post("/audit-retention", status_code=201)
def create_retention_policy(payload: RetentionPolicyPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.audit.manage")
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), **payload.model_dump(), "status": "active" if payload.enabled else "disabled",
        "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
    }
    return save_extension_record(RETENTION_POLICIES, record, create=True)


class ArchiveTaskPayload(BaseModel):
    policyId: str
    dryRun: bool = True


@router.post("/archive-tasks", status_code=202)
def create_archive_task(payload: ArchiveTaskPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.audit.manage")
    policy = extension_record_by_id(RETENTION_POLICIES, payload.policyId)
    if not policy:
        raise HTTPException(status_code=422, detail="审计保留策略不存在。")
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(policy.get("retentionMonths") or 6) * 30)
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), "policyId": policy["id"], "dryRun": payload.dryRun,
        "cutoffAt": cutoff.isoformat(), "status": "queued", "scannedCount": 0, "archivedCount": 0,
        "failureCount": 0, "failureQueue": [], "version": 1, "createdBy": context.user,
        "createdAt": now, "updatedAt": now, "deletedAt": None,
    }
    return save_extension_record(ARCHIVE_TASKS, record, create=True)


@router.get("/archive-tasks")
def archive_tasks(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "operations.audit.view")
    records = list_extension_records(ARCHIVE_TASKS)
    return {"items": records, "total": len(records)}
