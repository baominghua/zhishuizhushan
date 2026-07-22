from __future__ import annotations

import json


def test_auth_config_reports_whether_authentication_is_required(app_client):
    response = app_client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "required": False,
        "scheme": "session-or-bearer",
        "humanLoginEnabled": True,
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


def test_health_reports_unified_auth_configuration(app_client):
    response = app_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["deployment"]["auth"] == {
        "required": False,
        "tokensConfigured": 0,
    }


def test_json_string_service_profile_preserves_unprivileged_legacy_scope(app_client, monkeypatch):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("REMOTE_SENSING_API_TOKENS", json.dumps({"legacy-token": "legacy-user"}))
    settings.get_settings.cache_clear()
    try:
        headers = {"Authorization": "Bearer legacy-token"}
        profile = app_client.get("/api/auth/me", headers=headers)
        denied_delete = app_client.delete("/api/scenes/missing-scene", headers=headers)
    finally:
        settings.get_settings.cache_clear()

    assert profile.status_code == 200
    assert profile.json()["user"] == "legacy-user"
    assert profile.json()["roles"] == []
    assert profile.json()["permissions"] == []
    assert profile.json()["dataScopes"] == {}
    assert denied_delete.status_code == 403
    assert "imagery.scenes.delete" in denied_delete.json()["detail"]


def test_compact_service_profiles_preserve_legacy_identity_roles_and_scopes(app_client, monkeypatch):
    import server.modules.settings as settings

    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
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
