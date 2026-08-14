from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from server.modules.database import JSON_STORE_LOCK, ai_inference_runs_json_path, load_json_records, mysql_connect, save_json_records, use_mysql


RUN_SELECT = """SELECT id,run_no,title,status,model_asset_id,deployment_asset_id,finding_id,
parameters_json,output_json,error_message,requested_at,started_at,completed_at,duration_ms,
created_by,created_at,updated_at,deleted_at FROM ai_inference_runs"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mysql_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _from_row(row: Any) -> dict[str, Any]:
    values = list(row)
    return {
        "id": str(values[0]), "runNo": values[1], "title": values[2], "status": values[3],
        "modelAssetId": str(values[4]), "deploymentAssetId": str(values[5] or ""), "findingId": str(values[6] or ""),
        "parameters": _json(values[7]), "output": _json(values[8]), "errorMessage": values[9] or "",
        "requestedAt": _iso(values[10]), "startedAt": _iso(values[11]), "completedAt": _iso(values[12]),
        "durationMs": int(values[13]) if values[13] is not None else None, "createdBy": values[14] or "",
        "createdAt": _iso(values[15]), "updatedAt": _iso(values[16]), "deletedAt": _iso(values[17]),
    }


def _hydrate(cur: Any, record: dict[str, Any]) -> dict[str, Any]:
    cur.execute("SELECT forest_block_id,block_code FROM ai_inference_run_block_links WHERE ai_inference_run_id=%s ORDER BY block_code", (record["id"],))
    record["blocks"] = [{"id": str(row[0]), "code": row[1]} for row in cur.fetchall()]
    return record


def list_runs(q: str = "", status: str = "", model_asset_id: str = "", block_code: str = "", *, include_deleted: bool = False) -> list[dict[str, Any]]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(RUN_SELECT + ("" if include_deleted else " WHERE deleted_at IS NULL"))
                records = [_hydrate(cur, _from_row(row)) for row in cur.fetchall()]
    else:
        records = load_json_records(ai_inference_runs_json_path())
        if not include_deleted:
            records = [item for item in records if not item.get("deletedAt")]
    needle = q.strip().lower()
    if needle:
        records = [item for item in records if needle in f"{item.get('runNo')} {item.get('title')} {item.get('errorMessage')}".lower()]
    if status:
        records = [item for item in records if item.get("status") == status]
    if model_asset_id:
        records = [item for item in records if item.get("modelAssetId") == model_asset_id]
    if block_code:
        records = [item for item in records if block_code in {link.get("code") for link in item.get("blocks") or []}]
    return sorted(records, key=lambda item: str(item.get("requestedAt") or ""), reverse=True)


def run_by_id(run_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(RUN_SELECT + " WHERE id=%s" + ("" if include_deleted else " AND deleted_at IS NULL"), (run_id,))
                row = cur.fetchone()
                return _hydrate(cur, _from_row(row)) if row else None
    return next((item for item in load_json_records(ai_inference_runs_json_path()) if item.get("id") == run_id and (include_deleted or not item.get("deletedAt"))), None)


def _values(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record["runNo"], record["title"], record["status"], record["modelAssetId"], record.get("deploymentAssetId") or None,
        record.get("findingId") or None, json.dumps(record.get("parameters") or {}, ensure_ascii=False),
        json.dumps(record.get("output") or {}, ensure_ascii=False), record.get("errorMessage") or None,
        mysql_datetime(record["requestedAt"]), mysql_datetime(record.get("startedAt")), mysql_datetime(record.get("completedAt")),
        record.get("durationMs"), record.get("createdBy") or None, mysql_datetime(record["createdAt"]),
        mysql_datetime(record["updatedAt"]), mysql_datetime(record.get("deletedAt")),
    )


def create_run(record: dict[str, Any]) -> dict[str, Any]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO ai_inference_runs (run_no,title,status,model_asset_id,deployment_asset_id,finding_id,parameters_json,output_json,error_message,requested_at,started_at,completed_at,duration_ms,created_by,created_at,updated_at,deleted_at,id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (*_values(record), record["id"]))
                links = record.get("blocks") or []
                if links:
                    cur.executemany("INSERT INTO ai_inference_run_block_links (ai_inference_run_id,forest_block_id,block_code) VALUES (%s,%s,%s)", [(record["id"], item["id"], item["code"]) for item in links])
            conn.commit()
        return run_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(ai_inference_runs_json_path())
        records.append(record)
        save_json_records(ai_inference_runs_json_path(), records)
    return record


def update_run(record: dict[str, Any]) -> dict[str, Any]:
    updated = {**record, "updatedAt": utc_now()}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE ai_inference_runs SET run_no=%s,title=%s,status=%s,model_asset_id=%s,deployment_asset_id=%s,finding_id=%s,parameters_json=%s,output_json=%s,error_message=%s,requested_at=%s,started_at=%s,completed_at=%s,duration_ms=%s,created_by=%s,created_at=%s,updated_at=%s,deleted_at=%s WHERE id=%s""", (*_values(updated), updated["id"]))
                cur.execute("DELETE FROM ai_inference_run_block_links WHERE ai_inference_run_id=%s", (updated["id"],))
                links = updated.get("blocks") or []
                if links:
                    cur.executemany("INSERT INTO ai_inference_run_block_links (ai_inference_run_id,forest_block_id,block_code) VALUES (%s,%s,%s)", [(updated["id"], item["id"], item["code"]) for item in links])
            conn.commit()
        return run_by_id(updated["id"], include_deleted=True) or updated
    with JSON_STORE_LOCK:
        records = load_json_records(ai_inference_runs_json_path())
        save_json_records(ai_inference_runs_json_path(), [updated if item.get("id") == updated["id"] else item for item in records])
    return updated


def set_run_deleted(run_id: str, *, deleted: bool) -> bool:
    record = run_by_id(run_id, include_deleted=True)
    if not record:
        return False
    record["deletedAt"] = utc_now() if deleted else None
    update_run(record)
    return True
