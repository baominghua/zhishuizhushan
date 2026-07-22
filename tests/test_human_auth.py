from __future__ import annotations

from datetime import timedelta

import pytest

from server.modules import admin_users
from server.modules import human_auth
from server.modules.auth_store import (
    create_session,
    credential_for_user,
    iso_utc,
    new_credential,
    record_failed_login,
    save_credential,
    save_session,
    session_for_token,
    utc_now,
)
from server.modules.passwords import hash_password, verify_password


@pytest.fixture()
def password_user_client(app_client):
    user = admin_users.normalize_user(
        {
            "username": "field_worker",
            "displayName": "Field Worker",
            "status": "active",
            "roles": ["operator"],
            "dataScopes": {"areas": ["350782001"]},
        }
    )
    admin_users.save_users([user])
    save_credential(new_credential(user["id"], hash_password("Bamboo-2026!")))
    return app_client, user


def login(client):
    return client.post(
        "/api/auth/login",
        json={"username": " field_worker ", "password": "Bamboo-2026!"},
        headers={"X-Forwarded-Proto": "https"},
    )


def csrf_headers(response):
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_login_returns_profile_and_sets_http_only_cookie(password_user_client):
    client, _user = password_user_client

    response = login(client)

    assert response.status_code == 200
    assert response.json()["user"] == "field_worker"
    assert response.json()["roles"] == ["operator"]
    assert response.json()["mustChangePassword"] is True
    assert response.json()["csrfToken"]
    cookie = response.headers["set-cookie"]
    assert "smart_bamboo_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


def test_login_normalizes_whitespace_and_casefolded_username(password_user_client):
    client, _user = password_user_client

    response = client.post(
        "/api/auth/login",
        json={"username": "  FIELD_WORKER  ", "password": "Bamboo-2026!"},
        headers={"X-Forwarded-Proto": "https"},
    )

    assert response.status_code == 200
    assert response.json()["user"] == "field_worker"


def test_login_rejects_http_in_production(password_user_client, monkeypatch):
    client, _user = password_user_client
    monkeypatch.setenv("SMART_BAMBOO_DEPLOYMENT_MODE", "production")

    response = client.post(
        "/api/auth/login",
        json={"username": "field_worker", "password": "Bamboo-2026!"},
    )

    assert response.status_code == 426
    assert response.json()["detail"] == "HTTPS is required for password login"


def test_production_rejects_http_login_when_https_override_is_disabled(password_user_client, monkeypatch):
    client, _user = password_user_client
    monkeypatch.setenv("SMART_BAMBOO_DEPLOYMENT_MODE", "production")
    monkeypatch.setenv("SMART_BAMBOO_AUTH_REQUIRE_HTTPS", "0")

    response = client.post(
        "/api/auth/login",
        json={"username": "field_worker", "password": "Bamboo-2026!"},
    )

    assert response.status_code == 426
    assert response.json()["detail"] == "HTTPS is required for password login"


def test_production_trusted_proxy_https_sets_a_secure_cookie(password_user_client, monkeypatch):
    client, _user = password_user_client
    monkeypatch.setenv("SMART_BAMBOO_DEPLOYMENT_MODE", "production")
    monkeypatch.setenv("SMART_BAMBOO_AUTH_REQUIRE_HTTPS", "0")
    monkeypatch.setenv("SMART_BAMBOO_TRUST_PROXY_HEADERS", "1")
    human_auth.get_settings.cache_clear()
    try:
        response = client.post(
            "/api/auth/login",
            json={"username": "field_worker", "password": "Bamboo-2026!"},
            headers={"X-Forwarded-Proto": "https"},
        )
    finally:
        human_auth.get_settings.cache_clear()

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


def test_five_bad_passwords_lock_account(password_user_client):
    client, _user = password_user_client
    headers = {"X-Forwarded-Proto": "https"}

    for _ in range(5):
        response = client.post(
            "/api/auth/login",
            json={"username": "field_worker", "password": "wrong-password"},
            headers=headers,
        )

    assert response.status_code == 423
    assert response.json()["detail"] == "Account temporarily locked"


