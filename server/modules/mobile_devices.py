from __future__ import annotations

from typing import Any

from .database import JSON_STORE_LOCK, load_json_records, mobile_devices_json_path, save_json_records


def list_mobile_devices(q: str = "", status: str = "", user_id: str = "") -> list[dict[str, Any]]:
    needle = q.strip().casefold()
    records = load_json_records(mobile_devices_json_path())
    return sorted(
        [
            item for item in records
            if (not status or item.get("status") == status)
            and (not user_id or item.get("userId") == user_id)
            and (not needle or needle in " ".join(str(item.get(key) or "") for key in ("deviceId", "deviceName", "userId", "platform", "appVersion")).casefold())
        ],
        key=lambda item: str(item.get("lastSeenAt") or ""),
        reverse=True,
    )


def mobile_device_by_id(device_id: str) -> dict[str, Any] | None:
    return next((item for item in load_json_records(mobile_devices_json_path()) if item.get("deviceId") == device_id), None)


def upsert_mobile_device(record: dict[str, Any]) -> dict[str, Any]:
    path = mobile_devices_json_path()
    with JSON_STORE_LOCK:
        records = load_json_records(path)
        existing = next((item for item in records if item.get("deviceId") == record["deviceId"]), None)
        if existing:
            existing.update(record)
            saved = existing
        else:
            records.append(record)
            saved = record
        save_json_records(path, records)
    return dict(saved)


def revoke_mobile_device(device_id: str, revoked_at: str, revoked_by: str, note: str) -> dict[str, Any] | None:
    path = mobile_devices_json_path()
    with JSON_STORE_LOCK:
        records = load_json_records(path)
        target = next((item for item in records if item.get("deviceId") == device_id), None)
        if not target:
            return None
        target.update({"status": "revoked", "pushToken": "", "revokedAt": revoked_at, "revokedBy": revoked_by, "revocationNote": note})
        save_json_records(path, records)
        return dict(target)


def restore_mobile_device(device_id: str, restored_at: str, restored_by: str) -> dict[str, Any] | None:
    path = mobile_devices_json_path()
    with JSON_STORE_LOCK:
        records = load_json_records(path)
        target = next((item for item in records if item.get("deviceId") == device_id), None)
        if not target:
            return None
        target.update({"status": "active", "restoredAt": restored_at, "restoredBy": restored_by, "revokedAt": "", "revokedBy": "", "revocationNote": ""})
        save_json_records(path, records)
        return dict(target)
