from __future__ import annotations

import json


def test_auth_config_reports_whether_authentication_is_required(app_client):
    response = app_client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "required": False,
        "scheme": "session-or-bearer",
        "humanLoginEnabled": False,
        "httpsRequired": False,
        "serviceTokenEnabled": False,
    }


def test_auth_me_returns_effective_role_menu_and_scope(app_client):
    response = app_client.get(
        "/api/auth/me",
        headers={
            "X-RS-User": "forest-operator",
            "X-RS-Roles": "admin",
            "X-RS-Areas": "350703",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == "forest-operator"
    assert "admin" in body["roles"]
    assert body["permissions"]
    assert body["visibleMenuModules"]
    assert body["dataScopes"]["areas"] == ["350703"]


def test_auth_me_requires_and_accepts_bearer_token(app_client, monkeypatch):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv(
        "REMOTE_SENSING_API_TOKENS",
        json.dumps(
            {
                "secure-test-token": {
                    "user": "token-admin",
                    "roles": ["admin"],
                    "areas": ["350703"],
                    "projects": ["*"],
                }
            }
        ),
    )
    settings.get_settings.cache_clear()
    try:
        unauthorized = app_client.get("/api/auth/me")
        authorized = app_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer secure-test-token"},
        )
    finally:
        settings.get_settings.cache_clear()

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["user"] == "token-admin"
    assert authorized.json()["authenticated"] is True
    assert authorized.json()["authType"] == "service-token"
    assert authorized.json()["mustChangePassword"] is False
    assert authorized.json()["sessionExpiresAt"] is None
    assert authorized.json()["roles"] == ["admin"]
    assert authorized.json()["permissions"]
    assert authorized.json()["menuModules"]
    assert authorized.json()["dataScopes"]["areas"] == ["350703"]
    assert authorized.json()["permissionImplications"]


def test_human_auth_mode_rejects_every_service_token_transport(app_client, monkeypatch):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "1")
    monkeypatch.setenv(
        "REMOTE_SENSING_API_TOKENS",
        json.dumps({"secure-test-token": {"user": "token-admin", "roles": ["admin"]}}),
    )
    settings.get_settings.cache_clear()
    try:
        config = app_client.get("/api/auth/config")
        responses = [
            app_client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer secure-test-token"},
            ),
            app_client.get(
                "/api/auth/me",
                headers={"X-RS-Token": "secure-test-token"},
            ),
            app_client.get("/api/auth/me?token=secure-test-token"),
        ]
    finally:
        settings.get_settings.cache_clear()

    assert config.status_code == 200
    assert config.json()["serviceTokenEnabled"] is False
    assert [response.status_code for response in responses] == [401, 401, 401]


def test_human_auth_mode_stays_fail_closed_when_auth_required_flag_is_off(
    app_client, monkeypatch
):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "0")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "1")
    settings.get_settings.cache_clear()
    try:
        config = app_client.get("/api/auth/config")
        response = app_client.get(
            "/api/auth/me",
            headers={"X-RS-User": "forged", "X-RS-Roles": "admin"},
        )
    finally:
        settings.get_settings.cache_clear()

    assert config.status_code == 200
    assert config.json()["required"] is True
    assert response.status_code == 401


def test_public_browser_config_only_exposes_dashboard_token_in_service_mode(
    app_client, monkeypatch
):
    import server.modules.settings as settings

    dashboard_token = "dashboard-token-must-not-leak"
    monkeypatch.setenv("SMART_BAMBOO_DASHBOARD_TOKEN", dashboard_token)
    monkeypatch.setenv(
        "REMOTE_SENSING_API_TOKENS",
        json.dumps(
            {
                dashboard_token: {
                    "user": "dashboard",
                    "roles": ["viewer"],
                    "projects": ["*"],
                    "areas": ["*"],
                }
            }
        ),
    )
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "1")
    settings.get_settings.cache_clear()
    try:
        human_config = app_client.get("/satellite-config.local.js")
        monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
        monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
        settings.get_settings.cache_clear()
        service_config = app_client.get("/satellite-config.local.js")
    finally:
        settings.get_settings.cache_clear()

    assert human_config.status_code == 200
    assert "humanLoginEnabled: true" in human_config.text
    assert dashboard_token not in human_config.text
    assert service_config.status_code == 200
    assert "humanLoginEnabled: false" in service_config.text
    assert dashboard_token in service_config.text
    assert human_config.headers["cache-control"].startswith("no-store")


def test_public_browser_config_refuses_a_privileged_dashboard_token(
    app_client, monkeypatch
):
    import server.modules.settings as settings

    dashboard_token = "privileged-dashboard-token"
    monkeypatch.setenv("SMART_BAMBOO_DASHBOARD_TOKEN", dashboard_token)
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv(
        "REMOTE_SENSING_API_TOKENS",
        json.dumps(
            {
                dashboard_token: {
                    "user": "dashboard",
                    "roles": ["admin"],
                    "projects": ["*"],
                    "areas": ["*"],
                }
            }
        ),
    )
    settings.get_settings.cache_clear()
    try:
        response = app_client.get("/satellite-config.local.js")
    finally:
        settings.get_settings.cache_clear()

    assert response.status_code == 200
    assert dashboard_token not in response.text


