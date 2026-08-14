from __future__ import annotations

import json
import importlib
import math
import os
import sys
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
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


def test_auth_required_enforces_api_tokens_for_forest_writes(isolated_env, monkeypatch):
    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv(
        "REMOTE_SENSING_API_TOKENS",
        json.dumps(
            {
                "admin-token": {"user": "alice", "roles": ["admin"], "areas": ["*"], "projects": ["*"]},
                "viewer-token": {"user": "bob", "roles": ["viewer"], "areas": ["*"], "projects": ["*"]},
            }
        ),
    )

    import server.app as app_module
    import server.modules.database as database
    import server.modules.settings as settings

    settings.get_settings.cache_clear()
    importlib.reload(settings)
    importlib.reload(database)
    importlib.reload(app_module)
    settings.get_settings.cache_clear()
    client = TestClient(app_module.app)

    missing = client.post("/api/forest-blocks", json=sample_block_payload("AUTH-TOKEN-001"))
    viewer = client.post(
        "/api/forest-blocks",
        json=sample_block_payload("AUTH-TOKEN-002"),
        headers={"Authorization": "Bearer viewer-token"},
    )
    admin = client.post(
        "/api/forest-blocks",
        json=sample_block_payload("AUTH-TOKEN-003"),
        headers={"X-RS-Token": "admin-token"},
    )

    assert missing.status_code == 401
    assert viewer.status_code == 403
    assert admin.status_code == 200
    assert admin.json()["blockCode"] == "AUTH-TOKEN-003"


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
    smart_bamboo = body["deployment"]["smartBamboo"]
    assert smart_bamboo["storageBackend"] == "json"
    assert smart_bamboo["postgisEnabled"] is False
    assert smart_bamboo["schemaReady"] is True
    assert smart_bamboo["importTuning"] == {
        "strategy": "incremental-batch",
        "mysqlWriteBatchSize": 500,
        "identityLookupBatchSize": 500,
        "singleTransaction": True,
        "mysqlReportTargets": "normalized-relational",
        "databaseReportCache": "disabled",
        "mysqlTargetRead": "paginated-relational",
        "mysqlRollback": "targeted-relational",
        "mysqlSceneLink": "insert-select-relational",
        "mysqlSceneCoverage": "aggregate-bounded-samples",
        "mysqlLayerLink": "copy-relational",
        "mysqlLayerTargets": "paginated-summary",
        "mysqlLayerCrud": "targeted-scalar",
        "mysqlBusinessTargets": "paginated-summary",
        "mysqlBusinessCrud": "targeted-scalar",
        "mysqlBusinessDashboard": "aggregate-bounded-rows",
        "mysqlRightTargets": "paginated-summary",
        "mysqlRightCrud": "targeted-scalar",
    }
    assert {item["key"] for item in smart_bamboo["jsonData"]["datasets"]} >= {
        "forestBlocks",
        "forestRights",
        "mapLayers",
        "importBatches",
        "businessRecords",
    }
    assert body["deployment"]["database"]["platform"] == {
        "backend": "json",
        "mysqlEnabled": False,
        "postgisEnabled": False,
        "reachable": True,
        "schemaReady": True,
        "missingTables": [],
        "error": "",
    }
    assert body["deployment"]["database"]["remoteSensingCatalog"] == {
        "backend": "json",
        "mysqlEnabled": False,
        "postgisEnabled": False,
        "reachable": True,
        "schemaReady": True,
        "missingTables": [],
        "error": "",
    }


def test_platform_storage_health_checks_postgis_schema(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    _, database_module = reload_platform_modules()
    cursor = FakeCursor(
        fetchone_result=(
                "forest_blocks",
                "forest_block_versions",
                "forest_subcompartments",
                "forest_subcompartment_versions",
                "resource_surveys",
                "resource_snapshots",
                "resource_snapshot_versions",
                "attachments",
                "attachment_links",
                "attachment_events",
                "forest_rights",
                "forest_right_versions",
                "map_layers",
                "business_records",
                "dictionary_types",
                "dictionary_items",
                "admin_roles",
                "admin_users",
                None,
        )
    )

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda *_args, **_kwargs: FakeConnection(cursor)))

    health = database_module.platform_storage_health()

    assert health["backend"] == "postgis"
    assert health["postgisEnabled"] is True
    assert health["reachable"] is True
    assert health["schemaReady"] is False
    assert health["missingTables"] == ["import_batches"]
    assert health["error"] == ""
    assert "to_regclass('public.forest_blocks')" in cursor.executed[0][0]


class FakeCursor:
    def __init__(self, *, fetchall_result=None, fetchone_result=None):
        self.fetchall_result = list(fetchall_result or [])
        self.fetchone_result = fetchone_result
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params=None):
        normalized = " ".join(sql.split())
        self.executed.append((normalized, tuple(params) if params is not None else None))

    def fetchall(self):
        return list(self.fetchall_result)

    def fetchone(self):
        return self.fetchone_result


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self.cursor_obj = cursor
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commit_count += 1


def install_fake_psycopg(monkeypatch, cursors: list[FakeCursor], connect_calls: list[str]):
    def fake_connect(database_url: str):
        connect_calls.append(database_url)
        return FakeConnection(cursors.pop(0))

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fake_connect))


def reload_forest_blocks_module(reload_platform_modules):
    reload_platform_modules()
    import server.modules.forest_blocks as forest_blocks_module

    importlib.reload(forest_blocks_module)
    return forest_blocks_module


SAMPLE_GEOMETRY = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [118.10, 26.50],
                [118.12, 26.50],
                [118.12, 26.52],
                [118.10, 26.52],
                [118.10, 26.50],
            ]
        ]
    ],
}


def sample_block_payload(code: str = "FB-001") -> dict[str, object]:
    return {
        "blockCode": code,
        "name": "北坡示范林班",
        "countyCode": "350703",
        "countyName": "建阳区",
        "townCode": "350703101",
        "townName": "麻沙镇",
        "villageName": "黄坑村",
        "baseType": "self_operated",
        "operationType": "timber",
        "forestType": "毛竹",
        "areaMu": 126.5,
        "qualityGrade": "A",
        "healthStatus": "normal",
        "riskLevel": "low",
        "geometry": SAMPLE_GEOMETRY,
    }


