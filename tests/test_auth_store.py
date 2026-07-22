from datetime import UTC, datetime, timedelta

import pytest

from server.modules.auth_store import (
    create_session,
    credential_for_user,
    new_credential,
    record_failed_login,
    reset_failed_login,
    revoke_session,
    revoke_user_sessions,
    save_credential,
    session_for_token,
)


@pytest.fixture(autouse=True)
def clear_settings_cache(isolated_env):
    from server.modules.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_fifth_failure_locks_for_fifteen_minutes(isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    save_credential(new_credential("user-1", "$argon2id$test"))

    for _ in range(5):
        credential = record_failed_login("user-1", now)

    assert credential["failedLoginCount"] == 5
    assert credential["lockedUntil"] == (now + timedelta(minutes=15)).isoformat()


def test_reset_failed_login_clears_lock_and_persists_credential(isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    save_credential(new_credential("user-1", "$argon2id$test"))
    for _ in range(5):
        record_failed_login("user-1", now)

    credential = reset_failed_login("user-1")

    assert credential["failedLoginCount"] == 0
    assert credential["lockedUntil"] is None
    assert credential_for_user("user-1") == credential


def test_session_lookup_uses_hash_and_rejects_expired_token(isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)

    raw_token, csrf_token, record = create_session("user-1", 1, now, "127.0.0.1", "pytest")

    assert raw_token not in str(record)
    assert csrf_token not in str(record)
    assert session_for_token(raw_token, now)["userId"] == "user-1"
    assert session_for_token(raw_token, now + timedelta(hours=25)) is None


def test_session_revocation_by_token_and_user_preserves_excepted_session(isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    first_token, _csrf, first = create_session("user-1", 1, now, "127.0.0.1", "pytest")
    second_token, _csrf, second = create_session("user-1", 1, now, "127.0.0.1", "pytest")

    revoke_session(first_token)
    assert session_for_token(first_token, now) is None
    assert session_for_token(second_token, now) == second

    assert revoke_user_sessions("user-1", except_session_id=second["id"]) == 0
    assert session_for_token(second_token, now) == second
    assert revoke_user_sessions("user-1") == 1
    assert session_for_token(second_token, now) is None
