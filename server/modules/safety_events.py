from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from .database import (
    JSON_STORE_LOCK,
    load_json_records,
    mysql_connect,
    safety_alerts_json_path,
    safety_events_json_path,
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


def timeline_entry(
    action: str,
    from_status: str,
    to_status: str,
    actor: str,
    note: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "action": action,
        "fromStatus": from_status,
        "toStatus": to_status,
        "actor": actor,
        "note": str(note or "").strip(),
        "data": dict(data or {}),
        "createdAt": utc_now(),
    }


def event_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "incidentNo": str(row[1]),
        "title": str(row[2]),
        "eventType": str(row[3]),
        "severity": str(row[4]),
        "status": str(row[5]),
        "sourceType": str(row[6]),
        "sourceRef": str(row[7] or ""),
        "locationText": str(row[8] or ""),
        "longitude": number_value(row[9]),
        "latitude": number_value(row[10]),
        "responsibilityUnit": str(row[11] or ""),
        "assigneeName": str(row[12] or ""),
        "deadlineAt": iso_value(row[13]),
        "description": str(row[14] or ""),
        "resolution": json_value(row[15], {}),
        "review": json_value(row[16], {}),
        "version": int(row[17]),
        "createdBy": str(row[18] or ""),
        "createdAt": iso_value(row[19]),
        "updatedAt": iso_value(row[20]),
        "closedAt": iso_value(row[21]),
        "deletedAt": iso_value(row[22]),
    }


EVENT_SELECT = """
    SELECT id, incident_no, title, event_type, severity, status, source_type,
           source_ref, location_text, longitude, latitude, responsibility_unit,
           assignee_name, deadline_at, description, resolution_json, review_json,
           version, created_by, created_at, updated_at, closed_at, deleted_at
    FROM safety_events
"""


def hydrate_event(cur: Any, record: dict[str, Any]) -> dict[str, Any]:
    cur.execute(
        "SELECT forest_block_id, block_code FROM safety_event_block_links WHERE safety_event_id = %s ORDER BY block_code",
        (record["id"],),
    )
    record["blocks"] = [{"id": str(row[0]), "code": str(row[1])} for row in cur.fetchall()]
    cur.execute(
        "SELECT id, action, from_status, to_status, actor, note, event_json, created_at FROM safety_event_timeline WHERE safety_event_id = %s ORDER BY created_at, id",
        (record["id"],),
    )
    record["timeline"] = [
        {
            "id": str(row[0]),
            "action": str(row[1]),
            "fromStatus": str(row[2] or ""),
            "toStatus": str(row[3] or ""),
            "actor": str(row[4] or ""),
            "note": str(row[5] or ""),
            "data": json_value(row[6], {}),
            "createdAt": iso_value(row[7]),
        }
        for row in cur.fetchall()
    ]
    return record


