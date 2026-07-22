from __future__ import annotations

import os
import json
import re
import subprocess
import sys
import importlib.util
import io
from pathlib import Path

import pytest
from server.modules import admin_users
from server.modules.auth_store import credential_for_user
from server.modules.passwords import verify_password


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def bootstrap_command():
    return [sys.executable, "ops/scripts/bootstrap-admin-password.py", "--username", "bootstrap_admin", "--display-name", "Bootstrap Admin"]


def bootstrap_env(tmp_path):
    environment = os.environ.copy()
    environment.update(
        {
            "REMOTE_SENSING_DATA_DIR": str(tmp_path / "remote-sensing"),
            "SMART_BAMBOO_STORAGE_BACKEND": "json",
        }
    )
    environment.pop("SMART_BAMBOO_DATABASE_URL", None)
    return environment


def load_bootstrap_module():
    spec = importlib.util.spec_from_file_location(
        "bootstrap_admin_password", PROJECT_ROOT / "ops" / "scripts" / "bootstrap-admin-password.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_bootstrap_rejects_json_storage_without_explicit_development_flag(tmp_path):
    result = subprocess.run(
        bootstrap_command(),
        cwd=PROJECT_ROOT,
        env=bootstrap_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--allow-json-development" in result.stderr
    assert not (tmp_path / "remote-sensing" / "admin" / "credentials.json").exists()


def test_bootstrap_rejects_mysql_backend_without_a_database_url_and_never_writes_json(tmp_path):
    environment = bootstrap_env(tmp_path)
    environment["SMART_BAMBOO_STORAGE_BACKEND"] = "mysql"

    result = subprocess.run(
        bootstrap_command(),
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "MySQL" in result.stderr
    assert not (tmp_path / "remote-sensing" / "admin").exists()


def test_bootstrap_generates_one_temporary_password_without_persisting_it(tmp_path, monkeypatch):
    result = subprocess.run(
        [*bootstrap_command(), "--allow-json-development"],
        cwd=PROJECT_ROOT,
        env=bootstrap_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    matches = re.findall(r"Temporary password: (.+)", result.stdout)
    assert len(matches) == 1
    temporary_password = matches[0]
    assert len(temporary_password) == 20
    monkeypatch.setenv("REMOTE_SENSING_DATA_DIR", str(tmp_path / "remote-sensing"))
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "json")
    from server.modules.settings import get_settings

    get_settings.cache_clear()
    try:
        user = admin_users.user_by_username("bootstrap_admin")
        assert user is not None
        assert user["status"] == "active"
        assert user["roles"] == ["admin"]
        roles_path = tmp_path / "remote-sensing" / "admin" / "roles.json"
        assert roles_path.exists()
        roles = json.loads(roles_path.read_text(encoding="utf-8"))
        admin_role = next(role for role in roles if role["roleCode"] == "admin")
        assert "system.users.manage" in admin_role["permissions"]
        assert "users" in admin_role["menuModules"]
        credential = credential_for_user(user["id"])
        assert credential is not None
        assert credential["mustChangePassword"] is True
        assert verify_password(credential["passwordHash"], temporary_password)
        assert all(
            temporary_password not in path.read_text(encoding="utf-8")
            for path in (tmp_path / "remote-sensing").rglob("*")
            if path.is_file()
        )
    finally:
        get_settings.cache_clear()


def test_bootstrap_restores_a_deleted_same_name_administrator_instead_of_duplicating_it(tmp_path):
    environment = bootstrap_env(tmp_path)
    first = subprocess.run(
        [*bootstrap_command(), "--allow-json-development"],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    users_path = tmp_path / "remote-sensing" / "admin" / "users.json"
    users = json.loads(users_path.read_text(encoding="utf-8"))
    users[0]["deletedAt"] = "2026-07-22T00:00:00+00:00"
    users_path.write_text(json.dumps(users), encoding="utf-8")

    supplied_password = "Supplied-Bamboo-2026!"
    restored = subprocess.run(
        [*bootstrap_command(), "--allow-json-development", "--password-stdin"],
        cwd=PROJECT_ROOT,
        env=environment,
        input=supplied_password + "\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert restored.returncode == 0, restored.stderr
    assert supplied_password not in restored.stdout
    users = json.loads(users_path.read_text(encoding="utf-8"))
    assert len(users) == 1
    assert users[0]["deletedAt"] is None
    assert users[0]["roles"] == ["admin"]
    credentials = json.loads((tmp_path / "remote-sensing" / "admin" / "credentials.json").read_text(encoding="utf-8"))
    assert credentials[0]["credentialVersion"] == 2
    assert verify_password(credentials[0]["passwordHash"], supplied_password)


def test_bootstrap_rolls_back_json_user_and_role_when_credential_write_fails(tmp_path, monkeypatch):
    module = load_bootstrap_module()
    monkeypatch.setenv("REMOTE_SENSING_DATA_DIR", str(tmp_path / "remote-sensing"))
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "json")
    module.get_settings.cache_clear()
    monkeypatch.setattr(sys, "argv", [
        "bootstrap-admin-password.py", "--username", "rollback_admin", "--display-name", "Rollback Admin",
        "--allow-json-development", "--password-stdin",
    ])
    monkeypatch.setattr(sys, "stdin", io.StringIO("Rollback-Bamboo-2026!\n"))
    monkeypatch.setattr(module, "save_credential", lambda _credential: (_ for _ in ()).throw(RuntimeError("credential write failed")))

    with pytest.raises(RuntimeError, match="credential write failed"):
        module.main()

    admin_dir = tmp_path / "remote-sensing" / "admin"
    assert not (admin_dir / "users.json").exists()
    assert not (admin_dir / "roles.json").exists()
    assert not (admin_dir / "credentials.json").exists()


def test_bootstrap_mysql_path_commits_role_user_and_credential_in_one_transaction(monkeypatch):
    module = load_bootstrap_module()
    calls = []

    class Cursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            calls.append(("sql", " ".join(sql.split()), params))

        def fetchone(self):
            return (1,)

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()
            self.committed = False
            self.rolled_back = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    connection = Connection()
    monkeypatch.setattr(module, "use_mysql", lambda: True)
    monkeypatch.setattr(module, "mysql_connect", lambda: connection)
    monkeypatch.setattr(module.admin_roles, "role_by_code", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.admin_users, "user_by_username", lambda *_args: None)
    monkeypatch.setattr(module.admin_users, "load_all_users", lambda: [])
    monkeypatch.setattr(module.admin_roles, "execute_upsert_role_mysql", lambda _cur, role: calls.append(("role", role)))
    monkeypatch.setattr(module.admin_users, "execute_upsert_user_mysql", lambda _cur, user: calls.append(("user", user)))
    monkeypatch.setattr(module, "mysql_credential_for_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "write_mysql_credential", lambda _cur, credential: calls.append(("credential", credential)))
    monkeypatch.setattr(sys, "stdin", io.StringIO("Mysql-Bamboo-2026!\n"))
    monkeypatch.setattr(sys, "argv", [
        "bootstrap-admin-password.py", "--username", "mysql_admin", "--display-name", "MySQL Admin", "--password-stdin",
    ])

    assert module.main() == 0
    assert connection.committed is True
    assert connection.rolled_back is False
    assert next(item[1] for item in calls if item[0] == "role")["roleCode"] == "admin"
    assert "admin" in next(item[1] for item in calls if item[0] == "user")["roles"]
    assert next(item[1] for item in calls if item[0] == "credential")["mustChangePassword"] is True
    assert any("FROM admin_user_roles" in item[1] for item in calls if item[0] == "sql")