def postgis_row(code: str = "PG-001") -> dict[str, object]:
    return {
        "id": "8ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        "block_code": code,
        "name": "PostGIS block",
        "county_code": "350703",
        "county_name": "Jianyang",
        "town_code": "350703101",
        "town_name": "Masha",
        "village_code": None,
        "village_name": None,
        "base_type": "self_operated",
        "operation_type": "timber",
        "forest_type": None,
        "area_mu": 126.5,
        "slope_degree": None,
        "ownership_status": None,
        "management_status": None,
        "quality_grade": "A",
        "health_status": "normal",
        "risk_level": "low",
        "bamboo_age": None,
        "avg_dbh_cm": None,
        "avg_height_m": None,
        "standing_density": None,
        "carbon_estimate_tco2e": None,
        "yield_estimate": {},
        "tags": [],
        "properties": {},
        "geometry": SAMPLE_GEOMETRY,
        "source_batch_id": None,
        "created_at": "2026-07-07T00:00:00+00:00",
        "updated_at": "2026-07-07T00:00:00+00:00",
        "deleted_at": None,
    }


def test_postgis_create_forest_block_uses_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    forest_blocks_module = reload_forest_blocks_module(reload_platform_modules)
    duplicate_cursor = FakeCursor(fetchall_result=[])
    insert_cursor = FakeCursor()
    version_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [duplicate_cursor, insert_cursor, version_cursor], connect_calls)

    created = forest_blocks_module.create_forest_block(
        forest_blocks_module.ForestBlockIn(**sample_block_payload("PG-CREATE-001")),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert created.blockCode == "PG-CREATE-001"
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo", "postgresql://smart-bamboo"]
    assert "FROM forest_blocks" in duplicate_cursor.executed[0][0]
    assert "INSERT INTO forest_blocks" in insert_cursor.executed[0][0]
    assert "ST_GeomFromGeoJSON" in insert_cursor.executed[0][0]
    assert insert_cursor.executed[0][1][1] == "PG-CREATE-001"
    assert "INSERT INTO forest_block_versions" in version_cursor.executed[0][0]
    assert version_cursor.executed[0][1][2] == "create"


def test_postgis_load_and_save_blocks_use_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    forest_blocks_module = reload_forest_blocks_module(reload_platform_modules)
    insert_cursor = FakeCursor()
    select_cursor = FakeCursor(fetchall_result=[postgis_row("PG-LOAD-001")])
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [insert_cursor, select_cursor], connect_calls)

    block = forest_blocks_module.normalize_block(sample_block_payload("PG-LOAD-001"))
    forest_blocks_module.save_blocks([block])
    loaded = forest_blocks_module.load_all_blocks()

    assert loaded[0]["blockCode"] == "PG-LOAD-001"
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo"]
    assert "INSERT INTO forest_blocks" in insert_cursor.executed[0][0]
    assert "FROM forest_blocks" in select_cursor.executed[0][0]


def test_postgis_list_filters_are_applied_in_database(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    forest_blocks_module = reload_forest_blocks_module(reload_platform_modules)
    list_cursor = FakeCursor(fetchall_result=[postgis_row("PG-FILTER-001")])
    count_cursor = FakeCursor(fetchone_result=(1,))
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [list_cursor, count_cursor], connect_calls)

    response = forest_blocks_module.list_forest_blocks(
        forest_blocks_module.ForestBlockFilters(
            q="block",
            countyCode="350703",
            bbox="118.09,26.49,118.13,26.53",
            limit=20,
            offset=5,
        ),
        AuthContext(user="alice", roles=set(), projects=set(), areas={"350703"}),
    )

    list_sql, list_params = list_cursor.executed[0]
    count_sql, count_params = count_cursor.executed[0]
    assert response["total"] == 1
    assert response["items"][0]["blockCode"] == "PG-FILTER-001"
    assert "county_code = %s" in list_sql
    assert "geometry && ST_MakeEnvelope" in list_sql
    assert "ILIKE" in list_sql
    assert "LIMIT %s OFFSET %s" in list_sql
    assert list_params[-2:] == (20, 5)
    assert "SELECT COUNT(*) FROM forest_blocks" in count_sql
    assert count_params[:2] == ("350703", "350703")


