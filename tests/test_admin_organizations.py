from __future__ import annotations


def organization_payload(code: str, name: str, parent_id: str | None = None) -> dict[str, object]:
    return {
        "organizationCode": code,
        "name": name,
        "parentId": parent_id,
        "organizationType": "department",
        "status": "active",
        "sortOrder": 10,
        "dataScopes": {"areas": ["350703"]},
        "properties": {},
    }


def test_organization_crud_tree_search_and_restore(app_client):
    root = app_client.post(
        "/api/admin/organizations",
        json=organization_payload("ORG-ROOT", "智慧竹山运营中心"),
        headers={"X-RS-Roles": "system.organizations.create"},
    )
    assert root.status_code == 200

    child = app_client.post(
        "/api/admin/organizations",
        json=organization_payload("ORG-TECH", "技术与数据部", root.json()["id"]),
        headers={"X-RS-Roles": "system.organizations.create"},
    )
    assert child.status_code == 200

    listed = app_client.get(
        "/api/admin/organizations?q=数据部",
        headers={"X-RS-Roles": "system.organizations.view"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["parentId"] == root.json()["id"]

    patched = app_client.patch(
        f"/api/admin/organizations/{child.json()['id']}",
        json={"leader": "林主任", "phone": "13900000000"},
        headers={"X-RS-Roles": "system.organizations.update"},
    )
    assert patched.status_code == 200
    assert patched.json()["leader"] == "林主任"

    blocked_parent_delete = app_client.delete(
        f"/api/admin/organizations/{root.json()['id']}",
        headers={"X-RS-Roles": "system.organizations.delete"},
    )
    assert blocked_parent_delete.status_code == 409

    deleted = app_client.delete(
        f"/api/admin/organizations/{child.json()['id']}",
        headers={"X-RS-Roles": "system.organizations.delete"},
    )
    assert deleted.status_code == 200

    restored = app_client.post(
        f"/api/admin/organizations/{child.json()['id']}/restore",
        headers={"X-RS-Roles": "system.organizations.restore"},
    )
    assert restored.status_code == 200
    assert restored.json()["deletedAt"] is None


def test_organization_hierarchy_rejects_cycles_and_unknown_parents(app_client):
    first = app_client.post(
        "/api/admin/organizations",
        json=organization_payload("ORG-A", "组织 A"),
        headers={"X-RS-Roles": "admin"},
    ).json()
    second = app_client.post(
        "/api/admin/organizations",
        json=organization_payload("ORG-B", "组织 B", first["id"]),
        headers={"X-RS-Roles": "admin"},
    ).json()

    cycle = app_client.patch(
        f"/api/admin/organizations/{first['id']}",
        json={"parentId": second["id"]},
        headers={"X-RS-Roles": "system.organizations.update"},
    )
    missing = app_client.patch(
        f"/api/admin/organizations/{first['id']}",
        json={"parentId": "missing-organization"},
        headers={"X-RS-Roles": "system.organizations.update"},
    )

    assert cycle.status_code == 422
    assert "cycle" in cycle.json()["detail"].lower()
    assert missing.status_code == 422


def test_organization_delete_is_blocked_while_users_are_assigned(app_client):
    organization = app_client.post(
        "/api/admin/organizations",
        json=organization_payload("ORG-FIELD", "林业生产部"),
        headers={"X-RS-Roles": "admin"},
    ).json()
    user = app_client.post(
        "/api/admin/users",
        json={
            "username": "field_manager",
            "displayName": "生产负责人",
            "status": "active",
            "roles": [],
            "dataScopes": {},
            "properties": {"organizationId": organization["id"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    assert user.status_code == 200

    listed = app_client.get(
        "/api/admin/organizations",
        headers={"X-RS-Roles": "system.organizations.view"},
    )
    assert listed.json()["items"][0]["userCount"] == 1

    blocked = app_client.delete(
        f"/api/admin/organizations/{organization['id']}",
        headers={"X-RS-Roles": "system.organizations.delete"},
    )
    assert blocked.status_code == 409
    assert "users" in blocked.json()["detail"].lower()


def test_user_effective_scopes_include_primary_and_parent_organizations(app_client):
    root_payload = organization_payload("ORG-NP", "南平市")
    root_payload["dataScopes"] = {"areas": ["350700"], "projects": ["CITY"]}
    root = app_client.post(
        "/api/admin/organizations", json=root_payload, headers={"X-RS-Roles": "admin"}
    ).json()
    child_payload = organization_payload("ORG-ZH", "建阳区", root["id"])
    child_payload["dataScopes"] = {"areas": ["350703"], "towns": ["黄坑镇"]}
    child = app_client.post(
        "/api/admin/organizations", json=child_payload, headers={"X-RS-Roles": "admin"}
    ).json()
    user = app_client.post(
        "/api/admin/users",
        json={
            "username": "organization_scope_user",
            "displayName": "组织范围用户",
            "status": "active",
            "roles": [],
            "dataScopes": {"blockCodes": ["LB-001"]},
            "properties": {"organizationId": child["id"]},
        },
        headers={"X-RS-Roles": "admin"},
    ).json()

    effective = app_client.get(
        f"/api/admin/users/{user['id']}/effective-permissions",
        headers={"X-RS-Roles": "system.users.view"},
    )
    assert effective.status_code == 200
    assert effective.json()["dataScopes"] == {
        "areas": ["350700", "350703"],
        "blockCodes": ["LB-001"],
        "projects": ["CITY"],
        "towns": ["黄坑镇"],
    }


def test_organization_endpoints_enforce_independent_permissions(app_client):
    denied = app_client.post(
        "/api/admin/organizations",
        json=organization_payload("ORG-DENIED", "无权限组织"),
        headers={"X-RS-Roles": "system.organizations.view"},
    )
    assert denied.status_code == 403
    assert "system.organizations.create" in denied.json()["detail"]

    catalog = app_client.get(
        "/api/admin/permission-catalog",
        headers={"X-RS-Roles": "system.roles.view"},
    )
    codes = {item["code"] for item in catalog.json()["permissions"]}
    assert {
        "system.organizations.view",
        "system.organizations.create",
        "system.organizations.update",
        "system.organizations.delete",
        "system.organizations.restore",
    } <= codes
