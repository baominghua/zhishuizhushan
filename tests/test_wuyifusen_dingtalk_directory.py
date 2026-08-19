from __future__ import annotations

def test_wuyifusen_directory_import_is_complete_safe_and_idempotent(isolated_env):
    from server.modules.settings import get_settings
    from server.modules.admin_organizations import load_all_organizations
    from server.modules.admin_users import load_all_users
    from server.modules.wuyifusen_dingtalk_directory import import_wuyifusen_directory

    get_settings.cache_clear()
    first = import_wuyifusen_directory()
    second = import_wuyifusen_directory()

    organizations = load_all_organizations()
    users = load_all_users()
    root = next(item for item in organizations if item["organizationCode"] == "WYFS")
    children = [item for item in organizations if item.get("parentId") == root["id"]]

    assert first == {
        "sourceSystem": "dingtalk-desktop-directory",
        "sourceSnapshotDate": "2026-08-19",
        "company": "福建武夷福森农林科技有限公司",
        "organizationCreated": 8,
        "organizationUpdated": 0,
        "userCreated": 16,
        "userUpdated": 0,
        "organizationTotal": 8,
        "userTotal": 16,
        "credentialsCreated": 0,
    }
    assert second["organizationCreated"] == 0
    assert second["organizationUpdated"] == 8
    assert second["userCreated"] == 0
    assert second["userUpdated"] == 16
    assert {item["name"] for item in children} == {
        "技术部", "市场部", "综合部", "财务部", "总经理", "董事长", "其他",
    }
    assert len(users) == 16
    assert all(user["status"] == "disabled" for user in users)
    assert all(user["roles"] == [] for user in users)
    assert all(user["dataScopes"] == {} for user in users)
    assert all(user["properties"]["directoryOnly"] is True for user in users)
    assert all(user["properties"]["credentialProvisioned"] is False for user in users)
    assert next(item for item in children if item["name"] == "财务部")["properties"]["sourceMemberCount"] == 0
    assert root["properties"]["sourceMemberCount"] == 16