def test_postgis_summary_uses_database_aggregation(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    forest_blocks_module = reload_forest_blocks_module(reload_platform_modules)
    totals_cursor = FakeCursor(fetchone_result=(2, 199.75, 1))
    risk_cursor = FakeCursor(fetchall_result=[("low", 1), ("high", 1)])
    quality_cursor = FakeCursor(fetchall_result=[("A", 1), ("C", 1)])
    base_cursor = FakeCursor(fetchall_result=[("self_operated", 1), ("cooperative", 1)])
    health_cursor = FakeCursor(fetchall_result=[("normal", 1), ("warning", 1)])
    connect_calls: list[str] = []
    install_fake_psycopg(
        monkeypatch,
        [totals_cursor, risk_cursor, quality_cursor, base_cursor, health_cursor],
        connect_calls,
    )

    response = forest_blocks_module.forest_block_summary(
        forest_blocks_module.ForestBlockFilters(
            countyCode="350703",
            bbox="118.09,26.49,118.13,26.53",
        ),
        AuthContext(user="alice", roles=set(), projects=set(), areas={"350703"}),
    )

    assert response["total"] == 2
    assert response["totalAreaMu"] == 199.75
    assert response["healthyCount"] == 1
    assert response["healthyRate"] == 50
    assert response["riskLevel"] == {"low": 1, "high": 1}
    assert response["healthStatus"] == {"normal": 1, "warning": 1}
    totals_sql, totals_params = totals_cursor.executed[0]
    assert "COUNT(*)" in totals_sql
    assert "SUM(area_mu)" in totals_sql
    assert "health_status" in totals_sql
    assert "FROM forest_blocks" in totals_sql
    assert "geometry && ST_MakeEnvelope" in totals_sql
    assert totals_params[:2] == ("350703", "350703")
    assert len(connect_calls) == 5


def test_postgis_map_aggregates_are_grouped_in_database(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    forest_blocks_module = reload_forest_blocks_module(reload_platform_modules)
    aggregate_cursor = FakeCursor(
        fetchall_result=[
            ("350703101", "Town A", 2, 150.0, 118.11, 26.51, 1, 0, 1, 2, 0, 0),
        ]
    )
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [aggregate_cursor], connect_calls)

    response = forest_blocks_module.forest_block_aggregates(
        "town",
        forest_blocks_module.ForestBlockFilters(
            countyCode="350703",
            bbox="118.09,26.49,118.13,26.53",
        ),
        AuthContext(user="alice", roles=set(), projects=set(), areas={"350703"}),
    )

    assert response["totalGroups"] == 1
    assert response["totalBlocks"] == 2
    assert response["items"][0]["centroid"] == [118.11, 26.51]
    sql, params = aggregate_cursor.executed[0]
    assert "GROUP BY town_code, town_name" in sql
    assert "ST_Centroid(ST_Collect" in sql
    assert "geometry && ST_MakeEnvelope" in sql
    assert params[:2] == ("350703", "350703")
    assert connect_calls == ["postgresql://smart-bamboo"]


def test_postgis_map_geojson_simplifies_geometry_in_database(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    forest_blocks_module = reload_forest_blocks_module(reload_platform_modules)
    count_cursor = FakeCursor(fetchone_result=(1,))
    select_cursor = FakeCursor(fetchall_result=[postgis_row("PG-SIMPLIFY-001")])
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [count_cursor, select_cursor], connect_calls)

    response = forest_blocks_module.forest_block_feature_collection(
        forest_blocks_module.ForestBlockFilters(
            countyCode="350703",
            bbox="118.09,26.49,118.13,26.53",
        ),
        AuthContext(user="alice", roles=set(), projects=set(), areas={"350703"}),
        max_features=100,
        zoom=12,
    )

    sql, params = select_cursor.executed[0]
    assert "ST_SimplifyPreserveTopology(geometry, %s)" in sql
    assert params[0] == response["meta"]["simplificationTolerance"]
    assert response["meta"]["geometryMode"] == "simplified"
    assert response["meta"]["zoom"] == 12
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo"]


def test_create_list_patch_and_delete_forest_block(app_client):
    create = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload(),
        headers={"X-RS-Roles": "admin"},
    )
    assert create.status_code == 200
    block = create.json()
    assert block["blockCode"] == "FB-001"
    assert block["areaMu"] == 126.5

    listed = app_client.get("/api/forest-blocks?countyCode=350703&q=北坡")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    patched = app_client.patch(
        f"/api/forest-blocks/{block['id']}",
        json={"riskLevel": "medium"},
        headers={"X-RS-Roles": "admin"},
    )
    assert patched.status_code == 200
    assert patched.json()["riskLevel"] == "medium"

    deleted = app_client.delete(
        f"/api/forest-blocks/{block['id']}",
        headers={"X-RS-Roles": "admin"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True


def test_forest_block_versions_capture_create_update_and_delete(app_client):
    created = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("VERSION-BLOCK-001"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "creator"},
    )
    block_id = created.json()["id"]
    patched = app_client.patch(
        f"/api/forest-blocks/{block_id}",
        json={"riskLevel": "medium", "areaMu": 130.25},
        headers={"X-RS-Roles": "admin", "X-RS-User": "editor"},
    )
    deleted = app_client.delete(
        f"/api/forest-blocks/{block_id}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "deleter"},
    )

    denied = app_client.get(
        f"/api/forest-blocks/{block_id}/versions",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    versions = app_client.get(
        f"/api/forest-blocks/{block_id}/versions",
        headers={"X-RS-Roles": "admin"},
    )

    assert created.status_code == 200
    assert patched.status_code == 200
    assert deleted.status_code == 200
    assert denied.status_code == 403
    assert "forest.blocks.view" in denied.json()["detail"]
    assert versions.status_code == 200
    body = versions.json()
    assert body["total"] == 3
    assert [item["changeType"] for item in body["items"]] == ["delete", "update", "create"]
    update_version = next(item for item in body["items"] if item["changeType"] == "update")
    assert update_version["createdBy"] == "editor"
    assert update_version["snapshot"]["riskLevel"] == "medium"
    assert update_version["snapshot"]["areaMu"] == 130.25
    assert update_version["snapshot"]["blockCode"] == "VERSION-BLOCK-001"


def test_forest_block_can_rollback_to_previous_version(app_client):
    created = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("ROLLBACK-VERSION-001"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "creator"},
    )
    block_id = created.json()["id"]
    app_client.patch(
        f"/api/forest-blocks/{block_id}",
        json={"riskLevel": "high", "areaMu": 188.0},
        headers={"X-RS-Roles": "admin", "X-RS-User": "editor"},
    )
    versions = app_client.get(
        f"/api/forest-blocks/{block_id}/versions",
        headers={"X-RS-Roles": "admin"},
    )
    create_version = next(item for item in versions.json()["items"] if item["changeType"] == "create")

    denied = app_client.post(
        f"/api/forest-blocks/{block_id}/rollback",
        json={"versionId": create_version["id"]},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    rolled_back = app_client.post(
        f"/api/forest-blocks/{block_id}/rollback",
        json={"versionId": create_version["id"]},
        headers={"X-RS-Roles": "admin", "X-RS-User": "rollbacker"},
    )
    current = app_client.get(f"/api/forest-blocks/{block_id}")
    after_versions = app_client.get(
        f"/api/forest-blocks/{block_id}/versions",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert rolled_back.status_code == 200
    assert rolled_back.json()["ok"] is True
    assert rolled_back.json()["block"]["riskLevel"] == "low"
    assert rolled_back.json()["block"]["areaMu"] == 126.5
    assert current.json()["riskLevel"] == "low"
    assert current.json()["areaMu"] == 126.5
    assert after_versions.json()["items"][0]["changeType"] == "rollback"
    assert after_versions.json()["items"][0]["createdBy"] == "rollbacker"
    assert after_versions.json()["items"][0]["sourceVersionId"] == create_version["id"]


def test_map_geojson_filters_by_bbox(app_client):
    app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-002"),
        headers={"X-RS-Roles": "admin"},
    )
    response = app_client.get("/api/map/forest-blocks.geojson?bbox=118.09,26.49,118.13,26.53")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    assert body["features"][0]["properties"]["blockCode"] == "FB-002"
    assert body["meta"]["returned"] == 1
    assert body["meta"]["truncated"] is False


def test_forest_block_map_endpoints_require_view_permission_for_identified_roles(app_client):
    denied_headers = {"X-RS-Roles": "business.farmers.manage"}
    allowed_headers = {"X-RS-Roles": "forest.blocks.view"}

    denied = app_client.get("/api/map/forest-blocks.geojson", headers=denied_headers)
    allowed = app_client.get("/api/map/forest-blocks.geojson", headers=allowed_headers)
    denied_summary = app_client.get("/api/map/forest-blocks/summary", headers=denied_headers)
    allowed_facets = app_client.get("/api/map/forest-blocks/facets", headers=allowed_headers)

    assert denied.status_code == 403
    assert denied.json()["detail"] == "Permission required: forest.blocks.view"
    assert denied_summary.status_code == 403
    assert allowed.status_code == 200
    assert allowed_facets.status_code == 200


def test_map_vector_tile_returns_mvt_and_uses_scope_aware_server_cache(app_client):
    first = sample_block_payload("MVT-350703")
    first["countyCode"] = "350703"
    first["countyName"] = "建阳区"
    second = sample_block_payload("MVT-350704")
    second["countyCode"] = "350704"
    second["countyName"] = "另一区县"
    for payload in (first, second):
        assert app_client.post(
            "/api/forest-blocks",
            json=payload,
            headers={"X-RS-Roles": "admin"},
        ).status_code == 200

    zoom = 14
    tile_count = 2**zoom
    longitude, latitude = 118.11, 26.51
    tile_x = int((longitude + 180.0) / 360.0 * tile_count)
    tile_y = int(
        (1.0 - math.asinh(math.tan(math.radians(latitude))) / math.pi)
        / 2.0
        * tile_count
    )
    url = f"/api/map/forest-blocks/tiles/{zoom}/{tile_x}/{tile_y}.pbf"
    headers = {"X-RS-Areas": "350703", "X-RS-User": "county-viewer"}

    first_response = app_client.get(url, headers=headers)
    assert first_response.status_code == 200
    assert first_response.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert first_response.headers["x-vector-tile-cache"] == "MISS"
    assert first_response.content

    from mapbox_vector_tile import decode

    decoded = decode(first_response.content)
    features = decoded["forest_blocks"]["features"]
    assert [feature["properties"]["blockCode"] for feature in features] == ["MVT-350703"]
    assert features[0]["properties"]["countyCode"] == "350703"

    cached_response = app_client.get(url, headers=headers)
    assert cached_response.status_code == 200
    assert cached_response.content == first_response.content
    assert cached_response.headers["x-vector-tile-cache"] == "HIT"


def test_map_vector_tile_bypasses_an_unwritable_cache(app_client, monkeypatch):
    from server.modules import forest_blocks

    payload = sample_block_payload("MVT-CACHE-BYPASS")
    assert app_client.post(
        "/api/forest-blocks",
        json=payload,
        headers={"X-RS-Roles": "admin"},
    ).status_code == 200

    class UnwritablePath:
        name = "tile.pbf"

        def exists(self):
            return False

        def with_name(self, _name):
            return self

        @property
        def parent(self):
            return self

        def mkdir(self, **_kwargs):
            raise PermissionError("cache is read-only")

        def unlink(self, **_kwargs):
            return None

    monkeypatch.setattr(
        forest_blocks,
        "vector_tile_cache_path",
        lambda *_args, **_kwargs: UnwritablePath(),
    )

    response = app_client.get("/api/map/forest-blocks/tiles/14/13566/6867.pbf")

    assert response.status_code == 200
    assert response.headers["x-vector-tile-cache"] == "BYPASS"
    assert response.content


def test_vector_tile_cache_prunes_expired_and_over_capacity_files(tmp_path, monkeypatch):
    from server.modules import forest_blocks

    cache_dir = tmp_path / "forest-block-tiles"
    tile_dir = cache_dir / "14" / "13566"
    tile_dir.mkdir(parents=True)
    revision = cache_dir / "revision.txt"
    revision.write_text("revision", encoding="ascii")
    old_tile = tile_dir / "1-old.pbf"
    older_recent_tile = tile_dir / "2-recent.pbf"
    newest_tile = tile_dir / "3-newest.pbf"
    old_tile.write_bytes(b"123456")
    older_recent_tile.write_bytes(b"12345678")
    newest_tile.write_bytes(b"abcdefgh")
    now = time.time()
    os.utime(old_tile, (now - 100, now - 100))
    os.utime(older_recent_tile, (now - 2, now - 2))
    os.utime(newest_tile, (now - 1, now - 1))

    monkeypatch.setattr(forest_blocks, "forest_vector_tile_cache_dir", lambda: cache_dir)
    monkeypatch.setattr(forest_blocks, "FOREST_VECTOR_TILE_CACHE_MAX_AGE_SECONDS", 50)
    monkeypatch.setattr(forest_blocks, "FOREST_VECTOR_TILE_CACHE_MAX_BYTES", 10)
    monkeypatch.setattr(forest_blocks, "FOREST_VECTOR_TILE_CACHE_PRUNE_INTERVAL_SECONDS", 0)

    result = forest_blocks.prune_forest_vector_tile_cache(now=now, force=True)

    assert result["deletedFiles"] == 2
    assert result["reclaimedBytes"] == 14
    assert not old_tile.exists()
    assert not older_recent_tile.exists()
    assert newest_tile.exists()
    assert revision.exists()


def test_vector_tile_env_integer_falls_back_for_invalid_values(monkeypatch):
    from server.modules import forest_blocks

    monkeypatch.setenv("SMART_BAMBOO_TEST_INT", "not-an-integer")
    assert forest_blocks.positive_env_int("SMART_BAMBOO_TEST_INT", 300, minimum=30) == 300
    monkeypatch.setenv("SMART_BAMBOO_TEST_INT", "4")
    assert forest_blocks.positive_env_int("SMART_BAMBOO_TEST_INT", 300, minimum=30) == 30


def test_map_geojson_adapts_geometry_detail_to_zoom_without_mutating_source(app_client):
    payload = sample_block_payload("FB-SIMPLIFY-001")
    payload["geometry"] = {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [
                    [118.10, 26.50],
                    [118.105, 26.50],
                    [118.11, 26.50],
                    [118.12, 26.50],
                    [118.12, 26.51],
                    [118.12, 26.52],
                    [118.11, 26.52],
                    [118.10, 26.52],
                    [118.10, 26.51],
                    [118.10, 26.50],
                ]
            ]
        ],
    }
    assert app_client.post(
        "/api/forest-blocks",
        json=payload,
        headers={"X-RS-Roles": "admin"},
    ).status_code == 200

    simplified = app_client.get("/api/map/forest-blocks.geojson?zoom=12&maxFeatures=10")
    detailed = app_client.get("/api/map/forest-blocks.geojson?zoom=16&maxFeatures=10")
    stored = app_client.get("/api/forest-blocks?q=FB-SIMPLIFY-001")

    assert simplified.status_code == 200
    assert detailed.status_code == 200
    simplified_body = simplified.json()
    detailed_body = detailed.json()
    simplified_ring = simplified_body["features"][0]["geometry"]["coordinates"][0][0]
    detailed_ring = detailed_body["features"][0]["geometry"]["coordinates"][0][0]
    assert len(simplified_ring) < len(detailed_ring)
    assert simplified_ring[0] == simplified_ring[-1]
    assert simplified_body["meta"]["geometryMode"] == "simplified"
    assert simplified_body["meta"]["simplificationTolerance"] > 0
    assert detailed_body["meta"]["geometryMode"] == "full"
    assert detailed_body["meta"]["simplificationTolerance"] == 0
    assert len(stored.json()["items"][0]["geometry"]["coordinates"][0][0]) == len(detailed_ring)


