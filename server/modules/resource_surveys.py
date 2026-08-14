from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .admin_roles import require_permission
from .auth import AuthContext
from .database import (
    json_transaction,
    load_json_records,
    mysql_connect,
    resource_snapshot_versions_json_path,
    resource_snapshots_json_path,
    resource_surveys_json_path,
    save_json_records,
    use_mysql,
    use_postgis,
)
from .forest_blocks import datetime_to_iso, decimal_to_float, json_value, mysql_datetime, now_iso, postgis_connect
from .forest_subcompartments import get_forest_subcompartment


class ResourceSurveyIn(BaseModel):
    surveyNo: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    surveyType: str = Field(min_length=1, max_length=64)
    surveyDate: date
    status: Literal["draft", "in_progress", "completed", "cancelled"] = "draft"
    organization: str | None = None
    surveyor: str | None = None
    sourceType: str | None = None
    method: str | None = None
    notes: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}


class ResourceSurveyPatch(BaseModel):
    expectedVersion: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    surveyType: str | None = None
    surveyDate: date | None = None
    status: Literal["draft", "in_progress", "completed", "cancelled"] | None = None
    organization: str | None = None
    surveyor: str | None = None
    sourceType: str | None = None
    method: str | None = None
    notes: str | None = None
    properties: dict[str, Any] | None = None
    model_config = {"extra": "forbid"}


class ResourceSnapshotIn(BaseModel):
    forestSubcompartmentId: str = Field(min_length=1)
    sampledAt: str | None = None
    areaMu: float | None = Field(default=None, ge=0)
    bambooSpecies: str | None = None
    origin: str | None = None
    ageGroup: str | None = None
    bambooDensityPerMu: float | None = Field(default=None, ge=0)
    avgDbhCm: float | None = Field(default=None, ge=0)
    avgHeightM: float | None = Field(default=None, ge=0)
    standingVolumeM3: float | None = Field(default=None, ge=0)
    biomassT: float | None = Field(default=None, ge=0)
    carbonEstimateTco2e: float | None = Field(default=None, ge=0)
    qualityGrade: str | None = None
    healthStatus: str | None = None
    riskLevel: str | None = None
    samplePlotCount: int | None = Field(default=None, ge=0)
    evidenceUrls: list[str] = Field(default_factory=list)
    attachmentIds: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}


class ResourceSnapshotPatch(BaseModel):
    expectedVersion: int = Field(ge=1)
    sampledAt: str | None = None
    areaMu: float | None = Field(default=None, ge=0)
    bambooSpecies: str | None = None
    origin: str | None = None
    ageGroup: str | None = None
    bambooDensityPerMu: float | None = Field(default=None, ge=0)
    avgDbhCm: float | None = Field(default=None, ge=0)
    avgHeightM: float | None = Field(default=None, ge=0)
    standingVolumeM3: float | None = Field(default=None, ge=0)
    biomassT: float | None = Field(default=None, ge=0)
    carbonEstimateTco2e: float | None = Field(default=None, ge=0)
    qualityGrade: str | None = None
    healthStatus: str | None = None
    riskLevel: str | None = None
    samplePlotCount: int | None = Field(default=None, ge=0)
    evidenceUrls: list[str] | None = None
    attachmentIds: list[str] | None = None
    properties: dict[str, Any] | None = None
    model_config = {"extra": "forbid"}


