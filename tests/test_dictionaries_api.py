from __future__ import annotations


def test_standard_administrative_division_snapshot_has_four_level_national_coverage():
    from server.modules.dictionaries import standard_administrative_division_seeds

    first = standard_administrative_division_seeds()
    second = standard_administrative_division_seeds()
    by_code = {item["itemCode"]: item for item in first}
    by_identity = {
        (item["levelCode"], item["itemCode"]): item for item in first
    }
    level_counts = {
        level: sum(item["levelCode"] == level for item in first)
        for level in ("province", "city", "county", "town")
    }

    assert first is second
    assert len(first) == 44_706
    assert level_counts == {
        "province": 34,
        "city": 342,
        "county": 2_978,
        "town": 41_352,
    }
    assert len(by_identity) == len(first)
    assert by_code["110000"]["label"] == "北京市"
    assert by_code["440300"]["parentCode"] == "440000"
    assert by_code["440305"]["parentCode"] == "440300"
    assert by_code["440305001"]["parentCode"] == "440305"
    assert by_code["440305001"]["fullName"] == "广东省 / 深圳市 / 南山区 / 南头街道"
    assert by_identity[("city", "441900")]["label"] == "东莞市"
    assert by_identity[("county", "441900")]["label"] == "东莞市"
    assert by_code["440305001"]["metadata"]["referenceYear"] == 2023
    assert by_code["440305001"]["metadata"]["snapshotStatus"] == "historical-public-snapshot"
    assert by_code["710000"]["label"] == "台湾省"
    assert by_code["810000"]["label"] == "香港特别行政区"
    assert by_code["820000"]["label"] == "澳门特别行政区"
    assert by_code["440305001"]["id"] == standard_administrative_division_seeds()[
        first.index(by_code["440305001"])
    ]["id"]


def test_bulk_dictionary_item_save_writes_json_storage_once(monkeypatch):
    from server.modules import dictionaries

    saved: list[list[dict[str, object]]] = []
    monkeypatch.setattr(dictionaries, "use_mysql", lambda: False)
    monkeypatch.setattr(dictionaries, "use_postgis", lambda: False)
    monkeypatch.setattr(dictionaries, "load_all_items", lambda: [])
    monkeypatch.setattr(
        dictionaries,
        "save_json_records",
        lambda _path, records: saved.append(records),
    )

    dictionaries._save_item_records(
        [
            {
                "dictionaryTypeId": "division-type",
                "typeCode": "administrative-divisions",
                "itemCode": "110000",
                "label": "北京市",
            },
            {
                "dictionaryTypeId": "division-type",
                "typeCode": "administrative-divisions",
                "itemCode": "110100",
                "label": "市辖区",
                "parentCode": "110000",
            },
        ]
    )

    assert len(saved) == 1
    assert [item["itemCode"] for item in saved[0]] == ["110000", "110100"]


def sample_dictionary(type_code: str = "maintenance-methods") -> dict[str, object]:
    return {
        "typeCode": type_code,
        "name": "管护方式",
        "category": "forestry",
        "hierarchyEnabled": True,
        "valueMode": "code",
        "description": "竹林管护作业方式",
        "status": "active",
        "sortOrder": 20,
        "systemDefined": False,
    }


def sample_item(
    item_code: str,
    label: str,
    *,
    parent_code: str = "",
    level_code: str = "",
) -> dict[str, object]:
    return {
        "itemCode": item_code,
        "label": label,
        "parentCode": parent_code,
        "levelCode": level_code,
        "fullName": label,
        "searchAliases": [label, item_code],
        "status": "active",
        "sortOrder": 10,
        "metadata": {"sourceNote": "test"},
    }


