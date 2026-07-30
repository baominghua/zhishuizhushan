from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

from server.modules.business import normalize_business_properties


ROOT = Path(__file__).resolve().parents[1]


FORMAL_BASELINE_FIELDS = {
    "farmers": {
        "identityType",
        "identityNumber",
        "phone",
        "provinceCode",
        "cityCode",
        "countyCode",
        "townCode",
        "villageCode",
        "address",
        "operationAreaMu",
        "cooperativeIds",
    },
    "cooperatives": {
        "unifiedSocialCreditCode",
        "legalRepresentative",
        "phone",
        "provinceCode",
        "cityCode",
        "countyCode",
        "townCode",
        "villageCode",
        "address",
        "memberCount",
        "serviceCapacity",
        "operationStatus",
        "memberFarmerIds",
    },
    "enterprises": {
        "unifiedSocialCreditCode",
        "enterpriseType",
        "mainBusiness",
        "contactName",
        "phone",
        "provinceCode",
        "cityCode",
        "countyCode",
        "townCode",
        "villageCode",
        "address",
        "processingCapacityTons",
        "purchaseStatus",
        "inventoryStatus",
        "cooperativeIds",
    },
    "plant-protection-events": {
        "issueType",
        "riskLevel",
        "discoveredAt",
        "detectionSource",
        "affectedAreaMu",
        "treatmentAdvice",
        "handlerFarmerIds",
        "handlerCooperativeIds",
        "closedAt",
        "handlingStatus",
        "maintenanceTaskIds",
        "materialIds",
    },
    "materials": {
        "itemCategory",
        "specification",
        "unit",
        "batchNo",
        "stock",
        "warningThreshold",
        "supplierEnterpriseIds",
        "expiryDate",
        "warehouse",
        "inventoryStatus",
    },
    "policies": {
        "issuingBody",
        "policyLevel",
        "policyType",
        "publishDate",
        "effectiveDate",
        "deadline",
        "target",
        "applicationItem",
        "summary",
        "attachmentUrl",
        "reviewStatus",
    },
    "stewardship-agreements": {
        "ownerFarmerIds",
        "serviceProviderCooperativeIds",
        "serviceProviderEnterpriseIds",
        "serviceMode",
        "signedDate",
        "startDate",
        "endDate",
        "areaMu",
        "feeMode",
        "performanceStatus",
    },
    "franchise-bases": {
        "provinceCode",
        "cityCode",
        "countyCode",
        "townCode",
        "villageCode",
        "operatorCooperativeIds",
        "operatorEnterpriseIds",
        "baseAreaMu",
        "serviceLevel",
        "operationStatus",
        "agreementIds",
    },
    "maintenance-tasks": {
        "taskType",
        "priority",
        "assigneeFarmerIds",
        "assigneeCooperativeIds",
        "plannedStartAt",
        "plannedEndAt",
        "completedAt",
        "closureStatus",
        "equipmentIds",
        "materialIds",
    },
    "work-logs": {
        "workStage",
        "workDate",
        "workerFarmerIds",
        "workerCooperativeIds",
        "laborCount",
        "workQuantity",
        "resultSummary",
        "reviewerFarmerIds",
        "taskIds",
        "materialIds",
    },
    "drone-tasks": {
        "taskType",
        "equipmentIds",
        "routeCode",
        "plannedStartAt",
        "actualStartAt",
        "actualEndAt",
        "resultStatus",
        "resultPackageUrl",
    },
    "equipment": {
        "deviceType",
        "deviceCode",
        "model",
        "ownerCooperativeIds",
        "ownerEnterpriseIds",
        "installLocation",
        "purchaseDate",
        "onlineStatus",
        "maintenanceDueDate",
    },
    "pest-warnings": {
        "riskType",
        "riskLevel",
        "detectionSource",
        "issuedAt",
        "affectedAreaMu",
        "treatmentAdvice",
        "reviewStatus",
        "eventIds",
        "taskIds",
    },
    "material-services": {
        "serviceType",
        "materialIds",
        "supplierEnterpriseIds",
        "applicantFarmerIds",
        "applicantCooperativeIds",
        "requestedQuantity",
        "deliveredQuantity",
        "requestedAt",
        "deliveryDate",
        "deliveryStatus",
        "feedbackStatus",
    },
    "yield-forecasts": {
        "forecastObject",
        "forecastPeriod",
        "bambooSpecies",
        "areaMu",
        "forecastYield",
        "modelName",
        "confidence",
        "publishStatus",
    },
    "harvest-plans": {
        "harvestType",
        "plannedStartDate",
        "plannedEndDate",
        "plannedQuantity",
        "harvestMethod",
        "executionStatus",
        "forecastIds",
        "operatorCooperativeIds",
        "operatorEnterpriseIds",
        "equipmentIds",
    },
    "income-estimates": {
        "estimateType",
        "estimatePeriod",
        "expectedIncome",
        "cost",
        "netIncome",
        "assumptions",
        "reviewStatus",
        "harvestPlanIds",
        "cooperativeIds",
        "enterpriseIds",
    },
    "performance-dashboards": {
        "metricType",
        "coverage",
        "metricCaliber",
        "metricValue",
        "metricPeriod",
        "ownerCooperativeIds",
        "ownerEnterpriseIds",
        "publishStatus",
    },
    "carbon-estimates": {
        "accountingType",
        "projectBoundary",
        "accountingStartDate",
        "accountingEndDate",
        "carbonStock",
        "carbonIncrement",
        "methodology",
        "verifier",
        "verificationStatus",
    },
    "trade-matches": {
        "tradeType",
        "productType",
        "qualityGrade",
        "quantity",
        "unit",
        "unitPrice",
        "deliveryStartDate",
        "deliveryEndDate",
        "matchStatus",
        "buyerEnterpriseIds",
        "sellerCooperativeIds",
        "sellerEnterpriseIds",
    },
    "logistics-traces": {
        "batchNo",
        "carrierEnterpriseIds",
        "vehicleNo",
        "driverName",
        "driverPhone",
        "currentNode",
        "quantity",
        "departureAt",
        "arrivalAt",
        "logisticsStatus",
        "tradeMatchIds",
    },
    "product-qrcodes": {
        "qrCode",
        "codeType",
        "productType",
        "batchNo",
        "targetUrl",
        "issuedAt",
        "publishStatus",
        "scanCount",
        "enterpriseIds",
        "logisticsTraceIds",
    },
    "supply-chain-finance": {
        "financeProduct",
        "borrowerCooperativeIds",
        "borrowerEnterpriseIds",
        "amount",
        "termMonths",
        "dueDate",
        "reviewStatus",
        "riskLevel",
        "tradeMatchIds",
    },
    "price-indexes": {
        "productType",
        "qualityGrade",
        "provinceCode",
        "cityCode",
        "countyCode",
        "price",
        "period",
        "sourceCount",
        "publishStatus",
    },
    "mobile-service-channels": {
        "target",
        "channel",
        "entry",
        "ownerCooperativeIds",
        "ownerEnterpriseIds",
        "releaseVersion",
        "publishStatus",
        "relatedPolicyIds",
        "relatedServiceIds",
    },
}