def list_events(
    *,
    query: str = "",
    status: str = "",
    severity: str = "",
    block_code: str = "",
    overdue_only: bool = False,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    if use_mysql():
        clauses = [] if include_deleted else ["se.deleted_at IS NULL"]
        params: list[Any] = []
        if query:
            clauses.append("(se.incident_no LIKE %s OR se.title LIKE %s OR se.location_text LIKE %s OR se.assignee_name LIKE %s)")
            params.extend([f"%{query}%"] * 4)
        if status:
            clauses.append("se.status = %s")
            params.append(status)
        if severity:
            clauses.append("se.severity = %s")
            params.append(severity)
        if block_code:
            clauses.append("EXISTS (SELECT 1 FROM safety_event_block_links sbl WHERE sbl.safety_event_id = se.id AND sbl.block_code = %s)")
            params.append(block_code)
        if overdue_only:
            clauses.append("se.deadline_at < UTC_TIMESTAMP() AND se.status NOT IN ('verified', 'closed')")
        sql = EVENT_SELECT.replace("FROM safety_events", "FROM safety_events se").replace("SELECT id,", "SELECT se.id,")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY FIELD(se.severity, 'critical', 'high', 'medium', 'low'), se.updated_at DESC"
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                return [hydrate_event(cur, event_from_row(row)) for row in cur.fetchall()]
    needle = query.strip().lower()
    now = datetime.now(timezone.utc)
    records = []
    for item in load_json_records(safety_events_json_path()):
        if item.get("deletedAt") and not include_deleted:
            continue
        if status and item.get("status") != status:
            continue
        if severity and item.get("severity") != severity:
            continue
        if block_code and block_code not in [str(link.get("code")) for link in item.get("blocks") or []]:
            continue
        if needle and needle not in f"{item.get('incidentNo')} {item.get('title')} {item.get('locationText')} {item.get('assigneeName')}".lower():
            continue
        if overdue_only:
            deadline = item.get("deadlineAt")
            if not deadline or item.get("status") in {"verified", "closed"}:
                continue
            if datetime.fromisoformat(str(deadline).replace("Z", "+00:00")) >= now:
                continue
        records.append(item)
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    records.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    records.sort(key=lambda item: severity_order.get(str(item.get("severity")), 9))
    return records


def event_by_id(event_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                sql = EVENT_SELECT + " WHERE id = %s"
                if not include_deleted:
                    sql += " AND deleted_at IS NULL"
                cur.execute(sql, (event_id,))
                row = cur.fetchone()
                return hydrate_event(cur, event_from_row(row)) if row else None
    return next(
        (item for item in load_json_records(safety_events_json_path()) if item.get("id") == event_id and (include_deleted or not item.get("deletedAt"))),
        None,
    )


def insert_timeline_mysql(cur: Any, event_id: str, entry: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO safety_event_timeline (
            id, safety_event_id, action, from_status, to_status, actor, note, event_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            entry["id"], event_id, entry["action"], entry.get("fromStatus") or None,
            entry.get("toStatus") or None, entry.get("actor") or None,
            entry.get("note") or None, json.dumps(entry.get("data") or {}, ensure_ascii=False),
            mysql_datetime(entry["createdAt"]),
        ),
    )


def create_event(record: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    record = {**record, "timeline": [entry]}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO safety_events (
                        id, incident_no, title, event_type, severity, status, source_type,
                        source_ref, location_text, longitude, latitude, responsibility_unit,
                        assignee_name, deadline_at, description, resolution_json, review_json,
                        version, created_by, created_at, updated_at, closed_at, deleted_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL)
                    """,
                    (
                        record["id"], record["incidentNo"], record["title"], record["eventType"],
                        record["severity"], record["status"], record["sourceType"], record.get("sourceRef") or None,
                        record.get("locationText") or None, record.get("longitude"), record.get("latitude"),
                        record.get("responsibilityUnit") or None, record.get("assigneeName") or None,
                        mysql_datetime(record.get("deadlineAt")), record.get("description") or None,
                        json.dumps(record.get("resolution") or {}, ensure_ascii=False),
                        json.dumps(record.get("review") or {}, ensure_ascii=False), record.get("version", 1),
                        record.get("createdBy") or None, mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"]),
                    ),
                )
                for block in record.get("blocks") or []:
                    cur.execute(
                        "INSERT INTO safety_event_block_links (safety_event_id, forest_block_id, block_code) VALUES (%s, %s, %s)",
                        (record["id"], block["id"], block["code"]),
                    )
                insert_timeline_mysql(cur, record["id"], entry)
            conn.commit()
        return event_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(safety_events_json_path())
        records.append(record)
        save_json_records(safety_events_json_path(), records)
    return record


def update_event(record: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    updated = {**record, "updatedAt": now, "version": int(record.get("version") or 0) + 1}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE safety_events SET title=%s, event_type=%s, severity=%s, status=%s,
                        source_type=%s, source_ref=%s,
                        location_text=%s, longitude=%s, latitude=%s, responsibility_unit=%s,
                        assignee_name=%s, deadline_at=%s, description=%s, resolution_json=%s,
                        review_json=%s, version=%s, updated_at=%s, closed_at=%s
                    WHERE id=%s AND deleted_at IS NULL
                    """,
                    (
                        updated["title"], updated["eventType"], updated["severity"], updated["status"],
                        updated.get("sourceType") or "manual", updated.get("sourceRef") or None,
                        updated.get("locationText") or None, updated.get("longitude"), updated.get("latitude"),
                        updated.get("responsibilityUnit") or None, updated.get("assigneeName") or None,
                        mysql_datetime(updated.get("deadlineAt")), updated.get("description") or None,
                        json.dumps(updated.get("resolution") or {}, ensure_ascii=False),
                        json.dumps(updated.get("review") or {}, ensure_ascii=False), updated["version"],
                        mysql_datetime(now), mysql_datetime(updated.get("closedAt")), updated["id"],
                    ),
                )
                cur.execute("DELETE FROM safety_event_block_links WHERE safety_event_id=%s", (updated["id"],))
                for block in updated.get("blocks") or []:
                    cur.execute(
                        "INSERT INTO safety_event_block_links (safety_event_id, forest_block_id, block_code) VALUES (%s, %s, %s)",
                        (updated["id"], block["id"], block["code"]),
                    )
                insert_timeline_mysql(cur, updated["id"], entry)
            conn.commit()
        return event_by_id(updated["id"]) or updated
    with JSON_STORE_LOCK:
        records = load_json_records(safety_events_json_path())
        for index, item in enumerate(records):
            if item.get("id") == updated["id"]:
                updated["timeline"] = [*(item.get("timeline") or []), entry]
                records[index] = updated
                break
        else:
            raise KeyError(updated["id"])
        save_json_records(safety_events_json_path(), records)
    return updated


def set_event_deleted(event_id: str, *, deleted: bool, actor: str) -> dict[str, Any]:
    record = event_by_id(event_id, include_deleted=True)
    if not record:
        raise KeyError(event_id)
    if record.get("status") != "new":
        raise RuntimeError("只有未分级的安全事件可以删除或恢复。")
    now = utc_now()
    deleted_at = now if deleted else None
    entry = timeline_entry(
        "delete" if deleted else "restore", "new", "new", actor,
        "安全事件已移入回收站。" if deleted else "安全事件已从回收站恢复。",
    )
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE safety_events SET deleted_at=%s, updated_at=%s, version=version+1 WHERE id=%s",
                    (mysql_datetime(deleted_at), mysql_datetime(now), event_id),
                )
                insert_timeline_mysql(cur, event_id, entry)
            conn.commit()
        return event_by_id(event_id, include_deleted=True) or record
    with JSON_STORE_LOCK:
        records = load_json_records(safety_events_json_path())
        for index, item in enumerate(records):
            if item.get("id") == event_id:
                updated = {**item, "deletedAt": deleted_at, "updatedAt": now, "version": int(item.get("version") or 0) + 1,
                           "timeline": [*(item.get("timeline") or []), entry]}
                records[index] = updated
                save_json_records(safety_events_json_path(), records)
                return updated
    raise KeyError(event_id)


def alert_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "alertNo": str(row[1]), "title": str(row[2]),
        "alertType": str(row[3]), "severity": str(row[4]), "status": str(row[5]),
        "sourceType": str(row[6]), "sourceRef": str(row[7] or ""), "deviceCode": str(row[8] or ""),
        "locationText": str(row[9] or ""), "longitude": number_value(row[10]), "latitude": number_value(row[11]),
        "description": str(row[12] or ""), "linkedBlockCodes": json_value(row[13], []),
        "rawPayload": json_value(row[14], {}), "review": json_value(row[15], {}),
        "eventId": str(row[16] or ""), "occurredAt": iso_value(row[17]),
        "createdAt": iso_value(row[18]), "updatedAt": iso_value(row[19]),
    }