def test_system_administrative_division_dictionary_is_seeded(app_client):
    response = app_client.get(
        "/api/dictionaries",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )

    assert response.status_code == 200
    body = response.json()
    dictionary = next(
        item
        for item in body["items"]
        if item["typeCode"] == "administrative-divisions"
    )
    assert dictionary["hierarchyEnabled"] is True
    assert dictionary["systemDefined"] is True

    provinces = app_client.get(
        "/api/dictionary-options/administrative-divisions?level=province",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    cities = app_client.get(
        "/api/dictionary-options/administrative-divisions?parentCode=350000",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    counties = app_client.get(
        "/api/dictionary-options/administrative-divisions?parentCode=350700",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )

    assert provinces.status_code == 200
    assert provinces.json()["items"][0]["value"] == "350000"
    assert provinces.json()["items"][0]["label"] == "福建省"
    assert {item["value"] for item in cities.json()["items"]} >= {"350700"}
    assert {item["value"] for item in counties.json()["items"]} >= {"350703"}

    jianyang_towns = app_client.get(
        "/api/dictionary-options/administrative-divisions?parentCode=350703",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    jianou_towns = app_client.get(
        "/api/dictionary-options/administrative-divisions?parentCode=350783",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    masha_villages = app_client.get(
        "/api/dictionary-options/administrative-divisions?parentCode=350703105",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    huangkeng_villages = app_client.get(
        "/api/dictionary-options/administrative-divisions?parentCode=350703106",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    xiaoqiao_villages = app_client.get(
        "/api/dictionary-options/administrative-divisions?parentCode=350783105",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )

    assert {item["value"] for item in counties.json()["items"]} >= {
        "350703",
        "350783",
    }
    assert {item["value"] for item in jianyang_towns.json()["items"]} >= {
        "350703105",
        "350703106",
    }
    assert {item["value"] for item in jianou_towns.json()["items"]} >= {"350783105"}
    assert {item["label"] for item in masha_villages.json()["items"]} >= {
        "杜潭村",
        "溪头村",
    }
    assert {item["label"] for item in huangkeng_villages.json()["items"]} >= {"新峰村"}
    assert {item["label"] for item in xiaoqiao_villages.json()["items"]} >= {"上屯村"}


def test_dictionary_crud_hierarchy_options_and_soft_delete(app_client):
    created = app_client.post(
        "/api/dictionaries",
        json=sample_dictionary(),
        headers={"X-RS-Roles": "system.dictionaries.create"},
    )

    assert created.status_code == 200
    dictionary = created.json()
    assert dictionary["typeCode"] == "maintenance-methods"

    parent = app_client.post(
        "/api/dictionaries/maintenance-methods/items",
        json=sample_item("manual", "人工管护", level_code="method"),
        headers={"X-RS-Roles": "system.dictionaries.create"},
    )
    assert parent.status_code == 200

    child = app_client.post(
        "/api/dictionaries/maintenance-methods/items",
        json=sample_item(
            "manual-weeding",
            "人工除草",
            parent_code="manual",
            level_code="operation",
        ),
        headers={"X-RS-Roles": "system.dictionaries.create"},
    )
    assert child.status_code == 200
    item = child.json()
    assert item["parentCode"] == "manual"

    options = app_client.get(
        "/api/dictionary-options/maintenance-methods"
        "?parentCode=manual&q=%E9%99%A4%E8%8D%89",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    assert options.status_code == 200
    assert options.json()["total"] == 1
    assert options.json()["items"][0] == {
        "value": "manual-weeding",
        "label": "人工除草",
        "parentCode": "manual",
        "levelCode": "operation",
        "fullName": "人工除草",
        "disabled": False,
        "metadata": {"sourceNote": "test"},
    }

    patched = app_client.patch(
        f"/api/dictionaries/maintenance-methods/items/{item['id']}",
        json={"label": "人工割灌", "sortOrder": 30},
        headers={"X-RS-Roles": "system.dictionaries.update"},
    )
    assert patched.status_code == 200
    assert patched.json()["label"] == "人工割灌"

    deleted = app_client.delete(
        f"/api/dictionaries/maintenance-methods/items/{item['id']}",
        headers={"X-RS-Roles": "system.dictionaries.delete"},
    )
    assert deleted.status_code == 200

    hidden = app_client.get(
        "/api/dictionary-options/maintenance-methods?parentCode=manual",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    assert hidden.json()["total"] == 0

    restored = app_client.post(
        f"/api/dictionaries/maintenance-methods/items/{item['id']}/restore",
        headers={"X-RS-Roles": "system.dictionaries.restore"},
    )
    assert restored.status_code == 200
    assert restored.json()["item"]["deletedAt"] is None


def test_dictionary_action_permissions_are_independent(app_client):
    denied_create = app_client.post(
        "/api/dictionaries",
        json=sample_dictionary("permission-test"),
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    created = app_client.post(
        "/api/dictionaries",
        json=sample_dictionary("permission-test"),
        headers={"X-RS-Roles": "system.dictionaries.create"},
    )

    assert denied_create.status_code == 403
    assert "system.dictionaries.create" in denied_create.json()["detail"]
    assert created.status_code == 200

    denied_delete = app_client.delete(
        f"/api/dictionaries/{created.json()['id']}",
        headers={"X-RS-Roles": "system.dictionaries.update"},
    )
    assert denied_delete.status_code == 403
    assert "system.dictionaries.delete" in denied_delete.json()["detail"]


def test_authenticated_module_users_can_read_active_dictionary_options(app_client):
    response = app_client.get(
        "/api/dictionary-options/risk-levels",
        headers={"X-RS-Roles": "forest.blocks.view"},
    )

    assert response.status_code == 200
    assert {item["value"] for item in response.json()["items"]} >= {
        "low",
        "medium",
        "high",
        "critical",
    }


def test_business_enumeration_dictionaries_are_generated_from_backend_field_schemas(app_client):
    dictionaries = app_client.get(
        "/api/dictionaries?q=%E7%AE%A1%E6%8A%A4%E4%BB%BB%E5%8A%A1",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    options = app_client.get(
        "/api/dictionary-options/business-maintenance-tasks-task-type",
        headers={"X-RS-Roles": "business.maintenanceTasks.view"},
    )

    assert dictionaries.status_code == 200
    dictionary = next(
        item
        for item in dictionaries.json()["items"]
        if item["typeCode"] == "business-maintenance-tasks-task-type"
    )
    assert dictionary["category"] == "business"
    assert dictionary["systemDefined"] is True
    assert options.status_code == 200
    assert [(item["value"], item["label"]) for item in options.json()["items"]] == [
        ("patrol", "巡护"),
        ("tending", "抚育"),
        ("fire-prevention", "防火"),
        ("anti-theft", "防盗伐"),
        ("plant-protection", "植保"),
        ("other", "其他"),
    ]


def test_business_dictionary_controls_validation_and_dashboard_labels(app_client):
    type_code = "business-maintenance-tasks-task-type"
    items = app_client.get(
        f"/api/dictionaries/{type_code}/items",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    patrol = next(item for item in items.json()["items"] if item["itemCode"] == "patrol")

    renamed = app_client.patch(
        f"/api/dictionaries/{type_code}/items/{patrol['id']}",
        json={"label": "日常巡护"},
        headers={"X-RS-Roles": "system.dictionaries.update"},
    )
    assert renamed.status_code == 200

    properties = {
        "taskType": "patrol",
        "assignee": "张三",
        "planDate": "2026-07-29",
        "closureStatus": "pending",
    }
    created = app_client.post(
        "/api/business/maintenance-tasks",
        json={
            "recordCode": "TASK-DICTIONARY-001",
            "name": "山区日常巡护",
            "status": "active",
            "properties": properties,
        },
        headers={"X-RS-Roles": "business.maintenanceTasks.create"},
    )
    assert created.status_code == 200

    dashboard = app_client.get("/api/business/maintenance-tasks/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["rows"][0][1] == "日常巡护"

    deleted = app_client.delete(
        f"/api/dictionaries/{type_code}/items/{patrol['id']}",
        headers={"X-RS-Roles": "system.dictionaries.delete"},
    )
    assert deleted.status_code == 200

    historical_update = app_client.patch(
        f"/api/business/maintenance-tasks/{created.json()['id']}",
        json={"properties": {**properties, "assignee": "李四"}},
        headers={"X-RS-Roles": "business.maintenanceTasks.update"},
    )
    assert historical_update.status_code == 200
    assert historical_update.json()["properties"]["taskType"] == "patrol"

    rejected = app_client.post(
        "/api/business/maintenance-tasks",
        json={
            "recordCode": "TASK-DICTIONARY-002",
            "name": "停用词项新任务",
            "status": "active",
            "properties": properties,
        },
        headers={"X-RS-Roles": "business.maintenanceTasks.create"},
    )
    assert rejected.status_code == 422
    assert "taskType" in rejected.json()["detail"]

    historical_dashboard = app_client.get("/api/business/maintenance-tasks/dashboard")
    assert historical_dashboard.status_code == 200
    assert historical_dashboard.json()["rows"][0][1] == "日常巡护"


def test_administrative_divisions_are_derived_idempotently_from_forest_blocks(app_client):
    block = app_client.post(
        "/api/forest-blocks",
        headers={"X-RS-Roles": "forest.blocks.create"},
        json={
            "blockCode": "DICT-DIVISION-001",
            "name": "区划同步测试林班",
            "countyCode": "350784",
            "countyName": "武夷山市",
            "townCode": "350784102",
            "townName": "星村镇",
            "villageCode": "350784102201",
            "villageName": "星村村",
            "areaMu": 12.5,
        },
    )
    assert block.status_code == 200

    from server.modules.dictionaries import sync_administrative_divisions_from_blocks

    first = sync_administrative_divisions_from_blocks()
    second = sync_administrative_divisions_from_blocks()

    assert first["created"] == 0
    assert second["created"] == 0
    towns = app_client.get(
        "/api/dictionary-options/administrative-divisions?parentCode=350784",
        headers={"X-RS-Roles": "forest.blocks.view"},
    )
    villages = app_client.get(
        "/api/dictionary-options/administrative-divisions?parentCode=350784102",
        headers={"X-RS-Roles": "forest.blocks.view"},
    )
    assert towns.status_code == 200
    assert towns.json()["items"][0]["value"] == "350784102"
    assert towns.json()["items"][0]["label"] == "星村镇"
    assert villages.json()["items"][0]["value"] == "350784102201"
    assert villages.json()["items"][0]["label"] == "星村村"


def test_derived_divisions_refresh_until_manually_curated(app_client):
    from server.modules.dictionaries import sync_administrative_divisions_from_blocks

    def block(town_name: str) -> dict[str, object]:
        return {
            "countyCode": "350703",
            "countyName": "建阳区",
            "townCode": "350703998",
            "townName": town_name,
        }

    first = sync_administrative_divisions_from_blocks([block("待校正乡镇")])
    corrected = sync_administrative_divisions_from_blocks([block("校正后乡镇")])

    assert first["created"] == 1
    assert corrected["updated"] == 1
    items = app_client.get(
        "/api/dictionaries/administrative-divisions/items?level=town&limit=500",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    derived = next(item for item in items.json()["items"] if item["itemCode"] == "350703998")
    assert derived["label"] == "校正后乡镇"
    assert derived["metadata"]["curated"] is False

    curated = app_client.patch(
        f"/api/dictionaries/administrative-divisions/items/{derived['id']}",
        json={"label": "人工确认乡镇", "fullName": "福建省 / 南平市 / 建阳区 / 人工确认乡镇"},
        headers={"X-RS-Roles": "system.dictionaries.update"},
    )
    assert curated.status_code == 200
    assert curated.json()["metadata"]["curated"] is True

    after_manual_edit = sync_administrative_divisions_from_blocks([block("不应覆盖人工名称")])
    assert after_manual_edit["updated"] == 0
    final_items = app_client.get(
        "/api/dictionaries/administrative-divisions/items?level=town&limit=500",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    final = next(item for item in final_items.json()["items"] if item["itemCode"] == "350703998")
    assert final["label"] == "人工确认乡镇"


def test_dictionary_import_previews_commits_and_upserts(app_client):
    created = app_client.post(
        "/api/dictionaries",
        json=sample_dictionary("import-methods"),
        headers={"X-RS-Roles": "system.dictionaries.create"},
    )
    assert created.status_code == 200
    payload = {
        "mode": "append",
        "dryRun": True,
        "items": [
            sample_item(
                "manual-weeding",
                "人工除草",
                parent_code="manual",
                level_code="operation",
            ),
            sample_item("manual", "人工管护", level_code="method"),
        ],
    }

    preview = app_client.post(
        "/api/dictionaries/import-methods/imports",
        json=payload,
        headers={"X-RS-Roles": "system.dictionaries.import"},
    )
    assert preview.status_code == 200
    assert preview.json()["canCommit"] is True
    assert preview.json()["created"] == 2

    committed = app_client.post(
        "/api/dictionaries/import-methods/imports",
        json={**payload, "dryRun": False},
        headers={"X-RS-Roles": "system.dictionaries.import"},
    )
    assert committed.status_code == 200
    assert committed.json()["committed"] == 2

    upsert = app_client.post(
        "/api/dictionaries/import-methods/imports",
        json={
            "mode": "upsert",
            "dryRun": False,
            "items": [sample_item("manual", "人工抚育", level_code="method")],
        },
        headers={"X-RS-Roles": "system.dictionaries.import"},
    )
    assert upsert.status_code == 200
    assert upsert.json()["updated"] == 1
    items = app_client.get(
        "/api/dictionaries/import-methods/items",
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    assert {item["label"] for item in items.json()["items"]} >= {"人工抚育", "人工除草"}


def test_dictionary_import_requires_permission_and_rejects_duplicates(app_client):
    created = app_client.post(
        "/api/dictionaries",
        json=sample_dictionary("import-permission"),
        headers={"X-RS-Roles": "system.dictionaries.create"},
    )
    assert created.status_code == 200
    payload = {
        "mode": "append",
        "dryRun": True,
        "items": [
            sample_item("same", "第一行", level_code="method"),
            sample_item("same", "第二行", level_code="method"),
        ],
    }
    denied = app_client.post(
        "/api/dictionaries/import-permission/imports",
        json=payload,
        headers={"X-RS-Roles": "system.dictionaries.view"},
    )
    preview = app_client.post(
        "/api/dictionaries/import-permission/imports",
        json=payload,
        headers={"X-RS-Roles": "system.dictionaries.import"},
    )

    assert denied.status_code == 403
    assert preview.status_code == 200
    assert preview.json()["canCommit"] is False
    assert preview.json()["errors"][0]["row"] == 3
