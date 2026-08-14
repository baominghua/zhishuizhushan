from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from .database import (
    JSON_STORE_LOCK,
    load_json_records,
    mobile_evidence_json_path,
    mobile_tracks_json_path,
    mobile_upload_sessions_json_path,
    mobile_sync_operations_json_path,
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


OPERATION_SELECT = """
    SELECT id,client_operation_id,user_id,entity_type,entity_id,action,base_version,
           status,request_json,result_json,error_code,occurred_at,received_at,completed_at
    FROM mobile_sync_operations
"""


def operation_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "clientOperationId": str(row[1]),
        "userId": str(row[2]),
        "entityType": str(row[3]),
        "entityId": str(row[4] or ""),
        "action": str(row[5]),
        "baseVersion": str(row[6] or ""),
        "status": str(row[7]),
        "request": json_value(row[8], {}),
        "result": json_value(row[9], {}),
        "errorCode": str(row[10] or ""),
        "occurredAt": iso_value(row[11]),
        "receivedAt": iso_value(row[12]),
        "completedAt": iso_value(row[13]),
    }


def operation_by_client_id(user_id: str, client_operation_id: str) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    OPERATION_SELECT + " WHERE user_id=%s AND client_operation_id=%s",
                    (user_id, client_operation_id),
                )
                row = cur.fetchone()
                return operation_from_row(row) if row else None
    return next(
        (
            item
            for item in load_json_records(mobile_sync_operations_json_path())
            if item.get("userId") == user_id
            and item.get("clientOperationId") == client_operation_id
        ),
        None,
    )


def operation_by_id(operation_id: str) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(OPERATION_SELECT + " WHERE id=%s", (operation_id,))
                row = cur.fetchone()
                return operation_from_row(row) if row else None
    return next(
        (
            item
            for item in load_json_records(mobile_sync_operations_json_path())
            if str(item.get("id") or "") == operation_id
        ),
        None,
    )


def begin_operation(record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT IGNORE INTO mobile_sync_operations (
                           id,client_operation_id,user_id,entity_type,entity_id,action,
                           base_version,status,request_json,result_json,error_code,
                           occurred_at,received_at,completed_at
                       ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        record["id"],
                        record["clientOperationId"],
                        record["userId"],
                        record["entityType"],
                        record.get("entityId") or None,
                        record["action"],
                        record.get("baseVersion") or None,
                        record["status"],
                        json.dumps(record.get("request") or {}, ensure_ascii=False),
                        json.dumps(record.get("result") or {}, ensure_ascii=False),
                        record.get("errorCode") or None,
                        mysql_datetime(record["occurredAt"]),
                        mysql_datetime(record["receivedAt"]),
                        mysql_datetime(record.get("completedAt")),
                    ),
                )
                created = cur.rowcount == 1
            conn.commit()
        stored = operation_by_client_id(record["userId"], record["clientOperationId"])
        return stored or record, created

    with JSON_STORE_LOCK:
        path = mobile_sync_operations_json_path()
        records = load_json_records(path)
        existing = next(
            (
                item
                for item in records
                if item.get("userId") == record["userId"]
                and item.get("clientOperationId") == record["clientOperationId"]
            ),
            None,
        )
        if existing:
            return existing, False
        records.append(record)
        save_json_records(path, records)
    return record, True


