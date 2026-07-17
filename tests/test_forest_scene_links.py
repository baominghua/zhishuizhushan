from __future__ import annotations

import importlib
import json
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from server.modules.auth import AuthContext
from tests.test_forest_blocks import sample_block_payload


def seed_catalog(reload_platform_modules, *scene_specs: str | dict[str, object]) -> None:
    _, database_module = reload_platform_modules()
    catalog_path = database_module.get_data_dir() / "catalog.json"
    scenes = []
    for scene_spec in scene_specs:
        if isinstance(scene_spec, str):
            scenes.append(
                {
                    "id": scene_spec,
                    "name": scene_spec,
                    "cogPath": f"cogs/{scene_spec}.tif",
                    "bounds": [117.0, 27.0, 118.0, 28.0],
                }
            )
            continue
        scenes.append(
            {
                "name": str(scene_spec.get("id") or "scene"),
                "cogPath": f"cogs/{scene_spec.get('id')}.tif",
                "bounds": [117.0, 27.0, 118.0, 28.0],
                **scene_spec,
            }
        )
    catalog_path.write_text(json.dumps({"scenes": scenes}, ensure_ascii=False, indent=2), encoding="utf-8")


def create_block(app_client, code: str = "LINK-001") -> dict[str, object]:
    response = app_client.post(
        "/api/forest-blocks",
        json=sample_block_payload(code),
        headers={"X-RS-Roles": "admin"},
    )
    assert response.status_code == 200
    return response.json()


def list_links(app_client, block_id: str, headers: dict[str, str] | None = None):
    return app_client.get(f"/api/forest-blocks/{block_id}/scenes", headers=headers or {})


def link_scene(
    app_client,
    block_id: str,
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
):
    return app_client.post(
        f"/api/forest-blocks/{block_id}/scenes",
        json=payload,
        headers=headers or {},
    )


def delete_scene_link(
    app_client,
    block_id: str,
    scene_id: str,
    *,
    relation_type: str | None = None,
    headers: dict[str, str] | None = None,
):
    params = {}
    if relation_type:
        params["relationType"] = relation_type
    return app_client.delete(
        f"/api/forest-blocks/{block_id}/scenes/{scene_id}",
        params=params,
        headers=headers or {},
    )


def reload_scene_links_module(reload_platform_modules):
    reload_platform_modules()
    import server.modules.forest_scene_links as forest_scene_links_module

    importlib.reload(forest_scene_links_module)
    return forest_scene_links_module


def seed_scene_links(reload_platform_modules, *items: dict[str, object]) -> None:
    forest_scene_links_module = reload_scene_links_module(reload_platform_modules)
    forest_scene_links_module.save_scene_links(list(items))


class FakeCursor:
    def __init__(self, *, fetchall_result=None, fetchone_result=None, rowcount: int = 0):
        self.fetchall_result = list(fetchall_result or [])
        self.fetchone_result = fetchone_result
        self.rowcount = rowcount
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


def install_fake_psycopg(monkeypatch, *, cursor: FakeCursor, connect_calls: list[str] | None = None):
    calls = connect_calls if connect_calls is not None else []

    def fake_connect(database_url: str):
        calls.append(database_url)
        return FakeConnection(cursor)

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fake_connect))
    return calls