def test_all_business_modules_expose_complete_versioned_domain_forms(app_client):
    response = app_client.get("/api/business/modules", headers={"X-RS-Roles": "admin"})

    assert response.status_code == 200
    modules = {item["key"]: item for item in response.json()["items"]}
    assert set(modules) == set(FORMAL_BASELINE_FIELDS)
    for module_key, expected_fields in FORMAL_BASELINE_FIELDS.items():
        module = modules[module_key]
        fields = {field["key"]: field for field in module["fieldSchema"]}
        assert module["formVersion"] == 2, module_key
        assert expected_fields.issubset(fields), (
            module_key,
            sorted(expected_fields - set(fields)),
        )
        assert all(str(field.get("section") or "").strip() for field in fields.values()), module_key


def test_form_relations_use_authorized_record_ids_and_divisions_cascade(app_client):
    response = app_client.get("/api/business/modules", headers={"X-RS-Roles": "admin"})
    modules = {item["key"]: item for item in response.json()["items"]}

    for module_key, module in modules.items():
        for field in module["fieldSchema"]:
            if field["inputType"] == "business-relation":
                target = field["targetModuleKey"]
                assert field["referenceEndpoint"] == f"/api/references/business/{target}", (
                    module_key,
                    field["key"],
                )
                assert field["referenceValueKey"] == "id"
                assert field["relationType"]

    division_fields = {
        field["key"]: field
        for field in modules["cooperatives"]["fieldSchema"]
        if field["key"].endswith("Code")
    }
    assert division_fields["provinceCode"]["referenceLevel"] == "province"
    assert division_fields["cityCode"]["parentField"] == "provinceCode"
    assert division_fields["countyCode"]["parentField"] == "cityCode"
    assert division_fields["townCode"]["parentField"] == "countyCode"
    assert division_fields["villageCode"]["parentField"] == "townCode"


