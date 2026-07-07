from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class PlatformSettings:
    data_dir: Path
    storage_backend: str
    database_url: str
    auth_required: bool
    cors_origins: list[str]


@lru_cache(maxsize=1)
def get_settings() -> PlatformSettings:
    data_dir = Path(
        os.environ.get("REMOTE_SENSING_DATA_DIR", str(ROOT_DIR / "data" / "remote-sensing"))
    ).expanduser().resolve()
    database_url = (
        os.environ.get("SMART_BAMBOO_DATABASE_URL")
        or os.environ.get("REMOTE_SENSING_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    storage_backend = os.environ.get("SMART_BAMBOO_STORAGE_BACKEND", "").strip().lower()
    if not storage_backend:
        storage_backend = "postgis" if database_url else "json"
    return PlatformSettings(
        data_dir=data_dir,
        storage_backend=storage_backend,
        database_url=database_url,
        auth_required=env_bool("REMOTE_SENSING_AUTH_REQUIRED", False),
        cors_origins=env_list("REMOTE_SENSING_CORS_ORIGINS", ["*"]),
    )
