from __future__ import annotations

from server.modules import extension_store
from server.v2 import roads


ADMIN_HEADERS = {"X-RS-Roles": "admin", "X-RS-User": "road-admin"}


def test_forest_road_crud_map_maintenance_and_export(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr(extension_store, "v2_extension_json_path", lambda key: tmp_path / f"{key}.json")
    monkeypatch.setattr(roads, "block_by_code", lambda code, **_kwargs: {"blockCode": code, "countyCode": "350703"})
    monkeypatch.setattr(roads, "require_target_block_allowed", lambda *_args, **_kwargs: None)
    payload = {
        "roadCode": "RD-GJ5-001",
        "name": "桂林镇五号林班生产道",
        "roadClass": "operation",
        "surfaceType": "gravel",
        "condition": "fair",
        "widthM": 3.5,
        "linkedBlockCodes": ["GJ5-25-1207-1130"],
        "responsibleUnit": "桂林镇林业站",
        "geometry": {"type": "LineString", "coordinates": [[117.90, 27.31], [117.91, 27.315], [117.92, 27.32]]},
    }
    created = app_client.post("/api/v2/roads", headers=ADMIN_HEADERS, json=payload)
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["roadCode"] == "RD-GJ5-001"
    assert record["lengthKm"] > 0

    listed = app_client.get("/api/v2/roads?q=桂林镇", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    mapped = app_client.get("/api/v2/roads/map.geojson", headers=ADMIN_HEADERS)
    assert mapped.status_code == 200
    assert mapped.json()["features"][0]["geometry"]["type"] == "LineString"

    patched = app_client.patch(
        f"/api/v2/roads/{record['id']}", headers=ADMIN_HEADERS,
        json={"expectedVersion": record["version"], "condition": "poor", "notes": "雨季排水沟损坏"},
    )
    assert patched.status_code == 200
    assert patched.json()["condition"] == "poor"

    maintained = app_client.post(
        f"/api/v2/roads/{record['id']}/maintenance", headers=ADMIN_HEADERS,
        json={"maintenanceType": "drainage", "occurredOn": "2026-09-02", "conditionAfter": "good", "costYuan": 3600, "responsibleUnit": "桂林镇林业站", "note": "修复边沟"},
    )
    assert maintained.status_code == 201
    detailed = app_client.get(f"/api/v2/roads/{record['id']}", headers=ADMIN_HEADERS).json()
    assert detailed["condition"] == "good"
    assert detailed["maintenance"][0]["costYuan"] == 3600

    exported = app_client.get("/api/v2/roads/export.csv", headers=ADMIN_HEADERS)
    assert exported.status_code == 200
    assert "forest-roads.csv" in exported.headers["content-disposition"]
    assert "RD-GJ5-001" in exported.content.decode("utf-8-sig")

    deleted = app_client.delete(f"/api/v2/roads/{record['id']}?expectedVersion={detailed['version']}", headers=ADMIN_HEADERS)
    assert deleted.status_code == 200
    assert deleted.json()["deletedAt"]
    restored = app_client.post(f"/api/v2/roads/{record['id']}/restore", headers=ADMIN_HEADERS)
    assert restored.status_code == 200
    assert restored.json()["deletedAt"] is None


def test_forest_road_rejects_polygon_geometry(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr(extension_store, "v2_extension_json_path", lambda key: tmp_path / f"{key}.json")
    monkeypatch.setattr(roads, "block_by_code", lambda code, **_kwargs: {"blockCode": code, "countyCode": "350703"})
    monkeypatch.setattr(roads, "require_target_block_allowed", lambda *_args, **_kwargs: None)
    response = app_client.post("/api/v2/roads", headers=ADMIN_HEADERS, json={
        "roadCode": "BAD-ROAD", "name": "错误道路", "linkedBlockCodes": ["GJ5-25-1207-1130"],
        "geometry": {"type": "Polygon", "coordinates": [[[117, 27], [118, 27], [118, 28], [117, 27]]]},
    })
    assert response.status_code == 422
