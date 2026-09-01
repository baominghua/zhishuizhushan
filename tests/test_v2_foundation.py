from __future__ import annotations

import hashlib


ADMIN_HEADERS = {
    "X-RS-User": "v2-admin",
    "X-RS-Roles": "admin",
    "X-RS-Areas": "*",
}


def test_v2_leadership_cockpit_uses_live_ledgers_and_marks_unavailable_sources(app_client):
    response = app_client.get("/api/v2/cockpit/leadership", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "live"
    assert payload["overview"]["forestBlockCount"]["source"] == "林班台账"
    assert payload["carbon"]["projectCount"]["source"] == "碳汇项目"
    assert isinstance(payload["carbon"]["districtRanking"], list)
    assert isinstance(payload["availability"], dict)


def test_requirements_role_presets_include_eleven_organization_scoped_roles():
    from server.modules.admin_roles import role_permission_presets

    presets = {item["roleCode"]: item for item in role_permission_presets() if item["group"] == "需求书预置角色"}
    assert len(presets) == 11
    assert presets["super-admin"]["scopeMode"] == "all"
    assert presets["city-leader"]["organizationLevel"] == "city"
    assert presets["town-forestry-chief"]["organizationLevel"] == "town"
    assert presets["forest-ranger"]["dataScopes"]["blockCodes"] == []
    assert "cockpit.leadership.view" in presets["city-leader"]["permissions"]


def test_v2_capabilities_expose_versioned_modules(app_client):
    response = app_client.get("/api/v2/system/capabilities", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["apiVersion"] == "v2"
    assert payload["storagePolicy"] == "v1-compatible-adapter"
    assert [item["key"] for item in payload["modules"]] == [
        "workspace",
        "leadership-cockpit",
        "operations-todos",
        "operations-notifications",
        "operations-audit",
        "map",
        "forest-blocks",
            "forest-subcompartments",
            "forest-roads",
            "resourceSurveys",
        "attachments",
        "forest-rights",
        "imports",
        "patrol",
        "harvest",
        "labor",
        "equipment",
        "drone-missions",
        "imagery-assets",
        "ai-findings",
        "ai-models",
        "ai-inference",
        "safety-events",
        "mobile-operations",
        "carbon-estimates",
        "resource-intelligence",
        "cost-management",
        "workforce-development",
        "integration-hub",
        "system-governance",
        "system-overview",
        "organizations",
        "users",
        "roles",
        "dictionaries",
        "permissions",
        "basemap-settings",
    ]
    assert all(item["visible"] for item in payload["modules"])


def test_v2_carbon_estimates_reuse_business_storage_and_validate_blocks(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-CARBON-BLOCK-001",
            "name": "碳汇核算林班",
            "countyCode": "350783",
            "countyName": "建瓯市",
            "townCode": "350783105",
            "townName": "小桥镇",
            "areaMu": 120,
        },
    )
    assert block.status_code == 200

    payload = {
        "projectCode": "CCER-ZS-2026-001",
        "name": "小桥镇竹林碳汇一期",
        "accountingType": "project",
        "verificationStatus": "calculating",
        "projectBoundary": "V2-CARBON-BLOCK-001 全域",
        "methodology": "竹林经营碳汇项目方法学",
        "accountingStartDate": "2026-01-01",
        "accountingEndDate": "2026-12-31",
        "accountingAreaMu": 120,
        "carbonStock": 320.5,
        "annualSequestration": 48.2,
        "carbonPrice": 68,
        "estimatedRevenue": 3277.6,
        "beneficiary": "上屯村集体",
        "linkedBlockCodes": ["V2-CARBON-BLOCK-001"],
    }
    created = app_client.post("/api/v2/carbon/estimates", headers=ADMIN_HEADERS, json=payload)
    assert created.status_code == 200
    record = created.json()
    assert record["projectCode"] == "CCER-ZS-2026-001"
    assert record["linkedBlockCodes"] == ["V2-CARBON-BLOCK-001"]

    listed = app_client.get(
        "/api/v2/carbon/estimates?linkedBlockCode=V2-CARBON-BLOCK-001&verificationStatus=calculating",
        headers=ADMIN_HEADERS,
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["summary"]["annualSequestration"] == 48.2

    payload["verificationStatus"] = "verified"
    payload["verifiedAmount"] = 45.6
    updated = app_client.patch(
        f"/api/v2/carbon/estimates/{record['id']}",
        headers=ADMIN_HEADERS,
        json=payload,
    )
    assert updated.status_code == 200
    assert updated.json()["verificationStatus"] == "verified"
    assert updated.json()["verifiedAmount"] == 45.6

    deleted = app_client.delete(
        f"/api/v2/carbon/estimates/{record['id']}",
        headers=ADMIN_HEADERS,
    )
    assert deleted.status_code == 200
    after_delete = app_client.get("/api/v2/carbon/estimates", headers=ADMIN_HEADERS)
    assert after_delete.status_code == 200
    assert after_delete.json()["total"] == 0

    invalid = {**payload, "projectCode": "CCER-ZS-INVALID", "linkedBlockCodes": ["NOT-A-BLOCK"]}
    rejected = app_client.post("/api/v2/carbon/estimates", headers=ADMIN_HEADERS, json=invalid)
    assert rejected.status_code == 422
    assert "关联林班不存在" in rejected.json()["detail"]


def test_v2_operations_center_exposes_real_empty_ledgers_and_exports(app_client):
    for path in (
        "/api/v2/operations-center/todos",
        "/api/v2/operations-center/notifications",
        "/api/v2/operations-center/audit",
    ):
        response = app_client.get(path, headers=ADMIN_HEADERS)
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}

    exported = app_client.get("/api/v2/operations-center/audit.csv", headers=ADMIN_HEADERS)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")

    missing = app_client.post(
        "/api/v2/operations-center/notifications/not-real/read",
        headers=ADMIN_HEADERS,
    )
    assert missing.status_code == 404


def test_v2_operations_center_aggregates_patrol_and_tracks_notification_reads(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-OPS-CENTER-BLOCK-001",
            "name": "统一运营中心测试林班",
            "countyCode": "350783",
            "countyName": "建瓯市",
            "townCode": "350783105",
            "townName": "小桥镇",
            "villageCode": "350783105206",
            "villageName": "上屯村",
            "areaMu": 36,
        },
    )
    assert block.status_code == 200

    created = app_client.post(
        "/api/v2/patrol/tasks",
        headers=ADMIN_HEADERS,
        json={
            "name": "统一待办巡护任务",
            "priority": "high",
            "plannedStartAt": "2026-08-11T08:00:00+08:00",
            "plannedEndAt": "2026-08-11T12:00:00+08:00",
            "assigneeName": "v2-admin",
            "linkedBlockCodes": ["V2-OPS-CENTER-BLOCK-001"],
            "instructions": "验证统一待办、消息和审计闭环。",
        },
    )
    assert created.status_code == 200
    task = created.json()

    todos = app_client.get(
        "/api/v2/operations-center/todos?module=patrol",
        headers=ADMIN_HEADERS,
    )
    assert todos.status_code == 200
    assert todos.json()["total"] == 1
    assert todos.json()["items"][0]["recordId"] == task["id"]
    assert todos.json()["items"][0]["linkedBlockCodes"] == ["V2-OPS-CENTER-BLOCK-001"]

    audit = app_client.get(
        "/api/v2/operations-center/audit?module=patrol",
        headers=ADMIN_HEADERS,
    )
    assert audit.status_code == 200
    assert audit.json()["total"] >= 1
    notification_id = audit.json()["items"][0]["id"]

    unread = app_client.get(
        "/api/v2/operations-center/notifications?module=patrol&unreadOnly=true",
        headers=ADMIN_HEADERS,
    )
    assert unread.status_code == 200
    assert any(item["id"] == notification_id and item["read"] is False for item in unread.json()["items"])

    marked = app_client.post(
        f"/api/v2/operations-center/notifications/{notification_id}/read",
        headers=ADMIN_HEADERS,
    )
    assert marked.status_code == 200
    assert marked.json()["read"] is True

    unread_after = app_client.get(
        "/api/v2/operations-center/notifications?module=patrol&unreadOnly=true",
        headers=ADMIN_HEADERS,
    )
    assert unread_after.status_code == 200
    assert all(item["id"] != notification_id for item in unread_after.json()["items"])

    restored = app_client.delete(
        f"/api/v2/operations-center/notifications/{notification_id}/read",
        headers=ADMIN_HEADERS,
    )
    assert restored.status_code == 200
    assert restored.json()["read"] is False

    for export_path in ("todos.csv", "notifications.csv", "audit.csv"):
        exported = app_client.get(
            f"/api/v2/operations-center/{export_path}?module=patrol",
            headers=ADMIN_HEADERS,
        )
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("text/csv")
        assert task["patrolNo"] in exported.content.decode("utf-8-sig")


def test_v2_workspace_and_selector_use_live_forest_block_data(app_client):
    empty_summary = app_client.get(
        "/api/v2/workspace/summary",
        headers=ADMIN_HEADERS,
    )
    assert empty_summary.status_code == 200
    assert empty_summary.json()["source"] == "live"
    assert empty_summary.json()["metrics"]["forestBlocks"] == 0
    assert empty_summary.json()["todos"] == []

    created = app_client.post(
        "/api/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-BLOCK-001",
            "name": "上屯村 003 林班",
            "countyCode": "350783",
            "countyName": "建瓯市",
            "townCode": "350783105",
            "townName": "小桥镇",
            "villageCode": "350783105206",
            "villageName": "上屯村",
            "areaMu": 195,
            "forestType": "毛竹林",
        },
    )
    assert created.status_code == 200

    selector = app_client.get(
        "/api/v2/entities/forest-blocks?q=上屯&limit=10",
        headers=ADMIN_HEADERS,
    )
    assert selector.status_code == 200
    selector_payload = selector.json()
    assert selector_payload["total"] == 1
    assert selector_payload["items"][0] == {
        "id": created.json()["id"],
        "code": "V2-BLOCK-001",
        "name": "上屯村 003 林班",
        "location": "建瓯市 / 小桥镇 / 上屯村",
        "areaMu": 195.0,
        "hasGeometry": False,
        "riskLevel": None,
    }

    live_summary = app_client.get(
        "/api/v2/workspace/summary",
        headers=ADMIN_HEADERS,
    )
    assert live_summary.status_code == 200
    assert live_summary.json()["metrics"]["forestBlocks"] == 1


def test_v2_entity_selector_enforces_existing_permissions(app_client):
    response = app_client.get("/api/v2/entities/forest-blocks")

    assert response.status_code == 403
    assert "forest.blocks.view" in response.json()["detail"]