ALERT_SELECT = """
    SELECT id, alert_no, title, alert_type, severity, status, source_type, source_ref,
           device_code, location_text, longitude, latitude, description, block_codes,
           raw_payload, review_json, safety_event_id, occurred_at, created_at, updated_at
    FROM safety_alerts
"""


def list_alerts(*, query: str = "", status: str = "", severity: str = "") -> list[dict[str, Any]]:
    if use_mysql():
        clauses: list[str] = []
        params: list[Any] = []
        if query:
            clauses.append("(alert_no LIKE %s OR title LIKE %s OR device_code LIKE %s OR location_text LIKE %s)")
            params.extend([f"%{query}%"] * 4)
        if status:
            clauses.append("status = %s")
            params.append(status)
        if severity:
            clauses.append("severity = %s")
            params.append(severity)
        sql = ALERT_SELECT + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY occurred_at DESC"
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                return [alert_from_row(row) for row in cur.fetchall()]
    needle = query.strip().lower()
    return sorted(
        [
            item for item in load_json_records(safety_alerts_json_path())
            if (not status or item.get("status") == status)
            and (not severity or item.get("severity") == severity)
            and (not needle or needle in f"{item.get('alertNo')} {item.get('title')} {item.get('deviceCode')} {item.get('locationText')}".lower())
        ],
        key=lambda item: str(item.get("occurredAt") or ""), reverse=True,
    )


