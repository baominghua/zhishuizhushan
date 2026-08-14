from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from .database import (
    JSON_STORE_LOCK,
    iot_devices_json_path,
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


DEVICE_SELECT = """
    SELECT id,device_code,name,device_type,vendor,model,serial_no,status,
           connectivity_status,owner_unit,custodian,firmware_version,installed_at,
           last_seen_at,longitude,latitude,location_text,metadata_json,created_by,
           created_at,updated_at,deleted_at
    FROM iot_devices
"""


def device_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "deviceCode": str(row[1]), "name": str(row[2]),
        "deviceType": str(row[3]), "vendor": str(row[4] or ""), "model": str(row[5] or ""),
        "serialNo": str(row[6] or ""), "status": str(row[7]),
        "connectivityStatus": str(row[8]), "ownerUnit": str(row[9] or ""),
        "custodian": str(row[10] or ""), "firmwareVersion": str(row[11] or ""),
        "installedAt": iso_value(row[12]), "lastSeenAt": iso_value(row[13]),
        "longitude": number_value(row[14]), "latitude": number_value(row[15]),
        "locationText": str(row[16] or ""), "metadata": json_value(row[17], {}),
        "createdBy": str(row[18] or ""), "createdAt": iso_value(row[19]),
        "updatedAt": iso_value(row[20]), "deletedAt": iso_value(row[21]),
    }


def hydrate_device(cur: Any, record: dict[str, Any]) -> dict[str, Any]:
    cur.execute(
        "SELECT forest_block_id,block_code FROM iot_device_block_links WHERE iot_device_id=%s ORDER BY block_code",
        (record["id"],),
    )
    record["blocks"] = [{"id": str(row[0]), "code": str(row[1])} for row in cur.fetchall()]
    cur.execute(
        """SELECT id,work_order_no,maintenance_type,status,scheduled_at,completed_at,
                  assignee_name,description,result,created_by,created_at,updated_at
           FROM iot_device_maintenance WHERE iot_device_id=%s ORDER BY created_at DESC""",
        (record["id"],),
    )
    record["maintenance"] = [{
        "id": str(row[0]), "workOrderNo": str(row[1]), "maintenanceType": str(row[2]),
        "status": str(row[3]), "scheduledAt": iso_value(row[4]), "completedAt": iso_value(row[5]),
        "assigneeName": str(row[6] or ""), "description": str(row[7] or ""),
        "result": str(row[8] or ""), "createdBy": str(row[9] or ""),
        "createdAt": iso_value(row[10]), "updatedAt": iso_value(row[11]),
    } for row in cur.fetchall()]
    return record


def list_devices(
    query: str = "", status: str = "", device_type: str = "", block_code: str = "",
    *, include_deleted: bool = False,
) -> list[dict[str, Any]]:
    if use_mysql():
        clauses = [] if include_deleted else ["d.deleted_at IS NULL"]
        params: list[Any] = []
        if query:
            clauses.append("(d.device_code LIKE %s OR d.name LIKE %s OR d.serial_no LIKE %s OR d.owner_unit LIKE %s)")
            params.extend([f"%{query}%"] * 4)
        if status:
            clauses.append("d.status=%s")
            params.append(status)
        if device_type:
            clauses.append("d.device_type=%s")
            params.append(device_type)
        if block_code:
            clauses.append("EXISTS (SELECT 1 FROM iot_device_block_links lb WHERE lb.iot_device_id=d.id AND lb.block_code=%s)")
            params.append(block_code)
        sql = DEVICE_SELECT.replace("FROM iot_devices", "FROM iot_devices d").replace("SELECT id,", "SELECT d.id,")
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                cur.execute(sql + where + " ORDER BY d.updated_at DESC", tuple(params))
                return [hydrate_device(cur, device_from_row(row)) for row in cur.fetchall()]
    needle = query.strip().lower()
    records = load_json_records(iot_devices_json_path())
    if not include_deleted:
        records = [item for item in records if not item.get("deletedAt")]
    if status:
        records = [item for item in records if item.get("status") == status]
    if device_type:
        records = [item for item in records if item.get("deviceType") == device_type]
    if block_code:
        records = [item for item in records if block_code in {link.get("code") for link in item.get("blocks") or []}]
    if needle:
        records = [item for item in records if needle in f"{item.get('deviceCode')} {item.get('name')} {item.get('serialNo')} {item.get('ownerUnit')}".lower()]
    return sorted(records, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)