def test_development_header_context_ignores_unconfigured_bearer_token(app_client):
    response = app_client.get(
        "/api/auth/me",
        headers={
            "Authorization": "Bearer not-configured",
            "X-RS-User": "forest-operator",
            "X-RS-Roles": "admin",
            "X-RS-Areas": "350703",
        },
    )

    assert response.status_code == 200
    assert response.json()["authenticated"] is False
    assert response.json()["authType"] == "development-header"
    assert response.json()["user"] == "forest-operator"


def test_service_bearer_unsafe_legacy_route_does_not_require_csrf(app_client, monkeypatch):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv(
        "REMOTE_SENSING_API_TOKENS",
        json.dumps({"secure-test-token": {"user": "token-admin", "roles": ["admin"]}}),
    )
    settings.get_settings.cache_clear()
    try:
        response = app_client.delete(
            "/api/cache/tiles",
            headers={"Authorization": "Bearer secure-test-token"},
        )
    finally:
        settings.get_settings.cache_clear()

    assert response.status_code == 200


def test_viewer_service_token_cannot_delete_or_prune_tile_cache(app_client, monkeypatch):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv(
        "REMOTE_SENSING_API_TOKENS",
        json.dumps(
            {
                "viewer-token": {
                    "user": "dashboard",
                    "roles": ["imagery.scenes.view"],
                }
            }
        ),
    )
    settings.get_settings.cache_clear()
    headers = {"Authorization": "Bearer viewer-token"}
    try:
        status = app_client.get("/api/cache/tiles", headers=headers)
        delete = app_client.delete("/api/cache/tiles", headers=headers)
        prune = app_client.post("/api/cache/tiles/prune", headers=headers)
        tianditu_delete = app_client.delete("/api/cache/tianditu", headers=headers)
        tianditu_prune = app_client.post("/api/cache/tianditu/prune", headers=headers)
    finally:
        settings.get_settings.cache_clear()

    assert status.status_code == 200
    assert delete.status_code == 403
    assert prune.status_code == 403
    assert tianditu_delete.status_code == 403
    assert tianditu_prune.status_code == 403


def test_dashboard_service_token_ignores_database_roles_for_same_username(
    app_client, monkeypatch
):
    from server.modules import admin_roles, admin_users
    import server.modules.settings as settings

    admin_roles.save_roles(
        [
            admin_roles.normalize_role(
                {
                    "roleCode": "dashboard_database_admin",
                    "name": "Dashboard database admin",
                    "status": "active",
                    "permissions": ["imagery.cache.manage"],
                    "menuModules": ["imagery"],
                    "dataScopes": {"areas": ["*"], "projects": ["*"]},
                    "properties": {},
                }
            )
        ]
    )
    admin_users.save_users(
        [
            admin_users.normalize_user(
                {
                    "username": "dashboard",
                    "displayName": "Dashboard",
                    "status": "active",
                    "roles": ["dashboard_database_admin"],
                    "dataScopes": {"areas": ["*"], "projects": ["*"]},
                    "properties": {},
                }
            )
        ]
    )

    token = "database-role-isolation-token"
    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv("SMART_BAMBOO_DASHBOARD_TOKEN", token)
    monkeypatch.setenv(
        "REMOTE_SENSING_API_TOKENS",
        json.dumps(
            {
                token: {
                    "user": "dashboard",
                    "roles": ["viewer"],
                    "projects": ["*"],
                    "areas": ["*"],
                }
            }
        ),
    )
    settings.get_settings.cache_clear()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        runtime_config = app_client.get("/satellite-config.local.js")
        profile = app_client.get("/api/auth/me", headers=headers)
        status = app_client.get("/api/cache/tiles", headers=headers)
        delete = app_client.delete("/api/cache/tiles", headers=headers)
    finally:
        settings.get_settings.cache_clear()

    assert token in runtime_config.text
    assert profile.status_code == 200
    assert "system.users.view" not in profile.json()["permissions"]
    assert "system.roles.view" not in profile.json()["permissions"]
    assert status.status_code == 200
    assert delete.status_code == 403


