from __future__ import annotations

import os
import json
import re
import subprocess
import sys
from pathlib import Path

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
