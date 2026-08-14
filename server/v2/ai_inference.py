from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission
from server.modules.ai_findings import create_finding, timeline_entry
from server.modules.ai_inference_runs import create_run, list_runs, run_by_id, set_run_deleted, update_run, utc_now
from server.modules.ai_model_assets import asset_by_id
from server.modules.attachments import get_attachment, linked_attachments, sync_attachment_links
from server.modules.auth import AuthContext, request_context
from server.modules.forest_blocks import block_by_code, require_target_block_allowed


router = APIRouter(prefix="/ai/inference-runs", tags=["v2-ai-inference"])
RUN_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}
FINDING_TYPES = {"pest", "fire", "disease", "illegal-cutting", "road-damage", "tree-fall", "other"}


class InferenceRunPayload(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    modelAssetId: str = Field(min_length=1)
    deploymentAssetId: str = ""
    inputAttachmentId: str = Field(min_length=1)
    linkedBlockCodes: list[str] = Field(default_factory=list, min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class InferenceRunPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    modelAssetId: str | None = None
    deploymentAssetId: str | None = None
    inputAttachmentId: str | None = None
    linkedBlockCodes: list[str] | None = None
    parameters: dict[str, Any] | None = None


class InferenceAction(BaseModel):
    output: dict[str, Any] = Field(default_factory=dict)
    outputAttachmentIds: list[str] = Field(default_factory=list)
    errorMessage: str = Field(default="", max_length=2000)


class FindingConversion(BaseModel):
    title: str = Field(default="", max_length=255)
    findingType: str = "other"
    confidence: float = Field(default=0, ge=0, le=1)
    locationText: str = Field(default="", max_length=500)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)


def run_number() -> str:
    return f"IR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def finding_number() -> str:
    return f"AI-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def compact(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def validated_assets(model_id: str, deployment_id: str = "") -> tuple[dict[str, Any], dict[str, Any] | None]:
    model = asset_by_id(model_id)
    if not model or model.get("assetType") != "model-version":
        raise HTTPException(status_code=422, detail="请选择有效的模型版本资产。")
    if model.get("status") not in {"ready", "active"}:
        raise HTTPException(status_code=409, detail="只有就绪或运行中的模型版本可以创建推理任务。")
    deployment = None
    if deployment_id:
        deployment = asset_by_id(deployment_id)
        if not deployment or deployment.get("assetType") != "deployment" or deployment.get("parentId") != model_id:
            raise HTTPException(status_code=422, detail="部署实例必须属于所选模型版本。")
        if deployment.get("status") != "active":
            raise HTTPException(status_code=409, detail="所选部署实例当前未运行。")
    return model, deployment


def validated_blocks(codes: list[str], context: AuthContext) -> list[dict[str, Any]]:
    blocks = []
    for code in compact(codes):
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"林班 {code} 不存在或已删除。")
        require_target_block_allowed(context, block)
        blocks.append(block)
    if not blocks:
        raise HTTPException(status_code=422, detail="推理任务至少需要关联一个正式林班。")
    return blocks


def require_scope(record: dict[str, Any], context: AuthContext) -> None:
    for link in record.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block:
            require_target_block_allowed(context, block)


def get_run(run_id: str, context: AuthContext, *, include_deleted: bool = True) -> dict[str, Any]:
    record = run_by_id(run_id, include_deleted=include_deleted)
    if not record:
        raise HTTPException(status_code=404, detail="AI 推理任务不存在。")
    require_scope(record, context)
    return record


def view(record: dict[str, Any]) -> dict[str, Any]:
    model = asset_by_id(str(record.get("modelAssetId") or ""), include_deleted=True)
    deployment = asset_by_id(str(record.get("deploymentAssetId") or ""), include_deleted=True) if record.get("deploymentAssetId") else None
    inputs = linked_attachments("ai_inference_run", str(record["id"]), "input")
    outputs = linked_attachments("ai_inference_run", str(record["id"]), "output")
    return {**record, "model": model, "deployment": deployment, "inputAttachmentId": str(inputs[0]["id"]) if inputs else "", "inputAttachments": inputs, "outputAttachmentIds": [str(item["id"]) for item in outputs], "outputAttachments": outputs}


