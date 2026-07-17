from __future__ import annotations

import importlib

import pytest

from server.modules.auth import AuthContext
from tests.test_forest_blocks import FakeCursor, install_fake_psycopg


BUSINESS_ENDPOINTS = [
    "/api/business/farmers",
    "/api/business/cooperatives",
    "/api/business/enterprises",
    "/api/business/plant-protection-events",
    "/api/business/materials",
    "/api/business/policies",
    "/api/business/stewardship-agreements",
    "/api/business/franchise-bases",
    "/api/business/maintenance-tasks",
    "/api/business/work-logs",
    "/api/business/drone-tasks",
    "/api/business/equipment",
    "/api/business/pest-warnings",
    "/api/business/material-services",
    "/api/business/yield-forecasts",
    "/api/business/harvest-plans",
    "/api/business/income-estimates",
    "/api/business/performance-dashboards",
    "/api/business/carbon-estimates",
    "/api/business/trade-matches",
    "/api/business/logistics-traces",
    "/api/business/product-qrcodes",
    "/api/business/supply-chain-finance",
    "/api/business/price-indexes",
    "/api/business/mobile-service-channels",
]

OPERATIONS_MODULES = {
    "stewardship-agreements": "business.stewardshipAgreements.manage",
    "franchise-bases": "business.franchiseBases.manage",
    "maintenance-tasks": "business.maintenanceTasks.manage",
    "work-logs": "business.workLogs.manage",
    "drone-tasks": "business.droneTasks.manage",
    "equipment": "business.equipment.manage",
    "pest-warnings": "business.pestWarnings.manage",
    "material-services": "business.materialServices.manage",
}

DECISION_MODULES = {
    "yield-forecasts": "business.yieldForecasts.manage",
    "harvest-plans": "business.harvestPlans.manage",
    "income-estimates": "business.incomeEstimates.manage",
    "performance-dashboards": "business.performanceDashboards.manage",
    "carbon-estimates": "business.carbonEstimates.manage",
}

INDUSTRY_PLATFORM_MODULES = {
    "trade-matches": "business.tradeMatches.manage",
    "logistics-traces": "business.logisticsTraces.manage",
    "product-qrcodes": "business.productQrcodes.manage",
    "supply-chain-finance": "business.supplyChainFinance.manage",
    "price-indexes": "business.priceIndexes.manage",
    "mobile-service-channels": "business.mobileServiceChannels.manage",
}
CORE_MODULES = {
    "farmers": "business.farmers.manage",
    "cooperatives": "business.cooperatives.manage",
    "enterprises": "business.enterprises.manage",
    "plant-protection-events": "business.plantProtection.manage",
    "materials": "business.materials.manage",
    "policies": "business.policies.manage",
}
ALL_BUSINESS_MODULES = {
    **CORE_MODULES,
    **OPERATIONS_MODULES,
    **DECISION_MODULES,
    **INDUSTRY_PLATFORM_MODULES,
}


def business_permission(module_key: str, action: str) -> str:
    return ALL_BUSINESS_MODULES[module_key].removesuffix(".manage") + f".{action}"


def endpoint_permission(endpoint: str, action: str) -> str:
    return business_permission(endpoint.rsplit("/", 1)[-1], action)


def sample_business_record(code: str = "REC-001") -> dict[str, object]:
    return {
        "recordCode": code,
        "name": "Xiaoqiao linked record",
        "status": "active",
        "linkedBlockCodes": ["BLOCK-001"],
        "linkedRightArchiveCodes": ["CERT-001"],
        "properties": {"ownerPhone": "13800000000"},
    }


def sample_map_layer_payload(code: str = "LAYER-QUALITY") -> dict[str, object]:
    return {
        "recordCode": code,
        "name": "质量等级",
        "status": "published",
        "layerType": "quality",
        "dataSource": "forest-blocks",
        "style": {"color": "#58ffa8"},
        "zIndex": 22,
        "visibleOnDashboard": True,
        "linkedBlockCodes": ["BLOCK-001"],
        "linkedRightArchiveCodes": ["ARCH-001"],
        "properties": {"legend": "quality"},
    }


def postgis_map_layer_row(code: str = "LAYER-PG-001") -> dict[str, object]:
    return {
        "id": "7ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        "record_code": code,
        "name": "PostGIS layer",
        "status": "published",
        "layer_type": "quality",
        "data_source": "forest-blocks",
        "style": {"color": "#58ffa8"},
        "z_index": 22,
        "visible_on_dashboard": True,
        "linked_block_codes": ["BLOCK-PG-001"],
        "linked_right_archive_codes": ["ARCH-PG-001"],
        "properties": {"legend": "quality"},
        "created_at": "2026-07-07T00:00:00+00:00",
        "updated_at": "2026-07-07T00:00:00+00:00",
        "deleted_at": None,
    }


def postgis_business_row(
    module_key: str = "farmers",
    code: str = "FARMER-PG-001",
) -> dict[str, object]:
    return {
        "id": "6ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        "module_key": module_key,
        "record_code": code,
        "name": "PostGIS farmer",
        "status": "active",
        "linked_block_codes": ["BLOCK-PG-001"],
        "linked_right_archive_codes": ["ARCH-PG-001"],
        "properties": {"ownerPhone": "13800000000"},
        "payload": {
            "townName": "Masha",
            "villageName": "Xinfeng",
            "serviceArea": "Masha / Xinfeng",
        },
        "created_at": "2026-07-07T00:00:00+00:00",
        "updated_at": "2026-07-07T00:00:00+00:00",
        "deleted_at": None,
    }


def reload_business_module(reload_platform_modules):
    reload_platform_modules()
    import server.modules.business as business_module

    importlib.reload(business_module)
    return business_module


@pytest.mark.parametrize("endpoint", BUSINESS_ENDPOINTS)
def test_business_module_crud_search_filter_and_soft_delete(app_client, endpoint):
    created = app_client.post(
        endpoint,
        json=sample_business_record(),
        headers={"X-RS-Roles": "admin"},
    )

    assert created.status_code == 200
    item = created.json()
    assert item["recordCode"] == "REC-001"
    assert item["linkedBlockCodes"] == ["BLOCK-001"]

    view_headers = {"X-RS-Roles": endpoint_permission(endpoint, "view")}
    searched = app_client.get(f"{endpoint}?q=ownerPhone", headers=view_headers)
    linked = app_client.get(f"{endpoint}?linkedBlockCode=BLOCK-001", headers=view_headers)
    missing_link = app_client.get(f"{endpoint}?linkedBlockCode=BLOCK-404", headers=view_headers)

    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert linked.json()["total"] == 1
    assert missing_link.json()["total"] == 0

    patched = app_client.patch(
        f"{endpoint}/{item['id']}",
        json={"status": "paused", "name": "Updated record"},
        headers={"X-RS-Roles": "admin"},
    )

    assert patched.status_code == 200
    assert patched.json()["status"] == "paused"
    assert patched.json()["name"] == "Updated record"

    deleted = app_client.delete(
        f"{endpoint}/{item['id']}",
        headers={"X-RS-Roles": "admin"},
    )
    listed_after_delete = app_client.get(endpoint, headers=view_headers)

    assert deleted.status_code == 200
    assert listed_after_delete.status_code == 200
    assert listed_after_delete.json()["total"] == 0