def test_link_scene_to_forest_block_lists_and_persists(app_client, reload_platform_modules):
    seed_catalog(reload_platform_modules, "cog-demo-001")
    block = create_block(app_client)

    response = link_scene(
        app_client,
        block["id"],
        {
            "sceneId": "cog-demo-001",
            "relationType": "orthophoto",
            "capturedAt": "2026-06-10",
            "confidence": 0.92,
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    assert response.json()["sceneId"] == "cog-demo-001"
    assert response.json()["relationType"] == "orthophoto"

    listed = list_links(app_client, block["id"])

    assert listed.status_code == 200
    assert listed.json() == {
        "items": [
            {
                "forestBlockId": block["id"],
                "sceneId": "cog-demo-001",
                "relationType": "orthophoto",
                "capturedAt": "2026-06-10",
                "confidence": 0.92,
            }
        ],
        "total": 1,
    }

    _, database_module = reload_platform_modules()
    link_path = database_module.get_data_dir() / "forest-blocks" / "forest_block_scene_links.json"
    assert json.loads(link_path.read_text(encoding="utf-8")) == listed.json()["items"]


def test_duplicate_scene_relation_upserts_in_place(app_client, reload_platform_modules):
    seed_catalog(reload_platform_modules, "cog-demo-002")
    block = create_block(app_client, "LINK-UPSERT-001")

    first = link_scene(
        app_client,
        block["id"],
        {
            "sceneId": "cog-demo-002",
            "relationType": "coverage",
            "capturedAt": "2026-06-01",
            "confidence": 0.66,
        },
        headers={"X-RS-Roles": "admin"},
    )
    assert first.status_code == 200

    second = link_scene(
        app_client,
        block["id"],
        {
            "sceneId": "cog-demo-002",
            "relationType": "coverage",
            "capturedAt": "2026-06-12",
            "confidence": 0.95,
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert second.status_code == 200
    listed = list_links(app_client, block["id"])
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["capturedAt"] == "2026-06-12"
    assert listed.json()["items"][0]["confidence"] == 0.95


def test_delete_scene_links_supports_relation_type_and_full_scene_removal(app_client, reload_platform_modules):
    seed_catalog(reload_platform_modules, "cog-demo-003", "cog-demo-004")
    block = create_block(app_client, "LINK-DELETE-001")
    for relation_type in ("coverage", "orthophoto"):
        response = link_scene(
            app_client,
            block["id"],
            {
                "sceneId": "cog-demo-003",
                "relationType": relation_type,
            },
            headers={"X-RS-Roles": "admin"},
        )
        assert response.status_code == 200

    extra = link_scene(
        app_client,
        block["id"],
        {
            "sceneId": "cog-demo-004",
            "relationType": "coverage",
        },
        headers={"X-RS-Roles": "admin"},
    )
    assert extra.status_code == 200

    deleted_one = delete_scene_link(
        app_client,
        block["id"],
        "cog-demo-003",
        relation_type="coverage",
        headers={"X-RS-Roles": "admin"},
    )
    assert deleted_one.status_code == 200
    assert deleted_one.json() == {"ok": True, "deleted": 1}

    after_one = list_links(app_client, block["id"])
    assert after_one.status_code == 200
    assert {(item["sceneId"], item["relationType"]) for item in after_one.json()["items"]} == {
        ("cog-demo-003", "orthophoto"),
        ("cog-demo-004", "coverage"),
    }

    deleted_all = delete_scene_link(
        app_client,
        block["id"],
        "cog-demo-003",
        headers={"X-RS-Roles": "admin"},
    )
    assert deleted_all.status_code == 200
    assert deleted_all.json() == {"ok": True, "deleted": 1}

    final_list = list_links(app_client, block["id"])
    assert final_list.status_code == 200
    assert {(item["sceneId"], item["relationType"]) for item in final_list.json()["items"]} == {
        ("cog-demo-004", "coverage"),
    }


def test_deleting_imagery_scene_removes_forest_block_scene_link_records(app_client, reload_platform_modules):
    from server.modules import forest_scene_links as forest_scene_links_module

    seed_catalog(reload_platform_modules, "scene-delete-cleanup")
    block = create_block(app_client, "LINK-SCENE-DELETE-001")
    linked = link_scene(
        app_client,
        block["id"],
        {"sceneId": "scene-delete-cleanup", "relationType": "coverage"},
        headers={"X-RS-Roles": "admin"},
    )

    assert linked.status_code == 200
    assert forest_scene_links_module.load_scene_links()[0]["sceneId"] == "scene-delete-cleanup"

    deleted = app_client.delete(
        "/api/scenes/scene-delete-cleanup",
        headers={"X-RS-Roles": "admin"},
    )

    assert deleted.status_code == 200
    assert forest_scene_links_module.load_scene_links() == []


def test_scene_links_require_visible_block_for_read_and_write(app_client, reload_platform_modules):
    seed_catalog(reload_platform_modules, "cog-demo-005")
    block = create_block(app_client, "LINK-VIS-001")
    hidden_headers = {"X-RS-Roles": "operator", "X-RS-Areas": "350702"}

    listed = list_links(app_client, block["id"], headers=hidden_headers)
    created = link_scene(
        app_client,
        block["id"],
        {"sceneId": "cog-demo-005", "relationType": "coverage"},
        headers=hidden_headers,
    )
    deleted = delete_scene_link(
        app_client,
        block["id"],
        "cog-demo-005",
        headers=hidden_headers,
    )

    assert listed.status_code == 404
    assert created.status_code == 404
    assert deleted.status_code == 404


def test_scene_links_require_write_access_for_mutations(app_client, reload_platform_modules):
    seed_catalog(reload_platform_modules, "cog-demo-006")
    block = create_block(app_client, "LINK-AUTH-001")

    created = link_scene(
        app_client,
        block["id"],
        {"sceneId": "cog-demo-006", "relationType": "coverage"},
        headers={"X-RS-Roles": "viewer", "X-RS-Areas": "350703"},
    )
    deleted = delete_scene_link(
        app_client,
        block["id"],
        "cog-demo-006",
        headers={"X-RS-Roles": "viewer", "X-RS-Areas": "350703"},
    )

    assert created.status_code == 403
    assert deleted.status_code == 403


def test_scene_link_permission_allows_linkage_writes_without_admin_role(app_client, reload_platform_modules):
    app_client.post(
        "/api/admin/roles",
        json={
            "roleCode": "linkage_editor",
            "name": "Linkage editor",
            "status": "active",
            "permissions": ["forest.linkages.manage"],
            "menuModules": ["linkages"],
            "dataScopes": {},
            "properties": {},
        },
        headers={"X-RS-Roles": "admin"},
    )
    seed_catalog(reload_platform_modules, "cog-demo-perm-001")
    block = create_block(app_client, "LINK-PERM-001")

    created = link_scene(
        app_client,
        block["id"],
        {"sceneId": "cog-demo-perm-001", "relationType": "coverage"},
        headers={"X-RS-Roles": "linkage_editor", "X-RS-Areas": "350703"},
    )

    assert created.status_code == 200
    assert created.json()["sceneId"] == "cog-demo-perm-001"


def test_scene_link_permission_is_required_for_linkage_writes(app_client, reload_platform_modules):
    app_client.post(
        "/api/admin/roles",
        json={
            "roleCode": "rights_editor",
            "name": "Rights editor",
            "status": "active",
            "permissions": ["forest.rights.manage"],
            "menuModules": ["rights"],
            "dataScopes": {},
            "properties": {},
        },
        headers={"X-RS-Roles": "admin"},
    )
    seed_catalog(reload_platform_modules, "cog-demo-perm-002")
    block = create_block(app_client, "LINK-PERM-002")

    denied = link_scene(
        app_client,
        block["id"],
        {"sceneId": "cog-demo-perm-002", "relationType": "coverage"},
        headers={"X-RS-Roles": "rights_editor", "X-RS-Areas": "350703"},
    )

    assert denied.status_code == 403
    assert "forest.linkages.manage" in denied.json()["detail"]


def test_scene_links_reject_nonexistent_scene_id(app_client):
    block = create_block(app_client, "LINK-MISSING-SCENE-001")

    response = link_scene(
        app_client,
        block["id"],
        {"sceneId": "cog-demo-missing", "relationType": "coverage"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Scene not found"}


def test_create_scene_link_rejects_hidden_scene_for_current_context(app_client, reload_platform_modules):
    seed_catalog(
        reload_platform_modules,
        {
            "id": "scene-open",
            "projectId": "project-alpha",
            "areaCode": "350703",
            "allowedRoles": ["operator"],
            "allowedUsers": ["alice"],
        },
        {
            "id": "scene-hidden-project",
            "projectId": "project-secret",
        },
        {
            "id": "scene-hidden-area",
            "areaCode": "350702",
        },
        {
            "id": "scene-hidden-role",
            "allowedRoles": ["gis-admin"],
        },
        {
            "id": "scene-hidden-user",
            "allowedUsers": ["bob"],
        },
    )
    block = create_block(app_client, "LINK-SCENE-CREATE-VIS-001")
    allowed_headers = {
        "X-RS-Roles": "operator",
        "X-RS-Projects": "project-alpha",
        "X-RS-Areas": "350703",
        "X-RS-User": "alice",
    }

    visible = link_scene(
        app_client,
        block["id"],
        {"sceneId": "scene-open", "relationType": "coverage"},
        headers=allowed_headers,
    )
    hidden_project = link_scene(
        app_client,
        block["id"],
        {"sceneId": "scene-hidden-project", "relationType": "coverage"},
        headers=allowed_headers,
    )
    hidden_area = link_scene(
        app_client,
        block["id"],
        {"sceneId": "scene-hidden-area", "relationType": "coverage"},
        headers=allowed_headers,
    )
    hidden_role = link_scene(
        app_client,
        block["id"],
        {"sceneId": "scene-hidden-role", "relationType": "coverage"},
        headers=allowed_headers,
    )
    hidden_user = link_scene(
        app_client,
        block["id"],
        {"sceneId": "scene-hidden-user", "relationType": "coverage"},
        headers=allowed_headers,
    )

    assert visible.status_code == 200
    for response in (hidden_project, hidden_area, hidden_role, hidden_user):
        assert response.status_code == 403
        assert response.json() == {"detail": "Scene is not visible for current context"}


def test_scene_links_match_committed_wildcard_role_visibility_semantics(app_client, reload_platform_modules):
    seed_catalog(
        reload_platform_modules,
        {
            "id": "scene-wildcard",
            "projectId": "project-alpha",
            "areaCode": "350703",
            "allowedRoles": ["*"],
        },
    )
    forest_scene_links_module = reload_scene_links_module(reload_platform_modules)
    block = create_block(app_client, "LINK-SCENE-WILDCARD-001")
    operator_context = AuthContext(
        user="alice",
        roles={"operator"},
        projects={"project-alpha"},
        areas={"350703"},
    )
    wildcard_context = AuthContext(
        user="alice",
        roles={"*"},
        projects={"project-alpha"},
        areas={"350703"},
    )
    operator_headers = {"X-RS-Roles": "operator", "X-RS-Projects": "project-alpha", "X-RS-Areas": "350703"}
    wildcard_headers = {"X-RS-Roles": "*", "X-RS-Projects": "project-alpha", "X-RS-Areas": "350703"}

    assert forest_scene_links_module.scene_allowed(
        {
            "id": "scene-wildcard",
            "projectId": "project-alpha",
            "areaCode": "350703",
            "allowedRoles": ["*"],
        },
        operator_context,
    ) is False
    assert forest_scene_links_module.scene_allowed(
        {
            "id": "scene-wildcard",
            "projectId": "project-alpha",
            "areaCode": "350703",
            "allowedRoles": ["*"],
        },
        wildcard_context,
    ) is True

    operator_created = link_scene(
        app_client,
        block["id"],
        {"sceneId": "scene-wildcard", "relationType": "coverage"},
        headers=operator_headers,
    )
    wildcard_created = link_scene(
        app_client,
        block["id"],
        {"sceneId": "scene-wildcard", "relationType": "coverage"},
        headers=wildcard_headers,
    )
    operator_listed = list_links(app_client, block["id"], headers=operator_headers)
    wildcard_listed = list_links(app_client, block["id"], headers=wildcard_headers)
    operator_deleted = delete_scene_link(
        app_client,
        block["id"],
        "scene-wildcard",
        headers=operator_headers,
    )
    wildcard_deleted = delete_scene_link(
        app_client,
        block["id"],
        "scene-wildcard",
        headers=wildcard_headers,
    )

    assert operator_created.status_code == 403
    assert operator_created.json() == {"detail": "Scene is not visible for current context"}
    assert wildcard_created.status_code == 200
    assert wildcard_created.json() == {
        "forestBlockId": block["id"],
        "sceneId": "scene-wildcard",
        "relationType": "coverage",
        "capturedAt": None,
        "confidence": None,
    }
    assert operator_listed.status_code == 200
    assert operator_listed.json() == {"items": [], "total": 0}
    assert wildcard_listed.status_code == 200
    assert wildcard_listed.json() == {
        "items": [
            {
                "forestBlockId": block["id"],
                "sceneId": "scene-wildcard",
                "relationType": "coverage",
                "capturedAt": None,
                "confidence": None,
            }
        ],
        "total": 1,
    }
    assert operator_deleted.status_code == 403
    assert operator_deleted.json() == {"detail": "Scene is not visible for current context"}
    assert wildcard_deleted.status_code == 200
    assert wildcard_deleted.json() == {"ok": True, "deleted": 1}


def test_list_scene_links_filters_hidden_scenes_for_current_context(app_client, reload_platform_modules):
    seed_catalog(
        reload_platform_modules,
        {
            "id": "scene-open",
            "projectId": "project-alpha",
            "areaCode": "350703",
            "allowedRoles": ["operator"],
            "allowedUsers": ["alice"],
        },
        {"id": "scene-hidden-project", "projectId": "project-secret"},
        {"id": "scene-hidden-area", "areaCode": "350702"},
        {"id": "scene-hidden-role", "allowedRoles": ["gis-admin"]},
        {"id": "scene-hidden-user", "allowedUsers": ["bob"]},
    )
    block = create_block(app_client, "LINK-SCENE-LIST-VIS-001")
    seed_scene_links(
        reload_platform_modules,
        {
            "forestBlockId": block["id"],
            "sceneId": "scene-open",
            "relationType": "coverage",
            "capturedAt": None,
            "confidence": None,
        },
        {
            "forestBlockId": block["id"],
            "sceneId": "scene-hidden-project",
            "relationType": "coverage",
            "capturedAt": None,
            "confidence": None,
        },
        {
            "forestBlockId": block["id"],
            "sceneId": "scene-hidden-area",
            "relationType": "coverage",
            "capturedAt": None,
            "confidence": None,
        },
        {
            "forestBlockId": block["id"],
            "sceneId": "scene-hidden-role",
            "relationType": "coverage",
            "capturedAt": None,
            "confidence": None,
        },
        {
            "forestBlockId": block["id"],
            "sceneId": "scene-hidden-user",
            "relationType": "coverage",
            "capturedAt": None,
            "confidence": None,
        },
    )

    allowed_headers = {
        "X-RS-Roles": "operator",
        "X-RS-Projects": "project-alpha",
        "X-RS-Areas": "350703",
        "X-RS-User": "alice",
    }
    listed = list_links(app_client, block["id"], headers=allowed_headers)

    assert listed.status_code == 200
    assert listed.json() == {
        "items": [
            {
                "forestBlockId": block["id"],
                "sceneId": "scene-open",
                "relationType": "coverage",
                "capturedAt": None,
                "confidence": None,
            }
        ],
        "total": 1,
    }


def test_delete_scene_link_rejects_hidden_scene_for_current_context(app_client, reload_platform_modules):
    seed_catalog(
        reload_platform_modules,
        {"id": "scene-open", "projectId": "project-alpha"},
        {"id": "scene-hidden", "projectId": "project-secret"},
    )
    block = create_block(app_client, "LINK-SCENE-DELETE-VIS-001")
    seed_scene_links(
        reload_platform_modules,
        {
            "forestBlockId": block["id"],
            "sceneId": "scene-open",
            "relationType": "coverage",
            "capturedAt": None,
            "confidence": None,
        },
        {
            "forestBlockId": block["id"],
            "sceneId": "scene-hidden",
            "relationType": "coverage",
            "capturedAt": None,
            "confidence": None,
        },
    )

    allowed_headers = {
        "X-RS-Roles": "operator",
        "X-RS-Projects": "project-alpha",
        "X-RS-User": "alice",
    }

    hidden_deleted = delete_scene_link(
        app_client,
        block["id"],
        "scene-hidden",
        headers=allowed_headers,
    )
    visible_deleted = delete_scene_link(
        app_client,
        block["id"],
        "scene-open",
        headers=allowed_headers,
    )
    listed = list_links(app_client, block["id"], headers={"X-RS-Roles": "admin", "X-RS-Projects": "project-secret"})

    assert hidden_deleted.status_code == 403
    assert hidden_deleted.json() == {"detail": "Scene is not visible for current context"}
    assert visible_deleted.status_code == 200
    assert visible_deleted.json() == {"ok": True, "deleted": 1}
    assert {(item["sceneId"], item["relationType"]) for item in listed.json()["items"]} == {
        ("scene-hidden", "coverage"),
    }


def test_postgis_list_scene_links_returns_api_shape(monkeypatch, reload_platform_modules):
    forest_scene_links_module = reload_scene_links_module(reload_platform_modules)
    block_id = "8ab8cd2e-f574-4fd8-bdf6-b7788e632111"
    cursor = FakeCursor(
        fetchall_result=[
            (block_id, "scene-a", "coverage", "2026-06-01", 0.75),
            (block_id, "scene-b", "orthophoto", None, None),
        ]
    )
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, cursor=cursor, connect_calls=connect_calls)

    monkeypatch.setattr(forest_scene_links_module, "use_postgis", lambda: True)
    monkeypatch.setattr(
        forest_scene_links_module,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql://smart-bamboo"),
    )

    items = forest_scene_links_module.scene_links_for_block(block_id)

    assert items == [
        {
            "forestBlockId": block_id,
            "sceneId": "scene-a",
            "relationType": "coverage",
            "capturedAt": "2026-06-01",
            "confidence": 0.75,
        },
        {
            "forestBlockId": block_id,
            "sceneId": "scene-b",
            "relationType": "orthophoto",
            "capturedAt": None,
            "confidence": None,
        },
    ]
    assert connect_calls == ["postgresql://smart-bamboo"]
    assert cursor.executed == [
        (
            "SELECT forest_block_id::text, scene_id, relation_type, captured_at, confidence "
            "FROM forest_block_scene_links WHERE forest_block_id = %s ORDER BY created_at DESC, scene_id, relation_type",
            (block_id,),
        )
    ]


def test_postgis_create_and_delete_scene_links_use_database_storage(monkeypatch, reload_platform_modules):
    forest_scene_links_module = reload_scene_links_module(reload_platform_modules)
    block_id = "8ab8cd2e-f574-4fd8-bdf6-b7788e632222"
    create_cursor = FakeCursor()
    delete_cursor = FakeCursor(rowcount=2)
    cursors = [create_cursor, delete_cursor]
    connect_calls: list[str] = []

    def fake_connect(database_url: str):
        connect_calls.append(database_url)
        return FakeConnection(cursors.pop(0))

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fake_connect))
    monkeypatch.setattr(forest_scene_links_module, "use_postgis", lambda: True)
    monkeypatch.setattr(
        forest_scene_links_module,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql://smart-bamboo"),
    )
    monkeypatch.setattr(
        forest_scene_links_module,
        "require_visible_block",
        lambda block_id, context: {"id": block_id},
    )
    monkeypatch.setattr(
        forest_scene_links_module,
        "require_catalog_scene",
        lambda scene_id: {"id": scene_id},
    )

    context = AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set())
    created = forest_scene_links_module.create_forest_block_scene_link(
        block_id,
        forest_scene_links_module.ForestSceneLinkIn(
            sceneId="scene-a",
            relationType="coverage",
            capturedAt="2026-06-12",
            confidence=0.98,
        ),
        context=context,
    )
    deleted = forest_scene_links_module.delete_forest_block_scene_link(
        block_id,
        "scene-a",
        relationType="",
        context=context,
    )

    assert created == {
        "forestBlockId": block_id,
        "sceneId": "scene-a",
        "relationType": "coverage",
        "capturedAt": "2026-06-12",
        "confidence": 0.98,
    }
    assert deleted == {"ok": True, "deleted": 2}
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo"]
    assert create_cursor.executed == [
        (
            "INSERT INTO forest_block_scene_links ( forest_block_id, scene_id, relation_type, captured_at, confidence ) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (forest_block_id, scene_id, relation_type) DO UPDATE "
            "SET captured_at = EXCLUDED.captured_at, confidence = EXCLUDED.confidence, created_at = now()",
            (block_id, "scene-a", "coverage", "2026-06-12", 0.98),
        )
    ]
    assert delete_cursor.executed == [
        (
            "DELETE FROM forest_block_scene_links WHERE forest_block_id = %s AND scene_id = %s",
            (block_id, "scene-a"),
        )
    ]


def test_postgis_link_storage_still_rejects_scene_missing_from_json_catalog(
    isolated_env, monkeypatch, reload_platform_modules
):
    seed_catalog(reload_platform_modules, "scene-in-catalog")
    monkeypatch.setenv("REMOTE_SENSING_CATALOG_BACKEND", "postgis")
    monkeypatch.setenv("REMOTE_SENSING_DATABASE_URL", "postgresql://remote-sensing")
    forest_scene_links_module = reload_scene_links_module(reload_platform_modules)
    cursor = FakeCursor(fetchone_result=("scene-only-in-db",))
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, cursor=cursor, connect_calls=connect_calls)
    monkeypatch.setattr(forest_scene_links_module, "use_postgis", lambda: True)
    monkeypatch.setattr(
        forest_scene_links_module,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql://smart-bamboo"),
    )
    monkeypatch.setattr(
        forest_scene_links_module,
        "require_visible_block",
        lambda block_id, context: {"id": block_id},
    )

    context = AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set())

    with pytest.raises(HTTPException) as excinfo:
        forest_scene_links_module.create_forest_block_scene_link(
            "8ab8cd2e-f574-4fd8-bdf6-b7788e632223",
            forest_scene_links_module.ForestSceneLinkIn(
                sceneId="scene-only-in-db",
                relationType="coverage",
            ),
            context=context,
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Scene not found"
    assert connect_calls == []
    assert cursor.executed == []


def test_postgis_link_storage_inserts_when_scene_exists_in_json_catalog(
    isolated_env, monkeypatch, reload_platform_modules
):
    seed_catalog(reload_platform_modules, "scene-in-catalog")
    monkeypatch.setenv("REMOTE_SENSING_CATALOG_BACKEND", "postgis")
    monkeypatch.setenv("REMOTE_SENSING_DATABASE_URL", "postgresql://remote-sensing")
    forest_scene_links_module = reload_scene_links_module(reload_platform_modules)
    cursor = FakeCursor(fetchone_result=("scene-in-catalog",))
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, cursor=cursor, connect_calls=connect_calls)
    monkeypatch.setattr(forest_scene_links_module, "use_postgis", lambda: True)
    monkeypatch.setattr(
        forest_scene_links_module,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql://smart-bamboo"),
    )
    monkeypatch.setattr(
        forest_scene_links_module,
        "require_visible_block",
        lambda block_id, context: {"id": block_id},
    )

    context = AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set())
    created = forest_scene_links_module.create_forest_block_scene_link(
        "8ab8cd2e-f574-4fd8-bdf6-b7788e632224",
        forest_scene_links_module.ForestSceneLinkIn(
            sceneId="scene-in-catalog",
            relationType="coverage",
            capturedAt="2026-06-12",
            confidence=0.8,
        ),
        context=context,
    )

    assert created == {
        "forestBlockId": "8ab8cd2e-f574-4fd8-bdf6-b7788e632224",
        "sceneId": "scene-in-catalog",
        "relationType": "coverage",
        "capturedAt": "2026-06-12",
        "confidence": 0.8,
    }
    assert connect_calls == ["postgresql://smart-bamboo"]
    assert cursor.executed == [
        (
            "INSERT INTO forest_block_scene_links ( forest_block_id, scene_id, relation_type, captured_at, confidence ) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (forest_block_id, scene_id, relation_type) DO UPDATE "
            "SET captured_at = EXCLUDED.captured_at, confidence = EXCLUDED.confidence, created_at = now()",
            ("8ab8cd2e-f574-4fd8-bdf6-b7788e632224", "scene-in-catalog", "coverage", "2026-06-12", 0.8),
        )
    ]