def complete_operation(
    operation_id: str,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error_code: str = "",
) -> dict[str, Any]:
    completed_at = utc_now()
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE mobile_sync_operations
                       SET status=%s,result_json=%s,error_code=%s,completed_at=%s
                       WHERE id=%s""",
                    (
                        status,
                        json.dumps(result or {}, ensure_ascii=False),
                        error_code or None,
                        mysql_datetime(completed_at),
                        operation_id,
                    ),
                )
                cur.execute(OPERATION_SELECT + " WHERE id=%s", (operation_id,))
                row = cur.fetchone()
            conn.commit()
        return operation_from_row(row) if row else {}

    with JSON_STORE_LOCK:
        path = mobile_sync_operations_json_path()
        records = load_json_records(path)
        updated: dict[str, Any] = {}
        for index, item in enumerate(records):
            if item.get("id") != operation_id:
                continue
            updated = {
                **item,
                "status": status,
                "result": dict(result or {}),
                "errorCode": error_code,
                "completedAt": completed_at,
            }
            records[index] = updated
            break
        save_json_records(path, records)
    return updated


def list_operations(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    OPERATION_SELECT
                    + " WHERE user_id=%s ORDER BY received_at DESC LIMIT %s",
                    (user_id, limit),
                )
                return [operation_from_row(row) for row in cur.fetchall()]
    records = [
        item
        for item in load_json_records(mobile_sync_operations_json_path())
        if item.get("userId") == user_id
    ]
    return sorted(records, key=lambda item: str(item.get("receivedAt") or ""), reverse=True)[:limit]


def operation_ledger(
    *, q: str = "", status: str = "", user_id: str = "", limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    if use_mysql():
        clauses: list[str] = []
        params: list[Any] = []
        if q:
            clauses.append("(client_operation_id LIKE %s OR entity_id LIKE %s OR action LIKE %s)")
            params.extend([f"%{q}%"] * 3)
        if status:
            clauses.append("status=%s")
            params.append(status)
        if user_id:
            clauses.append("user_id=%s")
            params.append(user_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM mobile_sync_operations{where}", tuple(params))
                total = int(cur.fetchone()[0])
                cur.execute(
                    OPERATION_SELECT + where + " ORDER BY received_at DESC LIMIT %s OFFSET %s",
                    tuple([*params, limit, offset]),
                )
                items = [operation_from_row(row) for row in cur.fetchall()]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    lowered = q.casefold().strip()
    records = load_json_records(mobile_sync_operations_json_path())
    records = [
        item for item in records
        if (not status or item.get("status") == status)
        and (not user_id or item.get("userId") == user_id)
        and (not lowered or lowered in " ".join(str(item.get(key) or "") for key in ("clientOperationId", "entityId", "action")).casefold())
    ]
    records.sort(key=lambda item: str(item.get("receivedAt") or ""), reverse=True)
    return {"items": records[offset:offset + limit], "total": len(records), "limit": limit, "offset": offset}


def save_track(record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT IGNORE INTO mobile_tracks
                       (id,client_track_id,user_id,task_type,task_id,status,points_json,
                        point_count,distance_meters,started_at,ended_at,created_at,deleted_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL)""",
                    (record["id"], record["clientTrackId"], record["userId"], record["taskType"],
                     record["taskId"], record["status"], json.dumps(record["points"], ensure_ascii=False),
                     record["pointCount"], record["distanceMeters"], mysql_datetime(record["startedAt"]),
                     mysql_datetime(record["endedAt"]), mysql_datetime(record["createdAt"])),
                )
                created = cur.rowcount == 1
                cur.execute(
                    """SELECT id,client_track_id,user_id,task_type,task_id,status,points_json,
                              point_count,distance_meters,started_at,ended_at,created_at,deleted_at
                       FROM mobile_tracks WHERE user_id=%s AND client_track_id=%s""",
                    (record["userId"], record["clientTrackId"]),
                )
                row = cur.fetchone()
            conn.commit()
        return track_from_row(row), created
    with JSON_STORE_LOCK:
        path = mobile_tracks_json_path()
        records = load_json_records(path)
        existing = next((item for item in records if item.get("userId") == record["userId"] and item.get("clientTrackId") == record["clientTrackId"]), None)
        if existing:
            return existing, False
        records.append(record)
        save_json_records(path, records)
    return record, True


def track_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "clientTrackId": str(row[1]), "userId": str(row[2]),
        "taskType": str(row[3]), "taskId": str(row[4]), "status": str(row[5]),
        "points": json_value(row[6], []), "pointCount": int(row[7]),
        "distanceMeters": float(row[8]), "startedAt": iso_value(row[9]),
        "endedAt": iso_value(row[10]), "createdAt": iso_value(row[11]),
        "deletedAt": iso_value(row[12]),
    }


