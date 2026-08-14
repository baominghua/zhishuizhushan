from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from .business import business_records
from .database import (
    JSON_STORE_LOCK,
    harvest_applications_json_path,
    harvest_batches_json_path,
    harvest_quotas_json_path,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
)


SUBJECT_MODULES = {
    "farmer": "farmers",
    "cooperative": "cooperatives",
    "enterprise": "enterprises",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mysql_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


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


def iso_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def number_value(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def list_subjects(query: str = "", subject_type: str = "") -> list[dict[str, Any]]:
    needle = str(query or "").strip().lower()
    requested_type = str(subject_type or "").strip()
    items: list[dict[str, Any]] = []
    for item_type, module_key in SUBJECT_MODULES.items():
        if requested_type and requested_type != item_type:
            continue
        for record in business_records(module_key):
            if record.get("deletedAt"):
                continue
            identifier = str(record.get("id") or "")
            name = str(record.get("name") or "").strip()
            code = str(record.get("recordCode") or "").strip()
            if needle and needle not in f"{name} {code}".lower():
                continue
            items.append(
                {
                    "id": identifier,
                    "type": item_type,
                    "code": code,
                    "name": name,
                    "status": str(record.get("status") or ""),
                    "linkedBlockCodes": list(record.get("linkedBlockCodes") or []),
                }
            )
    return sorted(items, key=lambda item: (item["type"], item["name"], item["code"]))


def subject_by_identity(subject_type: str, subject_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in list_subjects(subject_type=subject_type)
            if item["id"] == str(subject_id)
        ),
        None,
    )


def quota_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "quotaYear": int(row[1]),
        "authorityName": str(row[2]),
        "forestType": str(row[3] or ""),
        "blockCode": str(row[4] or ""),
        "quotaAreaMu": number_value(row[5]),
        "quotaQuantityTon": number_value(row[6]),
        "usedAreaMu": number_value(row[7]),
        "usedQuantityTon": number_value(row[8]),
        "status": str(row[9]),
        "notes": str(row[10] or ""),
        "createdBy": str(row[11] or ""),
        "createdAt": iso_value(row[12]),
        "updatedAt": iso_value(row[13]),
        "deletedAt": iso_value(row[14]),
    }


QUOTA_SELECT = """
    SELECT id, quota_year, authority_name, forest_type, block_code,
           quota_area_mu, quota_quantity_ton, used_area_mu, used_quantity_ton,
           status, notes, created_by, created_at, updated_at, deleted_at
    FROM harvest_quotas
"""


def list_quotas(*, year: int | None = None, active_only: bool = True) -> list[dict[str, Any]]:
    if use_mysql():
        clauses: list[str] = []
        params: list[Any] = []
        if year is not None:
            clauses.append("quota_year = %s")
            params.append(year)
        if active_only:
            clauses.extend(["status = 'active'", "deleted_at IS NULL"])
        sql = QUOTA_SELECT + (" WHERE " + " AND ".join(clauses) if clauses else "")
        sql += " ORDER BY quota_year DESC, updated_at DESC"
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                return [quota_from_row(row) for row in cur.fetchall()]
    records = load_json_records(harvest_quotas_json_path())
    return sorted(
        [
            item
            for item in records
            if (year is None or int(item.get("quotaYear") or 0) == year)
            and (not active_only or (item.get("status") == "active" and not item.get("deletedAt")))
        ],
        key=lambda item: (int(item.get("quotaYear") or 0), str(item.get("updatedAt") or "")),
        reverse=True,
    )


def quota_by_id(quota_id: str) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(QUOTA_SELECT + " WHERE id = %s AND deleted_at IS NULL", (quota_id,))
                row = cur.fetchone()
        return quota_from_row(row) if row else None
    return next(
        (item for item in load_json_records(harvest_quotas_json_path()) if item.get("id") == quota_id and not item.get("deletedAt")),
        None,
    )


