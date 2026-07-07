from __future__ import annotations

import json

from tests.test_forest_blocks import sample_block_payload


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


def test_link_scene_to_forest_block_lists_and_persists(app_client, reload_platform_modules):
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


def test_duplicate_scene_relation_upserts_in_place(app_client):
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


def test_delete_scene_links_supports_relation_type_and_full_scene_removal(app_client):
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


def test_scene_links_require_visible_block_for_read_and_write(app_client):
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


def test_scene_links_require_write_access_for_mutations(app_client):
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