def test_mysql_catalog_scene_lookup_uses_remote_catalog_database(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("REMOTE_SENSING_CATALOG_BACKEND", "mysql")
    catalog_url = "mysql://catalog_user:super-secret@catalog-db:3306/smart_bamboo"
    monkeypatch.setenv("REMOTE_SENSING_DATABASE_URL", catalog_url)
    forest_scene_links_module = reload_scene_links_module(reload_platform_modules)
    cursor = FakeCursor(
        fetchone_result=(
            json.dumps(
                {
                    "id": "scene-only-in-mysql",
                    "name": "MySQL scene",
                    "projectId": "project-alpha",
                    "areaCode": "350703",
                },
                ensure_ascii=False,
            ),
        )
    )
    connect_calls: list[str] = []

    def fake_mysql_connect(database_url: str | None = None):
        connect_calls.append(str(database_url or ""))
        return FakeConnection(cursor)

    monkeypatch.setattr(forest_scene_links_module, "mysql_connect", fake_mysql_connect)

    scene = forest_scene_links_module.require_catalog_scene("scene-only-in-mysql")

    assert scene == {
        "id": "scene-only-in-mysql",
        "name": "MySQL scene",
        "projectId": "project-alpha",
        "areaCode": "350703",
    }
    assert connect_calls == [catalog_url]
    assert cursor.executed == [
        (
            "SELECT scene FROM remote_sensing_scenes WHERE id = %s AND deleted_at IS NULL LIMIT 1",
            ("scene-only-in-mysql",),
        )
    ]


def test_postgis_scene_links_raise_503_when_connect_fails(monkeypatch, reload_platform_modules):
    forest_scene_links_module = reload_scene_links_module(reload_platform_modules)
    monkeypatch.setattr(forest_scene_links_module, "use_postgis", lambda: True)
    database_url = "postgresql://forest_user:super-secret@db.internal:5432/forest"
    monkeypatch.setattr(
        forest_scene_links_module,
        "get_settings",
        lambda: SimpleNamespace(database_url=database_url),
    )

    def fail_connect(database_url: str):
        raise RuntimeError(f"boom for {database_url}")

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fail_connect))

    with pytest.raises(HTTPException) as excinfo:
        forest_scene_links_module.scene_links_for_block("8ab8cd2e-f574-4fd8-bdf6-b7788e632333")

    assert excinfo.value.status_code == 503
    assert "forest scene links PostGIS database is unavailable" in excinfo.value.detail
    assert database_url not in excinfo.value.detail
    assert "super-secret" not in excinfo.value.detail
    assert "boom for" not in excinfo.value.detail


