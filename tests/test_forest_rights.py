from __future__ import annotations

import importlib
import io

from server.modules.auth import AuthContext
from tests.test_forest_blocks import FakeCursor, install_fake_psycopg
from tests.test_imports import ovobj_bytes


def sample_right_payload() -> dict[str, object]:
    return {
        "archiveCode": "ARCH-001",
        "certificateNo": "CERT-001",
        "holder": "Xiaoqiao Village Committee",
        "certificateType": "forest-right",
        "rightType": "contract-management",
        "rightStart": "2026-01-01",
        "rightEnd": "2036-12-31",
        "contractNo": "CONTRACT-001",
        "archiveStatus": "complete",
        "areaMu": 56.0,
        "linkedBlockCodes": ["BLOCK-001"],
        "properties": {"source": {"fileName": "manual"}},
    }


def reload_forest_rights_module(reload_platform_modules):
    reload_platform_modules()
    import server.modules.forest_rights as forest_rights_module

    importlib.reload(forest_rights_module)
    return forest_rights_module


def postgis_right_row(code: str = "ARCH-PG-001") -> dict[str, object]:
    return {
        "id": "9ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        "archive_code": code,
        "certificate_no": "CERT-PG-001",
        "holder": "PostGIS Holder",
        "certificate_type": "forest-right",
        "right_type": "contract-management",
        "ownership_type": "collective",
        "right_start": "2026-01-01",
        "right_end": "2036-12-31",
        "contract_no": "CONTRACT-PG-001",
        "circulation_status": None,
        "archive_status": "complete",
        "registrar": None,
        "missing_items": None,
        "area_mu": 56.0,
        "county_code": "350703",
        "county_name": "Jianyang",
        "town_code": "350703101",
        "town_name": "Masha",
        "village_code": None,
        "village_name": None,
        "linked_block_ids": [],
        "linked_block_codes": ["BLOCK-PG-001"],
        "documents": [],
        "properties": {"source": {"fileName": "pg"}},
        "created_at": "2026-07-07T00:00:00+00:00",
        "updated_at": "2026-07-07T00:00:00+00:00",
        "deleted_at": None,
    }


def test_postgis_create_forest_right_uses_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    forest_rights_module = reload_forest_rights_module(reload_platform_modules)
    duplicate_cursor = FakeCursor(fetchone_result=None)
    insert_cursor = FakeCursor()
    version_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [duplicate_cursor, insert_cursor, version_cursor], connect_calls)

    created = forest_rights_module.create_forest_right(
        forest_rights_module.ForestRightIn(**sample_right_payload()),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert created.archiveCode == "ARCH-001"
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo", "postgresql://smart-bamboo"]
    assert "FROM forest_rights" in duplicate_cursor.executed[0][0]
    assert "INSERT INTO forest_rights" in insert_cursor.executed[0][0]
    assert insert_cursor.executed[0][1][1] == "ARCH-001"
    assert "INSERT INTO forest_right_versions" in version_cursor.executed[0][0]
    assert version_cursor.executed[0][1][2] == "create"


def test_postgis_load_and_save_rights_use_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    forest_rights_module = reload_forest_rights_module(reload_platform_modules)
    insert_cursor = FakeCursor()
    select_cursor = FakeCursor(fetchall_result=[postgis_right_row("ARCH-PG-LOAD")])
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [insert_cursor, select_cursor], connect_calls)

    right = forest_rights_module.normalize_right(sample_right_payload())
    forest_rights_module.save_rights([right])
    loaded = forest_rights_module.load_all_rights()

    assert loaded[0]["archiveCode"] == "ARCH-PG-LOAD"
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo"]
    assert "INSERT INTO forest_rights" in insert_cursor.executed[0][0]
    assert "FROM forest_rights" in select_cursor.executed[0][0]


def test_postgis_list_right_filters_are_applied_in_database(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    forest_rights_module = reload_forest_rights_module(reload_platform_modules)
    list_cursor = FakeCursor(fetchall_result=[postgis_right_row("ARCH-PG-FILTER")])
    count_cursor = FakeCursor(fetchone_result=(1,))
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [list_cursor, count_cursor], connect_calls)

    response = forest_rights_module.list_forest_rights(
        forest_rights_module.ForestRightFilters(
            q="holder",
            archiveStatus="complete",
            linkedBlockCode="BLOCK-PG-001",
            limit=20,
            offset=5,
        )
    )

    list_sql, list_params = list_cursor.executed[0]
    count_sql, count_params = count_cursor.executed[0]
    assert response["total"] == 1
    assert response["items"][0]["archiveCode"] == "ARCH-PG-FILTER"
    assert "archive_status = %s" in list_sql
    assert "linked_block_codes ? %s" in list_sql
    assert "ILIKE" in list_sql
    assert "LIMIT %s OFFSET %s" in list_sql
    assert list_params[-2:] == (20, 5)
    assert "SELECT COUNT(*) FROM forest_rights" in count_sql
    assert count_params[:2] == ("complete", "BLOCK-PG-001")


