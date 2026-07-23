from datetime import UTC, datetime, timedelta
import os
import sqlite3
import stat
import threading

import pytest

import server.modules.auth_store as auth_store
from server.modules.auth_store import (
    create_session,
    credential_for_user,
    new_credential,
    record_failed_login,
    reset_failed_login,
    revoke_session,
    revoke_user_sessions,
    save_credential,
    save_session,
    session_for_token,
)
from server.modules.database import admin_credentials_json_path, admin_sessions_json_path


@pytest.fixture(autouse=True)
def clear_settings_cache(isolated_env):
    from server.modules.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_human_auth_storage_readiness_fails_closed_for_json_storage(monkeypatch):
    monkeypatch.setattr(auth_store, "use_mysql", lambda: False)

    assert auth_store.human_auth_storage_readiness() == {
        "backend": "json",
        "reachable": False,
        "credentialTable": False,
        "sessionTable": False,
        "activeAdminCredential": False,
    }


def test_human_auth_storage_readiness_queries_mysql_tables_and_active_credential(monkeypatch):
    class Cursor:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement):
            self.statements.append(statement)

        def fetchall(self):
            return [("admin_user_credentials",), ("admin_sessions",)]

        def fetchone(self):
            return (1,)

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

    connection = Connection()
    monkeypatch.setattr(auth_store, "use_mysql", lambda: True)
    monkeypatch.setattr(auth_store, "mysql_connect", lambda: connection)

    readiness = auth_store.human_auth_storage_readiness()

    assert readiness == {
        "backend": "mysql",
        "reachable": True,
        "credentialTable": True,
        "sessionTable": True,
        "activeAdminCredential": True,
    }
    assert "information_schema.tables" in connection.cursor_instance.statements[0]
    assert "admin_user_credentials" in connection.cursor_instance.statements[1]
    assert "admin_users" in connection.cursor_instance.statements[1]


