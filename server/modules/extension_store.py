from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from .database import (
    JSON_STORE_LOCK,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
    v2_extension_json_path,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def _decode(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    return dict(json.loads(str(value or "{}")))


def _mysql_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def list_extension_records(
    collection: str,
    *,
    include_deleted: bool = False,
    area_codes: set[str] | None = None,
) -> list[dict[str, Any]]:
    if use_mysql():
        clauses = ["collection_key=%s"]
        params: list[Any] = [collection]
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        if area_codes and "*" not in area_codes:
            placeholders = ",".join(["%s"] * len(area_codes))
            clauses.append(f"(area_code IS NULL OR area_code='' OR area_code IN ({placeholders}))")
            params.extend(sorted(area_codes))
        with mysql_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT record_json FROM v2_extension_records WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY updated_at DESC",
                    tuple(params),
                )
                return [_decode(row[0]) for row in cursor.fetchall()]
    records = load_json_records(v2_extension_json_path(collection))
    if not include_deleted:
        records = [record for record in records if not record.get("deletedAt")]
    if area_codes and "*" not in area_codes:
        records = [
            record for record in records
            if not record.get("areaCode") or str(record.get("areaCode")) in area_codes
        ]
    return sorted(records, key=lambda record: str(record.get("updatedAt") or ""), reverse=True)


def extension_record_by_id(collection: str, record_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    return next(
        (
            record for record in list_extension_records(collection, include_deleted=include_deleted)
            if str(record.get("id")) == str(record_id)
        ),
        None,
    )


def extension_record_by_idempotency_key(
    collection: str, key: str, *, area_codes: set[str] | None = None,
) -> dict[str, Any] | None:
    normalized = str(key or "").strip()
    if not normalized:
        return None
    return next(
        (
            record for record in list_extension_records(collection, area_codes=area_codes)
            if str(record.get("idempotencyKey") or "") == normalized
        ),
        None,
    )


def save_extension_record(collection: str, record: dict[str, Any], *, create: bool) -> dict[str, Any]:
    stored = dict(record)
    if use_mysql():
        payload = json.dumps(stored, ensure_ascii=False, default=_json_default)
        with mysql_connect() as connection:
            with connection.cursor() as cursor:
                if create:
                    cursor.execute(
                        """INSERT INTO v2_extension_records
                           (collection_key,id,area_code,version_no,idempotency_key,record_json,created_at,updated_at,deleted_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            collection, stored["id"], stored.get("areaCode") or None,
                            int(stored.get("version") or 1), stored.get("idempotencyKey") or None,
                            payload, _mysql_datetime(stored.get("createdAt")),
                            _mysql_datetime(stored.get("updatedAt")), _mysql_datetime(stored.get("deletedAt")),
                        ),
                    )
                else:
                    cursor.execute(
                        """UPDATE v2_extension_records
                           SET area_code=%s,version_no=%s,idempotency_key=%s,record_json=%s,updated_at=%s,deleted_at=%s
                           WHERE collection_key=%s AND id=%s""",
                        (
                            stored.get("areaCode") or None, int(stored.get("version") or 1),
                            stored.get("idempotencyKey") or None, payload,
                            _mysql_datetime(stored.get("updatedAt")), _mysql_datetime(stored.get("deletedAt")),
                            collection, stored["id"],
                        ),
                    )
            connection.commit()
        return stored
    path = v2_extension_json_path(collection)
    with JSON_STORE_LOCK:
        records = load_json_records(path)
        if create:
            records.append(stored)
        else:
            replaced = False
            next_records = []
            for item in records:
                if str(item.get("id")) == str(stored["id"]):
                    next_records.append(stored)
                    replaced = True
                else:
                    next_records.append(item)
            records = next_records if replaced else [*next_records, stored]
        save_json_records(path, records)
    return stored


def soft_delete_extension_record(collection: str, record_id: str, *, expected_version: int | None = None) -> dict[str, Any] | None:
    record = extension_record_by_id(collection, record_id)
    if not record:
        return None
    if expected_version is not None and int(record.get("version") or 1) != expected_version:
        raise ValueError("version_conflict")
    record["deletedAt"] = utc_now()
    record["updatedAt"] = record["deletedAt"]
    record["version"] = int(record.get("version") or 1) + 1
    return save_extension_record(collection, record, create=False)
