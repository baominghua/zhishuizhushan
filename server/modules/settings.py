from __future__ import annotations

import os
import json
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
PRODUCTION_MODES = {"prod", "production"}
PLACEHOLDER_PASSWORDS = {
    "change-me",
    "changeme",
    "password",
    "root",
    "smart_bamboo_dev",
    "smart_bamboo_root_dev",
}


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


def production_configuration_issues(environ: Mapping[str, str] | None = None) -> list[str]:
    values = environ if environ is not None else os.environ
    mode = str(values.get("SMART_BAMBOO_DEPLOYMENT_MODE", "development")).strip().lower()
    if mode not in PRODUCTION_MODES:
        return []

    issues: list[str] = []
    platform_url = str(values.get("SMART_BAMBOO_DATABASE_URL", "")).strip()
    platform_backend = str(values.get("SMART_BAMBOO_STORAGE_BACKEND", "")).strip().lower()
    if platform_backend != "mysql":
        issues.append("platform_storage_not_mysql")
    _validate_mysql_url(platform_url, "platform_database", issues)

    catalog_url = str(values.get("REMOTE_SENSING_DATABASE_URL", "")).strip()
    catalog_backend = str(values.get("REMOTE_SENSING_CATALOG_BACKEND", "")).strip().lower()
    if catalog_backend != "mysql":
        issues.append("catalog_storage_not_mysql")
    _validate_mysql_url(catalog_url, "catalog_database", issues)

    auth_required = str(values.get("REMOTE_SENSING_AUTH_REQUIRED", "")).strip().lower()
    if auth_required not in {"1", "true", "yes", "on"}:
        issues.append("auth_disabled")
    tokens_raw = str(values.get("REMOTE_SENSING_API_TOKENS", "")).strip()
    try:
        tokens = json.loads(tokens_raw) if tokens_raw else {}
    except json.JSONDecodeError:
        tokens = {}
        issues.append("auth_tokens_invalid")
    if not isinstance(tokens, dict) or not tokens:
        issues.append("auth_tokens_missing")

    cors_origins = [
        item.strip()
        for item in str(values.get("REMOTE_SENSING_CORS_ORIGINS", "")).split(",")
        if item.strip()
    ]
    if not cors_origins:
        issues.append("cors_origins_missing")
    elif "*" in cors_origins:
        issues.append("cors_wildcard")
    return issues


def _validate_mysql_url(database_url: str, prefix: str, issues: list[str]) -> None:
    if not database_url:
        issues.append(f"{prefix}_missing")
        return
    parsed = urllib.parse.urlparse(database_url)
    if parsed.scheme.lower() not in {"mysql", "mysql+pymysql"}:
        issues.append(f"{prefix}_not_mysql")
        return
    password = urllib.parse.unquote(parsed.password or "").strip()
    if not password:
        issues.append(f"{prefix}_password_missing")
    elif password.lower() in PLACEHOLDER_PASSWORDS:
        issues.append(f"{prefix}_placeholder_password")


def enforce_production_configuration(environ: Mapping[str, str] | None = None) -> None:
    issues = production_configuration_issues(environ)
    if issues:
        raise RuntimeError(
            "Unsafe Smart Bamboo production configuration: " + ", ".join(issues)
        )


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
    database_url = os.environ.get("SMART_BAMBOO_DATABASE_URL", "").strip()
    storage_backend = os.environ.get("SMART_BAMBOO_STORAGE_BACKEND", "").strip().lower()
    if not storage_backend:
        if database_url.lower().startswith(("mysql://", "mysql+pymysql://")):
            storage_backend = "mysql"
        else:
            storage_backend = "postgis" if database_url else "json"
    return PlatformSettings(
        data_dir=data_dir,
        storage_backend=storage_backend,
        database_url=database_url,
        auth_required=env_bool("REMOTE_SENSING_AUTH_REQUIRED", False),
        cors_origins=env_list("REMOTE_SENSING_CORS_ORIGINS", ["*"]),
    )
