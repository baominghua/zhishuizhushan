from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

from .database import (
    JSON_STORE_LOCK,
    drone_missions_json_path,
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


MISSION_SELECT = """
    SELECT id,mission_no,title,mission_type,status,drone_device_id,device_code,
           device_name,pilot_name,route_name,objective,planned_start_at,planned_end_at,
           actual_start_at,actual_end_at,flight_summary,result_asset_urls,version,
           created_by,created_at,updated_at,closed_at,deleted_at
    FROM drone_missions
"""


def mission_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "missionNo": str(row[1]), "title": str(row[2]),
        "missionType": str(row[3]), "status": str(row[4]), "droneDeviceId": str(row[5] or ""),
        "deviceCode": str(row[6] or ""), "deviceName": str(row[7] or ""), "pilotName": str(row[8] or ""),
        "routeName": str(row[9] or ""), "objective": str(row[10] or ""),
        "plannedStartAt": iso_value(row[11]), "plannedEndAt": iso_value(row[12]),
        "actualStartAt": iso_value(row[13]), "actualEndAt": iso_value(row[14]),
        "flightSummary": json_value(row[15], {}), "resultAssetUrls": json_value(row[16], []),
        "version": int(row[17]), "createdBy": str(row[18] or ""),
        "createdAt": iso_value(row[19]), "updatedAt": iso_value(row[20]),
        "closedAt": iso_value(row[21]), "deletedAt": iso_value(row[22]),
    }


def hydrate_mission(cur: Any, record: dict[str, Any]) -> dict[str, Any]:
    cur.execute("SELECT forest_block_id,block_code FROM drone_mission_block_links WHERE drone_mission_id=%s ORDER BY block_code", (record["id"],))
    record["blocks"] = [{"id": str(row[0]), "code": str(row[1])} for row in cur.fetchall()]
    cur.execute("SELECT id,action,from_status,to_status,actor,note,event_json,created_at FROM drone_mission_timeline WHERE drone_mission_id=%s ORDER BY created_at,id", (record["id"],))
    record["timeline"] = [{
        "id": str(row[0]), "action": str(row[1]), "fromStatus": str(row[2] or ""),
        "toStatus": str(row[3] or ""), "actor": str(row[4] or ""), "note": str(row[5] or ""),
        "data": json_value(row[6], {}), "createdAt": iso_value(row[7]),
    } for row in cur.fetchall()]
    return record


def list_missions(query: str = "", status: str = "", block_code: str = "", device_id: str = "", *, include_deleted: bool = False) -> list[dict[str, Any]]:
    if use_mysql():
        clauses = [] if include_deleted else ["m.deleted_at IS NULL"]
        params: list[Any] = []
        if query:
            clauses.append("(m.mission_no LIKE %s OR m.title LIKE %s OR m.device_name LIKE %s OR m.pilot_name LIKE %s)")
            params.extend([f"%{query}%"] * 4)
        if status:
            clauses.append("m.status=%s")
            params.append(status)
        if device_id:
            clauses.append("m.drone_device_id=%s")
            params.append(device_id)
        if block_code:
            clauses.append("EXISTS (SELECT 1 FROM drone_mission_block_links lb WHERE lb.drone_mission_id=m.id AND lb.block_code=%s)")
            params.append(block_code)
        sql = MISSION_SELECT.replace("FROM drone_missions", "FROM drone_missions m").replace("SELECT id,", "SELECT m.id,")
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                cur.execute(sql + where + " ORDER BY m.updated_at DESC", tuple(params))
                return [hydrate_mission(cur, mission_from_row(row)) for row in cur.fetchall()]
    needle = query.strip().lower()
    records = load_json_records(drone_missions_json_path())
    if not include_deleted:
        records = [item for item in records if not item.get("deletedAt")]
    if status:
        records = [item for item in records if item.get("status") == status]
    if device_id:
        records = [item for item in records if item.get("droneDeviceId") == device_id]
    if block_code:
        records = [item for item in records if block_code in {link.get("code") for link in item.get("blocks") or []}]
    if needle:
        records = [item for item in records if needle in f"{item.get('missionNo')} {item.get('title')} {item.get('deviceName')} {item.get('pilotName')}".lower()]
    return sorted(records, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)