def test_enterprise_form_rejects_invalid_credit_code_and_phone():
    with pytest.raises(HTTPException, match="unifiedSocialCreditCode"):
        normalize_business_properties(
            "enterprises",
            {"unifiedSocialCreditCode": "123", "phone": "13800000000"},
        )

    with pytest.raises(HTTPException, match="phone"):
        normalize_business_properties(
            "enterprises",
            {
                "unifiedSocialCreditCode": "91350784MA2Y12345X",
                "phone": "12345",
            },
        )

    normalized = normalize_business_properties(
        "enterprises",
        {
            "unifiedSocialCreditCode": "91350784MA2Y12345X",
            "phone": "13800000000",
        },
    )
    assert normalized["unifiedSocialCreditCode"] == "91350784MA2Y12345X"
    assert normalized["phone"] == "13800000000"


def test_computed_business_fields_are_derived_instead_of_manually_entered():
    low_stock = normalize_business_properties(
        "materials",
        {"stock": 5, "warningThreshold": 10, "inventoryStatus": "normal"},
    )
    no_stock = normalize_business_properties(
        "materials",
        {"stock": 0, "warningThreshold": 10},
    )
    healthy_stock = normalize_business_properties(
        "materials",
        {"stock": 15, "warningThreshold": 10},
    )
    estimate = normalize_business_properties(
        "income-estimates",
        {"expectedIncome": 125000, "cost": 43210.5, "netIncome": 1},
    )

    assert low_stock["inventoryStatus"] == "warning"
    assert no_stock["inventoryStatus"] == "out"
    assert healthy_stock["inventoryStatus"] == "normal"
    assert estimate["netIncome"] == 81789.5


def test_cross_field_dates_reject_an_end_before_its_start():
    with pytest.raises(HTTPException, match="plannedEndAt"):
        normalize_business_properties(
            "maintenance-tasks",
            {
                "plannedStartAt": "2026-08-02T10:00",
                "plannedEndAt": "2026-08-01T10:00",
            },
        )

    with pytest.raises(HTTPException, match="accountingEndDate"):
        normalize_business_properties(
            "carbon-estimates",
            {
                "accountingStartDate": "2026-12-31",
                "accountingEndDate": "2026-01-01",
            },
        )