def test_map_geojson_can_limit_features_and_report_truncation(app_client):
    for index in range(3):
        payload = sample_block_payload(f"MAP-LIMIT-{index + 1:03d}")
        payload["name"] = f"Map limit block {index + 1}"
        app_client.post(
            "/api/forest-blocks",
            json=payload,
            headers={"X-RS-Roles": "admin"},
        )

    response = app_client.get(
        "/api/map/forest-blocks.geojson?bbox=118.09,26.49,118.13,26.53&maxFeatures=2"
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["features"]) == 2
    assert body["meta"] == {
        "total": 3,
        "returned": 2,
        "maxFeatures": 2,
        "truncated": True,
        "zoom": 14.0,
        "geometryMode": "simplified",
        "simplificationTolerance": 0.00001,
    }


def test_deleted_block_is_hidden_but_preserved_for_later_writes(
    app_client, isolated_env, reload_platform_modules
):
    first = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-003"),
        headers={"X-RS-Roles": "admin"},
    )
    assert first.status_code == 200
    deleted_id = first.json()["id"]

    deleted = app_client.delete(
        f"/api/forest-blocks/{deleted_id}",
        headers={"X-RS-Roles": "admin"},
    )
    assert deleted.status_code == 200

    second = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-004"),
        headers={"X-RS-Roles": "admin"},
    )
    assert second.status_code == 200

    listed = app_client.get("/api/forest-blocks")
    assert listed.status_code == 200
    assert [item["blockCode"] for item in listed.json()["items"]] == ["FB-004"]

    geojson = app_client.get("/api/map/forest-blocks.geojson")
    assert geojson.status_code == 200
    assert [feature["properties"]["blockCode"] for feature in geojson.json()["features"]] == ["FB-004"]

    _, database_module = reload_platform_modules()
    stored = json.loads(database_module.forest_blocks_json_path().read_text(encoding="utf-8"))
    assert {item["blockCode"] for item in stored} == {"FB-003", "FB-004"}
    assert next(item for item in stored if item["blockCode"] == "FB-003")["deletedAt"]


