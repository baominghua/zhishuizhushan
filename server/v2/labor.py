from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.forest_blocks import block_by_code, require_target_block_allowed
from server.modules.extension_store import save_extension_record
from server.modules.labor import (
    create_job,
    job_by_id,
    list_jobs,
    list_teams,
    list_workers,
    replace_draft_job,
    save_team,
    save_worker,
    set_job_deleted,
    set_team_deleted,
    set_worker_deleted,
    team_by_id,
    timeline_entry,
    update_job,
    utc_now,
    worker_by_id,
)


router = APIRouter(prefix="/labor", tags=["v2-labor"])
WORKER_STATUSES = {"available", "working", "inactive"}
TRAINING_STATUSES = {"valid", "expiring", "missing"}
TEAM_STATUSES = {"active", "busy", "inactive"}
JOB_STATUSES = {"draft", "published", "matched", "contracted", "working", "submitted", "settled", "closed"}
WORK_TYPES = {"tending", "harvest", "transport", "fertilization", "pest-control", "survey", "other"}
EMPLOYER_TYPES = {"farmer", "cooperative", "enterprise", "government", "other"}
PRICE_UNITS = {"mu", "day", "ton", "job"}


class WorkerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    mobile: str = Field(default="", max_length=32)
    idCardMask: str = Field(default="", max_length=32)
    gender: str = Field(default="", max_length=16)
    employmentStatus: str = "available"
    skillCodes: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    trainingStatus: str = "missing"
    creditScore: float = Field(default=100, ge=0, le=100)
    homeAddress: str = Field(default="", max_length=500)
    emergencyContact: str = Field(default="", max_length=128)
    notes: str = Field(default="", max_length=2000)


class WorkerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    mobile: str | None = Field(default=None, max_length=32)
    idCardMask: str | None = Field(default=None, max_length=32)
    gender: str | None = Field(default=None, max_length=16)
    employmentStatus: str | None = None
    skillCodes: list[str] | None = None
    qualifications: list[str] | None = None
    trainingStatus: str | None = None
    creditScore: float | None = Field(default=None, ge=0, le=100)
    homeAddress: str | None = Field(default=None, max_length=500)
    emergencyContact: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=2000)


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    status: str = "active"
    leaderWorkerId: str
    memberIds: list[str] = Field(default_factory=list)
    contactPhone: str = Field(default="", max_length=32)
    serviceArea: str = Field(default="", max_length=500)
    skillCodes: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)


class TeamPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    status: str | None = None
    leaderWorkerId: str | None = None
    memberIds: list[str] | None = None
    contactPhone: str | None = Field(default=None, max_length=32)
    serviceArea: str | None = Field(default=None, max_length=500)
    skillCodes: list[str] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class LaborJobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    employerType: str = "cooperative"
    employerId: str = Field(default="", max_length=36)
    employerName: str = Field(min_length=1, max_length=160)
    workType: str = "tending"
    requiredHeadcount: int = Field(ge=1, le=10000)
    unitPrice: float = Field(ge=0)
    priceUnit: str = "mu"
    plannedStartAt: str
    plannedEndAt: str
    linkedBlockCodes: list[str] = Field(min_length=1)
    instructions: str = Field(default="", max_length=5000)


class LaborAction(BaseModel):
    note: str = Field(default="", max_length=2000)
    teamId: str = ""
    contractNo: str = Field(default="", max_length=96)
    contractStartAt: str = ""
    contractEndAt: str = ""
    paymentTerms: str = Field(default="", max_length=1000)
    workerId: str = ""
    workDate: str = ""
    checkInAt: str = ""
    checkOutAt: str = ""
    workHours: float | None = Field(default=None, ge=0, le=24)
    workQuantity: float | None = Field(default=None, ge=0)
    attendanceStatus: str = "present"
    helmetDetected: bool | None = None
    gpsValid: bool | None = None
    insideGeofence: bool | None = None
    verificationEvidence: dict[str, Any] = Field(default_factory=dict)
    actualQuantity: float | None = Field(default=None, ge=0)
    settlementAmount: float | None = Field(default=None, ge=0)
    evidenceUrls: list[str] = Field(default_factory=list)


