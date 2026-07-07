from __future__ import annotations

import csv
import io
import json
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from .auth import request_context, require_write_access
from .forest_blocks import (
    load_all_blocks,
    normalize_block,
    require_target_area_allowed,
    save_blocks,
)


router = APIRouter(prefix="/api", tags=["forest-imports"])

IMPORT_REPORTS: dict[str, dict[str, Any]] = {}

FIELD_ALIASES: dict[str, list[str]] = {
    "blockCode": ["blockCode", "林班编号", "小班编号", "编号", "block_code"],
    "name": ["name", "林班名称", "小班名称", "名称"],
    "countyCode": ["countyCode", "区县编码"],
    "countyName": ["countyName", "区县", "县", "行政区"],
    "townCode": ["townCode", "乡镇编码"],
    "townName": ["townName", "乡镇", "镇"],
    "villageCode": ["villageCode", "村编码"],
    "villageName": ["villageName", "村", "行政村"],
    "areaMu": ["areaMu", "面积", "亩", "面积亩"],
    "qualityGrade": ["qualityGrade", "质量等级"],
    "healthStatus": ["healthStatus", "健康状态"],
    "riskLevel": ["riskLevel", "风险等级"],
    "baseType": ["baseType"],
    "operationType": ["operationType"],
    "forestType": ["forestType"],
}


def pick_field(values: dict[str, Any], field_name: str) -> Any:
    for alias in FIELD_ALIASES.get(field_name, []):
        if alias not in values:
            continue
        value = values[alias]
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        if value == "":
            continue
        return value
    return None