def _active_admin_credential_count(
    *,
    user_status: str = "active",
    user_deleted_at: str | None = None,
    role_code: str = "admin",
    role_status: str = "active",
    role_deleted_at: str | None = None,
    has_role: bool = True,
    has_credential: bool = True,
    password_hash: str | None = "$argon2id$valid",
    password_changed_at: str | None = "2026-07-22T00:00:00+00:00",
    credential_version: int = 1,
    credential_created_at: str | None = "2026-07-22T00:00:00+00:00",
    credential_updated_at: str | None = "2026-07-22T00:00:00+00:00",
) -> int:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE admin_users (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE TABLE admin_roles (
            id TEXT PRIMARY KEY,
            role_code TEXT NOT NULL,
            status TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE TABLE admin_user_roles (
            admin_user_id TEXT NOT NULL,
            admin_role_id TEXT NOT NULL
        );
        CREATE TABLE admin_user_credentials (
            admin_user_id TEXT NOT NULL,
            password_hash TEXT,
            password_changed_at TEXT,
            credential_version INTEGER,
            created_at TEXT,
            updated_at TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO admin_users VALUES (?, ?, ?)",
        ("user-1", user_status, user_deleted_at),
    )
    connection.execute(
        "INSERT INTO admin_roles VALUES (?, ?, ?, ?)",
        ("role-1", role_code, role_status, role_deleted_at),
    )
    if has_role:
        connection.execute(
            "INSERT INTO admin_user_roles VALUES (?, ?)",
            ("user-1", "role-1"),
        )
    if has_credential:
        connection.execute(
            "INSERT INTO admin_user_credentials VALUES (?, ?, ?, ?, ?, ?)",
            (
                "user-1",
                password_hash,
                password_changed_at,
                credential_version,
                credential_created_at,
                credential_updated_at,
            ),
        )
    try:
        cursor = connection.cursor()
        cursor.execute(auth_store.ACTIVE_ADMIN_CREDENTIAL_COUNT_SQL.replace("BINARY ", ""))
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()


def test_active_admin_credential_production_sql_uses_binary_status_and_role_checks():
    sql = auth_store.ACTIVE_ADMIN_CREDENTIAL_COUNT_SQL

    assert "BINARY admin_user.status = 'active'" in sql
    assert "BINARY admin_role.status = 'active'" in sql
    assert "BINARY admin_role.role_code = 'admin'" in sql


@pytest.mark.parametrize(
    ("case", "kwargs", "expected"),
    [
        ("ordinary_user_credential", {"role_code": "operator"}, 0),
        ("uppercase_user_status", {"user_status": "ACTIVE"}, 0),
        ("mixed_case_user_status", {"user_status": "Active"}, 0),
        ("inactive_user", {"user_status": "inactive"}, 0),
        ("deleted_user", {"user_deleted_at": "2026-07-22T00:00:00+00:00"}, 0),
        ("inactive_admin_role", {"role_status": "inactive"}, 0),
        ("uppercase_role_status", {"role_status": "ACTIVE"}, 0),
        ("mixed_case_role_status", {"role_status": "Active"}, 0),
        ("deleted_admin_role", {"role_deleted_at": "2026-07-22T00:00:00+00:00"}, 0),
        ("uppercase_role_code", {"role_code": "ADMIN"}, 0),
        ("mixed_case_role_code", {"role_code": "Admin"}, 0),
        ("no_role", {"has_role": False}, 0),
        ("no_credential", {"has_credential": False}, 0),
        ("blank_password_hash", {"password_hash": "  "}, 0),
        ("missing_password_change", {"password_changed_at": None}, 0),
        ("zero_credential_version", {"credential_version": 0}, 0),
        ("missing_credential_created_at", {"credential_created_at": None}, 0),
        ("missing_credential_updated_at", {"credential_updated_at": None}, 0),
        ("active_admin_credential", {}, 1),
    ],
)
def test_active_admin_credential_query_enforces_real_relational_constraints(case, kwargs, expected):
    assert _active_admin_credential_count(**kwargs) == expected, case


def test_human_auth_storage_readiness_fails_closed_when_mysql_is_unreachable(monkeypatch):
    monkeypatch.setattr(auth_store, "use_mysql", lambda: True)

    def unavailable_mysql():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(auth_store, "mysql_connect", unavailable_mysql)

    assert auth_store.human_auth_storage_readiness() == {
        "backend": "mysql",
        "reachable": False,
        "credentialTable": False,
        "sessionTable": False,
        "activeAdminCredential": False,
    }


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


def test_stale_json_session_save_cannot_clear_a_concurrent_revocation(isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    raw_token, _csrf, _session = create_session(
        "user-1", 1, now, "127.0.0.1", "pytest"
    )
    stale = session_for_token(raw_token, now)
    assert stale is not None

    revoke_session(raw_token)
    stale["lastSeenAt"] = (now + timedelta(minutes=1)).isoformat()
    save_session(stale)

    assert session_for_token(raw_token, now + timedelta(minutes=1)) is None


def test_mysql_session_touch_is_conditional_on_an_unrevoked_current_row(monkeypatch):
    calls = []

    class Cursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            calls.append((" ".join(sql.split()), params))

    class Connection:
        committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

        def commit(self):
            self.committed = True

    connection = Connection()
    monkeypatch.setattr(auth_store, "use_mysql", lambda: True)
    monkeypatch.setattr(auth_store, "mysql_connect", lambda: connection)
    record = {
        "id": "session-1",
        "userId": "user-1",
        "tokenHash": "token-hash",
        "csrfTokenHash": "csrf-hash",
        "credentialVersion": 1,
        "ipAddress": "127.0.0.1",
        "userAgent": "pytest",
        "issuedAt": "2026-07-22T09:00:00+00:00",
        "lastSeenAt": "2026-07-22T09:01:00+00:00",
        "expiresAt": "2026-07-22T10:00:00+00:00",
        "revokedAt": None,
    }

    touched = auth_store.touch_session(record)

    assert touched is False
    assert connection.committed is True
    assert "revoked_at IS NULL" in calls[0][0]
    assert "credential_version = %s" in calls[0][0]


def _run_concurrently(workers):
    start = threading.Barrier(len(workers) + 1)
    errors = []

    def run(worker):
        try:
            start.wait()
            worker()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join()
    assert errors == []


def _delay_parallel_json_writes(monkeypatch, path, participants):
    original_save = auth_store.save_json_records
    write_barrier = threading.Barrier(participants)

    def delayed_save(saved_path, records):
        if saved_path == path:
            try:
                write_barrier.wait(timeout=0.1)
            except threading.BrokenBarrierError:
                pass
        original_save(saved_path, records)

    monkeypatch.setattr(auth_store, "save_json_records", delayed_save)


def test_concurrent_json_failed_logins_keep_every_increment(monkeypatch, isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    save_credential(new_credential("user-1", "$argon2id$test"))
    _delay_parallel_json_writes(monkeypatch, admin_credentials_json_path(), participants=5)

    _run_concurrently([lambda: record_failed_login("user-1", now) for _ in range(5)])

    credential = credential_for_user("user-1")
    assert credential["failedLoginCount"] == 5
    assert credential["lockedUntil"] == (now + timedelta(minutes=15)).isoformat()


def test_mysql_failed_login_locks_credential_row_in_its_update_transaction(monkeypatch, isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    row = (
        "credential-1", "user-1", "$argon2id$test", now.replace(tzinfo=None), True,
        4, None, 1, now.replace(tzinfo=None), now.replace(tzinfo=None),
    )
    connections = []

    class Cursor:
        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), params))

        def fetchone(self):
            return row

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.committed = True

    def connect():
        connection = Connection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(auth_store, "use_mysql", lambda: True)
    monkeypatch.setattr(auth_store, "mysql_connect", connect)

    credential = record_failed_login("user-1", now)

    assert credential["failedLoginCount"] == 5
    assert len(connections) == 1
    assert connections[0].committed is True
    assert "FOR UPDATE" in connections[0].cursor_instance.calls[0][0]


def test_concurrent_json_session_creates_and_revocations_keep_all_records(monkeypatch, isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    _delay_parallel_json_writes(monkeypatch, admin_sessions_json_path(), participants=5)
    created = []
    created_lock = threading.Lock()

    def create():
        raw_token, _csrf_token, _record = create_session("user-1", 1, now, "127.0.0.1", "pytest")
        with created_lock:
            created.append(raw_token)

    _run_concurrently([create for _ in range(5)])
    assert len(created) == 5
    assert len(auth_store.load_json_records(admin_sessions_json_path())) == 5

    _delay_parallel_json_writes(monkeypatch, admin_sessions_json_path(), participants=5)
    _run_concurrently([lambda token=token: revoke_session(token) for token in created])

    assert all(session_for_token(token, now) is None for token in created)


def test_json_session_store_never_persists_raw_tokens(isolated_env):
    now = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    raw_token, csrf_token, _record = create_session("user-1", 1, now, "127.0.0.1", "pytest")

    persisted = admin_sessions_json_path().read_text(encoding="utf-8")

    assert raw_token not in persisted
    assert csrf_token not in persisted


def test_json_credential_upsert_preserves_existing_identity(isolated_env):
    original = new_credential("user-1", "$argon2id$first")
    save_credential(original)

    replacement = new_credential("user-1", "$argon2id$replacement")
    save_credential(replacement)

    stored = credential_for_user("user-1")
    assert stored["id"] == original["id"]
    assert stored["createdAt"] == original["createdAt"]
    assert stored["passwordHash"] == "$argon2id$replacement"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are enforced on deployment hosts")
def test_json_credentials_are_written_owner_only_and_directory_entry_is_durable(
    monkeypatch, isolated_env
):
    fsynced_directories = []
    original_open = os.open

    def tracking_open(path, flags, *args, **kwargs):
        descriptor = original_open(path, flags, *args, **kwargs)
        if flags & getattr(os, "O_DIRECTORY", 0):
            fsynced_directories.append(str(path))
        return descriptor

    monkeypatch.setattr(auth_store.os, "open", tracking_open)
    save_credential(new_credential("user-1", "$argon2id$test"))

    path = admin_credentials_json_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert str(path.parent) in fsynced_directories
