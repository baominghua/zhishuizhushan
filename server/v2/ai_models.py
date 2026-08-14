from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission
from server.modules.ai_inference_runs import list_runs
from server.modules.ai_model_assets import asset_by_id, create_asset, list_assets, set_asset_deleted, update_asset, utc_now
from server.modules.attachments import linked_attachments, sync_attachment_links
from server.modules.auth import AuthContext, request_context


router = APIRouter(prefix="/ai/model-assets", tags=["v2-ai-models"])
ASSET_TYPES = {"dataset", "model-version", "deployment", "evaluation"}
ASSET_STATUSES = {"draft", "ready", "active", "paused", "failed", "retired", "archived"}
PARENT_TYPES = {"model-version": "dataset", "deployment": "model-version", "evaluation": "model-version"}


class ModelAssetPayload(BaseModel):
    assetType: str
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=128)
    version: str = Field(default="", max_length=96)
    status: str = "draft"
    parentId: str = ""
    framework: str = Field(default="", max_length=128)
    runtimeTarget: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=2000)
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    attachmentIds: list[str] = Field(default_factory=list)


class ModelAssetPatch(BaseModel):
    assetType: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=128)
    version: str | None = Field(default=None, max_length=96)
    status: str | None = None
    parentId: str | None = None
    framework: str | None = Field(default=None, max_length=128)
    runtimeTarget: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    metrics: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    attachmentIds: list[str] | None = None


def normalized(value: str, allowed: set[str], label: str) -> str:
    result = str(value or "").strip().lower()
    if result not in allowed:
        raise HTTPException(status_code=422, detail=f"不支持的{label}。")
    return result


def asset_number(asset_type: str) -> str:
    prefix = {"dataset": "DS", "model-version": "MV", "deployment": "DP", "evaluation": "EV"}[asset_type]
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def validate_parent(asset_type: str, parent_id: str, current_id: str = "") -> dict[str, Any] | None:
    expected = PARENT_TYPES.get(asset_type)
    if not expected:
        if parent_id:
            raise HTTPException(status_code=422, detail="数据集不应设置上级资产。")
        return None
    if not parent_id:
        raise HTTPException(status_code=422, detail=f"{asset_type} 必须关联一个 {expected}。")
    if parent_id == current_id:
        raise HTTPException(status_code=422, detail="资产不能关联自身。")
    parent = asset_by_id(parent_id)
    if not parent or parent.get("assetType") != expected:
        raise HTTPException(status_code=422, detail=f"上级资产必须是有效的 {expected}。")
    return parent


def asset_view(record: dict[str, Any]) -> dict[str, Any]:
    parent = asset_by_id(str(record.get("parentId") or ""), include_deleted=True) if record.get("parentId") else None
    attachments = linked_attachments("ai_model_asset", str(record["id"]), "artifact")
    return {
        **record,
        "parent": {"id": parent["id"], "assetNo": parent["assetNo"], "name": parent["name"], "assetType": parent["assetType"]} if parent else None,
        "attachmentIds": [str(item["id"]) for item in attachments],
        "attachments": attachments,
    }


def get_asset(asset_id: str, *, include_deleted: bool = True) -> dict[str, Any]:
    record = asset_by_id(asset_id, include_deleted=include_deleted)
    if not record:
        raise HTTPException(status_code=404, detail="AI 模型资产不存在。")
    return record


@router.get("")
def asset_ledger(
    q: str = Query(default=""), asset_type: str = Query(default="", alias="assetType"),
    status: str = Query(default=""), include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "ai.models.view")
    if asset_type:
        normalized(asset_type, ASSET_TYPES, "资产类型")
    if status:
        normalized(status, ASSET_STATUSES, "资产状态")
    records = list_assets(q, asset_type, status, include_deleted=include_deleted)
    return {"items": [asset_view(item) for item in records[offset:offset + limit]], "total": len(records), "limit": limit, "offset": offset}


