from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from .database import (
    JSON_STORE_LOCK,
    labor_jobs_json_path,
    labor_teams_json_path,
    labor_workers_json_path,
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


WORKER_SELECT = """
    SELECT id, worker_no, name, mobile, id_card_mask, gender, employment_status,
           skill_codes, qualifications_json, training_status, credit_score,
           home_address, emergency_contact, notes, created_by, created_at,
           updated_at, deleted_at
    FROM labor_workers
"""


def worker_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "workerNo": str(row[1]), "name": str(row[2]),
        "mobile": str(row[3] or ""), "idCardMask": str(row[4] or ""),
        "gender": str(row[5] or ""), "employmentStatus": str(row[6]),
        "skillCodes": json_value(row[7], []), "qualifications": json_value(row[8], []),
        "trainingStatus": str(row[9]), "creditScore": number_value(row[10]) or 0,
        "homeAddress": str(row[11] or ""), "emergencyContact": str(row[12] or ""),
        "notes": str(row[13] or ""), "createdBy": str(row[14] or ""),
        "createdAt": iso_value(row[15]), "updatedAt": iso_value(row[16]),
        "deletedAt": iso_value(row[17]),
    }


def list_workers(query: str = "", status: str = "", *, include_deleted: bool = False) -> list[dict[str, Any]]:
    if use_mysql():
        clauses = [] if include_deleted else ["deleted_at IS NULL"]
        params: list[Any] = []
        if query:
            clauses.append("(worker_no LIKE %s OR name LIKE %s OR mobile LIKE %s)")
            params.extend([f"%{query}%"] * 3)
        if status:
            clauses.append("employment_status = %s")
            params.append(status)
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                cur.execute(WORKER_SELECT + where + " ORDER BY updated_at DESC", tuple(params))
                return [worker_from_row(row) for row in cur.fetchall()]
    needle = query.strip().lower()
    records = [item for item in load_json_records(labor_workers_json_path()) if include_deleted or not item.get("deletedAt")]
    if status:
        records = [item for item in records if item.get("employmentStatus") == status]
    if needle:
        records = [item for item in records if needle in f"{item.get('workerNo')} {item.get('name')} {item.get('mobile')}".lower()]
    return sorted(records, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)


