from __future__ import annotations

import importlib
import io
import json
import re
from pathlib import Path

import pytest

from server.modules.auth import AuthContext
from server.modules.auth_store import (
    create_session,
    credential_for_user,
    new_credential,
    save_credential,
    session_for_token,
    utc_now,
)
from server.modules.passwords import hash_password, verify_password
from tests.test_forest_blocks import FakeCursor, install_fake_psycopg


def sample_role(code: str = "forestry_operator") -> dict[str, object]:
    return {
        "roleCode": code,
        "name": "Forestry Operator",
        "status": "active",
        "permissions": ["forest.blocks.manage", "forest.rights.manage"],
        "menuModules": ["blocks", "rights"],
        "dataScopes": {"areas": ["350703"]},
        "properties": {"note": "field team"},
    }


def sample_user(username: str = "field_worker") -> dict[str, object]:
    return {
        "username": username,
        "displayName": "Field Worker",
        "status": "active",
        "roles": ["forest_user_role"],
        "dataScopes": {"areas": ["350703"]},
        "properties": {"phone": "13800000000"},
    }


def seed_legacy_role(role: dict[str, object]) -> dict[str, object]:
    from server.modules import admin_roles

    stored = admin_roles.normalize_role(role)
    roles = admin_roles.load_all_roles()
    roles.append(stored)
    admin_roles.save_roles(roles)
    return stored


def postgis_role_row(code: str = "role_pg") -> dict[str, object]:
    return {
        "id": "5ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        "role_code": code,
        "name": "PostGIS Role",
        "status": "active",
        "permissions": ["forest.blocks.manage"],
        "menu_modules": ["blocks"],
        "data_scopes": {"areas": ["350703"]},
        "properties": {"note": "pg"},
        "created_at": "2026-07-07T00:00:00+00:00",
        "updated_at": "2026-07-07T00:00:00+00:00",
        "deleted_at": None,
    }


def postgis_user_row(username: str = "user_pg") -> dict[str, object]:
    return {
        "id": "6ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        "username": username,
        "display_name": "PostGIS User",
        "status": "active",
        "roles": ["forest_user_role"],
        "data_scopes": {"areas": ["350703"]},
        "properties": {"note": "pg-user"},
        "created_at": "2026-07-07T00:00:00+00:00",
        "updated_at": "2026-07-07T00:00:00+00:00",
        "deleted_at": None,
    }


def reload_admin_roles_module(reload_platform_modules):
    reload_platform_modules()
    import server.modules.admin_roles as admin_roles_module

    importlib.reload(admin_roles_module)
    return admin_roles_module


def reload_admin_users_module(reload_platform_modules):
    reload_platform_modules()
    import server.modules.admin_users as admin_users_module

    importlib.reload(admin_users_module)
    return admin_users_module


def test_admin_roles_crud_search_and_soft_delete(app_client):
    created = app_client.post(
        "/api/admin/roles",
        json=sample_role(),
        headers={"X-RS-Roles": "admin"},
    )

    assert created.status_code == 200
    role = created.json()
    assert role["roleCode"] == "forestry_operator"
    assert role["permissions"] == ["forest.blocks.manage", "forest.rights.manage"]
    assert role["menuModules"] == ["blocks", "rights"]
    assert role["dataScopes"] == {"areas": ["350703"]}

    view_headers = {"X-RS-Roles": "system.roles.view"}
    searched = app_client.get("/api/admin/roles?q=field%20team", headers=view_headers)
    filtered = app_client.get("/api/admin/roles?permission=forest.blocks.manage&menuModule=blocks", headers=view_headers)
    missing = app_client.get("/api/admin/roles?permission=map.layers.publish", headers=view_headers)

    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert filtered.json()["total"] == 1
    assert missing.json()["total"] == 0

    patched = app_client.patch(
        f"/api/admin/roles/{role['id']}",
        json={"permissions": ["map.layers.publish"], "menuModules": ["mapLayers"]},
        headers={"X-RS-Roles": "admin"},
    )

    assert patched.status_code == 200
    assert patched.json()["permissions"] == ["map.layers.publish"]
    assert patched.json()["menuModules"] == ["mapLayers"]

    deleted = app_client.delete(
        f"/api/admin/roles/{role['id']}",
        headers={"X-RS-Roles": "admin"},
    )
    listed_after_delete = app_client.get("/api/admin/roles", headers=view_headers)

    assert deleted.status_code == 200
    assert listed_after_delete.status_code == 200
    assert listed_after_delete.json()["total"] == 0


def test_role_crud_endpoints_use_independent_action_permissions(app_client):
    created = app_client.post(
        "/api/admin/roles",
        json=sample_role("granular_role_permissions"),
        headers={"X-RS-Roles": "system.roles.create"},
    )

    assert created.status_code == 200
    role_id = created.json()["id"]

    denied_patch = app_client.patch(
        f"/api/admin/roles/{role_id}",
        json={"name": "Denied update"},
        headers={"X-RS-Roles": "system.roles.create"},
    )
    assert denied_patch.status_code == 403
    assert "system.roles.update" in denied_patch.json()["detail"]

    patched = app_client.patch(
        f"/api/admin/roles/{role_id}",
        json={"name": "Updated role"},
        headers={"X-RS-Roles": "system.roles.update"},
    )
    assert patched.status_code == 200

    denied_delete = app_client.delete(
        f"/api/admin/roles/{role_id}",
        headers={"X-RS-Roles": "system.roles.update"},
    )
    assert denied_delete.status_code == 403
    assert "system.roles.delete" in denied_delete.json()["detail"]

    deleted = app_client.delete(
        f"/api/admin/roles/{role_id}",
        headers={"X-RS-Roles": "system.roles.delete"},
    )
    assert deleted.status_code == 200

    restored = app_client.post(
        f"/api/admin/roles/{role_id}/restore",
        headers={"X-RS-Roles": "system.roles.restore"},
    )
    assert restored.status_code == 200


def test_role_permission_catalog_exposes_granular_crud_actions(app_client):
    response = app_client.get(
        "/api/admin/permission-catalog",
        headers={"X-RS-Roles": "system.roles.view"},
    )

    assert response.status_code == 200
    body = response.json()
    codes = {item["code"] for item in body["permissions"]}
    assert {
        "system.roles.view",
        "system.roles.create",
        "system.roles.update",
        "system.roles.delete",
        "system.roles.restore",
        "system.roles.export",
    } <= codes
    assert {
        "system.roles.view",
        "system.roles.create",
        "system.roles.update",
        "system.roles.delete",
        "system.roles.restore",
        "system.roles.export",
    } <= set(body["permissionImplications"]["system.roles.manage"])


