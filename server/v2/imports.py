from __future__ import annotations

import hashlib
import csv
import io
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context
from server.modules.database import get_data_dir
from server.modules.forest_blocks import block_identities_by_codes, require_target_area_allowed
from server.modules.imports import (
    IMPORT_ERROR_FIELD,
    IMPORT_FOREST_BLOCKS_CREATE_PERMISSION,
    IMPORT_FOREST_BLOCKS_VIEW_PERMISSION,
    clean_import_record,
    execute_forest_block_import,
    parse_import_file,
    validate_record,
)


router = APIRouter(prefix="/imports", tags=["v2-imports"])
MAX_UPLOAD_BYTES = 250 * 1024 * 1024


class ImportJobConfirmation(BaseModel):
    skipInvalidRows: bool = True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def jobs_dir() -> Path:
    root = get_data_dir() / "imports" / "v2-jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def normalized_job_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Import job not found") from exc


def job_dir(job_id: str) -> Path:
    return jobs_dir() / normalized_job_id(job_id)


def manifest_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"


def save_job(job: dict[str, Any]) -> dict[str, Any]:
    target_dir = job_dir(str(job["id"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "job.json"
    temporary = target.with_suffix(".json.tmp")
    job["updatedAt"] = now_iso()
    temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return job


def load_job(job_id: str) -> dict[str, Any]:
    target = manifest_path(job_id)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Import job not found")
    return json.loads(target.read_text(encoding="utf-8"))


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"rawFile", "acceptedRows"}}


def import_issue(
    *,
    row: int,
    code: str,
    severity: str,
    message: str,
    suggestion: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": f"row-{row}-{code.replace('.', '-')}",
        "row": row,
        "code": code,
        "severity": severity,
        "message": message,
        "suggestion": suggestion,
        "blockCode": str(record.get("blockCode") or ""),
        "name": str(record.get("name") or ""),
    }


def geometry_issues(record: dict[str, Any], row_number: int) -> list[dict[str, Any]]:
    geometry = record.get("geometry")
    if not geometry:
        return [
            import_issue(
                row=row_number,
                code="geometry.missing",
                severity="warning",
                message="缺少空间边界",
                suggestion="可先入库属性台账，随后在林班台账中补绘或导入 GIS 边界。",
                record=record,
            )
        ]
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        return [
            import_issue(
                row=row_number,
                code="geometry.unsupported_type",
                severity="blocking",
                message="林班边界必须是 Polygon 或 MultiPolygon",
                suggestion="在 GIS 软件中转为面要素后重新导出。",
                record=record,
            )
        ]
    try:
        from shapely.geometry import shape

        parsed = shape(geometry)
        if parsed.is_empty:
            raise ValueError("empty geometry")
        if not parsed.is_valid:
            return [
                import_issue(
                    row=row_number,
                    code="geometry.invalid",
                    severity="blocking",
                    message="边界存在自相交、环未闭合或其他拓扑错误",
                    suggestion="执行 GIS 的修复几何/检查几何工具后重新导出。",
                    record=record,
                )
            ]
        west, south, east, north = parsed.bounds
        if west < -180 or east > 180 or south < -90 or north > 90:
            return [
                import_issue(
                    row=row_number,
                    code="geometry.coordinate_range",
                    severity="blocking",
                    message="坐标超出 WGS84 经纬度范围",
                    suggestion="将成果坐标系转换为 EPSG:4326 后重新导出。",
                    record=record,
                )
            ]
    except (TypeError, ValueError, KeyError):
        return [
            import_issue(
                row=row_number,
                code="geometry.unreadable",
                severity="blocking",
                message="空间边界无法解析",
                suggestion="检查坐标数组、闭合环和文件编码后重新导出。",
                record=record,
            )
        ]
    return []


def analyze_records(records: list[dict[str, Any]], context: AuthContext) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    preview: list[dict[str, Any]] = []
    accepted_rows: list[int] = []
    codes = [str(record.get("blockCode") or "").strip() for record in records]
    code_counts = Counter(code for code in codes if code)
    existing = block_identities_by_codes([code for code in codes if code])

    for row_number, record in enumerate(records, start=1):
        row_issues: list[dict[str, Any]] = []
        for index, message in enumerate(validate_record(record), start=1):
            if "blockCode is required" in message:
                code, suggestion = "required.block_code", "补充唯一林班编号。"
            elif "name is required" in message:
                code, suggestion = "required.name", "补充林班名称。"
            else:
                code, suggestion = f"parser.error_{index}", "根据提示修正源文件对应记录。"
            row_issues.append(
                import_issue(
                    row=row_number,
                    code=code,
                    severity="blocking",
                    message=message,
                    suggestion=suggestion,
                    record=record,
                )
            )
        try:
            require_target_area_allowed(context, record.get("countyCode"))
        except HTTPException as exc:
            row_issues.append(
                import_issue(
                    row=row_number,
                    code="scope.outside_authorized_area",
                    severity="blocking",
                    message=str(exc.detail),
                    suggestion="改为当前账号有权限的区县，或由管理员调整数据范围。",
                    record=record,
                )
            )

        block_code = str(record.get("blockCode") or "").strip()
        if block_code and code_counts[block_code] > 1:
            row_issues.append(
                import_issue(
                    row=row_number,
                    code="identity.duplicate_in_file",
                    severity="blocking",
                    message=f"文件内林班编号重复，共出现 {code_counts[block_code]} 次",
                    suggestion="合并重复记录或为不同地块设置不同林班编号。",
                    record=record,
                )
            )
        if block_code and block_code in existing:
            row_issues.append(
                import_issue(
                    row=row_number,
                    code="identity.exists",
                    severity="warning",
                    message="林班编号已存在，将按所选重复策略处理",
                    suggestion="确认选择“更新现有”或“仅新增”是否符合本次接入目的。",
                    record=record,
                )
            )

        area_mu = record.get("areaMu")
        if area_mu is None:
            row_issues.append(
                import_issue(
                    row=row_number,
                    code="attribute.area_missing",
                    severity="warning",
                    message="缺少面积",
                    suggestion="可从 GIS 几何计算面积，或在林班台账中补录。",
                    record=record,
                )
            )
        else:
            try:
                if float(area_mu) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                row_issues.append(
                    import_issue(
                        row=row_number,
                        code="attribute.area_invalid",
                        severity="blocking",
                        message="面积必须大于 0",
                        suggestion="修正面积字段的单位和数值。",
                        record=record,
                    )
                )
        for name_field, code_field, label in (
            ("townName", "townCode", "乡镇"),
            ("villageName", "villageCode", "村"),
        ):
            if record.get(name_field) and not record.get(code_field):
                row_issues.append(
                    import_issue(
                        row=row_number,
                        code=f"administrative.{code_field}_missing",
                        severity="warning",
                        message=f"已填写{label}名称但缺少行政区划代码",
                        suggestion=f"从系统行政区划字典选择{label}并补齐代码。",
                        record=record,
                    )
                )
        row_issues.extend(geometry_issues(record, row_number))
        issues.extend(row_issues)
        blocked = any(issue["severity"] == "blocking" for issue in row_issues)
        if not blocked:
            accepted_rows.append(row_number)

        if len(preview) < 12:
            clean = clean_import_record(record)
            preview.append(
                {
                    "row": row_number,
                    "blockCode": clean.get("blockCode") or "",
                    "name": clean.get("name") or "",
                    "villageName": clean.get("villageName") or "",
                    "areaMu": clean.get("areaMu"),
                    "hasGeometry": bool(clean.get("geometry")),
                    "valid": not blocked,
                    "warnings": sum(1 for issue in row_issues if issue["severity"] == "warning"),
                }
            )

    blocking_issues = sum(1 for issue in issues if issue["severity"] == "blocking")
    warning_issues = sum(1 for issue in issues if issue["severity"] == "warning")
    invalid_rows = len(records) - len(accepted_rows)
    duplicate_count = sum(1 for code in codes if code and code in existing)
    return {
        "totalRows": len(records),
        "validRows": len(accepted_rows),
        "invalidRows": invalid_rows,
        "existingRows": duplicate_count,
        "newRows": max(len(accepted_rows) - duplicate_count, 0),
        "blockingIssues": blocking_issues,
        "warningIssues": warning_issues,
        "qualityStatus": "blocked" if invalid_rows else ("warning" if warning_issues else "passed"),
        "acceptedRows": accepted_rows,
        "issues": issues,
        "preview": preview,
    }


@router.get("/jobs")
def list_import_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, IMPORT_FOREST_BLOCKS_VIEW_PERMISSION)
    items: list[dict[str, Any]] = []
    for target in jobs_dir().glob("*/job.json"):
        try:
            items.append(public_job(json.loads(target.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    items.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return {"items": items[:limit], "total": len(items), "limit": limit, "offset": 0}


@router.post("/jobs")
async def create_import_job(
    file: UploadFile = File(...),
    strategy: str = Form(default="upsert"),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, IMPORT_FOREST_BLOCKS_CREATE_PERMISSION)
    if strategy not in {"upsert", "skip"}:
        raise HTTPException(status_code=400, detail="strategy must be 'upsert' or 'skip'")

    file_name = Path(file.filename or "upload").name
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空，请重新选择成果文件。")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="单个文件暂不能超过 250 MB。")

    records = parse_import_file(file_name, content)
    analysis = analyze_records(records, context)
    job_id = str(uuid.uuid4())
    target_dir = job_dir(job_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file_name).suffix.lower() or ".bin"
    raw_file = target_dir / f"source{suffix}"
    raw_file.write_bytes(content)
    job = {
        "id": job_id,
        "fileName": file_name,
        "fileType": suffix.lstrip("."),
        "sizeBytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "strategy": strategy,
        "status": "needs_confirmation" if analysis["invalidRows"] else "ready_to_commit",
        "phase": "checked",
        "createdBy": context.user,
        "createdAt": now_iso(),
        "confirmedAt": None,
        "committedAt": None,
        "batchId": None,
        "rawFile": raw_file.name,
        **analysis,
    }
    return public_job(save_job(job))


@router.get("/jobs/{job_id}")
def get_import_job(
    job_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, IMPORT_FOREST_BLOCKS_VIEW_PERMISSION)
    return public_job(load_job(job_id))


@router.get("/jobs/{job_id}/issues.csv")
def export_import_job_issues(
    job_id: str,
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, IMPORT_FOREST_BLOCKS_VIEW_PERMISSION)
    job = load_job(job_id)
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["行号", "严重级别", "规则编号", "林班编号", "林班名称", "问题", "修复建议"])
    for issue in job.get("issues") or []:
        writer.writerow(
            [
                issue.get("row"),
                issue.get("severity"),
                issue.get("code"),
                issue.get("blockCode"),
                issue.get("name"),
                issue.get("message"),
                issue.get("suggestion"),
            ]
        )
    filename = f"import-quality-{normalized_job_id(job_id)}.csv"
    return Response(
        content="\ufeff" + stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/jobs/{job_id}/confirm")
def confirm_import_job(
    job_id: str,
    payload: ImportJobConfirmation,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, IMPORT_FOREST_BLOCKS_CREATE_PERMISSION)
    job = load_job(job_id)
    if job.get("status") == "completed":
        return public_job(job)
    if not payload.skipInvalidRows:
        raise HTTPException(status_code=400, detail="当前仅支持跳过阻断记录后导入有效数据。")
    job["status"] = "ready_to_commit"
    job["phase"] = "confirmed"
    job["confirmedAt"] = now_iso()
    job["confirmedBy"] = context.user
    return public_job(save_job(job))


@router.post("/jobs/{job_id}/commit")
def commit_import_job(
    job_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, IMPORT_FOREST_BLOCKS_CREATE_PERMISSION)
    job = load_job(job_id)
    if job.get("status") == "completed":
        return public_job(job)
    if job.get("invalidRows") and job.get("status") != "ready_to_commit":
        raise HTTPException(status_code=409, detail="请先确认阻断记录的处理方式。")

    source = job_dir(job_id) / str(job.get("rawFile") or "")
    if not source.is_file():
        raise HTTPException(status_code=409, detail="原始成果文件缺失，无法继续入库。")
    content = source.read_bytes()
    if hashlib.sha256(content).hexdigest() != job.get("sha256"):
        raise HTTPException(status_code=409, detail="原始成果文件校验失败，请重新上传。")

    try:
        records = parse_import_file(str(job.get("fileName") or source.name), content)
        accepted_values = job.get("acceptedRows")
        if accepted_values is not None:
            accepted_rows = {int(value) for value in accepted_values}
            records = [record for row, record in enumerate(records, start=1) if row in accepted_rows]
        result = execute_forest_block_import(
            records=records,
            file_name=str(job.get("fileName") or source.name),
            strategy=str(job.get("strategy") or "upsert"),
            context=context,
        )
    except Exception as exc:
        job["status"] = "failed"
        job["phase"] = "commit_failed"
        job["error"] = str(getattr(exc, "detail", exc))
        save_job(job)
        raise

    job["status"] = "completed"
    job["phase"] = "committed"
    job["batchId"] = result.get("id")
    job["committedAt"] = now_iso()
    job["committedBy"] = context.user
    job["commitSummary"] = {
        "totalRows": result.get("totalRows", 0),
        "validRows": result.get("validRows", 0),
        "invalidRows": result.get("invalidRows", 0),
        "importedBlocks": len(result.get("importedBlocks") or []),
        "importedRightsArchives": len(result.get("importedRightsArchives") or []),
    }
    return public_job(save_job(job))
