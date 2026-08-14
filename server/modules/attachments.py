from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, Field

from .admin_roles import require_permission
from .auth import AuthContext
from .database import (
    attachment_events_json_path,
    attachment_links_json_path,
    attachment_objects_dir,
    attachments_json_path,
    json_transaction,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
    use_postgis,
)
from .forest_blocks import datetime_to_iso, json_value, mysql_datetime, now_iso, postgis_connect


MAX_ATTACHMENT_BYTES = max(1, int(os.environ.get("SMART_BAMBOO_ATTACHMENT_MAX_BYTES", 100 * 1024 * 1024)))
SAFE_EXTENSION = re.compile(r"^\.[A-Za-z0-9]{1,12}$")

ATTACHMENT_FIELDS = (
    ("id", "id"), ("original_name", "originalName"), ("stored_name", "storedName"),
    ("object_key", "objectKey"), ("content_type", "contentType"), ("size_bytes", "sizeBytes"),
    ("sha256", "sha256"), ("category", "category"), ("description", "description"),
    ("status", "status"), ("properties", "properties"), ("version", "version"),
    ("uploaded_by", "uploadedBy"), ("created_at", "createdAt"), ("updated_at", "updatedAt"),
    ("deleted_at", "deletedAt"),
)
LINK_FIELDS = (
    ("id", "id"), ("attachment_id", "attachmentId"), ("entity_type", "entityType"),
    ("entity_id", "entityId"), ("relation_type", "relationType"),
    ("created_by", "createdBy"), ("created_at", "createdAt"), ("deleted_at", "deletedAt"),
)
EVENT_FIELDS = (
    ("id", "id"), ("attachment_id", "attachmentId"), ("action", "action"),
    ("actor", "actor"), ("detail", "detail"), ("created_at", "createdAt"),
)


class AttachmentPatch(BaseModel):
    expectedVersion: int = Field(ge=1)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    properties: dict[str, Any] | None = None
    model_config = {"extra": "forbid"}


class AttachmentLinkIn(BaseModel):
    attachmentId: str = Field(min_length=1)
    entityType: str = Field(min_length=1, max_length=80)
    entityId: str = Field(min_length=1, max_length=160)
    relationType: str = Field(default="evidence", min_length=1, max_length=64)
    model_config = {"extra": "forbid"}


def _connection():
    return mysql_connect() if use_mysql() else postgis_connect()


def _normalize(row: tuple[Any, ...], fields: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for (_, api_name), value in zip(fields, row):
        if api_name in {"properties", "detail"}:
            value = json_value(value, {})
        result[api_name] = datetime_to_iso(value)
    return result


def _records(kind: str) -> list[dict[str, Any]]:
    paths = {
        "attachment": attachments_json_path(),
        "link": attachment_links_json_path(),
        "event": attachment_events_json_path(),
    }
    tables = {"attachment": "attachments", "link": "attachment_links", "event": "attachment_events"}
    fields = {"attachment": ATTACHMENT_FIELDS, "link": LINK_FIELDS, "event": EVENT_FIELDS}
    if not (use_mysql() or use_postgis()):
        return load_json_records(paths[kind])
    columns = ", ".join(column for column, _ in fields[kind])
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {columns} FROM {tables[kind]}")
            return [_normalize(row, fields[kind]) for row in cur.fetchall()]


def _save(kind: str, record: dict[str, Any]) -> None:
    paths = {
        "attachment": attachments_json_path(),
        "link": attachment_links_json_path(),
        "event": attachment_events_json_path(),
    }
    tables = {"attachment": "attachments", "link": "attachment_links", "event": "attachment_events"}
    fields = {"attachment": ATTACHMENT_FIELDS, "link": LINK_FIELDS, "event": EVENT_FIELDS}
    if not (use_mysql() or use_postgis()):
        path = paths[kind]
        with json_transaction([path]):
            records = load_json_records(path)
            index = next((i for i, item in enumerate(records) if item.get("id") == record["id"]), None)
            if index is None:
                records.append(record)
            else:
                records[index] = record
            save_json_records(path, records)
        return
    columns = [column for column, _ in fields[kind]]
    names = [name for _, name in fields[kind]]
    values = []
    for name in names:
        value = record.get(name)
        if name in {"properties", "detail"}:
            value = json.dumps(value or {}, ensure_ascii=False)
        if use_mysql() and name in {"createdAt", "updatedAt", "deletedAt"}:
            value = mysql_datetime(value)
        values.append(value)
    updates = ", ".join(f"{column}=VALUES({column})" for column in columns[1:]) if use_mysql() else ", ".join(f"{column}=EXCLUDED.{column}" for column in columns[1:])
    conflict = "ON DUPLICATE KEY UPDATE" if use_mysql() else "ON CONFLICT (id) DO UPDATE SET"
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {tables[kind]} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) {conflict} {updates}",
                tuple(values),
            )
        conn.commit()