def record_number(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def validate_enum(value: str, allowed: set[str], label: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise HTTPException(status_code=422, detail=f"不支持的{label}。")
    return normalized


def parse_timestamp(value: str, label: str, *, required: bool = False) -> str | None:
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


def csv_response(filename: str, headers: list[str], rows: list[list[Any]]) -> Response:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        content="\ufeff" + stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def validated_blocks(codes: list[str], context: AuthContext) -> list[dict[str, Any]]:
    normalized = compact(codes)
    if not normalized:
        raise HTTPException(status_code=422, detail="用工任务至少需要关联一个正式林班。")
    blocks: list[dict[str, Any]] = []
    for code in normalized:
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"林班 {code} 不存在或已删除。")
        require_target_block_allowed(context, block)
        blocks.append(block)
    return blocks


def require_job_scope(record: dict[str, Any], context: AuthContext) -> None:
    for link in record.get("blocks") or []:
        block = block_by_code(str(link.get("code") or ""))
        if block:
            require_target_block_allowed(context, block)


def get_job(job_id: str, context: AuthContext, *, include_deleted: bool = False) -> dict[str, Any]:
    record = job_by_id(job_id, include_deleted=include_deleted)
    if not record:
        raise HTTPException(status_code=404, detail="用工任务不存在。")
    require_job_scope(record, context)
    return record


def worker_record(payload: WorkerCreate, actor: str) -> dict[str, Any]:
    now = utc_now()
    return {
        "id": str(uuid.uuid4()), "workerNo": record_number("RY"), "name": payload.name.strip(),
        "mobile": payload.mobile.strip(), "idCardMask": payload.idCardMask.strip(), "gender": payload.gender.strip(),
        "employmentStatus": validate_enum(payload.employmentStatus, WORKER_STATUSES, "人员状态"),
        "skillCodes": compact(payload.skillCodes), "qualifications": compact(payload.qualifications),
        "trainingStatus": validate_enum(payload.trainingStatus, TRAINING_STATUSES, "培训状态"),
        "creditScore": payload.creditScore, "homeAddress": payload.homeAddress.strip(),
        "emergencyContact": payload.emergencyContact.strip(), "notes": payload.notes.strip(),
        "createdBy": actor, "createdAt": now, "updatedAt": now, "deletedAt": None,
    }


def team_members(leader_id: str, member_ids: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    leader = worker_by_id(leader_id)
    if not leader:
        raise HTTPException(status_code=422, detail="班组负责人不在正式人员台账中。")
    ids = compact([leader_id, *member_ids])
    members: list[dict[str, Any]] = []
    for worker_id in ids:
        worker = worker_by_id(worker_id)
        if not worker:
            raise HTTPException(status_code=422, detail=f"人员 {worker_id} 不存在或已停用。")
        members.append({
            "id": worker["id"], "workerNo": worker["workerNo"], "name": worker["name"],
            "role": "leader" if worker_id == leader_id else "member", "joinedAt": utc_now(),
        })
    return leader, members


@router.get("/workers")
def worker_ledger(
    q: str = Query(default=""), status: str = Query(default=""),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "labor.view")
    if status:
        validate_enum(status, WORKER_STATUSES, "人员状态")
    records = list_workers(q, status, include_deleted=include_deleted)
    return {"items": records[offset:offset + limit], "total": len(records), "limit": limit, "offset": offset}


@router.post("/workers")
def add_worker(payload: WorkerCreate, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.workers.manage")
    return save_worker(worker_record(payload, context.user), create=True)


@router.get("/workers-export.csv")
def export_workers(
    q: str = Query(default=""), status: str = Query(default=""),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "labor.view")
    if status:
        validate_enum(status, WORKER_STATUSES, "人员状态")
    records = list_workers(q, status)
    return csv_response("labor-workers.csv", ["人员编号", "姓名", "手机", "从业状态", "培训状态", "技能", "资格证书", "信用分", "更新时间"], [
        [item["workerNo"], item["name"], item["mobile"], item["employmentStatus"], item["trainingStatus"],
         "、".join(item.get("skillCodes") or []), "、".join(item.get("qualifications") or []), item["creditScore"], item["updatedAt"]]
        for item in records
    ])


@router.get("/workers/{worker_id}")
def worker_detail(
    worker_id: str, include_deleted: bool = Query(default=False, alias="includeDeleted"),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "labor.view")
    record = worker_by_id(worker_id, include_deleted=include_deleted)
    if not record:
        raise HTTPException(status_code=404, detail="劳务人员不存在。")
    return record


@router.patch("/workers/{worker_id}")
def edit_worker(worker_id: str, payload: WorkerPatch, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.workers.manage")
    record = worker_by_id(worker_id)
    if not record:
        raise HTTPException(status_code=404, detail="劳务人员不存在。")
    changes = payload.model_dump(exclude_unset=True)
    if "employmentStatus" in changes:
        changes["employmentStatus"] = validate_enum(changes["employmentStatus"], WORKER_STATUSES, "人员状态")
    if "trainingStatus" in changes:
        changes["trainingStatus"] = validate_enum(changes["trainingStatus"], TRAINING_STATUSES, "培训状态")
    for key in ("skillCodes", "qualifications"):
        if key in changes:
            changes[key] = compact(changes[key])
    return save_worker({**record, **changes, "updatedAt": utc_now()}, create=False)


@router.delete("/workers/{worker_id}")
def delete_worker(worker_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.workers.manage")
    record = worker_by_id(worker_id)
    if not record:
        raise HTTPException(status_code=404, detail="劳务人员不存在。")
    occupied = [team["name"] for team in list_teams() if any(member.get("id") == worker_id for member in team.get("members") or [])]
    if occupied:
        raise HTTPException(status_code=409, detail=f"该人员仍属于班组：{'、'.join(occupied[:3])}，请先调整班组成员。")
    try:
        return set_worker_deleted(worker_id, deleted=True)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workers/{worker_id}/restore")
def restore_worker(worker_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.workers.manage")
    try:
        return set_worker_deleted(worker_id, deleted=False)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="已删除的劳务人员不存在。") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/teams")
def team_ledger(
    q: str = Query(default=""), status: str = Query(default=""),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "labor.view")
    if status:
        validate_enum(status, TEAM_STATUSES, "班组状态")
    records = list_teams(q, status, include_deleted=include_deleted)
    return {"items": records[offset:offset + limit], "total": len(records), "limit": limit, "offset": offset}


@router.post("/teams")
def add_team(payload: TeamCreate, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.teams.manage")
    leader, members = team_members(payload.leaderWorkerId, payload.memberIds)
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), "teamNo": record_number("BZ"), "name": payload.name.strip(),
        "status": validate_enum(payload.status, TEAM_STATUSES, "班组状态"),
        "leaderWorkerId": leader["id"], "leaderName": leader["name"],
        "contactPhone": payload.contactPhone.strip() or leader.get("mobile") or "",
        "serviceArea": payload.serviceArea.strip(), "skillCodes": compact(payload.skillCodes),
        "notes": payload.notes.strip(), "members": members, "createdBy": context.user,
        "createdAt": now, "updatedAt": now, "deletedAt": None,
    }
    return save_team(record, create=True)


@router.get("/teams-export.csv")
def export_teams(
    q: str = Query(default=""), status: str = Query(default=""),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "labor.view")
    if status:
        validate_enum(status, TEAM_STATUSES, "班组状态")
    records = list_teams(q, status)
    return csv_response("labor-teams.csv", ["班组编号", "班组名称", "负责人", "联系电话", "状态", "成员数", "技能", "服务范围", "更新时间"], [
        [item["teamNo"], item["name"], item["leaderName"], item["contactPhone"], item["status"],
         len(item.get("members") or []), "、".join(item.get("skillCodes") or []), item["serviceArea"], item["updatedAt"]]
        for item in records
    ])


@router.get("/teams/{team_id}")
def team_detail(
    team_id: str, include_deleted: bool = Query(default=False, alias="includeDeleted"),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "labor.view")
    record = team_by_id(team_id, include_deleted=include_deleted)
    if not record:
        raise HTTPException(status_code=404, detail="劳务班组不存在。")
    return record


@router.patch("/teams/{team_id}")
def edit_team(team_id: str, payload: TeamPatch, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.teams.manage")
    record = team_by_id(team_id)
    if not record:
        raise HTTPException(status_code=404, detail="劳务班组不存在。")
    changes = payload.model_dump(exclude_unset=True)
    leader_id = str(changes.pop("leaderWorkerId", record["leaderWorkerId"]))
    member_ids = changes.pop("memberIds", [item["id"] for item in record.get("members") or []])
    leader, members = team_members(leader_id, member_ids)
    if "status" in changes:
        changes["status"] = validate_enum(changes["status"], TEAM_STATUSES, "班组状态")
    if "skillCodes" in changes:
        changes["skillCodes"] = compact(changes["skillCodes"])
    updated = {**record, **changes, "leaderWorkerId": leader["id"], "leaderName": leader["name"], "members": members, "updatedAt": utc_now()}
    return save_team(updated, create=False)


@router.delete("/teams/{team_id}")
def delete_team(team_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.teams.manage")
    record = team_by_id(team_id)
    if not record:
        raise HTTPException(status_code=404, detail="劳务班组不存在。")
    occupied = [job["jobNo"] for job in list_jobs() if job.get("teamId") == team_id and job.get("status") != "closed"]
    if occupied:
        raise HTTPException(status_code=409, detail=f"班组仍有关联的在办任务：{'、'.join(occupied[:3])}。")
    try:
        return set_team_deleted(team_id, deleted=True)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/teams/{team_id}/restore")
def restore_team(team_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.teams.manage")
    try:
        return set_team_deleted(team_id, deleted=False)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="已删除的劳务班组不存在。") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/jobs")
def job_ledger(
    q: str = Query(default=""), status: str = Query(default=""),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "labor.view")
    if status:
        validate_enum(status, JOB_STATUSES, "任务状态")
    scoped: list[dict[str, Any]] = []
    for record in list_jobs(q, status, linked_block_code, include_deleted=include_deleted):
        try:
            require_job_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(record)
    return {"items": scoped[offset:offset + limit], "total": len(scoped), "limit": limit, "offset": offset}


@router.post("/jobs")
def add_job(payload: LaborJobCreate, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.jobs.create")
    blocks = validated_blocks(payload.linkedBlockCodes, context)
    start = parse_timestamp(payload.plannedStartAt, "计划开始时间", required=True)
    end = parse_timestamp(payload.plannedEndAt, "计划结束时间", required=True)
    if datetime.fromisoformat(str(end)) <= datetime.fromisoformat(str(start)):
        raise HTTPException(status_code=422, detail="计划结束时间必须晚于开始时间。")
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()), "jobNo": record_number("YG"), "title": payload.title.strip(), "status": "draft",
        "employerType": validate_enum(payload.employerType, EMPLOYER_TYPES, "发包方类型"),
        "employerId": payload.employerId.strip(), "employerName": payload.employerName.strip(),
        "workType": validate_enum(payload.workType, WORK_TYPES, "作业类型"), "requiredHeadcount": payload.requiredHeadcount,
        "unitPrice": payload.unitPrice, "priceUnit": validate_enum(payload.priceUnit, PRICE_UNITS, "计价单位"),
        "plannedStartAt": start, "plannedEndAt": end, "teamId": "", "teamName": "", "contractNo": "",
        "contractStartAt": None, "contractEndAt": None, "paymentTerms": "", "actualQuantity": None,
        "settlementAmount": None, "settlement": {}, "instructions": payload.instructions.strip(), "version": 1,
        "createdBy": context.user, "createdAt": now, "updatedAt": now, "closedAt": None, "deletedAt": None,
        "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks],
    }
    return create_job(record, timeline_entry("create", "", "draft", context.user, "用工任务草稿已建立。"))


@router.get("/jobs-export.csv")
def export_jobs(
    q: str = Query(default=""), status: str = Query(default=""),
    linked_block_code: str = Query(default="", alias="linkedBlockCode"),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "labor.view")
    if status:
        validate_enum(status, JOB_STATUSES, "任务状态")
    scoped: list[dict[str, Any]] = []
    for record in list_jobs(q, status, linked_block_code):
        try:
            require_job_scope(record, context)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        scoped.append(record)
    return csv_response("labor-jobs.csv", ["任务编号", "任务名称", "发包方", "作业类型", "状态", "需求人数", "单价", "计价单位", "计划开始", "计划结束", "承接班组", "合同编号", "关联林班", "结算金额", "更新时间"], [
        [item["jobNo"], item["title"], item["employerName"], item["workType"], item["status"],
         item["requiredHeadcount"], item["unitPrice"], item["priceUnit"], item["plannedStartAt"], item["plannedEndAt"],
         item.get("teamName") or "", item.get("contractNo") or "", "、".join(block["code"] for block in item.get("blocks") or []),
         item.get("settlementAmount") if item.get("settlementAmount") is not None else "", item["updatedAt"]]
        for item in scoped
    ])


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.view")
    return get_job(job_id, context)


@router.patch("/jobs/{job_id}")
def edit_job(job_id: str, payload: LaborJobCreate, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.jobs.create")
    record = get_job(job_id, context)
    if record.get("status") != "draft":
        raise HTTPException(status_code=409, detail="只有草稿用工任务可以编辑。")
    blocks = validated_blocks(payload.linkedBlockCodes, context)
    start = parse_timestamp(payload.plannedStartAt, "计划开始时间", required=True)
    end = parse_timestamp(payload.plannedEndAt, "计划结束时间", required=True)
    if datetime.fromisoformat(str(end)) <= datetime.fromisoformat(str(start)):
        raise HTTPException(status_code=422, detail="计划结束时间必须晚于开始时间。")
    updated = {
        **record, "title": payload.title.strip(),
        "employerType": validate_enum(payload.employerType, EMPLOYER_TYPES, "发包方类型"),
        "employerId": payload.employerId.strip(), "employerName": payload.employerName.strip(),
        "workType": validate_enum(payload.workType, WORK_TYPES, "作业类型"),
        "requiredHeadcount": payload.requiredHeadcount, "unitPrice": payload.unitPrice,
        "priceUnit": validate_enum(payload.priceUnit, PRICE_UNITS, "计价单位"),
        "plannedStartAt": start, "plannedEndAt": end, "instructions": payload.instructions.strip(),
        "blocks": [{"id": str(block["id"]), "code": str(block["blockCode"])} for block in blocks],
    }
    try:
        return replace_draft_job(updated, timeline_entry("edit", "draft", "draft", context.user, "用工任务草稿已修改。"))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.jobs.create")
    get_job(job_id, context)
    try:
        return set_job_deleted(job_id, deleted=True, actor=context.user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="用工任务不存在。") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/restore")
def restore_job(job_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "labor.jobs.create")
    get_job(job_id, context, include_deleted=True)
    try:
        return set_job_deleted(job_id, deleted=False, actor=context.user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="已删除的用工任务不存在。") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/actions/{action}")
def apply_job_action(job_id: str, action: str, payload: LaborAction, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    permission = {
        "publish": "labor.jobs.dispatch", "match": "labor.jobs.dispatch", "contract": "labor.jobs.dispatch",
        "start": "labor.jobs.operate", "attendance": "labor.jobs.operate", "submit": "labor.jobs.operate",
        "return": "labor.jobs.settle", "settle": "labor.jobs.settle", "close": "labor.jobs.settle",
    }.get(action)
    if not permission:
        raise HTTPException(status_code=404, detail="不支持的劳务任务操作。")
    require_permission(context, permission)
    record = get_job(job_id, context)
    status = str(record["status"])
    note = payload.note.strip()

    if action == "publish":
        if status != "draft":
            raise HTTPException(status_code=409, detail="只有草稿任务可以发布。")
        return update_job({**record, "status": "published"}, timeline_entry(action, status, "published", context.user, note or "用工需求已发布。"))
    if action == "match":
        if status != "published":
            raise HTTPException(status_code=409, detail="只有已发布任务可以匹配班组。")
        team = team_by_id(payload.teamId.strip())
        if not team or team.get("status") == "inactive":
            raise HTTPException(status_code=422, detail="请选择可用的正式劳务班组。")
        data = {"teamId": team["id"], "teamName": team["name"], "memberCount": len(team.get("members") or [])}
        return update_job({**record, "status": "matched", "teamId": team["id"], "teamName": team["name"]}, timeline_entry(action, status, "matched", context.user, note or f"已匹配 {team['name']}。", data))
    if action == "contract":
        if status != "matched":
            raise HTTPException(status_code=409, detail="完成班组匹配后才能签订合同。")
        contract_no = payload.contractNo.strip()
        if not contract_no:
            raise HTTPException(status_code=422, detail="合同编号不能为空。")
        start = parse_timestamp(payload.contractStartAt, "合同开始时间", required=True)
        end = parse_timestamp(payload.contractEndAt, "合同结束时间", required=True)
        if datetime.fromisoformat(str(end)) <= datetime.fromisoformat(str(start)):
            raise HTTPException(status_code=422, detail="合同结束时间必须晚于开始时间。")
        data = {"contractNo": contract_no, "contractStartAt": start, "contractEndAt": end}
        return update_job({**record, "status": "contracted", "contractNo": contract_no, "contractStartAt": start, "contractEndAt": end, "paymentTerms": payload.paymentTerms.strip()}, timeline_entry(action, status, "contracted", context.user, note or "劳务合同已签订。", data))
    if action == "start":
        if status != "contracted":
            raise HTTPException(status_code=409, detail="合同生效后才能开始作业。")
        return update_job({**record, "status": "working"}, timeline_entry(action, status, "working", context.user, note or "班组已进场作业。"))
    if action == "attendance":
        if status != "working":
            raise HTTPException(status_code=409, detail="只有作业中的任务可以登记考勤。")
        worker = worker_by_id(payload.workerId.strip())
        team = team_by_id(str(record.get("teamId") or ""))
        member_ids = {str(item.get("id")) for item in (team or {}).get("members") or []}
        if not worker or worker["id"] not in member_ids:
            raise HTTPException(status_code=422, detail="考勤人员必须属于当前匹配班组。")
        try:
            work_date = datetime.fromisoformat(payload.workDate).date().isoformat()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="作业日期格式不正确。") from exc
        if payload.workHours is None:
            raise HTTPException(status_code=422, detail="请填写有效工时。")
        now = utc_now()
        factors_provided = all(
            value is not None
            for value in (payload.helmetDetected, payload.gpsValid, payload.insideGeofence)
        )
        factor_passed = bool(
            payload.helmetDetected and payload.gpsValid and payload.insideGeofence
        ) if factors_provided else None
        attendance_status = (
            "verified" if factor_passed else "exception" if factors_provided
            else (payload.attendanceStatus.strip() or "present")
        )
        attendance = {
            "id": str(uuid.uuid4()), "workerId": worker["id"], "workerNo": worker["workerNo"], "workerName": worker["name"],
            "workDate": work_date, "checkInAt": parse_timestamp(payload.checkInAt, "签到时间"),
            "checkOutAt": parse_timestamp(payload.checkOutAt, "签退时间"), "workHours": payload.workHours,
            "workQuantity": payload.workQuantity, "status": attendance_status,
            "verifierName": context.user, "note": note, "createdBy": context.user, "createdAt": now, "updatedAt": now,
        }
        updated = update_job(record, timeline_entry(action, status, status, context.user, note or f"已登记 {worker['name']} 的 {work_date} 考勤。", {"workerId": worker["id"], "workDate": work_date, "workHours": payload.workHours}), attendance)
        if factors_provided:
            save_extension_record(
                "labor-attendance-verifications",
                {
                    "id": str(uuid.uuid4()), "attendanceId": attendance["id"], "laborJobId": record["id"],
                    "workerId": worker["id"], "workDate": work_date, "helmetDetected": payload.helmetDetected,
                    "gpsValid": payload.gpsValid, "insideGeofence": payload.insideGeofence,
                    "evidence": payload.verificationEvidence, "status": attendance_status,
                    "reviewStatus": "pending" if attendance_status == "exception" else "not-required",
                    "version": 1, "createdBy": context.user, "createdAt": now, "updatedAt": now, "deletedAt": None,
                },
                create=True,
            )
        return updated
    if action == "submit":
        if status != "working":
            raise HTTPException(status_code=409, detail="只有作业中的任务可以提交验收。")
        if not record.get("attendance"):
            raise HTTPException(status_code=422, detail="至少登记一条考勤后才能提交验收。")
        if payload.actualQuantity is None:
            raise HTTPException(status_code=422, detail="请填写实际完成工作量。")
        return update_job({**record, "status": "submitted", "actualQuantity": payload.actualQuantity}, timeline_entry(action, status, "submitted", context.user, note or "班组已提交完工记录。", {"actualQuantity": payload.actualQuantity, "evidenceUrls": compact(payload.evidenceUrls)}))
    if action == "return":
        if status != "submitted" or not note:
            raise HTTPException(status_code=409 if status != "submitted" else 422, detail="当前任务不能退回，或尚未填写退回原因。")
        return update_job({**record, "status": "working"}, timeline_entry(action, status, "working", context.user, note))
    if action == "settle":
        if status != "submitted":
            raise HTTPException(status_code=409, detail="完工记录提交后才能结算。")
        if payload.settlementAmount is None:
            raise HTTPException(status_code=422, detail="请填写结算金额。")
        settlement = {"amount": payload.settlementAmount, "settledBy": context.user, "settledAt": utc_now(), "note": note}
        return update_job({**record, "status": "settled", "settlementAmount": payload.settlementAmount, "settlement": settlement}, timeline_entry(action, status, "settled", context.user, note or "劳务工资已核算。", settlement))
    if status != "settled":
        raise HTTPException(status_code=409, detail="结算完成后才能归档。")
    closed_at = utc_now()
    return update_job({**record, "status": "closed", "closedAt": closed_at}, timeline_entry(action, status, "closed", context.user, note or "用工任务已归档。", {"closedAt": closed_at}))
