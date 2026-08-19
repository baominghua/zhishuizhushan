from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any

from .database import basemap_settings_json_path


SETTINGS_LOCK = RLock()


def _environment_settings() -> dict[str, str]:
    return {
        "serverKey": os.environ.get("REMOTE_SENSING_TIANDITU_TK", "").strip(),
        "webKey": os.environ.get("REMOTE_SENSING_TIANDITU_WEB_TK", "").strip(),
        "androidKey": os.environ.get("REMOTE_SENSING_TIANDITU_ANDROID_TK", "").strip(),
        "iosKey": os.environ.get("REMOTE_SENSING_TIANDITU_IOS_TK", "").strip(),
        "webDirectEnabled": os.environ.get("REMOTE_SENSING_TIANDITU_WEB_DIRECT", "0").strip(),
        "proxyBaseUrl": os.environ.get("REMOTE_SENSING_TIANDITU_PROXY_BASE_URL", "").strip().rstrip("/"),
        "referer": os.environ.get("REMOTE_SENSING_TIANDITU_REFERER", "").strip(),
    }


def _load_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def runtime_basemap_settings() -> dict[str, Any]:
    stored = _load_file(basemap_settings_json_path())
    source = stored if stored is not None else _environment_settings()
    return {
        "serverKey": str(source.get("serverKey") or "").strip(),
        "webKey": str(source.get("webKey") or "").strip(),
        "androidKey": str(source.get("androidKey") or "").strip(),
        "iosKey": str(source.get("iosKey") or "").strip(),
        "webDirectEnabled": str(source.get("webDirectEnabled") or "").strip().lower()
        in {"1", "true", "yes", "on"},
        "proxyBaseUrl": str(source.get("proxyBaseUrl") or "").strip().rstrip("/"),
        "referer": str(source.get("referer") or "").strip(),
    }


def public_basemap_settings() -> dict[str, Any]:
    settings = runtime_basemap_settings()
    def credential_status(name: str) -> tuple[bool, str]:
        key = str(settings[name])
        return bool(key), f"{'*' * 8}{key[-4:]}" if key else ""

    has_server_key, server_key_masked = credential_status("serverKey")
    has_web_key, web_key_masked = credential_status("webKey")
    has_android_key, android_key_masked = credential_status("androidKey")
    has_ios_key, ios_key_masked = credential_status("iosKey")
    return {
        "provider": "tianditu",
        "available": bool(
            has_server_key
            or settings["proxyBaseUrl"]
            or (has_web_key and settings["webDirectEnabled"])
        ),
        "hasServerKey": has_server_key,
        "serverKeyMasked": server_key_masked,
        "hasWebKey": has_web_key,
        "webKeyMasked": web_key_masked,
        "hasAndroidKey": has_android_key,
        "androidKeyMasked": android_key_masked,
        "hasIosKey": has_ios_key,
        "iosKeyMasked": ios_key_masked,
        "webDirectEnabled": bool(settings["webDirectEnabled"] and has_web_key),
        "proxyBaseUrl": settings["proxyBaseUrl"],
        "referer": settings["referer"],
        "source": "stored" if basemap_settings_json_path().exists() else "environment",
    }


def save_basemap_settings(
    *,
    server_key: str,
    web_key: str,
    android_key: str,
    ios_key: str,
    web_direct_enabled: bool,
    proxy_base_url: str,
    referer: str,
) -> dict[str, Any]:
    path = basemap_settings_json_path()
    record = {
        "serverKey": server_key.strip(),
        "webKey": web_key.strip(),
        "androidKey": android_key.strip(),
        "iosKey": ios_key.strip(),
        "webDirectEnabled": bool(web_direct_enabled),
        "proxyBaseUrl": proxy_base_url.strip().rstrip("/"),
        "referer": referer.strip(),
    }
    with SETTINGS_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return public_basemap_settings()