def test_deleted_forest_block_can_be_listed_and_restored(app_client):
    created = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-RESTORE-001"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    block_id = created.json()["id"]

    deleted = app_client.delete(
        f"/api/forest-blocks/{block_id}",
        headers={"X-RS-Roles": "admin"},
    )
    hidden = app_client.get("/api/forest-blocks?q=FB-RESTORE-001")
    deleted_list = app_client.get(
        "/api/forest-blocks?q=FB-RESTORE-001&includeDeleted=true",
        headers={"X-RS-Roles": "admin"},
    )
    denied_restore = app_client.post(
        f"/api/forest-blocks/{block_id}/restore",
        headers={"X-RS-Roles": "forest.rights.manage"},
    )
    restored = app_client.post(
        f"/api/forest-blocks/{block_id}/restore",
        headers={"X-RS-Roles": "admin"},
    )
    active_again = app_client.get("/api/forest-blocks?q=FB-RESTORE-001")

    assert deleted.status_code == 200
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0
    assert deleted_list.status_code == 200
    assert deleted_list.json()["total"] == 1
    assert deleted_list.json()["items"][0]["deletedAt"]
    assert denied_restore.status_code == 403
    assert "forest.blocks.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    assert restored.json()["ok"] is True
    assert restored.json()["restored"] == block_id
    assert restored.json()["block"]["deletedAt"] is None
    assert active_again.status_code == 200
    assert active_again.json()["total"] == 1