def elapsed_ms(started: str | None, completed: str) -> int | None:
    if not started:
        return None
    try:
        return max(0, int((datetime.fromisoformat(completed) - datetime.fromisoformat(started)).total_seconds() * 1000))
    except ValueError:
        return None


@router.get("")
def run_ledger(q: str = Query(default=""), status: str = Query(default=""), model_asset_id: str = Query(default="", alias="modelAssetId"), linked_block_code: str = Query(default="", alias="linkedBlockCode"), include_deleted: bool = Query(default=False, alias="includeDeleted"), limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.inference.view")
    if status and status not in RUN_STATUSES:
        raise HTTPException(status_code=422, detail="不支持的推理任务状态。")
    scoped = []
    for record in list_runs(q, status, model_asset_id, linked_block_code, include_deleted=include_deleted):
        try:
            require_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(view(record))
    return {"items": scoped[offset:offset + limit], "total": len(scoped), "limit": limit, "offset": offset}


@router.get("/export.csv")
def export_runs(q: str = Query(default=""), status: str = Query(default=""), model_asset_id: str = Query(default="", alias="modelAssetId"), context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "ai.inference.view")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["任务编号", "标题", "状态", "模型", "版本", "部署实例", "林班", "提交时间", "开始时间", "完成时间", "耗时(ms)", "识别成果", "错误信息"])
    for record in list_runs(q, status, model_asset_id):
        try:
            require_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        item = view(record)
        writer.writerow([item["runNo"], item["title"], item["status"], (item.get("model") or {}).get("name") or "", (item.get("model") or {}).get("version") or "", (item.get("deployment") or {}).get("name") or "", "、".join(link["code"] for link in item.get("blocks") or []), item["requestedAt"], item.get("startedAt") or "", item.get("completedAt") or "", item.get("durationMs") or "", item.get("findingId") or "", item.get("errorMessage") or ""])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ai-inference-runs.csv"'})