@router.get("/export.csv")
def export_assets(
    q: str = Query(default=""), asset_type: str = Query(default="", alias="assetType"), status: str = Query(default=""),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "ai.models.view")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["资产编号", "类型", "名称", "代码", "版本", "状态", "上级资产", "框架", "运行目标", "指标", "更新时间"])
    for record in list_assets(q, asset_type, status):
        parent = asset_by_id(str(record.get("parentId") or ""), include_deleted=True) if record.get("parentId") else None
        writer.writerow([record["assetNo"], record["assetType"], record["name"], record["code"], record["version"], record["status"], (parent or {}).get("assetNo") or "", record["framework"], record["runtimeTarget"], record["metrics"], record["updatedAt"]])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ai-model-assets.csv"'})


@router.get("/{asset_id}")
def asset_detail(asset_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.view")
    return asset_view(get_asset(asset_id))


@router.post("")
def create_model_asset(payload: ModelAssetPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    asset_type = normalized(payload.assetType, ASSET_TYPES, "资产类型")
    status = normalized(payload.status, ASSET_STATUSES, "资产状态")
    parent_id = payload.parentId.strip()
    validate_parent(asset_type, parent_id)
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), "assetNo": asset_number(asset_type), "assetType": asset_type,
        "name": payload.name.strip(), "code": payload.code.strip(), "version": payload.version.strip(),
        "status": status, "parentId": parent_id, "framework": payload.framework.strip(),
        "runtimeTarget": payload.runtimeTarget.strip(), "description": payload.description.strip(),
        "metrics": payload.metrics, "metadata": payload.metadata, "createdBy": context.user,
        "createdAt": now, "updatedAt": now, "deletedAt": None,
    }
    created = create_asset(record)
    if payload.attachmentIds:
        sync_attachment_links("ai_model_asset", str(created["id"]), payload.attachmentIds, context, relation_type="artifact")
    return asset_view(created)


@router.patch("/{asset_id}")
def patch_model_asset(asset_id: str, payload: ModelAssetPatch, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    current = get_asset(asset_id, include_deleted=False)
    changes = payload.model_dump(exclude_unset=True)
    attachment_ids = changes.pop("attachmentIds", None)
    updated = {**current, **changes}
    updated["assetType"] = normalized(str(updated["assetType"]), ASSET_TYPES, "资产类型")
    updated["status"] = normalized(str(updated["status"]), ASSET_STATUSES, "资产状态")
    updated["parentId"] = str(updated.get("parentId") or "").strip()
    validate_parent(updated["assetType"], updated["parentId"], asset_id)
    saved = update_asset(updated)
    if attachment_ids is not None:
        sync_attachment_links("ai_model_asset", asset_id, attachment_ids, context, relation_type="artifact")
    return asset_view(saved)


@router.delete("/{asset_id}")
def delete_model_asset(asset_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    get_asset(asset_id, include_deleted=False)
    children = [item for item in list_assets(include_deleted=False) if item.get("parentId") == asset_id]
    if children:
        raise HTTPException(status_code=409, detail="该资产仍有关联的下级模型、部署或评测记录，不能删除。")
    inference_runs = [
        item for item in list_runs(include_deleted=False)
        if item.get("modelAssetId") == asset_id or item.get("deploymentAssetId") == asset_id
    ]
    if inference_runs:
        raise HTTPException(status_code=409, detail="该资产已被 AI 推理任务引用，不能删除。")
    set_asset_deleted(asset_id, deleted=True)
    return {"ok": True, "deleted": asset_id}


@router.post("/{asset_id}/restore")
def restore_model_asset(asset_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.models.manage")
    record = get_asset(asset_id)
    if record.get("parentId") and not asset_by_id(str(record["parentId"])):
        raise HTTPException(status_code=409, detail="请先恢复该资产的上级记录。")
    if record.get("deletedAt"):
        set_asset_deleted(asset_id, deleted=False)
    return asset_view(get_asset(asset_id, include_deleted=False))
