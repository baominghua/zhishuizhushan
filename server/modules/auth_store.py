from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

from . import database
from .database import (
    admin_credentials_json_path,
    admin_sessions_json_path,
    load_json_records,
    mysql_connect,
    use_mysql,
)


SESSION_LIFETIME = timedelta(hours=24)
FAILED_LOGIN_LIMIT = 5
LOCKOUT_DURATION = timedelta(minutes=15)


class CredentialRecord(TypedDict):
    id: str
    userId: str
    passwordHash: str
    passwordChangedAt: str | None
    mustChangePassword: bool
    failedLoginCount: int
    lockedUntil: str | None
    credentialVersion: int
    createdAt: str
    updatedAt: str


class SessionRecord(TypedDict):
    id: str
    userId: str
    tokenHash: str
    csrfTokenHash: str
    credentialVersion: int
    ipAddress: str | None
    userAgent: str | None
    issuedAt: str
    lastSeenAt: str
    expiresAt: str
    revokedAt: str | None


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def mysql_datetime(value: str | None) -> datetime | None:
    parsed = parse_utc(value)
    return parsed.replace(tzinfo=None) if parsed is not None else None


def mysql_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return iso_utc(parse_utc(value) or utc_now())
    if isinstance(value, datetime):
        return iso_utc(value)
    raise TypeError(f"Unsupported MySQL timestamp value: {type(value)!r}")


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def save_json_records(path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def new_credential(user_id: str, password_hash: str) -> CredentialRecord:
    now = iso_utc(utc_now())
    return {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "passwordHash": password_hash,
        "passwordChangedAt": now,
        "mustChangePassword": True,
        "failedLoginCount": 0,
        "lockedUntil": None,
        "credentialVersion": 1,
        "createdAt": now,
        "updatedAt": now,
    }


def normalize_credential(source: dict[str, Any]) -> CredentialRecord:
    return {
        "id": str(source["id"]),
        "userId": str(source["userId"]),
        "passwordHash": str(source["passwordHash"]),
        "passwordChangedAt": source.get("passwordChangedAt"),
        "mustChangePassword": bool(source.get("mustChangePassword", True)),
        "failedLoginCount": int(source.get("failedLoginCount", 0)),
        "lockedUntil": source.get("lockedUntil"),
        "credentialVersion": int(source.get("credentialVersion", 1)),
        "createdAt": str(source["createdAt"]),
        "updatedAt": str(source["updatedAt"]),
    }


def credential_from_mysql(row: tuple[Any, ...]) -> CredentialRecord:
    return {
        "id": str(row[0]),
        "userId": str(row[1]),
        "passwordHash": str(row[2]),
        "passwordChangedAt": mysql_iso(row[3]),
        "mustChangePassword": bool(row[4]),
        "failedLoginCount": int(row[5]),
        "lockedUntil": mysql_iso(row[6]),
        "credentialVersion": int(row[7]),
        "createdAt": str(mysql_iso(row[8])),
        "updatedAt": str(mysql_iso(row[9])),
    }


def mysql_credential_for_user(cur: Any, user_id: str, *, lock: bool = False) -> CredentialRecord | None:
    sql = (
        "SELECT id, admin_user_id, password_hash, password_changed_at, "
        "must_change_password, failed_login_count, locked_until, credential_version, "
        "created_at, updated_at FROM admin_user_credentials WHERE admin_user_id = %s"
    )
    if lock:
        sql += " FOR UPDATE"
    cur.execute(sql, (user_id,))
    row = cur.fetchone()
    return credential_from_mysql(row) if row else None


def write_mysql_credential(cur: Any, normalized: CredentialRecord) -> None:
    cur.execute(
        """
        INSERT INTO admin_user_credentials (
            id, admin_user_id, password_hash, password_changed_at, must_change_password,
            failed_login_count, locked_until, credential_version, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            password_hash = VALUES(password_hash),
            password_changed_at = VALUES(password_changed_at),
            must_change_password = VALUES(must_change_password),
            failed_login_count = VALUES(failed_login_count),
            locked_until = VALUES(locked_until),
            credential_version = VALUES(credential_version),
            updated_at = VALUES(updated_at)
        """,
        (
            normalized["id"], normalized["userId"], normalized["passwordHash"],
            mysql_datetime(normalized["passwordChangedAt"]), normalized["mustChangePassword"],
            normalized["failedLoginCount"], mysql_datetime(normalized["lockedUntil"]),
            normalized["credentialVersion"], mysql_datetime(normalized["createdAt"]),
            mysql_datetime(normalized["updatedAt"]),
        ),
    )


def credential_for_user(user_id: str) -> CredentialRecord | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                return mysql_credential_for_user(cur, user_id)
    for record in load_json_records(admin_credentials_json_path()):
        if str(record.get("userId")) == user_id:
            return normalize_credential(record)
    return None


def save_credential(record: CredentialRecord) -> None:
    normalized = normalize_credential(record)
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                write_mysql_credential(cur, normalized)
            conn.commit()
        return
    with database.JSON_STORE_LOCK:
        records = load_json_records(admin_credentials_json_path())
        for index, existing in enumerate(records):
            if str(existing.get("userId")) == normalized["userId"]:
                existing_credential = normalize_credential(existing)
                normalized["id"] = existing_credential["id"]
                normalized["createdAt"] = existing_credential["createdAt"]
                records[index] = normalized
                break
        else:
            records.append(normalized)
        save_json_records(admin_credentials_json_path(), records)


def record_failed_login(user_id: str, now: datetime) -> CredentialRecord:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                credential = mysql_credential_for_user(cur, user_id, lock=True)
                if credential is None:
                    raise KeyError(f"Credential not found for user {user_id}")
                credential["failedLoginCount"] += 1
                if credential["failedLoginCount"] >= FAILED_LOGIN_LIMIT:
                    credential["lockedUntil"] = iso_utc(now + LOCKOUT_DURATION)
                credential["updatedAt"] = iso_utc(now)
                write_mysql_credential(cur, credential)
            conn.commit()
        return credential
    with database.JSON_STORE_LOCK:
        credential = credential_for_user(user_id)
        if credential is None:
            raise KeyError(f"Credential not found for user {user_id}")
        credential["failedLoginCount"] += 1
        if credential["failedLoginCount"] >= FAILED_LOGIN_LIMIT:
            credential["lockedUntil"] = iso_utc(now + LOCKOUT_DURATION)
        credential["updatedAt"] = iso_utc(now)
        save_credential(credential)
        return credential


def reset_failed_login(user_id: str) -> CredentialRecord:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                credential = mysql_credential_for_user(cur, user_id, lock=True)
                if credential is None:
                    raise KeyError(f"Credential not found for user {user_id}")
                credential["failedLoginCount"] = 0
                credential["lockedUntil"] = None
                credential["updatedAt"] = iso_utc(utc_now())
                write_mysql_credential(cur, credential)
            conn.commit()
        return credential
    with database.JSON_STORE_LOCK:
        credential = credential_for_user(user_id)
        if credential is None:
            raise KeyError(f"Credential not found for user {user_id}")
        credential["failedLoginCount"] = 0
        credential["lockedUntil"] = None
        credential["updatedAt"] = iso_utc(utc_now())
        save_credential(credential)
        return credential


def normalize_session(source: dict[str, Any]) -> SessionRecord:
    return {
        "id": str(source["id"]),
        "userId": str(source["userId"]),
        "tokenHash": str(source["tokenHash"]),
        "csrfTokenHash": str(source["csrfTokenHash"]),
        "credentialVersion": int(source["credentialVersion"]),
        "ipAddress": source.get("ipAddress"),
        "userAgent": source.get("userAgent"),
        "issuedAt": str(source["issuedAt"]),
        "lastSeenAt": str(source["lastSeenAt"]),
        "expiresAt": str(source["expiresAt"]),
        "revokedAt": source.get("revokedAt"),
    }


def session_from_mysql(row: tuple[Any, ...]) -> SessionRecord:
    return {
        "id": str(row[0]),
        "userId": str(row[1]),
        "tokenHash": str(row[2]),
        "csrfTokenHash": str(row[3]),
        "credentialVersion": int(row[4]),
        "ipAddress": row[5],
        "userAgent": row[6],
        "issuedAt": str(mysql_iso(row[7])),
        "lastSeenAt": str(mysql_iso(row[8])),
        "expiresAt": str(mysql_iso(row[9])),
        "revokedAt": mysql_iso(row[10]),
    }


def save_session(record: SessionRecord) -> None:
    normalized = normalize_session(record)
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_sessions (
                        id, admin_user_id, token_hash, csrf_token_hash, credential_version, ip_address,
                        user_agent, issued_at, last_seen_at, expires_at, revoked_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        credential_version = VALUES(credential_version), ip_address = VALUES(ip_address),
                        user_agent = VALUES(user_agent), last_seen_at = VALUES(last_seen_at),
                        expires_at = VALUES(expires_at), revoked_at = VALUES(revoked_at)
                    """,
                    (
                        normalized["id"], normalized["userId"], normalized["tokenHash"], normalized["csrfTokenHash"],
                        normalized["credentialVersion"], normalized["ipAddress"], normalized["userAgent"],
                        mysql_datetime(normalized["issuedAt"]), mysql_datetime(normalized["lastSeenAt"]),
                        mysql_datetime(normalized["expiresAt"]), mysql_datetime(normalized["revokedAt"]),
                    ),
                )
            conn.commit()
        return
    with database.JSON_STORE_LOCK:
        records = load_json_records(admin_sessions_json_path())
        records = [item for item in records if str(item.get("id")) != normalized["id"]]
        records.append(normalized)
        save_json_records(admin_sessions_json_path(), records)


def create_session(
    user_id: str,
    credential_version: int,
    now: datetime,
    ip_address: str,
    user_agent: str,
) -> tuple[str, str, SessionRecord]:
    raw_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    issued_at = iso_utc(now)
    record: SessionRecord = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "tokenHash": token_hash(raw_token),
        "csrfTokenHash": token_hash(csrf_token),
        "credentialVersion": credential_version,
        "ipAddress": ip_address,
        "userAgent": user_agent,
        "issuedAt": issued_at,
        "lastSeenAt": issued_at,
        "expiresAt": iso_utc(now + SESSION_LIFETIME),
        "revokedAt": None,
    }
    save_session(record)
    return raw_token, csrf_token, record


def session_for_token(raw_token: str, now: datetime) -> SessionRecord | None:
    hashed_token = token_hash(raw_token)
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, admin_user_id, token_hash, csrf_token_hash, credential_version, ip_address, "
                    "user_agent, issued_at, last_seen_at, expires_at, revoked_at "
                    "FROM admin_sessions WHERE token_hash = %s",
                    (hashed_token,),
                )
                row = cur.fetchone()
        record = session_from_mysql(row) if row else None
    else:
        record = next(
            (
                normalize_session(item)
                for item in load_json_records(admin_sessions_json_path())
                if item.get("tokenHash") == hashed_token
            ),
            None,
        )
    if record is None or record["revokedAt"] is not None:
        return None
    expires_at = parse_utc(record["expiresAt"])
    if expires_at is None or expires_at <= now.astimezone(UTC):
        return None
    return record


def revoke_session(raw_token: str) -> None:
    hashed_token = token_hash(raw_token)
    revoked_at = iso_utc(utc_now())
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE admin_sessions SET revoked_at = %s WHERE token_hash = %s AND revoked_at IS NULL",
                    (mysql_datetime(revoked_at), hashed_token),
                )
            conn.commit()
        return
    with database.JSON_STORE_LOCK:
        records = load_json_records(admin_sessions_json_path())
        for record in records:
            if record.get("tokenHash") == hashed_token and record.get("revokedAt") is None:
                record["revokedAt"] = revoked_at
                save_json_records(admin_sessions_json_path(), records)
                return


def revoke_user_sessions(user_id: str, except_session_id: str | None = None) -> int:
    revoked_at = iso_utc(utc_now())
    if use_mysql():
        where = "admin_user_id = %s AND revoked_at IS NULL"
        params: list[Any] = [mysql_datetime(revoked_at), user_id]
        if except_session_id is not None:
            where += " AND id <> %s"
            params.append(except_session_id)
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE admin_sessions SET revoked_at = %s WHERE {where}", tuple(params))
                revoked = int(cur.rowcount)
            conn.commit()
        return revoked

    with database.JSON_STORE_LOCK:
        records = load_json_records(admin_sessions_json_path())
        revoked = 0
        for record in records:
            if (
                str(record.get("userId")) == user_id
                and record.get("revokedAt") is None
                and str(record.get("id")) != except_session_id
            ):
                record["revokedAt"] = revoked_at
                revoked += 1
        if revoked:
            save_json_records(admin_sessions_json_path(), records)
        return revoked


def revoke_user_sessions_mysql(cur: Any, user_id: str, except_session_id: str | None = None) -> int:
    revoked_at = iso_utc(utc_now())
    where = "admin_user_id = %s AND revoked_at IS NULL"
    params: list[Any] = [mysql_datetime(revoked_at), user_id]
    if except_session_id is not None:
        where += " AND id <> %s"
        params.append(except_session_id)
    cur.execute(f"UPDATE admin_sessions SET revoked_at = %s WHERE {where}", tuple(params))
    return int(cur.rowcount)