def test_successful_login_resets_previous_failed_login_count(password_user_client):
    client, user = password_user_client
    record_failed_login(user["id"], utc_now())

    response = login(client)
    credential = credential_for_user(user["id"])

    assert response.status_code == 200
    assert credential is not None
    assert credential["failedLoginCount"] == 0
    assert credential["lockedUntil"] is None


def test_session_returns_current_human_profile(password_user_client):
    client, _user = password_user_client

    response = login(client)
    session = client.get("/api/auth/session")

    assert response.status_code == 200
    assert session.status_code == 200
    assert session.json() == {
        "authenticated": True,
        "user": "field_worker",
        "roles": ["operator"],
        "mustChangePassword": True,
    }


def test_request_context_accepts_human_session(password_user_client):
    client, _user = password_user_client

    login_response = login(client)
    response = client.get("/api/auth/me")

    assert login_response.status_code == 200
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert response.json()["authType"] == "session"
    assert response.json()["mustChangePassword"] is True
    assert response.json()["sessionExpiresAt"]
    assert response.json()["roles"] == ["operator"]
    assert response.json()["permissions"]
    assert response.json()["menuModules"]
    assert response.json()["dataScopes"]["areas"] == ["350782001"]


def test_forced_password_change_blocks_non_auth_api(password_user_client):
    client, _user = password_user_client

    login_response = login(client)
    response = client.get("/api/admin/effective-permissions")

    assert login_response.status_code == 200
    assert response.status_code == 403
    assert response.json()["detail"] == "Password change required"


def test_forced_password_change_blocks_legacy_cache_routes_and_requires_csrf(password_user_client):
    client, user = password_user_client

    login_response = login(client)
    forced_read = client.get("/api/cache/tiles")
    forced_delete = client.delete("/api/cache/tiles")
    credential = credential_for_user(user["id"])
    assert credential is not None
    credential["mustChangePassword"] = False
    save_credential(credential)
    missing_csrf = client.delete("/api/cache/tiles")
    accepted = client.delete("/api/cache/tiles", headers=csrf_headers(login_response))

    assert login_response.status_code == 200
    assert forced_read.status_code == 403
    assert forced_read.json()["detail"] == "Password change required"
    assert forced_delete.status_code == 403
    assert forced_delete.json()["detail"] == "Password change required"
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["detail"] == "CSRF validation failed"
    assert accepted.status_code == 200


def test_forced_password_change_blocks_config_and_login(password_user_client):
    client, _user = password_user_client

    login_response = login(client)
    config = client.get("/api/auth/config")
    retry_login = login(client)

    assert login_response.status_code == 200
    assert config.status_code == 403
    assert config.json()["detail"] == "Password change required"
    assert retry_login.status_code == 403
    assert retry_login.json()["detail"] == "Password change required"


def test_forced_password_change_blocks_public_api_routes(password_user_client):
    client, _user = password_user_client

    login_response = login(client)
    response = client.get("/api/health")

    assert login_response.status_code == 200
    assert response.status_code == 403
    assert response.json()["detail"] == "Password change required"


def test_anonymous_auth_config_and_login_remain_available(password_user_client):
    client, _user = password_user_client

    config = client.get("/api/auth/config")
    login_response = login(client)

    assert config.status_code == 200
    assert login_response.status_code == 200


def test_cookie_session_requires_csrf_for_mutating_api(password_user_client):
    client, user = password_user_client

    login_response = login(client)
    credential = credential_for_user(user["id"])
    assert credential is not None
    credential["mustChangePassword"] = False
    save_credential(credential)
    response = client.post(
        "/api/admin/roles/preview",
        json={},
        headers={"X-CSRF-Token": "not-the-session-token"},
    )

    assert login_response.status_code == 200
    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"