def create_quota(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    now = utc_now()
    quota = {
        "id": str(uuid.uuid4()),
        "quotaYear": int(payload["quotaYear"]),
        "authorityName": str(payload["authorityName"]).strip(),
        "forestType": str(payload.get("forestType") or "").strip(),
        "blockCode": str(payload.get("blockCode") or "").strip(),
        "quotaAreaMu": float(payload.get("quotaAreaMu") or 0),
        "quotaQuantityTon": float(payload.get("quotaQuantityTon") or 0),
        "usedAreaMu": 0.0,
        "usedQuantityTon": 0.0,
        "status": "active",
        "notes": str(payload.get("notes") or "").strip(),
        "createdBy": actor,
        "createdAt": now,
        "updatedAt": now,
        "deletedAt": None,
    }
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO harvest_quotas (
                        id, quota_year, authority_name, forest_type, block_code,
                        quota_area_mu, quota_quantity_ton, used_area_mu,
                        used_quantity_ton, status, notes, created_by, created_at,
                        updated_at, deleted_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, 'active', %s, %s, %s, %s, NULL)
                    """,
                    (
                        quota["id"], quota["quotaYear"], quota["authorityName"],
                        quota["forestType"] or None, quota["blockCode"] or None,
                        quota["quotaAreaMu"], quota["quotaQuantityTon"], quota["notes"] or None,
                        actor, mysql_datetime(now), mysql_datetime(now),
                    ),
                )
            conn.commit()
        return quota
    with JSON_STORE_LOCK:
        records = load_json_records(harvest_quotas_json_path())
        records.append(quota)
        save_json_records(harvest_quotas_json_path(), records)
    return quota


def event_payload(action: str, from_status: str, to_status: str, actor: str, note: str = "", data: dict[str, Any] | None = None) -> dict[str, Any]:
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


def application_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "applicationNo": str(row[1]), "name": str(row[2]),
        "applicantType": str(row[3]), "applicantId": str(row[4]), "applicantName": str(row[5]),
        "status": str(row[6]), "harvestType": str(row[7]),
        "requestedAreaMu": number_value(row[8]), "requestedQuantityTon": number_value(row[9]),
        "quotaId": str(row[10]), "workStartAt": iso_value(row[11]), "workEndAt": iso_value(row[12]),
        "purpose": str(row[13] or ""), "quotaCheck": json_value(row[14], {}),
        "approval": json_value(row[15], {}), "operation": json_value(row[16], {}),
        "verification": json_value(row[17], {}), "version": int(row[18]),
        "createdBy": str(row[19] or ""), "createdAt": iso_value(row[20]),
        "updatedAt": iso_value(row[21]), "deletedAt": iso_value(row[22]),
    }


APPLICATION_SELECT = """
    SELECT id, application_no, name, applicant_type, applicant_id, applicant_name,
           status, harvest_type, requested_area_mu, requested_quantity_ton,
           quota_id, work_start_at, work_end_at, purpose, quota_check_json,
           approval_json, operation_json, verification_json, version, created_by,
           created_at, updated_at, deleted_at
    FROM harvest_applications
"""


def hydrate_mysql_application(cur: Any, record: dict[str, Any]) -> dict[str, Any]:
    cur.execute(
        "SELECT forest_block_id, block_code, declared_area_mu FROM harvest_application_block_links WHERE harvest_application_id = %s ORDER BY block_code",
        (record["id"],),
    )
    record["blocks"] = [
        {"id": str(row[0]), "code": str(row[1]), "declaredAreaMu": number_value(row[2])}
        for row in cur.fetchall()
    ]
    cur.execute(
        "SELECT forest_right_id, archive_code FROM harvest_application_right_links WHERE harvest_application_id = %s ORDER BY archive_code",
        (record["id"],),
    )
    record["rights"] = [{"id": str(row[0]), "archiveCode": str(row[1])} for row in cur.fetchall()]
    cur.execute(
        "SELECT id, action, from_status, to_status, actor, note, event_json, created_at FROM harvest_events WHERE harvest_application_id = %s ORDER BY created_at, id",
        (record["id"],),
    )
    record["timeline"] = [
        {
            "id": str(row[0]), "action": str(row[1]), "fromStatus": str(row[2] or ""),
            "toStatus": str(row[3] or ""), "actor": str(row[4] or ""), "note": str(row[5] or ""),
            "data": json_value(row[6], {}), "createdAt": iso_value(row[7]),
        }
        for row in cur.fetchall()
    ]
    cur.execute(
        "SELECT id, batch_no, trace_code, actual_area_mu, actual_quantity_ton, block_codes, resource_version_ids, created_by, created_at FROM harvest_batches WHERE harvest_application_id = %s",
        (record["id"],),
    )
    batch = cur.fetchone()
    record["batch"] = None if not batch else {
        "id": str(batch[0]), "batchNo": str(batch[1]), "traceCode": str(batch[2]),
        "actualAreaMu": number_value(batch[3]), "actualQuantityTon": number_value(batch[4]),
        "blockCodes": json_value(batch[5], []), "resourceVersionIds": json_value(batch[6], []),
        "createdBy": str(batch[7] or ""), "createdAt": iso_value(batch[8]),
    }
    return record


def list_applications(*, query: str = "", status: str = "", block_code: str = "", include_deleted: bool = False) -> list[dict[str, Any]]:
    if use_mysql():
        clauses = [] if include_deleted else ["ha.deleted_at IS NULL"]
        params: list[Any] = []
        if query:
            clauses.append("(ha.application_no LIKE %s OR ha.name LIKE %s OR ha.applicant_name LIKE %s)")
            params.extend([f"%{query}%"] * 3)
        if status:
            clauses.append("ha.status = %s")
            params.append(status)
        if block_code:
            clauses.append("EXISTS (SELECT 1 FROM harvest_application_block_links hbl WHERE hbl.harvest_application_id = ha.id AND hbl.block_code = %s)")
            params.append(block_code)
        sql = APPLICATION_SELECT.replace("FROM harvest_applications", "FROM harvest_applications ha").replace("SELECT id,", "SELECT ha.id,")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ha.updated_at DESC"
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                records = [application_from_row(row) for row in cur.fetchall()]
                return [hydrate_mysql_application(cur, record) for record in records]
    needle = query.strip().lower()
    records = load_json_records(harvest_applications_json_path())
    return sorted(
        [
            item for item in records
            if (include_deleted or not item.get("deletedAt"))
            and (not status or item.get("status") == status)
            and (not block_code or block_code in [link.get("code") for link in item.get("blocks") or []])
            and (not needle or needle in f"{item.get('applicationNo')} {item.get('name')} {item.get('applicantName')}".lower())
        ],
        key=lambda item: str(item.get("updatedAt") or ""), reverse=True,
    )


def application_by_id(application_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                suffix = " WHERE id = %s" + ("" if include_deleted else " AND deleted_at IS NULL")
                cur.execute(APPLICATION_SELECT + suffix, (application_id,))
                row = cur.fetchone()
                return hydrate_mysql_application(cur, application_from_row(row)) if row else None
    return next(
        (
            item for item in load_json_records(harvest_applications_json_path())
            if item.get("id") == application_id and (include_deleted or not item.get("deletedAt"))
        ),
        None,
    )


def replace_draft_application(record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    record = {**record, "updatedAt": utc_now(), "version": int(record.get("version") or 0) + 1}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE harvest_applications SET name=%s, applicant_type=%s, applicant_id=%s,
                        applicant_name=%s, harvest_type=%s, requested_area_mu=%s,
                        requested_quantity_ton=%s, quota_id=%s, work_start_at=%s,
                        work_end_at=%s, purpose=%s, version=%s, updated_at=%s
                    WHERE id=%s AND version=%s AND status='draft' AND deleted_at IS NULL
                    """,
                    (
                        record["name"], record["applicantType"], record["applicantId"], record["applicantName"],
                        record["harvestType"], record["requestedAreaMu"], record["requestedQuantityTon"],
                        record["quotaId"], mysql_datetime(record["workStartAt"]), mysql_datetime(record["workEndAt"]),
                        record.get("purpose") or None, record["version"], mysql_datetime(record["updatedAt"]),
                        record["id"], record["version"] - 1,
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("采伐申请已被其他用户更新，或已不再是草稿。")
                cur.execute("DELETE FROM harvest_application_block_links WHERE harvest_application_id = %s", (record["id"],))
                cur.execute("DELETE FROM harvest_application_right_links WHERE harvest_application_id = %s", (record["id"],))
                for block in record["blocks"]:
                    cur.execute(
                        "INSERT INTO harvest_application_block_links (harvest_application_id, forest_block_id, block_code, declared_area_mu) VALUES (%s, %s, %s, %s)",
                        (record["id"], block["id"], block["code"], block.get("declaredAreaMu")),
                    )
                for right in record["rights"]:
                    cur.execute(
                        "INSERT INTO harvest_application_right_links (harvest_application_id, forest_right_id, archive_code) VALUES (%s, %s, %s)",
                        (record["id"], right["id"], right["archiveCode"]),
                    )
                insert_event_mysql(cur, record["id"], event)
            conn.commit()
        return application_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(harvest_applications_json_path())
        index = next((index for index, item in enumerate(records) if item.get("id") == record["id"] and not item.get("deletedAt")), None)
        if index is None or str(records[index].get("status") or "") != "draft":
            raise RuntimeError("采伐申请已被其他用户更新，或已不再是草稿。")
        record["timeline"] = [*(records[index].get("timeline") or []), event]
        records[index] = record
        save_json_records(harvest_applications_json_path(), records)
    return record


def soft_delete_application(application_id: str, actor: str) -> dict[str, Any]:
    record = application_by_id(application_id)
    if not record:
        raise KeyError(application_id)
    if str(record.get("status") or "") != "draft":
        raise ValueError("只有草稿申请可以删除。")
    now = utc_now()
    event = event_payload("delete", "draft", "draft", actor, "采伐申请已移入回收站。")
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE harvest_applications SET deleted_at=%s, updated_at=%s, version=version+1 WHERE id=%s AND status='draft' AND deleted_at IS NULL",
                    (mysql_datetime(now), mysql_datetime(now), application_id),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("采伐申请删除失败，请刷新后重试。")
                insert_event_mysql(cur, application_id, event)
            conn.commit()
        return application_by_id(application_id, include_deleted=True) or {**record, "deletedAt": now}
    with JSON_STORE_LOCK:
        records = load_json_records(harvest_applications_json_path())
        index = next((index for index, item in enumerate(records) if item.get("id") == application_id and not item.get("deletedAt")), None)
        if index is None:
            raise KeyError(application_id)
        records[index] = {
            **records[index], "deletedAt": now, "updatedAt": now,
            "version": int(records[index].get("version") or 0) + 1,
            "timeline": [*(records[index].get("timeline") or []), event],
        }
        save_json_records(harvest_applications_json_path(), records)
        return records[index]


def restore_application(application_id: str, actor: str) -> dict[str, Any]:
    record = application_by_id(application_id, include_deleted=True)
    if not record or not record.get("deletedAt"):
        raise KeyError(application_id)
    if str(record.get("status") or "") != "draft":
        raise ValueError("只有草稿申请可以恢复。")
    now = utc_now()
    event = event_payload("restore", "draft", "draft", actor, "采伐申请已从回收站恢复。")
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE harvest_applications SET deleted_at=NULL, updated_at=%s, version=version+1 WHERE id=%s AND status='draft' AND deleted_at IS NOT NULL",
                    (mysql_datetime(now), application_id),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("采伐申请恢复失败，请刷新后重试。")
                insert_event_mysql(cur, application_id, event)
            conn.commit()
        return application_by_id(application_id) or {**record, "deletedAt": None}
    with JSON_STORE_LOCK:
        records = load_json_records(harvest_applications_json_path())
        index = next((index for index, item in enumerate(records) if item.get("id") == application_id and item.get("deletedAt")), None)
        if index is None:
            raise KeyError(application_id)
        records[index] = {
            **records[index], "deletedAt": None, "updatedAt": now,
            "version": int(records[index].get("version") or 0) + 1,
            "timeline": [*(records[index].get("timeline") or []), event],
        }
        save_json_records(harvest_applications_json_path(), records)
        return records[index]


def insert_event_mysql(cur: Any, application_id: str, event: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO harvest_events (id, harvest_application_id, action, from_status, to_status, actor, note, event_json, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            event["id"], application_id, event["action"], event.get("fromStatus") or None,
            event.get("toStatus") or None, event.get("actor") or None, event.get("note") or None,
            json.dumps(event.get("data") or {}, ensure_ascii=False), mysql_datetime(event["createdAt"]),
        ),
    )


def create_application(record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    record = {**record, "timeline": [event], "batch": None}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO harvest_applications (
                        id, application_no, name, applicant_type, applicant_id, applicant_name,
                        status, harvest_type, requested_area_mu, requested_quantity_ton,
                        quota_id, work_start_at, work_end_at, purpose, quota_check_json,
                        approval_json, operation_json, verification_json, version, created_by,
                        created_at, updated_at, deleted_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                    """,
                    (
                        record["id"], record["applicationNo"], record["name"], record["applicantType"],
                        record["applicantId"], record["applicantName"], record["status"], record["harvestType"],
                        record["requestedAreaMu"], record["requestedQuantityTon"], record["quotaId"],
                        mysql_datetime(record["workStartAt"]), mysql_datetime(record["workEndAt"]), record["purpose"] or None,
                        json.dumps(record["quotaCheck"], ensure_ascii=False), json.dumps(record["approval"], ensure_ascii=False),
                        json.dumps(record["operation"], ensure_ascii=False), json.dumps(record["verification"], ensure_ascii=False),
                        record["version"], record["createdBy"], mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"]),
                    ),
                )
                for block in record["blocks"]:
                    cur.execute(
                        "INSERT INTO harvest_application_block_links (harvest_application_id, forest_block_id, block_code, declared_area_mu) VALUES (%s, %s, %s, %s)",
                        (record["id"], block["id"], block["code"], block.get("declaredAreaMu")),
                    )
                for right in record["rights"]:
                    cur.execute(
                        "INSERT INTO harvest_application_right_links (harvest_application_id, forest_right_id, archive_code) VALUES (%s, %s, %s)",
                        (record["id"], right["id"], right["archiveCode"]),
                    )
                insert_event_mysql(cur, record["id"], event)
            conn.commit()
        return application_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(harvest_applications_json_path())
        records.append(record)
        save_json_records(harvest_applications_json_path(), records)
    return record


def update_application(record: dict[str, Any], event: dict[str, Any], batch: dict[str, Any] | None = None) -> dict[str, Any]:
    record = {**record, "updatedAt": utc_now(), "version": int(record.get("version") or 0) + 1}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE harvest_applications SET status=%s, quota_check_json=%s, approval_json=%s,
                        operation_json=%s, verification_json=%s, version=%s, updated_at=%s
                    WHERE id=%s AND version=%s AND deleted_at IS NULL
                    """,
                    (
                        record["status"], json.dumps(record.get("quotaCheck") or {}, ensure_ascii=False),
                        json.dumps(record.get("approval") or {}, ensure_ascii=False),
                        json.dumps(record.get("operation") or {}, ensure_ascii=False),
                        json.dumps(record.get("verification") or {}, ensure_ascii=False), record["version"],
                        mysql_datetime(record["updatedAt"]), record["id"], record["version"] - 1,
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("采伐申请已被其他用户更新，请刷新后重试。")
                insert_event_mysql(cur, record["id"], event)
                if batch:
                    cur.execute(
                        """
                        INSERT INTO harvest_batches (id, batch_no, harvest_application_id, trace_code,
                            actual_area_mu, actual_quantity_ton, block_codes, resource_version_ids,
                            created_by, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            batch["id"], batch["batchNo"], record["id"], batch["traceCode"],
                            batch["actualAreaMu"], batch["actualQuantityTon"],
                            json.dumps(batch["blockCodes"], ensure_ascii=False),
                            json.dumps(batch["resourceVersionIds"], ensure_ascii=False),
                            batch["createdBy"], mysql_datetime(batch["createdAt"]),
                        ),
                    )
            conn.commit()
        return application_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(harvest_applications_json_path())
        index = next((index for index, item in enumerate(records) if item.get("id") == record["id"]), None)
        if index is None:
            raise RuntimeError("采伐申请不存在。")
        timeline = list(records[index].get("timeline") or [])
        timeline.append(event)
        record["timeline"] = timeline
        if batch:
            record["batch"] = batch
            batches = load_json_records(harvest_batches_json_path())
            batches.append(batch)
            save_json_records(harvest_batches_json_path(), batches)
        records[index] = record
        save_json_records(harvest_applications_json_path(), records)
    return record


def reserve_quota_and_approve(record: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    quota_id = str(record["quotaId"])
    area = float(record["requestedAreaMu"])
    quantity = float(record["requestedQuantityTon"])
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(QUOTA_SELECT + " WHERE id = %s AND status = 'active' AND deleted_at IS NULL FOR UPDATE", (quota_id,))
                row = cur.fetchone()
                if not row:
                    raise ValueError("采伐配额不存在或已停用。")
                quota = quota_from_row(row)
                if quota["usedAreaMu"] + area > quota["quotaAreaMu"] + 1e-8:
                    raise ValueError("剩余采伐面积配额不足。")
                if quota["quotaQuantityTon"] > 0 and quota["usedQuantityTon"] + quantity > quota["quotaQuantityTon"] + 1e-8:
                    raise ValueError("剩余采伐数量配额不足。")
                cur.execute(
                    "UPDATE harvest_quotas SET used_area_mu = used_area_mu + %s, used_quantity_ton = used_quantity_ton + %s, updated_at = %s WHERE id = %s",
                    (area, quantity, mysql_datetime(utc_now()), quota_id),
                )
                record = {**record, "updatedAt": utc_now(), "version": int(record.get("version") or 0) + 1}
                cur.execute(
                    """
                    UPDATE harvest_applications SET status=%s, approval_json=%s, version=%s, updated_at=%s
                    WHERE id=%s AND version=%s AND deleted_at IS NULL
                    """,
                    (record["status"], json.dumps(record["approval"], ensure_ascii=False), record["version"], mysql_datetime(record["updatedAt"]), record["id"], record["version"] - 1),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("采伐申请已被其他用户更新，请刷新后重试。")
                insert_event_mysql(cur, record["id"], event)
            conn.commit()
        return application_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        quotas = load_json_records(harvest_quotas_json_path())
        quota_index = next((index for index, item in enumerate(quotas) if item.get("id") == quota_id and item.get("status") == "active" and not item.get("deletedAt")), None)
        if quota_index is None:
            raise ValueError("采伐配额不存在或已停用。")
        quota = quotas[quota_index]
        if float(quota.get("usedAreaMu") or 0) + area > float(quota.get("quotaAreaMu") or 0) + 1e-8:
            raise ValueError("剩余采伐面积配额不足。")
        if float(quota.get("quotaQuantityTon") or 0) > 0 and float(quota.get("usedQuantityTon") or 0) + quantity > float(quota.get("quotaQuantityTon") or 0) + 1e-8:
            raise ValueError("剩余采伐数量配额不足。")
        quota["usedAreaMu"] = float(quota.get("usedAreaMu") or 0) + area
        quota["usedQuantityTon"] = float(quota.get("usedQuantityTon") or 0) + quantity
        quota["updatedAt"] = utc_now()
        quotas[quota_index] = quota
        save_json_records(harvest_quotas_json_path(), quotas)
        return update_application(record, event)