def test_computed_form_metadata_is_exposed_for_frontend_auto_fill(app_client):
    response = app_client.get("/api/business/modules", headers={"X-RS-Roles": "admin"})
    modules = {item["key"]: item for item in response.json()["items"]}
    materials = {item["key"]: item for item in modules["materials"]["fieldSchema"]}
    income = {item["key"]: item for item in modules["income-estimates"]["fieldSchema"]}

    assert materials["inventoryStatus"]["readOnly"] is True
    assert materials["inventoryStatus"]["computed"] == {
        "operation": "stock-status",
        "fields": ["stock", "warningThreshold"],
    }
    assert income["netIncome"]["readOnly"] is True
    assert income["netIncome"]["computed"] == {
        "operation": "subtract",
        "fields": ["expectedIncome", "cost"],
        "precision": 2,
    }


def test_browser_form_computations_match_backend_derivations():
    node = shutil.which("node")
    assert node
    script_path = ROOT / "admin-business-computations.js"
    script = """
const compute = require(process.argv[1]);
const result = {
  low: compute.computeFieldValue(
    {operation: "stock-status", fields: ["stock", "warningThreshold"]},
    {stock: 5, warningThreshold: 10}
  ),
  out: compute.computeFieldValue(
    {operation: "stock-status", fields: ["stock", "warningThreshold"]},
    {stock: 0, warningThreshold: 10}
  ),
  healthy: compute.computeFieldValue(
    {operation: "stock-status", fields: ["stock", "warningThreshold"]},
    {stock: 15, warningThreshold: 10}
  ),
  net: compute.computeFieldValue(
    {operation: "subtract", fields: ["expectedIncome", "cost"], precision: 2},
    {expectedIncome: 125000, cost: 43210.5}
  )
};
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        [node, "-e", script, str(script_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert json.loads(completed.stdout) == {
        "low": "warning",
        "out": "out",
        "healthy": "normal",
        "net": 81789.5,
    }


def test_browser_relation_validation_rejects_missing_required_and_group_targets():
    node = shutil.which("node")
    assert node
    script_path = ROOT / "admin-business-computations.js"
    script = """
