from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .admin_organizations import load_all_organizations, save_organization
from .admin_users import load_all_users, save_user


SOURCE_SYSTEM = "dingtalk-desktop-directory"
SOURCE_COMPANY = "福建武夷福森农林科技有限公司"
SOURCE_SNAPSHOT_DATE = "2026-08-19"

COMPANY = {
    "code": "WYFS",
    "name": SOURCE_COMPANY,
    "shortName": "武夷福森",
    "organizationType": "enterprise",
    "sortOrder": 10,
}

DIRECTORY_UNITS: tuple[dict[str, Any], ...] = (
    {
        "code": "WYFS-TECH",
        "name": "技术部",
        "sortOrder": 10,
        "members": (
            ("wyfs-dt-001", "吴婷", "职员"),
            ("wyfs-dt-002", "鲍明华", "经理"),
            ("wyfs-dt-003", "刘旭", "职员"),
        ),
    },
    {
        "code": "WYFS-MARKET",
        "name": "市场部",
        "sortOrder": 20,
        "members": (
            ("wyfs-dt-004", "陈超凡", "业务主办"),
            ("wyfs-dt-005", "刘丽娟", "职员"),
            ("wyfs-dt-006", "康良建", ""),
            ("wyfs-dt-007", "裴家彬", "业务主办"),
            ("wyfs-dt-008", "叶俊杰", "销售"),
        ),
    },
    {
        "code": "WYFS-GENERAL",
        "name": "综合部",
        "sortOrder": 30,
        "members": (
            ("wyfs-dt-009", "阮喜燕", "职员"),
            ("wyfs-dt-010", "陈巧江", "职员"),
            ("wyfs-dt-011", "葛清燕", "综合部"),
            ("wyfs-dt-012", "林芳", "职员"),
        ),
    },
    {"code": "WYFS-FINANCE", "name": "财务部", "sortOrder": 40, "members": ()},
    {
        "code": "WYFS-GENERAL-MANAGER",
        "name": "总经理",
        "sortOrder": 50,
        "nodeKind": "position-group",
        "members": (("wyfs-dt-013", "黄晓恒", "总经理"),),
    },
    {
        "code": "WYFS-CHAIRMAN",
        "name": "董事长",
        "sortOrder": 60,
        "nodeKind": "position-group",
        "members": (("wyfs-dt-014", "官君逸", "董事长"),),
    },
    {
        "code": "WYFS-OTHER",
        "name": "其他",
        "sortOrder": 70,
        "members": (
            ("wyfs-dt-015", "陈晖文", "其他"),
            ("wyfs-dt-016", "葛春祥", "董事长"),
        ),
    },
)


def stable_id(kind: str, key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"smart-bamboo:{SOURCE_SYSTEM}:{kind}:{key}"))


def source_properties(**values: Any) -> dict[str, Any]:
    return {
        "sourceSystem": SOURCE_SYSTEM,
        "sourceCompany": SOURCE_COMPANY,
        "sourceSnapshotDate": SOURCE_SNAPSHOT_DATE,
        **values,
    }