def normalize_geometry(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not geometry:
        return None
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        return {"type": "MultiPolygon", "coordinates": [coordinates]}
    if geometry_type == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": coordinates}
    return None


def normalize_import_record(
    properties: dict[str, Any],
    geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        field_name: pick_field(properties, field_name) for field_name in FIELD_ALIASES
    }
    area_mu = record.get("areaMu")
    if area_mu is not None:
        record["areaMu"] = float(area_mu)
    record["geometry"] = normalize_geometry(geometry)
    record["properties"] = dict(properties)
    return record


def parse_geojson(content: bytes) -> list[dict[str, Any]]:
    payload = json.loads(content.decode("utf-8-sig"))
    if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
        features = payload.get("features") or []
    elif isinstance(payload, dict) and payload.get("type") == "Feature":
        features = [payload]
    elif isinstance(payload, list):
        features = payload
    else:
        raise HTTPException(status_code=400, detail="GeoJSON import must be a FeatureCollection, Feature, or JSON list")

    return [
        normalize_import_record(feature.get("properties") or {}, feature.get("geometry"))
        for feature in features
    ]


def parse_csv_file(content: bytes) -> list[dict[str, Any]]:
    rows = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    return [normalize_import_record(dict(row)) for row in rows]


def parse_xlsx_file(content: bytes) -> list[dict[str, Any]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="XLSX import requires openpyxl") from exc

    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    try:
        headers = next(rows)
    except StopIteration:
        return []
    normalized_headers = [str(value).strip() if value is not None else "" for value in headers]
    records: list[dict[str, Any]] = []
    for row in rows:
        values = {
            normalized_headers[index]: row[index]
            for index in range(min(len(normalized_headers), len(row)))
            if normalized_headers[index]
        }
        records.append(normalize_import_record(values))
    return records


def parse_shapefile_zip(content: bytes) -> list[dict[str, Any]]:
    try:
        import pyogrio
        from shapely.geometry import mapping
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Shapefile import requires pyogrio and shapely") from exc

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            archive.extractall(root)
        shapefiles = list(root.rglob("*.shp"))
        if not shapefiles:
            raise HTTPException(status_code=400, detail="Shapefile ZIP must include a .shp file")
        frame = pyogrio.read_dataframe(shapefiles[0])
        if getattr(frame, "crs", None):
            frame = frame.to_crs("EPSG:4326")

        records: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            values = row.to_dict()
            geometry = values.pop("geometry", None)
            records.append(
                normalize_import_record(
                    values,
                    mapping(geometry) if geometry is not None else None,
                )
            )
        return records


def parse_import_file(file_name: str, content: bytes) -> list[dict[str, Any]]:
    lower_name = file_name.lower()
    if lower_name.endswith(".geojson") or lower_name.endswith(".json"):
        return parse_geojson(content)
    if lower_name.endswith(".csv"):
        return parse_csv_file(content)
    if lower_name.endswith(".xlsx"):
        return parse_xlsx_file(content)
    if lower_name.endswith(".zip"):
        return parse_shapefile_zip(content)
    raise HTTPException(status_code=400, detail="Supported formats: CSV, XLSX, GeoJSON, JSON, Shapefile ZIP")


def validate_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not record.get("blockCode"):
        errors.append("blockCode is required")
    if not record.get("name"):
        errors.append("name is required")
    return errors


def build_report(
    *,
    batch_id: str,
    file_name: str,
    total_rows: int,
    valid_rows: int,
    invalid_rows: int,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    suffix = Path(file_name).suffix.lower().lstrip(".")
    return {
        "id": batch_id,
        "fileName": file_name,
        "fileType": suffix,
        "status": "completed",
        "totalRows": total_rows,
        "validRows": valid_rows,
        "invalidRows": invalid_rows,
        "errors": errors,
    }


@router.post("/imports/forest-blocks")
async def import_forest_blocks(
    request: Request,
    file: UploadFile = File(...),
    strategy: str = Form(default="upsert"),
) -> dict[str, Any]:
    context = request_context(request)
    require_write_access(context)
    if strategy not in {"upsert", "skip"}:
        raise HTTPException(status_code=400, detail="strategy must be 'upsert' or 'skip'")

    content = await file.read()
    records = parse_import_file(file.filename or "upload", content)
    blocks = load_all_blocks()
    active_indexes = {
        block["blockCode"]: index
        for index, block in enumerate(blocks)
        if block.get("blockCode") and not block.get("deletedAt")
    }

    valid_rows = 0
    errors: list[dict[str, Any]] = []
    for row_number, record in enumerate(records, start=1):
        row_errors = validate_record(record)
        try:
            require_target_area_allowed(context, record.get("countyCode"))
        except HTTPException as exc:
            row_errors.append(str(exc.detail))
        if row_errors:
            errors.extend({"row": row_number, "message": message} for message in row_errors)
            continue

        valid_rows += 1
        existing_index = active_indexes.get(record["blockCode"])
        if existing_index is not None and strategy == "skip":
            continue

        normalized = normalize_block(record)
        if existing_index is not None:
            existing = blocks[existing_index]
            normalized["id"] = existing["id"]
            normalized["createdAt"] = existing.get("createdAt", normalized["createdAt"])
            normalized["deletedAt"] = existing.get("deletedAt")
            blocks[existing_index] = normalized
            continue

        blocks.append(normalized)
        active_indexes[record["blockCode"]] = len(blocks) - 1

    save_blocks(blocks)

    batch_id = str(uuid.uuid4())
    report = build_report(
        batch_id=batch_id,
        file_name=file.filename or "upload",
        total_rows=len(records),
        valid_rows=valid_rows,
        invalid_rows=len(records) - valid_rows,
        errors=errors,
    )
    IMPORT_REPORTS[batch_id] = report
    return {**report, "report": report}


def get_report_or_404(batch_id: str) -> dict[str, Any]:
    report = IMPORT_REPORTS.get(batch_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Import batch not found")
    return report


@router.get("/imports/{batch_id}")
def get_import_batch(batch_id: str) -> dict[str, Any]:
    return get_report_or_404(batch_id)


@router.get("/imports/{batch_id}/report")
def get_import_report(batch_id: str) -> dict[str, Any]:
    return get_report_or_404(batch_id)