SURVEY_FIELDS = (
    ("id", "id"), ("survey_no", "surveyNo"), ("name", "name"),
    ("survey_type", "surveyType"), ("survey_date", "surveyDate"), ("status", "status"),
    ("organization", "organization"), ("surveyor", "surveyor"), ("source_type", "sourceType"),
    ("method", "method"), ("notes", "notes"), ("properties", "properties"),
    ("version", "version"), ("created_by", "createdBy"), ("created_at", "createdAt"),
    ("updated_at", "updatedAt"), ("completed_at", "completedAt"), ("deleted_at", "deletedAt"),
)
SNAPSHOT_FIELDS = (
    ("id", "id"), ("resource_survey_id", "resourceSurveyId"),
    ("forest_subcompartment_id", "forestSubcompartmentId"),
    ("previous_snapshot_id", "previousSnapshotId"), ("sampled_at", "sampledAt"),
    ("area_mu", "areaMu"), ("bamboo_species", "bambooSpecies"), ("origin", "origin"),
    ("age_group", "ageGroup"), ("bamboo_density_per_mu", "bambooDensityPerMu"),
    ("avg_dbh_cm", "avgDbhCm"), ("avg_height_m", "avgHeightM"),
    ("standing_volume_m3", "standingVolumeM3"), ("biomass_t", "biomassT"),
    ("carbon_estimate_tco2e", "carbonEstimateTco2e"), ("quality_grade", "qualityGrade"),
    ("health_status", "healthStatus"), ("risk_level", "riskLevel"),
    ("sample_plot_count", "samplePlotCount"), ("evidence_urls", "evidenceUrls"),
    ("properties", "properties"), ("version", "version"), ("created_by", "createdBy"),
    ("created_at", "createdAt"), ("updated_at", "updatedAt"), ("deleted_at", "deletedAt"),
)


def _connection():
    return mysql_connect() if use_mysql() else postgis_connect()