def alert_by_id(alert_id: str) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ALERT_SELECT + " WHERE id = %s", (alert_id,))
                row = cur.fetchone()
        return alert_from_row(row) if row else None
    return next((item for item in load_json_records(safety_alerts_json_path()) if item.get("id") == alert_id), None)


def create_alert(record: dict[str, Any]) -> dict[str, Any]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO safety_alerts (
                        id, alert_no, title, alert_type, severity, status, source_type,
                        source_ref, device_code, location_text, longitude, latitude,
                        description, block_codes, raw_payload, review_json, safety_event_id,
                        occurred_at, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
                    """,
                    (
                        record["id"], record["alertNo"], record["title"], record["alertType"],
                        record["severity"], record["status"], record["sourceType"], record.get("sourceRef") or None,
                        record.get("deviceCode") or None, record.get("locationText") or None,
                        record.get("longitude"), record.get("latitude"), record.get("description") or None,
                        json.dumps(record.get("linkedBlockCodes") or [], ensure_ascii=False),
                        json.dumps(record.get("rawPayload") or {}, ensure_ascii=False),
                        json.dumps(record.get("review") or {}, ensure_ascii=False),
                        mysql_datetime(record["occurredAt"]), mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"]),
                    ),
                )
            conn.commit()
        return alert_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(safety_alerts_json_path())
        records.append(record)
        save_json_records(safety_alerts_json_path(), records)
    return record


def update_alert(
    alert_id: str,
    *,
    status: str,
    event_id: str = "",
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    review_value = dict(review or {})
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE safety_alerts SET status=%s, safety_event_id=%s, review_json=%s, updated_at=%s WHERE id=%s",
                    (
                        status,
                        event_id or None,
                        json.dumps(review_value, ensure_ascii=False),
                        mysql_datetime(now),
                        alert_id,
                    ),
                )
            conn.commit()
        updated = alert_by_id(alert_id)
        if not updated:
            raise KeyError(alert_id)
        return updated
    with JSON_STORE_LOCK:
        records = load_json_records(safety_alerts_json_path())
        for index, item in enumerate(records):
            if item.get("id") == alert_id:
                records[index] = {
                    **item,
                    "status": status,
                    "eventId": event_id,
                    "review": review_value,
                    "updatedAt": now,
                }
                updated = records[index]
                break
        else:
            raise KeyError(alert_id)
        save_json_records(safety_alerts_json_path(), records)
    return updated