const rules = require(process.argv[1]);
const fields = [
  {
    key: "buyerEnterpriseIds",
    label: "采购企业",
    inputType: "business-relation",
    required: true,
    relationType: "buyer",
    targetModuleKey: "enterprises"
  },
  {
    key: "sellerCooperativeIds",
    label: "供应合作社",
    inputType: "business-relation",
    relationType: "seller",
    targetModuleKey: "cooperatives",
    relationGroup: "seller",
    minGroupTargets: 1
  },
  {
    key: "sellerEnterpriseIds",
    label: "供应企业",
    inputType: "business-relation",
    relationType: "seller",
    targetModuleKey: "enterprises",
    relationGroup: "seller",
    minGroupTargets: 1
  }
];
const buyer = {
  relationType: "buyer",
  targetModuleKey: "enterprises",
  targetRecordId: "buyer-1"
};
const seller = {
  relationType: "seller",
  targetModuleKey: "cooperatives",
  targetRecordId: "seller-1"
};
process.stdout.write(JSON.stringify({
  missingRequired: rules.validateRelationRequirements(fields, []),
  missingGroup: rules.validateRelationRequirements(fields, [buyer]),
  valid: rules.validateRelationRequirements(fields, [buyer, seller])
}));
"""
    completed = subprocess.run(
        [node, "-e", script, str(script_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result["missingRequired"]["valid"] is False
    assert result["missingRequired"]["fieldKey"] == "buyerEnterpriseIds"
    assert result["missingGroup"]["valid"] is False
    assert result["missingGroup"]["relationGroup"] == "seller"
    assert result["valid"] == {"valid": True}


def test_all_business_pages_load_computations_before_the_form_controller():
    business_pages = sorted(ROOT.glob("admin-*.html"))
    pages = [
        page
        for page in business_pages
        if '<script src="admin-business-module.js"></script>' in page.read_text(encoding="utf-8")
    ]

    assert len(pages) == 25
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert html.index("admin-business-computations.js") < html.index("admin-business-module.js"), page.name


def test_finance_requires_one_existing_borrower_relation(app_client):
    properties = {
        "financeProduct": "order-finance",
        "amount": 500000,
        "termMonths": 12,
        "dueDate": "2027-08-01",
        "reviewStatus": "draft",
        "riskLevel": "low",
    }
    missing = app_client.post(
        "/api/business/supply-chain-finance",
        json={
            "formVersion": 2,
            "recordCode": "FINANCE-NO-BORROWER",
            "name": "缺少融资主体",
            "status": "active",
            "properties": properties,
        },
        headers={"X-RS-Roles": "admin"},
    )
    enterprise = app_client.post(
        "/api/business/enterprises",
        json={
            "recordCode": "ENTERPRISE-FINANCE-001",
            "name": "融资测试竹企",
            "status": "active",
            "properties": {},
        },
        headers={"X-RS-Roles": "admin"},
    )
    assert enterprise.status_code == 200
    enterprise_id = enterprise.json()["id"]

    created = app_client.post(
        "/api/business/supply-chain-finance",
        json={
            "formVersion": 2,
            "recordCode": "FINANCE-WITH-BORROWER",
            "name": "融资主体关联测试",
            "status": "active",
            "properties": properties,
            "linkedRecords": [
                {
                    "relationType": "borrower",
                    "targetModuleKey": "enterprises",
                    "targetRecordId": enterprise_id,
                }
            ],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert missing.status_code == 422
    assert "borrower" in str(missing.json()["detail"])
    assert created.status_code == 200
    assert created.json()["linkedRecords"][0]["targetRecordId"] == enterprise_id


def test_relation_group_metadata_explains_either_or_subject_choices(app_client):
    response = app_client.get("/api/business/modules", headers={"X-RS-Roles": "admin"})
    modules = {item["key"]: item for item in response.json()["items"]}
    finance = {item["key"]: item for item in modules["supply-chain-finance"]["fieldSchema"]}
    agreements = {item["key"]: item for item in modules["stewardship-agreements"]["fieldSchema"]}

    for field_key in ("borrowerCooperativeIds", "borrowerEnterpriseIds"):
        assert finance[field_key]["relationGroup"] == "borrower"
        assert finance[field_key]["minGroupTargets"] == 1
    for field_key in ("serviceProviderCooperativeIds", "serviceProviderEnterpriseIds"):
        assert agreements[field_key]["relationGroup"] == "service-provider"
        assert agreements[field_key]["minGroupTargets"] == 1


def test_every_either_or_subject_pair_has_a_required_relation_group(app_client):
    response = app_client.get("/api/business/modules", headers={"X-RS-Roles": "admin"})
    modules = {item["key"]: item for item in response.json()["items"]}
    expectations = {
        "franchise-bases": ("operator", {"operatorCooperativeIds", "operatorEnterpriseIds"}),
        "maintenance-tasks": ("assignee", {"assigneeFarmerIds", "assigneeCooperativeIds"}),
        "work-logs": ("worker", {"workerFarmerIds", "workerCooperativeIds"}),
        "equipment": ("owner", {"ownerCooperativeIds", "ownerEnterpriseIds"}),
        "material-services": ("applicant", {"applicantFarmerIds", "applicantCooperativeIds"}),
        "harvest-plans": ("operator", {"operatorCooperativeIds", "operatorEnterpriseIds"}),
        "income-estimates": ("subject", {"cooperativeIds", "enterpriseIds"}),
        "performance-dashboards": ("owner", {"ownerCooperativeIds", "ownerEnterpriseIds"}),
        "trade-matches": ("seller", {"sellerCooperativeIds", "sellerEnterpriseIds"}),
        "mobile-service-channels": ("owner", {"ownerCooperativeIds", "ownerEnterpriseIds"}),
    }

    for module_key, (group_name, field_keys) in expectations.items():
        fields = {item["key"]: item for item in modules[module_key]["fieldSchema"]}
        for field_key in field_keys:
            assert fields[field_key]["relationGroup"] == group_name
            assert fields[field_key]["minGroupTargets"] == 1