def test_v2_map_config_reports_server_side_tianditu_availability(
    app_client,
    monkeypatch,
):
    monkeypatch.setenv("REMOTE_SENSING_TIANDITU_TK", "a" * 32)

    response = app_client.get(
        "/api/v2/system/map-config",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {
        "provider": "tianditu",
        "available": True,
        "accessMode": "server-proxy",
        "imageryUrl": "/api/basemaps/tianditu/img_w/{z}/{x}/{y}.png",
        "labelsUrl": "/api/basemaps/tianditu/cia_w/{z}/{x}/{y}.png",
        "maximumLevel": 18,
        "message": "天地图服务已连接",
    }


def test_v2_map_config_accepts_a_central_tianditu_cache_proxy(
    app_client,
    monkeypatch,
):
    monkeypatch.delenv("REMOTE_SENSING_TIANDITU_TK", raising=False)
    monkeypatch.setenv(
        "REMOTE_SENSING_TIANDITU_PROXY_BASE_URL",
        "https://tiles.example.test",
    )

    response = app_client.get(
        "/api/v2/system/map-config",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["imageryUrl"] == "/api/basemaps/tianditu/img_w/{z}/{x}/{y}.png"
    assert response.json()["maximumLevel"] == 18


def test_v2_basemap_settings_are_persisted_and_never_return_the_full_key(
    app_client,
    isolated_env,
    monkeypatch,
):
    monkeypatch.delenv("REMOTE_SENSING_TIANDITU_TK", raising=False)
    monkeypatch.delenv("REMOTE_SENSING_TIANDITU_PROXY_BASE_URL", raising=False)
    server_key = "a" * 32
    web_key = "b" * 32
    android_key = "c" * 32
    ios_key = "d" * 32

    saved = app_client.put(
        "/api/v2/system/basemap-settings",
        headers=ADMIN_HEADERS,
        json={
            "serverKey": server_key,
            "webKey": web_key,
            "androidKey": android_key,
            "iosKey": ios_key,
            "webDirectEnabled": True,
            "proxyBaseUrl": "",
            "referer": "https://platform.example.test",
        },
    )

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["available"] is True
    assert payload["hasServerKey"] is True
    assert payload["serverKeyMasked"] == "********aaaa"
    assert payload["webKeyMasked"] == "********bbbb"
    assert payload["androidKeyMasked"] == "********cccc"
    assert payload["iosKeyMasked"] == "********dddd"
    assert payload["webDirectEnabled"] is True
    assert server_key not in saved.text
    assert web_key not in saved.text
    assert android_key not in saved.text
    assert ios_key not in saved.text
    assert payload["source"] == "stored"

    settings_file = isolated_env / "remote-sensing" / "system" / "basemap_settings.json"
    assert settings_file.exists()
    assert server_key in settings_file.read_text(encoding="utf-8")

    loaded = app_client.get("/api/v2/system/basemap-settings", headers=ADMIN_HEADERS)
    assert loaded.status_code == 200
    assert loaded.json()["serverKeyMasked"] == "********aaaa"
    assert server_key not in loaded.text
    assert android_key not in loaded.text
    assert ios_key not in loaded.text

    map_config = app_client.get("/api/v2/system/map-config", headers=ADMIN_HEADERS)
    assert map_config.status_code == 200
    assert map_config.json()["available"] is True
    assert map_config.json()["accessMode"] == "web-direct"
    assert f"tk={web_key}" in map_config.json()["imageryUrl"]
    assert android_key not in map_config.text
    assert ios_key not in map_config.text


def test_v2_basemap_settings_reject_invalid_keys(app_client):
    response = app_client.put(
        "/api/v2/system/basemap-settings",
        headers=ADMIN_HEADERS,
        json={"serverKey": "too-short", "proxyBaseUrl": "", "referer": ""},
    )

    assert response.status_code == 422
    assert "32" in response.json()["detail"]


def test_v2_resource_ledgers_keep_blocks_and_rights_independent(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-RESOURCE-001",
            "name": "资源中心一号林班",
            "countyCode": "350783",
            "countyName": "建瓯市",
            "townCode": "350783105",
            "townName": "小桥镇",
            "villageCode": "350783105206",
            "villageName": "上屯村",
            "areaMu": 48,
            "forestType": "毛竹林",
        },
    )
    assert block.status_code == 200

    right = app_client.post(
        "/api/v2/resources/forest-rights",
        headers=ADMIN_HEADERS,
        json={
            "archiveCode": "V2-RIGHT-001",
            "certificateNo": "闽(2025)建瓯市不动产权第0012622号",
            "holder": "谭立广",
            "rightType": "林地经营权/林木所有权",
            "areaMu": 48,
            "linkedBlockIds": [block.json()["id"]],
            "linkedBlockCodes": ["V2-RESOURCE-001"],
        },
    )
    assert right.status_code == 200

    blocks = app_client.get(
        "/api/v2/resources/forest-blocks?q=资源中心",
        headers=ADMIN_HEADERS,
    )
    rights = app_client.get(
        "/api/v2/resources/forest-rights?linkedBlockCode=V2-RESOURCE-001",
        headers=ADMIN_HEADERS,
    )
    assert blocks.status_code == 200
    assert rights.status_code == 200
    assert blocks.json()["items"][0]["blockCode"] == "V2-RESOURCE-001"
    assert "certificateNo" not in blocks.json()["items"][0]
    assert rights.json()["items"][0]["archiveCode"] == "V2-RIGHT-001"
    assert rights.json()["items"][0]["linkedBlockCodes"] == ["V2-RESOURCE-001"]

    exported_blocks = app_client.get(
        "/api/v2/resources/forest-blocks-export.csv?q=资源中心",
        headers=ADMIN_HEADERS,
    )
    assert exported_blocks.status_code == 200
    assert exported_blocks.headers["content-type"].startswith("text/csv")
    exported_text = exported_blocks.content.decode("utf-8-sig")
    assert "V2-RESOURCE-001" in exported_text
    assert "资源中心一号林班" in exported_text
    assert "不动产权" not in exported_text

    updated = app_client.patch(
        f"/api/v2/resources/forest-rights/{right.json()['id']}",
        headers=ADMIN_HEADERS,
        json={"archiveStatus": "active"},
    )
    assert updated.status_code == 200
    assert updated.json()["archiveStatus"] == "active"


def test_v2_resource_ledgers_enforce_existing_permissions(app_client):
    blocks = app_client.get("/api/v2/resources/forest-blocks")
    subcompartments = app_client.get("/api/v2/resources/forest-subcompartments")
    rights = app_client.get("/api/v2/resources/forest-rights")

    assert blocks.status_code == 403
    assert "forest.blocks.view" in blocks.json()["detail"]
    assert subcompartments.status_code == 403
    assert "forest.subcompartments.view" in subcompartments.json()["detail"]
    assert rights.status_code == 403
    assert "forest.rights.view" in rights.json()["detail"]
    assert app_client.get("/api/v2/resources/forest-blocks-export.csv").status_code == 403
    assert app_client.get("/api/v2/resources/forest-subcompartments-export.csv").status_code == 403


def test_v2_subcompartment_ledger_requires_a_formal_parent_and_tracks_versions(app_client):
    parent = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-SUB-PARENT-001",
            "name": "上屯村 003 林班",
            "countyCode": "350783",
            "countyName": "建瓯市",
            "townCode": "350783105",
            "townName": "小桥镇",
            "villageCode": "350783105206",
            "villageName": "上屯村",
            "areaMu": 195,
            "forestType": "毛竹林",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[118.0, 27.0], [118.3, 27.0], [118.3, 27.3], [118.0, 27.3], [118.0, 27.0]]],
            },
        },
    )
    assert parent.status_code == 200
    parent_record = parent.json()

    missing_parent = app_client.post(
        "/api/v2/resources/forest-subcompartments",
        headers=ADMIN_HEADERS,
        json={
            "subcompartmentCode": "V2-SUB-MISSING",
            "name": "无父级小班",
            "forestBlockId": "not-a-formal-block",
        },
    )
    assert missing_parent.status_code == 404

    created = app_client.post(
        "/api/v2/resources/forest-subcompartments",
        headers=ADMIN_HEADERS,
        json={
            "subcompartmentCode": "003-7-1",
            "name": "上屯村毛竹经营小班",
            "forestBlockId": parent_record["id"],
            "areaMu": 40,
            "landCategory": "竹林地",
            "forestCategory": "商品林",
            "origin": "人工",
            "ageGroup": "成林",
            "bambooSpecies": "毛竹",
            "qualityGrade": "I",
            "healthStatus": "良好",
            "riskLevel": "low",
            "managementStatus": "active",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[118.1, 27.1], [118.2, 27.1], [118.2, 27.2], [118.1, 27.1]]],
            },
        },
    )
    assert created.status_code == 200
    record = created.json()
    assert record["version"] == 1
    assert record["forestBlockId"] == parent_record["id"]
    assert record["forestBlockCode"] == "V2-SUB-PARENT-001"
    assert record["countyName"] == "建瓯市"
    assert record["townName"] == "小桥镇"
    assert record["villageName"] == "上屯村"
    assert record["geometry"]["type"] == "MultiPolygon"

    shrunk_parent = app_client.patch(
        f"/api/v2/resources/forest-blocks/{parent_record['id']}",
        headers=ADMIN_HEADERS,
        json={
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[118.0, 27.0], [118.05, 27.0], [118.05, 27.05], [118.0, 27.0]]],
            },
        },
    )
    assert shrunk_parent.status_code == 422
    assert "003-7-1" in shrunk_parent.json()["detail"]

    cleared_parent = app_client.patch(
        f"/api/v2/resources/forest-blocks/{parent_record['id']}",
        headers=ADMIN_HEADERS,
        json={"geometry": None},
    )
    assert cleared_parent.status_code == 422
    assert "不能清空林班边界" in cleared_parent.json()["detail"]

    outside_parent = app_client.post(
        "/api/v2/resources/forest-subcompartments",
        headers=ADMIN_HEADERS,
        json={
            "subcompartmentCode": "003-OUTSIDE",
            "name": "越界小班",
            "forestBlockId": parent_record["id"],
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[119.0, 28.0], [119.1, 28.0], [119.1, 28.1], [119.0, 28.0]]],
            },
        },
    )
    assert outside_parent.status_code == 422
    assert "完整落在所属林班边界内" in outside_parent.json()["detail"]

    duplicate = app_client.post(
        "/api/v2/resources/forest-subcompartments",
        headers=ADMIN_HEADERS,
        json={
            "subcompartmentCode": "003-7-1",
            "name": "重复编号",
            "forestBlockId": parent_record["id"],
        },
    )
    assert duplicate.status_code == 409

    ledger = app_client.get(
        f"/api/v2/resources/forest-subcompartments?forestBlockId={parent_record['id']}&q=毛竹",
        headers=ADMIN_HEADERS,
    )
    assert ledger.status_code == 200
    assert ledger.json()["total"] == 1
    assert ledger.json()["items"][0]["subcompartmentCode"] == "003-7-1"

    exported_subcompartments = app_client.get(
        f"/api/v2/resources/forest-subcompartments-export.csv?forestBlockId={parent_record['id']}&q=毛竹",
        headers=ADMIN_HEADERS,
    )
    assert exported_subcompartments.status_code == 200
    assert exported_subcompartments.headers["content-type"].startswith("text/csv")
    exported_text = exported_subcompartments.content.decode("utf-8-sig")
    assert "003-7-1" in exported_text
    assert "V2-SUB-PARENT-001" in exported_text

    selector = app_client.get(
        f"/api/v2/entities/forest-subcompartments?forestBlockId={parent_record['id']}",
        headers=ADMIN_HEADERS,
    )
    assert selector.status_code == 200
    assert selector.json()["kind"] == "forest-subcompartment"
    assert selector.json()["items"][0]["forestBlockCode"] == "V2-SUB-PARENT-001"

    updated = app_client.patch(
        f"/api/v2/resources/forest-subcompartments/{record['id']}",
        headers=ADMIN_HEADERS,
        json={"expectedVersion": 1, "managementStatus": "resting", "areaMu": 39.5},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["managementStatus"] == "resting"
    assert updated.json()["areaMu"] == 39.5

    versions = app_client.get(
        f"/api/v2/resources/forest-subcompartments/{record['id']}/versions",
        headers=ADMIN_HEADERS,
    )
    assert versions.status_code == 200
    assert versions.json()["total"] == 2
    assert [item["version"] for item in versions.json()["items"]] == [2, 1]
    create_version_id = versions.json()["items"][1]["id"]

    rolled_back = app_client.post(
        f"/api/v2/resources/forest-subcompartments/{record['id']}/rollback",
        headers=ADMIN_HEADERS,
        json={"versionId": create_version_id, "expectedVersion": 2},
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["record"]["version"] == 3
    assert rolled_back.json()["record"]["managementStatus"] == "active"
    assert rolled_back.json()["record"]["areaMu"] == 40
    assert rolled_back.json()["record"]["geometry"]["type"] == "MultiPolygon"

    stale_rollback = app_client.post(
        f"/api/v2/resources/forest-subcompartments/{record['id']}/rollback",
        headers=ADMIN_HEADERS,
        json={"versionId": create_version_id, "expectedVersion": 2},
    )
    assert stale_rollback.status_code == 409

    stale = app_client.patch(
        f"/api/v2/resources/forest-subcompartments/{record['id']}",
        headers=ADMIN_HEADERS,
        json={"expectedVersion": 1, "riskLevel": "high"},
    )
    assert stale.status_code == 409

    deleted = app_client.delete(
        f"/api/v2/resources/forest-subcompartments/{record['id']}",
        headers=ADMIN_HEADERS,
    )
    assert deleted.status_code == 200
    assert deleted.json()["version"] == 4
    assert app_client.get(
        "/api/v2/resources/forest-subcompartments",
        headers=ADMIN_HEADERS,
    ).json()["total"] == 0
    recycled = app_client.get(
        "/api/v2/resources/forest-subcompartments?includeDeleted=true",
        headers=ADMIN_HEADERS,
    )
    assert recycled.status_code == 200
    assert recycled.json()["items"][0]["deletedAt"]


def test_v2_resource_surveys_track_versions_compare_periods_and_lock_archives(app_client):
    parent = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={"blockCode": "SURVEY-BLOCK-001", "name": "调查林班", "areaMu": 120},
    )
    assert parent.status_code == 200
    subcompartment = app_client.post(
        "/api/v2/resources/forest-subcompartments",
        headers=ADMIN_HEADERS,
        json={
            "subcompartmentCode": "SURVEY-SUB-001",
            "name": "调查小班",
            "forestBlockId": parent.json()["id"],
            "areaMu": 40,
            "bambooSpecies": "毛竹",
        },
    )
    assert subcompartment.status_code == 200

    first_survey = app_client.post(
        "/api/v2/resources/resource-surveys",
        headers=ADMIN_HEADERS,
        json={
            "surveyNo": "RS-2025-001",
            "name": "2025 年资源调查",
            "surveyType": "annual",
            "surveyDate": "2025-08-01",
            "status": "in_progress",
        },
    )
    assert first_survey.status_code == 200
    first_snapshot = app_client.post(
        f"/api/v2/resources/resource-surveys/{first_survey.json()['id']}/snapshots",
        headers=ADMIN_HEADERS,
        json={
            "forestSubcompartmentId": subcompartment.json()["id"],
            "bambooDensityPerMu": 180,
            "avgDbhCm": 8.2,
            "qualityGrade": "II",
        },
    )
    assert first_snapshot.status_code == 200
    assert first_snapshot.json()["areaMu"] == 40
    assert first_snapshot.json()["previousSnapshotId"] is None

    updated = app_client.patch(
        f"/api/v2/resources/resource-snapshots/{first_snapshot.json()['id']}",
        headers=ADMIN_HEADERS,
        json={"expectedVersion": 1, "bambooDensityPerMu": 190},
    )
    assert updated.status_code == 200
    versions = app_client.get(
        f"/api/v2/resources/resource-snapshots/{first_snapshot.json()['id']}/versions",
        headers=ADMIN_HEADERS,
    )
    assert versions.status_code == 200
    assert [item["changeType"] for item in versions.json()["items"]] == ["update", "create"]
    assert [item["version"] for item in versions.json()["items"]] == [2, 1]

    second_survey = app_client.post(
        "/api/v2/resources/resource-surveys",
        headers=ADMIN_HEADERS,
        json={
            "surveyNo": "RS-2026-001",
            "name": "2026 年资源调查",
            "surveyType": "annual",
            "surveyDate": "2026-08-01",
            "status": "in_progress",
        },
    )
    assert second_survey.status_code == 200
    second_snapshot = app_client.post(
        f"/api/v2/resources/resource-surveys/{second_survey.json()['id']}/snapshots",
        headers=ADMIN_HEADERS,
        json={
            "forestSubcompartmentId": subcompartment.json()["id"],
            "bambooDensityPerMu": 205,
            "avgDbhCm": 8.6,
            "qualityGrade": "I",
        },
    )
    assert second_snapshot.status_code == 200
    assert second_snapshot.json()["previousSnapshotId"] == first_snapshot.json()["id"]
    comparison = app_client.get(
        f"/api/v2/resources/resource-snapshots/{second_snapshot.json()['id']}/comparison",
        headers=ADMIN_HEADERS,
    )
    assert comparison.status_code == 200
    changes = {item["field"]: item for item in comparison.json()["changes"]}
    assert changes["bambooDensityPerMu"]["delta"] == 15
    assert changes["qualityGrade"]["before"] == "II"
    assert changes["qualityGrade"]["after"] == "I"

    denied_completion = app_client.patch(
        f"/api/v2/resources/resource-surveys/{second_survey.json()['id']}",
        headers={
            "X-RS-User": "survey-editor",
            "X-RS-Roles": "forest.surveys.view,forest.surveys.update",
            "X-RS-Areas": "*",
        },
        json={"expectedVersion": 1, "status": "completed"},
    )
    assert denied_completion.status_code == 403

    completed = app_client.patch(
        f"/api/v2/resources/resource-surveys/{second_survey.json()['id']}",
        headers=ADMIN_HEADERS,
        json={"expectedVersion": 1, "status": "completed"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completedAt"]
    locked_snapshot = app_client.patch(
        f"/api/v2/resources/resource-snapshots/{second_snapshot.json()['id']}",
        headers=ADMIN_HEADERS,
        json={"expectedVersion": 1, "avgDbhCm": 9.0},
    )
    assert locked_snapshot.status_code == 409
    reopened = app_client.patch(
        f"/api/v2/resources/resource-surveys/{second_survey.json()['id']}",
        headers=ADMIN_HEADERS,
        json={"expectedVersion": 2, "status": "in_progress"},
    )
    assert reopened.status_code == 409


def test_v2_attachment_center_links_controlled_evidence_and_protects_deletion(app_client):
    content = "上屯村资源调查现场照片说明".encode("utf-8")
    uploaded = app_client.post(
        "/api/v2/attachments",
        headers=ADMIN_HEADERS,
        files={"file": ("调查证据.txt", content, "text/plain")},
        data={"category": "survey_evidence", "description": "2026 年现场调查证据"},
    )
    assert uploaded.status_code == 200
    attachment = uploaded.json()
    assert attachment["originalName"] == "调查证据.txt"
    assert attachment["sizeBytes"] == len(content)
    assert attachment["linkCount"] == 0
    assert attachment["downloadUrl"].endswith("/download")

    parent = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={"blockCode": "ATTACH-BLOCK-001", "name": "附件测试林班", "areaMu": 20},
    )
    assert parent.status_code == 200
    subcompartment = app_client.post(
        "/api/v2/resources/forest-subcompartments",
        headers=ADMIN_HEADERS,
        json={
            "subcompartmentCode": "ATTACH-SUB-001",
            "name": "附件测试小班",
            "forestBlockId": parent.json()["id"],
            "areaMu": 12,
            "bambooSpecies": "毛竹",
        },
    )
    assert subcompartment.status_code == 200
    survey = app_client.post(
        "/api/v2/resources/resource-surveys",
        headers=ADMIN_HEADERS,
        json={
            "surveyNo": "ATTACH-SURVEY-001",
            "name": "附件关联资源调查",
            "surveyType": "annual",
            "surveyDate": "2026-08-10",
            "status": "in_progress",
        },
    )
    assert survey.status_code == 200
    snapshot = app_client.post(
        f"/api/v2/resources/resource-surveys/{survey.json()['id']}/snapshots",
        headers=ADMIN_HEADERS,
        json={
            "forestSubcompartmentId": subcompartment.json()["id"],
            "bambooDensityPerMu": 180,
            "attachmentIds": [attachment["id"]],
        },
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["attachmentIds"] == [attachment["id"]]
    assert snapshot.json()["attachments"][0]["originalName"] == "调查证据.txt"

    linked_delete = app_client.delete(
        f"/api/v2/attachments/{attachment['id']}",
        headers=ADMIN_HEADERS,
    )
    assert linked_delete.status_code == 409

    detached = app_client.patch(
        f"/api/v2/resources/resource-snapshots/{snapshot.json()['id']}",
        headers=ADMIN_HEADERS,
        json={"expectedVersion": snapshot.json()["version"], "attachmentIds": []},
    )
    assert detached.status_code == 200
    assert detached.json()["attachments"] == []

    downloaded = app_client.get(
        f"/api/v2/attachments/{attachment['id']}/download",
        headers=ADMIN_HEADERS,
    )
    assert downloaded.status_code == 200
    assert downloaded.content == content

    deleted = app_client.delete(
        f"/api/v2/attachments/{attachment['id']}",
        headers=ADMIN_HEADERS,
    )
    assert deleted.status_code == 200
    recycled = app_client.get(
        "/api/v2/attachments?includeDeleted=true",
        headers=ADMIN_HEADERS,
    )
    assert recycled.status_code == 200
    assert recycled.json()["items"][0]["status"] == "deleted"
    restored = app_client.post(
        f"/api/v2/attachments/{attachment['id']}/restore",
        headers=ADMIN_HEADERS,
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"

    events = app_client.get(
        f"/api/v2/attachments/{attachment['id']}/events",
        headers=ADMIN_HEADERS,
    )
    assert events.status_code == 200
    assert {item["action"] for item in events.json()["items"]} >= {
        "upload", "link", "unlink", "delete", "restore",
    }
    exported = app_client.get("/api/v2/attachments/export.csv", headers=ADMIN_HEADERS)
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    assert "调查证据.txt" in exported.content.decode("utf-8-sig")


def test_v2_attachment_center_enforces_permissions(app_client):
    response = app_client.get("/api/v2/attachments")

    assert response.status_code == 403
    assert "files.attachments.view" in response.json()["detail"]


def test_v2_import_job_requires_one_confirmation_then_commits_idempotently(app_client):
    content = (
        "林班编号,林班名称,区县编码,区县,乡镇编码,乡镇,村编码,村,面积(亩)\n"
        "V2-IMPORT-001,康村一号林班,350783,建瓯市,350783105,小桥镇,350783105206,上屯村,48\n"
        "V2-IMPORT-BLOCKED,,350783,建瓯市,350783105,小桥镇,350783105206,上屯村,12\n"
    ).encode("utf-8-sig")
    staged = app_client.post(
        "/api/v2/imports/jobs",
        headers=ADMIN_HEADERS,
        files={"file": ("康村林班.csv", content, "text/csv")},
        data={"strategy": "upsert"},
    )
    assert staged.status_code == 200
    job = staged.json()
    assert job["status"] == "needs_confirmation"
    assert job["totalRows"] == 2
    assert job["validRows"] == 1
    assert job["invalidRows"] == 1
    assert job["blockingIssues"] == 1
    assert job["warningIssues"] >= 1
    assert job["qualityStatus"] == "blocked"
    issue_codes = {issue["code"] for issue in job["issues"]}
    assert "geometry.missing" in issue_codes
    assert "required.name" in issue_codes
    assert job["sha256"]
    assert "rawFile" not in job
    assert "acceptedRows" not in job

    issues_csv = app_client.get(
        f"/api/v2/imports/jobs/{job['id']}/issues.csv",
        headers=ADMIN_HEADERS,
    )
    assert issues_csv.status_code == 200
    assert "required.name" in issues_csv.text
    assert "geometry.missing" in issues_csv.text

    blocked_commit = app_client.post(
        f"/api/v2/imports/jobs/{job['id']}/commit",
        headers=ADMIN_HEADERS,
    )
    assert blocked_commit.status_code == 409

    confirmed = app_client.post(
        f"/api/v2/imports/jobs/{job['id']}/confirm",
        headers=ADMIN_HEADERS,
        json={"skipInvalidRows": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "ready_to_commit"

    committed = app_client.post(
        f"/api/v2/imports/jobs/{job['id']}/commit",
        headers=ADMIN_HEADERS,
    )
    assert committed.status_code == 200
    assert committed.json()["status"] == "completed"
    assert committed.json()["commitSummary"]["importedBlocks"] == 1

    repeated = app_client.post(
        f"/api/v2/imports/jobs/{job['id']}/commit",
        headers=ADMIN_HEADERS,
    )
    assert repeated.status_code == 200
    assert repeated.json()["batchId"] == committed.json()["batchId"]

    ledger = app_client.get(
        "/api/v2/resources/forest-blocks?q=V2-IMPORT-001",
        headers=ADMIN_HEADERS,
    )
    assert ledger.status_code == 200
    assert ledger.json()["total"] == 1

    jobs = app_client.get("/api/v2/imports/jobs", headers=ADMIN_HEADERS)
    assert jobs.status_code == 200
    assert jobs.json()["items"][0]["id"] == job["id"]


def test_v2_import_quality_rules_block_duplicate_codes_and_invalid_geometry(app_client):
    content = b'''{"type":"FeatureCollection","features":[
      {"type":"Feature","properties":{"blockCode":"V2-DUPLICATE-001","name":"Duplicate A","countyCode":"350783","townCode":"350783105","villageCode":"350783105206","areaMu":48},"geometry":{"type":"Polygon","coordinates":[[[218,27],[219,27],[219,28],[218,28],[218,27]]]}},
      {"type":"Feature","properties":{"blockCode":"V2-DUPLICATE-001","name":"Duplicate B","countyCode":"350783","townCode":"350783105","villageCode":"350783105206","areaMu":-1},"geometry":{"type":"Polygon","coordinates":[[[218,27],[219,27],[219,28],[218,28],[218,27]]]}}
    ]}'''
    response = app_client.post(
        "/api/v2/imports/jobs",
        headers=ADMIN_HEADERS,
        files={"file": ("duplicate-blocks.geojson", content, "application/geo+json")},
        data={"strategy": "upsert"},
    )

    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "needs_confirmation"
    assert job["validRows"] == 0
    assert job["invalidRows"] == 2
    assert job["qualityStatus"] == "blocked"
    issue_codes = {issue["code"] for issue in job["issues"]}
    assert "identity.duplicate_in_file" in issue_codes
    assert "geometry.coordinate_range" in issue_codes
    assert "attribute.area_invalid" in issue_codes


def test_v2_import_jobs_enforce_existing_permissions(app_client):
    response = app_client.get("/api/v2/imports/jobs")
    assert response.status_code == 403
    assert "imports.forestBlocks.view" in response.json()["detail"]


def test_v2_patrol_task_runs_the_formal_state_machine(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-PATROL-BLOCK-001",
            "name": "上屯村巡护林班",
            "countyCode": "350783",
            "countyName": "建瓯市",
            "townCode": "350783105",
            "townName": "小桥镇",
            "villageCode": "350783105206",
            "villageName": "上屯村",
            "areaMu": 48,
        },
    )
    assert block.status_code == 200

    created = app_client.post(
        "/api/v2/patrol/tasks",
        headers=ADMIN_HEADERS,
        json={
            "name": "上屯村毛竹林日常巡护",
            "priority": "high",
            "plannedStartAt": "2026-08-06T08:00:00",
            "plannedEndAt": "2026-08-06T12:00:00",
            "assigneeName": "林业巡护一组",
            "linkedBlockCodes": ["V2-PATROL-BLOCK-001"],
            "instructions": "检查火险、盗伐和病虫害迹象。",
        },
    )
    assert created.status_code == 200
    task = created.json()
    assert task["status"] == "assigned"
    assert task["patrolNo"].startswith("XH-")
    assert task["linkedBlockCodes"] == ["V2-PATROL-BLOCK-001"]

    task_id = task["id"]
    edited = app_client.patch(
        f"/api/v2/patrol/tasks/{task_id}",
        headers=ADMIN_HEADERS,
        json={"name": "上屯村重点毛竹林巡护", "priority": "urgent"},
    )
    assert edited.status_code == 200
    assert edited.json()["name"] == "上屯村重点毛竹林巡护"
    assert edited.json()["priority"] == "urgent"

    attachment = app_client.post(
        "/api/v2/attachments",
        headers=ADMIN_HEADERS,
        data={"category": "patrol_evidence", "description": "巡护现场照片"},
        files={"file": ("巡护现场.txt", b"patrol evidence", "text/plain")},
    )
    assert attachment.status_code == 200
    attachment_id = attachment.json()["id"]

    for action, expected in (
        ("accept", "accepted"),
        ("start", "patrolling"),
    ):
        response = app_client.post(
            f"/api/v2/patrol/tasks/{task_id}/actions/{action}",
            headers=ADMIN_HEADERS,
            json={},
        )
        assert response.status_code == 200
        assert response.json()["status"] == expected

    reported = app_client.post(
        f"/api/v2/patrol/tasks/{task_id}/actions/report",
        headers=ADMIN_HEADERS,
        json={
            "summary": "完成巡护，发现一处轻微竹蝗迹象。",
            "issueType": "pest",
            "issueLevel": "low",
            "locationText": "林班东侧作业道附近",
            "attachmentIds": [attachment_id],
        },
    )
    assert reported.status_code == 200
    assert reported.json()["status"] == "reported"
    assert reported.json()["report"]["issueType"] == "pest"
    assert reported.json()["attachmentIds"] == [attachment_id]

    invalid_close = app_client.post(
        f"/api/v2/patrol/tasks/{task_id}/actions/close",
        headers=ADMIN_HEADERS,
        json={},
    )
    assert invalid_close.status_code == 409

    invalid_verify = app_client.post(
        f"/api/v2/patrol/tasks/{task_id}/actions/verify",
        headers=ADMIN_HEADERS,
        json={"note": "现场证据完整，同意通过。"},
    )
    assert invalid_verify.status_code == 409

    resolved = app_client.post(
        f"/api/v2/patrol/tasks/{task_id}/actions/resolve",
        headers=ADMIN_HEADERS,
        json={
            "dispositionSummary": "完成竹蝗风险点处置。",
            "dispositionResult": "风险已消除，纳入后续复查。",
            "attachmentIds": [attachment_id],
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["disposition"]["result"] == "风险已消除，纳入后续复查。"

    verified = app_client.post(
        f"/api/v2/patrol/tasks/{task_id}/actions/verify",
        headers=ADMIN_HEADERS,
        json={"note": "现场证据完整，同意通过。"},
    )
    assert verified.status_code == 200
    closed = app_client.post(
        f"/api/v2/patrol/tasks/{task_id}/actions/close",
        headers=ADMIN_HEADERS,
        json={},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert len(closed.json()["timeline"]) == 8

    ledger = app_client.get(
        "/api/v2/patrol/tasks?linkedBlockCode=V2-PATROL-BLOCK-001",
        headers=ADMIN_HEADERS,
    )
    assert ledger.status_code == 200
    assert ledger.json()["total"] == 1
    assert ledger.json()["items"][0]["status"] == "closed"

    exported = app_client.get("/api/v2/patrol/tasks-export.csv", headers=ADMIN_HEADERS)
    assert exported.status_code == 200
    assert "上屯村重点毛竹林巡护" in exported.content.decode("utf-8-sig")


def test_v2_patrol_supports_soft_delete_and_restore_before_acceptance(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={"blockCode": "V2-PATROL-BLOCK-DELETE", "name": "可撤销巡护林班", "areaMu": 12},
    )
    assert block.status_code == 200
    created = app_client.post(
        "/api/v2/patrol/tasks",
        headers=ADMIN_HEADERS,
        json={
            "name": "待派发巡护计划",
            "priority": "normal",
            "plannedStartAt": "2026-08-07T08:00:00",
            "plannedEndAt": "2026-08-07T12:00:00",
            "assigneeName": "",
            "linkedBlockCodes": ["V2-PATROL-BLOCK-DELETE"],
            "instructions": "待确认后派发。",
        },
    )
    task_id = created.json()["id"]
    deleted = app_client.delete(f"/api/v2/patrol/tasks/{task_id}", headers=ADMIN_HEADERS)
    assert deleted.status_code == 200
    recycle_bin = app_client.get("/api/v2/patrol/tasks?includeDeleted=true", headers=ADMIN_HEADERS)
    assert any(item["id"] == task_id and item["deletedAt"] for item in recycle_bin.json()["items"])
    restored = app_client.post(f"/api/v2/patrol/tasks/{task_id}/restore", headers=ADMIN_HEADERS)
    assert restored.status_code == 200
    assert restored.json()["deletedAt"] is None


def test_v2_patrol_requires_existing_business_permissions(app_client):
    response = app_client.get("/api/v2/patrol/tasks")
    assert response.status_code == 403
    assert "business.maintenanceTasks.view" in response.json()["detail"]


def create_harvest_foundation(app_client, suffix: str = "001", quota_area: float = 60):
    block_code = f"V2-HARVEST-BLOCK-{suffix}"
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": block_code,
            "name": f"上屯村采伐林班 {suffix}",
            "countyCode": "350783",
            "countyName": "建瓯市",
            "townCode": "350783105",
            "townName": "小桥镇",
            "villageCode": "350783105206",
            "villageName": "上屯村",
            "areaMu": 48,
            "forestType": "毛竹林",
        },
    )
    assert block.status_code == 200
    right = app_client.post(
        "/api/v2/resources/forest-rights",
        headers=ADMIN_HEADERS,
        json={
            "archiveCode": f"V2-HARVEST-RIGHT-{suffix}",
            "certificateNo": f"闽(2026)建瓯市不动产权第{suffix}号",
            "holder": f"采伐权利人 {suffix}",
            "archiveStatus": "active",
            "areaMu": 48,
            "countyCode": "350783",
            "townCode": "350783105",
            "villageCode": "350783105206",
            "linkedBlockIds": [block.json()["id"]],
            "linkedBlockCodes": [block_code],
        },
    )
    assert right.status_code == 200
    farmer = app_client.post(
        "/api/business/farmers",
        headers=ADMIN_HEADERS,
        json={
            "recordCode": f"FARMER-HARVEST-{suffix}",
            "name": f"上屯村竹农 {suffix}",
            "status": "active",
            "linkedBlockCodes": [block_code],
            "properties": {},
        },
    )
    assert farmer.status_code == 200
    quota = app_client.post(
        "/api/v2/harvest/quotas",
        headers=ADMIN_HEADERS,
        json={
            "quotaYear": 2026,
            "authorityName": "建瓯市林业主管部门",
            "forestType": "毛竹林",
            "blockCode": block_code,
            "quotaAreaMu": quota_area,
            "quotaQuantityTon": 100,
            "notes": "年度毛竹采伐限额",
        },
    )
    assert quota.status_code == 200
    return block.json(), right.json(), farmer.json(), quota.json()


def test_v2_harvest_runs_application_quota_operation_and_verification_closure(app_client):
    block, right, farmer, quota = create_harvest_foundation(app_client)
    created = app_client.post(
        "/api/v2/harvest/applications",
        headers=ADMIN_HEADERS,
        json={
            "name": "上屯村毛竹择伐申请",
            "applicantType": "farmer",
            "applicantId": farmer["id"],
            "harvestType": "timber",
            "requestedAreaMu": 30,
            "requestedQuantityTon": 45,
            "quotaId": quota["id"],
            "workStartAt": "2026-09-01T08:00:00",
            "workEndAt": "2026-09-10T18:00:00",
            "purpose": "成熟毛竹择伐更新",
            "linkedBlockCodes": [block["blockCode"]],
            "linkedRightIds": [right["id"]],
        },
    )
    assert created.status_code == 200
    application = created.json()
    assert application["status"] == "draft"
    assert application["blocks"][0]["code"] == block["blockCode"]
    assert application["rights"][0]["archiveCode"] == right["archiveCode"]

    edited = app_client.patch(
        f"/api/v2/harvest/applications/{application['id']}",
        headers=ADMIN_HEADERS,
        json={"name": "上屯村毛竹择伐申请（已核对）", "purpose": "成熟毛竹择伐更新及林分优化"},
    )
    assert edited.status_code == 200
    application = edited.json()
    assert application["name"].endswith("（已核对）")
    assert application["timeline"][-1]["action"] == "edit"

    exported = app_client.get(
        "/api/v2/harvest/applications-export.csv?q=已核对",
        headers=ADMIN_HEADERS,
    )
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    assert "上屯村毛竹择伐申请（已核对）" in exported.content.decode("utf-8-sig")

    submitted = app_client.post(
        f"/api/v2/harvest/applications/{application['id']}/actions/submit",
        headers=ADMIN_HEADERS,
        json={},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "approving"
    assert submitted.json()["quotaCheck"]["passed"] is True
    assert [item["toStatus"] for item in submitted.json()["timeline"]][-2:] == ["submitted", "approving"]

    approved = app_client.post(
        f"/api/v2/harvest/applications/{application['id']}/actions/approve",
        headers=ADMIN_HEADERS,
        json={"note": "权属和限额核验通过。"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    started = app_client.post(
        f"/api/v2/harvest/applications/{application['id']}/actions/start",
        headers=ADMIN_HEADERS,
        json={},
    )
    assert started.status_code == 200
    assert started.json()["operation"]["geofence"]["blockCodes"] == [block["blockCode"]]

    alerted = app_client.post(
        f"/api/v2/harvest/applications/{application['id']}/actions/record-alert",
        headers=ADMIN_HEADERS,
        json={
            "alertType": "outside-geofence",
            "alertLevel": "high",
            "alertMessage": "作业设备短时越出批准林班边界。",
            "locationText": "林班东侧界桩附近",
            "deviceCode": "UAV-001",
        },
    )
    assert alerted.status_code == 200
    assert alerted.json()["status"] == "operating"
    assert alerted.json()["operation"]["alerts"][0]["type"] == "outside-geofence"
    safety_alerts = app_client.get(
        "/api/v2/safety/alerts?status=new",
        headers=ADMIN_HEADERS,
    )
    assert safety_alerts.status_code == 200
    linked_alert = next(
        item
        for item in safety_alerts.json()["items"]
        if item["id"] == alerted.json()["operation"]["alerts"][0]["safetyAlertId"]
    )
    assert linked_alert["sourceType"] == "harvest"
    assert linked_alert["sourceRef"] == application["id"]
    assert linked_alert["linkedBlockCodes"] == [block["blockCode"]]

    attachment = app_client.post(
        "/api/v2/attachments",
        headers=ADMIN_HEADERS,
        data={"category": "harvest_evidence", "description": "采伐作业现场凭证"},
        files={"file": ("采伐现场记录.txt", b"harvest evidence", "text/plain")},
    )
    assert attachment.status_code == 200
    attachment_id = attachment.json()["id"]

    reported = app_client.post(
        f"/api/v2/harvest/applications/{application['id']}/actions/report-complete",
        headers=ADMIN_HEADERS,
        json={"actualAreaMu": 28.5, "actualQuantityTon": 42, "note": "现场作业完成，界线内无超采。", "attachmentIds": [attachment_id]},
    )
    assert reported.status_code == 200
    assert reported.json()["status"] == "verifying"
    assert reported.json()["attachmentIds"] == [attachment_id]
    assert reported.json()["attachments"][0]["originalName"] == "采伐现场记录.txt"

    verified = app_client.post(
        f"/api/v2/harvest/applications/{application['id']}/actions/verify",
        headers=ADMIN_HEADERS,
        json={"note": "现场验收合格。"},
    )
    assert verified.status_code == 200
    completed = verified.json()
    assert completed["status"] == "completed"
    assert completed["batch"]["batchNo"].startswith("PC-")
    assert completed["batch"]["traceCode"].startswith("ZS-PC-")
    assert len(completed["batch"]["resourceVersionIds"]) == 1

    quotas = app_client.get("/api/v2/harvest/quotas?year=2026", headers=ADMIN_HEADERS)
    assert quotas.status_code == 200
    stored_quota = next(item for item in quotas.json()["items"] if item["id"] == quota["id"])
    assert stored_quota["usedAreaMu"] == 30
    assert stored_quota["usedQuantityTon"] == 45


def test_v2_harvest_draft_supports_soft_delete_recycle_and_restore(app_client):
    block, right, farmer, quota = create_harvest_foundation(app_client, "003")
    created = app_client.post(
        "/api/v2/harvest/applications",
        headers=ADMIN_HEADERS,
        json={
            "name": "待调整采伐草稿",
            "applicantType": "farmer",
            "applicantId": farmer["id"],
            "harvestType": "tending",
            "requestedAreaMu": 8,
            "requestedQuantityTon": 5,
            "quotaId": quota["id"],
            "workStartAt": "2026-11-01T08:00:00",
            "workEndAt": "2026-11-02T18:00:00",
            "purpose": "抚育采收",
            "linkedBlockCodes": [block["blockCode"]],
            "linkedRightIds": [right["id"]],
        },
    )
    assert created.status_code == 200
    application_id = created.json()["id"]

    deleted = app_client.delete(
        f"/api/v2/harvest/applications/{application_id}",
        headers=ADMIN_HEADERS,
    )
    assert deleted.status_code == 200
    assert deleted.json()["deletedAt"]
    assert app_client.get(
        "/api/v2/harvest/applications?q=待调整",
        headers=ADMIN_HEADERS,
    ).json()["total"] == 0

    recycled = app_client.get(
        "/api/v2/harvest/applications?q=待调整&includeDeleted=true",
        headers=ADMIN_HEADERS,
    )
    assert recycled.status_code == 200
    assert recycled.json()["total"] == 1
    assert recycled.json()["items"][0]["deletedAt"]

    restored = app_client.post(
        f"/api/v2/harvest/applications/{application_id}/restore",
        headers=ADMIN_HEADERS,
    )
    assert restored.status_code == 200
    assert restored.json()["deletedAt"] is None
    assert restored.json()["timeline"][-1]["action"] == "restore"


def test_v2_harvest_blocks_approval_when_quota_is_insufficient(app_client):
    block, right, farmer, quota = create_harvest_foundation(app_client, "002", quota_area=10)
    created = app_client.post(
        "/api/v2/harvest/applications",
        headers=ADMIN_HEADERS,
        json={
            "name": "超限额申请",
            "applicantType": "farmer",
            "applicantId": farmer["id"],
            "harvestType": "timber",
            "requestedAreaMu": 20,
            "requestedQuantityTon": 20,
            "quotaId": quota["id"],
            "workStartAt": "2026-10-01T08:00:00",
            "workEndAt": "2026-10-05T18:00:00",
            "linkedBlockCodes": [block["blockCode"]],
            "linkedRightIds": [right["id"]],
        },
    )
    assert created.status_code == 200
    checked = app_client.post(
        f"/api/v2/harvest/applications/{created.json()['id']}/actions/submit",
        headers=ADMIN_HEADERS,
        json={},
    )
    assert checked.status_code == 200
    assert checked.json()["status"] == "quota_check"
    assert checked.json()["quotaCheck"]["passed"] is False
    assert "剩余采伐面积配额不足" in checked.json()["quotaCheck"]["reasons"]
    approve = app_client.post(
        f"/api/v2/harvest/applications/{created.json()['id']}/actions/approve",
        headers=ADMIN_HEADERS,
        json={},
    )
    assert approve.status_code == 409


def test_v2_harvest_requires_dedicated_permission(app_client):
    response = app_client.get("/api/v2/harvest/applications")
    assert response.status_code == 403
    assert "operations.harvest.view" in response.json()["detail"]


def test_v2_safety_alert_confirmation_and_event_closure(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-SAFETY-BLOCK-001",
            "name": "上屯村安全事件林班",
            "countyCode": "350783",
            "countyName": "建瓯市",
            "townCode": "350783105",
            "townName": "小桥镇",
            "villageCode": "350783105206",
            "villageName": "上屯村",
            "areaMu": 40,
            "forestType": "毛竹林",
        },
    )
    assert block.status_code == 200

    camera = app_client.post(
        "/api/v2/iot/devices",
        headers=ADMIN_HEADERS,
        json={
            "name": "上屯村热成像摄像机",
            "deviceType": "camera",
            "serialNo": "V2-SAFETY-CAMERA-001",
            "status": "active",
            "connectivityStatus": "online",
            "locationText": "上屯村林班北坡",
            "linkedBlockCodes": ["V2-SAFETY-BLOCK-001"],
        },
    )
    assert camera.status_code == 200, camera.text

    created_alert = app_client.post(
        "/api/v2/safety/alerts",
        headers=ADMIN_HEADERS,
        json={
            "title": "上屯村烟点识别告警",
            "alertType": "fire",
            "severity": "high",
            "sourceType": "device",
            "sourceRef": "CAMERA-ALERT-001",
            "deviceCode": camera.json()["deviceCode"],
            "locationText": "上屯村林班北坡",
            "description": "热成像识别到持续烟点。",
            "linkedBlockCodes": ["V2-SAFETY-BLOCK-001"],
        },
    )
    assert created_alert.status_code == 200
    alert = created_alert.json()
    assert alert["status"] == "new"

    event_ledger_before = app_client.get(
        "/api/v2/safety/events",
        headers=ADMIN_HEADERS,
    )
    assert event_ledger_before.status_code == 200
    assert event_ledger_before.json()["total"] == 0

    converted = app_client.post(
        f"/api/v2/safety/alerts/{alert['id']}/actions/convert",
        headers=ADMIN_HEADERS,
        json={
            "title": "上屯村竹林疑似火情",
            "eventType": "fire",
            "severity": "high",
            "note": "人工复核画面，确认为需要现场核查的火情。",
        },
    )
    assert converted.status_code == 200
    assert converted.json()["alert"]["status"] == "converted"
    assert converted.json()["alert"]["review"]["decision"] == "converted"
    assert converted.json()["alert"]["review"]["reviewedBy"] == "v2-admin"
    event = converted.json()["event"]
    assert event["status"] == "new"
    assert event["sourceType"] == "alert"
    assert event["blocks"][0]["code"] == "V2-SAFETY-BLOCK-001"

    event_id = event["id"]
    transitions = (
        ("triage", {"eventType": "fire", "severity": "high", "responsibilityUnit": "小桥镇林业站"}, "triaged"),
        ("assign", {"assigneeName": "应急处置一组", "deadlineAt": "2026-12-31T18:00:00+08:00"}, "assigned"),
        ("accept", {"note": "处置组已出发。"}, "handling"),
        ("progress", {"note": "已抵达现场并建立隔离带。"}, "handling"),
        ("escalate", {"severity": "critical", "note": "现场风力增大，升级为紧急事件。"}, "handling"),
        ("resolve", {"resolutionSummary": "烟点已扑灭，现场完成复查。", "evidenceUrls": ["https://evidence.example/fire-001.jpg"]}, "resolved"),
        ("return", {"note": "缺少余火监测说明，退回补充。"}, "handling"),
        ("resolve", {"resolutionSummary": "完成两轮余火监测，无复燃迹象。"}, "resolved"),
        ("verify", {"note": "证据与现场复核一致。"}, "verified"),
        ("close", {"note": "事件关闭归档。"}, "closed"),
    )
    for action, body, expected in transitions:
        response = app_client.post(
            f"/api/v2/safety/events/{event_id}/actions/{action}",
            headers=ADMIN_HEADERS,
            json=body,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected

    closed = response.json()
    assert closed["severity"] == "critical"
    assert closed["resolution"]["summary"] == "完成两轮余火监测，无复燃迹象。"
    assert [item["action"] for item in closed["timeline"]] == [
        "convert-alert", "triage", "assign", "accept", "progress", "escalate",
        "resolve", "return", "resolve", "verify", "close",
    ]

    reopened = app_client.post(
        f"/api/v2/safety/events/{event_id}/actions/reopen",
        headers=ADMIN_HEADERS,
        json={"note": "复查发现同一位置再次出现烟点。"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "triaged"
    assert reopened.json()["assigneeName"] == ""
    assert reopened.json()["deadlineAt"] is None

    second_alert = app_client.post(
        "/api/v2/safety/alerts",
        headers=ADMIN_HEADERS,
        json={
            "title": "同一位置烟点重复告警",
            "alertType": "fire",
            "severity": "high",
            "sourceType": "ai",
            "sourceRef": "AI-ALERT-002",
            "linkedBlockCodes": ["V2-SAFETY-BLOCK-001"],
        },
    )
    assert second_alert.status_code == 200
    merged = app_client.post(
        f"/api/v2/safety/alerts/{second_alert.json()['id']}/actions/merge",
        headers=ADMIN_HEADERS,
        json={"eventId": event_id, "note": "位置和时间一致，合并到已重开事件。"},
    )
    assert merged.status_code == 200
    assert merged.json()["alert"]["status"] == "merged"
    assert merged.json()["alert"]["review"]["decision"] == "merged"
    assert merged.json()["event"]["timeline"][-1]["action"] == "merge-alert"

    filtered = app_client.get(
        "/api/v2/safety/events?linkedBlockCode=V2-SAFETY-BLOCK-001&severity=critical",
        headers=ADMIN_HEADERS,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1


def test_v2_safety_requires_dedicated_permissions(app_client):
    events = app_client.get("/api/v2/safety/events")
    alerts = app_client.get("/api/v2/safety/alerts")
    assert events.status_code == 403
    assert "safety.events.view" in events.json()["detail"]
    assert alerts.status_code == 403
    assert "safety.alerts.view" in alerts.json()["detail"]


def test_v2_safety_event_ledger_supports_edit_soft_delete_restore_and_export(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks", headers=ADMIN_HEADERS,
        json={"blockCode": "V2-SAFETY-CRUD-001", "name": "安全事件回归林班", "countyCode": "350783",
              "countyName": "建瓯市", "townCode": "350783105", "townName": "小桥镇",
              "villageCode": "350783105206", "villageName": "上屯村", "areaMu": 18, "forestType": "毛竹林"},
    )
    assert block.status_code == 200, block.text
    payload = {
        "title": "安全事件台账测试", "eventType": "equipment", "severity": "medium",
        "sourceType": "manual", "sourceRef": "", "locationText": "上屯村作业点",
        "description": "现场设备存在异常振动。", "linkedBlockCodes": ["V2-SAFETY-CRUD-001"],
    }
    created = app_client.post("/api/v2/safety/events", headers=ADMIN_HEADERS, json=payload)
    assert created.status_code == 200, created.text
    event_id = created.json()["id"]
    edited = app_client.patch(
        f"/api/v2/safety/events/{event_id}", headers=ADMIN_HEADERS,
        json={**payload, "title": "安全事件台账测试（更新）", "severity": "high"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"].endswith("（更新）")
    assert edited.json()["version"] == 2
    deleted = app_client.delete(f"/api/v2/safety/events/{event_id}", headers=ADMIN_HEADERS)
    assert deleted.status_code == 200 and deleted.json()["deletedAt"]
    assert app_client.get("/api/v2/safety/events", headers=ADMIN_HEADERS).json()["total"] == 0
    recycle = app_client.get("/api/v2/safety/events?includeDeleted=true", headers=ADMIN_HEADERS)
    assert recycle.status_code == 200
    assert any(item["id"] == event_id and item["deletedAt"] for item in recycle.json()["items"])
    restored = app_client.post(f"/api/v2/safety/events/{event_id}/restore", headers=ADMIN_HEADERS)
    assert restored.status_code == 200 and restored.json()["deletedAt"] is None
    export = app_client.get("/api/v2/safety/events-export.csv", headers=ADMIN_HEADERS)
    assert export.status_code == 200 and export.content.startswith(b"\xef\xbb\xbf")
    assert "安全事件台账测试" in export.content.decode("utf-8-sig")


def test_v2_labor_runs_worker_team_contract_attendance_and_settlement_closure(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-LABOR-BLOCK-001",
            "name": "上屯村劳务作业林班",
            "countyCode": "350783",
            "countyName": "建瓯市",
            "townCode": "350783105",
            "townName": "小桥镇",
            "villageCode": "350783105206",
            "villageName": "上屯村",
            "areaMu": 48,
            "forestType": "毛竹林",
        },
    )
    assert block.status_code == 200

    workers = []
    for index, name in enumerate(("张师傅", "李师傅"), start=1):
        response = app_client.post(
            "/api/v2/labor/workers",
            headers=ADMIN_HEADERS,
            json={
                "name": name,
                "mobile": f"1380000000{index}",
                "employmentStatus": "available",
                "skillCodes": ["tending", "harvest"],
                "qualifications": ["林业安全培训合格证"],
                "trainingStatus": "valid",
            },
        )
        assert response.status_code == 200, response.text
        workers.append(response.json())

    team = app_client.post(
        "/api/v2/labor/teams",
        headers=ADMIN_HEADERS,
        json={
            "name": "上屯毛竹作业一组",
            "leaderWorkerId": workers[0]["id"],
            "memberIds": [workers[1]["id"]],
            "serviceArea": "建瓯市小桥镇",
            "skillCodes": ["tending", "harvest"],
        },
    )
    assert team.status_code == 200, team.text
    assert len(team.json()["members"]) == 2

    created = app_client.post(
        "/api/v2/labor/jobs",
        headers=ADMIN_HEADERS,
        json={
            "title": "上屯村毛竹抚育用工",
            "employerType": "cooperative",
            "employerName": "上屯村竹产业合作社",
            "workType": "tending",
            "requiredHeadcount": 2,
            "unitPrice": 180,
            "priceUnit": "mu",
            "plannedStartAt": "2026-09-01T08:00:00+08:00",
            "plannedEndAt": "2026-09-05T18:00:00+08:00",
            "linkedBlockCodes": ["V2-LABOR-BLOCK-001"],
            "instructions": "完成竹林清杂、疏伐与作业面整理。",
        },
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    actions = (
        ("publish", {}, "published"),
        ("match", {"teamId": team.json()["id"]}, "matched"),
        (
            "contract",
            {
                "contractNo": "LW-HT-2026-001",
                "contractStartAt": "2026-09-01T08:00:00+08:00",
                "contractEndAt": "2026-09-05T18:00:00+08:00",
                "paymentTerms": "验收后 7 日内结算。",
            },
            "contracted",
        ),
        ("start", {}, "working"),
    )
    for action, body, expected in actions:
        response = app_client.post(
            f"/api/v2/labor/jobs/{job_id}/actions/{action}",
            headers=ADMIN_HEADERS,
            json=body,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected

    blocked_submit = app_client.post(
        f"/api/v2/labor/jobs/{job_id}/actions/submit",
        headers=ADMIN_HEADERS,
        json={"actualQuantity": 42},
    )
    assert blocked_submit.status_code == 422
    assert "考勤" in blocked_submit.json()["detail"]

    attendance = app_client.post(
        f"/api/v2/labor/jobs/{job_id}/actions/attendance",
        headers=ADMIN_HEADERS,
        json={
            "workerId": workers[0]["id"],
            "workDate": "2026-09-01",
            "checkInAt": "2026-09-01T08:00:00+08:00",
            "checkOutAt": "2026-09-01T17:30:00+08:00",
            "workHours": 8,
            "workQuantity": 9.5,
            "note": "现场负责人核验通过。",
        },
    )
    assert attendance.status_code == 200, attendance.text
    assert attendance.json()["attendance"][0]["workerName"] == "张师傅"

    submitted = app_client.post(
        f"/api/v2/labor/jobs/{job_id}/actions/submit",
        headers=ADMIN_HEADERS,
        json={"actualQuantity": 42, "evidenceUrls": ["https://evidence.example/labor-001.jpg"]},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"

    settled = app_client.post(
        f"/api/v2/labor/jobs/{job_id}/actions/settle",
        headers=ADMIN_HEADERS,
        json={"settlementAmount": 7560, "note": "按 42 亩完成量结算。"},
    )
    assert settled.status_code == 200
    assert settled.json()["settlement"]["amount"] == 7560

    closed = app_client.post(
        f"/api/v2/labor/jobs/{job_id}/actions/close",
        headers=ADMIN_HEADERS,
        json={"note": "工资已支付，任务归档。"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert [item["action"] for item in closed.json()["timeline"]] == [
        "create", "publish", "match", "contract", "start", "attendance", "submit", "settle", "close",
    ]

    ledger = app_client.get(
        "/api/v2/labor/jobs?linkedBlockCode=V2-LABOR-BLOCK-001&status=closed",
        headers=ADMIN_HEADERS,
    )
    assert ledger.status_code == 200
    assert ledger.json()["total"] == 1


def test_v2_labor_rejects_non_team_attendance_and_requires_permission(app_client):
    response = app_client.get("/api/v2/labor/jobs")
    assert response.status_code == 403
    assert "labor.view" in response.json()["detail"]


def test_v2_labor_ledgers_support_edit_soft_delete_restore_and_csv_export(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-LABOR-CRUD-001", "name": "劳务台账回归林班",
            "countyCode": "350783", "countyName": "建瓯市", "townCode": "350783105",
            "townName": "小桥镇", "villageCode": "350783105206", "villageName": "上屯村",
            "areaMu": 26, "forestType": "毛竹林",
        },
    )
    assert block.status_code == 200, block.text

    worker_payload = {
        "name": "劳务台账测试人员", "mobile": "13800009001", "idCardMask": "3507********9001",
        "gender": "男", "employmentStatus": "available", "skillCodes": ["tending"],
        "qualifications": ["安全培训证"], "trainingStatus": "valid", "creditScore": 96,
        "homeAddress": "建瓯市小桥镇", "emergencyContact": "联系人 13800009002", "notes": "初始档案",
    }
    worker = app_client.post("/api/v2/labor/workers", headers=ADMIN_HEADERS, json=worker_payload)
    assert worker.status_code == 200, worker.text
    worker_id = worker.json()["id"]
    edited_worker = app_client.patch(
        f"/api/v2/labor/workers/{worker_id}", headers=ADMIN_HEADERS,
        json={**worker_payload, "mobile": "13800009003", "notes": "已更新档案"},
    )
    assert edited_worker.status_code == 200, edited_worker.text
    assert edited_worker.json()["mobile"] == "13800009003"
    assert app_client.delete(f"/api/v2/labor/workers/{worker_id}", headers=ADMIN_HEADERS).status_code == 200
    deleted_workers = app_client.get("/api/v2/labor/workers?includeDeleted=true", headers=ADMIN_HEADERS)
    assert any(item["id"] == worker_id and item["deletedAt"] for item in deleted_workers.json()["items"])
    assert app_client.post(f"/api/v2/labor/workers/{worker_id}/restore", headers=ADMIN_HEADERS).status_code == 200
    worker_csv = app_client.get("/api/v2/labor/workers-export.csv", headers=ADMIN_HEADERS)
    assert worker_csv.status_code == 200 and worker_csv.content.startswith(b"\xef\xbb\xbf")

    team = app_client.post(
        "/api/v2/labor/teams", headers=ADMIN_HEADERS,
        json={"name": "劳务台账测试班组", "status": "active", "leaderWorkerId": worker_id,
              "memberIds": [worker_id], "contactPhone": "13800009003", "serviceArea": "建瓯市小桥镇",
              "skillCodes": ["tending"], "notes": "初始班组"},
    )
    assert team.status_code == 200, team.text
    team_id = team.json()["id"]
    edited_team = app_client.patch(
        f"/api/v2/labor/teams/{team_id}", headers=ADMIN_HEADERS,
        json={"name": "劳务台账测试班组（更新）", "status": "active", "leaderWorkerId": worker_id,
              "memberIds": [worker_id], "contactPhone": "13800009003", "serviceArea": "建瓯市小桥镇及周边",
              "skillCodes": ["tending", "survey"], "notes": "已更新班组"},
    )
    assert edited_team.status_code == 200, edited_team.text
    assert edited_team.json()["serviceArea"].endswith("及周边")
    assert app_client.delete(f"/api/v2/labor/teams/{team_id}", headers=ADMIN_HEADERS).status_code == 200
    assert app_client.get("/api/v2/labor/teams", headers=ADMIN_HEADERS).json()["total"] == 0
    assert app_client.post(f"/api/v2/labor/teams/{team_id}/restore", headers=ADMIN_HEADERS).status_code == 200
    assert app_client.get("/api/v2/labor/teams-export.csv", headers=ADMIN_HEADERS).status_code == 200

    job_payload = {
        "title": "劳务台账测试任务", "employerType": "cooperative", "employerName": "测试合作社",
        "workType": "tending", "requiredHeadcount": 3, "unitPrice": 160, "priceUnit": "mu",
        "plannedStartAt": "2026-10-01T08:00:00+08:00", "plannedEndAt": "2026-10-03T18:00:00+08:00",
        "linkedBlockCodes": ["V2-LABOR-CRUD-001"], "instructions": "初始作业要求",
    }
    job = app_client.post("/api/v2/labor/jobs", headers=ADMIN_HEADERS, json=job_payload)
    assert job.status_code == 200, job.text
    job_id = job.json()["id"]
    edited_job = app_client.patch(
        f"/api/v2/labor/jobs/{job_id}", headers=ADMIN_HEADERS,
        json={**job_payload, "title": "劳务台账测试任务（更新）", "requiredHeadcount": 4},
    )
    assert edited_job.status_code == 200, edited_job.text
    assert edited_job.json()["title"].endswith("（更新）")
    assert edited_job.json()["version"] == 2
    assert app_client.delete(f"/api/v2/labor/jobs/{job_id}", headers=ADMIN_HEADERS).status_code == 200
    deleted_jobs = app_client.get("/api/v2/labor/jobs?includeDeleted=true", headers=ADMIN_HEADERS)
    assert any(item["id"] == job_id and item["deletedAt"] for item in deleted_jobs.json()["items"])
    restored_job = app_client.post(f"/api/v2/labor/jobs/{job_id}/restore", headers=ADMIN_HEADERS)
    assert restored_job.status_code == 200 and restored_job.json()["deletedAt"] is None
    job_csv = app_client.get("/api/v2/labor/jobs-export.csv", headers=ADMIN_HEADERS)
    assert job_csv.status_code == 200 and "劳务台账测试任务" in job_csv.content.decode("utf-8-sig")


def test_v2_equipment_drone_and_ai_finding_form_one_traceable_chain(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-DRONE-BLOCK-001",
            "name": "上屯村无人机巡检林班",
            "countyCode": "350783",
            "countyName": "建瓯市",
            "townCode": "350783105",
            "townName": "小桥镇",
            "villageCode": "350783105206",
            "villageName": "上屯村",
            "areaMu": 261,
            "forestType": "毛竹林",
        },
    )
    assert block.status_code == 200, block.text

    device = app_client.post(
        "/api/v2/iot/devices",
        headers=ADMIN_HEADERS,
        json={
            "name": "小桥镇巡检无人机 01",
            "deviceType": "drone",
            "vendor": "DJI",
            "model": "M350 RTK",
            "serialNo": "V2-DRONE-SN-001",
            "status": "active",
            "connectivityStatus": "online",
            "ownerUnit": "小桥镇林业站",
            "custodian": "林业无人机中队",
            "locationText": "小桥镇无人机机库",
            "linkedBlockCodes": ["V2-DRONE-BLOCK-001"],
            "metadata": {"payload": "可见光+热成像"},
        },
    )
    assert device.status_code == 200, device.text
    device_record = device.json()
    assert device_record["blocks"][0]["code"] == "V2-DRONE-BLOCK-001"

    maintained = app_client.post(
        f"/api/v2/iot/devices/{device_record['id']}/maintenance",
        headers=ADMIN_HEADERS,
        json={
            "maintenanceType": "inspection",
            "scheduledAt": "2026-09-01T08:00:00+08:00",
            "completedAt": "2026-09-01T09:00:00+08:00",
            "assigneeName": "设备保障组",
            "description": "飞前电池、桨叶和云台检查。",
            "result": "检查通过，可执行任务。",
        },
    )
    assert maintained.status_code == 200, maintained.text
    assert maintained.json()["maintenance"][0]["status"] == "completed"

    mission = app_client.post(
        "/api/v2/drone/missions",
        headers=ADMIN_HEADERS,
        json={
            "title": "上屯村病虫害低空巡检",
            "missionType": "pest",
            "droneDeviceId": device_record["id"],
            "plannedStartAt": "2026-09-02T08:00:00+08:00",
            "plannedEndAt": "2026-09-02T12:00:00+08:00",
            "linkedBlockCodes": ["V2-DRONE-BLOCK-001"],
            "objective": "采集竹冠层异常影像并形成待复核成果。",
        },
    )
    assert mission.status_code == 200, mission.text
    mission_id = mission.json()["id"]
    transitions = (
        ("assign", {"pilotName": "陈飞手", "routeName": "上屯北坡航线"}, "assigned"),
        ("start", {"note": "完成飞前检查，开始作业。"}, "flying"),
        (
            "upload-result",
            {
                "resultAssetUrls": ["https://assets.example/drone/mission-001/orthophoto.tif"],
                "flightDurationMinutes": 76,
                "flightDistanceKm": 14.2,
                "coverageAreaMu": 261,
            },
            "processing",
        ),
        ("review", {"reviewNote": "影像完整、坐标正确，可归档并进入 AI 分析。"}, "reviewed"),
        ("complete", {"note": "飞行任务成果归档。"}, "completed"),
    )
    for action, body, expected in transitions:
        response = app_client.post(
            f"/api/v2/drone/missions/{mission_id}/actions/{action}",
            headers=ADMIN_HEADERS,
            json=body,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected

    flights = app_client.get("/api/v2/drone/flights", headers=ADMIN_HEADERS)
    assert flights.status_code == 200, flights.text
    flight = next(item for item in flights.json()["items"] if item["missionId"] == mission_id)
    assert flight["origin"] == "mission"
    assert flight["completeness"] == "complete"
    assert flight["durationMinutes"] == 76
    assert flight["distanceKm"] == 14.2
    assert flight["coverageAreaMu"] == 261
    assert flight["blocks"][0]["code"] == "V2-DRONE-BLOCK-001"
    flight_csv = app_client.get("/api/v2/drone/flights-export.csv", headers=ADMIN_HEADERS)
    assert flight_csv.status_code == 200
    assert mission_id in flight_csv.content.decode("utf-8-sig")

    finding = app_client.post(
        "/api/v2/ai/findings",
        headers=ADMIN_HEADERS,
        json={
            "title": "上屯北坡疑似竹蝗危害斑块",
            "findingType": "pest",
            "modelCode": "bamboo-pest-detector",
            "modelVersion": "2.1.0",
            "confidence": 0.92,
            "sourceAssetUrl": "https://assets.example/drone/mission-001/pest-clip-07.jpg",
            "droneMissionId": mission_id,
            "result": {"class": "bamboo-locust", "bbox": [0.2, 0.1, 0.6, 0.7]},
        },
    )
    assert finding.status_code == 200, finding.text
    finding_record = finding.json()
    assert finding_record["status"] == "pending"
    assert finding_record["deviceId"] == device_record["id"]
    assert finding_record["blocks"][0]["code"] == "V2-DRONE-BLOCK-001"

    confirmed = app_client.post(
        f"/api/v2/ai/findings/{finding_record['id']}/actions/confirm",
        headers=ADMIN_HEADERS,
        json={"note": "人工核对原始影像，确认为需要现场排查的疑似虫害。"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["result"]["humanConfirmed"] is True

    converted = app_client.post(
        f"/api/v2/ai/findings/{finding_record['id']}/actions/convert-alert",
        headers=ADMIN_HEADERS,
        json={"severity": "high", "note": "转植保安全告警，安排现场踏查。"},
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["finding"]["status"] == "converted"
    alert = converted.json()["alert"]
    assert alert["sourceType"] == "ai"
    assert alert["sourceRef"] == finding_record["id"]
    assert alert["deviceCode"] == device_record["deviceCode"]
    assert alert["linkedBlockCodes"] == ["V2-DRONE-BLOCK-001"]
    assert alert["rawPayload"]["modelVersion"] == "2.1.0"
    assert alert["rawPayload"]["confidence"] == 0.92

    alerts = app_client.get(
        "/api/v2/safety/alerts?status=new&severity=high",
        headers=ADMIN_HEADERS,
    )
    assert alerts.status_code == 200
    assert any(item["id"] == alert["id"] for item in alerts.json()["items"])


def test_v2_equipment_drone_and_ai_require_dedicated_permissions(app_client):
    devices = app_client.get("/api/v2/iot/devices")
    missions = app_client.get("/api/v2/drone/missions")
    flights = app_client.get("/api/v2/drone/flights")
    findings = app_client.get("/api/v2/ai/findings")
    assert devices.status_code == 403
    assert "iot.devices.view" in devices.json()["detail"]
    assert missions.status_code == 403
    assert flights.status_code == 403
    assert "drone.missions.view" in missions.json()["detail"]
    assert findings.status_code == 403
    assert "ai.findings.view" in findings.json()["detail"]


def test_v2_drone_and_ai_ledgers_support_export_recycle_restore_and_audit_lock(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks", headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-LOWALT-CRUD-001", "name": "低空作业闭环林班",
            "countyCode": "350783", "countyName": "建瓯市", "townCode": "350783105",
            "townName": "小桥镇", "villageCode": "350783105206", "villageName": "上屯村",
            "areaMu": 56, "forestType": "毛竹林",
        },
    )
    assert block.status_code == 200, block.text
    device = app_client.post(
        "/api/v2/iot/devices", headers=ADMIN_HEADERS,
        json={
            "name": "低空闭环测试无人机", "deviceType": "drone", "serialNo": "V2-LOWALT-DRONE-001",
            "status": "active", "connectivityStatus": "online", "ownerUnit": "小桥镇林业站",
            "custodian": "无人机中队", "linkedBlockCodes": ["V2-LOWALT-CRUD-001"],
        },
    )
    assert device.status_code == 200, device.text
    mission_payload = {
        "title": "低空台账闭环任务", "missionType": "survey", "droneDeviceId": device.json()["id"],
        "plannedStartAt": "2026-09-10T08:00:00+08:00", "plannedEndAt": "2026-09-10T10:00:00+08:00",
        "linkedBlockCodes": ["V2-LOWALT-CRUD-001"], "objective": "验证正式台账闭环。",
    }
    mission = app_client.post("/api/v2/drone/missions", headers=ADMIN_HEADERS, json=mission_payload)
    assert mission.status_code == 200, mission.text
    mission_id = mission.json()["id"]
    edited_mission = app_client.patch(
        f"/api/v2/drone/missions/{mission_id}", headers=ADMIN_HEADERS,
        json={**mission_payload, "title": "低空台账闭环任务（更新）"},
    )
    assert edited_mission.status_code == 200 and edited_mission.json()["title"].endswith("（更新）")
    mission_csv = app_client.get("/api/v2/drone/missions-export.csv", headers=ADMIN_HEADERS)
    assert mission_csv.status_code == 200 and "低空台账闭环任务" in mission_csv.content.decode("utf-8-sig")
    assert app_client.delete(f"/api/v2/drone/missions/{mission_id}", headers=ADMIN_HEADERS).status_code == 200
    deleted_missions = app_client.get("/api/v2/drone/missions?includeDeleted=true", headers=ADMIN_HEADERS)
    assert any(item["id"] == mission_id and item["deletedAt"] for item in deleted_missions.json()["items"])
    restored_mission = app_client.post(f"/api/v2/drone/missions/{mission_id}/restore", headers=ADMIN_HEADERS)
    assert restored_mission.status_code == 200 and restored_mission.json()["deletedAt"] is None

    finding_payload = {
        "title": "低空成果疑似异常", "findingType": "pest", "modelCode": "bamboo-audit-model",
        "modelVersion": "1.0.0", "confidence": 0.81,
        "sourceAssetUrl": "https://assets.example/low-altitude/finding-001.jpg",
        "droneMissionId": mission_id, "result": {"observation": "初始识别结果"},
    }
    finding = app_client.post("/api/v2/ai/findings", headers=ADMIN_HEADERS, json=finding_payload)
    assert finding.status_code == 200, finding.text
    finding_id = finding.json()["id"]
    edited_finding = app_client.patch(
        f"/api/v2/ai/findings/{finding_id}", headers=ADMIN_HEADERS,
        json={"title": "低空成果疑似异常（更新）", "confidence": 0.86},
    )
    assert edited_finding.status_code == 200, edited_finding.text
    assert edited_finding.json()["confidence"] == 0.86
    finding_csv = app_client.get("/api/v2/ai/findings-export.csv", headers=ADMIN_HEADERS)
    assert finding_csv.status_code == 200 and "低空成果疑似异常" in finding_csv.content.decode("utf-8-sig")
    assert app_client.delete(f"/api/v2/ai/findings/{finding_id}", headers=ADMIN_HEADERS).status_code == 200
    deleted_findings = app_client.get("/api/v2/ai/findings?includeDeleted=true", headers=ADMIN_HEADERS)
    assert any(item["id"] == finding_id and item["deletedAt"] for item in deleted_findings.json()["items"])
    restored_finding = app_client.post(f"/api/v2/ai/findings/{finding_id}/restore", headers=ADMIN_HEADERS)
    assert restored_finding.status_code == 200 and restored_finding.json()["deletedAt"] is None
    confirmed = app_client.post(
        f"/api/v2/ai/findings/{finding_id}/actions/confirm", headers=ADMIN_HEADERS,
        json={"note": "人工确认后锁定算法依据。"},
    )
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"
    assert app_client.patch(f"/api/v2/ai/findings/{finding_id}", headers=ADMIN_HEADERS, json={"title": "不应修改"}).status_code == 409
    assert app_client.delete(f"/api/v2/ai/findings/{finding_id}", headers=ADMIN_HEADERS).status_code == 409


def test_v2_ai_model_assets_support_lifecycle_relations_export_and_delete_protection(app_client):
    dataset = app_client.post(
        "/api/v2/ai/model-assets",
        headers=ADMIN_HEADERS,
        json={
            "assetType": "dataset", "name": "竹林病虫害标注集", "code": "bamboo-pest-dataset",
            "status": "ready", "description": "病虫害样本与标注清单。",
            "metrics": {"sampleCount": 1200, "labeledCount": 1180},
        },
    )
    assert dataset.status_code == 200, dataset.text
    dataset_record = dataset.json()
    assert dataset_record["assetType"] == "dataset"
    assert dataset_record["parent"] is None

    model = app_client.post(
        "/api/v2/ai/model-assets",
        headers=ADMIN_HEADERS,
        json={
            "assetType": "model-version", "name": "竹林病虫害识别模型", "code": "bamboo-pest-detector",
            "version": "2.1.0", "status": "ready", "parentId": dataset_record["id"],
            "framework": "PyTorch / ONNX", "metrics": {"accuracy": 0.94, "recall": 0.91},
        },
    )
    assert model.status_code == 200, model.text
    model_record = model.json()
    assert model_record["parent"]["id"] == dataset_record["id"]

    deployment = app_client.post(
        "/api/v2/ai/model-assets",
        headers=ADMIN_HEADERS,
        json={
            "assetType": "deployment", "name": "病虫害模型生产部署", "code": "bamboo-pest-prod",
            "status": "active", "parentId": model_record["id"], "runtimeTarget": "GPU 推理集群",
            "metrics": {"replicaCount": 2, "latencyMs": 86},
        },
    )
    assert deployment.status_code == 200, deployment.text
    assert deployment.json()["parent"]["assetType"] == "model-version"

    invalid_parent = app_client.post(
        "/api/v2/ai/model-assets",
        headers=ADMIN_HEADERS,
        json={"assetType": "evaluation", "name": "错误评测", "code": "invalid-eval", "status": "draft", "parentId": dataset_record["id"]},
    )
    assert invalid_parent.status_code == 422

    export = app_client.get("/api/v2/ai/model-assets/export.csv", headers=ADMIN_HEADERS)
    assert export.status_code == 200
    assert "竹林病虫害识别模型" in export.content.decode("utf-8-sig")

    protected_delete = app_client.delete(f"/api/v2/ai/model-assets/{model_record['id']}", headers=ADMIN_HEADERS)
    assert protected_delete.status_code == 409
    deleted = app_client.delete(f"/api/v2/ai/model-assets/{deployment.json()['id']}", headers=ADMIN_HEADERS)
    assert deleted.status_code == 200
    restored = app_client.post(f"/api/v2/ai/model-assets/{deployment.json()['id']}/restore", headers=ADMIN_HEADERS)
    assert restored.status_code == 200 and restored.json()["deletedAt"] is None


def test_v2_ai_inference_runs_link_models_attachments_blocks_and_findings(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks", headers=ADMIN_HEADERS,
        json={"blockCode": "V2-AI-RUN-001", "name": "AI 推理测试林班", "countyCode": "350783", "countyName": "建瓯市", "townCode": "350783105", "townName": "小桥镇", "villageCode": "350783105206", "villageName": "上屯村", "areaMu": 36, "forestType": "毛竹林"},
    )
    assert block.status_code == 200, block.text
    uploaded = app_client.post(
        "/api/v2/attachments", headers=ADMIN_HEADERS,
        files={"file": ("竹林航片.jpg", b"controlled-ai-input", "image/jpeg")},
        data={"category": "ai_inference_input", "description": "AI 推理受控输入"},
    )
    assert uploaded.status_code == 200, uploaded.text
    dataset = app_client.post(
        "/api/v2/ai/model-assets", headers=ADMIN_HEADERS,
        json={"assetType": "dataset", "name": "AI 推理训练集", "code": "ai-run-dataset", "status": "ready"},
    ).json()
    model = app_client.post(
        "/api/v2/ai/model-assets", headers=ADMIN_HEADERS,
        json={"assetType": "model-version", "name": "AI 推理测试模型", "code": "ai-run-model", "version": "1.0.0", "status": "ready", "parentId": dataset["id"]},
    )
    assert model.status_code == 200, model.text
    created = app_client.post(
        "/api/v2/ai/inference-runs", headers=ADMIN_HEADERS,
        json={"title": "上屯村病虫害推理", "modelAssetId": model.json()["id"], "inputAttachmentId": uploaded.json()["id"], "linkedBlockCodes": ["V2-AI-RUN-001"], "parameters": {"threshold": 0.75}},
    )
    assert created.status_code == 200, created.text
    run = created.json()
    assert run["status"] == "queued"
    assert run["blocks"][0]["code"] == "V2-AI-RUN-001"
    assert run["inputAttachments"][0]["originalName"] == "竹林航片.jpg"
    protected_model = app_client.delete(f"/api/v2/ai/model-assets/{model.json()['id']}", headers=ADMIN_HEADERS)
    assert protected_model.status_code == 409
    assert "推理任务" in protected_model.json()["detail"]

    started = app_client.post(f"/api/v2/ai/inference-runs/{run['id']}/actions/start", headers=ADMIN_HEADERS, json={})
    assert started.status_code == 200 and started.json()["status"] == "running"
    succeeded = app_client.post(
        f"/api/v2/ai/inference-runs/{run['id']}/actions/succeed", headers=ADMIN_HEADERS,
        json={"output": {"class": "pest", "confidence": 0.93}},
    )
    assert succeeded.status_code == 200, succeeded.text
    assert succeeded.json()["status"] == "succeeded"
    assert succeeded.json()["durationMs"] is not None

    converted = app_client.post(
        f"/api/v2/ai/inference-runs/{run['id']}/finding", headers=ADMIN_HEADERS,
        json={"title": "上屯村疑似虫害", "findingType": "pest", "confidence": 0.93, "locationText": "上屯村测试区"},
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["run"]["findingId"] == converted.json()["finding"]["id"]
    assert converted.json()["finding"]["status"] == "pending"
    assert converted.json()["finding"]["result"]["inferenceRunId"] == run["id"]
    assert app_client.delete(f"/api/v2/ai/inference-runs/{run['id']}", headers=ADMIN_HEADERS).status_code == 409

    exported = app_client.get("/api/v2/ai/inference-runs/export.csv", headers=ADMIN_HEADERS)
    assert exported.status_code == 200
    assert "上屯村病虫害推理" in exported.content.decode("utf-8-sig")


def test_v2_equipment_ledger_supports_update_export_recycle_restore_and_device_alert_linkage(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-IOT-CRUD-001", "name": "设备闭环测试林班",
            "countyCode": "350783", "countyName": "建瓯市", "townCode": "350783105",
            "townName": "小桥镇", "villageCode": "350783105206", "villageName": "上屯村",
            "areaMu": 48, "forestType": "毛竹林",
        },
    )
    assert block.status_code == 200, block.text
    created = app_client.post(
        "/api/v2/iot/devices",
        headers=ADMIN_HEADERS,
        json={
            "name": "北坡环境监测站", "deviceType": "sensor", "vendor": "竹山物联",
            "model": "BAMBOO-IOT-01", "serialNo": "V2-IOT-CRUD-SN-001", "status": "active",
            "connectivityStatus": "online", "ownerUnit": "小桥镇林业站", "custodian": "设备组",
            "longitude": 118.32, "latitude": 27.05, "locationText": "上屯村北坡监测点",
            "linkedBlockCodes": ["V2-IOT-CRUD-001"], "metadata": {"protocol": "MQTT"},
        },
    )
    assert created.status_code == 200, created.text
    device = created.json()
    edited = app_client.patch(
        f"/api/v2/iot/devices/{device['id']}", headers=ADMIN_HEADERS,
        json={"name": "北坡环境监测站（校准）", "connectivityStatus": "offline"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"].endswith("（校准）")

    exported = app_client.get("/api/v2/iot/devices-export.csv?q=校准", headers=ADMIN_HEADERS)
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    assert "北坡环境监测站（校准）" in exported.content.decode("utf-8-sig")

    deleted = app_client.delete(f"/api/v2/iot/devices/{device['id']}", headers=ADMIN_HEADERS)
    assert deleted.status_code == 200
    assert app_client.get("/api/v2/iot/devices?q=校准", headers=ADMIN_HEADERS).json()["total"] == 0
    recycle = app_client.get("/api/v2/iot/devices?q=校准&includeDeleted=true", headers=ADMIN_HEADERS)
    assert recycle.status_code == 200
    assert recycle.json()["items"][0]["deletedAt"]

    rejected_alert = app_client.post(
        "/api/v2/safety/alerts", headers=ADMIN_HEADERS,
        json={"title": "已删除设备告警", "alertType": "equipment", "severity": "medium",
              "sourceType": "device", "sourceRef": "sensor-message-001", "deviceCode": device["deviceCode"]},
    )
    assert rejected_alert.status_code == 422
    assert "已删除" in rejected_alert.json()["detail"]

    restored = app_client.post(f"/api/v2/iot/devices/{device['id']}/restore", headers=ADMIN_HEADERS)
    assert restored.status_code == 200
    assert restored.json()["deletedAt"] is None
    alert = app_client.post(
        "/api/v2/safety/alerts", headers=ADMIN_HEADERS,
        json={"title": "监测站离线告警", "alertType": "equipment", "severity": "medium",
              "sourceType": "device", "sourceRef": "sensor-message-002", "deviceCode": device["deviceCode"]},
    )
    assert alert.status_code == 200, alert.text
    assert alert.json()["deviceCode"] == device["deviceCode"]
    assert alert.json()["linkedBlockCodes"] == ["V2-IOT-CRUD-001"]
    assert alert.json()["locationText"] == "上屯村北坡监测点"


def test_v2_situation_assets_are_derived_from_formal_device_ledger_and_block_relation(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": "V2-SITUATION-BLOCK-001", "name": "态势联动测试林班",
            "countyCode": "350783", "countyName": "建瓯市", "townCode": "350783105",
            "townName": "小桥镇", "villageCode": "350783105206", "villageName": "上屯村",
            "areaMu": 32.5, "forestType": "毛竹林",
        },
    )
    assert block.status_code == 200, block.text
    device = app_client.post(
        "/api/v2/iot/devices",
        headers=ADMIN_HEADERS,
        json={
            "name": "上屯村态势联动卡口", "deviceType": "camera", "vendor": "竹山物联",
            "model": "PTZ-4K", "serialNo": "V2-SITUATION-CAM-001", "status": "active",
            "connectivityStatus": "online", "ownerUnit": "小桥镇林业站", "custodian": "设备组",
            "locationText": "上屯村林班入口", "linkedBlockCodes": ["V2-SITUATION-BLOCK-001"],
            "metadata": {"displayOnDashboard": True, "situationKind": "camera", "network": "5G 专网"},
        },
    )
    assert device.status_code == 200, device.text

    response = app_client.get("/api/v2/iot/situation-assets", headers=ADMIN_HEADERS)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "device-and-mission-ledgers"
    point = next(item for item in payload["items"] if item["id"] == device.json()["id"])
    assert point["sourceType"] == "device"
    assert point["kind"] == "camera"
    assert point["blockCode"] == "V2-SITUATION-BLOCK-001"
    assert ["网络状态", "5G 专网"] in point["parameters"]


def test_v2_mobile_offline_sync_track_and_resumable_evidence_flow(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={"blockCode": "V2-MOBILE-001", "name": "移动巡护林班", "areaMu": 36},
    )
    assert block.status_code == 200
    task = app_client.post(
        "/api/v2/patrol/tasks",
        headers=ADMIN_HEADERS,
        json={
            "name": "移动端离线巡护",
            "priority": "high",
            "plannedStartAt": "2026-08-11T08:00:00+08:00",
            "plannedEndAt": "2026-08-11T12:00:00+08:00",
            "assigneeName": "v2-admin",
            "linkedBlockCodes": ["V2-MOBILE-001"],
            "instructions": "弱网条件下记录轨迹并回传证据。",
        },
    ).json()

    package = app_client.get("/api/v2/mobile/offline-package", headers=ADMIN_HEADERS)
    assert package.status_code == 200
    assert package.json()["packageVersion"]
    assert package.json()["clientPolicy"]["minimumVersions"]["android"] == "1.0.0"
    assert any(item["id"] == task["id"] for item in package.json()["tasks"])

    registration_payload = {
        "deviceId": "android-field-device-0001",
        "deviceName": "巡护员手机",
        "platform": "android",
        "appVersion": "1.0.0",
        "osVersion": "Android 14",
        "pushToken": "push-token-0001",
        "capabilities": ["camera", "location", "secure-store"],
    }
    registered = app_client.post("/api/v2/mobile/devices/register", headers=ADMIN_HEADERS, json=registration_payload)
    assert registered.status_code == 200, registered.text
    assert registered.json()["device"]["status"] == "active"
    assert registered.json()["clientPolicy"]["latestVersions"]["android"] == "1.0.0"
    device_ledger = app_client.get("/api/v2/mobile/devices", headers=ADMIN_HEADERS)
    assert device_ledger.status_code == 200
    assert device_ledger.json()["total"] == 1
    assert device_ledger.json()["items"][0]["pushToken"] == ""
    assert device_ledger.json()["items"][0]["pushTokenRegistered"] is True
    revoked = app_client.post(
        "/api/v2/mobile/devices/android-field-device-0001/revoke",
        headers=ADMIN_HEADERS, json={"note": "测试远程注销设备"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["pushToken"] == ""
    blocked_package = app_client.get(
        "/api/v2/mobile/offline-package", headers={**ADMIN_HEADERS, "X-Smart-Bamboo-Device-ID": "android-field-device-0001"},
    )
    assert blocked_package.status_code == 403
    assert "远程注销" in blocked_package.json()["detail"]
    denied = app_client.post("/api/v2/mobile/devices/register", headers=ADMIN_HEADERS, json=registration_payload)
    assert denied.status_code == 403
    restored_device = app_client.post(
        "/api/v2/mobile/devices/android-field-device-0001/restore", headers=ADMIN_HEADERS,
    )
    assert restored_device.status_code == 200
    assert restored_device.json()["status"] == "active"

    track_payload = {
        "clientTrackId": "track-mobile-0001",
        "taskType": "patrol",
        "taskId": task["id"],
        "status": "completed",
        "points": [
            {"longitude": 118.312, "latitude": 27.045, "capturedAt": "2026-08-11T08:10:00+08:00"},
            {"longitude": 118.313, "latitude": 27.046, "capturedAt": "2026-08-11T08:15:00+08:00"},
        ],
    }
    first_track = app_client.post("/api/v2/mobile/tracks", headers=ADMIN_HEADERS, json=track_payload)
    replayed_track = app_client.post("/api/v2/mobile/tracks", headers=ADMIN_HEADERS, json=track_payload)
    assert first_track.status_code == replayed_track.status_code == 200
    assert first_track.json()["replayed"] is False
    assert replayed_track.json()["replayed"] is True
    assert app_client.get("/api/v2/mobile/tracks", headers=ADMIN_HEADERS).json()["total"] == 1

    sync_payload = {"operations": [{
        "clientOperationId": "operation-mobile-0001",
        "entityType": "patrol",
        "entityId": task["id"],
        "action": "accept",
        "occurredAt": "2026-08-11T08:05:00+08:00",
        "payload": {},
    }]}
    first_sync = app_client.post("/api/v2/mobile/sync", headers=ADMIN_HEADERS, json=sync_payload)
    replayed_sync = app_client.post("/api/v2/mobile/sync", headers=ADMIN_HEADERS, json=sync_payload)
    assert first_sync.json()["completed"] == 1
    assert replayed_sync.json()["results"][0]["replayed"] is True
    assert app_client.get("/api/v2/mobile/operations", headers=ADMIN_HEADERS).json()["total"] == 1
    assert app_client.get("/api/v2/mobile/operations-export.csv", headers=ADMIN_HEADERS).status_code == 200

    content = b"mobile-evidence-data"
    session = app_client.post(
        "/api/v2/mobile/uploads",
        headers=ADMIN_HEADERS,
        json={
            "fileName": "patrol.png",
            "contentType": "image/png",
            "totalBytes": len(content),
            "totalChunks": 2,
            "sha256": hashlib.sha256(content).hexdigest(),
            "taskType": "patrol",
            "taskId": task["id"],
        },
    ).json()
    first_chunk = content[:8]
    second_chunk = content[8:]
    assert app_client.put(
        f"/api/v2/mobile/uploads/{session['id']}/chunks/0",
        headers=ADMIN_HEADERS,
        files={"file": ("0.part", first_chunk, "application/octet-stream")},
    ).status_code == 200
    assert app_client.post(
        f"/api/v2/mobile/uploads/{session['id']}/complete", headers=ADMIN_HEADERS
    ).status_code == 409
    assert app_client.put(
        f"/api/v2/mobile/uploads/{session['id']}/chunks/1",
        headers=ADMIN_HEADERS,
        files={"file": ("1.part", second_chunk, "application/octet-stream")},
    ).status_code == 200
    completed = app_client.post(
        f"/api/v2/mobile/uploads/{session['id']}/complete", headers=ADMIN_HEADERS
    )
    assert completed.status_code == 200
    evidence_id = completed.json()["evidenceId"]
    evidence = app_client.get(f"/api/v2/mobile/evidence/{evidence_id}/content", headers=ADMIN_HEADERS)
    assert evidence.status_code == 200
    assert evidence.content == content

    cancelled_session = app_client.post(
        "/api/v2/mobile/uploads",
        headers=ADMIN_HEADERS,
        json={"fileName": "retry.png", "contentType": "image/png", "totalBytes": 8, "totalChunks": 1},
    ).json()
    cancelled = app_client.delete(
        f"/api/v2/mobile/uploads/{cancelled_session['id']}", headers=ADMIN_HEADERS
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["deletedAt"]
    restored = app_client.post(
        f"/api/v2/mobile/uploads/{cancelled_session['id']}/restore", headers=ADMIN_HEADERS
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "uploading"
    assert restored.json()["deletedAt"] is None
    upload_ledger = app_client.get(
        "/api/v2/mobile/uploads?includeDeleted=true", headers=ADMIN_HEADERS
    )
    assert upload_ledger.status_code == 200
    assert upload_ledger.json()["total"] == 2


def test_v2_mobile_conflicts_can_be_retried_or_discarded(app_client):
    block = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={"blockCode": "V2-MOBILE-CONFLICT", "name": "移动冲突处理林班", "areaMu": 21},
    )
    assert block.status_code == 200, block.text

    def create_task(name: str) -> dict:
        response = app_client.post(
            "/api/v2/patrol/tasks",
            headers=ADMIN_HEADERS,
            json={
                "name": name,
                "priority": "normal",
                "plannedStartAt": "2026-08-11T08:00:00+08:00",
                "plannedEndAt": "2026-08-11T12:00:00+08:00",
                "assigneeName": "v2-admin",
                "linkedBlockCodes": ["V2-MOBILE-CONFLICT"],
                "instructions": "冲突处理验收任务。",
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def make_conflict(task: dict, client_operation_id: str) -> dict:
        stale_version = task["updatedAt"]
        edited = app_client.patch(
            f"/api/v2/patrol/tasks/{task['id']}",
            headers=ADMIN_HEADERS,
            json={"instructions": "服务端已更新，现场提交基于旧版本。"},
        )
        assert edited.status_code == 200, edited.text
        response = app_client.post(
            "/api/v2/mobile/sync",
            headers=ADMIN_HEADERS,
            json={
                "operations": [{
                    "clientOperationId": client_operation_id,
                    "entityType": "patrol",
                    "entityId": task["id"],
                    "action": "accept",
                    "baseVersion": stale_version,
                    "occurredAt": "2026-08-11T08:30:00+08:00",
                    "payload": {},
                }],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()["results"][0]
        assert result["status"] == "conflict"
        assert result["errorCode"] == "version_conflict"
        return result

    retry_task = create_task("移动冲突重试任务")
    retry_conflict = make_conflict(retry_task, "mobile-conflict-retry-0001")
    retried = app_client.post(
        f"/api/v2/mobile/operations/{retry_conflict['id']}/resolve",
        headers=ADMIN_HEADERS,
        json={"strategy": "retry", "note": "现场负责人确认数据有效，按最新版本接单。"},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["operation"]["status"] == "resolved"
    assert retried.json()["retryOperation"]["status"] == "completed"
    retry_task_detail = app_client.get(
        f"/api/v2/patrol/tasks/{retry_task['id']}", headers=ADMIN_HEADERS
    )
    assert retry_task_detail.status_code == 200
    assert retry_task_detail.json()["status"] == "accepted"

    discard_task = create_task("移动冲突放弃任务")
    discard_conflict = make_conflict(discard_task, "mobile-conflict-discard-0001")
    discarded = app_client.post(
        f"/api/v2/mobile/operations/{discard_conflict['id']}/resolve",
        headers=ADMIN_HEADERS,
        json={"strategy": "discard", "note": "现场数据已失效，保留记录后放弃。"},
    )
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["operation"]["status"] == "discarded"
    assert discarded.json()["retryOperation"] is None
    discard_task_detail = app_client.get(
        f"/api/v2/patrol/tasks/{discard_task['id']}", headers=ADMIN_HEADERS
    )
    assert discard_task_detail.status_code == 200
    assert discard_task_detail.json()["status"] == "assigned"

    resolved_ledger = app_client.get(
        "/api/v2/mobile/operations?status=resolved", headers=ADMIN_HEADERS
    )
    discarded_ledger = app_client.get(
        "/api/v2/mobile/operations?status=discarded", headers=ADMIN_HEADERS
    )
    assert resolved_ledger.status_code == discarded_ledger.status_code == 200
    assert any(item["id"] == retry_conflict["id"] for item in resolved_ledger.json()["items"])
    assert any(item["id"] == discard_conflict["id"] for item in discarded_ledger.json()["items"])
