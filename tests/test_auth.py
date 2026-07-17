from __future__ import annotations

import json


def test_auth_config_reports_whether_authentication_is_required(app_client):
    response = app_client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json() == {"required": False, "scheme": "bearer"}


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
