from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from .database import (
    JSON_STORE_LOCK,
    ai_findings_json_path,
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


def number_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def timeline_entry(action: str, from_status: str, to_status: str, actor: str, note: str = "", data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()), "action": action, "fromStatus": from_status,
        "toStatus": to_status, "actor": actor, "note": str(note or "").strip(),
        "data": dict(data or {}), "createdAt": utc_now(),
    }


FINDING_SELECT = """
    SELECT id,finding_no,title,finding_type,status,model_code,model_version,
           confidence,source_asset_url,drone_mission_id,iot_device_id,device_code,
           location_text,longitude,latitude,result_json,review_json,safety_alert_id,
           occurred_at,created_by,created_at,updated_at,deleted_at
    FROM ai_findings
"""


def finding_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "findingNo": str(row[1]), "title": str(row[2]),
        "findingType": str(row[3]), "status": str(row[4]), "modelCode": str(row[5]),
        "modelVersion": str(row[6]), "confidence": number_value(row[7]) or 0,
        "sourceAssetUrl": str(row[8] or ""), "droneMissionId": str(row[9] or ""),
        "deviceId": str(row[10] or ""), "deviceCode": str(row[11] or ""),
        "locationText": str(row[12] or ""), "longitude": number_value(row[13]),
        "latitude": number_value(row[14]), "result": json_value(row[15], {}),
        "review": json_value(row[16], {}), "safetyAlertId": str(row[17] or ""),
        "occurredAt": iso_value(row[18]), "createdBy": str(row[19] or ""),
        "createdAt": iso_value(row[20]), "updatedAt": iso_value(row[21]),
        "deletedAt": iso_value(row[22]),
    }


def hydrate_finding(cur: Any, record: dict[str, Any]) -> dict[str, Any]:
    cur.execute("SELECT forest_block_id,block_code FROM ai_finding_block_links WHERE ai_finding_id=%s ORDER BY block_code", (record["id"],))
    record["blocks"] = [{"id": str(row[0]), "code": str(row[1])} for row in cur.fetchall()]
    cur.execute("SELECT id,action,from_status,to_status,actor,note,event_json,created_at FROM ai_finding_timeline WHERE ai_finding_id=%s ORDER BY created_at,id", (record["id"],))
    record["timeline"] = [{
        "id": str(row[0]), "action": str(row[1]), "fromStatus": str(row[2] or ""),
        "toStatus": str(row[3] or ""), "actor": str(row[4] or ""), "note": str(row[5] or ""),
        "data": json_value(row[6], {}), "createdAt": iso_value(row[7]),
    } for row in cur.fetchall()]
    return record


def list_findings(query: str = "", status: str = "", finding_type: str = "", block_code: str = "", *, include_deleted: bool = False) -> list[dict[str, Any]]:
    if use_mysql():
        clauses = [] if include_deleted else ["f.deleted_at IS NULL"]
        params: list[Any] = []
        if query:
            clauses.append("(f.finding_no LIKE %s OR f.title LIKE %s OR f.model_code LIKE %s OR f.device_code LIKE %s)")
            params.extend([f"%{query}%"] * 4)
        if status:
            clauses.append("f.status=%s")
            params.append(status)
        if finding_type:
            clauses.append("f.finding_type=%s")
            params.append(finding_type)
        if block_code:
            clauses.append("EXISTS (SELECT 1 FROM ai_finding_block_links lb WHERE lb.ai_finding_id=f.id AND lb.block_code=%s)")
            params.append(block_code)
        sql = FINDING_SELECT.replace("FROM ai_findings", "FROM ai_findings f").replace("SELECT id,", "SELECT f.id,")
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                cur.execute(sql + where + " ORDER BY f.occurred_at DESC", tuple(params))
                return [hydrate_finding(cur, finding_from_row(row)) for row in cur.fetchall()]
    needle = query.strip().lower()
    records = load_json_records(ai_findings_json_path())
    if not include_deleted:
        records = [item for item in records if not item.get("deletedAt")]
    if status:
        records = [item for item in records if item.get("status") == status]
    if finding_type:
        records = [item for item in records if item.get("findingType") == finding_type]
    if block_code:
        records = [item for item in records if block_code in {link.get("code") for link in item.get("blocks") or []}]
    if needle:
        records = [item for item in records if needle in f"{item.get('findingNo')} {item.get('title')} {item.get('modelCode')} {item.get('deviceCode')}".lower()]
    return sorted(records, key=lambda item: str(item.get("occurredAt") or ""), reverse=True)