@router.get("/{run_id}")
def run_detail(run_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.inference.view")
    return view(get_run(run_id, context))


@router.post("")
def create_inference(payload: InferenceRunPayload, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.inference.manage")
    validated_assets(payload.modelAssetId.strip(), payload.deploymentAssetId.strip())
    get_attachment(payload.inputAttachmentId.strip(), context)
    blocks = validated_blocks(payload.linkedBlockCodes, context)
    now = utc_now()
    record = {"id": str(uuid.uuid4()), "runNo": run_number(), "title": payload.title.strip(), "status": "queued", "modelAssetId": payload.modelAssetId.strip(), "deploymentAssetId": payload.deploymentAssetId.strip(), "findingId": "", "parameters": payload.parameters, "output": {}, "errorMessage": "", "requestedAt": now, "startedAt": None, "completedAt": None, "durationMs": None, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None, "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks]}
    created = create_run(record)
    sync_attachment_links("ai_inference_run", created["id"], [payload.inputAttachmentId.strip()], context, relation_type="input")
    return view(created)


@router.patch("/{run_id}")
def patch_inference(run_id: str, payload: InferenceRunPatch, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.inference.manage")
    current = get_run(run_id, context, include_deleted=False)
    if current["status"] != "queued":
        raise HTTPException(status_code=409, detail="只有排队中的推理任务可以编辑。")
    changes = payload.model_dump(exclude_unset=True)
    input_id = changes.pop("inputAttachmentId", None)
    block_codes = changes.pop("linkedBlockCodes", None)
    updated = {**current, **changes}
    validated_assets(str(updated["modelAssetId"]), str(updated.get("deploymentAssetId") or ""))
    if block_codes is not None:
        blocks = validated_blocks(block_codes, context)
        updated["blocks"] = [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks]
    if input_id is not None:
        get_attachment(input_id, context)
    saved = update_run(updated)
    if input_id is not None:
        sync_attachment_links("ai_inference_run", run_id, [input_id], context, relation_type="input")
    return view(saved)


@router.delete("/{run_id}")
def delete_inference(run_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.inference.manage")
    record = get_run(run_id, context, include_deleted=False)
    if record["status"] not in {"queued", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="运行中或已成功的推理任务不能删除。")
    set_run_deleted(run_id, deleted=True)
    return {"ok": True, "deleted": record["runNo"]}


@router.post("/{run_id}/restore")
def restore_inference(run_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.inference.manage")
    record = get_run(run_id, context)
    if record.get("deletedAt"):
        set_run_deleted(run_id, deleted=False)
    return view(get_run(run_id, context, include_deleted=False))


@router.post("/{run_id}/actions/{action}")
def apply_action(run_id: str, action: str, payload: InferenceAction, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.inference.operate")
    record = get_run(run_id, context, include_deleted=False)
    status = record["status"]
    now = utc_now()
    if action == "start":
        if status != "queued":
            raise HTTPException(status_code=409, detail="只有排队中的任务可以开始运行。")
        return view(update_run({**record, "status": "running", "startedAt": now, "errorMessage": ""}))
    if action == "succeed":
        if status != "running":
            raise HTTPException(status_code=409, detail="只有运行中的任务可以标记成功。")
        for attachment_id in payload.outputAttachmentIds:
            get_attachment(attachment_id, context)
        saved = update_run({**record, "status": "succeeded", "output": payload.output, "errorMessage": "", "completedAt": now, "durationMs": elapsed_ms(record.get("startedAt"), now)})
        sync_attachment_links("ai_inference_run", run_id, payload.outputAttachmentIds, context, relation_type="output")
        return view(saved)
    if action == "fail":
        if status != "running":
            raise HTTPException(status_code=409, detail="只有运行中的任务可以标记失败。")
        if not payload.errorMessage.strip():
            raise HTTPException(status_code=422, detail="标记失败时必须填写错误信息。")
        return view(update_run({**record, "status": "failed", "errorMessage": payload.errorMessage.strip(), "completedAt": now, "durationMs": elapsed_ms(record.get("startedAt"), now)}))
    if action == "cancel":
        if status not in {"queued", "running"}:
            raise HTTPException(status_code=409, detail="当前任务不能取消。")
        return view(update_run({**record, "status": "cancelled", "errorMessage": payload.errorMessage.strip(), "completedAt": now, "durationMs": elapsed_ms(record.get("startedAt"), now)}))
    raise HTTPException(status_code=404, detail="不支持的推理任务操作。")


@router.post("/{run_id}/finding")
def create_finding_from_run(run_id: str, payload: FindingConversion, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "ai.inference.operate")
    require_permission(context, "ai.findings.ingest")
    record = get_run(run_id, context, include_deleted=False)
    if record["status"] != "succeeded":
        raise HTTPException(status_code=409, detail="只有成功的推理任务可以生成识别成果。")
    if record.get("findingId"):
        raise HTTPException(status_code=409, detail="该推理任务已经生成识别成果。")
    finding_type = payload.findingType.strip().lower()
    if finding_type not in FINDING_TYPES:
        raise HTTPException(status_code=422, detail="不支持的识别类型。")
    model = asset_by_id(record["modelAssetId"], include_deleted=True) or {}
    source = linked_attachments("ai_inference_run", run_id, "input")
    if not source:
        raise HTTPException(status_code=409, detail="推理任务缺少输入附件，不能生成可追溯成果。")
    now = utc_now()
    finding_id = str(uuid.uuid4())
    finding = {"id": finding_id, "findingNo": finding_number(), "title": payload.title.strip() or record["title"], "findingType": finding_type, "status": "pending", "modelCode": str(model.get("code") or "unknown"), "modelVersion": str(model.get("version") or "unknown"), "confidence": payload.confidence, "sourceAssetUrl": str(source[0].get("downloadUrl") or ""), "droneMissionId": "", "deviceId": "", "deviceCode": "", "locationText": payload.locationText.strip(), "longitude": payload.longitude, "latitude": payload.latitude, "result": {**(record.get("output") or {}), "inferenceRunId": run_id, "humanConfirmed": False}, "review": {}, "safetyAlertId": "", "occurredAt": record.get("completedAt") or now, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None, "blocks": list(record.get("blocks") or [])}
    created = create_finding(finding, timeline_entry("ingest", "", "pending", context.user, "由 AI 推理任务生成，等待人工复核。", {"inferenceRunId": run_id, "runNo": record["runNo"]}))
    sync_attachment_links("ai_finding", finding_id, [str(source[0]["id"])], context, relation_type="source")
    saved = update_run({**record, "findingId": finding_id})
    return {"run": view(saved), "finding": created}