def test_area_scoped_writer_cannot_create_block_outside_allowed_areas(app_client):
    response = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-005") | {"countyCode": "350702"},
        headers={"X-RS-Roles": "operator", "X-RS-Areas": "350703"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Area access denied"


def test_area_context_filters_forest_blocks(app_client):
    first = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("AREA-001"),
        headers={"X-RS-Roles": "admin"},
    )
    assert first.status_code == 200

    other = sample_block_payload("AREA-002")
    other["countyCode"] = "350702"
    other["countyName"] = "延平区"
    second = app_client.post(
        "/api/forest-blocks",
        json=other,
        headers={"X-RS-Roles": "admin"},
    )
    assert second.status_code == 200

    response = app_client.get("/api/forest-blocks", headers={"X-RS-Areas": "350703"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["countyCode"] == "350703"


def test_area_scoped_writer_cannot_create_block_without_county_code(app_client):
    payload = sample_block_payload("FB-005A")
    payload.pop("countyCode")

    response = app_client.post(
        "/api/forest-blocks",
        json=payload,
        headers={"X-RS-Roles": "operator", "X-RS-Areas": "350703"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Area access denied"


def test_area_scoped_patch_cannot_move_block_into_unauthorized_county(app_client):
    created = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-005B"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    block_id = created.json()["id"]

    patched = app_client.patch(
        f"/api/forest-blocks/{block_id}",
        json={"countyCode": "350702"},
        headers={"X-RS-Roles": "operator", "X-RS-Areas": "350703"},
    )

    assert patched.status_code == 403
    assert patched.json()["detail"] == "Area access denied"

    fetched = app_client.get(
        f"/api/forest-blocks/{block_id}",
        headers={"X-RS-Roles": "operator", "X-RS-Areas": "350703"},
    )

    assert fetched.status_code == 200
    assert fetched.json()["countyCode"] == "350703"


def test_non_writer_role_cannot_create_forest_block(app_client):
    response = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("PERM-CREATE-001"),
        headers={"X-RS-Roles": "viewer"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission required: forest.blocks.create"


def test_non_writer_role_cannot_patch(app_client):
    created = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("PERM-PATCH-001"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    block_id = created.json()["id"]

    response = app_client.patch(
        f"/api/forest-blocks/{block_id}",
        json={"riskLevel": "high"},
        headers={"X-RS-Roles": "viewer"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission required: forest.blocks.update"


def test_non_writer_role_cannot_delete_forest_block(app_client):
    created = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("PERM-DELETE-001"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    block_id = created.json()["id"]

    response = app_client.delete(
        f"/api/forest-blocks/{block_id}",
        headers={"X-RS-Roles": "viewer"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission required: forest.blocks.delete"


def test_forest_block_action_permissions_control_each_write_operation(app_client):
    created = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("ACTION-BLOCK-001"),
        headers={"X-RS-Roles": "forest.blocks.create", "X-RS-User": "creator"},
    )

    assert created.status_code == 200
    block_id = created.json()["id"]

    denied_patch = app_client.patch(
        f"/api/forest-blocks/{block_id}",
        json={"riskLevel": "medium"},
        headers={"X-RS-Roles": "forest.blocks.create"},
    )
    patched = app_client.patch(
        f"/api/forest-blocks/{block_id}",
        json={"riskLevel": "medium"},
        headers={"X-RS-Roles": "forest.blocks.update", "X-RS-User": "editor"},
    )
    versions = app_client.get(
        f"/api/forest-blocks/{block_id}/versions",
        headers={"X-RS-Roles": "forest.blocks.view"},
    )
    create_version = next(item for item in versions.json()["items"] if item["changeType"] == "create")
    denied_rollback = app_client.post(
        f"/api/forest-blocks/{block_id}/rollback",
        json={"versionId": create_version["id"]},
        headers={"X-RS-Roles": "forest.blocks.update"},
    )
    rolled_back = app_client.post(
        f"/api/forest-blocks/{block_id}/rollback",
        json={"versionId": create_version["id"]},
        headers={"X-RS-Roles": "forest.blocks.rollback", "X-RS-User": "rollbacker"},
    )
    denied_delete = app_client.delete(
        f"/api/forest-blocks/{block_id}",
        headers={"X-RS-Roles": "forest.blocks.update"},
    )
    deleted = app_client.delete(
        f"/api/forest-blocks/{block_id}",
        headers={"X-RS-Roles": "forest.blocks.delete", "X-RS-User": "deleter"},
    )
    denied_restore = app_client.post(
        f"/api/forest-blocks/{block_id}/restore",
        headers={"X-RS-Roles": "forest.blocks.delete"},
    )
    restored = app_client.post(
        f"/api/forest-blocks/{block_id}/restore",
        headers={"X-RS-Roles": "forest.blocks.restore", "X-RS-User": "restorer"},
    )

    assert denied_patch.status_code == 403
    assert "forest.blocks.update" in denied_patch.json()["detail"]
    assert patched.status_code == 200
    assert versions.status_code == 200
    assert denied_rollback.status_code == 403
    assert "forest.blocks.rollback" in denied_rollback.json()["detail"]
    assert rolled_back.status_code == 200
    assert denied_delete.status_code == 403
    assert "forest.blocks.delete" in denied_delete.json()["detail"]
    assert deleted.status_code == 200
    assert denied_restore.status_code == 403
    assert "forest.blocks.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    assert restored.json()["block"]["deletedAt"] is None


def test_patch_rejects_block_code_mutation(app_client):
    created = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-006"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    block_id = created.json()["id"]

    patched = app_client.patch(
        f"/api/forest-blocks/{block_id}",
        json={"blockCode": "FB-006-NEW"},
        headers={"X-RS-Roles": "admin"},
    )

    assert patched.status_code == 422


def test_duplicate_block_code_conflicts(app_client):
    first = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-007"),
        headers={"X-RS-Roles": "admin"},
    )
    assert first.status_code == 200

    duplicate = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-007"),
        headers={"X-RS-Roles": "admin"},
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "blockCode already exists"


def test_map_geojson_returns_no_features_outside_bbox(app_client):
    created = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-008"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200

    response = app_client.get("/api/map/forest-blocks.geojson?bbox=119.00,27.00,119.10,27.10")

    assert response.status_code == 200
    assert response.json()["features"] == []


def test_forest_block_summary_counts_filtered_dimensions(app_client):
    first = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-SUM-1"),
        headers={"X-RS-Roles": "admin"},
    )
    assert first.status_code == 200

    second_payload = sample_block_payload("FB-SUM-2")
    second_payload.update(
        {
            "baseType": "cooperative",
            "qualityGrade": "C",
            "riskLevel": "high",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [118.30, 26.70],
                            [118.32, 26.70],
                            [118.32, 26.72],
                            [118.30, 26.72],
                            [118.30, 26.70],
                        ]
                    ]
                ],
            },
        }
    )
    second = app_client.post(
        "/api/forest-blocks",
        json=second_payload,
        headers={"X-RS-Roles": "admin"},
    )
    assert second.status_code == 200

    response = app_client.get("/api/map/forest-blocks/summary?bbox=118.09,26.49,118.13,26.53")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "total": 1,
        "totalAreaMu": 126.5,
        "healthyCount": 1,
        "healthyRate": 100,
        "riskLevel": {"low": 1},
        "qualityGrade": {"A": 1},
        "baseType": {"self_operated": 1},
        "healthStatus": {"normal": 1},
    }


def test_forest_block_summary_counts_unknown_dimension_buckets(app_client):
    first = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-SUM-UNKNOWN-1"),
        headers={"X-RS-Roles": "admin"},
    )
    assert first.status_code == 200

    second_payload = sample_block_payload("FB-SUM-UNKNOWN-2")
    second_payload.update(
        {
            "baseType": "",
            "qualityGrade": None,
            "riskLevel": "",
        }
    )
    second = app_client.post(
        "/api/forest-blocks",
        json=second_payload,
        headers={"X-RS-Roles": "admin"},
    )
    assert second.status_code == 200

    response = app_client.get("/api/map/forest-blocks/summary")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "total": 2,
        "totalAreaMu": 253.0,
        "healthyCount": 2,
        "healthyRate": 100,
        "riskLevel": {"low": 1, "unknown": 1},
        "qualityGrade": {"A": 1, "unknown": 1},
        "baseType": {"self_operated": 1, "unknown": 1},
        "healthStatus": {"normal": 2},
    }


def test_forest_block_summary_includes_mobile_resource_metrics(app_client):
    first = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("FB-SUM-MOBILE-1"),
        headers={"X-RS-Roles": "admin"},
    )
    assert first.status_code == 200

    second_payload = sample_block_payload("FB-SUM-MOBILE-2")
    second_payload.update({"areaMu": 73.25, "healthStatus": "warning"})
    second = app_client.post(
        "/api/forest-blocks",
        json=second_payload,
        headers={"X-RS-Roles": "admin"},
    )
    assert second.status_code == 200

    response = app_client.get("/api/map/forest-blocks/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["totalAreaMu"] == 199.75
    assert body["healthyCount"] == 1
    assert body["healthyRate"] == 50
    assert body["healthStatus"] == {"normal": 1, "warning": 1}


def test_forest_block_facets_return_layer_filter_options_and_counts(app_client):
    first_payload = sample_block_payload("FB-FACET-1")
    first_payload.update({"countyName": "Jianyang", "townName": "Town A"})
    first = app_client.post(
        "/api/forest-blocks",
        json=first_payload,
        headers={"X-RS-Roles": "admin"},
    )
    assert first.status_code == 200

    second_payload = sample_block_payload("FB-FACET-2")
    second_payload.update(
        {
            "countyCode": "350702",
            "countyName": "Yanping",
            "townCode": "350702101",
            "townName": "Town B",
            "baseType": "cooperative",
            "operationType": "shoot",
            "qualityGrade": "B",
            "healthStatus": "warning",
            "riskLevel": "medium",
        }
    )
    second = app_client.post(
        "/api/forest-blocks",
        json=second_payload,
        headers={"X-RS-Roles": "admin"},
    )
    assert second.status_code == 200

    response = app_client.get("/api/map/forest-blocks/facets")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total"] == 2
    assert body["facets"]["countyCode"] == [
        {"value": "350702", "label": "Yanping", "count": 1},
        {"value": "350703", "label": "Jianyang", "count": 1},
    ]
    assert body["facets"]["townCode"] == [
        {"value": "350702101", "label": "Town B", "count": 1},
        {"value": "350703101", "label": "Town A", "count": 1},
    ]
    assert {"value": "self_operated", "label": "self_operated", "count": 1} in body["facets"]["baseType"]
    assert {"value": "cooperative", "label": "cooperative", "count": 1} in body["facets"]["baseType"]


def test_forest_block_facets_respect_current_filters_and_area_scope(app_client):
    first_payload = sample_block_payload("FB-FACET-SCOPE-1")
    first_payload.update({"countyName": "Jianyang", "townName": "Town A"})
    app_client.post(
        "/api/forest-blocks",
        json=first_payload,
        headers={"X-RS-Roles": "admin"},
    )
    other = sample_block_payload("FB-FACET-SCOPE-2")
    other.update({"countyCode": "350702", "countyName": "Yanping", "riskLevel": "high"})
    app_client.post(
        "/api/forest-blocks",
        json=other,
        headers={"X-RS-Roles": "admin"},
    )

    response = app_client.get(
        "/api/map/forest-blocks/facets?riskLevel=low",
        headers={"X-RS-Areas": "350703"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total"] == 1
    assert body["facets"]["countyCode"] == [
        {"value": "350703", "label": "Jianyang", "count": 1},
    ]
    assert body["facets"]["riskLevel"] == [
        {"value": "low", "label": "low", "count": 1},
    ]


def test_forest_block_aggregates_group_blocks_for_low_zoom_map(app_client):
    first = sample_block_payload("AGG-TOWN-001")
    first.update(
        {
            "townCode": "350703101",
            "townName": "Town A",
            "villageCode": "350703101001",
            "villageName": "Village A",
            "areaMu": 100,
            "riskLevel": "low",
        }
    )
    second = sample_block_payload("AGG-TOWN-002")
    second.update(
        {
            "townCode": "350703101",
            "townName": "Town A",
            "villageCode": "350703101001",
            "villageName": "Village A",
            "areaMu": 50,
            "riskLevel": "high",
        }
    )
    third = sample_block_payload("AGG-TOWN-003")
    third.update(
        {
            "townCode": "350703102",
            "townName": "Town B",
            "villageCode": "350703102001",
            "villageName": "Village B",
            "areaMu": 25,
            "riskLevel": "medium",
        }
    )
    for payload in (first, second, third):
        response = app_client.post(
            "/api/forest-blocks",
            json=payload,
            headers={"X-RS-Roles": "admin"},
        )
        assert response.status_code == 200

    response = app_client.get("/api/map/forest-blocks/aggregates?level=town")

    assert response.status_code == 200
    body = response.json()
    assert body["level"] == "town"
    assert body["totalGroups"] == 2
    assert body["totalBlocks"] == 3
    assert body["totalAreaMu"] == 175
    town_a = next(item for item in body["items"] if item["code"] == "350703101")
    assert town_a["name"] == "Town A"
    assert town_a["blockCount"] == 2
    assert town_a["areaMu"] == 150
    assert town_a["riskLevel"] == "high"
    assert town_a["riskCounts"] == {"high": 1, "medium": 0, "low": 1, "unknown": 0}
    assert town_a["qualityCounts"] == {"A": 2, "B": 0, "C": 0, "unknown": 0}
    assert town_a["centroid"] == pytest.approx([118.11, 26.51])


def test_forest_block_aggregates_support_village_filter_and_area_scope(app_client):
    allowed = sample_block_payload("AGG-VILLAGE-001")
    allowed.update(
        {
            "countyCode": "350703",
            "villageCode": "350703101001",
            "villageName": "Village A",
        }
    )
    denied = sample_block_payload("AGG-VILLAGE-002")
    denied.update(
        {
            "countyCode": "350704",
            "countyName": "County B",
            "villageCode": "350704101001",
            "villageName": "Village B",
        }
    )
    for payload in (allowed, denied):
        assert app_client.post(
            "/api/forest-blocks",
            json=payload,
            headers={"X-RS-Roles": "admin"},
        ).status_code == 200

    response = app_client.get(
        "/api/map/forest-blocks/aggregates?level=village&villageCode=350703101001",
        headers={"X-RS-Areas": "350703"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["totalGroups"] == 1
    assert body["totalBlocks"] == 1
    assert body["items"][0]["code"] == "350703101001"


def test_forest_block_aggregates_reject_invalid_level(app_client):
    response = app_client.get("/api/map/forest-blocks/aggregates?level=block")

    assert response.status_code == 422


def test_forest_block_write_rejects_rights_status_fields(app_client):
    payload = sample_block_payload("RIGHTS-FIELDS-001")
    payload.update(
        {
            "ownershipStatus": "certified",
            "managementStatus": "active",
        }
    )

    created = app_client.post("/api/forest-blocks", json=payload, headers={"X-RS-Roles": "admin"})
    assert created.status_code == 422

    valid = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload("RIGHTS-FIELDS-002"),
        headers={"X-RS-Roles": "admin"},
    )
    assert valid.status_code == 200

    patched = app_client.patch(
        f"/api/forest-blocks/{valid.json()['id']}",
        json={"managementStatus": "active"},
        headers={"X-RS-Roles": "admin"},
    )
    assert patched.status_code == 422


def test_keyword_search_does_not_match_forest_rights_archive_properties(app_client):
    payload = sample_block_payload("RIGHTS-SEARCH-001")
    payload["properties"] = {
        "rights": {
            "holder": "North Slope Cooperative",
            "certificateNo": "CERT-2026-001",
        }
    }

    assert app_client.post("/api/forest-blocks", json=payload, headers={"X-RS-Roles": "admin"}).status_code == 200

    by_holder = app_client.get("/api/forest-blocks?q=North%20Slope")
    by_certificate = app_client.get("/api/forest-blocks?q=CERT-2026-001")

    assert by_holder.status_code == 200
    assert by_holder.json()["total"] == 0
    assert by_certificate.status_code == 200
    assert by_certificate.json()["total"] == 0


def test_forest_block_ledger_hides_legacy_right_archive_rows(app_client, reload_platform_modules):
    _, database_module = reload_platform_modules()
    from server.modules import forest_blocks as forest_blocks_module

    legacy = forest_blocks_module.normalize_block(
        {
            **sample_block_payload("BAMBOO-RIGHTS-001"),
            "name": "黄坑示范竹林林权档案",
            "properties": {
                "rights": {
                    "holder": "黄坑村股份经济合作社",
                    "certificateNo": "闽林权证-350703-2026-0001",
                }
            },
        }
    )
    forest_blocks_module.save_blocks([legacy])

    listed = app_client.get("/api/forest-blocks?q=BAMBOO-RIGHTS-001")
    geojson = app_client.get("/api/map/forest-blocks.geojson?q=BAMBOO-RIGHTS-001")
    summary = app_client.get("/api/map/forest-blocks/summary?q=BAMBOO-RIGHTS-001")
    stored = json.loads(database_module.forest_blocks_json_path().read_text(encoding="utf-8"))

    assert listed.status_code == 200
    assert listed.json()["total"] == 0
    assert geojson.status_code == 200
    assert geojson.json()["features"] == []
    assert summary.status_code == 200
    assert summary.json()["total"] == 0
    assert stored[0]["blockCode"] == "BAMBOO-RIGHTS-001"
