from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

def farmer_properties(**overrides: object) -> dict[str, object]:
    properties: dict[str, object] = {
        "identityType": "resident-id",
        "identityNumber": "350703199001011234",
        "phone": "13800000000",
        "provinceCode": "350000",
        "cityCode": "350700",
        "countyCode": "350703",
        "townCode": "350703105",
        "villageCode": "350703105217",
        "address": "福建省南平市建阳区麻沙镇杜潭村",
        "operationAreaMu": 195,
    }
    properties.update(overrides)
    return properties


def farmer_payload(code: str, **property_overrides: object) -> dict[str, object]:
    return {
        "formVersion": 2,
        "recordCode": code,
        "name": "正式竹农档案",
        "status": "active",
        "properties": farmer_properties(**property_overrides),
    }


def test_farmer_schema_is_a_formal_domain_form_with_stable_relations(app_client):
    response = app_client.get("/api/business/modules", headers={"X-RS-Roles": "admin"})

    assert response.status_code == 200
    module = next(item for item in response.json()["items"] if item["key"] == "farmers")
    fields = {field["key"]: field for field in module["fieldSchema"]}
    assert module["formVersion"] == 2
    assert {
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
    }.issubset(fields)
    assert fields["identityType"]["inputType"] == "dictionary"
    assert fields["identityNumber"]["required"] is True
    assert fields["phone"]["required"] is True
    assert fields["phone"]["pattern"] == r"^1[3-9]\d{9}$"
    for key, level in (
        ("provinceCode", "province"),
        ("cityCode", "city"),
        ("countyCode", "county"),
        ("townCode", "town"),
        ("villageCode", "village"),
    ):
        assert fields[key]["referenceDictionaryCode"] == "administrative-divisions"
        assert fields[key]["referenceLevel"] == level
        assert fields[key]["referenceValueKey"] == "value"
    assert fields["cooperativeIds"]["inputType"] == "business-relation"
    assert fields["cooperativeIds"]["relationType"] == "member-of"
    assert fields["cooperativeIds"]["targetModuleKey"] == "cooperatives"
    assert fields["cooperativeIds"]["referenceValueKey"] == "id"


def test_formal_farmer_requires_domain_fields_and_hydrates_division_labels(app_client):
    missing = app_client.post(
        "/api/business/farmers",
        json=farmer_payload("FARMER-REQUIRED-001", phone=""),
        headers={"X-RS-Roles": "business.farmers.create"},
    )
    invalid_code = app_client.post(
        "/api/business/farmers",
        json=farmer_payload("FARMER-DIVISION-BAD", villageCode="350703105"),
        headers={"X-RS-Roles": "business.farmers.create"},
    )
    created = app_client.post(
        "/api/business/farmers",
        json=farmer_payload("FARMER-FORMAL-001"),
        headers={"X-RS-Roles": "business.farmers.create"},
    )

    assert missing.status_code == 422
    assert "phone" in str(missing.json()["detail"])
    assert invalid_code.status_code == 422
    assert "villageCode" in str(invalid_code.json()["detail"])
    assert created.status_code == 200
    properties = created.json()["properties"]
    assert properties["provinceName"] == "福建省"
    assert properties["cityName"] == "南平市"
    assert properties["countyName"] == "建阳区"
    assert properties["townName"] == "麻沙镇"
    assert properties["villageName"] == "杜潭村"
    assert properties["townVillage"] == "麻沙镇 / 杜潭村"


def test_business_reference_api_and_farmer_links_use_target_record_ids(app_client):
    cooperative = app_client.post(
        "/api/business/cooperatives",
        json={
            "recordCode": "COOP-LINK-001",
            "name": "麻沙合作社",
            "status": "active",
            "properties": {"serviceArea": ["麻沙镇"]},
        },
        headers={"X-RS-Roles": "business.cooperatives.create"},
    )
    assert cooperative.status_code == 200
    cooperative_id = cooperative.json()["id"]

    options = app_client.get(
        "/api/references/business/cooperatives?q=%E9%BA%BB%E6%B2%99",
        headers={"X-RS-Roles": "business.cooperatives.view"},
    )
    assert options.status_code == 200
    assert options.json()["items"][0]["value"] == cooperative_id
    assert options.json()["items"][0]["id"] == cooperative_id

    linked = app_client.post(
        "/api/business/farmers",
        json={
            **farmer_payload("FARMER-COOP-LINK-001"),
            "linkedRecords": [
                {
                    "relationType": "member-of",
                    "targetModuleKey": "cooperatives",
                    "targetRecordId": cooperative_id,
                }
            ],
        },
        headers={"X-RS-Roles": "admin"},
    )
    invalid = app_client.post(
        "/api/business/farmers",
        json={
            **farmer_payload("FARMER-COOP-LINK-BAD"),
            "linkedRecords": [
                {
                    "relationType": "member-of",
                    "targetModuleKey": "cooperatives",
                    "targetRecordId": "00000000-0000-0000-0000-000000000000",
                }
            ],
        },
        headers={"X-RS-Roles": "admin"},
    )

    assert linked.status_code == 200
    assert linked.json()["linkedRecords"][0]["targetRecordId"] == cooperative_id
    assert invalid.status_code == 422
    assert "cooperativeIds" in str(invalid.json()["detail"])


def test_business_form_frontend_uses_form_version_sections_and_normalized_relations():
    script = (ROOT / "admin-business-module.js").read_text(encoding="utf-8")

    assert "moduleSchema: null" in script
    assert "formVersion: 1" in script
    assert "state.formVersion = Number(current?.formVersion || 1)" in script
    assert 'field.inputType === "business-relation"' in script
    assert "function businessLinksFromForm()" in script
    assert "linkedRecords: businessLinksFromForm()" in script
    assert "field.section" in script
    assert "state.formVersion >= 2" in script
    assert "propertiesLabel.hidden" in script


def test_reference_picker_supports_cascading_administrative_queries():
    script = (ROOT / "admin-smart-fields.js").read_text(encoding="utf-8")

    assert "queryProvider = null" in script
    assert "onChange = null" in script
    assert "queryProvider()" in script
    assert "smart-reference-change" in script
    assert "parentCode" in script


def test_formal_business_form_never_serializes_relation_fields_as_property_json():
    script = (ROOT / "admin-business-module.js").read_text(encoding="utf-8")

    assert 'field.inputType !== "business-relation"' in script
    assert "targetRecordId" in script
    assert "targetModuleKey" in script
    assert "relationType" in script
