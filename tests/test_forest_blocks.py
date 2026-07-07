from __future__ import annotations

import json
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
        json={"riskLevel": "medium", "managementStatus": "管护中"},
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
    assert response.json()["detail"] == "Write access denied"


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
    assert response.json()["detail"] == "Write access denied"


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
    assert response.json()["detail"] == "Write access denied"


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
        "riskLevel": {"low": 1},
        "qualityGrade": {"A": 1},
        "baseType": {"self_operated": 1},
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
        "riskLevel": {"low": 1, "unknown": 1},
        "qualityGrade": {"A": 1, "unknown": 1},
        "baseType": {"self_operated": 1, "unknown": 1},
    }