def test_logout_requires_csrf_and_revokes_the_current_session(password_user_client):
    client, _user = password_user_client
    login_response = login(client)

    rejected = client.post("/api/auth/logout")
    response = client.post("/api/auth/logout", headers=csrf_headers(login_response))
    session = client.get("/api/auth/session")

    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "CSRF validation failed"
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "smart_bamboo_session=\"\"" in response.headers["set-cookie"]
    assert session.status_code == 401


def test_session_rejects_an_expired_persisted_session(password_user_client):
    client, _user = password_user_client
    login_response = login(client)
    raw_token = client.cookies.get("smart_bamboo_session")
    record = session_for_token(raw_token, utc_now())
    assert login_response.status_code == 200
    assert record is not None
    record["expiresAt"] = iso_utc(utc_now() - timedelta(seconds=1))
    save_session(record)

    response = client.get("/api/auth/session")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_change_password_enforces_csrf_and_revokes_other_sessions(password_user_client):
    client, user = password_user_client
    login_response = login(client)
    credential = credential_for_user(user["id"])
    assert credential is not None
    other_token, _other_csrf, _other = create_session(
        user["id"], credential["credentialVersion"], utc_now(), "127.0.0.1", "pytest"
    )
    payload = {"currentPassword": "Bamboo-2026!", "newPassword": "New-Bamboo-2026!"}

    rejected = client.post("/api/auth/change-password", json=payload)
    response = client.post(
        "/api/auth/change-password", json=payload, headers=csrf_headers(login_response)
    )
    updated = credential_for_user(user["id"])

    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "CSRF validation failed"
    assert response.status_code == 200
    assert response.json() == {"ok": True, "mustChangePassword": False}
    assert updated is not None
    assert updated["credentialVersion"] == 2
    assert updated["mustChangePassword"] is False
    assert verify_password(updated["passwordHash"], "New-Bamboo-2026!")
    assert not verify_password(updated["passwordHash"], "Bamboo-2026!")
    assert session_for_token(other_token, utc_now()) is None
    assert client.get("/api/auth/session").status_code == 200


def test_authentication_audits_never_record_credentials_or_session_secrets(password_user_client):
    client, user = password_user_client
    login_response = login(client)
    raw_token = client.cookies.get("smart_bamboo_session")
    client.post("/api/auth/logout", headers=csrf_headers(login_response))

    stored = admin_users.find_user(user["id"])
    assert stored is not None
    events = stored["properties"]["auditEvents"]
    serialized_events = str(events)
    assert [event["action"] for event in events[-2:]] == ["login_success", "logout"]
    assert "Bamboo-2026!" not in serialized_events
    assert login_response.json()["csrfToken"] not in serialized_events
    assert raw_token not in serialized_events
    assert credential_for_user(user["id"])["passwordHash"] not in serialized_events


def test_password_change_audit_never_records_credentials_or_session_secrets(password_user_client):
    client, user = password_user_client
    login_response = login(client)
    raw_token = client.cookies.get("smart_bamboo_session")
    previous_hash = credential_for_user(user["id"])["passwordHash"]
    payload = {"currentPassword": "Bamboo-2026!", "newPassword": "New-Bamboo-2026!"}

    response = client.post(
        "/api/auth/change-password", json=payload, headers=csrf_headers(login_response)
    )
    stored = admin_users.find_user(user["id"])
    current_hash = credential_for_user(user["id"])["passwordHash"]

    assert response.status_code == 200
    assert stored is not None
    serialized_events = str(stored["properties"]["auditEvents"])
    assert stored["properties"]["auditEvents"][-1]["action"] == "password_change"
    assert payload["currentPassword"] not in serialized_events
    assert payload["newPassword"] not in serialized_events
    assert previous_hash not in serialized_events
    assert current_hash not in serialized_events
    assert raw_token not in serialized_events
    assert login_response.json()["csrfToken"] not in serialized_events