def track_ledger(*, q: str = "", status: str = "", user_id: str = "", include_deleted: bool = False, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    if use_mysql():
        clauses = [] if include_deleted else ["deleted_at IS NULL"]
        params: list[Any] = []
        if q:
            clauses.append("(client_track_id LIKE %s OR task_id LIKE %s)")
            params.extend([f"%{q}%"] * 2)
        if status:
            clauses.append("status=%s"); params.append(status)
        if user_id:
            clauses.append("user_id=%s"); params.append(user_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        select = """SELECT id,client_track_id,user_id,task_type,task_id,status,points_json,
                            point_count,distance_meters,started_at,ended_at,created_at,deleted_at FROM mobile_tracks"""
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM mobile_tracks{where}", tuple(params)); total = int(cur.fetchone()[0])
                cur.execute(select + where + " ORDER BY created_at DESC LIMIT %s OFFSET %s", tuple([*params, limit, offset]))
                items = [track_from_row(row) for row in cur.fetchall()]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    lowered = q.casefold().strip()
    items = [item for item in load_json_records(mobile_tracks_json_path()) if (include_deleted or not item.get("deletedAt")) and (not status or item.get("status") == status) and (not user_id or item.get("userId") == user_id) and (not lowered or lowered in f"{item.get('clientTrackId', '')} {item.get('taskId', '')}".casefold())]
    items.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return {"items": items[offset:offset + limit], "total": len(items), "limit": limit, "offset": offset}


def list_evidence(*, q: str = "", user_id: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    if use_mysql():
        clauses = ["deleted_at IS NULL"]
        params: list[Any] = []
        if q:
            clauses.append("(evidence_no LIKE %s OR file_name LIKE %s OR task_id LIKE %s)"); params.extend([f"%{q}%"] * 3)
        if user_id:
            clauses.append("user_id=%s"); params.append(user_id)
        where = " WHERE " + " AND ".join(clauses)
        select = """SELECT id,evidence_no,user_id,task_type,task_id,file_name,stored_name,
                            content_type,byte_size,sha256,captured_at,longitude,latitude,created_at
                     FROM mobile_evidence"""
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM mobile_evidence{where}", tuple(params)); total = int(cur.fetchone()[0])
                cur.execute(select + where + " ORDER BY created_at DESC LIMIT %s OFFSET %s", tuple([*params, limit, offset]))
                items = [evidence_from_row(row) for row in cur.fetchall()]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    lowered = q.casefold().strip()
    items = [item for item in load_json_records(mobile_evidence_json_path()) if not item.get("deletedAt") and (not user_id or item.get("userId") == user_id) and (not lowered or lowered in f"{item.get('evidenceNo', '')} {item.get('fileName', '')} {item.get('taskId', '')}".casefold())]
    items.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return {"items": items[offset:offset + limit], "total": len(items), "limit": limit, "offset": offset}


def evidence_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]), "evidenceNo": str(row[1]), "userId": str(row[2]),
        "taskType": str(row[3] or ""), "taskId": str(row[4] or ""), "fileName": str(row[5]),
        "storedName": str(row[6]), "contentType": str(row[7]), "byteSize": int(row[8]),
        "sha256": str(row[9]), "capturedAt": iso_value(row[10]),
        "longitude": float(row[11]) if row[11] is not None else None,
        "latitude": float(row[12]) if row[12] is not None else None, "createdAt": iso_value(row[13]),
        "url": f"/api/v2/mobile/evidence/{row[0]}/content",
    }


def upload_session_by_id(session_id: str) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT id,user_id,task_type,task_id,file_name,content_type,total_bytes,total_chunks,
                                      expected_sha256,received_chunks_json,status,evidence_id,created_at,updated_at,expires_at,deleted_at
                               FROM mobile_upload_sessions WHERE id=%s""", (session_id,))
                row = cur.fetchone()
        return upload_session_from_row(row) if row else None
    return next((item for item in load_json_records(mobile_upload_sessions_json_path()) if item.get("id") == session_id), None)


def upload_session_ledger(
    *,
    q: str = "",
    status: str = "",
    user_id: str = "",
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    if use_mysql():
        clauses = [] if include_deleted else ["deleted_at IS NULL"]
        params: list[Any] = []
        if q:
            clauses.append("(file_name LIKE %s OR task_id LIKE %s OR id LIKE %s)")
            params.extend([f"%{q}%"] * 3)
        if status:
            clauses.append("status=%s")
            params.append(status)
        if user_id:
            clauses.append("user_id=%s")
            params.append(user_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        select = """SELECT id,user_id,task_type,task_id,file_name,content_type,total_bytes,total_chunks,
                            expected_sha256,received_chunks_json,status,evidence_id,created_at,updated_at,expires_at,deleted_at
                     FROM mobile_upload_sessions"""
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM mobile_upload_sessions{where}", tuple(params))
                total = int(cur.fetchone()[0])
                cur.execute(
                    select + where + " ORDER BY updated_at DESC LIMIT %s OFFSET %s",
                    tuple([*params, limit, offset]),
                )
                items = [upload_session_from_row(row) for row in cur.fetchall()]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    lowered = q.casefold().strip()
    items = [
        item
        for item in load_json_records(mobile_upload_sessions_json_path())
        if (include_deleted or not item.get("deletedAt"))
        and (not status or item.get("status") == status)
        and (not user_id or item.get("userId") == user_id)
        and (
            not lowered
            or lowered
            in f"{item.get('id', '')} {item.get('fileName', '')} {item.get('taskId', '')}".casefold()
        )
    ]
    items.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return {
        "items": items[offset:offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


def upload_session_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {"id": str(row[0]), "userId": str(row[1]), "taskType": str(row[2] or ""), "taskId": str(row[3] or ""), "fileName": str(row[4]), "contentType": str(row[5]), "totalBytes": int(row[6]), "totalChunks": int(row[7]), "expectedSha256": str(row[8] or ""), "receivedChunks": json_value(row[9], []), "status": str(row[10]), "evidenceId": str(row[11] or ""), "createdAt": iso_value(row[12]), "updatedAt": iso_value(row[13]), "expiresAt": iso_value(row[14]), "deletedAt": iso_value(row[15])}


def save_upload_session(record: dict[str, Any]) -> dict[str, Any]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO mobile_upload_sessions
                    (id,user_id,task_type,task_id,file_name,content_type,total_bytes,total_chunks,expected_sha256,
                     received_chunks_json,status,evidence_id,created_at,updated_at,expires_at,deleted_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,NULL)""",
                    (record["id"], record["userId"], record.get("taskType") or None, record.get("taskId") or None,
                     record["fileName"], record["contentType"], record["totalBytes"], record["totalChunks"],
                     record.get("expectedSha256") or None, json.dumps(record.get("receivedChunks") or []), record["status"],
                     mysql_datetime(record["createdAt"]), mysql_datetime(record["updatedAt"]), mysql_datetime(record["expiresAt"])))
            conn.commit()
        return record
    with JSON_STORE_LOCK:
        path = mobile_upload_sessions_json_path(); records = load_json_records(path); records.append(record); save_json_records(path, records)
    return record


