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

from server.modules import admin_roles, admin_users
from server.modules.auth import AuthContext
from server.modules.auth_store import credential_for_user, iso_utc, mysql_credential_for_user, new_credential, save_credential, utc_now, write_mysql_credential
from server.modules.database import admin_credentials_json_path, admin_roles_json_path, admin_sessions_json_path, admin_users_json_path, json_transaction, mysql_connect, use_mysql
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


def administrator_role() -> dict:
    return admin_roles.normalize_role({
        "roleCode": "admin",
        "name": "System Administrator",
        "status": "active",
        "permissions": [item["code"] for item in admin_roles.permission_catalog()],
        "menuModules": [item["key"] for item in admin_roles.ADMIN_MENU_MODULES],
    })


def credential_for_password(user_id: str, password: str, existing: dict | None) -> dict:
    now = utc_now()
    credential = existing or new_credential(user_id, hash_password(password))
    if existing is not None:
        credential["passwordHash"] = hash_password(password)
        credential["credentialVersion"] += 1
    credential["passwordChangedAt"] = iso_utc(now)
    credential["mustChangePassword"] = True
    credential["failedLoginCount"] = 0
    credential["lockedUntil"] = None
    credential["updatedAt"] = iso_utc(now)
    return credential


def main() -> int:
    args = parse_args()
    if not use_mysql() and (get_settings().storage_backend != "json" or not args.allow_json_development):
        print("Refusing non-JSON development storage; human credential bootstrap requires MySQL or --allow-json-development with JSON storage.", file=sys.stderr)
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
    existing_role = admin_roles.role_by_code("admin", include_deleted=True)
    role = administrator_role()
    if existing_role is not None:
        role.update({
            "id": existing_role["id"],
            "createdAt": existing_role["createdAt"],
            "properties": existing_role.get("properties") or {},
        })
    user["roles"] = admin_users.compact_list([*(user.get("roles") or []), "admin"])
    context = AuthContext(user="bootstrap", roles={"admin"}, projects={"*"}, areas={"*"})
    user = admin_users.append_user_audit_event(user, "bootstrap_password", context, changed_fields=["roles", "passwordHash", "credentialVersion", "sessions"])

    if use_mysql():
        with mysql_connect() as conn:
            try:
                with conn.cursor() as cur:
                    admin_roles.execute_upsert_role_mysql(cur, role)
                    admin_users.execute_upsert_user_mysql(cur, user)
                    write_mysql_credential(cur, credential_for_password(user["id"], password, mysql_credential_for_user(cur, user["id"], lock=True)))
                    cur.execute("UPDATE admin_sessions SET revoked_at = %s WHERE admin_user_id = %s AND revoked_at IS NULL", (iso_utc(utc_now()), user["id"]))
                    cur.execute("SELECT 1 FROM admin_user_roles aur JOIN admin_roles ar ON ar.id = aur.admin_role_id WHERE aur.admin_user_id = %s AND ar.role_code = %s", (user["id"], "admin"))
                    if cur.fetchone() is None:
                        raise RuntimeError("admin role association was not created")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    else:
        with json_transaction([admin_users_json_path(), admin_roles_json_path(), admin_credentials_json_path(), admin_sessions_json_path()]):
            roles = admin_roles.load_all_roles()
            for index, existing_role in enumerate(roles):
                if existing_role.get("roleCode") == "admin":
                    roles[index] = role
                    break
            else:
                roles.append(role)
            admin_roles.save_roles(roles)
            admin_users.save_user(user)
            credential = credential_for_password(user["id"], password, credential_for_user(user["id"]))
            save_credential(credential)
            from server.modules.auth_store import revoke_user_sessions
            revoke_user_sessions(user["id"])

    print(f"Bootstrap administrator initialized: {user['username']}")
    if generated:
        print(f"Temporary password: {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