def test_dashboard_service_token_ignores_mutable_viewer_role_permissions(
    app_client, monkeypatch
):
    from server.modules import admin_roles
    import server.modules.settings as settings

    admin_roles.save_roles(
        [
            admin_roles.normalize_role(
                {
                    "roleCode": "viewer",
                    "name": "Mutable viewer",
                    "status": "active",
                    "permissions": ["imagery.cache.manage"],
                    "menuModules": ["imagery"],
                    "dataScopes": {"areas": ["*"], "projects": ["*"]},
                    "properties": {},
                }
            )
        ]
    )

    token = "mutable-viewer-isolation-token"
    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv("SMART_BAMBOO_DASHBOARD_TOKEN", token)
    monkeypatch.setenv(
        "REMOTE_SENSING_API_TOKENS",
        json.dumps(
            {
                token: {
                    "user": "dashboard",
                    "roles": ["viewer"],
                    "projects": ["*"],
                    "areas": ["*"],
                }
            }
        ),
    )
    settings.get_settings.cache_clear()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        runtime_config = app_client.get("/satellite-config.local.js")
        status = app_client.get("/api/cache/tiles", headers=headers)
        delete = app_client.delete("/api/cache/tiles", headers=headers)
    finally:
        settings.get_settings.cache_clear()

    assert token in runtime_config.text
    assert status.status_code == 200
    assert delete.status_code == 403


def test_health_reports_unified_auth_configuration(app_client):
    response = app_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["deployment"]["auth"] == {
        "required": False,
        "tokensConfigured": 0,
    }


def test_liveness_health_is_small_and_skips_deployment_audit(app_client, monkeypatch):
    import server.app as app_module

    monkeypatch.setattr(
        app_module,
        "deployment_health_payload",
        lambda: (_ for _ in ()).throw(AssertionError("full deployment audit must not run")),
    )

    response = app_client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "status": "live"}
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert len(response.content) < 64


def test_json_string_service_profile_preserves_legacy_global_admin_scope(app_client, monkeypatch):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv("REMOTE_SENSING_API_TOKENS", json.dumps({"legacy-token": "legacy-user"}))
    settings.get_settings.cache_clear()
    try:
        headers = {"Authorization": "Bearer legacy-token"}
        profile = app_client.get("/api/auth/me", headers=headers)
        allowed_delete = app_client.delete("/api/scenes/missing-scene", headers=headers)
    finally:
        settings.get_settings.cache_clear()

    assert profile.status_code == 200
    assert profile.json()["user"] == "legacy-user"
    assert profile.json()["roles"] == ["admin"]
    assert profile.json()["dataScopes"] == {"areas": ["*"], "projects": ["*"]}
    assert allowed_delete.status_code == 404


def test_compact_service_profiles_preserve_legacy_identity_roles_and_scopes(app_client, monkeypatch):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv(
        "REMOTE_SENSING_API_TOKENS",
        "legacy-token=legacy-user|legacy-reader,legacy-writer|project-a project-b|350703,350704;"
        "empty-token=empty-user|||",
    )
    settings.get_settings.cache_clear()
    try:
        profile = app_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer legacy-token"},
        )
        empty_profile = app_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer empty-token"},
        )
    finally:
        settings.get_settings.cache_clear()

    assert profile.status_code == 200
    assert profile.json()["user"] == "legacy-user"
    assert profile.json()["roles"] == ["legacy-reader", "legacy-writer"]
    assert profile.json()["dataScopes"] == {
        "areas": ["350703", "350704"],
        "projects": ["project-a", "project-b"],
    }
    assert empty_profile.status_code == 200
    assert empty_profile.json()["user"] == "empty-user"
    assert empty_profile.json()["roles"] == []
    assert empty_profile.json()["dataScopes"] == {}


def test_comma_delimited_service_tokens_preserve_legacy_admin_defaults(app_client, monkeypatch):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv("REMOTE_SENSING_API_TOKENS", "alpha,beta")
    settings.get_settings.cache_clear()
    try:
        alpha = app_client.get("/api/auth/me", headers={"Authorization": "Bearer alpha"})
        beta = app_client.get("/api/auth/me", headers={"Authorization": "Bearer beta"})
    finally:
        settings.get_settings.cache_clear()

    for response, user in ((alpha, "alpha"), (beta, "beta")):
        assert response.status_code == 200
        assert response.json()["user"] == user
        assert response.json()["roles"] == ["admin"]
        assert response.json()["dataScopes"] == {"areas": ["*"], "projects": ["*"]}


def test_semicolon_delimited_service_tokens_preserve_legacy_admin_defaults(app_client, monkeypatch):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    monkeypatch.setenv("REMOTE_SENSING_API_TOKENS", "alpha;beta")
    settings.get_settings.cache_clear()
    try:
        alpha = app_client.get("/api/auth/me", headers={"Authorization": "Bearer alpha"})
        beta = app_client.get("/api/auth/me", headers={"Authorization": "Bearer beta"})
    finally:
        settings.get_settings.cache_clear()

    for response, user in ((alpha, "alpha"), (beta, "beta")):
        assert response.status_code == 200
        assert response.json()["user"] == user
        assert response.json()["roles"] == ["admin"]
        assert response.json()["dataScopes"] == {"areas": ["*"], "projects": ["*"]}