def update_upload_session(session_id: str, **changes: Any) -> dict[str, Any]:
    current = upload_session_by_id(session_id)
    if not current:
        return {}
    updated = {**current, **changes, "updatedAt": utc_now()}
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE mobile_upload_sessions SET received_chunks_json=%s,status=%s,evidence_id=%s,
                               updated_at=%s,deleted_at=%s WHERE id=%s""",
                            (json.dumps(updated.get("receivedChunks") or []), updated["status"], updated.get("evidenceId") or None,
                             mysql_datetime(updated["updatedAt"]), mysql_datetime(updated.get("deletedAt")), session_id))
            conn.commit()
        return updated
    with JSON_STORE_LOCK:
        path = mobile_upload_sessions_json_path(); records = load_json_records(path)
        records = [updated if item.get("id") == session_id else item for item in records]; save_json_records(path, records)
    return updated


def save_evidence(record: dict[str, Any]) -> dict[str, Any]:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO mobile_evidence (
                           id,evidence_no,user_id,task_type,task_id,file_name,stored_name,
                           content_type,byte_size,sha256,captured_at,longitude,latitude,created_at
                       ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        record["id"],
                        record["evidenceNo"],
                        record["userId"],
                        record.get("taskType") or None,
                        record.get("taskId") or None,
                        record["fileName"],
                        record["storedName"],
                        record["contentType"],
                        record["byteSize"],
                        record["sha256"],
                        mysql_datetime(record.get("capturedAt")),
                        record.get("longitude"),
                        record.get("latitude"),
                        mysql_datetime(record["createdAt"]),
                    ),
                )
            conn.commit()
        return record
    with JSON_STORE_LOCK:
        path = mobile_evidence_json_path()
        records = load_json_records(path)
        records.append(record)
        save_json_records(path, records)
    return record


def evidence_by_id(evidence_id: str) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id,evidence_no,user_id,task_type,task_id,file_name,stored_name,
                              content_type,byte_size,sha256,captured_at,longitude,latitude,created_at
                       FROM mobile_evidence WHERE id=%s""",
                    (evidence_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]), "evidenceNo": str(row[1]), "userId": str(row[2]),
            "taskType": str(row[3] or ""), "taskId": str(row[4] or ""),
            "fileName": str(row[5]), "storedName": str(row[6]), "contentType": str(row[7]),
            "byteSize": int(row[8]), "sha256": str(row[9]), "capturedAt": iso_value(row[10]),
            "longitude": float(row[11]) if row[11] is not None else None,
            "latitude": float(row[12]) if row[12] is not None else None,
            "createdAt": iso_value(row[13]),
        }
    return next(
        (item for item in load_json_records(mobile_evidence_json_path()) if item.get("id") == evidence_id),
        None,
    )