def _find_attachment(attachment_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
    record = next((item for item in _records("attachment") if item.get("id") == attachment_id), None)
    if not record or (record.get("deletedAt") and not include_deleted):
        raise HTTPException(status_code=404, detail="Attachment not found")
    return record


def _view(record: dict[str, Any]) -> dict[str, Any]:
    links = [item for item in _records("link") if item.get("attachmentId") == record["id"] and not item.get("deletedAt")]
    return {
        **{key: value for key, value in record.items() if key not in {"objectKey", "storedName"}},
        "links": links,
        "linkCount": len(links),
        "downloadUrl": f"/api/v2/attachments/{record['id']}/download" if not record.get("deletedAt") else None,
    }


def _event(attachment_id: str, action: str, context: AuthContext, detail: dict[str, Any] | None = None) -> None:
    _save("event", {
        "id": str(uuid.uuid4()), "attachmentId": attachment_id, "action": action,
        "actor": context.user, "detail": detail or {}, "createdAt": now_iso(),
    })


async def upload_attachment(upload: UploadFile, category: str, description: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "files.attachments.upload")
    original_name = Path(upload.filename or "attachment").name[:512]
    suffix = Path(original_name).suffix.lower()
    suffix = suffix if SAFE_EXTENSION.match(suffix) else ""
    temporary = attachment_objects_dir() / f".{uuid.uuid4().hex}.upload"
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("xb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ATTACHMENT_BYTES:
                    raise HTTPException(status_code=413, detail=f"Attachment exceeds {MAX_ATTACHMENT_BYTES} bytes")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if size == 0:
            raise HTTPException(status_code=400, detail="Attachment is empty")
        sha256 = digest.hexdigest()
        object_key = f"{sha256[:2]}/{sha256}{suffix}"
        target = attachment_objects_dir() / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            temporary.unlink()
        else:
            os.replace(temporary, target)
        timestamp = now_iso()
        record = {
            "id": str(uuid.uuid4()), "originalName": original_name,
            "storedName": target.name, "objectKey": object_key,
            "contentType": upload.content_type or "application/octet-stream", "sizeBytes": size,
            "sha256": sha256, "category": category.strip() or "document",
            "description": description.strip() or None, "status": "active", "properties": {},
            "version": 1, "uploadedBy": context.user, "createdAt": timestamp,
            "updatedAt": timestamp, "deletedAt": None,
        }
        _save("attachment", record)
        _event(record["id"], "upload", context, {"sha256": sha256, "sizeBytes": size})
        return _view(record)
    finally:
        await upload.close()
        if temporary.exists():
            temporary.unlink()


def list_attachments(*, q: str, category: str, entity_type: str, entity_id: str, include_deleted: bool, limit: int, offset: int, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "files.attachments.view")
    if include_deleted:
        require_permission(context, "files.attachments.restore")
    query = q.strip().lower()
    linked_ids = None
    if entity_type or entity_id:
        linked_ids = {
            item["attachmentId"] for item in _records("link")
            if not item.get("deletedAt")
            and (not entity_type or item.get("entityType") == entity_type)
            and (not entity_id or item.get("entityId") == entity_id)
        }
    items = []
    for record in _records("attachment"):
        if record.get("deletedAt") and not include_deleted:
            continue
        if category and record.get("category") != category:
            continue
        if linked_ids is not None and record.get("id") not in linked_ids:
            continue
        if query and query not in " ".join(str(record.get(key) or "") for key in ("originalName", "description", "sha256", "uploadedBy")).lower():
            continue
        items.append(_view(record))
    items.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return {"items": items[offset:offset + limit], "total": len(items), "limit": limit, "offset": offset}


def get_attachment(attachment_id: str, context: AuthContext, *, include_deleted: bool = False) -> dict[str, Any]:
    require_permission(context, "files.attachments.view")
    return _view(_find_attachment(attachment_id, include_deleted=include_deleted))


def patch_attachment(attachment_id: str, payload: AttachmentPatch, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "files.attachments.update")
    record = _find_attachment(attachment_id)
    if record.get("version") != payload.expectedVersion:
        raise HTTPException(status_code=409, detail="Attachment was updated by another user")
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("expectedVersion", None)
    record.update(changes)
    record.update({"version": int(record.get("version") or 1) + 1, "updatedAt": now_iso()})
    _save("attachment", record)
    _event(attachment_id, "update", context, {"fields": sorted(changes)})
    return _view(record)


def delete_attachment(attachment_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "files.attachments.delete")
    record = _find_attachment(attachment_id)
    active_links = [item for item in _records("link") if item.get("attachmentId") == attachment_id and not item.get("deletedAt")]
    if active_links:
        raise HTTPException(status_code=409, detail="Attachment is still linked to business records; unlink it before deletion")
    record.update({"status": "deleted", "deletedAt": now_iso(), "updatedAt": now_iso(), "version": int(record.get("version") or 1) + 1})
    _save("attachment", record)
    _event(attachment_id, "delete", context)
    return {"ok": True, "deleted": attachment_id, "version": record["version"]}


def restore_attachment(attachment_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "files.attachments.restore")
    record = _find_attachment(attachment_id, include_deleted=True)
    record.update({"status": "active", "deletedAt": None, "updatedAt": now_iso(), "version": int(record.get("version") or 1) + 1})
    _save("attachment", record)
    _event(attachment_id, "restore", context)
    return _view(record)


def create_attachment_link(payload: AttachmentLinkIn, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "files.attachments.link")
    _find_attachment(payload.attachmentId)
    existing = next((item for item in _records("link") if item.get("attachmentId") == payload.attachmentId and item.get("entityType") == payload.entityType and item.get("entityId") == payload.entityId and item.get("relationType") == payload.relationType), None)
    if existing and not existing.get("deletedAt"):
        return existing
    timestamp = now_iso()
    record = {**payload.model_dump(), "id": existing["id"] if existing else str(uuid.uuid4()), "createdBy": context.user, "createdAt": timestamp, "deletedAt": None}
    _save("link", record)
    _event(payload.attachmentId, "link", context, {"entityType": payload.entityType, "entityId": payload.entityId, "relationType": payload.relationType})
    return record


def delete_attachment_link(link_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "files.attachments.link")
    record = next((item for item in _records("link") if item.get("id") == link_id and not item.get("deletedAt")), None)
    if not record:
        raise HTTPException(status_code=404, detail="Attachment link not found")
    record["deletedAt"] = now_iso()
    _save("link", record)
    _event(str(record["attachmentId"]), "unlink", context, {"entityType": record["entityType"], "entityId": record["entityId"]})
    return {"ok": True, "deleted": link_id}


def linked_attachments(entity_type: str, entity_id: str, relation_type: str = "") -> list[dict[str, Any]]:
    ids = [
        item["attachmentId"]
        for item in _records("link")
        if item.get("entityType") == entity_type
        and item.get("entityId") == entity_id
        and (not relation_type or item.get("relationType") == relation_type)
        and not item.get("deletedAt")
    ]
    return [_view(record) for record in _records("attachment") if record.get("id") in ids and not record.get("deletedAt")]


def sync_attachment_links(
    entity_type: str,
    entity_id: str,
    attachment_ids: list[str],
    context: AuthContext,
    *,
    relation_type: str = "evidence",
) -> None:
    require_permission(context, "files.attachments.link")
    wanted = list(dict.fromkeys(attachment_ids))
    for attachment_id in wanted:
        _find_attachment(attachment_id)
    current = [item for item in _records("link") if item.get("entityType") == entity_type and item.get("entityId") == entity_id and item.get("relationType") == relation_type and not item.get("deletedAt")]
    for link in current:
        if link["attachmentId"] not in wanted:
            delete_attachment_link(str(link["id"]), context)
    existing_ids = {item["attachmentId"] for item in current}
    for attachment_id in wanted:
        if attachment_id not in existing_ids:
            create_attachment_link(AttachmentLinkIn(attachmentId=attachment_id, entityType=entity_type, entityId=entity_id, relationType=relation_type), context)


def attachment_file(attachment_id: str, context: AuthContext) -> tuple[Path, dict[str, Any]]:
    require_permission(context, "files.attachments.view")
    record = _find_attachment(attachment_id)
    root = attachment_objects_dir().resolve()
    path = (root / str(record["objectKey"])).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment content not found")
    return path, record


def attachment_events(attachment_id: str, context: AuthContext) -> dict[str, Any]:
    require_permission(context, "files.attachments.view")
    _find_attachment(attachment_id, include_deleted=True)
    items = [item for item in _records("event") if item.get("attachmentId") == attachment_id]
    items.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return {"items": items, "total": len(items)}


def export_attachments_csv(context: AuthContext) -> bytes:
    require_permission(context, "files.attachments.export")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["附件ID", "文件名", "分类", "类型", "字节数", "SHA-256", "上传人", "上传时间", "状态", "关联数"])
    for record in sorted((_view(item) for item in _records("attachment")), key=lambda item: str(item.get("createdAt") or ""), reverse=True):
        writer.writerow([record["id"], record["originalName"], record["category"], record.get("contentType") or "", record["sizeBytes"], record["sha256"], record.get("uploadedBy") or "", record["createdAt"], record["status"], record["linkCount"]])
    return output.getvalue().encode("utf-8-sig")