def finding_by_id(finding_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                deleted_clause = "" if include_deleted else " AND deleted_at IS NULL"
                cur.execute(FINDING_SELECT + " WHERE id=%s" + deleted_clause, (finding_id,))
                row = cur.fetchone()
                return hydrate_finding(cur, finding_from_row(row)) if row else None
    return next((item for item in load_json_records(ai_findings_json_path()) if item.get("id") == finding_id and (include_deleted or not item.get("deletedAt"))), None)


def insert_timeline(cur: Any, finding_id: str, timeline: dict[str, Any]) -> None:
    cur.execute(
        """INSERT INTO ai_finding_timeline (id,ai_finding_id,action,from_status,to_status,actor,note,event_json,created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (timeline["id"], finding_id, timeline["action"], timeline.get("fromStatus") or None,
         timeline.get("toStatus") or None, timeline.get("actor") or None, timeline.get("note") or None,
         json.dumps(timeline.get("data") or {}, ensure_ascii=False), mysql_datetime(timeline["createdAt"])),
    )


def create_finding(record: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    record = {**record, "timeline": [timeline]}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO ai_findings (
                        id,finding_no,title,finding_type,status,model_code,model_version,
                        confidence,source_asset_url,drone_mission_id,iot_device_id,device_code,
                        location_text,longitude,latitude,result_json,review_json,safety_alert_id,
                        occurred_at,created_by,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["id"], record["findingNo"], record["title"], record["findingType"], record["status"],
                     record["modelCode"], record["modelVersion"], record["confidence"], record.get("sourceAssetUrl") or None,
                     record.get("droneMissionId") or None, record.get("deviceId") or None, record.get("deviceCode") or None,
                     record.get("locationText") or None, record.get("longitude"), record.get("latitude"),
                     json.dumps(record.get("result") or {}, ensure_ascii=False), json.dumps(record.get("review") or {}, ensure_ascii=False),
                     record.get("safetyAlertId") or None, mysql_datetime(record["occurredAt"]), record.get("createdBy") or None,
                     mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"])),
                )
                links = record.get("blocks") or []
                if links:
                    cur.executemany("INSERT INTO ai_finding_block_links (ai_finding_id,forest_block_id,block_code) VALUES (%s,%s,%s)", [(record["id"], item["id"], item["code"]) for item in links])
                insert_timeline(cur, record["id"], timeline)
            conn.commit()
        return finding_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(ai_findings_json_path())
        records.append(record)
        save_json_records(ai_findings_json_path(), records)
    return record


def update_finding(record: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    updated = {**record, "updatedAt": utc_now()}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE ai_findings SET title=%s,finding_type=%s,status=%s,model_code=%s,
                        model_version=%s,confidence=%s,source_asset_url=%s,drone_mission_id=%s,
                        iot_device_id=%s,device_code=%s,location_text=%s,longitude=%s,latitude=%s,
                        result_json=%s,review_json=%s,safety_alert_id=%s,occurred_at=%s,
                        updated_at=%s WHERE id=%s AND deleted_at IS NULL""",
                    (updated["title"], updated["findingType"], updated["status"], updated["modelCode"],
                     updated["modelVersion"], updated["confidence"], updated.get("sourceAssetUrl") or None,
                     updated.get("droneMissionId") or None, updated.get("deviceId") or None,
                     updated.get("deviceCode") or None, updated.get("locationText") or None,
                     updated.get("longitude"), updated.get("latitude"),
                     json.dumps(updated.get("result") or {}, ensure_ascii=False),
                     json.dumps(updated.get("review") or {}, ensure_ascii=False), updated.get("safetyAlertId") or None,
                     mysql_datetime(updated["occurredAt"]), mysql_datetime(updated["updatedAt"]), updated["id"]),
                )
                cur.execute("DELETE FROM ai_finding_block_links WHERE ai_finding_id=%s", (updated["id"],))
                links = updated.get("blocks") or []
                if links:
                    cur.executemany("INSERT INTO ai_finding_block_links (ai_finding_id,forest_block_id,block_code) VALUES (%s,%s,%s)", [(updated["id"], item["id"], item["code"]) for item in links])
                insert_timeline(cur, updated["id"], timeline)
            conn.commit()
        return finding_by_id(updated["id"]) or updated
    with JSON_STORE_LOCK:
        records = load_json_records(ai_findings_json_path())
        updated["timeline"] = [*(record.get("timeline") or []), timeline]
        records = [updated if item.get("id") == updated["id"] else item for item in records]
        save_json_records(ai_findings_json_path(), records)
    return updated


def soft_delete_finding(finding_id: str) -> bool:
    return set_finding_deleted(finding_id, deleted=True)


def restore_finding(finding_id: str) -> bool:
    return set_finding_deleted(finding_id, deleted=False)


def set_finding_deleted(finding_id: str, *, deleted: bool) -> bool:
    now = utc_now()
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                current = "IS NULL" if deleted else "IS NOT NULL"
                cur.execute(
                    f"UPDATE ai_findings SET deleted_at=%s,updated_at=%s WHERE id=%s AND deleted_at {current}",
                    (mysql_datetime(now) if deleted else None, mysql_datetime(now), finding_id),
                )
                changed = cur.rowcount > 0
            conn.commit()
        return changed
    with JSON_STORE_LOCK:
        records = load_json_records(ai_findings_json_path())
        changed = False
        for item in records:
            if item.get("id") == finding_id and bool(item.get("deletedAt")) != deleted:
                item["deletedAt"] = now if deleted else None
                item["updatedAt"] = now
                changed = True
        save_json_records(ai_findings_json_path(), records)
    return changed