def test_postgis_delete_scene_links_scopes_relation_type_when_requested(monkeypatch, reload_platform_modules):
    forest_scene_links_module = reload_scene_links_module(reload_platform_modules)
    cursor = FakeCursor(rowcount=1)
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, cursor=cursor, connect_calls=connect_calls)
    monkeypatch.setattr(
        forest_scene_links_module,
        "get_settings",
        lambda: SimpleNamespace(database_url="postgresql://smart-bamboo"),
    )

    deleted = forest_scene_links_module.delete_scene_links_postgis(
        "8ab8cd2e-f574-4fd8-bdf6-b7788e632225",
        "scene-a",
        "orthophoto",
    )

    assert deleted == 1
    assert connect_calls == ["postgresql://smart-bamboo"]
    assert cursor.executed == [
        (
            "DELETE FROM forest_block_scene_links WHERE forest_block_id = %s AND scene_id = %s AND relation_type = %s",
            ("8ab8cd2e-f574-4fd8-bdf6-b7788e632225", "scene-a", "orthophoto"),
        )
    ]


def test_postgis_list_scene_links_filters_hidden_scenes_for_current_context(monkeypatch, reload_platform_modules):
    forest_scene_links_module = reload_scene_links_module(reload_platform_modules)
    block_id = "8ab8cd2e-f574-4fd8-bdf6-b7788e632334"
    seed_catalog(
        reload_platform_modules,
        {"id": "scene-open", "projectId": "project-alpha", "allowedRoles": ["operator"]},
        {"id": "scene-hidden", "projectId": "project-secret"},
    )
    monkeypatch.setattr(forest_scene_links_module, "use_postgis", lambda: True)
    monkeypatch.setattr(
        forest_scene_links_module,
        "require_visible_block",
        lambda block_id, context: {"id": block_id},
    )
    monkeypatch.setattr(
        forest_scene_links_module,
        "list_scene_links_postgis",
        lambda block_id: [
            {
                "forestBlockId": block_id,
                "sceneId": "scene-open",
                "relationType": "coverage",
                "capturedAt": None,
                "confidence": None,
            },
            {
                "forestBlockId": block_id,
                "sceneId": "scene-hidden",
                "relationType": "coverage",
                "capturedAt": None,
                "confidence": None,
            },
        ],
    )

    context = AuthContext(user="alice", roles={"operator"}, projects={"project-alpha"}, areas=set())
    response = forest_scene_links_module.list_forest_block_scene_links(block_id, context=context)

    assert response == {
        "items": [
            {
                "forestBlockId": block_id,
                "sceneId": "scene-open",
                "relationType": "coverage",
                "capturedAt": None,
                "confidence": None,
            }
        ],
        "total": 1,
    }
