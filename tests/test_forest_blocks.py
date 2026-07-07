from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from server.modules.auth import AuthContext, request_context, require_write_access


def build_request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (key.lower().encode("latin-1"), value.encode("latin-1"))
                for key, value in headers.items()
            ],
        }
    )


def test_platform_settings_use_json_fallback(isolated_env, reload_platform_modules):
    settings_module, _ = reload_platform_modules()

    settings = settings_module.get_settings()

    assert settings.storage_backend == "json"
    assert settings.database_url == ""
    assert settings.data_dir.name == "remote-sensing"


def test_request_context_parses_remote_sensing_headers():
    context = request_context(
        build_request(
            {
                "X-RS-User": "alice",
                "X-RS-Roles": "admin;operator",
                "X-RS-Projects": "p1, p2",
                "X-RS-Areas": "a1;a2",
            }
        )
    )

    assert context.user == "alice"
    assert context.roles == {"admin", "operator"}
    assert context.projects == {"p1", "p2"}
    assert context.areas == {"a1", "a2"}


@pytest.mark.parametrize(
    ("roles", "should_raise"),
    [
        (set(), False),
        ({"admin"}, False),
        ({"operator"}, False),
        ({"gis-admin"}, False),
        ({"viewer"}, True),
    ],
)
def test_require_write_access_handles_expected_roles(roles: set[str], should_raise: bool):
    context = AuthContext(user="alice", roles=roles, projects=set(), areas=set())

    if should_raise:
        with pytest.raises(HTTPException) as excinfo:
            require_write_access(context)
        assert excinfo.value.status_code == 403
        return

    require_write_access(context)


def test_get_data_dir_creates_forest_blocks_directory(isolated_env, reload_platform_modules):
    _, database_module = reload_platform_modules()

    data_dir = database_module.get_data_dir()

    assert data_dir.name == "remote-sensing"
    assert (data_dir / "forest-blocks").is_dir()


def test_use_postgis_is_false_for_remote_sensing_database_env_only(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("REMOTE_SENSING_DATABASE_URL", "postgresql://remote-sensing")
    settings_module, database_module = reload_platform_modules()
    settings = settings_module.get_settings()

    assert settings.database_url == ""
    assert settings.storage_backend == "json"
    assert database_module.use_postgis() is False


@pytest.mark.parametrize("storage_backend", ["", "postgis"])
def test_use_postgis_requires_explicit_smart_bamboo_database_url(
    isolated_env, monkeypatch, storage_backend: str, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", storage_backend)
    settings_module, database_module = reload_platform_modules()

    settings = settings_module.get_settings()

    assert settings.database_url == "postgresql://smart-bamboo"
    assert settings.storage_backend == "postgis"
    assert database_module.use_postgis() is True


def test_use_postgis_is_false_when_database_url_only_comes_from_database_url(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("DATABASE_URL", "postgresql://shared-default")
    settings_module, database_module = reload_platform_modules()

    settings = settings_module.get_settings()

    assert settings.database_url == ""
    assert settings.storage_backend == "json"
    assert database_module.use_postgis() is False


def test_init_platform_schema_skips_postgis_when_disabled(
    isolated_env, monkeypatch, reload_platform_modules
):
    _, database_module = reload_platform_modules()
    connect_attempted = {"value": False}

    def fail_connect(*args, **kwargs):
        connect_attempted["value"] = True
        raise AssertionError("psycopg.connect should not be called")

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fail_connect))

    database_module.init_platform_schema()

    assert connect_attempted["value"] is False


def test_health_includes_platform_schema_status(app_client):
    response = app_client.get("/api/health")

    assert response.status_code == 200
    body = response.json()

    assert body["ok"] is True
    assert body["deployment"]["smartBamboo"] == {
        "storageBackend": "json",
        "postgisEnabled": False,
        "schemaReady": True,
    }