def _normalize_row(row: tuple[Any, ...], fields: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for (_, api_name), value in zip(fields, row):
        if api_name in {"properties", "evidenceUrls"}:
            value = json_value(value, {} if api_name == "properties" else [])
        value = decimal_to_float(datetime_to_iso(value))
        if isinstance(value, date):
            value = value.isoformat()
        result[api_name] = value
    return result


def _sql_records(table: str, fields: tuple[tuple[str, str], ...]) -> list[dict[str, Any]]:
    columns = ", ".join(column for column, _ in fields)
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {columns} FROM {table}")
            return [_normalize_row(row, fields) for row in cur.fetchall()]


def _records(kind: str) -> list[dict[str, Any]]:
    if kind == "survey":
        return _sql_records("resource_surveys", SURVEY_FIELDS) if (use_mysql() or use_postgis()) else load_json_records(resource_surveys_json_path())
    if kind == "snapshot":
        return _sql_records("resource_snapshots", SNAPSHOT_FIELDS) if (use_mysql() or use_postgis()) else load_json_records(resource_snapshots_json_path())
    if use_mysql() or use_postgis():
        fields = (("id", "id"), ("resource_snapshot_id", "resourceSnapshotId"), ("change_type", "changeType"), ("version", "version"), ("snapshot", "snapshot"), ("created_by", "createdBy"), ("created_at", "createdAt"))
        return _sql_records("resource_snapshot_versions", fields)
    return load_json_records(resource_snapshot_versions_json_path())


def _find(records: list[dict[str, Any]], record_id: str, label: str) -> dict[str, Any]:
    record = next((item for item in records if item.get("id") == record_id), None)
    if not record:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return record


def _survey_snapshot_count(survey_id: str) -> int:
    return sum(1 for item in _records("snapshot") if item.get("resourceSurveyId") == survey_id and not item.get("deletedAt"))


def _survey_view(record: dict[str, Any]) -> dict[str, Any]:
    return {**record, "snapshotCount": _survey_snapshot_count(str(record["id"]))}


def list_resource_surveys(*, q: str, status: str, survey_type: str, include_deleted: bool, limit: int, offset: int, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.surveys.view")
    query = q.strip().lower()
    items = []
    for record in _records("survey"):
        if record.get("deletedAt") and not include_deleted:
            continue
        if status and record.get("status") != status:
            continue
        if survey_type and record.get("surveyType") != survey_type:
            continue
        if query and query not in " ".join(str(record.get(key) or "") for key in ("surveyNo", "name", "organization", "surveyor")).lower():
            continue
        items.append(_survey_view(record))
    items.sort(key=lambda item: (str(item.get("surveyDate") or ""), str(item.get("updatedAt") or "")), reverse=True)
    return {"items": items[offset:offset + limit], "total": len(items), "limit": limit, "offset": offset}


def get_resource_survey(record_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.surveys.view")
    return _survey_view(_find(_records("survey"), record_id, "Resource survey"))


def _save_json(kind: str, record: dict[str, Any]) -> None:
    path = resource_surveys_json_path() if kind == "survey" else resource_snapshots_json_path()
    with json_transaction([path]):
        records = load_json_records(path)
        index = next((i for i, item in enumerate(records) if item.get("id") == record["id"]), None)
        if index is None:
            records.append(record)
        else:
            records[index] = record
        save_json_records(path, records)


def _sql_value(api_name: str, value: Any) -> Any:
    if api_name in {"properties", "evidenceUrls", "snapshot"}:
        return json.dumps(value, ensure_ascii=False)
    if api_name in {"createdAt", "updatedAt", "completedAt", "deletedAt", "sampledAt"} and use_mysql():
        return mysql_datetime(value)
    return value


def _save_sql(table: str, fields: tuple[tuple[str, str], ...], record: dict[str, Any]) -> None:
    columns = [column for column, _ in fields]
    api_names = [api_name for _, api_name in fields]
    values = tuple(_sql_value(name, record.get(name)) for name in api_names)
    placeholders = ", ".join(["%s"] * len(columns))
    updates = ", ".join(f"{column}=VALUES({column})" for column in columns[1:]) if use_mysql() else ", ".join(f"{column}=EXCLUDED.{column}" for column in columns[1:])
    conflict = "ON DUPLICATE KEY UPDATE" if use_mysql() else "ON CONFLICT (id) DO UPDATE SET"
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) {conflict} {updates}", values)
        conn.commit()


def _save(kind: str, record: dict[str, Any]) -> None:
    if use_mysql() or use_postgis():
        _save_sql("resource_surveys" if kind == "survey" else "resource_snapshots", SURVEY_FIELDS if kind == "survey" else SNAPSHOT_FIELDS, record)
    else:
        _save_json(kind, record)


def create_resource_survey(payload: ResourceSurveyIn, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.surveys.create")
    if payload.status == "completed":
        require_permission(context, "forest.surveys.complete")
    if any(item.get("surveyNo") == payload.surveyNo for item in _records("survey")):
        raise HTTPException(status_code=409, detail="Survey number already exists")
    timestamp = now_iso()
    record = {**payload.model_dump(mode="json"), "id": str(uuid.uuid4()), "version": 1, "createdBy": context.user, "createdAt": timestamp, "updatedAt": timestamp, "completedAt": timestamp if payload.status == "completed" else None, "deletedAt": None}
    _save("survey", record)
    return _survey_view(record)


def patch_resource_survey(record_id: str, payload: ResourceSurveyPatch, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.surveys.update")
    record = _find(_records("survey"), record_id, "Resource survey")
    if record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="Deleted survey cannot be edited")
    if record.get("version") != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="Survey was updated by another user")
    if record.get("status") == "completed":
        raise HTTPException(status_code=409, detail="Completed survey is archived and cannot be edited or reopened")
    if payload.status == "completed":
        require_permission(context, "forest.surveys.complete")
    changes = payload.model_dump(exclude_unset=True, mode="json")
    changes.pop("expectedVersion", None)
    record = {**record, **changes, "version": int(record.get("version") or 1) + 1, "updatedAt": now_iso()}
    if record.get("status") == "completed" and not record.get("completedAt"):
        record["completedAt"] = now_iso()
    _save("survey", record)
    return _survey_view(record)


def delete_resource_survey(record_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.surveys.delete")
    record = _find(_records("survey"), record_id, "Resource survey")
    if _survey_snapshot_count(record_id):
        raise HTTPException(status_code=409, detail="Survey with resource records cannot be deleted")
    record.update({"deletedAt": now_iso(), "updatedAt": now_iso(), "version": int(record.get("version") or 1) + 1})
    _save("survey", record)
    return {"ok": True, "deleted": record_id, "version": record["version"]}


def _snapshot_view(record: dict[str, Any], context: AuthContext) -> dict[str, Any]:
    from .attachments import linked_attachments

    survey = _find(_records("survey"), str(record["resourceSurveyId"]), "Resource survey")
    sub = get_forest_subcompartment(str(record["forestSubcompartmentId"]), context).model_dump(mode="json")
    attachments = linked_attachments("resource_snapshot", str(record["id"]))
    return {**record, "attachments": attachments, "attachmentIds": [item["id"] for item in attachments], "surveyNo": survey["surveyNo"], "surveyName": survey["name"], "surveyDate": survey["surveyDate"], "subcompartmentCode": sub["subcompartmentCode"], "subcompartmentName": sub["name"], "forestBlockId": sub["forestBlockId"], "forestBlockCode": sub["forestBlockCode"], "forestBlockName": sub["forestBlockName"]}


def list_resource_snapshots(*, survey_id: str, subcompartment_id: str, q: str, include_deleted: bool, limit: int, offset: int, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.surveys.view")
    query = q.strip().lower()
    items = []
    for record in _records("snapshot"):
        if survey_id and record.get("resourceSurveyId") != survey_id:
            continue
        if subcompartment_id and record.get("forestSubcompartmentId") != subcompartment_id:
            continue
        if record.get("deletedAt") and not include_deleted:
            continue
        try:
            view = _snapshot_view(record, context)
        except HTTPException:
            continue
        if query and query not in " ".join(str(view.get(key) or "") for key in ("surveyNo", "surveyName", "subcompartmentCode", "subcompartmentName", "bambooSpecies")).lower():
            continue
        items.append(view)
    items.sort(key=lambda item: str(item.get("sampledAt") or item.get("createdAt") or ""), reverse=True)
    return {"items": items[offset:offset + limit], "total": len(items), "limit": limit, "offset": offset}


def get_resource_snapshot(record_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.surveys.view")
    return _snapshot_view(_find(_records("snapshot"), record_id, "Resource snapshot"), context)


def _latest_previous(subcompartment_id: str, survey_id: str) -> str | None:
    survey = _find(_records("survey"), survey_id, "Resource survey")
    candidates = []
    surveys = {item["id"]: item for item in _records("survey")}
    for item in _records("snapshot"):
        parent = surveys.get(item.get("resourceSurveyId"))
        if item.get("forestSubcompartmentId") == subcompartment_id and item.get("resourceSurveyId") != survey_id and not item.get("deletedAt") and parent and str(parent.get("surveyDate") or "") <= str(survey.get("surveyDate") or ""):
            candidates.append(item)
    candidates.sort(key=lambda item: str(surveys[item["resourceSurveyId"]].get("surveyDate") or ""), reverse=True)
    return str(candidates[0]["id"]) if candidates else None


def _version_entry(record: dict[str, Any], change_type: str, context: AuthContext) -> dict[str, Any]:
    return {"id": str(uuid.uuid4()), "resourceSnapshotId": record["id"], "changeType": change_type, "version": record["version"], "snapshot": record, "createdBy": context.user, "createdAt": now_iso()}


def _save_version(entry: dict[str, Any]) -> None:
    if use_mysql() or use_postgis():
        fields = (("id", "id"), ("resource_snapshot_id", "resourceSnapshotId"), ("change_type", "changeType"), ("version", "version"), ("snapshot", "snapshot"), ("created_by", "createdBy"), ("created_at", "createdAt"))
        _save_sql("resource_snapshot_versions", fields, entry)
    else:
        path = resource_snapshot_versions_json_path()
        with json_transaction([path]):
            records = load_json_records(path)
            records.append(entry)
            save_json_records(path, records)


def create_resource_snapshot(survey_id: str, payload: ResourceSnapshotIn, context: AuthContext) -> dict[str, Any]:
    from .attachments import sync_attachment_links

    require_permission(context, "forest.surveys.create")
    survey = _find(_records("survey"), survey_id, "Resource survey")
    if survey.get("status") == "completed" or survey.get("deletedAt"):
        raise HTTPException(status_code=409, detail="Completed or deleted survey cannot accept records")
    sub = get_forest_subcompartment(payload.forestSubcompartmentId, context)
    if any(item.get("resourceSurveyId") == survey_id and item.get("forestSubcompartmentId") == payload.forestSubcompartmentId and not item.get("deletedAt") for item in _records("snapshot")):
        raise HTTPException(status_code=409, detail="This subcompartment already has a record in the survey")
    timestamp = now_iso()
    values = payload.model_dump(mode="json")
    attachment_ids = values.pop("attachmentIds", [])
    if values.get("areaMu") is None:
        values["areaMu"] = sub.areaMu
    record = {**values, "id": str(uuid.uuid4()), "resourceSurveyId": survey_id, "previousSnapshotId": _latest_previous(payload.forestSubcompartmentId, survey_id), "sampledAt": values.get("sampledAt") or timestamp, "version": 1, "createdBy": context.user, "createdAt": timestamp, "updatedAt": timestamp, "deletedAt": None}
    _save("snapshot", record)
    if attachment_ids:
        sync_attachment_links("resource_snapshot", str(record["id"]), attachment_ids, context)
    _save_version(_version_entry(record, "create", context))
    return _snapshot_view(record, context)


def patch_resource_snapshot(record_id: str, payload: ResourceSnapshotPatch, context: AuthContext) -> dict[str, Any]:
    from .attachments import sync_attachment_links

    require_permission(context, "forest.surveys.update")
    record = _find(_records("snapshot"), record_id, "Resource snapshot")
    survey = _find(_records("survey"), str(record["resourceSurveyId"]), "Resource survey")
    if survey.get("status") == "completed" or record.get("deletedAt"):
        raise HTTPException(status_code=409, detail="Completed survey records cannot be edited")
    if record.get("version") != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="Resource record was updated by another user")
    changes = payload.model_dump(exclude_unset=True, mode="json")
    changes.pop("expectedVersion", None)
    attachment_ids = changes.pop("attachmentIds", None)
    record = {**record, **changes, "version": int(record.get("version") or 1) + 1, "updatedAt": now_iso()}
    _save("snapshot", record)
    if attachment_ids is not None:
        sync_attachment_links("resource_snapshot", record_id, attachment_ids, context)
    _save_version(_version_entry(record, "update", context))
    return _snapshot_view(record, context)


def delete_resource_snapshot(record_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.surveys.delete")
    record = _find(_records("snapshot"), record_id, "Resource snapshot")
    survey = _find(_records("survey"), str(record["resourceSurveyId"]), "Resource survey")
    if survey.get("status") == "completed":
        raise HTTPException(status_code=409, detail="Completed survey records cannot be deleted")
    record.update({"deletedAt": now_iso(), "updatedAt": now_iso(), "version": int(record.get("version") or 1) + 1})
    _save("snapshot", record)
    _save_version(_version_entry(record, "delete", context))
    return {"ok": True, "deleted": record_id, "version": record["version"]}


def resource_snapshot_versions(record_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "forest.surveys.view")
    get_resource_snapshot(record_id, context)
    items = [item for item in _records("version") if item.get("resourceSnapshotId") == record_id]
    items.sort(key=lambda item: int(item.get("version") or 0), reverse=True)
    return {"items": items, "total": len(items)}


COMPARISON_FIELDS = {
    "areaMu": "面积(亩)", "bambooSpecies": "竹种", "origin": "起源", "ageGroup": "龄组",
    "bambooDensityPerMu": "每亩密度", "avgDbhCm": "平均胸径(cm)", "avgHeightM": "平均高度(m)",
    "standingVolumeM3": "蓄积量(m3)", "biomassT": "生物量(t)",
    "carbonEstimateTco2e": "碳储量(tCO2e)", "qualityGrade": "质量等级",
    "healthStatus": "健康状态", "riskLevel": "风险等级", "samplePlotCount": "样地数",
}


def resource_snapshot_comparison(record_id: str, context: AuthContext) -> dict[str, Any]:
    current = get_resource_snapshot(record_id, context)
    previous_id = current.get("previousSnapshotId")
    previous = get_resource_snapshot(str(previous_id), context) if previous_id else None
    changes = []
    for field, label in COMPARISON_FIELDS.items():
        before = previous.get(field) if previous else None
        after = current.get(field)
        if before == after:
            continue
        delta = round(float(after) - float(before), 4) if isinstance(before, (int, float)) and isinstance(after, (int, float)) else None
        changes.append({"field": field, "label": label, "before": before, "after": after, "delta": delta})
    return {"current": current, "previous": previous, "changes": changes, "changedCount": len(changes)}