def worker_by_id(worker_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                deleted_clause = "" if include_deleted else " AND deleted_at IS NULL"
                cur.execute(WORKER_SELECT + " WHERE id = %s" + deleted_clause, (worker_id,))
                row = cur.fetchone()
                return worker_from_row(row) if row else None
    return next((item for item in load_json_records(labor_workers_json_path()) if item.get("id") == worker_id and (include_deleted or not item.get("deletedAt"))), None)


def save_worker(record: dict[str, Any], *, create: bool) -> dict[str, Any]:
    if use_mysql():
        values = (
            record["workerNo"], record["name"], record.get("mobile") or None,
            record.get("idCardMask") or None, record.get("gender") or None,
            record["employmentStatus"], json.dumps(record.get("skillCodes") or [], ensure_ascii=False),
            json.dumps(record.get("qualifications") or [], ensure_ascii=False), record["trainingStatus"],
            record.get("creditScore") or 0, record.get("homeAddress") or None,
            record.get("emergencyContact") or None, record.get("notes") or None,
            mysql_datetime(record["updatedAt"]), record["id"],
        )
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                if create:
                    cur.execute(
                        """INSERT INTO labor_workers (
                            id, worker_no, name, mobile, id_card_mask, gender, employment_status,
                            skill_codes, qualifications_json, training_status, credit_score,
                            home_address, emergency_contact, notes, created_by, created_at, updated_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (record["id"], *values[:-2], record.get("createdBy") or None,
                         mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"])),
                    )
                else:
                    cur.execute(
                        """UPDATE labor_workers SET worker_no=%s, name=%s, mobile=%s,
                            id_card_mask=%s, gender=%s, employment_status=%s, skill_codes=%s,
                            qualifications_json=%s, training_status=%s, credit_score=%s,
                            home_address=%s, emergency_contact=%s, notes=%s, updated_at=%s
                            WHERE id=%s AND deleted_at IS NULL""",
                        values,
                    )
            conn.commit()
        return worker_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(labor_workers_json_path())
        if create:
            records.append(record)
        else:
            records = [record if item.get("id") == record["id"] else item for item in records]
        save_json_records(labor_workers_json_path(), records)
    return record


def set_worker_deleted(worker_id: str, *, deleted: bool) -> dict[str, Any]:
    record = worker_by_id(worker_id, include_deleted=True)
    if not record or bool(record.get("deletedAt")) == deleted:
        raise KeyError(worker_id)
    now = utc_now()
    deleted_at = now if deleted else None
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                expected = "IS NULL" if deleted else "IS NOT NULL"
                cur.execute(
                    f"UPDATE labor_workers SET deleted_at=%s, updated_at=%s WHERE id=%s AND deleted_at {expected}",
                    (mysql_datetime(deleted_at), mysql_datetime(now), worker_id),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("劳务人员状态已变化，请刷新后重试。")
            conn.commit()
        return worker_by_id(worker_id, include_deleted=True) or {**record, "deletedAt": deleted_at, "updatedAt": now}
    with JSON_STORE_LOCK:
        records = load_json_records(labor_workers_json_path())
        index = next((index for index, item in enumerate(records) if item.get("id") == worker_id), None)
        if index is None:
            raise KeyError(worker_id)
        records[index] = {**records[index], "deletedAt": deleted_at, "updatedAt": now}
        save_json_records(labor_workers_json_path(), records)
        return records[index]


TEAM_SELECT = """
    SELECT id, team_no, name, status, leader_worker_id, leader_name, contact_phone,
           service_area, skill_codes, notes, created_by, created_at, updated_at, deleted_at
    FROM labor_teams
"""


def team_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "teamNo": str(row[1]), "name": str(row[2]), "status": str(row[3]),
        "leaderWorkerId": str(row[4] or ""), "leaderName": str(row[5] or ""),
        "contactPhone": str(row[6] or ""), "serviceArea": str(row[7] or ""),
        "skillCodes": json_value(row[8], []), "notes": str(row[9] or ""),
        "createdBy": str(row[10] or ""), "createdAt": iso_value(row[11]),
        "updatedAt": iso_value(row[12]), "deletedAt": iso_value(row[13]),
    }


def hydrate_team(cur: Any, record: dict[str, Any]) -> dict[str, Any]:
    cur.execute(
        """SELECT w.id, w.worker_no, w.name, m.member_role, m.joined_at
           FROM labor_team_members m JOIN labor_workers w ON w.id=m.labor_worker_id
           WHERE m.labor_team_id=%s AND m.left_at IS NULL ORDER BY FIELD(m.member_role,'leader','member'), w.name""",
        (record["id"],),
    )
    record["members"] = [
        {"id": str(row[0]), "workerNo": str(row[1]), "name": str(row[2]),
         "role": str(row[3]), "joinedAt": iso_value(row[4])}
        for row in cur.fetchall()
    ]
    return record


def list_teams(query: str = "", status: str = "", *, include_deleted: bool = False) -> list[dict[str, Any]]:
    if use_mysql():
        clauses = [] if include_deleted else ["deleted_at IS NULL"]
        params: list[Any] = []
        if query:
            clauses.append("(team_no LIKE %s OR name LIKE %s OR leader_name LIKE %s)")
            params.extend([f"%{query}%"] * 3)
        if status:
            clauses.append("status = %s")
            params.append(status)
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                cur.execute(TEAM_SELECT + where + " ORDER BY updated_at DESC", tuple(params))
                return [hydrate_team(cur, team_from_row(row)) for row in cur.fetchall()]
    needle = query.strip().lower()
    records = [item for item in load_json_records(labor_teams_json_path()) if include_deleted or not item.get("deletedAt")]
    if status:
        records = [item for item in records if item.get("status") == status]
    if needle:
        records = [item for item in records if needle in f"{item.get('teamNo')} {item.get('name')} {item.get('leaderName')}".lower()]
    return sorted(records, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)


def team_by_id(team_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                deleted_clause = "" if include_deleted else " AND deleted_at IS NULL"
                cur.execute(TEAM_SELECT + " WHERE id=%s" + deleted_clause, (team_id,))
                row = cur.fetchone()
                return hydrate_team(cur, team_from_row(row)) if row else None
    return next((item for item in load_json_records(labor_teams_json_path()) if item.get("id") == team_id and (include_deleted or not item.get("deletedAt"))), None)


def save_team(record: dict[str, Any], *, create: bool) -> dict[str, Any]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                if create:
                    cur.execute(
                        """INSERT INTO labor_teams (
                            id, team_no, name, status, leader_worker_id, leader_name,
                            contact_phone, service_area, skill_codes, notes, created_by,
                            created_at, updated_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (record["id"], record["teamNo"], record["name"], record["status"],
                         record.get("leaderWorkerId") or None, record.get("leaderName") or None,
                         record.get("contactPhone") or None, record.get("serviceArea") or None,
                         json.dumps(record.get("skillCodes") or [], ensure_ascii=False), record.get("notes") or None,
                         record.get("createdBy") or None, mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"])),
                    )
                else:
                    cur.execute(
                        """UPDATE labor_teams SET name=%s, status=%s, leader_worker_id=%s,
                            leader_name=%s, contact_phone=%s, service_area=%s, skill_codes=%s,
                            notes=%s, updated_at=%s WHERE id=%s AND deleted_at IS NULL""",
                        (record["name"], record["status"], record.get("leaderWorkerId") or None,
                         record.get("leaderName") or None, record.get("contactPhone") or None,
                         record.get("serviceArea") or None, json.dumps(record.get("skillCodes") or [], ensure_ascii=False),
                         record.get("notes") or None, mysql_datetime(record["updatedAt"]), record["id"]),
                    )
                cur.execute("DELETE FROM labor_team_members WHERE labor_team_id=%s", (record["id"],))
                members = record.get("members") or []
                if members:
                    cur.executemany(
                        "INSERT INTO labor_team_members (labor_team_id,labor_worker_id,member_role,joined_at) VALUES (%s,%s,%s,%s)",
                        [(record["id"], item["id"], item.get("role") or "member", mysql_datetime(item.get("joinedAt") or utc_now())) for item in members],
                    )
            conn.commit()
        return team_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(labor_teams_json_path())
        if create:
            records.append(record)
        else:
            records = [record if item.get("id") == record["id"] else item for item in records]
        save_json_records(labor_teams_json_path(), records)
    return record


def set_team_deleted(team_id: str, *, deleted: bool) -> dict[str, Any]:
    record = team_by_id(team_id, include_deleted=True)
    if not record or bool(record.get("deletedAt")) == deleted:
        raise KeyError(team_id)
    now = utc_now()
    deleted_at = now if deleted else None
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                expected = "IS NULL" if deleted else "IS NOT NULL"
                cur.execute(
                    f"UPDATE labor_teams SET deleted_at=%s, updated_at=%s WHERE id=%s AND deleted_at {expected}",
                    (mysql_datetime(deleted_at), mysql_datetime(now), team_id),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("劳务班组状态已变化，请刷新后重试。")
            conn.commit()
        return team_by_id(team_id, include_deleted=True) or {**record, "deletedAt": deleted_at, "updatedAt": now}
    with JSON_STORE_LOCK:
        records = load_json_records(labor_teams_json_path())
        index = next((index for index, item in enumerate(records) if item.get("id") == team_id), None)
        if index is None:
            raise KeyError(team_id)
        records[index] = {**records[index], "deletedAt": deleted_at, "updatedAt": now}
        save_json_records(labor_teams_json_path(), records)
        return records[index]


JOB_SELECT = """
    SELECT id, job_no, title, status, employer_type, employer_id, employer_name,
           work_type, required_headcount, unit_price, price_unit, planned_start_at,
           planned_end_at, team_id, team_name, contract_no, contract_start_at,
           contract_end_at, payment_terms, actual_quantity, settlement_amount,
           settlement_json, instructions, version, created_by, created_at,
           updated_at, closed_at, deleted_at
    FROM labor_jobs
"""


def job_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "jobNo": str(row[1]), "title": str(row[2]), "status": str(row[3]),
        "employerType": str(row[4]), "employerId": str(row[5] or ""), "employerName": str(row[6]),
        "workType": str(row[7]), "requiredHeadcount": int(row[8]), "unitPrice": number_value(row[9]) or 0,
        "priceUnit": str(row[10]), "plannedStartAt": iso_value(row[11]), "plannedEndAt": iso_value(row[12]),
        "teamId": str(row[13] or ""), "teamName": str(row[14] or ""), "contractNo": str(row[15] or ""),
        "contractStartAt": iso_value(row[16]), "contractEndAt": iso_value(row[17]),
        "paymentTerms": str(row[18] or ""), "actualQuantity": number_value(row[19]),
        "settlementAmount": number_value(row[20]), "settlement": json_value(row[21], {}),
        "instructions": str(row[22] or ""), "version": int(row[23]), "createdBy": str(row[24] or ""),
        "createdAt": iso_value(row[25]), "updatedAt": iso_value(row[26]), "closedAt": iso_value(row[27]),
        "deletedAt": iso_value(row[28]),
    }


def hydrate_job(cur: Any, record: dict[str, Any]) -> dict[str, Any]:
    cur.execute("SELECT forest_block_id, block_code FROM labor_job_block_links WHERE labor_job_id=%s ORDER BY block_code", (record["id"],))
    record["blocks"] = [{"id": str(row[0]), "code": str(row[1])} for row in cur.fetchall()]
    cur.execute(
        """SELECT a.id,a.labor_worker_id,w.worker_no,w.name,a.work_date,a.check_in_at,a.check_out_at,
                  a.work_hours,a.work_quantity,a.status,a.verifier_name,a.note,a.created_by,a.created_at,a.updated_at
           FROM labor_attendance a JOIN labor_workers w ON w.id=a.labor_worker_id
           WHERE a.labor_job_id=%s ORDER BY a.work_date DESC,w.name""",
        (record["id"],),
    )
    record["attendance"] = [{
        "id": str(row[0]), "workerId": str(row[1]), "workerNo": str(row[2]), "workerName": str(row[3]),
        "workDate": iso_value(row[4]), "checkInAt": iso_value(row[5]), "checkOutAt": iso_value(row[6]),
        "workHours": number_value(row[7]) or 0, "workQuantity": number_value(row[8]), "status": str(row[9]),
        "verifierName": str(row[10] or ""), "note": str(row[11] or ""), "createdBy": str(row[12] or ""),
        "createdAt": iso_value(row[13]), "updatedAt": iso_value(row[14]),
    } for row in cur.fetchall()]
    cur.execute("SELECT id,action,from_status,to_status,actor,note,event_json,created_at FROM labor_job_timeline WHERE labor_job_id=%s ORDER BY created_at,id", (record["id"],))
    record["timeline"] = [{
        "id": str(row[0]), "action": str(row[1]), "fromStatus": str(row[2] or ""), "toStatus": str(row[3] or ""),
        "actor": str(row[4] or ""), "note": str(row[5] or ""), "data": json_value(row[6], {}), "createdAt": iso_value(row[7]),
    } for row in cur.fetchall()]
    return record


def list_jobs(query: str = "", status: str = "", block_code: str = "", *, include_deleted: bool = False) -> list[dict[str, Any]]:
    if use_mysql():
        clauses = [] if include_deleted else ["lj.deleted_at IS NULL"]
        params: list[Any] = []
        if query:
            clauses.append("(lj.job_no LIKE %s OR lj.title LIKE %s OR lj.employer_name LIKE %s OR lj.team_name LIKE %s)")
            params.extend([f"%{query}%"] * 4)
        if status:
            clauses.append("lj.status=%s")
            params.append(status)
        if block_code:
            clauses.append("EXISTS (SELECT 1 FROM labor_job_block_links lb WHERE lb.labor_job_id=lj.id AND lb.block_code=%s)")
            params.append(block_code)
        sql = JOB_SELECT.replace("FROM labor_jobs", "FROM labor_jobs lj").replace("SELECT id,", "SELECT lj.id,")
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                cur.execute(sql + where + " ORDER BY lj.updated_at DESC", tuple(params))
                return [hydrate_job(cur, job_from_row(row)) for row in cur.fetchall()]
    needle = query.strip().lower()
    records = [item for item in load_json_records(labor_jobs_json_path()) if include_deleted or not item.get("deletedAt")]
    if status:
        records = [item for item in records if item.get("status") == status]
    if block_code:
        records = [item for item in records if block_code in [str(link.get("code")) for link in item.get("blocks") or []]]
    if needle:
        records = [item for item in records if needle in f"{item.get('jobNo')} {item.get('title')} {item.get('employerName')} {item.get('teamName')}".lower()]
    return sorted(records, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)


def job_by_id(job_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                deleted_clause = "" if include_deleted else " AND deleted_at IS NULL"
                cur.execute(JOB_SELECT + " WHERE id=%s" + deleted_clause, (job_id,))
                row = cur.fetchone()
                return hydrate_job(cur, job_from_row(row)) if row else None
    return next((item for item in load_json_records(labor_jobs_json_path()) if item.get("id") == job_id and (include_deleted or not item.get("deletedAt"))), None)


def insert_timeline_mysql(cur: Any, job_id: str, entry: dict[str, Any]) -> None:
    cur.execute(
        "INSERT INTO labor_job_timeline (id,labor_job_id,action,from_status,to_status,actor,note,event_json,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (entry["id"], job_id, entry["action"], entry.get("fromStatus") or None, entry.get("toStatus") or None,
         entry.get("actor") or None, entry.get("note") or None, json.dumps(entry.get("data") or {}, ensure_ascii=False), mysql_datetime(entry["createdAt"])),
    )


def create_job(record: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    record = {**record, "timeline": [entry], "attendance": []}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO labor_jobs (
                        id,job_no,title,status,employer_type,employer_id,employer_name,work_type,
                        required_headcount,unit_price,price_unit,planned_start_at,planned_end_at,
                        settlement_json,instructions,version,created_by,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["id"],record["jobNo"],record["title"],record["status"],record["employerType"],
                     record.get("employerId") or None,record["employerName"],record["workType"],record["requiredHeadcount"],
                     record["unitPrice"],record["priceUnit"],mysql_datetime(record["plannedStartAt"]),mysql_datetime(record["plannedEndAt"]),
                     json.dumps({},ensure_ascii=False),record.get("instructions") or None,record["version"],record.get("createdBy") or None,
                     mysql_datetime(record["createdAt"]),mysql_datetime(record["updatedAt"])),
                )
                for block in record.get("blocks") or []:
                    cur.execute("INSERT INTO labor_job_block_links (labor_job_id,forest_block_id,block_code) VALUES (%s,%s,%s)", (record["id"],block["id"],block["code"]))
                insert_timeline_mysql(cur, record["id"], entry)
            conn.commit()
        return job_by_id(record["id"]) or record
    with JSON_STORE_LOCK:
        records = load_json_records(labor_jobs_json_path())
        records.append(record)
        save_json_records(labor_jobs_json_path(), records)
    return record


def replace_draft_job(record: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    updated = {**record, "updatedAt": utc_now(), "version": int(record.get("version") or 0) + 1}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE labor_jobs SET title=%s,employer_type=%s,employer_id=%s,
                        employer_name=%s,work_type=%s,required_headcount=%s,unit_price=%s,
                        price_unit=%s,planned_start_at=%s,planned_end_at=%s,instructions=%s,
                        version=%s,updated_at=%s
                        WHERE id=%s AND version=%s AND status='draft' AND deleted_at IS NULL""",
                    (
                        updated["title"], updated["employerType"], updated.get("employerId") or None,
                        updated["employerName"], updated["workType"], updated["requiredHeadcount"],
                        updated["unitPrice"], updated["priceUnit"], mysql_datetime(updated["plannedStartAt"]),
                        mysql_datetime(updated["plannedEndAt"]), updated.get("instructions") or None,
                        updated["version"], mysql_datetime(updated["updatedAt"]), updated["id"], updated["version"] - 1,
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("用工任务已被其他用户更新，或已不再是草稿。")
                cur.execute("DELETE FROM labor_job_block_links WHERE labor_job_id=%s", (updated["id"],))
                for block in updated.get("blocks") or []:
                    cur.execute(
                        "INSERT INTO labor_job_block_links (labor_job_id,forest_block_id,block_code) VALUES (%s,%s,%s)",
                        (updated["id"], block["id"], block["code"]),
                    )
                insert_timeline_mysql(cur, updated["id"], entry)
            conn.commit()
        return job_by_id(updated["id"]) or updated
    with JSON_STORE_LOCK:
        records = load_json_records(labor_jobs_json_path())
        index = next((index for index, item in enumerate(records) if item.get("id") == updated["id"] and not item.get("deletedAt")), None)
        if index is None or str(records[index].get("status") or "") != "draft":
            raise RuntimeError("用工任务已被其他用户更新，或已不再是草稿。")
        updated["timeline"] = [*(records[index].get("timeline") or []), entry]
        updated["attendance"] = list(records[index].get("attendance") or [])
        records[index] = updated
        save_json_records(labor_jobs_json_path(), records)
    return updated


def set_job_deleted(job_id: str, *, deleted: bool, actor: str) -> dict[str, Any]:
    record = job_by_id(job_id, include_deleted=True)
    if not record or bool(record.get("deletedAt")) == deleted:
        raise KeyError(job_id)
    if str(record.get("status") or "") != "draft":
        raise ValueError("只有草稿用工任务可以删除或恢复。")
    now = utc_now()
    deleted_at = now if deleted else None
    action = "delete" if deleted else "restore"
    note = "用工任务已移入回收站。" if deleted else "用工任务已从回收站恢复。"
    entry = timeline_entry(action, "draft", "draft", actor, note)
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                expected = "IS NULL" if deleted else "IS NOT NULL"
                cur.execute(
                    f"UPDATE labor_jobs SET deleted_at=%s,updated_at=%s,version=version+1 WHERE id=%s AND status='draft' AND deleted_at {expected}",
                    (mysql_datetime(deleted_at), mysql_datetime(now), job_id),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("用工任务状态已变化，请刷新后重试。")
                insert_timeline_mysql(cur, job_id, entry)
            conn.commit()
        return job_by_id(job_id, include_deleted=True) or {**record, "deletedAt": deleted_at, "updatedAt": now}
    with JSON_STORE_LOCK:
        records = load_json_records(labor_jobs_json_path())
        index = next((index for index, item in enumerate(records) if item.get("id") == job_id), None)
        if index is None:
            raise KeyError(job_id)
        records[index] = {
            **records[index], "deletedAt": deleted_at, "updatedAt": now,
            "version": int(records[index].get("version") or 0) + 1,
            "timeline": [*(records[index].get("timeline") or []), entry],
        }
        save_json_records(labor_jobs_json_path(), records)
        return records[index]


def update_job(record: dict[str, Any], entry: dict[str, Any], attendance: dict[str, Any] | None = None) -> dict[str, Any]:
    now = utc_now()
    updated = {**record, "updatedAt": now, "version": int(record.get("version") or 0) + 1}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE labor_jobs SET status=%s,team_id=%s,team_name=%s,contract_no=%s,
                        contract_start_at=%s,contract_end_at=%s,payment_terms=%s,actual_quantity=%s,
                        settlement_amount=%s,settlement_json=%s,version=%s,updated_at=%s,closed_at=%s
                        WHERE id=%s AND deleted_at IS NULL""",
                    (updated["status"],updated.get("teamId") or None,updated.get("teamName") or None,updated.get("contractNo") or None,
                     mysql_datetime(updated.get("contractStartAt")),mysql_datetime(updated.get("contractEndAt")),updated.get("paymentTerms") or None,
                     updated.get("actualQuantity"),updated.get("settlementAmount"),json.dumps(updated.get("settlement") or {},ensure_ascii=False),
                     updated["version"],mysql_datetime(now),mysql_datetime(updated.get("closedAt")),updated["id"]),
                )
                if attendance:
                    cur.execute(
                        """INSERT INTO labor_attendance (
                            id,labor_job_id,labor_worker_id,work_date,check_in_at,check_out_at,
                            work_hours,work_quantity,status,verifier_name,note,created_by,created_at,updated_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE check_in_at=VALUES(check_in_at),check_out_at=VALUES(check_out_at),
                            work_hours=VALUES(work_hours),work_quantity=VALUES(work_quantity),status=VALUES(status),
                            verifier_name=VALUES(verifier_name),note=VALUES(note),updated_at=VALUES(updated_at)""",
                        (attendance["id"],updated["id"],attendance["workerId"],attendance["workDate"],
                         mysql_datetime(attendance.get("checkInAt")),mysql_datetime(attendance.get("checkOutAt")),
                         attendance["workHours"],attendance.get("workQuantity"),attendance["status"],attendance.get("verifierName") or None,
                         attendance.get("note") or None,attendance.get("createdBy") or None,mysql_datetime(attendance["createdAt"]),mysql_datetime(attendance["updatedAt"])),
                    )
                insert_timeline_mysql(cur, updated["id"], entry)
            conn.commit()
        return job_by_id(updated["id"]) or updated
    with JSON_STORE_LOCK:
        records = load_json_records(labor_jobs_json_path())
        for index, item in enumerate(records):
            if item.get("id") == updated["id"]:
                updated["timeline"] = [*(item.get("timeline") or []), entry]
                existing_attendance = list(item.get("attendance") or [])
                if attendance:
                    existing_attendance = [row for row in existing_attendance if not (row.get("workerId") == attendance["workerId"] and row.get("workDate") == attendance["workDate"])]
                    existing_attendance.append(attendance)
                updated["attendance"] = existing_attendance
                records[index] = updated
                break
        else:
            raise KeyError(updated["id"])
        save_json_records(labor_jobs_json_path(), records)
    return updated