def mission_by_id(mission_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                deleted_clause = "" if include_deleted else " AND deleted_at IS NULL"
                cur.execute(MISSION_SELECT + " WHERE id=%s" + deleted_clause, (mission_id,))
                row = cur.fetchone()
                return hydrate_mission(cur, mission_from_row(row)) if row else None
    return next((item for item in load_json_records(drone_missions_json_path()) if item.get("id") == mission_id and (include_deleted or not item.get("deletedAt"))), None)


def create_mission(record: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    record = {**record, "timeline": [timeline]}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO drone_missions (
                        id,mission_no,title,mission_type,status,drone_device_id,device_code,
                        device_name,pilot_name,route_name,objective,planned_start_at,planned_end_at,
                        actual_start_at,actual_end_at,flight_summary,result_asset_urls,version,
                        created_by,created_at,updated_at,closed_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["id"], record["missionNo"], record["title"], record["missionType"], record["status"],
                     record.get("droneDeviceId") or None, record.get("deviceCode") or None,
                     record.get("deviceName") or None, record.get("pilotName") or None,
                     record.get("routeName") or None, record.get("objective") or None,
                     mysql_datetime(record["plannedStartAt"]), mysql_datetime(record["plannedEndAt"]),
                     mysql_datetime(record.get("actualStartAt")), mysql_datetime(record.get("actualEndAt")),
                     json.dumps(record.get("flightSummary") or {}, ensure_ascii=False),
                     json.dumps(record.get("resultAssetUrls") or [], ensure_ascii=False), record.get("version") or 1,
                     record.get("createdBy") or None, mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"]),
                     mysql_datetime(record.get("closedAt"))),
                )
                links = record.get("blocks") or []
                if links:
                    cur.executemany("INSERT INTO drone_mission_block_links (drone_mission_id,forest_block_id,block_code) VALUES (%s,%s,%s)", [(record["id"], item["id"], item["code"]) for item in links])
                insert_timeline(cur, record["id"], timeline)
            conn.commit()
        return mission_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(drone_missions_json_path())
        records.append(record)
        save_json_records(drone_missions_json_path(), records)
    return record


def insert_timeline(cur: Any, mission_id: str, timeline: dict[str, Any]) -> None:
    cur.execute(
        """INSERT INTO drone_mission_timeline (id,drone_mission_id,action,from_status,to_status,actor,note,event_json,created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (timeline["id"], mission_id, timeline["action"], timeline.get("fromStatus") or None,
         timeline.get("toStatus") or None, timeline.get("actor") or None, timeline.get("note") or None,
         json.dumps(timeline.get("data") or {}, ensure_ascii=False), mysql_datetime(timeline["createdAt"])),
    )


def update_mission(record: dict[str, Any], timeline: dict[str, Any] | None = None) -> dict[str, Any]:
    updated = {**record, "version": int(record.get("version") or 0) + 1, "updatedAt": utc_now()}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE drone_missions SET title=%s,mission_type=%s,status=%s,drone_device_id=%s,
                        device_code=%s,device_name=%s,pilot_name=%s,route_name=%s,objective=%s,
                        planned_start_at=%s,planned_end_at=%s,actual_start_at=%s,actual_end_at=%s,
                        flight_summary=%s,result_asset_urls=%s,version=%s,updated_at=%s,closed_at=%s
                        WHERE id=%s AND deleted_at IS NULL""",
                    (updated["title"], updated["missionType"], updated["status"], updated.get("droneDeviceId") or None,
                     updated.get("deviceCode") or None, updated.get("deviceName") or None, updated.get("pilotName") or None,
                     updated.get("routeName") or None, updated.get("objective") or None,
                     mysql_datetime(updated["plannedStartAt"]), mysql_datetime(updated["plannedEndAt"]),
                     mysql_datetime(updated.get("actualStartAt")), mysql_datetime(updated.get("actualEndAt")),
                     json.dumps(updated.get("flightSummary") or {}, ensure_ascii=False),
                     json.dumps(updated.get("resultAssetUrls") or [], ensure_ascii=False), updated["version"],
                     mysql_datetime(updated["updatedAt"]), mysql_datetime(updated.get("closedAt")), updated["id"]),
                )
                cur.execute("DELETE FROM drone_mission_block_links WHERE drone_mission_id=%s", (updated["id"],))
                links = updated.get("blocks") or []
                if links:
                    cur.executemany("INSERT INTO drone_mission_block_links (drone_mission_id,forest_block_id,block_code) VALUES (%s,%s,%s)", [(updated["id"], item["id"], item["code"]) for item in links])
                if timeline:
                    insert_timeline(cur, updated["id"], timeline)
            conn.commit()
        return mission_by_id(updated["id"]) or updated
    with JSON_STORE_LOCK:
        records = load_json_records(drone_missions_json_path())
        if timeline:
            updated["timeline"] = [*(record.get("timeline") or []), timeline]
        records = [updated if item.get("id") == updated["id"] else item for item in records]
        save_json_records(drone_missions_json_path(), records)
    return updated


def soft_delete_mission(mission_id: str) -> bool:
    return set_mission_deleted(mission_id, deleted=True)


def restore_mission(mission_id: str) -> bool:
    return set_mission_deleted(mission_id, deleted=False)


def set_mission_deleted(mission_id: str, *, deleted: bool) -> bool:
    now = utc_now()
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                current = "IS NULL" if deleted else "IS NOT NULL"
                cur.execute(
                    f"UPDATE drone_missions SET deleted_at=%s,updated_at=%s WHERE id=%s AND deleted_at {current}",
                    (mysql_datetime(now) if deleted else None, mysql_datetime(now), mission_id),
                )
                changed = cur.rowcount > 0
            conn.commit()
        return changed
    with JSON_STORE_LOCK:
        records = load_json_records(drone_missions_json_path())
        changed = False
        for item in records:
            if item.get("id") == mission_id and bool(item.get("deletedAt")) != deleted:
                item["deletedAt"] = now if deleted else None
                item["updatedAt"] = now
                changed = True
        save_json_records(drone_missions_json_path(), records)
    return changed
