from __future__ import annotations

from datetime import datetime, timedelta, timezone


ADMIN_HEADERS = {"X-RS-User": "roadmap-admin", "X-RS-Roles": "admin", "X-RS-Areas": "*"}


def create_block(app_client, code: str):
    response = app_client.post(
        "/api/v2/resources/forest-blocks",
        headers=ADMIN_HEADERS,
        json={
            "blockCode": code, "name": f"测试林班 {code}", "countyCode": "350783", "countyName": "建瓯市",
            "townCode": "350783105", "townName": "小桥镇", "areaMu": 100,
            "geometry": {"type": "Polygon", "coordinates": [[[118.0, 27.0], [118.1, 27.0], [118.1, 27.1], [118.0, 27.1], [118.0, 27.0]]]},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_cost_mvp_uses_cents_idempotency_and_exact_budget_boundaries(app_client):
    create_block(app_client, "COST-YELLOW-001")
    create_block(app_client, "COST-RED-001")
    opened = app_client.post("/api/v2/costs/periods/actions", headers=ADMIN_HEADERS, json={"period": "2026-08", "action": "open"})
    assert opened.status_code == 200
    for code in ("COST-YELLOW-001", "COST-RED-001"):
        budget = app_client.post(
            "/api/v2/costs/budgets", headers=ADMIN_HEADERS,
            json={"period": "2026-08", "blockCode": code, "amount": "1000.00", "yellowThresholdPct": "15", "redThresholdPct": "30"},
        )
        assert budget.status_code == 201, budget.text
    entry_payload = {
        "costType": "adjustment", "blockCode": "COST-YELLOW-001", "amount": "1150.00",
        "occurredOn": "2026-08-19", "sourceType": "acceptance-test", "sourceId": "YELLOW-EDGE", "sourceVersion": 1,
    }
    first = app_client.post("/api/v2/costs/entries", headers={**ADMIN_HEADERS, "Idempotency-Key": "cost-yellow-edge"}, json=entry_payload)
    replay = app_client.post("/api/v2/costs/entries", headers={**ADMIN_HEADERS, "Idempotency-Key": "cost-yellow-edge"}, json=entry_payload)
    assert first.status_code == 201 and replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["amountCents"] == 115000
    red = app_client.post(
        "/api/v2/costs/entries", headers={**ADMIN_HEADERS, "Idempotency-Key": "cost-red-edge"},
        json={**entry_payload, "blockCode": "COST-RED-001", "amount": "1300.00", "sourceId": "RED-EDGE"},
    )
    assert red.status_code == 201
    report = app_client.get("/api/v2/costs/reports/monthly?period=2026-08", headers=ADMIN_HEADERS)
    assert report.status_code == 200
    alerts = {item["blockCode"]: item for item in report.json()["alerts"]}
    assert alerts["COST-YELLOW-001"]["variancePct"] == 15.0
    assert alerts["COST-YELLOW-001"]["level"] == "yellow"
    assert alerts["COST-RED-001"]["variancePct"] == 30.0
    assert alerts["COST-RED-001"]["level"] == "red"


def test_resource_change_requires_human_acceptance_before_version_update(app_client):
    block = create_block(app_client, "CHANGE-BLOCK-001")
    sub = app_client.post(
        "/api/v2/resources/forest-subcompartments", headers=ADMIN_HEADERS,
        json={
            "subcompartmentCode": "CHANGE-SUB-001", "name": "变化核查小班", "forestBlockId": block["id"],
            "areaMu": 20, "bambooSpecies": "毛竹", "ageGroup": "成熟林", "slopeDegree": 18,
            "geometry": {"type": "Polygon", "coordinates": [[[118.01, 27.01], [118.05, 27.01], [118.05, 27.05], [118.01, 27.05], [118.01, 27.01]]]},
        },
    )
    assert sub.status_code == 200, sub.text
    proposed = {"type": "Polygon", "coordinates": [[[118.01, 27.01], [118.06, 27.01], [118.06, 27.06], [118.01, 27.06], [118.01, 27.01]]]}
    job = app_client.post(
        "/api/v2/intelligence/resources/change-jobs", headers=ADMIN_HEADERS,
        json={"subcompartmentId": sub.json()["id"], "baselineSceneId": "scene-before", "comparisonSceneId": "scene-after", "changeType": "boundary", "changedAreaMu": 2, "confidence": 0.93, "proposedGeometry": proposed},
    )
    assert job.status_code == 201, job.text
    blocked = app_client.post(
        f"/api/v2/intelligence/resources/change-jobs/{job.json()['id']}/actions", headers=ADMIN_HEADERS,
        json={"action": "apply", "note": "跳过核查", "expectedVersion": 1},
    )
    assert blocked.status_code == 409
    accepted = app_client.post(
        f"/api/v2/intelligence/resources/change-jobs/{job.json()['id']}/actions", headers=ADMIN_HEADERS,
        json={"action": "accept", "note": "现场核查一致", "expectedVersion": 1},
    )
    assert accepted.status_code == 200
    applied = app_client.post(
        f"/api/v2/intelligence/resources/change-jobs/{job.json()['id']}/actions", headers=ADMIN_HEADERS,
        json={"action": "apply", "note": "更新版本", "expectedVersion": 2},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    assert applied.json()["resultVersion"] == sub.json()["version"] + 1


def test_telemetry_and_command_contracts_are_idempotent_and_receipted(app_client):
    device = app_client.post(
        "/api/v2/iot/devices", headers=ADMIN_HEADERS,
        json={"name": "联调安全帽", "deviceType": "helmet", "vendor": "测试供应商", "status": "active", "connectivityStatus": "unknown", "linkedBlockCodes": []},
    )
    assert device.status_code == 200, device.text
    telemetry_payload = {
        "deviceId": device.json()["id"], "collectedAt": datetime.now(timezone.utc).isoformat(),
        "longitude": 118.03, "latitude": 27.03, "batteryPct": 88, "signalDbm": -67, "sequence": 1,
        "metrics": {"wearing": True}, "rawMessageRef": "object://telemetry/1", "protocol": "mqtt",
    }
    first = app_client.post("/api/v2/iot/telemetry", headers={**ADMIN_HEADERS, "Idempotency-Key": "telemetry-1"}, json=telemetry_payload)
    replay = app_client.post("/api/v2/iot/telemetry", headers={**ADMIN_HEADERS, "Idempotency-Key": "telemetry-1"}, json=telemetry_payload)
    assert first.status_code == 202 and replay.status_code == 202
    assert first.json()["id"] == replay.json()["id"]
    assert replay.json()["duplicate"] is True
    command = app_client.post(
        "/api/v2/iot/commands", headers=ADMIN_HEADERS,
        json={"deviceId": device.json()["id"], "commandType": "reboot", "parameters": {}, "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()},
    )
    assert command.status_code == 202, command.text
    receipt = app_client.post(
        f"/api/v2/iot/commands/{command.json()['id']}/receipt", headers=ADMIN_HEADERS,
        json={"status": "acknowledged", "receiptCode": "OK", "message": "设备已执行", "receivedAt": datetime.now(timezone.utc).isoformat()},
    )
    assert receipt.status_code == 200
    assert receipt.json()["status"] == "acknowledged"


def test_governance_baseline_topics_and_permissions_preserve_eleven_roles(app_client):
    baseline = app_client.get("/api/v2/governance/requirements-baseline", headers=ADMIN_HEADERS)
    assert baseline.status_code == 200
    assert baseline.json()["roleCount"] == 11
    assert {item["key"] for item in baseline.json()["packages"]} == {"BASE-01", "RES-01", "OPS-01", "HAR-01", "LAB-01", "AI-01", "IOT-01", "COST-01", "MOB-01", "COK-01", "SYS-01"}
    topics = app_client.get("/api/v2/cockpit/topics", headers=ADMIN_HEADERS)
    assert topics.status_code == 200
    assert topics.json()["source"] == "live"
    assert [item["key"] for item in topics.json()["topics"]] == ["overview", "emergency", "harvest", "drone", "cost"]
    assert all(metric["definition"] and metric["drilldown"] for topic in topics.json()["topics"] for metric in topic["metrics"])
