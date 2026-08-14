from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from .database import (
    JSON_STORE_LOCK,
    ai_model_assets_json_path,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mysql_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def iso_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def json_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


ASSET_SELECT = """
    SELECT id,asset_no,asset_type,name,code,version,status,parent_id,framework,
           runtime_target,description,metrics_json,metadata_json,created_by,
           created_at,updated_at,deleted_at
    FROM ai_model_assets
"""


def asset_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "assetNo": str(row[1]), "assetType": str(row[2]),
        "name": str(row[3]), "code": str(row[4]), "version": str(row[5] or ""),
        "status": str(row[6]), "parentId": str(row[7] or ""),
        "framework": str(row[8] or ""), "runtimeTarget": str(row[9] or ""),
        "description": str(row[10] or ""), "metrics": json_value(row[11]),
        "metadata": json_value(row[12]), "createdBy": str(row[13] or ""),
        "createdAt": iso_value(row[14]), "updatedAt": iso_value(row[15]),
        "deletedAt": iso_value(row[16]),
    }


def list_assets(query: str = "", asset_type: str = "", status: str = "", *, include_deleted: bool = False) -> list[dict[str, Any]]:
    if use_mysql():
        clauses = [] if include_deleted else ["deleted_at IS NULL"]
        params: list[Any] = []
        if query:
            clauses.append("(asset_no LIKE %s OR name LIKE %s OR code LIKE %s OR version LIKE %s)")
            params.extend([f"%{query}%"] * 4)
        if asset_type:
            clauses.append("asset_type=%s")
            params.append(asset_type)
        if status:
            clauses.append("status=%s")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ASSET_SELECT + where + " ORDER BY updated_at DESC,asset_no", tuple(params))
                return [asset_from_row(row) for row in cur.fetchall()]
    records = load_json_records(ai_model_assets_json_path())
    if not include_deleted:
        records = [item for item in records if not item.get("deletedAt")]
    if asset_type:
        records = [item for item in records if item.get("assetType") == asset_type]
    if status:
        records = [item for item in records if item.get("status") == status]
    needle = query.strip().lower()
    if needle:
        records = [item for item in records if needle in f"{item.get('assetNo')} {item.get('name')} {item.get('code')} {item.get('version')}".lower()]
    return sorted(records, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)


def asset_by_id(asset_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        deleted = "" if include_deleted else " AND deleted_at IS NULL"
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ASSET_SELECT + " WHERE id=%s" + deleted, (asset_id,))
                row = cur.fetchone()
                return asset_from_row(row) if row else None
    return next((item for item in load_json_records(ai_model_assets_json_path()) if item.get("id") == asset_id and (include_deleted or not item.get("deletedAt"))), None)


def create_asset(record: dict[str, Any]) -> dict[str, Any]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO ai_model_assets (
                        id,asset_no,asset_type,name,code,version,status,parent_id,framework,
                        runtime_target,description,metrics_json,metadata_json,created_by,
                        created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["id"], record["assetNo"], record["assetType"], record["name"], record["code"],
                     record.get("version") or None, record["status"], record.get("parentId") or None,
                     record.get("framework") or None, record.get("runtimeTarget") or None,
                     record.get("description") or None, json.dumps(record.get("metrics") or {}, ensure_ascii=False),
                     json.dumps(record.get("metadata") or {}, ensure_ascii=False), record.get("createdBy") or None,
                     mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"])),
                )
            conn.commit()
        return asset_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(ai_model_assets_json_path())
        records.append(record)
        save_json_records(ai_model_assets_json_path(), records)
    return record


def update_asset(record: dict[str, Any]) -> dict[str, Any]:
    updated = {**record, "updatedAt": utc_now()}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE ai_model_assets SET asset_type=%s,name=%s,code=%s,version=%s,
                       status=%s,parent_id=%s,framework=%s,runtime_target=%s,description=%s,
                       metrics_json=%s,metadata_json=%s,updated_at=%s
                       WHERE id=%s AND deleted_at IS NULL""",
                    (updated["assetType"], updated["name"], updated["code"], updated.get("version") or None,
                     updated["status"], updated.get("parentId") or None, updated.get("framework") or None,
                     updated.get("runtimeTarget") or None, updated.get("description") or None,
                     json.dumps(updated.get("metrics") or {}, ensure_ascii=False),
                     json.dumps(updated.get("metadata") or {}, ensure_ascii=False), mysql_datetime(updated["updatedAt"]),
                     updated["id"]),
                )
            conn.commit()
        return asset_by_id(updated["id"]) or updated
    with JSON_STORE_LOCK:
        records = load_json_records(ai_model_assets_json_path())
        records = [updated if item.get("id") == updated["id"] else item for item in records]
        save_json_records(ai_model_assets_json_path(), records)
    return updated


def set_asset_deleted(asset_id: str, *, deleted: bool) -> bool:
    now = utc_now()
    if use_mysql():
        current = "IS NULL" if deleted else "IS NOT NULL"
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE ai_model_assets SET deleted_at=%s,updated_at=%s WHERE id=%s AND deleted_at {current}",
                    (mysql_datetime(now) if deleted else None, mysql_datetime(now), asset_id),
                )
                changed = cur.rowcount > 0
            conn.commit()
        return changed
    with JSON_STORE_LOCK:
        records = load_json_records(ai_model_assets_json_path())
        changed = False
        for item in records:
            if item.get("id") == asset_id and bool(item.get("deletedAt")) != deleted:
                item["deletedAt"] = now if deleted else None
                item["updatedAt"] = now
                changed = True
        save_json_records(ai_model_assets_json_path(), records)
    return changed