def test_deleted_admin_role_can_be_listed_and_restored(app_client):
    created = app_client.post(
        "/api/admin/roles",
        json=sample_role("restore_role"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    role = created.json()

    deleted = app_client.delete(
        f"/api/admin/roles/{role['id']}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    active_list = app_client.get("/api/admin/roles?q=restore_role", headers={"X-RS-Roles": "system.roles.view"})
    denied_list = app_client.get(
        "/api/admin/roles?q=restore_role&includeDeleted=true",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    deleted_list = app_client.get(
        "/api/admin/roles?q=restore_role&includeDeleted=true",
        headers={"X-RS-Roles": "admin"},
    )
    denied_restore = app_client.post(
        f"/api/admin/roles/{role['id']}/restore",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    restored = app_client.post(
        f"/api/admin/roles/{role['id']}/restore",
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )
    restored_active_list = app_client.get("/api/admin/roles?q=restore_role", headers={"X-RS-Roles": "system.roles.view"})

    assert created.status_code == 200
    assert deleted.status_code == 200
    assert active_list.status_code == 200
    assert active_list.json()["total"] == 0
    assert denied_list.status_code == 403
    assert "system.roles.view" in denied_list.json()["detail"]
    assert deleted_list.status_code == 200
    assert deleted_list.json()["total"] == 1
    assert deleted_list.json()["items"][0]["deletedAt"]
    assert denied_restore.status_code == 403
    assert "system.roles.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    body = restored.json()
    assert body["ok"] is True
    assert body["restored"] == role["id"]
    assert body["role"]["deletedAt"] is None
    assert body["role"]["properties"]["auditEvents"][-1]["action"] == "restore"
    assert body["role"]["properties"]["auditEvents"][-1]["actor"] == "bob"
    assert body["role"]["properties"]["auditEvents"][-1]["changedFields"] == ["deletedAt"]
    assert restored_active_list.json()["total"] == 1


def test_protected_write_endpoints_reject_missing_role_header(app_client):
    response = app_client.post(
        "/api/admin/roles",
        json=sample_role("missing_role_header"),
    )

    assert response.status_code == 403
    assert "system.roles.create" in response.json()["detail"]


def test_admin_role_changes_keep_audit_events_for_permission_configuration(app_client):
    from server.modules import admin_roles

    created = app_client.post(
        "/api/admin/roles",
        json=sample_role("audited_role"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )

    assert created.status_code == 200
    created_role = created.json()
    create_events = created_role["properties"]["auditEvents"]
    assert create_events[-1]["action"] == "create"
    assert create_events[-1]["actor"] == "alice"
    assert "permissions" in create_events[-1]["changedFields"]
    assert "menuModules" in create_events[-1]["changedFields"]

    patched = app_client.patch(
        f"/api/admin/roles/{created_role['id']}",
        json={
            "permissions": ["forest.blocks.manage", "map.layers.publish"],
            "menuModules": ["blocks", "mapLayers"],
        },
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )

    assert patched.status_code == 200
    update_events = patched.json()["properties"]["auditEvents"]
    assert [event["action"] for event in update_events] == ["create", "update"]
    assert update_events[-1]["actor"] == "bob"
    assert update_events[-1]["changedFields"] == ["menuModules", "permissions"]
    assert update_events[-1]["after"]["permissions"] == ["forest.blocks.manage", "map.layers.publish"]
    assert update_events[-1]["after"]["menuModules"] == ["blocks", "mapLayers"]

    deleted = app_client.delete(
        f"/api/admin/roles/{created_role['id']}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "carol"},
    )
    stored_role = next(role for role in admin_roles.load_all_roles() if role["id"] == created_role["id"])
    delete_events = stored_role["properties"]["auditEvents"]

    assert deleted.status_code == 200
    assert [event["action"] for event in delete_events] == ["create", "update", "delete"]
    assert delete_events[-1]["actor"] == "carol"
    assert delete_events[-1]["changedFields"] == ["deletedAt"]
    assert delete_events[-1]["after"]["deletedAt"] == stored_role["deletedAt"]


def test_admin_role_events_can_be_listed_across_roles(app_client):
    created = app_client.post(
        "/api/admin/roles",
        json=sample_role("event_ledger_role"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    role = created.json()
    app_client.patch(
        f"/api/admin/roles/{role['id']}",
        json={
            "permissions": ["forest.blocks.manage", "map.layers.publish"],
            "menuModules": ["blocks", "mapLayers"],
        },
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )
    app_client.delete(
        f"/api/admin/roles/{role['id']}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "carol"},
    )

    denied = app_client.get(
        "/api/admin/roles/events",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    listed = app_client.get("/api/admin/roles/events?limit=20", headers={"X-RS-Roles": "admin"})
    updated_only = app_client.get(
        "/api/admin/roles/events?action=update&q=map.layers.publish",
        headers={"X-RS-Roles": "admin"},
    )
    role_only = app_client.get(
        "/api/admin/roles/events?roleCode=event_ledger_role",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "system.roles.view" in denied.json()["detail"]
    assert listed.status_code == 200
    body = listed.json()
    assert body["limit"] == 20
    assert body["total"] == 3
    update_event = next(item for item in body["items"] if item["action"] == "update")
    assert update_event["eventId"]
    assert update_event["roleId"] == role["id"]
    assert update_event["roleCode"] == "event_ledger_role"
    assert update_event["actor"] == "bob"
    assert update_event["changedFields"] == ["menuModules", "permissions"]
    assert update_event["after"]["permissions"] == ["forest.blocks.manage", "map.layers.publish"]
    assert "map.layers.publish" in update_event["summary"]
    assert updated_only.status_code == 200
    assert updated_only.json()["total"] == 1
    assert role_only.status_code == 200
    assert role_only.json()["total"] == 3


def test_admin_role_events_can_be_exported_as_csv(app_client):
    created = app_client.post(
        "/api/admin/roles",
        json=sample_role("export_role_events"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    role = created.json()
    app_client.patch(
        f"/api/admin/roles/{role['id']}",
        json={
            "permissions": ["forest.blocks.manage", "map.layers.publish"],
            "menuModules": ["blocks", "mapLayers"],
        },
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )

    denied = app_client.get(
        "/api/admin/roles/events.csv",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    exported = app_client.get(
        "/api/admin/roles/events.csv?roleCode=export_role_events",
        headers={"X-RS-Roles": "system.roles.export"},
    )

    assert denied.status_code == 403
    assert "system.roles.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "attachment" in exported.headers["content-disposition"]
    csv_text = exported.text
    assert "eventId,roleId,roleCode,roleName,action,actor,at,changedFields,permissions,menuModules,summary" in csv_text
    assert "export_role_events" in csv_text
    assert "map.layers.publish" in csv_text
    assert "bob" in csv_text


def test_admin_role_permission_receipt_can_be_exported(app_client):
    payload = {
        **sample_role("export_role_receipt"),
        "permissions": ["forest.blocks.manage", "map.layers.publish"],
        "menuModules": ["blocks", "mapLayers"],
        "dataScopes": {
            "areas": ["350703"],
            "towns": ["350703101"],
            "villages": ["350703101001"],
            "blockCodes": ["FB-AUTH"],
        },
    }
    created = app_client.post(
        "/api/admin/roles",
        json=payload,
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    role = created.json()

    denied = app_client.get(
        f"/api/admin/roles/{role['id']}/permission-receipt.json",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    exported = app_client.get(
        f"/api/admin/roles/{role['id']}/permission-receipt.json",
        headers={"X-RS-Roles": "system.roles.export"},
    )

    assert denied.status_code == 403
    assert "system.roles.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "role-permission-receipt-export_role_receipt.json" in exported.headers["content-disposition"]
    body = exported.json()
    assert body["role"]["roleCode"] == "export_role_receipt"
    assert body["role"]["name"] == "Forestry Operator"
    assert body["dataScopes"]["areas"] == ["350703"]
    assert body["dataScopes"]["blockCodes"] == ["FB-AUTH"]
    assert "forest.blocks.create" in body["expandedPermissions"]
    assert "map.layers.view" in body["expandedPermissions"]
    assert body["menuDiagnostics"]["summary"]["effectiveMenuModules"] == 2
    assert body["menuDiagnostics"]["summary"]["blockedMenuModules"] == 0
    assert [item["key"] for item in body["menuDiagnostics"]["effectiveMenuModules"]] == ["blocks", "mapLayers"]
    assert body["exportedAt"]


def test_admin_role_permission_receipt_includes_effective_coverage_matrix(app_client):
    role = seed_legacy_role(
        sample_role("receipt_coverage_role")
        | {
            "permissions": ["forest.blocks.manage", "imagery.scenes.export"],
            "menuModules": ["blocks", "mapLayers"],
        }
    )

    exported = app_client.get(
        f"/api/admin/roles/{role['id']}/permission-receipt.json",
        headers={"X-RS-Roles": "system.roles.export"},
    )

    assert exported.status_code == 200
    coverage = exported.json()["effectivePermissionCoverage"]
    assert coverage["summary"] == {
        "totalModules": 3,
        "visibleMenuModules": 1,
        "blockedMenuModules": 1,
        "pendingMenuModules": 1,
        "grantedPermissionCount": 2,
        "missingPermissionCount": 8,
    }
    items = {item["key"]: item for item in coverage["items"]}
    assert items["blocks"]["state"] == "visible"
    assert items["blocks"]["entryPermission"] == "forest.blocks.view"
    assert "forest.blocks.manage" in items["blocks"]["grantedPermissions"]
    assert items["mapLayers"]["state"] == "blocked"
    assert items["mapLayers"]["missingEntryPermission"] == "map.layers.view"
    assert items["imagery"]["state"] == "pending"
    assert "imagery.scenes.export" in items["imagery"]["grantedPermissions"]


def test_admin_role_operation_queue_groups_blocked_empty_review_and_ready_roles(app_client):
    seed_legacy_role(
        {
            **sample_role("blocked_menu_role"),
            "name": "Blocked menu role",
            "permissions": [],
            "menuModules": ["blocks"],
        }
    )
    seed_legacy_role(
        {
            **sample_role("empty_config_role"),
            "name": "Empty role",
            "permissions": [],
            "menuModules": [],
        }
    )
    seed_legacy_role(
        {
            **sample_role("review_orphan_role"),
            "name": "Review orphan role",
            "permissions": ["map.layers.publish"],
            "menuModules": [],
        }
    )
    seed_legacy_role(
        {
            **sample_role("ready_permission_role"),
            "name": "Ready role",
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
        }
    )
    seed_legacy_role(
        {
            **sample_role("deleted_permission_role"),
            "permissions": [],
            "menuModules": ["blocks"],
            "deletedAt": "2026-07-09T00:00:00+08:00",
        }
    )

    denied = app_client.get("/api/admin/roles/operation-queue", headers={"X-RS-Roles": "business.farmers.manage"})
    response = app_client.get("/api/admin/roles/operation-queue?limit=1", headers={"X-RS-Roles": "admin"})

    assert denied.status_code == 403
    assert "system.roles.view" in denied.json()["detail"]
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["actionableQueueTotal"] == 3
    assert body["summary"]["operationQueueTotal"] == 4
    lanes = {lane["key"]: lane for lane in body["items"]}
    assert list(lanes) == ["blocked_roles", "review_roles", "empty_roles", "ready_roles"]
    assert lanes["blocked_roles"]["count"] == 1
    assert lanes["blocked_roles"]["items"][0]["roleCode"] == "blocked_menu_role"
    assert lanes["blocked_roles"]["items"][0]["riskLevel"] == "error"
    assert lanes["blocked_roles"]["items"][0]["requiredPermission"] == "system.roles.manage"
    assert "roleCode=blocked_menu_role" in lanes["blocked_roles"]["items"][0]["adminHref"]
    assert lanes["review_roles"]["count"] == 1
    assert lanes["review_roles"]["items"][0]["roleCode"] == "review_orphan_role"
    assert lanes["review_roles"]["items"][0]["riskLevel"] == "warning"
    assert lanes["empty_roles"]["count"] == 1
    assert lanes["ready_roles"]["count"] == 1
    assert lanes["ready_roles"]["items"][0]["roleCode"] == "ready_permission_role"
    assert "deleted_permission_role" not in json.dumps(body)


def test_admin_user_operation_queue_groups_role_scope_and_ready_users(app_client):
    seed_legacy_role(
        {
            **sample_role("valid_user_role"),
            "name": "Valid user role",
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
            "dataScopes": {"areas": ["350703"]},
        }
    )
    seed_legacy_role(
        {
            **sample_role("scope_empty_role"),
            "name": "Scope empty role",
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
            "dataScopes": {},
        }
    )
    seed_legacy_role(
        {
            **sample_role("paused_user_role"),
            "name": "Paused user role",
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
            "status": "paused",
        }
    )
    seed_legacy_role(
        {
            **sample_role("deleted_user_role"),
            "name": "Deleted user role",
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
            "deletedAt": "2026-07-09T00:00:00+08:00",
        }
    )

    user_payloads = [
        sample_user("broken_role_user")
        | {
            "displayName": "Broken Role User",
            "roles": ["missing_user_role", "paused_user_role", "deleted_user_role"],
            "dataScopes": {"areas": ["350703"]},
        },
        sample_user("missing_role_user") | {"displayName": "Missing Role User", "roles": [], "dataScopes": {"areas": ["350703"]}},
        sample_user("empty_scope_user") | {"displayName": "Empty Scope User", "roles": ["scope_empty_role"], "dataScopes": {}},
        sample_user("ready_scope_user") | {"displayName": "Ready Scope User", "roles": ["valid_user_role"], "dataScopes": {}},
    ]
    for payload in user_payloads:
        created = app_client.post("/api/admin/users", json=payload, headers={"X-RS-Roles": "admin"})
        assert created.status_code == 200
    deleted_user = app_client.post(
        "/api/admin/users",
        json=sample_user("deleted_queue_user") | {"roles": ["valid_user_role"]},
        headers={"X-RS-Roles": "admin"},
    ).json()
    app_client.delete(f"/api/admin/users/{deleted_user['id']}", headers={"X-RS-Roles": "admin"})

    denied = app_client.get("/api/admin/users/operation-queue", headers={"X-RS-Roles": "business.farmers.manage"})
    response = app_client.get("/api/admin/users/operation-queue?limit=1", headers={"X-RS-Roles": "admin"})

    assert denied.status_code == 403
    assert "system.users.view" in denied.json()["detail"]
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["actionableQueueTotal"] == 3
    assert body["summary"]["operationQueueTotal"] == 4
    lanes = {lane["key"]: lane for lane in body["items"]}
    assert list(lanes) == ["blocked_users", "review_users", "empty_scope_users", "ready_users"]
    assert lanes["blocked_users"]["count"] == 1
    assert lanes["blocked_users"]["items"][0]["username"] == "broken_role_user"
    assert lanes["blocked_users"]["items"][0]["riskLevel"] == "error"
    assert lanes["blocked_users"]["items"][0]["unknownRoleCount"] == 1
    assert lanes["blocked_users"]["items"][0]["invalidRoleCount"] == 2
    assert lanes["blocked_users"]["items"][0]["requiredPermission"] == "system.users.update"
    assert "username=broken_role_user" in lanes["blocked_users"]["items"][0]["adminHref"]
    assert lanes["review_users"]["count"] == 1
    assert lanes["review_users"]["items"][0]["username"] == "missing_role_user"
    assert lanes["review_users"]["items"][0]["riskLevel"] == "warning"
    assert lanes["empty_scope_users"]["count"] == 1
    assert lanes["empty_scope_users"]["items"][0]["username"] == "empty_scope_user"
    assert lanes["empty_scope_users"]["items"][0]["dataScopeValueCount"] == 0
    assert lanes["ready_users"]["count"] == 1
    assert lanes["ready_users"]["items"][0]["username"] == "ready_scope_user"
    assert "deleted_queue_user" not in json.dumps(body)


def test_admin_users_crud_search_soft_delete_and_restore(app_client):
    denied = app_client.post(
        "/api/admin/users",
        json=sample_user("denied_user"),
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    created = app_client.post(
        "/api/admin/users",
        json=sample_user("field_worker_001"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )

    assert denied.status_code == 403
    assert "system.users.create" in denied.json()["detail"]
    assert created.status_code == 200
    user = created.json()
    assert user["username"] == "field_worker_001"
    assert user["roles"] == ["forest_user_role"]
    assert user["dataScopes"] == {"areas": ["350703"]}
    assert user["properties"]["auditEvents"][-1]["action"] == "create"
    assert user["properties"]["auditEvents"][-1]["actor"] == "alice"

    searched = app_client.get(
        "/api/admin/users?q=field%20worker&role=forest_user_role",
        headers={"X-RS-Roles": "system.users.view"},
    )
    patched = app_client.patch(
        f"/api/admin/users/{user['id']}",
        json={"roles": ["forest_user_role", "map_publisher"], "displayName": "Updated Worker"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )
    deleted = app_client.delete(
        f"/api/admin/users/{user['id']}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "carol"},
    )
    active_list = app_client.get(
        "/api/admin/users?q=field_worker_001",
        headers={"X-RS-Roles": "system.users.view"},
    )
    deleted_list = app_client.get(
        "/api/admin/users?q=field_worker_001&includeDeleted=true",
        headers={"X-RS-Roles": "admin"},
    )
    restored = app_client.post(
        f"/api/admin/users/{user['id']}/restore",
        headers={"X-RS-Roles": "admin", "X-RS-User": "dave"},
    )

    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert patched.status_code == 200
    assert patched.json()["roles"] == ["forest_user_role", "map_publisher"]
    assert patched.json()["properties"]["auditEvents"][-1]["changedFields"] == ["displayName", "roles"]
    assert deleted.status_code == 200
    assert active_list.json()["total"] == 0
    assert deleted_list.status_code == 200
    assert deleted_list.json()["items"][0]["deletedAt"]
    assert restored.status_code == 200
    assert restored.json()["user"]["deletedAt"] is None
    assert restored.json()["user"]["properties"]["auditEvents"][-1]["action"] == "restore"


def test_user_crud_endpoints_use_independent_action_permissions(app_client):
    created = app_client.post(
        "/api/admin/users",
        json=sample_user("granular_user_permissions"),
        headers={"X-RS-Roles": "system.users.create"},
    )

    assert created.status_code == 200
    user_id = created.json()["id"]

    denied_patch = app_client.patch(
        f"/api/admin/users/{user_id}",
        json={"displayName": "Denied update"},
        headers={"X-RS-Roles": "system.users.create"},
    )
    assert denied_patch.status_code == 403
    assert "system.users.update" in denied_patch.json()["detail"]

    patched = app_client.patch(
        f"/api/admin/users/{user_id}",
        json={"displayName": "Updated user"},
        headers={"X-RS-Roles": "system.users.update"},
    )
    assert patched.status_code == 200

    deleted = app_client.delete(
        f"/api/admin/users/{user_id}",
        headers={"X-RS-Roles": "system.users.delete"},
    )
    assert deleted.status_code == 200

    restored = app_client.post(
        f"/api/admin/users/{user_id}/restore",
        headers={"X-RS-Roles": "system.users.restore"},
    )
    assert restored.status_code == 200


def test_password_reset_requires_independent_permission_and_revokes_sessions(app_client):
    created = app_client.post(
        "/api/admin/users",
        json=sample_user("password_reset_user"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    user = created.json()
    original = new_credential(user["id"], hash_password("Original-Bamboo-2026!"))
    original["failedLoginCount"] = 5
    original["lockedUntil"] = "2026-07-22T10:00:00+00:00"
    save_credential(original)
    token, _csrf, _session = create_session(user["id"], 1, utc_now(), "127.0.0.1", "pytest")
    temporary_password = "Temporary-Bamboo-2026!"

    denied = app_client.post(
        f"/api/admin/users/{user['id']}/set-password",
        json={"temporaryPassword": temporary_password},
        headers={"X-RS-Roles": "system.users.update"},
    )
    allowed = app_client.post(
        f"/api/admin/users/{user['id']}/set-password",
        json={"temporaryPassword": temporary_password},
        headers={"X-RS-Roles": "system.users.setPassword", "X-RS-User": "security_admin"},
    )
    credential = credential_for_user(user["id"])
    stored_user = app_client.get(
        f"/api/admin/users/{user['id']}", headers={"X-RS-Roles": "system.users.view"}
    ).json()

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json() == {"ok": True, "mustChangePassword": True}
    assert credential is not None
    assert credential["credentialVersion"] == 2
    assert credential["mustChangePassword"] is True
    assert credential["failedLoginCount"] == 0
    assert credential["lockedUntil"] is None
    assert verify_password(credential["passwordHash"], temporary_password)
    assert session_for_token(token, utc_now()) is None
    audit = stored_user["properties"]["auditEvents"][-1]
    serialized_audit = json.dumps(audit)
    assert audit["action"] == "set_password"
    assert audit["changedFields"] == ["passwordHash", "passwordChangedAt", "mustChangePassword", "failedLoginCount", "lockedUntil", "credentialVersion", "sessions"]
    assert temporary_password not in serialized_audit
    assert original["passwordHash"] not in serialized_audit
    assert credential["passwordHash"] not in serialized_audit
    assert token not in serialized_audit


def test_session_revocation_requires_independent_permission(app_client):
    created = app_client.post(
        "/api/admin/users",
        json=sample_user("session_revocation_user"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    user = created.json()
    first_token, _csrf, _session = create_session(user["id"], 1, utc_now(), "127.0.0.1", "pytest")
    second_token, _csrf, _session = create_session(user["id"], 1, utc_now(), "127.0.0.1", "pytest")

    denied = app_client.post(
        f"/api/admin/users/{user['id']}/revoke-sessions",
        headers={"X-RS-Roles": "system.users.update"},
    )
    allowed = app_client.post(
        f"/api/admin/users/{user['id']}/revoke-sessions",
        headers={"X-RS-Roles": "system.users.revokeSessions"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json() == {"ok": True, "revoked": 2}
    assert session_for_token(first_token, utc_now()) is None
    assert session_for_token(second_token, utc_now()) is None


@pytest.mark.parametrize("path,payload", [
    ("set-password", {"temporaryPassword": "Temporary-Bamboo-2026!"}),
    ("revoke-sessions", None),
])
def test_account_security_actions_roll_back_when_audit_write_fails(app_client, monkeypatch, path, payload):
    from server.modules import admin_users

    created = app_client.post(
        "/api/admin/users",
        json=sample_user(f"rollback_{path}"),
        headers={"X-RS-Roles": "admin"},
    )
    user = created.json()
    original = new_credential(user["id"], hash_password("Original-Bamboo-2026!"))
    save_credential(original)
    token, _csrf, _session = create_session(user["id"], 1, utc_now(), "127.0.0.1", "pytest")
    monkeypatch.setattr(
        admin_users,
        "append_user_audit_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit write failed")),
    )

    with pytest.raises(RuntimeError, match="audit write failed"):
        app_client.post(
            f"/api/admin/users/{user['id']}/{path}",
            json=payload,
            headers={"X-RS-Roles": "system.users.manage"},
        )

    credential = credential_for_user(user["id"])
    assert credential is not None
    assert credential["passwordHash"] == original["passwordHash"]
    assert credential["credentialVersion"] == original["credentialVersion"]
    assert session_for_token(token, utc_now()) is not None


@pytest.mark.parametrize("action", ["set_user_password", "revoke_sessions"])
def test_account_security_actions_reject_postgis_before_any_write(monkeypatch, action):
    from fastapi import HTTPException
    from server.modules import admin_users

    user = admin_users.normalize_user({"username": "postgis_security", "displayName": "PostGIS Security"})
    monkeypatch.setattr(admin_users, "use_postgis", lambda: True)
    monkeypatch.setattr(admin_users, "use_mysql", lambda: False)
    monkeypatch.setattr(admin_users, "find_user", lambda _user_id: (_ for _ in ()).throw(AssertionError("must not read or write")))

    with pytest.raises(HTTPException) as raised:
        if action == "set_user_password":
            admin_users.set_user_password(user["id"], admin_users.TemporaryPasswordIn(temporaryPassword="Temporary-Bamboo-2026!"), AuthContext(user="admin", roles={"admin"}, projects=set(), areas=set()))
        else:
            admin_users.revoke_sessions(user["id"], AuthContext(user="admin", roles={"admin"}, projects=set(), areas=set()))

    assert raised.value.status_code == 501
    assert raised.value.detail == "Human credential administration requires MySQL or JSON development storage"


def test_json_security_transaction_uses_the_shared_database_lock():
    from server.modules import auth_store, database

    assert auth_store.database.JSON_STORE_LOCK is database.JSON_STORE_LOCK


def test_json_store_lock_survives_database_reload_and_business_modules_resolve_it_dynamically():
    from server.modules import admin_roles, admin_users, auth_store, database

    lock = database.JSON_STORE_LOCK
    reloaded_database = importlib.reload(database)

    assert reloaded_database.JSON_STORE_LOCK is lock
    for module in (auth_store, admin_users, admin_roles):
        assert module.database.JSON_STORE_LOCK is lock


def test_mysql_password_reset_rolls_back_when_audit_fails(monkeypatch):
    from server.modules import admin_users

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class Connection:
        def __init__(self): self.committed = False; self.rolled_back = False
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def commit(self): self.committed = True
        def rollback(self): self.rolled_back = True

    connection = Connection()
    user = admin_users.normalize_user({"username": "mysql_rollback", "displayName": "MySQL Rollback"})
    original = new_credential(user["id"], hash_password("Original-Bamboo-2026!"))
    monkeypatch.setattr(admin_users, "use_mysql", lambda: True)
    monkeypatch.setattr(admin_users, "mysql_connect", lambda: connection)
    monkeypatch.setattr(admin_users, "mysql_credential_for_user", lambda *_args, **_kwargs: original)
    monkeypatch.setattr(admin_users, "write_mysql_credential", lambda *_args: None)
    monkeypatch.setattr(admin_users, "revoke_user_sessions_mysql", lambda *_args: 1)
    monkeypatch.setattr(admin_users, "append_user_audit_event", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit failed")))

    with pytest.raises(RuntimeError, match="audit failed"):
        admin_users.apply_account_security_action(user, AuthContext(user="admin", roles={"admin"}, projects=set(), areas=set()), temporary_password="Temporary-Bamboo-2026!")

    assert connection.rolled_back is True
    assert connection.committed is False


def test_user_permission_catalog_exposes_granular_crud_actions(app_client):
    response = app_client.get(
        "/api/admin/permission-catalog",
        headers={"X-RS-Roles": "system.roles.view"},
    )

    assert response.status_code == 200
    body = response.json()
    codes = {item["code"] for item in body["permissions"]}
    expected = {
        "system.users.view",
        "system.users.create",
        "system.users.update",
        "system.users.delete",
        "system.users.restore",
        "system.users.export",
        "system.users.setPassword",
        "system.users.revokeSessions",
    }
    assert expected <= codes
    assert expected <= set(body["permissionImplications"]["system.users.manage"])


def test_admin_user_events_can_be_listed_across_users(app_client):
    created = app_client.post(
        "/api/admin/users",
        json=sample_user("event_user_001"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    user = created.json()
    app_client.patch(
        f"/api/admin/users/{user['id']}",
        json={"roles": ["forest_user_role", "map_publisher"], "displayName": "Event Worker"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )
    app_client.delete(
        f"/api/admin/users/{user['id']}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "carol"},
    )

    denied = app_client.get(
        "/api/admin/users/events",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    listed = app_client.get("/api/admin/users/events?limit=20", headers={"X-RS-Roles": "admin"})
    updated_only = app_client.get(
        "/api/admin/users/events?action=update&q=map_publisher",
        headers={"X-RS-Roles": "admin"},
    )
    user_only = app_client.get(
        "/api/admin/users/events?username=event_user_001",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "system.users.view" in denied.json()["detail"]
    assert listed.status_code == 200
    body = listed.json()
    assert body["limit"] == 20
    assert body["total"] == 3
    update_event = next(item for item in body["items"] if item["action"] == "update")
    assert update_event["eventId"]
    assert update_event["userId"] == user["id"]
    assert update_event["username"] == "event_user_001"
    assert update_event["actor"] == "bob"
    assert update_event["changedFields"] == ["displayName", "roles"]
    assert update_event["after"]["roles"] == ["forest_user_role", "map_publisher"]
    assert "map_publisher" in update_event["summary"]
    assert updated_only.status_code == 200
    assert updated_only.json()["total"] == 1
    assert user_only.status_code == 200
    assert user_only.json()["total"] == 3


def test_admin_user_events_can_be_exported_as_csv(app_client):
    created = app_client.post(
        "/api/admin/users",
        json=sample_user("export_user_events"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    user = created.json()
    app_client.patch(
        f"/api/admin/users/{user['id']}",
        json={"roles": ["forest_user_role", "map_publisher"], "displayName": "Export Worker"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )

    denied = app_client.get(
        "/api/admin/users/events.csv",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    exported = app_client.get(
        "/api/admin/users/events.csv?username=export_user_events",
        headers={"X-RS-Roles": "system.users.export"},
    )

    assert denied.status_code == 403
    assert "system.users.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "attachment" in exported.headers["content-disposition"]
    csv_text = exported.text
    assert "eventId,userId,username,displayName,action,actor,at,changedFields,roles,dataScopes,summary" in csv_text
    assert "export_user_events" in csv_text
    assert "map_publisher" in csv_text
    assert "bob" in csv_text


def test_user_role_assignment_grants_effective_permissions_and_page_menu(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("forest_user_role") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
            "dataScopes": {"areas": ["350703"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    created_user = app_client.post(
        "/api/admin/users",
        json=sample_user("field_worker_002") | {
            "roles": ["forest_user_role"],
            "dataScopes": {"projects": ["bamboo-gis"]},
        },
        headers={"X-RS-Roles": "admin"},
    )

    effective = app_client.get(
        "/api/admin/effective-permissions",
        headers={"X-RS-User": "field_worker_002"},
    )
    allowed_write = app_client.post(
        "/api/forest-blocks",
        json={"blockCode": "USER-ROLE-BLOCK-001", "name": "User role block", "countyCode": "350703"},
        headers={"X-RS-User": "field_worker_002"},
    )
    denied_write = app_client.post(
        "/api/forest-blocks",
        json={"blockCode": "USER-ROLE-BLOCK-002", "name": "User out of scope block", "countyCode": "350724"},
        headers={"X-RS-User": "field_worker_002"},
    )

    assert created_user.status_code == 200
    assert effective.status_code == 200
    body = effective.json()
    assert body["user"] == "field_worker_002"
    assert body["roles"] == ["forest_user_role"]
    assert {
        "forest.blocks.manage",
        "forest.blocks.view",
        "forest.blocks.create",
        "forest.blocks.update",
        "forest.blocks.delete",
        "forest.blocks.restore",
        "forest.blocks.rollback",
    }.issubset(set(body["permissions"]))
    assert body["menuModules"] == ["blocks"]
    assert body["dataScopes"] == {"areas": ["350703"], "projects": ["bamboo-gis"]}
    assert [item["key"] for item in body["visibleMenuModules"]] == ["blocks"]
    assert allowed_write.status_code == 200
    assert denied_write.status_code == 403
    assert "Area access denied" in denied_write.json()["detail"]


def test_admin_can_preview_effective_permissions_for_user_account(app_client):
    seed_legacy_role(
        sample_role("user_preview_role") | {
            "permissions": ["forest.blocks.manage", "imports.forestBlocks.manage"],
            "menuModules": ["blocks", "imports", "mapLayers"],
            "dataScopes": {"areas": ["350703"], "projects": ["zhushan-core"]},
        }
    )
    created_user = app_client.post(
        "/api/admin/users",
        json=sample_user("preview_worker_001") | {
            "roles": ["user_preview_role"],
            "dataScopes": {"areas": ["350784"], "projects": ["zhushan-mobile"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    user_id = created_user.json()["id"]

    denied = app_client.get(
        f"/api/admin/users/{user_id}/effective-permissions",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    preview = app_client.get(
        f"/api/admin/users/{user_id}/effective-permissions",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "system.users.view" in denied.json()["detail"]
    assert preview.status_code == 200
    body = preview.json()
    assert body["user"] == "preview_worker_001"
    assert body["roles"] == ["user_preview_role"]
    assert {
        "forest.blocks.manage",
        "forest.blocks.view",
        "forest.blocks.create",
        "forest.blocks.update",
        "forest.blocks.delete",
        "forest.blocks.restore",
        "forest.blocks.rollback",
        "imports.forestBlocks.manage",
    }.issubset(set(body["permissions"]))
    assert body["configuredMenuModules"] == ["blocks", "imports", "mapLayers"]
    assert body["menuModules"] == ["blocks", "imports"]
    assert [item["key"] for item in body["visibleMenuModules"]] == ["blocks", "imports"]
    assert body["blockedMenuModules"][0]["key"] == "mapLayers"
    assert body["blockedMenuModules"][0]["missingEntryPermission"] == "map.layers.view"
    assert body["dataScopes"] == {
        "areas": ["350703", "350784"],
        "projects": ["zhushan-core", "zhushan-mobile"],
    }


def test_admin_user_access_receipt_can_be_exported(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("user_receipt_role") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
            "dataScopes": {"areas": ["350703"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    created_user = app_client.post(
        "/api/admin/users",
        json=sample_user("export_access_worker") | {
            "roles": ["user_receipt_role"],
            "dataScopes": {"projects": ["bamboo-gis"], "blockCodes": ["FB-AUTH"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    user_id = created_user.json()["id"]

    denied = app_client.get(
        f"/api/admin/users/{user_id}/access-receipt.json",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    exported = app_client.get(
        f"/api/admin/users/{user_id}/access-receipt.json",
        headers={"X-RS-Roles": "system.users.export"},
    )

    assert denied.status_code == 403
    assert "system.users.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "user-access-receipt-export_access_worker.json" in exported.headers["content-disposition"]
    body = exported.json()
    assert body["receiptType"] == "user-effective-access"
    assert body["user"]["username"] == "export_access_worker"
    assert body["user"]["roles"] == ["user_receipt_role"]
    access = body["effectiveAccess"]
    assert access["user"] == "export_access_worker"
    assert access["roles"] == ["user_receipt_role"]
    assert access["menuModules"] == ["blocks"]
    assert [item["key"] for item in access["visibleMenuModules"]] == ["blocks"]
    assert "forest.blocks.create" in access["permissions"]
    assert access["dataScopes"] == {
        "areas": ["350703"],
        "projects": ["bamboo-gis"],
        "blockCodes": ["FB-AUTH"],
    }
    assert body["exportedAt"]


def test_admin_user_access_receipt_includes_effective_permission_coverage(app_client):
    seed_legacy_role(
        sample_role("user_receipt_coverage_role")
        | {
            "permissions": ["forest.blocks.manage", "imagery.scenes.export"],
            "menuModules": ["blocks", "mapLayers"],
        }
    )
    created_user = app_client.post(
        "/api/admin/users",
        json=sample_user("receipt_coverage_worker") | {"roles": ["user_receipt_coverage_role"]},
        headers={"X-RS-Roles": "admin"},
    )
    user_id = created_user.json()["id"]

    exported = app_client.get(
        f"/api/admin/users/{user_id}/access-receipt.json",
        headers={"X-RS-Roles": "system.users.export"},
    )

    assert exported.status_code == 200
    coverage = exported.json()["effectivePermissionCoverage"]
    assert coverage["summary"]["totalModules"] == 3
    assert coverage["summary"]["visibleMenuModules"] == 1
    assert coverage["summary"]["blockedMenuModules"] == 1
    assert coverage["summary"]["pendingMenuModules"] == 1
    items = {item["key"]: item for item in coverage["items"]}
    assert items["blocks"]["state"] == "visible"
    assert items["mapLayers"]["state"] == "blocked"
    assert items["mapLayers"]["missingEntryPermission"] == "map.layers.view"
    assert items["imagery"]["state"] == "pending"
    assert "imagery.scenes.export" in items["imagery"]["grantedPermissions"]


def test_admin_user_effective_permissions_flags_unknown_roles(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("known_preview_role") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    created_user = app_client.post(
        "/api/admin/users",
        json=sample_user("unknown_role_worker") | {
            "roles": ["known_preview_role", "missing_preview_role"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    user_id = created_user.json()["id"]

    preview = app_client.get(
        f"/api/admin/users/{user_id}/effective-permissions",
        headers={"X-RS-Roles": "admin"},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["roles"] == ["known_preview_role", "missing_preview_role"]
    assert {
        "forest.blocks.manage",
        "forest.blocks.view",
        "forest.blocks.create",
        "forest.blocks.update",
        "forest.blocks.delete",
        "forest.blocks.restore",
        "forest.blocks.rollback",
    }.issubset(set(body["permissions"]))
    assert [item["key"] for item in body["visibleMenuModules"]] == ["blocks"]
    assert body["unknownRoles"] == [
        {"roleCode": "missing_preview_role", "label": "missing_preview_role"}
    ]


def test_admin_can_preview_effective_permissions_for_unsaved_user_draft(app_client):
    seed_legacy_role(
        sample_role("draft_preview_role") | {
            "permissions": ["forest.blocks.manage", "imports.forestBlocks.manage"],
            "menuModules": ["blocks", "imports", "mapLayers"],
            "dataScopes": {"areas": ["350703"], "towns": ["350703101"]},
        }
    )

    denied = app_client.post(
        "/api/admin/users/effective-permissions/preview",
        json={"roles": ["draft_preview_role"], "dataScopes": {"areas": ["350784"]}},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    preview = app_client.post(
        "/api/admin/users/effective-permissions/preview",
        json={
            "username": "draft_worker",
            "status": "active",
            "roles": ["draft_preview_role", "missing_draft_role"],
            "dataScopes": {"areas": ["350784"], "projects": ["zhushan-mobile"]},
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "system.users.create" in denied.json()["detail"]
    assert "system.users.update" in denied.json()["detail"]
    assert preview.status_code == 200
    body = preview.json()
    assert body["user"] == "draft_worker"
    assert body["roles"] == ["draft_preview_role", "missing_draft_role"]
    assert {
        "forest.blocks.manage",
        "forest.blocks.view",
        "imports.forestBlocks.manage",
    }.issubset(set(body["permissions"]))
    assert body["configuredMenuModules"] == ["blocks", "imports", "mapLayers"]
    assert body["menuModules"] == ["blocks", "imports"]
    assert [item["key"] for item in body["visibleMenuModules"]] == ["blocks", "imports"]
    assert body["blockedMenuModules"][0]["key"] == "mapLayers"
    assert body["blockedMenuModules"][0]["missingEntryPermission"] == "map.layers.view"
    assert body["dataScopes"] == {
        "areas": ["350703", "350784"],
        "projects": ["zhushan-mobile"],
        "towns": ["350703101"],
    }
    assert body["unknownRoles"] == [
        {"roleCode": "missing_draft_role", "label": "missing_draft_role"}
    ]


def test_admin_user_effective_permissions_flags_inactive_and_deleted_roles(app_client):
    active_role = app_client.post(
        "/api/admin/roles",
        json=sample_role("active_preview_role") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    inactive_role = app_client.post(
        "/api/admin/roles",
        json=sample_role("paused_preview_role") | {
            "status": "paused",
            "permissions": ["map.layers.manage"],
            "menuModules": ["mapLayers"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    deleted_role = app_client.post(
        "/api/admin/roles",
        json=sample_role("deleted_preview_role") | {
            "permissions": ["imports.forestBlocks.manage"],
            "menuModules": ["imports"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    app_client.delete(
        f"/api/admin/roles/{deleted_role.json()['id']}",
        headers={"X-RS-Roles": "admin"},
    )
    created_user = app_client.post(
        "/api/admin/users",
        json=sample_user("invalid_role_worker") | {
            "roles": [
                "active_preview_role",
                "paused_preview_role",
                "deleted_preview_role",
                "missing_preview_role",
            ],
        },
        headers={"X-RS-Roles": "admin"},
    )
    user_id = created_user.json()["id"]

    preview = app_client.get(
        f"/api/admin/users/{user_id}/effective-permissions",
        headers={"X-RS-Roles": "admin"},
    )

    assert active_role.status_code == 200
    assert inactive_role.status_code == 200
    assert deleted_role.status_code == 200
    assert created_user.status_code == 200
    assert preview.status_code == 200
    body = preview.json()
    assert body["roles"] == [
        "active_preview_role",
        "paused_preview_role",
        "deleted_preview_role",
        "missing_preview_role",
    ]
    assert "forest.blocks.create" in body["permissions"]
    assert "map.layers.create" not in body["permissions"]
    assert "imports.forestBlocks.create" not in body["permissions"]
    assert body["menuModules"] == ["blocks"]
    assert body["unknownRoles"] == [{"roleCode": "missing_preview_role", "label": "missing_preview_role"}]
    assert body["invalidRoles"] == [
        {
            "roleCode": "paused_preview_role",
            "label": "Forestry Operator",
            "status": "paused",
            "reason": "inactive",
        },
        {
            "roleCode": "deleted_preview_role",
            "label": "Forestry Operator",
            "status": "deleted",
            "reason": "deleted",
        },
    ]


def test_admin_permission_catalog_lists_menu_modules_and_permissions(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    body = catalog.json()
    menu_modules = {item["key"]: item for item in body["menuModules"]}
    permissions = {item["code"]: item for item in body["permissions"]}
    menu_keys = [item["key"] for item in body["menuModules"]]
    permission_codes = [item["code"] for item in body["permissions"]]
    assert "blocks" in menu_keys
    assert "roles" in menu_keys
    assert "imports" in menu_keys
    assert "imagery" in menu_keys
    assert "forest.blocks.manage" in permission_codes
    assert "system.roles.manage" in permission_codes
    assert "system.roles.export" in permission_codes
    assert "system.users.export" in permission_codes
    assert "/api/admin/roles/operation-queue" in menu_modules["roles"]["apiScopes"]
    assert "/api/admin/roles/operation-queue" in permissions["system.roles.manage"]["apiScopes"]
    assert "imports.forestBlocks.view" in permission_codes
    assert "imports.forestBlocks.manage" in permission_codes
    assert "imports.forestBlocks.create" in permission_codes
    assert "imports.forestBlocks.review" in permission_codes
    assert "imports.forestBlocks.quality" in permission_codes
    assert "imports.forestBlocks.rollback" in permission_codes
    assert "imports.forestBlocks.delete" in permission_codes
    assert "imports.forestBlocks.restore" in permission_codes
    assert "imports.forestBlocks.export" in permission_codes
    assert "imports.sceneLayers.link" in permission_codes
    assert "imagery.scenes.view" in permission_codes
    assert "imagery.scenes.manage" in permission_codes
    assert "imagery.scenes.create" in permission_codes
    assert "imagery.scenes.update" in permission_codes
    assert "imagery.scenes.delete" in permission_codes
    assert "imagery.scenes.restore" in permission_codes
    assert "imagery.scenes.archive" in permission_codes
    assert "imagery.scenes.quality" in permission_codes
    assert "imagery.scenes.export" in permission_codes
    assert "imagery.tasks.retry" in permission_codes
    assert "imagery.tasks.cancel" in permission_codes
    assert "imagery.tasks.archive" in permission_codes
    assert "imagery.layers.publish" in permission_codes
    assert "business.stewardshipAgreements.manage" in permission_codes
    assert "business.franchiseBases.manage" in permission_codes
    assert "business.maintenanceTasks.manage" in permission_codes
    assert "business.workLogs.manage" in permission_codes
    assert "business.droneTasks.manage" in permission_codes
    assert "business.equipment.manage" in permission_codes
    assert "business.pestWarnings.manage" in permission_codes
    assert "business.materialServices.manage" in permission_codes
    assert "business.yieldForecasts.manage" in permission_codes
    assert "business.harvestPlans.manage" in permission_codes
    assert "business.incomeEstimates.manage" in permission_codes
    assert "business.performanceDashboards.manage" in permission_codes
    assert "business.carbonEstimates.manage" in permission_codes
    assert "business.tradeMatches.manage" in permission_codes
    assert "business.logisticsTraces.manage" in permission_codes
    assert "business.productQrcodes.manage" in permission_codes
    assert "business.supplyChainFinance.manage" in permission_codes
    assert "business.priceIndexes.manage" in permission_codes
    assert "business.mobileServiceChannels.manage" in permission_codes
    assert "stewardshipAgreements" in menu_keys
    assert "franchiseBases" in menu_keys
    assert "maintenanceTasks" in menu_keys
    assert "workLogs" in menu_keys
    assert "droneTasks" in menu_keys
    assert "equipment" in menu_keys
    assert "pestWarnings" in menu_keys
    assert "materialServices" in menu_keys
    assert "yieldForecasts" in menu_keys
    assert "harvestPlans" in menu_keys
    assert "incomeEstimates" in menu_keys
    assert "performanceDashboards" in menu_keys
    assert "carbonEstimates" in menu_keys
    assert "tradeMatches" in menu_keys
    assert "logisticsTraces" in menu_keys
    assert "productQrcodes" in menu_keys
    assert "supplyChainFinance" in menu_keys
    assert "priceIndexes" in menu_keys
    assert "mobileServiceChannels" in menu_keys
    assert next(item for item in body["menuModules"] if item["key"] == "imagery")["href"] == "admin-imagery.html"
    assert next(item for item in body["menuModules"] if item["key"] == "rights")["permission"] == "forest.rights.view"


def test_permission_catalog_exposes_stage_role_permission_presets(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    presets = catalog.json()["rolePresets"]
    presets_by_key = {item["key"]: item for item in presets}

    assert {"phase1-data-foundation", "phase2-operations", "phase3-decision", "phase4-industry-platform"}.issubset(
        presets_by_key
    )

    phase1 = presets_by_key["phase1-data-foundation"]
    assert {"blocks", "rights", "linkages", "mapLayers", "imports", "imagery"}.issubset(
        set(phase1["menuModules"])
    )
    assert "imports.forestBlocks.manage" in phase1["permissions"]
    assert "imports.forestBlocks.acceptance" in phase1["expandedPermissions"]
    assert "imagery.scenes.delivery" in phase1["expandedPermissions"]
    assert phase1["preview"]["riskLevel"] == "ready"
    assert phase1["preview"]["summary"]["effectiveMenuModules"] == len(phase1["menuModules"])

    phase2 = presets_by_key["phase2-operations"]
    assert "maintenanceTasks" in phase2["menuModules"]
    assert "business.maintenanceTasks.manage" in phase2["permissions"]
    assert "business.maintenanceTasks.view" in phase2["expandedPermissions"]


def test_permission_catalog_exposes_first_stage_closure_guides(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    closures = {item["key"]: item for item in catalog.json()["permissionClosures"]}

    delivery = closures["phase1-delivery-loop"]
    assert delivery["label"] == "成果入库与影像发布闭环"
    assert delivery["menuModules"] == ["imports", "imagery", "mapLayers"]
    assert delivery["permissions"] == [
        "imports.forestBlocks.manage",
        "imagery.scenes.manage",
        "map.layers.manage",
    ]
    assert "/api/imports/forest-blocks/workflow-summary" in delivery["workflowEndpoints"]
    assert "/api/scenes/workflow-summary" in delivery["workflowEndpoints"]
    assert "/api/scenes/operation-queue" in delivery["workflowEndpoints"]
    assert "/api/imports/forest-blocks/delivery-packages" in delivery["workflowEndpoints"]
    assert "/api/map-layers/dashboard" in delivery["workflowEndpoints"]
    assert delivery["preview"]["riskLevel"] == "ready"

    identity = closures["identity-access-loop"]
    assert identity["menuModules"] == ["roles", "users", "deployment"]
    assert identity["permissions"] == ["system.roles.manage", "system.users.manage", "system.deployment.view"]
    assert "/api/admin/roles/operation-queue" in identity["workflowEndpoints"]


def test_permission_catalog_exposes_granular_phase1_operation_closure_guides(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    closures = {item["key"]: item for item in catalog.json()["permissionClosures"]}
    expected_keys = {
        "phase1-import-acceptance-loop",
        "phase1-imagery-delivery-loop",
        "phase1-layer-publishing-loop",
    }
    assert expected_keys.issubset(closures)

    import_loop = closures["phase1-import-acceptance-loop"]
    assert import_loop["menuModules"] == ["imports"]
    assert import_loop["permissions"] == [
        "imports.forestBlocks.view",
        "imports.forestBlocks.create",
        "imports.forestBlocks.review",
        "imports.forestBlocks.quality",
        "imports.forestBlocks.acceptance",
        "imports.forestBlocks.export",
    ]
    assert "/api/imports/{batch_id}/review" in import_loop["workflowEndpoints"]
    assert "/api/imports/{batch_id}/acceptance" in import_loop["workflowEndpoints"]
    assert "/api/imports/{batch_id}/acceptance-receipt.json" in import_loop["workflowEndpoints"]
    assert import_loop["preview"]["riskLevel"] == "warning"
    assert import_loop["preview"]["summary"]["blockedMenuModules"] == 0
    assert "imports.forestBlocks.rollback" in import_loop["omittedPermissions"]
    assert "imports.forestBlocks.delete" in import_loop["omittedPermissions"]
    assert "imports.forestBlocks.restore" in import_loop["omittedPermissions"]

    imagery_loop = closures["phase1-imagery-delivery-loop"]
    assert imagery_loop["menuModules"] == ["imagery"]
    assert imagery_loop["permissions"] == [
        "imagery.scenes.view",
        "imagery.scenes.create",
        "imagery.scenes.update",
        "imagery.scenes.quality",
        "imagery.scenes.delivery",
        "imagery.scenes.export",
    ]
    assert "/api/scenes/{scene_id}/delivery" in imagery_loop["workflowEndpoints"]
    assert "/api/scenes/{scene_id}/delivery-receipt.json" in imagery_loop["workflowEndpoints"]
    assert "/api/scenes/{scene_id}/publication-receipt.json" in imagery_loop["workflowEndpoints"]
    assert imagery_loop["preview"]["riskLevel"] == "warning"
    assert imagery_loop["preview"]["summary"]["blockedMenuModules"] == 0
    assert "imagery.scenes.delete" in imagery_loop["omittedPermissions"]
    assert "imagery.scenes.restore" in imagery_loop["omittedPermissions"]

    layer_loop = closures["phase1-layer-publishing-loop"]
    assert layer_loop["menuModules"] == ["imports", "imagery", "mapLayers"]
    assert layer_loop["permissions"] == [
        "imports.forestBlocks.view",
        "imports.sceneLayers.link",
        "imagery.scenes.view",
        "imagery.layers.publish",
        "map.layers.view",
        "map.layers.create",
        "map.layers.update",
        "map.layers.publish",
        "map.layers.export",
    ]
    assert "/api/imports/{batch_id}/link-scene-layer" in layer_loop["workflowEndpoints"]
    assert "/api/scenes/{scene_id}/publish-layer" in layer_loop["workflowEndpoints"]
    assert "/api/map-layers/{record_id}/publish" in layer_loop["workflowEndpoints"]
    assert "/api/map-layers/{record_id}/publication-receipt.json" in layer_loop["workflowEndpoints"]
    assert layer_loop["preview"]["riskLevel"] == "warning"
    assert layer_loop["preview"]["summary"]["blockedMenuModules"] == 0
    assert layer_loop["preview"]["summary"]["permissionDependencyIssues"] == 0
    assert "map.layers.delete" in layer_loop["omittedPermissions"]
    assert "map.layers.restore" in layer_loop["omittedPermissions"]

    high_risk_permissions = {
        "imports.forestBlocks.manage",
        "imports.forestBlocks.rollback",
        "imports.forestBlocks.delete",
        "imports.forestBlocks.restore",
        "imagery.scenes.manage",
        "imagery.scenes.delete",
        "imagery.scenes.restore",
        "map.layers.manage",
        "map.layers.delete",
        "map.layers.restore",
    }
    for key in expected_keys:
        assert high_risk_permissions.isdisjoint(set(closures[key]["permissions"]))


def test_permission_closure_package_can_be_exported_for_role_reviews(app_client):
    denied = app_client.get(
        "/api/admin/permission-closures.json",
        headers={"X-RS-Roles": "system.users.manage"},
    )
    exported = app_client.get(
        "/api/admin/permission-closures.json",
        headers={"X-RS-Roles": "system.roles.export", "X-RS-User": "closure-exporter"},
    )

    assert denied.status_code == 403
    assert "system.roles.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "permission-closure-package.json" in exported.headers["content-disposition"]
    body = exported.json()
    assert body["receiptType"] == "permission-closure-package"
    assert body["exportedBy"] == "closure-exporter"
    assert body["exportPermission"] == "system.roles.export"
    assert body["summary"]["closureCount"] >= 5
    assert body["summary"]["phase1ClosureCount"] >= 4
    assert "system.roles.export" in body["permissionImplications"]["system.roles.manage"]
    closures = {item["key"]: item for item in body["permissionClosures"]}
    assert "/api/scenes/{scene_id}/publication-receipt.json" in closures["phase1-imagery-delivery-loop"]["workflowEndpoints"]
    assert "/api/map-layers/{record_id}/publication-receipt.json" in closures["phase1-layer-publishing-loop"]["workflowEndpoints"]
    assert "imports.forestBlocks.rollback" in closures["phase1-import-acceptance-loop"]["omittedPermissions"]
    assert closures["phase1-layer-publishing-loop"]["preview"]["riskLevel"] == "warning"
    assert closures["phase1-layer-publishing-loop"]["summary"]["expandedPermissionCount"] >= len(
        closures["phase1-layer-publishing-loop"]["permissions"]
    )


def test_admin_permission_catalog_returns_health_coverage_for_role_configuration(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    body = catalog.json()
    coverage = body["coverage"]
    summary = coverage["summary"]
    issues = coverage["issues"]

    assert coverage["riskLevel"] == "ready"
    assert summary["menuModuleTotal"] == len(body["menuModules"])
    assert summary["permissionTotal"] == len(body["permissions"])
    assert summary["matrixModuleTotal"] == sum(len(group["modules"]) for group in body["matrix"])
    assert summary["pagePermissionTotal"] >= len(body["menuModules"])
    assert summary["actionPermissionTotal"] > summary["pagePermissionTotal"]
    assert issues["missingPagePermissions"] == []
    assert issues["permissionsWithoutKnownModule"] == []
    assert issues["missingManageImplications"] == []


def test_admin_permission_catalog_covers_every_independent_admin_page(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    project_root = Path(__file__).resolve().parents[1]
    admin_pages = {path.name for path in project_root.glob("admin-*.html")}
    admin_pages.discard("admin-login.html")
    admin_pages.add("admin.html")
    catalog_hrefs = {item["href"] for item in catalog.json()["menuModules"]}
    missing_from_catalog = admin_pages - catalog_hrefs
    missing_files = catalog_hrefs - admin_pages
    assert missing_from_catalog == set()
    assert missing_files == set()


def test_admin_permission_catalog_covers_declared_button_permissions(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    project_root = Path(__file__).resolve().parents[1]
    declared_permissions: set[str] = set()
    for path in list(project_root.glob("admin-*.html")) + list(project_root.glob("admin-*.js")):
        text = path.read_text(encoding="utf-8")
        declared_permissions.update(
            permission
            for permission in re.findall(r'data-permission\s*=\s*"([^"$]+)"', text)
            if "." in permission
        )
        declared_permissions.update(
            permission
            for permission in re.findall(r"const\s+[A-Z_]*PERMISSION\s*=\s*\"([a-zA-Z0-9_.-]+)\"", text)
            if "." in permission
        )

    catalog_permissions = {item["code"] for item in catalog.json()["permissions"]}
    assert declared_permissions - catalog_permissions == set()


def test_admin_permission_catalog_returns_grouped_menu_permission_matrix(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    body = catalog.json()
    matrix = body["matrix"]
    modules = {
        module["key"]: module
        for group in matrix
        for module in group["modules"]
    }

    assert modules["imports"]["href"] == "admin-imports.html"
    assert modules["imports"]["permission"] == "imports.forestBlocks.view"
    assert "imports.forestBlocks.view" in modules["imports"]["permissions"]
    assert "imports.forestBlocks.manage" in modules["imports"]["permissions"]
    assert "imports.forestBlocks.create" in modules["imports"]["permissions"]
    assert "imports.forestBlocks.review" in modules["imports"]["permissions"]
    assert "imports.forestBlocks.quality" in modules["imports"]["permissions"]
    assert "imports.forestBlocks.rollback" in modules["imports"]["permissions"]
    assert "imports.forestBlocks.delete" in modules["imports"]["permissions"]
    assert "imports.forestBlocks.restore" in modules["imports"]["permissions"]
    assert "imports.forestBlocks.export" in modules["imports"]["permissions"]
    assert "imports.sceneLayers.link" in modules["imports"]["permissions"]
    assert modules["imagery"]["permission"] == "imagery.scenes.view"
    assert "imagery.scenes.view" in modules["imagery"]["permissions"]
    assert "imagery.scenes.manage" in modules["imagery"]["permissions"]
    assert "imagery.scenes.create" in modules["imagery"]["permissions"]
    assert "imagery.scenes.update" in modules["imagery"]["permissions"]
    assert "imagery.scenes.delete" in modules["imagery"]["permissions"]
    assert "imagery.scenes.restore" in modules["imagery"]["permissions"]
    assert "imagery.scenes.archive" in modules["imagery"]["permissions"]
    assert "imagery.scenes.quality" in modules["imagery"]["permissions"]
    assert "imagery.scenes.export" in modules["imagery"]["permissions"]
    assert "imagery.tasks.retry" in modules["imagery"]["permissions"]
    assert "imagery.tasks.cancel" in modules["imagery"]["permissions"]
    assert "imagery.tasks.archive" in modules["imagery"]["permissions"]
    assert "imagery.layers.publish" in modules["imagery"]["permissions"]
    assert modules["roles"]["href"] == "admin-roles.html"
    assert modules["roles"]["group"]


def test_permission_catalog_exposes_api_scopes_for_data_governance_modules(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})
    preview = app_client.post(
        "/api/admin/roles/preview",
        json={
            "menuModules": ["imports", "imagery", "mapLayers"],
            "permissions": ["imports.forestBlocks.manage", "imagery.scenes.manage", "map.layers.manage"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert catalog.status_code == 200
    assert preview.status_code == 200
    body = catalog.json()
    menu_modules = {module["key"]: module for module in body["menuModules"]}
    matrix_modules = {
        module["key"]: module
        for group in body["matrix"]
        for module in group["modules"]
    }
    preview_modules = {module["key"]: module for module in preview.json()["effectiveMenuModules"]}

    assert menu_modules["imports"]["dataDomain"] == "forest-imports"
    assert "/api/imports/forest-blocks" in menu_modules["imports"]["apiScopes"]
    assert "/api/imports/forest-blocks/batches" in menu_modules["imports"]["apiScopes"]
    assert "/api/imports/forest-blocks/operation-queue" in menu_modules["imports"]["apiScopes"]
    assert "/api/imports/forest-blocks/delivery-packages" in menu_modules["imports"]["apiScopes"]
    assert "/api/imports/forest-blocks/quality-issues" in menu_modules["imports"]["apiScopes"]
    assert menu_modules["imagery"]["dataDomain"] == "remote-sensing"
    assert "/api/scenes" in menu_modules["imagery"]["apiScopes"]
    assert "/api/tasks" in menu_modules["imagery"]["apiScopes"]
    assert "/api/scenes/operation-queue" in menu_modules["imagery"]["apiScopes"]
    assert "/api/scenes/quality-issues" in menu_modules["imagery"]["apiScopes"]
    assert matrix_modules["mapLayers"]["dataDomain"] == "map-publishing"
    assert "/api/map-layers" in matrix_modules["mapLayers"]["apiScopes"]
    assert preview_modules["imports"]["apiScopes"] == menu_modules["imports"]["apiScopes"]
    assert preview_modules["imagery"]["apiScopes"] == menu_modules["imagery"]["apiScopes"]


def test_permission_catalog_maps_forest_aggregate_api_to_block_view_permission(app_client):
    response = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert response.status_code == 200
    body = response.json()
    blocks_module = next(item for item in body["menuModules"] if item["key"] == "blocks")
    block_view = next(item for item in body["permissions"] if item["code"] == "forest.blocks.view")
    assert "/api/map/forest-blocks/aggregates" in blocks_module["apiScopes"]
    assert "/api/map/forest-blocks/aggregates" in block_view["apiScopes"]


def test_permission_catalog_maps_delivery_receipt_exports_to_export_permissions(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})
    preview = app_client.post(
        "/api/admin/roles/preview",
        json={
            "menuModules": ["imports", "imagery"],
            "permissions": [
                "imports.forestBlocks.view",
                "imports.forestBlocks.export",
                "imagery.scenes.view",
                "imagery.scenes.export",
            ],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert catalog.status_code == 200
    assert preview.status_code == 200
    body = catalog.json()
    permissions = {item["code"]: item for item in body["permissions"]}
    matrix_modules = {
        module["key"]: module
        for group in body["matrix"]
        for module in group["modules"]
    }

    import_export = permissions["imports.forestBlocks.export"]
    import_view = permissions["imports.forestBlocks.view"]
    import_acceptance = permissions["imports.forestBlocks.acceptance"]
    imagery_view = permissions["imagery.scenes.view"]
    imagery_export = permissions["imagery.scenes.export"]
    imagery_delivery = permissions["imagery.scenes.delivery"]
    assert import_export["label"] == "成果交付材料导出"
    assert imagery_export["label"] == "影像交付材料导出"
    assert "/api/imports/forest-blocks/operation-queue" in import_view["apiScopes"]
    assert "/api/imports/forest-blocks/delivery-packages" in import_view["apiScopes"]
    assert "/api/imports/{batch_id}/acceptance" in import_acceptance["apiScopes"]
    assert "/api/imports/forest-blocks/workflow-summary.json" in import_export["apiScopes"]
    assert "/api/imports/forest-blocks/delivery-packages.csv" in import_export["apiScopes"]
    assert "/api/imports/forest-blocks/delivery-packages.json" in import_export["apiScopes"]
    assert "/api/imports/{batch_id}/report.json" in import_export["apiScopes"]
    assert "/api/imports/{batch_id}/errors.csv" in import_export["apiScopes"]
    assert "/api/imports/{batch_id}/acceptance-receipt.json" in import_export["apiScopes"]
    assert "/api/imports/{batch_id}/delivery-package-receipt.json" in import_export["apiScopes"]
    assert "/api/scenes/operation-queue" in imagery_view["apiScopes"]
    assert "/api/scenes/{scene_id}/delivery" in imagery_delivery["apiScopes"]
    assert "/api/scenes/workflow-summary.json" in imagery_export["apiScopes"]
    assert "/api/scenes/events.csv" in imagery_export["apiScopes"]
    assert "/api/tasks/events.csv" in imagery_export["apiScopes"]
    assert "/api/scenes/{scene_id}/delivery-receipt.json" in imagery_export["apiScopes"]
    assert "/api/scenes/{scene_id}/publication-receipt.json" in imagery_export["apiScopes"]
    assert "/api/scenes/{scene_id}/publication-receipt.json" in matrix_modules["imagery"]["apiScopes"]

    import_matrix_export = next(
        entry
        for entry in matrix_modules["imports"]["permissionEntries"]
        if entry["code"] == "imports.forestBlocks.export"
    )
    imagery_matrix_export = next(
        entry
        for entry in matrix_modules["imagery"]["permissionEntries"]
        if entry["code"] == "imagery.scenes.export"
    )
    assert import_matrix_export["apiScopes"] == import_export["apiScopes"]
    assert imagery_matrix_export["apiScopes"] == imagery_export["apiScopes"]

    preview_coverage = {
        item["key"]: item
        for item in preview.json()["actionPermissionCoverage"]
    }
    preview_modules = {item["key"]: item for item in preview.json()["effectiveMenuModules"]}
    preview_import_export = next(
        item
        for item in preview_coverage["imports"]["grantedActionPermissions"]
        if item["code"] == "imports.forestBlocks.export"
    )
    preview_imagery_export = next(
        item
        for item in preview_coverage["imagery"]["grantedActionPermissions"]
        if item["code"] == "imagery.scenes.export"
    )
    assert "/api/imports/{batch_id}/acceptance-receipt.json" in preview_import_export["apiScopes"]
    assert "/api/imports/forest-blocks/delivery-packages.csv" in preview_import_export["apiScopes"]
    assert "/api/imports/forest-blocks/delivery-packages.json" in preview_import_export["apiScopes"]
    assert "/api/imports/forest-blocks/delivery-packages" in preview_modules["imports"]["apiScopes"]
    assert "/api/scenes/{scene_id}/delivery-receipt.json" in preview_imagery_export["apiScopes"]
    assert "/api/scenes/{scene_id}/publication-receipt.json" in preview_imagery_export["apiScopes"]
    assert "/api/scenes/{scene_id}/publication-receipt.json" in preview_modules["imagery"]["apiScopes"]
    missing_import_codes = [
        item["code"] for item in preview_coverage["imports"]["missingActionPermissions"]
    ]
    missing_imagery_codes = [
        item["code"] for item in preview_coverage["imagery"]["missingActionPermissions"]
    ]
    assert "imports.forestBlocks.acceptance" in missing_import_codes
    assert "imagery.scenes.delivery" in missing_imagery_codes


def test_permission_catalog_maps_map_layer_publish_and_export_endpoints_to_action_permissions(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})
    preview = app_client.post(
        "/api/admin/roles/preview",
        json={
            "menuModules": ["mapLayers"],
            "permissions": ["map.layers.publish", "map.layers.export"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert catalog.status_code == 200
    assert preview.status_code == 200
    body = catalog.json()
    permissions = {item["code"]: item for item in body["permissions"]}
    matrix_modules = {
        module["key"]: module
        for group in body["matrix"]
        for module in group["modules"]
    }

    map_publish = permissions["map.layers.publish"]
    map_export = permissions["map.layers.export"]
    assert "/api/map-layers/{record_id}/publish" in map_publish["apiScopes"]
    assert "/api/map-layers/{record_id}/publish" in matrix_modules["mapLayers"]["apiScopes"]
    assert "/api/map-layers/events.csv" in map_export["apiScopes"]
    assert "/api/map-layers/{record_id}/publication-receipt.json" in map_export["apiScopes"]
    assert "/api/map-layers/events.csv" in matrix_modules["mapLayers"]["apiScopes"]
    assert "/api/map-layers/{record_id}/publication-receipt.json" in matrix_modules["mapLayers"]["apiScopes"]

    matrix_publish = next(
        entry
        for entry in matrix_modules["mapLayers"]["permissionEntries"]
        if entry["code"] == "map.layers.publish"
    )
    matrix_export = next(
        entry
        for entry in matrix_modules["mapLayers"]["permissionEntries"]
        if entry["code"] == "map.layers.export"
    )
    assert matrix_publish["apiScopes"] == map_publish["apiScopes"]
    assert matrix_export["apiScopes"] == map_export["apiScopes"]

    preview_coverage = {
        item["key"]: item
        for item in preview.json()["actionPermissionCoverage"]
    }
    preview_publish = next(
        item
        for item in preview_coverage["mapLayers"]["grantedActionPermissions"]
        if item["code"] == "map.layers.publish"
    )
    preview_export = next(
        item
        for item in preview_coverage["mapLayers"]["grantedActionPermissions"]
        if item["code"] == "map.layers.export"
    )
    assert "/api/map-layers/{record_id}/publish" in preview_publish["apiScopes"]
    assert "/api/map-layers/events.csv" in preview_export["apiScopes"]
    assert "/api/map-layers/{record_id}/publication-receipt.json" in preview_export["apiScopes"]


def test_permission_catalog_exposes_cross_module_dependencies_for_layer_publish_actions(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    body = catalog.json()
    permissions = {item["code"]: item for item in body["permissions"]}
    matrix_modules = {
        module["key"]: module
        for group in body["matrix"]
        for module in group["modules"]
    }

    imagery_publish = permissions["imagery.layers.publish"]
    import_link = permissions["imports.sceneLayers.link"]
    assert imagery_publish["requiresAllPermissions"] == ["map.layers.publish"]
    assert imagery_publish["requiresAnyPermissions"] == [["map.layers.create", "map.layers.update"]]
    assert import_link["requiresAllPermissions"] == ["map.layers.publish"]
    assert import_link["requiresAnyPermissions"] == [["map.layers.create", "map.layers.update"]]

    imagery_matrix_publish = next(
        item
        for item in matrix_modules["imagery"]["permissionEntries"]
        if item["code"] == "imagery.layers.publish"
    )
    assert imagery_matrix_publish["requiresAllPermissions"] == imagery_publish["requiresAllPermissions"]
    assert imagery_matrix_publish["requiresAnyPermissions"] == imagery_publish["requiresAnyPermissions"]

    coverage = body["coverage"]
    assert coverage["summary"]["permissionDependencyRules"] >= 2
    assert coverage["summary"]["missingPermissionDependencyTargets"] == 0


def test_permission_catalog_exposes_deployment_diagnostics_module(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})
    app_client.post(
        "/api/admin/roles",
        json=sample_role("deployment_viewer") | {
            "permissions": ["system.deployment.view"],
            "menuModules": ["deployment"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    effective = app_client.get(
        "/api/admin/effective-permissions",
        headers={"X-RS-Roles": "deployment_viewer"},
    )

    assert catalog.status_code == 200
    assert effective.status_code == 200
    body = catalog.json()
    modules = {module["key"]: module for module in body["menuModules"]}
    permission_codes = {permission["code"] for permission in body["permissions"]}
    assert modules["deployment"]["href"] == "admin-deployment.html"
    assert modules["deployment"]["permission"] == "system.deployment.view"
    assert modules["deployment"]["dataDomain"] == "deployment-readiness"
    assert "/api/health" in modules["deployment"]["apiScopes"]
    assert "system.deployment.view" in permission_codes
    assert effective.json()["menuModules"] == ["deployment"]
    assert [item["key"] for item in effective.json()["visibleMenuModules"]] == ["deployment"]


def test_admin_permission_catalog_matrix_returns_permission_entry_kinds(app_client):
    denied = app_client.get(
        "/api/admin/permission-catalog",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert denied.status_code == 403
    assert "system.roles.view" in denied.json()["detail"]
    assert catalog.status_code == 200
    modules = {
        module["key"]: module
        for group in catalog.json()["matrix"]
        for module in group["modules"]
    }
    imports_entries = modules["imports"]["permissionEntries"]
    imagery_entries = modules["imagery"]["permissionEntries"]

    assert imports_entries[0]["code"] == "imports.forestBlocks.view"
    assert imports_entries[0]["kind"] == "page"
    import_action_codes = [entry["code"] for entry in imports_entries if entry["kind"] == "action"]
    assert "imports.forestBlocks.manage" in import_action_codes
    assert "imports.sceneLayers.link" in import_action_codes
    _legacy_import_entry = {
        "code": "imports.forestBlocks.manage",
        "label": "成果入库管理",
        "module": "imports",
        "kind": "page",
        "kindLabel": "入口权限",
    }
    _legacy_link_entry = {
        "code": "imports.sceneLayers.link",
        "label": "成果批次关联影像图层",
        "module": "imports",
        "kind": "action",
        "kindLabel": "动作权限",
    }
    assert [entry["kind"] for entry in imagery_entries] == [
        "page",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
    ]
    assert [entry["code"] for entry in imagery_entries] == [
        "imagery.scenes.view",
        "imagery.scenes.manage",
        "imagery.scenes.create",
        "imagery.scenes.update",
        "imagery.scenes.delete",
        "imagery.scenes.restore",
        "imagery.scenes.archive",
        "imagery.scenes.quality",
        "imagery.scenes.delivery",
        "imagery.scenes.export",
        "imagery.tasks.retry",
        "imagery.tasks.cancel",
        "imagery.tasks.archive",
        "imagery.layers.publish",
    ]


def test_forest_block_and_right_permission_catalog_exposes_action_permissions(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    body = catalog.json()
    permissions = {item["code"] for item in body["permissions"]}
    modules = {
        module["key"]: module
        for group in body["matrix"]
        for module in group["modules"]
    }

    assert next(item for item in body["menuModules"] if item["key"] == "blocks")["permission"] == "forest.blocks.view"
    assert next(item for item in body["menuModules"] if item["key"] == "rights")["permission"] == "forest.rights.view"
    assert {
        "forest.blocks.view",
        "forest.blocks.create",
        "forest.blocks.update",
        "forest.blocks.delete",
        "forest.blocks.restore",
        "forest.blocks.rollback",
        "forest.rights.view",
        "forest.rights.create",
        "forest.rights.update",
        "forest.rights.delete",
        "forest.rights.restore",
        "forest.rights.rollback",
    }.issubset(permissions)
    assert [entry["code"] for entry in modules["blocks"]["permissionEntries"]] == [
        "forest.blocks.view",
        "forest.blocks.manage",
        "forest.blocks.create",
        "forest.blocks.update",
        "forest.blocks.delete",
        "forest.blocks.restore",
        "forest.blocks.rollback",
    ]
    assert [entry["kind"] for entry in modules["blocks"]["permissionEntries"]] == [
        "page",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
    ]


def test_manage_permissions_expand_to_forest_block_and_right_actions(app_client):
    response = app_client.get(
        "/api/admin/effective-permissions",
        headers={"X-RS-Roles": "forest.blocks.manage,forest.rights.manage"},
    )

    assert response.status_code == 200
    permissions = set(response.json()["permissions"])
    menu_modules = [item["key"] for item in response.json()["visibleMenuModules"]]
    assert {
        "forest.blocks.view",
        "forest.blocks.create",
        "forest.blocks.update",
        "forest.blocks.delete",
        "forest.blocks.restore",
        "forest.blocks.rollback",
        "forest.rights.view",
        "forest.rights.create",
        "forest.rights.update",
        "forest.rights.delete",
        "forest.rights.restore",
        "forest.rights.rollback",
    }.issubset(permissions)
    assert "blocks" in menu_modules
    assert "rights" in menu_modules


def test_manage_permissions_expand_to_import_and_imagery_actions(app_client):
    response = app_client.get(
        "/api/admin/effective-permissions",
        headers={"X-RS-Roles": "imports.forestBlocks.manage,imagery.scenes.manage"},
    )

    assert response.status_code == 200
    body = response.json()
    permissions = set(body["permissions"])
    assert {
        "imports.forestBlocks.view",
        "imports.forestBlocks.create",
        "imports.forestBlocks.review",
        "imports.forestBlocks.quality",
        "imports.forestBlocks.acceptance",
        "imports.forestBlocks.rollback",
        "imports.forestBlocks.delete",
        "imports.forestBlocks.restore",
        "imports.forestBlocks.export",
        "imports.sceneLayers.link",
        "imagery.scenes.view",
        "imagery.scenes.create",
        "imagery.scenes.update",
        "imagery.scenes.delete",
        "imagery.scenes.restore",
        "imagery.scenes.archive",
        "imagery.scenes.quality",
        "imagery.scenes.delivery",
        "imagery.scenes.export",
        "imagery.tasks.retry",
        "imagery.tasks.cancel",
        "imagery.tasks.archive",
        "imagery.layers.publish",
    }.issubset(permissions)
    assert [item["key"] for item in body["visibleMenuModules"]] == ["imports", "imagery"]


def test_system_manage_permissions_expand_to_audit_exports(app_client):
    response = app_client.get(
        "/api/admin/effective-permissions",
        headers={"X-RS-Roles": "system.roles.manage,system.users.manage"},
    )

    assert response.status_code == 200
    permissions = set(response.json()["permissions"])
    assert {"system.roles.export", "system.users.export"}.issubset(permissions)


def test_permission_catalog_can_be_exported_with_roles_export_permission(app_client):
    denied = app_client.get(
        "/api/admin/permission-catalog.csv",
        headers={"X-RS-Roles": "system.users.manage"},
    )
    exported = app_client.get(
        "/api/admin/permission-catalog.csv",
        headers={"X-RS-Roles": "system.roles.export"},
    )

    assert denied.status_code == 403
    assert "system.roles.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "permission-catalog.csv" in exported.headers["content-disposition"]
    text = exported.content.decode("utf-8-sig")
    assert "group,moduleKey,moduleLabel,href,entryPermission,permissionCode" in text.splitlines()[0]
    assert "permissionApiScopes" in text.splitlines()[0]
    assert "requiresAllPermissions" in text.splitlines()[0]
    assert "requiresAnyPermissions" in text.splitlines()[0]
    assert "dependencyReason" in text.splitlines()[0]
    assert "presetKeys" in text.splitlines()[0]
    assert "presetLabels" in text.splitlines()[0]
    assert "blocks" in text
    assert "forest.blocks.view" in text
    assert "phase1-data-foundation" in text
    assert "phase2-operations" in text
    assert "business.farmers.export" in text
    assert "/api/imports/{batch_id}/acceptance" in text
    assert "/api/imports/{batch_id}/acceptance-receipt.json" in text
    assert "/api/imports/{batch_id}/delivery-package-receipt.json" in text
    assert "/api/scenes/{scene_id}/delivery" in text
    assert "/api/scenes/{scene_id}/delivery-receipt.json" in text
    assert "imagery.layers.publish" in text
    assert "map.layers.publish" in text


def test_import_and_imagery_menu_modules_expose_closure_api_scopes(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})

    assert catalog.status_code == 200
    body = catalog.json()
    import_module = next(item for item in body["menuModules"] if item["key"] == "imports")
    imagery_module = next(item for item in body["menuModules"] if item["key"] == "imagery")

    assert {
        "/api/imports/forest-blocks/workflow-summary",
        "/api/imports/forest-blocks/delivery-packages",
        "/api/imports/forest-blocks/delivery-packages.csv",
        "/api/imports/forest-blocks/audit-events.csv",
        "/api/imports/forest-blocks/quality-issues.csv",
        "/api/imports/{batch_id}/publish-readiness",
        "/api/imports/{batch_id}/report.json",
        "/api/imports/{batch_id}/acceptance-receipt.json",
        "/api/imports/{batch_id}/delivery-package-receipt.json",
    } <= set(import_module["apiScopes"])
    assert {
        "/api/scenes/workflow-summary",
        "/api/scenes/operation-queue",
        "/api/scenes/events",
        "/api/scenes/events.csv",
        "/api/tasks/events.csv",
        "/api/scenes/{scene_id}/publish-layer",
        "/api/scenes/{scene_id}/delivery",
        "/api/scenes/{scene_id}/delivery-receipt.json",
    } <= set(imagery_module["apiScopes"])


def test_business_permission_catalog_exposes_crud_actions_and_manage_expansion(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})
    effective = app_client.get(
        "/api/admin/effective-permissions",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )

    assert catalog.status_code == 200
    body = catalog.json()
    farmer_module = next(item for item in body["menuModules"] if item["key"] == "farmers")
    farmer_matrix_module = next(
        module
        for group in body["matrix"]
        for module in group["modules"]
        if module["key"] == "farmers"
    )
    farmer_entries = farmer_matrix_module["permissionEntries"]
    farmer_entries_by_code = {entry["code"]: entry for entry in farmer_entries}
    permission_codes = {item["code"] for item in body["permissions"]}
    assert farmer_module["permission"] == "business.farmers.view"
    assert farmer_module["dataDomain"] == "business-farmers"
    assert "/api/business/farmers" in farmer_module["apiScopes"]
    assert "/api/business/farmers/dashboard" in farmer_module["apiScopes"]
    assert "/api/business/farmers/events" in farmer_module["apiScopes"]
    assert {
        "business.farmers.view",
        "business.farmers.manage",
        "business.farmers.create",
        "business.farmers.update",
        "business.farmers.delete",
        "business.farmers.restore",
        "business.farmers.export",
    } <= permission_codes
    assert [entry["kind"] for entry in farmer_entries] == [
        "page",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
    ]
    assert "/api/business/farmers/dashboard" in farmer_entries_by_code["business.farmers.view"]["apiScopes"]
    assert "/api/business/farmers" in farmer_entries_by_code["business.farmers.create"]["apiScopes"]
    assert "/api/business/farmers/{record_id}" in farmer_entries_by_code["business.farmers.update"]["apiScopes"]
    assert "/api/business/farmers/{record_id}" in farmer_entries_by_code["business.farmers.delete"]["apiScopes"]
    assert "/api/business/farmers/{record_id}/restore" in farmer_entries_by_code["business.farmers.restore"]["apiScopes"]
    assert "/api/business/farmers/events.csv" in farmer_entries_by_code["business.farmers.export"]["apiScopes"]
    assert effective.status_code == 200
    effective_body = effective.json()
    assert {
        "business.farmers.view",
        "business.farmers.create",
        "business.farmers.update",
        "business.farmers.delete",
        "business.farmers.restore",
        "business.farmers.export",
    } <= set(effective_body["permissions"])
    assert [item["key"] for item in effective_body["visibleMenuModules"]] == ["farmers"]


def test_map_layer_permission_catalog_exposes_crud_and_publish_actions(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})
    effective = app_client.get(
        "/api/admin/effective-permissions",
        headers={"X-RS-Roles": "map.layers.manage"},
    )

    assert catalog.status_code == 200
    body = catalog.json()
    map_layer_module = next(item for item in body["menuModules"] if item["key"] == "mapLayers")
    map_layer_matrix_module = next(
        module
        for group in body["matrix"]
        for module in group["modules"]
        if module["key"] == "mapLayers"
    )
    map_layer_entries = map_layer_matrix_module["permissionEntries"]
    permission_codes = {item["code"] for item in body["permissions"]}

    assert map_layer_module["permission"] == "map.layers.view"
    assert {
        "map.layers.view",
        "map.layers.manage",
        "map.layers.create",
        "map.layers.update",
        "map.layers.delete",
        "map.layers.restore",
        "map.layers.export",
        "map.layers.publish",
    } <= permission_codes
    assert [entry["code"] for entry in map_layer_entries] == [
        "map.layers.view",
        "map.layers.manage",
        "map.layers.create",
        "map.layers.update",
        "map.layers.delete",
        "map.layers.restore",
        "map.layers.export",
        "map.layers.publish",
    ]
    assert [entry["kind"] for entry in map_layer_entries] == [
        "page",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
        "action",
    ]
    assert effective.status_code == 200
    effective_body = effective.json()
    assert {
        "map.layers.view",
        "map.layers.create",
        "map.layers.update",
        "map.layers.delete",
        "map.layers.restore",
        "map.layers.export",
        "map.layers.publish",
    } <= set(effective_body["permissions"])
    assert [item["key"] for item in effective_body["visibleMenuModules"]] == ["mapLayers"]


def test_permission_catalog_exposes_manage_permission_implications(app_client):
    catalog = app_client.get("/api/admin/permission-catalog", headers={"X-RS-Roles": "admin"})
    effective = app_client.get(
        "/api/admin/effective-permissions",
        headers={"X-RS-Roles": "map.layers.manage,business.farmers.manage"},
    )

    assert catalog.status_code == 200
    assert effective.status_code == 200
    implications = catalog.json()["permissionImplications"]
    assert implications["map.layers.manage"] == [
        "map.layers.view",
        "map.layers.create",
        "map.layers.update",
        "map.layers.delete",
        "map.layers.restore",
        "map.layers.export",
        "map.layers.publish",
    ]
    assert implications["business.farmers.manage"] == [
        "business.farmers.view",
        "business.farmers.create",
        "business.farmers.update",
        "business.farmers.delete",
        "business.farmers.restore",
        "business.farmers.export",
    ]
    assert effective.json()["permissionImplications"] == implications


def test_role_menu_returns_catalog_details_for_allowed_modules(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("catalog_viewer") | {
            "permissions": ["forest.blocks.manage", "map.layers.publish"],
            "menuModules": ["blocks", "mapLayers"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    menu = app_client.get("/api/admin/roles/menu?roles=catalog_viewer")

    assert menu.status_code == 200
    body = menu.json()
    assert [item["key"] for item in body["visibleMenuModules"]] == ["blocks", "mapLayers"]
    assert body["visibleMenuModules"][0]["href"] == "admin-blocks.html"


def test_role_menu_flags_unknown_inactive_and_deleted_roles(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("menu_active_role") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    app_client.post(
        "/api/admin/roles",
        json=sample_role("menu_paused_role") | {
            "status": "paused",
            "permissions": ["map.layers.manage"],
            "menuModules": ["mapLayers"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    deleted_role = app_client.post(
        "/api/admin/roles",
        json=sample_role("menu_deleted_role") | {
            "permissions": ["imports.forestBlocks.manage"],
            "menuModules": ["imports"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    app_client.delete(
        f"/api/admin/roles/{deleted_role.json()['id']}",
        headers={"X-RS-Roles": "admin"},
    )

    menu = app_client.get("/api/admin/roles/menu?roles=menu_active_role,menu_paused_role,menu_deleted_role,menu_missing_role")

    assert menu.status_code == 200
    body = menu.json()
    assert body["roles"] == ["menu_active_role", "menu_paused_role", "menu_deleted_role", "menu_missing_role"]
    assert body["menuModules"] == ["blocks"]
    assert [item["key"] for item in body["visibleMenuModules"]] == ["blocks"]
    assert body["unknownRoles"] == [{"roleCode": "menu_missing_role", "label": "menu_missing_role"}]
    assert body["invalidRoles"] == [
        {
            "roleCode": "menu_paused_role",
            "label": "Forestry Operator",
            "status": "paused",
            "reason": "inactive",
        },
        {
            "roleCode": "menu_deleted_role",
            "label": "Forestry Operator",
            "status": "deleted",
            "reason": "deleted",
        },
    ]


def test_admin_role_draft_preview_validates_menu_permissions_and_actions(app_client):
    denied = app_client.post(
        "/api/admin/roles/preview",
        json={
            "menuModules": ["imports"],
            "permissions": ["imports.forestBlocks.view"],
        },
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    preview = app_client.post(
        "/api/admin/roles/preview",
        json={
            "menuModules": ["imports", "imagery"],
            "permissions": ["imports.forestBlocks.view", "imagery.layers.publish"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "system.roles.create" in denied.json()["detail"]
    assert "system.roles.update" in denied.json()["detail"]
    assert preview.status_code == 200
    body = preview.json()
    assert [item["key"] for item in body["effectiveMenuModules"]] == ["imports"]
    assert [item["key"] for item in body["blockedMenuModules"]] == ["imagery"]
    assert body["blockedMenuModules"][0]["missingEntryPermission"] == "imagery.scenes.view"
    imports_coverage = next(item for item in body["actionPermissionCoverage"] if item["key"] == "imports")
    assert [item["code"] for item in imports_coverage["grantedActionPermissions"]] == []
    assert [item["code"] for item in imports_coverage["missingActionPermissions"]] == [
        "imports.forestBlocks.manage",
        "imports.forestBlocks.create",
        "imports.forestBlocks.review",
        "imports.forestBlocks.quality",
        "imports.forestBlocks.acceptance",
        "imports.forestBlocks.rollback",
        "imports.forestBlocks.delete",
        "imports.forestBlocks.restore",
        "imports.forestBlocks.export",
        "imports.sceneLayers.link",
    ]
    assert [item["code"] for item in body["orphanActionPermissions"]] == ["imagery.layers.publish"]
    assert body["orphanActionPermissions"][0]["module"] == "imagery"


def test_admin_role_draft_preview_flags_unknown_menu_modules_and_permissions(app_client):
    preview = app_client.post(
        "/api/admin/roles/preview",
        json={
            "menuModules": ["blocks", "missingModule"],
            "permissions": ["forest.blocks.manage", "unknown.permission"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert [item["key"] for item in body["effectiveMenuModules"]] == ["blocks"]
    assert body["unknownMenuModules"] == [{"key": "missingModule", "label": "missingModule"}]
    assert body["unknownPermissions"] == [{"code": "unknown.permission", "label": "unknown.permission", "module": ""}]


def test_admin_role_draft_preview_returns_summary_and_risk_level(app_client):
    preview = app_client.post(
        "/api/admin/roles/preview",
        json={
            "menuModules": ["imports", "imagery", "missingModule"],
            "permissions": [
                "imports.forestBlocks.view",
                "imagery.layers.publish",
                "unknown.permission",
            ],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["riskLevel"] == "error"
    assert body["summary"]["configuredMenuModules"] == 3
    assert body["summary"]["effectiveMenuModules"] == 1
    assert body["summary"]["blockedMenuModules"] == 1
    assert body["summary"]["unknownMenuModules"] == 1
    assert body["summary"]["unknownPermissions"] == 1
    assert body["summary"]["orphanActionPermissions"] == 1
    assert body["summary"]["missingActionPermissions"] > 0


def test_admin_role_draft_preview_flags_missing_cross_module_permission_dependencies(app_client):
    preview = app_client.post(
        "/api/admin/roles/preview",
        json={
            "menuModules": ["imagery"],
            "permissions": ["imagery.scenes.view", "imagery.layers.publish"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["riskLevel"] == "warning"
    assert body["summary"]["permissionDependencyIssues"] == 1
    assert len(body["permissionDependencyIssues"]) == 1
    issue = body["permissionDependencyIssues"][0]
    assert issue["permissionCode"] == "imagery.layers.publish"
    assert issue["requiresAllPermissions"] == ["map.layers.publish"]
    assert issue["missingAllPermissions"] == ["map.layers.publish"]
    assert issue["requiresAnyPermissions"] == [["map.layers.create", "map.layers.update"]]
    assert issue["missingAnyPermissionGroups"] == [["map.layers.create", "map.layers.update"]]


def test_admin_role_draft_preview_accepts_manage_permissions_that_satisfy_dependencies(app_client):
    preview = app_client.post(
        "/api/admin/roles/preview",
        json={
            "menuModules": ["imagery", "mapLayers"],
            "permissions": ["imagery.scenes.manage", "map.layers.manage"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["riskLevel"] == "ready"
    assert body["summary"]["permissionDependencyIssues"] == 0
    assert body["permissionDependencyIssues"] == []


def test_admin_role_save_rejects_menu_modules_without_entry_permissions(app_client):
    rejected = app_client.post(
        "/api/admin/roles",
        json=sample_role("broken_menu_role") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks", "mapLayers"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    searched = app_client.get(
        "/api/admin/roles?q=broken_menu_role",
        headers={"X-RS-Roles": "system.roles.view"},
    )

    assert rejected.status_code == 400
    detail = rejected.json()["detail"]
    assert detail["message"] == "role menu modules require matching entry permissions"
    assert detail["riskLevel"] == "error"
    assert detail["summary"]["blockedMenuModules"] == 1
    assert [item["key"] for item in detail["blockedMenuModules"]] == ["mapLayers"]
    assert detail["blockedMenuModules"][0]["missingEntryPermission"] == "map.layers.view"
    assert searched.status_code == 200
    assert searched.json()["total"] == 0


def test_admin_role_patch_rejects_permission_drift_that_blocks_configured_menu(app_client):
    created = app_client.post(
        "/api/admin/roles",
        json=sample_role("patch_guard_role") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    role = created.json()

    rejected = app_client.patch(
        f"/api/admin/roles/{role['id']}",
        json={"permissions": ["map.layers.publish"]},
        headers={"X-RS-Roles": "admin"},
    )
    unchanged = app_client.get(
        f"/api/admin/roles/{role['id']}",
        headers={"X-RS-Roles": "system.roles.view"},
    )

    assert rejected.status_code == 400
    detail = rejected.json()["detail"]
    assert detail["riskLevel"] == "error"
    assert [item["key"] for item in detail["blockedMenuModules"]] == ["blocks"]
    assert detail["blockedMenuModules"][0]["missingEntryPermission"] == "forest.blocks.view"
    assert unchanged.status_code == 200
    assert unchanged.json()["permissions"] == ["forest.blocks.manage"]
    assert unchanged.json()["menuModules"] == ["blocks"]


def test_postgis_create_admin_role_uses_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    admin_roles_module = reload_admin_roles_module(reload_platform_modules)
    duplicate_cursor = FakeCursor(fetchall_result=[])
    insert_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [duplicate_cursor, insert_cursor], connect_calls)

    created = admin_roles_module.create_role(
        admin_roles_module.AdminRoleIn(**sample_role("role_pg_create")),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert created.roleCode == "role_pg_create"
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo"]
    assert "FROM admin_roles" in duplicate_cursor.executed[0][0]
    assert "role_code = %s" in duplicate_cursor.executed[0][0]
    assert "INSERT INTO admin_roles" in insert_cursor.executed[0][0]
    assert insert_cursor.executed[0][1][1] == "role_pg_create"


def test_postgis_list_admin_role_filters_are_applied_in_database(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    admin_roles_module = reload_admin_roles_module(reload_platform_modules)
    list_cursor = FakeCursor(fetchall_result=[postgis_role_row("role_pg_filter")])
    count_cursor = FakeCursor(fetchone_result=(1,))
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [list_cursor, count_cursor], connect_calls)

    response = admin_roles_module.list_roles(
        admin_roles_module.RoleFilters(
            q="pg",
            status="active",
            permission="forest.blocks.manage",
            menuModule="blocks",
            limit=20,
            offset=5,
        ),
        AuthContext(user="admin", roles={"admin"}, projects={"*"}, areas={"*"}),
    )

    list_sql, list_params = list_cursor.executed[0]
    count_sql, count_params = count_cursor.executed[0]
    assert response["total"] == 1
    assert response["items"][0]["roleCode"] == "role_pg_filter"
    assert "status = %s" in list_sql
    assert "permissions ? %s" in list_sql
    assert "menu_modules ? %s" in list_sql
    assert "ILIKE" in list_sql
    assert "LIMIT %s OFFSET %s" in list_sql
    assert list_params[:3] == ("active", "forest.blocks.manage", "blocks")
    assert list_params[-2:] == (20, 5)
    assert "SELECT COUNT(*) FROM admin_roles" in count_sql
    assert count_params[:3] == ("active", "forest.blocks.manage", "blocks")


def test_postgis_patch_and_delete_admin_role_use_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    admin_roles_module = reload_admin_roles_module(reload_platform_modules)
    select_for_patch = FakeCursor(fetchall_result=[postgis_role_row("role_pg_patch")])
    update_cursor = FakeCursor()
    select_for_delete = FakeCursor(fetchall_result=[postgis_role_row("role_pg_patch")])
    delete_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(
        monkeypatch,
        [select_for_patch, update_cursor, select_for_delete, delete_cursor],
        connect_calls,
    )

    patched = admin_roles_module.patch_role(
        "5ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        admin_roles_module.AdminRolePatch(
            name="Updated PG Role",
            permissions=["map.layers.publish"],
            menuModules=["mapLayers"],
        ),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )
    deleted = admin_roles_module.delete_role(
        "5ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert patched.name == "Updated PG Role"
    assert patched.permissions == ["map.layers.publish"]
    assert patched.menuModules == ["mapLayers"]
    assert deleted["ok"] is True
    assert "FROM admin_roles" in select_for_patch.executed[0][0]
    assert "INSERT INTO admin_roles" in update_cursor.executed[0][0]
    assert "INSERT INTO admin_roles" in delete_cursor.executed[0][0]


def test_postgis_create_admin_user_uses_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    admin_users_module = reload_admin_users_module(reload_platform_modules)
    duplicate_cursor = FakeCursor(fetchall_result=[])
    insert_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [duplicate_cursor, insert_cursor], connect_calls)

    created = admin_users_module.create_user(
        admin_users_module.AdminUserIn(**sample_user("user_pg_create")),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert created.username == "user_pg_create"
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo"]
    assert "FROM admin_users" in duplicate_cursor.executed[0][0]
    assert "LOWER(username) = %s" in duplicate_cursor.executed[0][0]
    assert duplicate_cursor.executed[0][1][0] == "user_pg_create"
    assert "INSERT INTO admin_users" in insert_cursor.executed[0][0]
    assert insert_cursor.executed[0][1][1] == "user_pg_create"


def test_postgis_list_admin_user_filters_are_applied_in_database(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    admin_users_module = reload_admin_users_module(reload_platform_modules)
    list_cursor = FakeCursor(fetchall_result=[postgis_user_row("user_pg_filter")])
    count_cursor = FakeCursor(fetchone_result=(1,))
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [list_cursor, count_cursor], connect_calls)

    response = admin_users_module.list_users(
        admin_users_module.UserFilters(
            q="pg",
            status="active",
            role="forest_user_role",
            limit=20,
            offset=5,
        ),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    list_sql, list_params = list_cursor.executed[0]
    count_sql, count_params = count_cursor.executed[0]
    assert response["total"] == 1
    assert response["items"][0]["username"] == "user_pg_filter"
    assert "status = %s" in list_sql
    assert "roles ? %s" in list_sql
    assert "ILIKE" in list_sql
    assert "LIMIT %s OFFSET %s" in list_sql
    assert list_params[:2] == ("active", "forest_user_role")
    assert list_params[-2:] == (20, 5)
    assert "SELECT COUNT(*) FROM admin_users" in count_sql
    assert count_params[:2] == ("active", "forest_user_role")


def test_postgis_patch_and_delete_admin_user_use_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    admin_users_module = reload_admin_users_module(reload_platform_modules)
    patch_cursor = FakeCursor(fetchone_result=postgis_user_row("user_pg_patch"))
    select_for_delete = FakeCursor(fetchall_result=[postgis_user_row("user_pg_patch")])
    delete_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(
        monkeypatch,
        [patch_cursor, select_for_delete, delete_cursor],
        connect_calls,
    )

    patched = admin_users_module.patch_user(
        "6ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        admin_users_module.AdminUserPatch(displayName="Updated PG User", roles=["forest_user_role", "map_publisher"]),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )
    deleted = admin_users_module.delete_user(
        "6ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert patched.displayName == "Updated PG User"
    assert patched.roles == ["forest_user_role", "map_publisher"]
    assert deleted["ok"] is True
    assert "FROM admin_users" in patch_cursor.executed[0][0]
    assert "FOR UPDATE" in patch_cursor.executed[0][0]
    assert "INSERT INTO admin_users" in patch_cursor.executed[1][0]
    assert "INSERT INTO admin_users" in delete_cursor.executed[0][0]


def test_admin_role_menu_for_known_role_codes(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("block_viewer") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    app_client.post(
        "/api/admin/roles",
        json=sample_role("map_publisher") | {
            "permissions": ["map.layers.publish"],
            "menuModules": ["mapLayers"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    menu = app_client.get("/api/admin/roles/menu?roles=block_viewer,map_publisher")

    assert menu.status_code == 200
    body = menu.json()
    assert body["roles"] == ["block_viewer", "map_publisher"]
    assert body["menuModules"] == ["blocks", "mapLayers"]
    assert body["permissions"] == ["forest.blocks.manage", "map.layers.publish"]


def test_role_permission_allows_forest_block_writes_without_admin_role(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("block_editor") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    allowed = app_client.post(
        "/api/forest-blocks",
        json={"blockCode": "PERM-BLOCK-001", "name": "Permission block", "countyCode": "350703"},
        headers={"X-RS-Roles": "block_editor"},
    )

    assert allowed.status_code == 200
    assert allowed.json()["blockCode"] == "PERM-BLOCK-001"


def test_role_without_required_permission_cannot_write_forest_blocks(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("rights_only") | {
            "permissions": ["forest.rights.manage"],
            "menuModules": ["rights"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    denied = app_client.post(
        "/api/forest-blocks",
        json={"blockCode": "PERM-BLOCK-002", "name": "Denied block"},
        headers={"X-RS-Roles": "rights_only"},
    )

    assert denied.status_code == 403
    assert "forest.blocks.create" in denied.json()["detail"]


def test_role_data_scope_limits_forest_block_visibility_and_writes(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("scoped_block_editor") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
            "dataScopes": {"areas": ["350703"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    allowed_seed = app_client.post(
        "/api/forest-blocks",
        json={"blockCode": "SCOPE-BLOCK-001", "name": "Allowed scoped block", "countyCode": "350703"},
        headers={"X-RS-Roles": "admin"},
    )
    denied_seed = app_client.post(
        "/api/forest-blocks",
        json={"blockCode": "SCOPE-BLOCK-002", "name": "Denied scoped block", "countyCode": "350724"},
        headers={"X-RS-Roles": "admin"},
    )

    assert allowed_seed.status_code == 200
    assert denied_seed.status_code == 200

    visible = app_client.get(
        "/api/forest-blocks?q=SCOPE-BLOCK",
        headers={"X-RS-Roles": "scoped_block_editor"},
    )
    denied_create = app_client.post(
        "/api/forest-blocks",
        json={"blockCode": "SCOPE-BLOCK-003", "name": "Out of scope create", "countyCode": "350724"},
        headers={"X-RS-Roles": "scoped_block_editor"},
    )
    allowed_create = app_client.post(
        "/api/forest-blocks",
        json={"blockCode": "SCOPE-BLOCK-004", "name": "In scope create", "countyCode": "350703"},
        headers={"X-RS-Roles": "scoped_block_editor"},
    )

    assert visible.status_code == 200
    assert visible.json()["total"] == 1
    assert visible.json()["items"][0]["blockCode"] == "SCOPE-BLOCK-001"
    assert denied_create.status_code == 403
    assert "Area access denied" in denied_create.json()["detail"]
    assert allowed_create.status_code == 200


def test_role_fine_grained_data_scopes_limit_forest_blocks_by_town_and_block_code(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("town_scoped_block_editor") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
            "dataScopes": {"areas": ["350703"], "towns": ["350703101"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    app_client.post(
        "/api/admin/roles",
        json=sample_role("block_code_scoped_editor") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
            "dataScopes": {"blockCodes": ["FINE-SCOPE-BLOCK-001"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    allowed_town = app_client.post(
        "/api/forest-blocks",
        json={
            "blockCode": "FINE-SCOPE-TOWN-001",
            "name": "Allowed town block",
            "countyCode": "350703",
            "townCode": "350703101",
            "villageCode": "350703101001",
        },
        headers={"X-RS-Roles": "admin"},
    )
    denied_town = app_client.post(
        "/api/forest-blocks",
        json={
            "blockCode": "FINE-SCOPE-TOWN-002",
            "name": "Denied town block",
            "countyCode": "350703",
            "townCode": "350703102",
            "villageCode": "350703102001",
        },
        headers={"X-RS-Roles": "admin"},
    )
    allowed_block_code = app_client.post(
        "/api/forest-blocks",
        json={
            "blockCode": "FINE-SCOPE-BLOCK-001",
            "name": "Allowed block code",
            "countyCode": "350724",
            "townCode": "350724201",
        },
        headers={"X-RS-Roles": "admin"},
    )
    denied_block_code = app_client.post(
        "/api/forest-blocks",
        json={
            "blockCode": "FINE-SCOPE-BLOCK-002",
            "name": "Denied block code",
            "countyCode": "350724",
            "townCode": "350724201",
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert allowed_town.status_code == 200
    assert denied_town.status_code == 200
    assert allowed_block_code.status_code == 200
    assert denied_block_code.status_code == 200

    town_visible = app_client.get(
        "/api/forest-blocks?q=FINE-SCOPE-TOWN",
        headers={"X-RS-Roles": "town_scoped_block_editor"},
    )
    town_denied_create = app_client.post(
        "/api/forest-blocks",
        json={
            "blockCode": "FINE-SCOPE-TOWN-003",
            "name": "Out of town create",
            "countyCode": "350703",
            "townCode": "350703102",
        },
        headers={"X-RS-Roles": "town_scoped_block_editor"},
    )
    town_allowed_create = app_client.post(
        "/api/forest-blocks",
        json={
            "blockCode": "FINE-SCOPE-TOWN-004",
            "name": "In town create",
            "countyCode": "350703",
            "townCode": "350703101",
        },
        headers={"X-RS-Roles": "town_scoped_block_editor"},
    )
    block_code_visible = app_client.get(
        "/api/forest-blocks?q=FINE-SCOPE-BLOCK",
        headers={"X-RS-Roles": "block_code_scoped_editor"},
    )
    block_code_denied_create = app_client.post(
        "/api/forest-blocks",
        json={
            "blockCode": "FINE-SCOPE-BLOCK-003",
            "name": "Out of block code create",
            "countyCode": "350724",
        },
        headers={"X-RS-Roles": "block_code_scoped_editor"},
    )

    assert town_visible.status_code == 200
    assert town_visible.json()["total"] == 1
    assert town_visible.json()["items"][0]["blockCode"] == "FINE-SCOPE-TOWN-001"
    assert town_denied_create.status_code == 403
    assert "Area access denied" in town_denied_create.json()["detail"]
    assert town_allowed_create.status_code == 200
    assert block_code_visible.status_code == 200
    assert block_code_visible.json()["total"] == 1
    assert block_code_visible.json()["items"][0]["blockCode"] == "FINE-SCOPE-BLOCK-001"
    assert block_code_denied_create.status_code == 403
    assert "Area access denied" in block_code_denied_create.json()["detail"]


def test_effective_permissions_include_role_menu_and_data_scopes(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("effective_scoped_role") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks"],
            "dataScopes": {"areas": ["350703"], "projects": ["bamboo-gis"]},
        },
        headers={"X-RS-Roles": "admin"},
    )

    response = app_client.get(
        "/api/admin/effective-permissions",
        headers={"X-RS-Roles": "effective_scoped_role"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["effective_scoped_role"]
    assert {
        "forest.blocks.manage",
        "forest.blocks.view",
        "forest.blocks.create",
        "forest.blocks.update",
        "forest.blocks.delete",
        "forest.blocks.restore",
        "forest.blocks.rollback",
    }.issubset(set(body["permissions"]))
    assert body["menuModules"] == ["blocks"]
    assert body["dataScopes"] == {"areas": ["350703"], "projects": ["bamboo-gis"]}
    assert [item["key"] for item in body["visibleMenuModules"]] == ["blocks"]


def test_effective_menu_modules_require_their_entry_permission(app_client):
    seed_legacy_role(
        sample_role("stale_menu_role") | {
            "permissions": ["forest.blocks.manage"],
            "menuModules": ["blocks", "mapLayers"],
        }
    )

    response = app_client.get(
        "/api/admin/effective-permissions",
        headers={"X-RS-Roles": "stale_menu_role"},
    )
    menu = app_client.get("/api/admin/roles/menu?roles=stale_menu_role")

    assert response.status_code == 200
    assert menu.status_code == 200
    assert {
        "forest.blocks.manage",
        "forest.blocks.view",
        "forest.blocks.create",
        "forest.blocks.update",
        "forest.blocks.delete",
        "forest.blocks.restore",
        "forest.blocks.rollback",
    }.issubset(set(response.json()["permissions"]))
    assert response.json()["menuModules"] == ["blocks"]
    assert [item["key"] for item in response.json()["visibleMenuModules"]] == ["blocks"]
    assert menu.json()["configuredMenuModules"] == ["blocks", "mapLayers"]
    assert menu.json()["menuModules"] == ["blocks"]
    assert [item["key"] for item in menu.json()["visibleMenuModules"]] == ["blocks"]


def create_role_with_permissions(app_client, code: str, permissions: list[str]) -> None:
    response = app_client.post(
        "/api/admin/roles",
        json=sample_role(code) | {
            "permissions": permissions,
            "menuModules": [],
        },
        headers={"X-RS-Roles": "admin"},
    )
    assert response.status_code == 200


def test_role_permission_allows_forest_right_writes_without_admin_role(app_client):
    create_role_with_permissions(app_client, "rights_editor", ["forest.rights.manage"])

    allowed = app_client.post(
        "/api/forest-rights",
        json={"archiveCode": "RIGHT-PERM-001", "holder": "Permission holder"},
        headers={"X-RS-Roles": "rights_editor"},
    )

    assert allowed.status_code == 200
    assert allowed.json()["archiveCode"] == "RIGHT-PERM-001"


def test_role_fine_grained_data_scopes_limit_forest_rights_by_town_and_linked_block(app_client):
    app_client.post(
        "/api/admin/roles",
        json=sample_role("town_scoped_rights_editor") | {
            "permissions": ["forest.rights.manage"],
            "menuModules": ["rights"],
            "dataScopes": {"areas": ["350703"], "towns": ["350703101"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    app_client.post(
        "/api/admin/roles",
        json=sample_role("linked_block_scoped_rights_editor") | {
            "permissions": ["forest.rights.manage"],
            "menuModules": ["rights"],
            "dataScopes": {"blockCodes": ["RIGHT-SCOPE-BLOCK-001"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    allowed_town = app_client.post(
        "/api/forest-rights",
        json={
            "archiveCode": "FINE-RIGHT-TOWN-001",
            "holder": "Allowed town holder",
            "countyCode": "350703",
            "townCode": "350703101",
            "linkedBlockCodes": ["RIGHT-SCOPE-TOWN-001"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    denied_town = app_client.post(
        "/api/forest-rights",
        json={
            "archiveCode": "FINE-RIGHT-TOWN-002",
            "holder": "Denied town holder",
            "countyCode": "350703",
            "townCode": "350703102",
            "linkedBlockCodes": ["RIGHT-SCOPE-TOWN-002"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    allowed_linked_block = app_client.post(
        "/api/forest-rights",
        json={
            "archiveCode": "FINE-RIGHT-BLOCK-001",
            "holder": "Allowed linked block holder",
            "countyCode": "350724",
            "linkedBlockCodes": ["RIGHT-SCOPE-BLOCK-001"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    denied_linked_block = app_client.post(
        "/api/forest-rights",
        json={
            "archiveCode": "FINE-RIGHT-BLOCK-002",
            "holder": "Denied linked block holder",
            "countyCode": "350724",
            "linkedBlockCodes": ["RIGHT-SCOPE-BLOCK-002"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert allowed_town.status_code == 200
    assert denied_town.status_code == 200
    assert allowed_linked_block.status_code == 200
    assert denied_linked_block.status_code == 200

    town_visible = app_client.get(
        "/api/forest-rights?q=FINE-RIGHT-TOWN",
        headers={"X-RS-Roles": "town_scoped_rights_editor"},
    )
    town_denied_create = app_client.post(
        "/api/forest-rights",
        json={
            "archiveCode": "FINE-RIGHT-TOWN-003",
            "holder": "Out of town holder",
            "countyCode": "350703",
            "townCode": "350703102",
        },
        headers={"X-RS-Roles": "town_scoped_rights_editor"},
    )
    town_allowed_create = app_client.post(
        "/api/forest-rights",
        json={
            "archiveCode": "FINE-RIGHT-TOWN-004",
            "holder": "In town holder",
            "countyCode": "350703",
            "townCode": "350703101",
        },
        headers={"X-RS-Roles": "town_scoped_rights_editor"},
    )
    linked_block_visible = app_client.get(
        "/api/forest-rights?q=FINE-RIGHT-BLOCK",
        headers={"X-RS-Roles": "linked_block_scoped_rights_editor"},
    )
    linked_block_denied_create = app_client.post(
        "/api/forest-rights",
        json={
            "archiveCode": "FINE-RIGHT-BLOCK-003",
            "holder": "Out of linked block holder",
            "countyCode": "350724",
            "linkedBlockCodes": ["RIGHT-SCOPE-BLOCK-003"],
        },
        headers={"X-RS-Roles": "linked_block_scoped_rights_editor"},
    )
    linked_block_allowed_create = app_client.post(
        "/api/forest-rights",
        json={
            "archiveCode": "FINE-RIGHT-BLOCK-004",
            "holder": "In linked block holder",
            "countyCode": "350724",
            "linkedBlockCodes": ["RIGHT-SCOPE-BLOCK-001"],
        },
        headers={"X-RS-Roles": "linked_block_scoped_rights_editor"},
    )

    assert town_visible.status_code == 200
    assert town_visible.json()["total"] == 1
    assert town_visible.json()["items"][0]["archiveCode"] == "FINE-RIGHT-TOWN-001"
    assert town_denied_create.status_code == 403
    assert "Area access denied" in town_denied_create.json()["detail"]
    assert town_allowed_create.status_code == 200
    assert linked_block_visible.status_code == 200
    assert linked_block_visible.json()["total"] == 1
    assert linked_block_visible.json()["items"][0]["archiveCode"] == "FINE-RIGHT-BLOCK-001"
    assert linked_block_denied_create.status_code == 403
    assert "Area access denied" in linked_block_denied_create.json()["detail"]
    assert linked_block_allowed_create.status_code == 200


def test_role_without_required_permission_cannot_write_forest_rights(app_client):
    create_role_with_permissions(app_client, "blocks_only", ["forest.blocks.manage"])

    denied = app_client.post(
        "/api/forest-rights",
        json={"archiveCode": "RIGHT-PERM-002", "holder": "Denied holder"},
        headers={"X-RS-Roles": "blocks_only"},
    )

    assert denied.status_code == 403
    assert "forest.rights.create" in denied.json()["detail"]


def test_business_module_permissions_are_module_specific(app_client):
    create_role_with_permissions(app_client, "farmer_editor", ["business.farmers.manage"])

    allowed = app_client.post(
        "/api/business/farmers",
        json={"recordCode": "FARMER-PERM-001", "name": "Permission farmer"},
        headers={"X-RS-Roles": "farmer_editor"},
    )
    denied = app_client.post(
        "/api/business/cooperatives",
        json={"recordCode": "COOP-PERM-001", "name": "Denied cooperative"},
        headers={"X-RS-Roles": "farmer_editor"},
    )

    assert allowed.status_code == 200
    assert allowed.json()["recordCode"] == "FARMER-PERM-001"
    assert denied.status_code == 403
    assert "business.cooperatives.create" in denied.json()["detail"]


def test_map_layer_create_permission_is_required_for_layer_creation(app_client):
    create_role_with_permissions(app_client, "layer_creator", ["map.layers.create"])
    create_role_with_permissions(app_client, "layer_publisher", ["map.layers.publish"])
    create_role_with_permissions(app_client, "farmer_only", ["business.farmers.manage"])

    allowed = app_client.post(
        "/api/map-layers",
        json={"recordCode": "LAYER-PERM-001", "name": "Permission layer"},
        headers={"X-RS-Roles": "layer_creator"},
    )
    denied_publisher = app_client.post(
        "/api/map-layers",
        json={"recordCode": "LAYER-PERM-002", "name": "Publish-only layer"},
        headers={"X-RS-Roles": "layer_publisher"},
    )
    denied = app_client.post(
        "/api/map-layers",
        json={"recordCode": "LAYER-PERM-003", "name": "Denied layer"},
        headers={"X-RS-Roles": "farmer_only"},
    )

    assert allowed.status_code == 200
    assert allowed.json()["recordCode"] == "LAYER-PERM-001"
    assert denied_publisher.status_code == 403
    assert "map.layers.create" in denied_publisher.json()["detail"]
    assert denied.status_code == 403
    assert "map.layers.create" in denied.json()["detail"]


def test_map_layer_publish_permission_toggles_dashboard_publication(app_client):
    create_role_with_permissions(app_client, "layer_creator_for_publish", ["map.layers.create"])
    create_role_with_permissions(app_client, "layer_publisher_for_toggle", ["map.layers.publish"])

    created = app_client.post(
        "/api/map-layers",
        json={
            "recordCode": "LAYER-PUBLISH-001",
            "name": "Publish toggle layer",
            "status": "draft",
            "visibleOnDashboard": False,
        },
        headers={"X-RS-Roles": "layer_creator_for_publish", "X-RS-User": "creator"},
    )
    assert created.status_code == 200
    layer_id = created.json()["id"]

    denied = app_client.post(
        f"/api/map-layers/{layer_id}/publish",
        json={"visibleOnDashboard": True},
        headers={"X-RS-Roles": "layer_creator_for_publish", "X-RS-User": "creator"},
    )
    published = app_client.post(
        f"/api/map-layers/{layer_id}/publish",
        json={"visibleOnDashboard": True},
        headers={"X-RS-Roles": "layer_publisher_for_toggle", "X-RS-User": "publisher"},
    )
    paused = app_client.post(
        f"/api/map-layers/{layer_id}/publish",
        json={"visibleOnDashboard": False, "status": "paused"},
        headers={"X-RS-Roles": "layer_publisher_for_toggle", "X-RS-User": "publisher"},
    )
    events = app_client.get(
        "/api/map-layers/events?recordCode=LAYER-PUBLISH-001&action=publish",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "map.layers.publish" in denied.json()["detail"]
    assert published.status_code == 200
    assert published.json()["layer"]["status"] == "published"
    assert published.json()["layer"]["visibleOnDashboard"] is True
    assert published.json()["event"]["action"] == "publish"
    assert paused.status_code == 200
    assert paused.json()["layer"]["status"] == "paused"
    assert paused.json()["layer"]["visibleOnDashboard"] is False
    assert paused.json()["event"]["action"] == "publish"
    assert events.status_code == 200
    assert events.json()["total"] >= 2


def test_map_layer_publication_receipt_can_be_exported(app_client):
    create_role_with_permissions(app_client, "layer_receipt_creator", ["map.layers.create"])
    create_role_with_permissions(app_client, "layer_receipt_publisher", ["map.layers.publish"])

    created = app_client.post(
        "/api/map-layers",
        json={
            "recordCode": "LAYER-RECEIPT-001",
            "name": "Publication receipt layer",
            "status": "draft",
            "layerType": "imagery",
            "dataSource": "scene:receipt-scene",
            "visibleOnDashboard": False,
            "linkedBlockCodes": ["FB-AUTH"],
            "properties": {"sourceSceneId": "receipt-scene", "publishRiskStatus": "clear"},
        },
        headers={"X-RS-Roles": "layer_receipt_creator", "X-RS-User": "creator"},
    )
    layer_id = created.json()["id"]
    published = app_client.post(
        f"/api/map-layers/{layer_id}/publish",
        json={"visibleOnDashboard": True},
        headers={"X-RS-Roles": "layer_receipt_publisher", "X-RS-User": "publisher"},
    )

    denied = app_client.get(
        f"/api/map-layers/{layer_id}/publication-receipt.json",
        headers={"X-RS-Roles": "map.layers.view"},
    )
    exported = app_client.get(
        f"/api/map-layers/{layer_id}/publication-receipt.json",
        headers={"X-RS-Roles": "map.layers.export", "X-RS-User": "receipt-exporter"},
    )

    assert created.status_code == 200
    assert published.status_code == 200
    assert denied.status_code == 403
    assert "map.layers.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert "map-layer-publication-receipt-LAYER-RECEIPT-001.json" in exported.headers["content-disposition"]
    body = exported.json()
    assert body["receiptType"] == "map-layer-publication"
    assert body["exportedBy"] == "receipt-exporter"
    assert body["layer"]["recordCode"] == "LAYER-RECEIPT-001"
    assert body["summary"]["published"] is True
    assert body["summary"]["dashboardHref"] == "zhushan-bigdata.html#mapLayers"
    assert body["summary"]["linkedBlockCount"] == 1
    assert body["sourceLinks"][0]["type"] == "imagery"
    assert body["events"][-1]["action"] == "publish"
    assert body["exportedAt"]


def test_scene_write_endpoints_require_imagery_permission(app_client):
    denied = app_client.patch(
        "/api/scenes/missing-scene/access",
        json={"projectId": "project-001"},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    allowed_to_reach_scene_lookup = app_client.patch(
        "/api/scenes/missing-scene/access",
        json={"projectId": "project-001"},
        headers={"X-RS-Roles": "imagery.scenes.update"},
    )

    assert denied.status_code == 403
    assert "imagery.scenes.update" in denied.json()["detail"]
    assert allowed_to_reach_scene_lookup.status_code == 404


def test_import_permission_is_required_for_uploaded_forest_blocks(app_client):
    create_role_with_permissions(app_client, "importer", ["imports.forestBlocks.create"])
    geojson = b"""
    {
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "properties": {"blockCode": "IMPORT-PERM-001", "name": "Permission import", "countyCode": "350703"},
          "geometry": null
        }
      ]
    }
    """

    allowed = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("permission.geojson", io.BytesIO(geojson), "application/geo+json")},
        headers={"X-RS-Roles": "importer"},
    )
    denied = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("permission-denied.geojson", io.BytesIO(geojson), "application/geo+json")},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )

    assert allowed.status_code == 200
    assert allowed.json()["validRows"] == 1
    assert denied.status_code == 403
    assert "imports.forestBlocks.create" in denied.json()["detail"]
