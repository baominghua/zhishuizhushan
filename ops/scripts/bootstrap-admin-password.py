#!/usr/bin/env python3
from __future__ import annotations

import argparse
import secrets
import string
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server.modules import admin_users
from server.modules.auth_store import credential_for_user, iso_utc, new_credential, save_credential, utc_now
from server.modules.passwords import hash_password, password_errors
from server.modules.settings import get_settings


def generated_temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(20))
        if not password_errors(password):
            return password


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize the first Smart Bamboo administrator password.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--password-stdin", action="store_true")
    parser.add_argument("--allow-json-development", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    if settings.storage_backend != "mysql" and not args.allow_json_development:
        print("Refusing non-MySQL storage; pass --allow-json-development only for local development.", file=sys.stderr)
        return 2

    generated = not args.password_stdin
    password = generated_temporary_password() if generated else sys.stdin.readline().rstrip("\r\n")
    errors = password_errors(password)
    if errors:
        print("Password does not meet policy: " + ", ".join(errors), file=sys.stderr)
        return 2

    username = admin_users.canonical_username(args.username)
    user = admin_users.user_by_username(username)
    if user is None:
        user = next(
            (
                candidate
                for candidate in admin_users.load_all_users()
                if admin_users.canonical_username(candidate.get("username")) == username
            ),
            None,
        )
    if user is None:
        user = admin_users.normalize_user(
            {
                "username": args.username,
                "displayName": args.display_name,
                "status": "active",
                "roles": ["admin"],
            }
        )
    else:
        user = admin_users.normalize_user(
            {
                **user,
                "displayName": args.display_name,
                "status": "active",
                "roles": admin_users.compact_list([*(user.get("roles") or []), "admin"]),
                "createdAt": user["createdAt"],
                "deletedAt": None,
            }
        )
    admin_users.save_user(user)

    now = utc_now()
    credential = credential_for_user(user["id"])
    if credential is None:
        credential = new_credential(user["id"], hash_password(password))
    else:
        credential["passwordHash"] = hash_password(password)
        credential["credentialVersion"] += 1
    credential["passwordChangedAt"] = iso_utc(now)
    credential["mustChangePassword"] = True
    credential["failedLoginCount"] = 0
    credential["lockedUntil"] = None
    credential["updatedAt"] = iso_utc(now)
    save_credential(credential)

    print(f"Bootstrap administrator initialized: {user['username']}")
    if generated:
        print(f"Temporary password: {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