def import_wuyifusen_directory() -> dict[str, Any]:
    """Idempotently import the desktop DingTalk directory snapshot.

    Imported people are directory-only, disabled user profiles. No credentials,
    roles, or additional data scopes are created by this operation.
    """

    imported_at = datetime.now(timezone.utc).isoformat()
    existing_organizations = {
        str(record.get("organizationCode") or ""): record
        for record in load_all_organizations()
    }
    existing_users = {
        str(record.get("username") or "").lower(): record
        for record in load_all_users()
    }
    organization_ids: dict[str, str] = {}
    organization_created = 0
    organization_updated = 0
    user_created = 0
    user_updated = 0

    root_existing = existing_organizations.get(COMPANY["code"])
    if root_existing and (root_existing.get("properties") or {}).get("sourceSystem") not in {None, SOURCE_SYSTEM}:
        raise RuntimeError(f"Organization code {COMPANY['code']} belongs to another source")
    root_id = str(root_existing.get("id")) if root_existing else stable_id("organization", COMPANY["code"])
    root_record = {
        **(root_existing or {}),
        "id": root_id,
        "organizationCode": COMPANY["code"],
        "name": COMPANY["name"],
        "shortName": COMPANY["shortName"],
        "parentId": None,
        "organizationType": COMPANY["organizationType"],
        "status": "active",
        "sortOrder": COMPANY["sortOrder"],
        "leader": (root_existing or {}).get("leader"),
        "phone": (root_existing or {}).get("phone"),
        "address": (root_existing or {}).get("address"),
        "administrativeDivisionCode": (root_existing or {}).get("administrativeDivisionCode"),
        "dataScopes": dict((root_existing or {}).get("dataScopes") or {}),
        "properties": {
            **dict((root_existing or {}).get("properties") or {}),
            **source_properties(sourceMemberCount=sum(len(unit["members"]) for unit in DIRECTORY_UNITS)),
        },
        "createdAt": (root_existing or {}).get("createdAt") or imported_at,
        "updatedAt": imported_at,
        "deletedAt": None,
    }
    save_organization(root_record)
    organization_ids[COMPANY["code"]] = root_id
    organization_updated += int(root_existing is not None)
    organization_created += int(root_existing is None)

    for unit in DIRECTORY_UNITS:
        existing = existing_organizations.get(unit["code"])
        if existing and (existing.get("properties") or {}).get("sourceSystem") not in {None, SOURCE_SYSTEM}:
            raise RuntimeError(f"Organization code {unit['code']} belongs to another source")
        organization_id = str(existing.get("id")) if existing else stable_id("organization", unit["code"])
        organization = {
            **(existing or {}),
            "id": organization_id,
            "organizationCode": unit["code"],
            "name": unit["name"],
            "shortName": unit["name"],
            "parentId": root_id,
            "organizationType": "department",
            "status": "active",
            "sortOrder": unit["sortOrder"],
            "leader": (existing or {}).get("leader"),
            "phone": (existing or {}).get("phone"),
            "address": (existing or {}).get("address"),
            "administrativeDivisionCode": (existing or {}).get("administrativeDivisionCode"),
            "dataScopes": dict((existing or {}).get("dataScopes") or {}),
            "properties": {
                **dict((existing or {}).get("properties") or {}),
                **source_properties(
                    sourcePath=f"{SOURCE_COMPANY}/{unit['name']}",
                    sourceMemberCount=len(unit["members"]),
                    sourceNodeKind=unit.get("nodeKind", "department"),
                ),
            },
            "createdAt": (existing or {}).get("createdAt") or imported_at,
            "updatedAt": imported_at,
            "deletedAt": None,
        }
        save_organization(organization)
        organization_ids[unit["code"]] = organization_id
        organization_updated += int(existing is not None)
        organization_created += int(existing is None)

    for unit in DIRECTORY_UNITS:
        organization_id = organization_ids[unit["code"]]
        for username, display_name, job_title in unit["members"]:
            existing = existing_users.get(username)
            existing_source = (existing.get("properties") or {}).get("sourceSystem") if existing else None
            if existing and existing_source not in {None, SOURCE_SYSTEM}:
                raise RuntimeError(f"Username {username} belongs to another source")
            properties = {
                **dict((existing or {}).get("properties") or {}),
                **source_properties(
                    organizationId=organization_id,
                    organizationIds=[],
                    jobTitle=job_title,
                    directoryOnly=True,
                    credentialProvisioned=False,
                ),
            }
            user = {
                **(existing or {}),
                "id": str(existing.get("id")) if existing else stable_id("user", username),
                "username": username,
                "displayName": display_name,
                "status": (existing or {}).get("status") or "disabled",
                "roles": list((existing or {}).get("roles") or []),
                "dataScopes": dict((existing or {}).get("dataScopes") or {}),
                "properties": properties,
                "createdAt": (existing or {}).get("createdAt") or imported_at,
                "updatedAt": imported_at,
                "deletedAt": None,
            }
            save_user(user)
            user_updated += int(existing is not None)
            user_created += int(existing is None)

    return {
        "sourceSystem": SOURCE_SYSTEM,
        "sourceSnapshotDate": SOURCE_SNAPSHOT_DATE,
        "company": SOURCE_COMPANY,
        "organizationCreated": organization_created,
        "organizationUpdated": organization_updated,
        "userCreated": user_created,
        "userUpdated": user_updated,
        "organizationTotal": 1 + len(DIRECTORY_UNITS),
        "userTotal": sum(len(unit["members"]) for unit in DIRECTORY_UNITS),
        "credentialsCreated": 0,
    }
