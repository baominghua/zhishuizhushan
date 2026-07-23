from __future__ import annotations

from server.modules.auth_config import auth_config_digest


def test_auth_config_digest_is_stable_and_changes_with_sensitive_settings():
    values = {
        "REMOTE_SENSING_API_TOKENS": '{"token":{"roles":["admin"]}}',
        "SMART_BAMBOO_BREAK_GLASS_TOKEN": "token",
        "SMART_BAMBOO_HUMAN_AUTH_ENABLED": "0",
        "SMART_BAMBOO_AUTH_REQUIRE_HTTPS": "1",
        "SMART_BAMBOO_TRUST_PROXY_HEADERS": "1",
        "SMART_BAMBOO_SESSION_COOKIE_SECURE": "1",
        "SMART_BAMBOO_TLS_ENABLED": "0",
        "SMART_BAMBOO_TLS_CERT_PATH": "",
        "SMART_BAMBOO_TLS_KEY_PATH": "",
    }

    first = auth_config_digest(values)
    reordered = auth_config_digest(dict(reversed(list(values.items()))))
    changed = auth_config_digest(values | {"SMART_BAMBOO_HUMAN_AUTH_ENABLED": "1"})

    assert len(first) == 64
    assert reordered == first
    assert changed != first


def test_auth_config_digest_ignores_host_local_tls_paths():
    primary = {
        "REMOTE_SENSING_API_TOKENS": '{"token":{"roles":["admin"]}}',
        "SMART_BAMBOO_BREAK_GLASS_TOKEN": "token",
        "SMART_BAMBOO_HUMAN_AUTH_ENABLED": "1",
        "SMART_BAMBOO_AUTH_REQUIRE_HTTPS": "1",
        "SMART_BAMBOO_TRUST_PROXY_HEADERS": "1",
        "SMART_BAMBOO_SESSION_COOKIE_SECURE": "1",
        "SMART_BAMBOO_TLS_ENABLED": "1",
        "SMART_BAMBOO_TLS_CERT_PATH": "/srv/smart-bamboo/tls/fullchain.pem",
        "SMART_BAMBOO_TLS_KEY_PATH": "/srv/smart-bamboo/tls/privkey.pem",
    }
    standby = primary | {
        "SMART_BAMBOO_TLS_CERT_PATH": "/srv/smart-bamboo-dr/tls/fullchain.pem",
        "SMART_BAMBOO_TLS_KEY_PATH": "/srv/smart-bamboo-dr/tls/privkey.pem",
    }

    assert auth_config_digest(primary) == auth_config_digest(standby)