def device_by_id(device_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                deleted_clause = "" if include_deleted else " AND deleted_at IS NULL"
                cur.execute(DEVICE_SELECT + " WHERE id=%s" + deleted_clause, (device_id,))
                row = cur.fetchone()
                return hydrate_device(cur, device_from_row(row)) if row else None
    return next((
        item for item in load_json_records(iot_devices_json_path())
        if item.get("id") == device_id and (include_deleted or not item.get("deletedAt"))
    ), None)


def device_by_code(device_code: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    normalized = str(device_code or "").strip()
    if not normalized:
        return None
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                deleted_clause = "" if include_deleted else " AND deleted_at IS NULL"
                cur.execute(DEVICE_SELECT + " WHERE device_code=%s" + deleted_clause, (normalized,))
                row = cur.fetchone()
                return hydrate_device(cur, device_from_row(row)) if row else None
    return next((
        item for item in load_json_records(iot_devices_json_path())
        if item.get("deviceCode") == normalized and (include_deleted or not item.get("deletedAt"))
    ), None)


def save_device(record: dict[str, Any], *, create: bool) -> dict[str, Any]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                if create:
                    cur.execute(
                        """INSERT INTO iot_devices (
                            id,device_code,name,device_type,vendor,model,serial_no,status,
                            connectivity_status,owner_unit,custodian,firmware_version,
                            installed_at,last_seen_at,longitude,latitude,location_text,
                            metadata_json,created_by,created_at,updated_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (record["id"], record["deviceCode"], record["name"], record["deviceType"],
                         record.get("vendor") or None, record.get("model") or None, record.get("serialNo") or None,
                         record["status"], record["connectivityStatus"], record.get("ownerUnit") or None,
                         record.get("custodian") or None, record.get("firmwareVersion") or None,
                         mysql_datetime(record.get("installedAt")), mysql_datetime(record.get("lastSeenAt")),
                         record.get("longitude"), record.get("latitude"), record.get("locationText") or None,
                         json.dumps(record.get("metadata") or {}, ensure_ascii=False), record.get("createdBy") or None,
                         mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"])),
                    )
                else:
                    cur.execute(
                        """UPDATE iot_devices SET name=%s,device_type=%s,vendor=%s,model=%s,
                            serial_no=%s,status=%s,connectivity_status=%s,owner_unit=%s,custodian=%s,
                            firmware_version=%s,installed_at=%s,last_seen_at=%s,longitude=%s,latitude=%s,
                            location_text=%s,metadata_json=%s,updated_at=%s WHERE id=%s AND deleted_at IS NULL""",
                        (record["name"], record["deviceType"], record.get("vendor") or None,
                         record.get("model") or None, record.get("serialNo") or None, record["status"],
                         record["connectivityStatus"], record.get("ownerUnit") or None, record.get("custodian") or None,
                         record.get("firmwareVersion") or None, mysql_datetime(record.get("installedAt")),
                         mysql_datetime(record.get("lastSeenAt")), record.get("longitude"), record.get("latitude"),
                         record.get("locationText") or None, json.dumps(record.get("metadata") or {}, ensure_ascii=False),
                         mysql_datetime(record["updatedAt"]), record["id"]),
                    )
                cur.execute("DELETE FROM iot_device_block_links WHERE iot_device_id=%s", (record["id"],))
                links = record.get("blocks") or []
                if links:
                    cur.executemany(
                        "INSERT INTO iot_device_block_links (iot_device_id,forest_block_id,block_code) VALUES (%s,%s,%s)",
                        [(record["id"], item["id"], item["code"]) for item in links],
                    )
            conn.commit()
        return device_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(iot_devices_json_path())
        if create:
            records.append(record)
        else:
            records = [record if item.get("id") == record["id"] else item for item in records]
        save_json_records(iot_devices_json_path(), records)
    return record


def set_device_deleted(device_id: str, *, deleted: bool) -> dict[str, Any] | None:
    now = utc_now()
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                target = mysql_datetime(now) if deleted else None
                predicate = "deleted_at IS NULL" if deleted else "deleted_at IS NOT NULL"
                cur.execute(
                    f"UPDATE iot_devices SET deleted_at=%s,updated_at=%s WHERE id=%s AND {predicate}",
                    (target, mysql_datetime(now), device_id),
                )
                changed = cur.rowcount > 0
            conn.commit()
        return device_by_id(device_id, include_deleted=True) if changed else None
    with JSON_STORE_LOCK:
        records = load_json_records(iot_devices_json_path())
        changed = False
        for item in records:
            matches_state = not item.get("deletedAt") if deleted else bool(item.get("deletedAt"))
            if item.get("id") == device_id and matches_state:
                item["deletedAt"] = now if deleted else None
                item["updatedAt"] = now
                changed = True
        save_json_records(iot_devices_json_path(), records)
    return device_by_id(device_id, include_deleted=True) if changed else None


def soft_delete_device(device_id: str) -> bool:
    return set_device_deleted(device_id, deleted=True) is not None


def restore_device(device_id: str) -> dict[str, Any] | None:
    return set_device_deleted(device_id, deleted=False)


def add_maintenance(device_id: str, record: dict[str, Any]) -> dict[str, Any]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO iot_device_maintenance (
                        id,iot_device_id,work_order_no,maintenance_type,status,scheduled_at,
                        completed_at,assignee_name,description,result,created_by,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["id"], device_id, record["workOrderNo"], record["maintenanceType"], record["status"],
                     mysql_datetime(record.get("scheduledAt")), mysql_datetime(record.get("completedAt")),
                     record.get("assigneeName") or None, record.get("description") or None,
                     record.get("result") or None, record.get("createdBy") or None,
                     mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"])),
                )
            conn.commit()
        return record
    with JSON_STORE_LOCK:
        records = load_json_records(iot_devices_json_path())
        for item in records:
            if item.get("id") == device_id:
                item.setdefault("maintenance", []).insert(0, record)
                item["updatedAt"] = record["updatedAt"]
        save_json_records(iot_devices_json_path(), records)
    return record