def test_deleted_business_record_can_be_listed_and_restored(app_client):
    created = app_client.post(
        "/api/business/farmers",
        json=sample_business_record("FARMER-RESTORE-001"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    record_id = created.json()["id"]

    deleted = app_client.delete(
        f"/api/business/farmers/{record_id}",
        headers={"X-RS-Roles": "admin"},
    )
    hidden = app_client.get(
        "/api/business/farmers?q=FARMER-RESTORE-001",
        headers={"X-RS-Roles": "business.farmers.view"},
    )
    deleted_list = app_client.get(
        "/api/business/farmers?q=FARMER-RESTORE-001&includeDeleted=true",
        headers={"X-RS-Roles": "business.farmers.restore"},
    )
    denied_restore = app_client.post(
        f"/api/business/farmers/{record_id}/restore",
        headers={"X-RS-Roles": "business.cooperatives.manage"},
    )
    restored = app_client.post(
        f"/api/business/farmers/{record_id}/restore",
        headers={"X-RS-Roles": "admin"},
    )
    active_again = app_client.get(
        "/api/business/farmers?q=FARMER-RESTORE-001",
        headers={"X-RS-Roles": "business.farmers.view"},
    )

    assert deleted.status_code == 200
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0
    assert deleted_list.status_code == 200
    assert deleted_list.json()["total"] == 1
    assert deleted_list.json()["items"][0]["deletedAt"]
    assert denied_restore.status_code == 403
    assert "business.farmers.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    assert restored.json()["ok"] is True
    assert restored.json()["restored"] == record_id
    assert restored.json()["item"]["deletedAt"] is None
    assert active_again.status_code == 200
    assert active_again.json()["total"] == 1


def test_operations_modules_expose_typed_field_schemas(app_client):
    response = app_client.get("/api/business/modules", headers={"X-RS-Roles": "admin"})

    assert response.status_code == 200
    modules = {item["key"]: item for item in response.json()["items"]}
    maintenance_fields = {item["key"]: item for item in modules["maintenance-tasks"]["fieldSchema"]}
    work_log_fields = {item["key"]: item for item in modules["work-logs"]["fieldSchema"]}

    assert maintenance_fields["taskType"]["inputType"] == "select"
    assert maintenance_fields["planDate"]["inputType"] == "date"
    assert maintenance_fields["closureStatus"]["options"]
    assert work_log_fields["laborCount"]["inputType"] == "integer"
    assert work_log_fields["laborCount"]["min"] == 0


def test_operations_core_fields_are_typed_and_enum_values_are_validated(app_client):
    created = app_client.post(
        "/api/business/work-logs",
        json={
            "recordCode": "WORK-TYPED-001",
            "name": "黄坑施肥作业",
            "status": "active",
            "linkedBlockCodes": [],
            "properties": {
                "workStage": "fertilizing",
                "worker": "一组",
                "workDate": "2026-07-15",
                "laborCount": "12",
            },
        },
        headers={"X-RS-Roles": "admin"},
    )
    invalid = app_client.post(
        "/api/business/maintenance-tasks",
        json={
            "recordCode": "TASK-TYPED-INVALID",
            "name": "无效闭环状态",
            "status": "active",
            "properties": {"closureStatus": "not-a-real-status"},
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert created.status_code == 200
    assert created.json()["properties"]["laborCount"] == 12
    assert created.json()["properties"]["workDate"] == "2026-07-15"
    assert invalid.status_code == 422
    assert "closureStatus" in invalid.json()["detail"]


def test_operations_records_can_filter_by_typed_core_field(app_client):
    for code, stage in [("WORK-FILTER-001", "fertilizing"), ("WORK-FILTER-002", "transport")]:
        response = app_client.post(
            "/api/business/work-logs",
            json={
                "recordCode": code,
                "name": code,
                "status": "active",
                "properties": {"workStage": stage},
            },
            headers={"X-RS-Roles": "admin"},
        )
        assert response.status_code == 200

    filtered = app_client.get(
        "/api/business/work-logs?fieldKey=workStage&fieldValue=fertilizing",
        headers={"X-RS-Roles": "business.workLogs.view"},
    )

    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["recordCode"] == "WORK-FILTER-001"


def test_operations_dashboard_rows_and_metrics_use_module_core_fields(app_client):
    for code, closure_status in [("TASK-DASH-001", "pending"), ("TASK-DASH-002", "completed")]:
        created = app_client.post(
            "/api/business/maintenance-tasks",
            json={
                "recordCode": code,
                "name": code,
                "status": "active",
                "linkedBlockCodes": ["BLOCK-001"],
                "properties": {
                    "taskType": "patrol",
                    "assignee": "巡护组",
                    "planDate": "2026-07-15",
                    "closureStatus": closure_status,
                },
            },
            headers={"X-RS-Roles": "admin"},
        )
        assert created.status_code == 200

    dashboard = app_client.get("/api/business/maintenance-tasks/dashboard")

    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["columns"] == ["任务名称", "任务类型", "涉及林班", "处理状态"]
    assert all(len(row) == len(body["columns"]) for row in body["rows"])
    assert body["rows"][0][1] == "巡护"
    assert {row[3] for row in body["rows"]} == {"待处理", "已完成"}
    assert ["待处理", "1"] in body["metrics"]


def test_decision_modules_expose_numeric_models_and_calculate_income(app_client):
    modules_response = app_client.get("/api/business/modules", headers={"X-RS-Roles": "admin"})
    modules = {item["key"]: item for item in modules_response.json()["items"]}
    yield_fields = {item["key"]: item for item in modules["yield-forecasts"]["fieldSchema"]}
    income_fields = {item["key"]: item for item in modules["income-estimates"]["fieldSchema"]}

    created = app_client.post(
        "/api/business/income-estimates",
        json={
            "recordCode": "INCOME-CALC-001",
            "name": "黄坑年度收益测算",
            "status": "active",
            "properties": {
                "estimateType": "net-income",
                "estimatePeriod": "2026",
                "expectedIncome": "1250000.50",
                "cost": "420000.25",
            },
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert modules_response.status_code == 200
    assert yield_fields["forecastYield"]["inputType"] == "number"
    assert yield_fields["forecastYield"]["unit"] == "吨"
    assert income_fields["netIncome"]["readOnly"] is True
    assert created.status_code == 200
    assert created.json()["properties"]["expectedIncome"] == 1250000.5
    assert created.json()["properties"]["cost"] == 420000.25
    assert created.json()["properties"]["netIncome"] == 830000.25


def test_decision_dashboard_aggregates_numeric_core_fields(app_client):
    for code, forecast_yield, status in [
        ("YIELD-AGG-001", 120.5, "published"),
        ("YIELD-AGG-002", 79.5, "draft"),
    ]:
        created = app_client.post(
            "/api/business/yield-forecasts",
            json={
                "recordCode": code,
                "name": code,
                "status": status,
                "linkedBlockCodes": ["BLOCK-001"],
                "properties": {
                    "forecastObject": "bamboo-timber",
                    "forecastPeriod": "2026-Q3",
                    "forecastYield": forecast_yield,
                    "modelName": "竹材产量模型 V1",
                },
            },
            headers={"X-RS-Roles": "admin"},
        )
        assert created.status_code == 200

    dashboard = app_client.get("/api/business/yield-forecasts/dashboard")
    body = dashboard.json()

    assert dashboard.status_code == 200
    assert all(len(row) == len(body["columns"]) for row in body["rows"])
    assert body["rows"][0][1] == "竹材"
    assert ["预测产量", "200 吨"] in body["metrics"]
    assert body["aggregates"]["forecastYield"] == 200


def test_industry_modules_expose_typed_models_and_generate_trace_code(app_client):
    modules_response = app_client.get("/api/business/modules", headers={"X-RS-Roles": "admin"})
    modules = {item["key"]: item for item in modules_response.json()["items"]}
    finance_fields = {item["key"]: item for item in modules["supply-chain-finance"]["fieldSchema"]}
    price_fields = {item["key"]: item for item in modules["price-indexes"]["fieldSchema"]}

    finance = app_client.post(
        "/api/business/supply-chain-finance",
        json={
            "recordCode": "FINANCE-001",
            "name": "合作社订单融资",
            "status": "active",
            "properties": {
                "financeProduct": "order-finance",
                "borrower": "黄坑合作社",
                "amount": "500000.75",
                "reviewStatus": "review",
            },
        },
        headers={"X-RS-Roles": "admin"},
    )
    qr_record = app_client.post(
        "/api/business/product-qrcodes",
        json={
            "recordCode": "QR-TRACE-001",
            "name": "黄坑竹材批次码",
            "status": "active",
            "properties": {"productType": "bamboo-timber", "batchNo": "BATCH-001"},
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert finance_fields["amount"]["inputType"] == "number"
    assert price_fields["price"]["unit"] == "元/吨"
    assert finance.status_code == 200
    assert finance.json()["properties"]["amount"] == 500000.75
    assert qr_record.status_code == 200
    assert qr_record.json()["properties"]["qrCode"] == "SB-QR-TRACE-001"
    assert qr_record.json()["properties"]["scanCount"] == 0


def test_industry_dashboard_uses_module_rows_statuses_and_numeric_aggregates(app_client):
    for code, price, publish_status in [
        ("PRICE-001", 510.0, "published"),
        ("PRICE-002", 530.0, "published"),
    ]:
        created = app_client.post(
            "/api/business/price-indexes",
            json={
                "recordCode": code,
                "name": code,
                "status": "active",
                "properties": {
                    "productType": "bamboo-timber",
                    "region": "建瓯市",
                    "price": price,
                    "period": "2026-07",
                    "publishStatus": publish_status,
                },
            },
            headers={"X-RS-Roles": "admin"},
        )
        assert created.status_code == 200

    module_dashboard = app_client.get("/api/business/price-indexes/dashboard")
    platform_dashboard = app_client.get("/api/industry-platform/dashboard")

    assert module_dashboard.status_code == 200
    module_body = module_dashboard.json()
    assert all(len(row) == len(module_body["columns"]) for row in module_body["rows"])
    assert ["平均价格", "520 元/吨"] in module_body["metrics"]
    assert module_body["aggregates"]["price"] == 520
    assert platform_dashboard.status_code == 200
    price_rows = [row for row in platform_dashboard.json()["rows"] if row[0] == "价格指数"]
    assert price_rows
    assert all(row[3] == "已发布" for row in price_rows)


def test_every_business_module_has_a_backend_owned_typed_field_schema(app_client):
    response = app_client.get("/api/business/modules", headers={"X-RS-Roles": "admin"})

    assert response.status_code == 200
    modules = response.json()["items"]
    assert len(modules) == len(ALL_BUSINESS_MODULES)
    assert all(module.get("fieldSchema") for module in modules)
    assert all(
        field.get("key") and field.get("label") and field.get("inputType")
        for module in modules
        for field in module["fieldSchema"]
    )


def test_core_business_dashboard_reads_typed_properties_instead_of_flat_demo_fields(app_client):
    created = app_client.post(
        "/api/business/farmers",
        json={
            "recordCode": "FARMER-MODEL-001",
            "name": "谭立广",
            "status": "active",
            "linkedBlockCodes": ["BLOCK-001"],
            "properties": {
                "townVillage": "小桥镇上屯村",
                "phone": "13800000000",
                "managedAreaMu": 195,
            },
        },
        headers={"X-RS-Roles": "admin"},
    )
    dashboard = app_client.get("/api/business/farmers/dashboard")

    assert created.status_code == 200
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["rows"][0] == ["谭立广", "小桥镇上屯村", "BLOCK-001", "active"]
    assert ["经营面积", "195 亩"] in body["metrics"]


def test_business_module_crud_actions_use_separate_permissions(app_client):
    denied_create = app_client.post(
        "/api/business/farmers",
        json=sample_business_record("FARMER-ACTION-DENIED"),
        headers={"X-RS-Roles": "business.farmers.view"},
    )
    created = app_client.post(
        "/api/business/farmers",
        json=sample_business_record("FARMER-ACTION-001"),
        headers={"X-RS-Roles": "business.farmers.create"},
    )
    assert denied_create.status_code == 403
    assert "business.farmers.create" in denied_create.json()["detail"]
    assert created.status_code == 200
    record_id = created.json()["id"]

    listed = app_client.get(
        "/api/business/farmers?q=FARMER-ACTION-001",
        headers={"X-RS-Roles": "business.farmers.view"},
    )
    denied_update = app_client.patch(
        f"/api/business/farmers/{record_id}",
        json={"status": "paused"},
        headers={"X-RS-Roles": "business.farmers.view"},
    )
    updated = app_client.patch(
        f"/api/business/farmers/{record_id}",
        json={"status": "paused"},
        headers={"X-RS-Roles": "business.farmers.update"},
    )
    deleted = app_client.delete(
        f"/api/business/farmers/{record_id}",
        headers={"X-RS-Roles": "business.farmers.delete"},
    )
    denied_deleted_list = app_client.get(
        "/api/business/farmers?q=FARMER-ACTION-001&includeDeleted=true",
        headers={"X-RS-Roles": "business.farmers.view"},
    )
    deleted_list = app_client.get(
        "/api/business/farmers?q=FARMER-ACTION-001&includeDeleted=true",
        headers={"X-RS-Roles": "business.farmers.restore"},
    )
    restored = app_client.post(
        f"/api/business/farmers/{record_id}/restore",
        headers={"X-RS-Roles": "business.farmers.restore"},
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert denied_update.status_code == 403
    assert "business.farmers.update" in denied_update.json()["detail"]
    assert updated.status_code == 200
    assert updated.json()["status"] == "paused"
    assert deleted.status_code == 200
    assert denied_deleted_list.status_code == 403
    assert "business.farmers.restore" in denied_deleted_list.json()["detail"]
    assert deleted_list.status_code == 200
    assert deleted_list.json()["total"] == 1
    assert restored.status_code == 200
    assert restored.json()["ok"] is True


def test_business_record_events_can_be_listed_across_crud_lifecycle(app_client):
    created = app_client.post(
        "/api/business/farmers",
        json=sample_business_record("FARMER-EVENTS-001"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    assert created.status_code == 200
    assert created.json()["properties"]["auditEvents"][-1]["action"] == "create"
    record_id = created.json()["id"]

    patched = app_client.patch(
        f"/api/business/farmers/{record_id}",
        json={"status": "paused", "name": "Events farmer updated"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )
    deleted = app_client.delete(
        f"/api/business/farmers/{record_id}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "carol"},
    )
    restored = app_client.post(
        f"/api/business/farmers/{record_id}/restore",
        headers={"X-RS-Roles": "admin", "X-RS-User": "dave"},
    )
    denied = app_client.get(
        "/api/business/farmers/events",
        headers={"X-RS-Roles": "business.cooperatives.manage"},
    )
    listed = app_client.get("/api/business/farmers/events?limit=20", headers={"X-RS-Roles": "business.farmers.view"})
    update_only = app_client.get(
        f"/api/business/farmers/events?action=update&recordId={record_id}&q=bob",
        headers={"X-RS-Roles": "business.farmers.view"},
    )
    linked_only = app_client.get(
        "/api/business/farmers/events?linkedBlockCode=BLOCK-001",
        headers={"X-RS-Roles": "business.farmers.view"},
    )

    assert patched.status_code == 200
    assert patched.json()["properties"]["auditEvents"][-1]["changedFields"] == ["name", "status"]
    assert deleted.status_code == 200
    assert restored.status_code == 200
    assert denied.status_code == 403
    assert "business.farmers.view" in denied.json()["detail"]
    assert listed.status_code == 200
    body = listed.json()
    assert body["limit"] == 20
    assert body["total"] == 4
    assert {item["action"] for item in body["items"]} == {"create", "update", "delete", "restore"}
    update_event = next(item for item in body["items"] if item["action"] == "update")
    assert update_event["eventId"]
    assert update_event["module"] == "farmers"
    assert update_event["recordId"] == record_id
    assert update_event["recordCode"] == "FARMER-EVENTS-001"
    assert update_event["recordName"] == "Events farmer updated"
    assert update_event["actor"] == "bob"
    assert update_event["status"] == "paused"
    assert update_event["linkedBlockCodes"] == ["BLOCK-001"]
    assert update_event["changedFields"] == ["name", "status"]
    assert update_event["adminHref"] == "admin-farmers.html"
    assert update_event["summary"] == "update: FARMER-EVENTS-001"
    assert update_only.status_code == 200
    assert update_only.json()["total"] == 1
    assert update_only.json()["items"][0]["action"] == "update"
    assert linked_only.status_code == 200
    assert linked_only.json()["total"] == 4


def test_business_record_events_can_be_exported_with_module_export_permission(app_client):
    created = app_client.post(
        "/api/business/farmers",
        json=sample_business_record("FARMER-EVENT-EXPORT-001"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    assert created.status_code == 200

    denied = app_client.get(
        "/api/business/farmers/events.csv?recordCode=FARMER-EVENT-EXPORT-001",
        headers={"X-RS-Roles": "business.farmers.view"},
    )
    exported = app_client.get(
        "/api/business/farmers/events.csv?recordCode=FARMER-EVENT-EXPORT-001",
        headers={"X-RS-Roles": "business.farmers.export"},
    )

    assert denied.status_code == 403
    assert "business.farmers.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "business-farmers-events.csv" in exported.headers["content-disposition"]
    assert "recordCode" in exported.text
    assert "FARMER-EVENT-EXPORT-001" in exported.text
    assert "alice" in exported.text


def test_business_dashboard_uses_real_records_not_static_defaults(app_client):
    app_client.post(
        "/api/business/farmers",
        json={
            **sample_business_record("FARMER-001"),
            "name": "Wei Sihua",
            "townName": "Xiaoqiao",
            "villageName": "Shangtun",
        },
        headers={"X-RS-Roles": "admin"},
    )

    dashboard = app_client.get("/api/business/farmers/dashboard")

    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["module"] == "farmers"
    assert body["metrics"][0] == ["竹农总数", "1 户"]
    assert body["rows"] == [["Wei Sihua", "Xiaoqiao / Shangtun", "BLOCK-001", "active"]]


def test_business_dashboard_exposes_independent_admin_page(app_client):
    dashboard = app_client.get("/api/business/farmers/dashboard")

    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["adminHref"] == "admin-farmers.html"
    assert body["adminLinks"][0]["href"] == "admin-farmers.html"


@pytest.mark.parametrize(("module_key", "permission"), sorted(OPERATIONS_MODULES.items()))
def test_operations_module_permissions_are_module_specific(app_client, module_key: str, permission: str):
    endpoint = f"/api/business/{module_key}"
    allowed = app_client.post(
        endpoint,
        json=sample_business_record(f"OPS-{module_key}"),
        headers={"X-RS-Roles": permission},
    )
    denied = app_client.post(
        endpoint,
        json=sample_business_record(f"DENIED-{module_key}"),
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    dashboard = app_client.get(f"{endpoint}/dashboard")

    assert allowed.status_code == 200
    assert allowed.json()["recordCode"] == f"OPS-{module_key}"
    assert denied.status_code == 403
    assert business_permission(module_key, "create") in denied.json()["detail"]
    assert dashboard.status_code == 200
    assert dashboard.json()["module"] == module_key


@pytest.mark.parametrize(("module_key", "permission"), sorted(DECISION_MODULES.items()))
def test_decision_module_permissions_are_module_specific(app_client, module_key: str, permission: str):
    endpoint = f"/api/business/{module_key}"
    allowed = app_client.post(
        endpoint,
        json=sample_business_record(f"DECISION-{module_key}"),
        headers={"X-RS-Roles": permission},
    )
    denied = app_client.post(
        endpoint,
        json=sample_business_record(f"DENIED-{module_key}"),
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    dashboard = app_client.get(f"{endpoint}/dashboard")

    assert allowed.status_code == 200
    assert allowed.json()["recordCode"] == f"DECISION-{module_key}"
    assert denied.status_code == 403
    assert business_permission(module_key, "create") in denied.json()["detail"]
    assert dashboard.status_code == 200
    assert dashboard.json()["module"] == module_key


@pytest.mark.parametrize(("module_key", "permission"), sorted(INDUSTRY_PLATFORM_MODULES.items()))
def test_industry_platform_module_permissions_are_module_specific(app_client, module_key: str, permission: str):
    endpoint = f"/api/business/{module_key}"
    allowed = app_client.post(
        endpoint,
        json=sample_business_record(f"INDUSTRY-{module_key}"),
        headers={"X-RS-Roles": permission},
    )
    denied = app_client.post(
        endpoint,
        json=sample_business_record(f"DENIED-{module_key}"),
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    dashboard = app_client.get(f"{endpoint}/dashboard")

    assert allowed.status_code == 200
    assert allowed.json()["recordCode"] == f"INDUSTRY-{module_key}"
    assert denied.status_code == 403
    assert business_permission(module_key, "create") in denied.json()["detail"]
    assert dashboard.status_code == 200
    assert dashboard.json()["module"] == module_key


def test_industry_platform_dashboard_aggregates_real_backend_records(app_client):
    app_client.post(
        "/api/business/trade-matches",
        json={
            **sample_business_record("TRADE-001"),
            "name": "鲜笋订单撮合",
            "status": "open",
        },
        headers={"X-RS-Roles": "admin"},
    )
    app_client.post(
        "/api/business/logistics-traces",
        json={
            **sample_business_record("TRACE-001"),
            "name": "黄坑鲜笋冷链批次",
            "status": "published",
            "linkedBlockCodes": ["BLOCK-002"],
        },
        headers={"X-RS-Roles": "admin"},
    )

    dashboard = app_client.get("/api/industry-platform/dashboard")

    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["module"] == "industry-platform"
    assert body["title"] == "产业平台信息卡"
    assert body["metrics"][0] == ["产业模块", "6 个"]
    assert body["metrics"][1] == ["业务记录", "2 条"]
    assert body["columns"] == ["模块", "记录名称", "关联林班", "状态"]
    assert ["交易撮合", "鲜笋订单撮合", "BLOCK-001", "open"] in body["rows"]
    assert ["物流溯源", "黄坑鲜笋冷链批次", "BLOCK-002", "published"] in body["rows"]
    assert [module["module"] for module in body["modules"]] == [
        "trade-matches",
        "logistics-traces",
        "product-qrcodes",
        "supply-chain-finance",
        "price-indexes",
        "mobile-service-channels",
    ]
    assert [link["href"] for link in body["adminLinks"]] == [
        "admin-trade-matches.html",
        "admin-logistics-traces.html",
        "admin-product-qrcodes.html",
        "admin-supply-chain-finance.html",
        "admin-price-indexes.html",
        "admin-mobile-service-channels.html",
    ]


def test_map_layers_crud_and_published_filter(app_client):
    created = app_client.post(
        "/api/map-layers",
        json=sample_map_layer_payload(),
        headers={"X-RS-Roles": "admin"},
    )

    assert created.status_code == 200
    assert created.json()["visibleOnDashboard"] is True

    listed = app_client.get("/api/map-layers?status=published&linkedBlockCode=BLOCK-001")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["recordCode"] == "LAYER-QUALITY"


def test_map_layer_targets_can_be_read_in_independent_pages(app_client):
    created = app_client.post(
        "/api/map-layers",
        json=sample_map_layer_payload("LAYER-TARGET-PAGING")
        | {
            "linkedBlockCodes": ["BLOCK-001", "BLOCK-002", "BLOCK-003"],
            "linkedRightArchiveCodes": ["RIGHT-001", "RIGHT-002"],
        },
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    layer_id = created.json()["id"]

    first_blocks = app_client.get(
        f"/api/map-layers/{layer_id}/targets?kind=blocks&limit=2&offset=0",
        headers={"X-RS-Roles": "map.layers.view"},
    )
    second_blocks = app_client.get(
        f"/api/map-layers/{layer_id}/targets?kind=blocks&limit=2&offset=2",
        headers={"X-RS-Roles": "map.layers.view"},
    )
    rights = app_client.get(
        f"/api/map-layers/{layer_id}/targets?kind=rights&limit=100&offset=0",
        headers={"X-RS-Roles": "map.layers.view"},
    )

    assert first_blocks.status_code == 200
    assert first_blocks.json() == {
        "kind": "blocks",
        "items": [{"blockCode": "BLOCK-001"}, {"blockCode": "BLOCK-002"}],
        "total": 3,
        "limit": 2,
        "offset": 0,
    }
    assert second_blocks.json()["items"] == [{"blockCode": "BLOCK-003"}]
    assert rights.status_code == 200
    assert rights.json()["total"] == 2
    assert rights.json()["items"] == [
        {"archiveCode": "RIGHT-001"},
        {"archiveCode": "RIGHT-002"},
    ]


def test_map_layers_filter_by_dashboard_visibility(app_client):
    visible_layer = sample_map_layer_payload("LAYER-DASHBOARD-VISIBLE") | {
        "name": "Dashboard visible layer",
        "visibleOnDashboard": True,
    }
    hidden_layer = sample_map_layer_payload("LAYER-DASHBOARD-HIDDEN") | {
        "name": "Dashboard hidden layer",
        "visibleOnDashboard": False,
    }
    draft_layer = sample_map_layer_payload("LAYER-DASHBOARD-DRAFT") | {
        "name": "Dashboard draft layer",
        "status": "draft",
        "visibleOnDashboard": True,
    }

    for payload in [visible_layer, hidden_layer, draft_layer]:
        response = app_client.post("/api/map-layers", json=payload, headers={"X-RS-Roles": "admin"})
        assert response.status_code == 200

    visible = app_client.get("/api/map-layers?status=published&visibleOnDashboard=true")
    hidden = app_client.get("/api/map-layers?status=published&visibleOnDashboard=false")

    assert visible.status_code == 200
    assert {item["recordCode"] for item in visible.json()["items"]} == {"LAYER-DASHBOARD-VISIBLE"}
    assert hidden.status_code == 200
    assert {item["recordCode"] for item in hidden.json()["items"]} == {"LAYER-DASHBOARD-HIDDEN"}


def test_map_layers_dashboard_returns_published_visible_layers_with_summary(app_client):
    import_layer = sample_map_layer_payload("LAYER-DASHBOARD-IMPORT") | {
        "name": "Import publish layer",
        "layerType": "quality",
        "linkedBlockCodes": ["BLOCK-001", "BLOCK-002"],
        "properties": {
            "importBatchId": "batch-dashboard-001",
            "publishRiskStatus": "clear",
        },
    }
    imagery_layer = sample_map_layer_payload("LAYER-DASHBOARD-IMAGERY") | {
        "name": "Imagery publish layer",
        "layerType": "imagery",
        "linkedBlockCodes": ["BLOCK-002"],
        "properties": {
            "sourceSceneId": "scene-dashboard-001",
            "publishRiskStatus": "warning",
        },
    }
    hidden_layer = sample_map_layer_payload("LAYER-DASHBOARD-HIDDEN") | {
        "visibleOnDashboard": False,
    }
    draft_layer = sample_map_layer_payload("LAYER-DASHBOARD-DRAFT") | {
        "status": "draft",
        "visibleOnDashboard": True,
    }
    deleted_layer = sample_map_layer_payload("LAYER-DASHBOARD-DELETED")

    for payload in [import_layer, imagery_layer, hidden_layer, draft_layer, deleted_layer]:
        response = app_client.post("/api/map-layers", json=payload, headers={"X-RS-Roles": "admin"})
        assert response.status_code == 200
        if payload["recordCode"] == "LAYER-DASHBOARD-DELETED":
            deleted = app_client.delete(f"/api/map-layers/{response.json()['id']}", headers={"X-RS-Roles": "admin"})
            assert deleted.status_code == 200

    dashboard = app_client.get("/api/map-layers/dashboard")

    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["total"] == 2
    assert [item["recordCode"] for item in body["items"]] == [
        "LAYER-DASHBOARD-IMPORT",
        "LAYER-DASHBOARD-IMAGERY",
    ]
    assert body["items"][0]["sourceType"] == "importBatch"
    assert body["items"][1]["sourceType"] == "imagery"
    assert body["summary"] == {
        "total": 2,
        "linkedBlockTotal": 2,
        "byLayerType": {"imagery": 1, "quality": 1},
        "bySourceType": {"imagery": 1, "importBatch": 1},
        "byPublishRiskStatus": {"clear": 1, "warning": 1},
    }
    assert body["filters"] == {"status": "published", "visibleOnDashboard": True}
    assert body["adminHref"] == "admin-map-layers.html"


def test_map_layers_dashboard_includes_publication_queue_for_closure(app_client):
    awaiting_publish = sample_map_layer_payload("LAYER-QUEUE-AWAITING") | {
        "name": "Awaiting publish layer",
        "status": "draft",
        "visibleOnDashboard": False,
        "properties": {"publishRiskStatus": "clear", "qualityStatus": "passed"},
    }
    needs_review = sample_map_layer_payload("LAYER-QUEUE-REVIEW") | {
        "name": "Review publish layer",
        "status": "draft",
        "visibleOnDashboard": False,
        "properties": {"publishRiskStatus": "warning", "qualityStatus": "warning"},
    }
    blocked = sample_map_layer_payload("LAYER-QUEUE-BLOCKED") | {
        "name": "Blocked publish layer",
        "status": "draft",
        "visibleOnDashboard": False,
        "properties": {"publishRiskStatus": "blocked", "qualityStatus": "blocked"},
    }
    receipt_ready = sample_map_layer_payload("LAYER-QUEUE-RECEIPT") | {
        "name": "Receipt ready layer",
        "status": "published",
        "visibleOnDashboard": True,
        "properties": {"publishRiskStatus": "clear", "sourceSceneId": "scene-queue-001"},
    }

    for payload in [awaiting_publish, needs_review, blocked, receipt_ready]:
        response = app_client.post("/api/map-layers", json=payload, headers={"X-RS-Roles": "admin"})
        assert response.status_code == 200

    dashboard = app_client.get("/api/map-layers/dashboard")

    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["publicationSummary"] == {
        "publicationQueueTotal": 4,
        "awaitingPublishTotal": 1,
        "reviewTotal": 1,
        "blockedTotal": 1,
        "receiptReadyTotal": 1,
        "publishedDashboardTotal": 1,
    }
    lanes = {lane["key"]: lane for lane in body["publicationQueue"]}
    assert list(lanes) == ["blocked", "needs_review", "awaiting_publish", "receipt_ready"]
    assert lanes["blocked"]["requiredPermission"] == "map.layers.update"
    assert lanes["needs_review"]["items"][0]["recordCode"] == "LAYER-QUEUE-REVIEW"
    assert lanes["awaiting_publish"]["requiredPermission"] == "map.layers.publish"
    assert lanes["awaiting_publish"]["items"][0]["adminHref"] == "admin-map-layers.html?layerCode=LAYER-QUEUE-AWAITING"
    assert lanes["receipt_ready"]["requiredPermission"] == "map.layers.export"
    assert lanes["receipt_ready"]["items"][0]["dashboardHref"] == "zhushan-bigdata.html#mapLayers"


def test_deleted_map_layer_can_be_listed_and_restored(app_client):
    created = app_client.post(
        "/api/map-layers",
        json=sample_map_layer_payload("LAYER-RESTORE-001"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    layer_id = created.json()["id"]

    deleted = app_client.delete(
        f"/api/map-layers/{layer_id}",
        headers={"X-RS-Roles": "admin"},
    )
    hidden = app_client.get("/api/map-layers?q=LAYER-RESTORE-001")
    deleted_list = app_client.get(
        "/api/map-layers?q=LAYER-RESTORE-001&includeDeleted=true",
        headers={"X-RS-Roles": "admin"},
    )
    denied_restore = app_client.post(
        f"/api/map-layers/{layer_id}/restore",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    restored = app_client.post(
        f"/api/map-layers/{layer_id}/restore",
        headers={"X-RS-Roles": "admin"},
    )
    active_again = app_client.get("/api/map-layers?q=LAYER-RESTORE-001")

    assert deleted.status_code == 200
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0
    assert deleted_list.status_code == 200
    assert deleted_list.json()["total"] == 1
    assert deleted_list.json()["items"][0]["deletedAt"]
    assert denied_restore.status_code == 403
    assert "map.layers.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    assert restored.json()["ok"] is True
    assert restored.json()["restored"] == layer_id
    assert restored.json()["item"]["deletedAt"] is None
    assert active_again.status_code == 200
    assert active_again.json()["total"] == 1


def test_map_layer_crud_actions_use_separate_permissions(app_client):
    denied_create = app_client.post(
        "/api/map-layers",
        json=sample_map_layer_payload("LAYER-ACTION-PERM"),
        headers={"X-RS-Roles": "map.layers.view"},
    )
    created = app_client.post(
        "/api/map-layers",
        json=sample_map_layer_payload("LAYER-ACTION-PERM"),
        headers={"X-RS-Roles": "map.layers.create"},
    )

    assert denied_create.status_code == 403
    assert "map.layers.create" in denied_create.json()["detail"]
    assert created.status_code == 200
    layer_id = created.json()["id"]

    listed = app_client.get(
        "/api/map-layers?q=LAYER-ACTION-PERM",
        headers={"X-RS-Roles": "map.layers.view"},
    )
    denied_update = app_client.patch(
        f"/api/map-layers/{layer_id}",
        json={"name": "Denied layer update"},
        headers={"X-RS-Roles": "map.layers.view"},
    )
    updated = app_client.patch(
        f"/api/map-layers/{layer_id}",
        json={"name": "Allowed layer update"},
        headers={"X-RS-Roles": "map.layers.update"},
    )
    deleted = app_client.delete(
        f"/api/map-layers/{layer_id}",
        headers={"X-RS-Roles": "map.layers.delete"},
    )
    denied_deleted_list = app_client.get(
        "/api/map-layers?q=LAYER-ACTION-PERM&includeDeleted=true",
        headers={"X-RS-Roles": "map.layers.view"},
    )
    deleted_list = app_client.get(
        "/api/map-layers?q=LAYER-ACTION-PERM&includeDeleted=true",
        headers={"X-RS-Roles": "map.layers.restore"},
    )
    denied_restore = app_client.post(
        f"/api/map-layers/{layer_id}/restore",
        headers={"X-RS-Roles": "map.layers.view"},
    )
    restored = app_client.post(
        f"/api/map-layers/{layer_id}/restore",
        headers={"X-RS-Roles": "map.layers.restore"},
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert denied_update.status_code == 403
    assert "map.layers.update" in denied_update.json()["detail"]
    assert updated.status_code == 200
    assert updated.json()["name"] == "Allowed layer update"
    assert deleted.status_code == 200
    assert denied_deleted_list.status_code == 403
    assert "map.layers.restore" in denied_deleted_list.json()["detail"]
    assert deleted_list.status_code == 200
    assert deleted_list.json()["total"] == 1
    assert denied_restore.status_code == 403
    assert "map.layers.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    assert restored.json()["ok"] is True


def test_map_layer_dashboard_publish_toggle_requires_publish_permission(app_client):
    created = app_client.post(
        "/api/map-layers",
        json=sample_map_layer_payload("LAYER-PUBLISH-PERM"),
        headers={"X-RS-Roles": "admin"},
    )
    layer_id = created.json()["id"]

    denied_publish_toggle = app_client.patch(
        f"/api/map-layers/{layer_id}",
        json={"visibleOnDashboard": False},
        headers={"X-RS-Roles": "map.layers.update"},
    )
    allowed_publish_toggle = app_client.patch(
        f"/api/map-layers/{layer_id}",
        json={"visibleOnDashboard": False},
        headers={"X-RS-Roles": "map.layers.update,map.layers.publish"},
    )

    assert created.status_code == 200
    assert denied_publish_toggle.status_code == 403
    assert "map.layers.publish" in denied_publish_toggle.json()["detail"]
    assert allowed_publish_toggle.status_code == 200
    assert allowed_publish_toggle.json()["visibleOnDashboard"] is False


def test_map_layer_include_deleted_requires_restore_permission(app_client):
    created = app_client.post(
        "/api/map-layers",
        json=sample_map_layer_payload("LAYER-DELETED-PERMISSION"),
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    layer_id = created.json()["id"]

    deleted = app_client.delete(
        f"/api/map-layers/{layer_id}",
        headers={"X-RS-Roles": "admin"},
    )
    denied = app_client.get(
        "/api/map-layers?q=LAYER-DELETED-PERMISSION&includeDeleted=true",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )

    assert deleted.status_code == 200
    assert denied.status_code == 403
    assert "map.layers.restore" in denied.json()["detail"]


def test_map_layer_events_can_be_listed_across_layers(app_client):
    created = app_client.post(
        "/api/map-layers",
        json=sample_map_layer_payload("LAYER-EVENTS-001"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    layer_id = created.json()["id"]
    patched = app_client.patch(
        f"/api/map-layers/{layer_id}",
        json={"name": "Events layer updated", "visibleOnDashboard": False},
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )
    deleted = app_client.delete(
        f"/api/map-layers/{layer_id}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "carol"},
    )
    restored = app_client.post(
        f"/api/map-layers/{layer_id}/restore",
        headers={"X-RS-Roles": "admin", "X-RS-User": "dave"},
    )
    denied = app_client.get(
        "/api/map-layers/events",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    listed = app_client.get("/api/map-layers/events?limit=20", headers={"X-RS-Roles": "admin"})
    update_only = app_client.get(
        f"/api/map-layers/events?action=update&layerId={layer_id}&q=bob",
        headers={"X-RS-Roles": "admin"},
    )

    assert created.status_code == 200
    assert created.json()["properties"]["auditEvents"][-1]["action"] == "create"
    assert patched.status_code == 200
    assert patched.json()["properties"]["auditEvents"][-1]["changedFields"] == ["name", "visibleOnDashboard"]
    assert deleted.status_code == 200
    assert restored.status_code == 200
    assert denied.status_code == 403
    assert "map.layers.view" in denied.json()["detail"]
    assert listed.status_code == 200
    body = listed.json()
    assert body["limit"] == 20
    assert body["total"] == 4
    actions = [item["action"] for item in body["items"]]
    assert set(actions) == {"create", "update", "delete", "restore"}
    update_event = next(item for item in body["items"] if item["action"] == "update")
    assert update_event["eventId"]
    assert update_event["layerId"] == layer_id
    assert update_event["recordCode"] == "LAYER-EVENTS-001"
    assert update_event["actor"] == "bob"
    assert update_event["visibleOnDashboard"] is False
    assert update_event["changedFields"] == ["name", "visibleOnDashboard"]
    assert update_event["sourceType"] == "manual"
    assert update_event["summary"] == "update: LAYER-EVENTS-001"
    assert update_only.status_code == 200
    assert update_only.json()["total"] == 1
    assert update_only.json()["items"][0]["action"] == "update"


def test_map_layer_events_csv_export_requires_export_permission(app_client):
    created = app_client.post(
        "/api/map-layers",
        json=sample_map_layer_payload("LAYER-EVENT-EXPORT"),
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    assert created.status_code == 200
    layer_id = created.json()["id"]

    published = app_client.post(
        f"/api/map-layers/{layer_id}/publish",
        json={"visibleOnDashboard": False, "status": "paused"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )
    denied = app_client.get(
        "/api/map-layers/events.csv?recordCode=LAYER-EVENT-EXPORT",
        headers={"X-RS-Roles": "map.layers.view"},
    )
    exported = app_client.get(
        "/api/map-layers/events.csv?recordCode=LAYER-EVENT-EXPORT",
        headers={"X-RS-Roles": "map.layers.export"},
    )

    assert published.status_code == 200
    assert denied.status_code == 403
    assert "map.layers.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert 'filename="map-layer-events.csv"' in exported.headers["content-disposition"]
    csv_text = exported.content.decode("utf-8-sig")
    assert "eventId,layerId,recordCode,layerName,action,actor,at,status,visibleOnDashboard,sourceType" in csv_text
    assert "LAYER-EVENT-EXPORT" in csv_text
    assert "publish" in csv_text
    assert "bob" in csv_text
    assert "paused" in csv_text


def test_map_layers_can_filter_by_source_type_for_traceability(app_client):
    imagery_layer = sample_map_layer_payload("LAYER-SCENE-SOURCE") | {
        "name": "Scene source layer",
        "properties": {"sourceSceneId": "scene-source-001"},
    }
    import_layer = sample_map_layer_payload("LAYER-IMPORT-SOURCE") | {
        "name": "Import batch source layer",
        "properties": {"sourceSceneId": "scene-source-001", "importBatchId": "batch-source-001"},
    }
    manual_layer = sample_map_layer_payload("LAYER-MANUAL-SOURCE") | {
        "name": "Manual source layer",
        "properties": {"legend": "manual"},
    }

    for payload in [imagery_layer, import_layer, manual_layer]:
        response = app_client.post("/api/map-layers", json=payload, headers={"X-RS-Roles": "admin"})
        assert response.status_code == 200

    imagery = app_client.get("/api/map-layers?sourceType=imagery")
    import_batches = app_client.get("/api/map-layers?sourceType=importBatch")
    manual = app_client.get("/api/map-layers?sourceType=manual")

    assert imagery.status_code == 200
    assert [item["recordCode"] for item in imagery.json()["items"]] == ["LAYER-SCENE-SOURCE"]
    assert import_batches.status_code == 200
    assert [item["recordCode"] for item in import_batches.json()["items"]] == ["LAYER-IMPORT-SOURCE"]
    assert manual.status_code == 200
    assert [item["recordCode"] for item in manual.json()["items"]] == ["LAYER-MANUAL-SOURCE"]


def test_map_layers_expose_workflow_trace_links(app_client):
    payload = sample_map_layer_payload("LAYER-TRACE-LINKS") | {
        "name": "Traceable import imagery layer",
        "properties": {
            "sourceSceneId": "scene-trace-001",
            "importBatchId": "batch-trace-001",
            "publishRiskStatus": "clear",
        },
    }
    created = app_client.post(
        "/api/map-layers",
        json=payload,
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    assert created.status_code == 200

    listed = app_client.get("/api/map-layers?q=LAYER-TRACE-LINKS")
    detail = app_client.get(
        f"/api/map-layers/{created.json()['id']}",
        headers={"X-RS-Roles": "map.layers.view"},
    )
    events = app_client.get(
        "/api/map-layers/events?recordCode=LAYER-TRACE-LINKS",
        headers={"X-RS-Roles": "admin"},
    )
    dashboard = app_client.get("/api/map-layers/dashboard")

    expected_source_links = [
        {
            "type": "importBatch",
            "label": "入库批次",
            "value": "batch-trace-001",
            "href": "admin-imports.html?batchId=batch-trace-001",
        },
        {
            "type": "imagery",
            "label": "影像场景",
            "value": "scene-trace-001",
            "href": "admin-imagery.html?sceneId=scene-trace-001",
        },
    ]
    dashboard_item = next(item for item in dashboard.json()["items"] if item["recordCode"] == "LAYER-TRACE-LINKS")

    for item in [created.json(), listed.json()["items"][0], detail.json(), dashboard_item]:
        assert item["sourceType"] == "importBatch"
        assert item["adminHref"] == "admin-map-layers.html?layerCode=LAYER-TRACE-LINKS"
        assert item["dashboardHref"] == "zhushan-bigdata.html#mapLayers"
        assert item["sourceLinks"] == expected_source_links

    assert events.status_code == 200
    event = events.json()["items"][0]
    assert event["sourceType"] == "importBatch"
    assert event["adminHref"] == "admin-map-layers.html?layerCode=LAYER-TRACE-LINKS"
    assert event["sourceLinks"] == expected_source_links


def test_map_layers_can_filter_by_publish_risk_status(app_client):
    warning_layer = sample_map_layer_payload("LAYER-RISK-WARNING") | {
        "name": "Import batch warning layer",
        "properties": {
            "importBatchId": "batch-risk-warning",
            "qualityStatus": "warning",
            "publishRiskStatus": "warning",
            "reviewRecommendation": "needs_correction",
        },
    }
    clear_layer = sample_map_layer_payload("LAYER-RISK-CLEAR") | {
        "name": "Import batch clear layer",
        "properties": {
            "importBatchId": "batch-risk-clear",
            "qualityStatus": "passed",
            "publishRiskStatus": "clear",
            "reviewRecommendation": "can_publish",
        },
    }

    for payload in [warning_layer, clear_layer]:
        response = app_client.post("/api/map-layers", json=payload, headers={"X-RS-Roles": "admin"})
        assert response.status_code == 200

    warning = app_client.get("/api/map-layers?publishRiskStatus=warning")

    assert warning.status_code == 200
    assert warning.json()["total"] == 1
    assert warning.json()["items"][0]["recordCode"] == "LAYER-RISK-WARNING"
    assert warning.json()["items"][0]["properties"]["reviewRecommendation"] == "needs_correction"


def test_postgis_create_map_layer_uses_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    business_module = reload_business_module(reload_platform_modules)
    existing_cursor = FakeCursor(fetchall_result=[])
    insert_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [existing_cursor, insert_cursor], connect_calls)

    created = business_module.create_map_layer(
        business_module.MapLayerIn(**sample_map_layer_payload("LAYER-PG-CREATE")),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert created.recordCode == "LAYER-PG-CREATE"
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo"]
    assert "FROM map_layers" in existing_cursor.executed[0][0]
    assert "INSERT INTO map_layers" in insert_cursor.executed[0][0]
    assert insert_cursor.executed[0][1][1] == "LAYER-PG-CREATE"


def test_postgis_list_map_layer_filters_are_applied_in_database(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    business_module = reload_business_module(reload_platform_modules)
    list_cursor = FakeCursor(fetchall_result=[postgis_map_layer_row("LAYER-PG-FILTER")])
    count_cursor = FakeCursor(fetchone_result=(1,))
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [list_cursor, count_cursor], connect_calls)

    response = business_module.list_map_layers(
        business_module.ManagedFilters(
            q="quality",
            status="published",
            linkedBlockCode="BLOCK-PG-001",
            sourceType="importBatch",
            publishRiskStatus="warning",
            visibleOnDashboard="true",
            limit=20,
            offset=5,
        )
    )

    list_sql, list_params = list_cursor.executed[0]
    count_sql, count_params = count_cursor.executed[0]
    assert response["total"] == 1
    assert response["items"][0]["recordCode"] == "LAYER-PG-FILTER"
    assert "status = %s" in list_sql
    assert "linked_block_codes ? %s" in list_sql
    assert "properties ? 'importBatchId'" in list_sql
    assert "properties->>'publishRiskStatus' = %s" in list_sql
    assert "COALESCE(visible_on_dashboard, TRUE) = %s" in list_sql
    assert "ILIKE" in list_sql
    assert "LIMIT %s OFFSET %s" in list_sql
    assert list_params[-2:] == (20, 5)
    assert "SELECT COUNT(*) FROM map_layers" in count_sql
    assert count_params[:4] == ("published", "BLOCK-PG-001", "warning", True)


def test_postgis_patch_and_delete_map_layer_use_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    business_module = reload_business_module(reload_platform_modules)
    select_for_patch = FakeCursor(fetchall_result=[postgis_map_layer_row("LAYER-PG-PATCH")])
    update_cursor = FakeCursor()
    select_for_delete = FakeCursor(fetchall_result=[postgis_map_layer_row("LAYER-PG-PATCH")])
    delete_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(
        monkeypatch,
        [select_for_patch, update_cursor, select_for_delete, delete_cursor],
        connect_calls,
    )

    patched = business_module.patch_map_layer(
        "7ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        business_module.MapLayerPatch(name="Updated layer", visibleOnDashboard=False),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )
    deleted = business_module.delete_map_layer(
        "7ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert patched.name == "Updated layer"
    assert patched.visibleOnDashboard is False
    assert deleted["ok"] is True
    assert "FROM map_layers" in select_for_patch.executed[0][0]
    assert "INSERT INTO map_layers" in update_cursor.executed[0][0]
    assert "INSERT INTO map_layers" in delete_cursor.executed[0][0]


def test_postgis_create_business_record_uses_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    business_module = reload_business_module(reload_platform_modules)
    existing_cursor = FakeCursor(fetchall_result=[])
    insert_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [existing_cursor, insert_cursor], connect_calls)

    payload = {
        **sample_business_record("FARMER-PG-CREATE"),
        "townName": "Masha",
        "villageName": "Xinfeng",
    }
    created = business_module.create_business_record(
        "farmers",
        business_module.ManagedRecordIn(**payload),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert created.recordCode == "FARMER-PG-CREATE"
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo"]
    assert "FROM business_records" in existing_cursor.executed[0][0]
    assert "module_key = %s" in existing_cursor.executed[0][0]
    assert "INSERT INTO business_records" in insert_cursor.executed[0][0]
    assert insert_cursor.executed[0][1][1] == "farmers"
    assert insert_cursor.executed[0][1][2] == "FARMER-PG-CREATE"


def test_postgis_list_business_record_filters_are_applied_in_database(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    business_module = reload_business_module(reload_platform_modules)
    list_cursor = FakeCursor(fetchall_result=[postgis_business_row("farmers", "FARMER-PG-FILTER")])
    count_cursor = FakeCursor(fetchone_result=(1,))
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [list_cursor, count_cursor], connect_calls)

    response = business_module.list_business_records(
        "farmers",
        business_module.ManagedFilters(
            q="ownerPhone",
            status="active",
            linkedBlockCode="BLOCK-PG-001",
            limit=20,
            offset=5,
        ),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    list_sql, list_params = list_cursor.executed[0]
    count_sql, count_params = count_cursor.executed[0]
    assert response["total"] == 1
    assert response["items"][0]["recordCode"] == "FARMER-PG-FILTER"
    assert response["items"][0]["townName"] == "Masha"
    assert "module_key = %s" in list_sql
    assert "status = %s" in list_sql
    assert "linked_block_codes ? %s" in list_sql
    assert "ILIKE" in list_sql
    assert "LIMIT %s OFFSET %s" in list_sql
    assert list_params[:3] == ("farmers", "active", "BLOCK-PG-001")
    assert list_params[-2:] == (20, 5)
    assert "SELECT COUNT(*) FROM business_records" in count_sql
    assert count_params[:3] == ("farmers", "active", "BLOCK-PG-001")


def test_postgis_patch_and_delete_business_record_use_database_storage(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    business_module = reload_business_module(reload_platform_modules)
    select_for_patch = FakeCursor(fetchall_result=[postgis_business_row("farmers", "FARMER-PG-PATCH")])
    update_cursor = FakeCursor()
    select_for_delete = FakeCursor(fetchall_result=[postgis_business_row("farmers", "FARMER-PG-PATCH")])
    delete_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(
        monkeypatch,
        [select_for_patch, update_cursor, select_for_delete, delete_cursor],
        connect_calls,
    )

    patched = business_module.patch_business_record(
        "farmers",
        "6ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        business_module.ManagedRecordPatch(name="Updated farmer", status="paused"),
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )
    deleted = business_module.delete_business_record(
        "farmers",
        "6ab8cd2e-f574-4fd8-bdf6-b7788e632101",
        context=AuthContext(user="alice", roles={"admin"}, projects=set(), areas=set()),
    )

    assert patched.name == "Updated farmer"
    assert patched.status == "paused"
    assert deleted["ok"] is True
    assert "FROM business_records" in select_for_patch.executed[0][0]
    assert "INSERT INTO business_records" in update_cursor.executed[0][0]
    assert "INSERT INTO business_records" in delete_cursor.executed[0][0]