def test_postgis_patch_and_delete_forest_right_use_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    forest_rights_module = reload_forest_rights_module(reload_platform_modules)
    select_for_patch = FakeCursor(fetchall_result=[postgis_right_row("ARCH-PG-PATCH")])
    update_cursor = FakeCursor()
    patch_version_cursor = FakeCursor()
    select_for_delete = FakeCursor(fetchall_result=[postgis_right_row("ARCH-PG-PATCH")])
    delete_cursor = FakeCursor()
    delete_version_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(
        monkeypatch,
        [select_for_patch, update_cursor, patch_version_cursor, select_for_delete, delete_cursor, delete_version_cursor],
        connect_calls,
    )

    patched = forest_rights_module.patch_forest_right(
        "9ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        forest_rights_module.ForestRightPatch(holder="Updated PostGIS Holder"),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )
    deleted = forest_rights_module.delete_forest_right(
        "9ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert patched.holder == "Updated PostGIS Holder"
    assert deleted["ok"] is True
    assert "FROM forest_rights" in select_for_patch.executed[0][0]
    assert "INSERT INTO forest_rights" in update_cursor.executed[0][0]
    assert "INSERT INTO forest_right_versions" in patch_version_cursor.executed[0][0]
    assert patch_version_cursor.executed[0][1][2] == "update"
    assert "INSERT INTO forest_rights" in delete_cursor.executed[0][0]
    assert "INSERT INTO forest_right_versions" in delete_version_cursor.executed[0][0]
    assert delete_version_cursor.executed[0][1][2] == "delete"


def test_deleted_forest_right_can_be_listed_and_restored(app_client):
    created = app_client.post(
        "/api/forest-rights",
        json=sample_right_payload() | {"archiveCode": "ARCH-RESTORE-001", "certificateNo": "CERT-RESTORE-001"},
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    right_id = created.json()["id"]

    deleted = app_client.delete(
        f"/api/forest-rights/{right_id}",
        headers={"X-RS-Roles": "admin"},
    )
    hidden = app_client.get("/api/forest-rights?q=ARCH-RESTORE-001")
    deleted_list = app_client.get(
        "/api/forest-rights?q=ARCH-RESTORE-001&includeDeleted=true",
        headers={"X-RS-Roles": "admin"},
    )
    denied_restore = app_client.post(
        f"/api/forest-rights/{right_id}/restore",
        headers={"X-RS-Roles": "forest.blocks.manage"},
    )
    restored = app_client.post(
        f"/api/forest-rights/{right_id}/restore",
        headers={"X-RS-Roles": "admin"},
    )
    active_again = app_client.get("/api/forest-rights?q=ARCH-RESTORE-001")

    assert deleted.status_code == 200
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0
    assert deleted_list.status_code == 200
    assert deleted_list.json()["total"] == 1
    assert deleted_list.json()["items"][0]["deletedAt"]
    assert denied_restore.status_code == 403
    assert "forest.rights.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    assert restored.json()["ok"] is True
    assert restored.json()["restored"] == right_id
    assert restored.json()["right"]["deletedAt"] is None
    assert active_again.status_code == 200
    assert active_again.json()["total"] == 1


def test_forest_right_versions_capture_create_update_delete_and_restore(app_client):
    created = app_client.post(
        "/api/forest-rights",
        json=sample_right_payload() | {"archiveCode": "ARCH-VERSION-001", "certificateNo": "CERT-VERSION-001"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "creator"},
    )
    right_id = created.json()["id"]
    patched = app_client.patch(
        f"/api/forest-rights/{right_id}",
        json={"holder": "Versioned Holder", "archiveStatus": "review"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "editor"},
    )
    deleted = app_client.delete(
        f"/api/forest-rights/{right_id}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "deleter"},
    )
    restored = app_client.post(
        f"/api/forest-rights/{right_id}/restore",
        headers={"X-RS-Roles": "admin", "X-RS-User": "restorer"},
    )

    denied = app_client.get(
        f"/api/forest-rights/{right_id}/versions",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    versions = app_client.get(
        f"/api/forest-rights/{right_id}/versions",
        headers={"X-RS-Roles": "admin"},
    )

    assert created.status_code == 200
    assert patched.status_code == 200
    assert deleted.status_code == 200
    assert restored.status_code == 200
    assert denied.status_code == 403
    assert "forest.rights.view" in denied.json()["detail"]
    assert versions.status_code == 200
    body = versions.json()
    assert body["total"] == 4
    assert [item["changeType"] for item in body["items"]] == ["restore", "delete", "update", "create"]
    update_version = next(item for item in body["items"] if item["changeType"] == "update")
    assert update_version["createdBy"] == "editor"
    assert update_version["snapshot"]["holder"] == "Versioned Holder"
    assert update_version["snapshot"]["archiveStatus"] == "review"
    assert update_version["snapshot"]["archiveCode"] == "ARCH-VERSION-001"


def test_forest_right_can_rollback_to_previous_version(app_client):
    created = app_client.post(
        "/api/forest-rights",
        json=sample_right_payload() | {"archiveCode": "ARCH-ROLLBACK-001", "certificateNo": "CERT-ROLLBACK-001"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "creator"},
    )
    right_id = created.json()["id"]
    app_client.patch(
        f"/api/forest-rights/{right_id}",
        json={"holder": "Changed Holder", "areaMu": 88.0, "archiveStatus": "review"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "editor"},
    )
    versions = app_client.get(
        f"/api/forest-rights/{right_id}/versions",
        headers={"X-RS-Roles": "admin"},
    )
    create_version = next(item for item in versions.json()["items"] if item["changeType"] == "create")

    denied = app_client.post(
        f"/api/forest-rights/{right_id}/rollback",
        json={"versionId": create_version["id"]},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    rolled_back = app_client.post(
        f"/api/forest-rights/{right_id}/rollback",
        json={"versionId": create_version["id"]},
        headers={"X-RS-Roles": "admin", "X-RS-User": "rollbacker"},
    )
    current = app_client.get(f"/api/forest-rights/{right_id}")
    after_versions = app_client.get(
        f"/api/forest-rights/{right_id}/versions",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert rolled_back.status_code == 200
    assert rolled_back.json()["ok"] is True
    assert rolled_back.json()["right"]["holder"] == "Xiaoqiao Village Committee"
    assert rolled_back.json()["right"]["areaMu"] == 56.0
    assert rolled_back.json()["right"]["archiveStatus"] == "complete"
    assert current.json()["holder"] == "Xiaoqiao Village Committee"
    assert current.json()["areaMu"] == 56.0
    assert after_versions.json()["items"][0]["changeType"] == "rollback"
    assert after_versions.json()["items"][0]["createdBy"] == "rollbacker"
    assert after_versions.json()["items"][0]["sourceVersionId"] == create_version["id"]


def test_truncated_mysql_right_version_preserves_current_block_relations_on_rollback(monkeypatch):
    from server.modules import forest_rights

    current = forest_rights.normalize_right(
        sample_right_payload()
        | {
            "id": "right-large-001",
            "archiveCode": "ARCH-LARGE-001",
            "linkedBlockIds": ["block-id-1", "block-id-2"],
            "linkedBlockCodes": ["BLOCK-001", "BLOCK-002"],
        }
    )
    version = {
        "id": "version-summary-001",
        "snapshot": {
            **current,
            "holder": "Historical Holder",
            "linkedBlockIds": [],
            "linkedBlockCodes": [],
            "properties": {"linkedBlockCount": 1200, "linkedTargetsTruncated": True},
        },
    }
    saved: list[dict] = []
    monkeypatch.setattr(forest_rights, "find_right_any_state", lambda *_args, **_kwargs: current)
    monkeypatch.setattr(forest_rights, "find_right_version", lambda *_args, **_kwargs: version)
    monkeypatch.setattr(forest_rights, "save_right", lambda right: saved.append(right))
    monkeypatch.setattr(
        forest_rights,
        "record_right_version",
        lambda *_args, **_kwargs: {"id": "rollback-version-001"},
    )

    response = forest_rights.rollback_forest_right(
        "right-large-001",
        forest_rights.ForestRightRollbackRequest(versionId="version-summary-001"),
        context=AuthContext(user="admin", roles={"admin"}, projects=set(), areas=set()),
    )

    assert response["right"]["holder"] == "Historical Holder"
    assert saved[0]["linkedBlockIds"] == ["block-id-1", "block-id-2"]
    assert saved[0]["linkedBlockCodes"] == ["BLOCK-001", "BLOCK-002"]


def test_forest_right_action_permissions_control_each_write_operation(app_client):
    created = app_client.post(
        "/api/forest-rights",
        json=sample_right_payload() | {"archiveCode": "ARCH-ACTION-001", "certificateNo": "CERT-ACTION-001"},
        headers={"X-RS-Roles": "forest.rights.create", "X-RS-User": "creator"},
    )

    assert created.status_code == 200
    right_id = created.json()["id"]

    denied_patch = app_client.patch(
        f"/api/forest-rights/{right_id}",
        json={"archiveStatus": "review"},
        headers={"X-RS-Roles": "forest.rights.create"},
    )
    patched = app_client.patch(
        f"/api/forest-rights/{right_id}",
        json={"archiveStatus": "review"},
        headers={"X-RS-Roles": "forest.rights.update", "X-RS-User": "editor"},
    )
    versions = app_client.get(
        f"/api/forest-rights/{right_id}/versions",
        headers={"X-RS-Roles": "forest.rights.view"},
    )
    create_version = next(item for item in versions.json()["items"] if item["changeType"] == "create")
    denied_rollback = app_client.post(
        f"/api/forest-rights/{right_id}/rollback",
        json={"versionId": create_version["id"]},
        headers={"X-RS-Roles": "forest.rights.update"},
    )
    rolled_back = app_client.post(
        f"/api/forest-rights/{right_id}/rollback",
        json={"versionId": create_version["id"]},
        headers={"X-RS-Roles": "forest.rights.rollback", "X-RS-User": "rollbacker"},
    )
    denied_delete = app_client.delete(
        f"/api/forest-rights/{right_id}",
        headers={"X-RS-Roles": "forest.rights.update"},
    )
    deleted = app_client.delete(
        f"/api/forest-rights/{right_id}",
        headers={"X-RS-Roles": "forest.rights.delete", "X-RS-User": "deleter"},
    )
    denied_restore = app_client.post(
        f"/api/forest-rights/{right_id}/restore",
        headers={"X-RS-Roles": "forest.rights.delete"},
    )
    restored = app_client.post(
        f"/api/forest-rights/{right_id}/restore",
        headers={"X-RS-Roles": "forest.rights.restore", "X-RS-User": "restorer"},
    )

    assert denied_patch.status_code == 403
    assert "forest.rights.update" in denied_patch.json()["detail"]
    assert patched.status_code == 200
    assert versions.status_code == 200
    assert denied_rollback.status_code == 403
    assert "forest.rights.rollback" in denied_rollback.json()["detail"]
    assert rolled_back.status_code == 200
    assert denied_delete.status_code == 403
    assert "forest.rights.delete" in denied_delete.json()["detail"]
    assert deleted.status_code == 200
    assert denied_restore.status_code == 403
    assert "forest.rights.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    assert restored.json()["right"]["deletedAt"] is None


def test_forest_rights_archive_crud_is_independent_from_forest_blocks(app_client):
    created = app_client.post(
        "/api/forest-rights",
        json=sample_right_payload(),
        headers={"X-RS-Roles": "admin"},
    )

    assert created.status_code == 200
    body = created.json()
    assert body["archiveCode"] == "ARCH-001"
    assert body["holder"] == "Xiaoqiao Village Committee"
    assert body["linkedBlockCodes"] == ["BLOCK-001"]

    listed = app_client.get("/api/forest-rights?q=CERT-001")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    blocks = app_client.get("/api/forest-blocks?q=ARCH-001")
    assert blocks.status_code == 200
    assert blocks.json()["total"] == 0

    patched = app_client.patch(
        f"/api/forest-rights/{body['id']}",
        json={"holder": "Updated Holder", "linkedBlockCodes": ["BLOCK-001", "BLOCK-002"]},
        headers={"X-RS-Roles": "admin"},
    )

    assert patched.status_code == 200
    assert patched.json()["holder"] == "Updated Holder"
    assert patched.json()["linkedBlockCodes"] == ["BLOCK-001", "BLOCK-002"]


def test_forest_rights_filter_by_linked_block_code(app_client):
    created = app_client.post(
        "/api/forest-rights",
        json=sample_right_payload(),
        headers={"X-RS-Roles": "admin"},
    )

    assert created.status_code == 200

    linked = app_client.get("/api/forest-rights?linkedBlockCode=BLOCK-001")
    unlinked = app_client.get("/api/forest-rights?linkedBlockCode=BLOCK-404")

    assert linked.status_code == 200
    assert linked.json()["total"] == 1
    assert unlinked.status_code == 200
    assert unlinked.json()["total"] == 0


def test_import_ovobj_creates_linked_forest_right_archive(app_client):
    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("xiaoqiao-shangtun.ovobj", io.BytesIO(ovobj_bytes()), "application/octet-stream")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert imported.status_code == 200
    assert imported.json()["validRows"] == 1

    rights = app_client.get("/api/forest-rights?q=0350783105206GDYMSY03631")
    assert rights.status_code == 200
    assert rights.json()["total"] == 1
    archive = rights.json()["items"][0]
    assert archive["certificateNo"] == "0350783105206GDYMSY03631"
    assert archive["holder"] == "Jianou Xiaoqiao Shangtun Village Committee"
    assert archive["linkedBlockCodes"] == ["0350783105206GDYMSY03631"]
    assert archive["archiveStatus"] == "complete"
