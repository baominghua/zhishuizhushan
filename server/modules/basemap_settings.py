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


def runtime_basemap_settings() -> dict[str, str]:
    stored = _load_file(basemap_settings_json_path())
    source = stored if stored is not None else _environment_settings()
    return {
        "serverKey": str(source.get("serverKey") or "").strip(),
        "proxyBaseUrl": str(source.get("proxyBaseUrl") or "").strip().rstrip("/"),
        "referer": str(source.get("referer") or "").strip(),
    }


def public_basemap_settings() -> dict[str, Any]:
    settings = runtime_basemap_settings()
    key = settings["serverKey"]
    return {
        "provider": "tianditu",
        "available": bool(key or settings["proxyBaseUrl"]),
        "hasServerKey": bool(key),
        "serverKeyMasked": f"{'*' * 8}{key[-4:]}" if key else "",
        "proxyBaseUrl": settings["proxyBaseUrl"],
        "referer": settings["referer"],
        "source": "stored" if basemap_settings_json_path().exists() else "environment",
    }


def save_basemap_settings(*, server_key: str, proxy_base_url: str, referer: str) -> dict[str, Any]:
    path = basemap_settings_json_path()
    record = {
        "serverKey": server_key.strip(),
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
