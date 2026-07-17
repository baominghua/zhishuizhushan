from __future__ import annotations

import io
import importlib
import json
import sys
import zipfile
from types import ModuleType, SimpleNamespace

import pytest
from openpyxl import Workbook

from tests.test_forest_blocks import FakeCursor, install_fake_psycopg


SAMPLE_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [118.20, 26.60],
            [118.21, 26.60],
            [118.21, 26.61],
            [118.20, 26.61],
            [118.20, 26.60],
        ]
    ],
}


def geojson_bytes(*, block_code: str = "IMP-001", include_block_code: bool = True) -> bytes:
    properties = {
        "blockCode": block_code,
        "name": "导入林班一",
        "countyCode": "350703",
        "countyName": "建阳区",
        "townName": "麻沙镇",
        "baseType": "franchise",
        "operationType": "dual_regular",
        "areaMu": 88.2,
        "qualityGrade": "B",
        "riskLevel": "medium",
    }
    if not include_block_code:
        properties.pop("blockCode")
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": SAMPLE_POLYGON,
                }
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


def geojson_feature_bytes(properties: dict[str, object]) -> bytes:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": SAMPLE_POLYGON,
                }
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


def seed_import_scene(scene_id: str = "scene-import-batch-001") -> None:
    seed_import_scenes(scene_id)


def seed_import_scenes(*scene_ids: str) -> None:
    from server.modules import database as database_module

    ids = list(scene_ids) or ["scene-import-batch-001"]
    catalog_path = database_module.get_data_dir() / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "id": scene_id,
                        "name": "Import batch orthophoto",
                        "cogPath": f"cogs/{scene_id}.tif",
                        "bounds": [117.55, 26.05, 118.85, 27.2],
                        "projectId": "zhushan",
                        "areaCode": "350703",
                        "capturedAt": "2026-07-07",
                    }
                    for scene_id in ids
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def reload_imports_module(reload_platform_modules):
    reload_platform_modules()
    import server.modules.imports as imports_module

    importlib.reload(imports_module)
    return imports_module


def postgis_import_batch_row(batch_id: str = "0174b462-9168-445a-92c9-2d7743894684") -> dict[str, object]:
    return {
        "id": batch_id,
        "file_name": "forest.geojson",
        "file_type": "geojson",
        "status": "completed",
        "total_rows": 1,
        "valid_rows": 1,
        "invalid_rows": 0,
        "created_by": None,
        "report_json": {
            "id": batch_id,
            "fileName": "forest.geojson",
            "fileType": "geojson",
            "status": "completed",
            "totalRows": 1,
            "validRows": 1,
            "invalidRows": 0,
            "errors": [],
        },
        "created_at": "2026-07-07T00:00:00+00:00",
        "completed_at": "2026-07-07T00:00:00+00:00",
    }


def csv_bytes() -> bytes:
    return (
        "林班编号,名称,区县编码,区县,乡镇,面积亩,质量等级,健康状态,风险等级\n"
        "CSV-001,导入林班二,350703,建阳区,麻沙镇,42.5,A,normal,low\n"
    ).encode("utf-8")


def xlsx_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["小班编号", "小班名称", "县", "镇", "面积", "质量等级", "健康状态", "风险等级"])
    sheet.append(["XLSX-001", "导入林班三", "建阳区", "麻沙镇", 15.8, "C", "watch", "medium"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def kml_bytes(placemarks: list[dict[str, object]]) -> bytes:
    placemark_markup = []
    for placemark in placemarks:
        rows = "\n".join(
            f"<tr><td>{key}</td><td>{value}</td></tr>"
            for key, value in dict(placemark.get("fields", {})).items()
        )
        coords = " ".join(
            f"{lon},{lat},0"
            for lon, lat in placemark.get(
                "coordinates",
                [
                    (118.20, 26.60),
                    (118.21, 26.60),
                    (118.21, 26.61),
                    (118.20, 26.61),
                    (118.20, 26.60),
                ],
            )
        )
        placemark_markup.append(
            f"""
            <Placemark>
              <name>{placemark["name"]}</name>
              <description><![CDATA[<table>{rows}</table>]]></description>
              <Polygon>
                <outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs>
              </Polygon>
            </Placemark>
            """
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        + "".join(placemark_markup)
        + "</Document></kml>"
    ).encode("utf-8")


def kmz_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "doc.kml",
            kml_bytes(
                [
                    {
                        "name": "13",
                        "fields": {
                            "XBNO": "35078410620204107030",
                            "XSQ": "350784",
                            "XZC": "106",
                            "CGQ": "202",
                            "XBMJ": "64861",
                            "FBF": "Jianou Masha Bamboo Cooperative",
                        },
                    },
                    {
                        "name": "17",
                        "fields": {
                            "XBNO": "35078410620204107031",
                            "XSQ": "350784",
                            "XZC": "106",
                            "CGQ": "202",
                            "XBMJ": "666.6667",
                            "FBF": "Jianou Masha Bamboo Cooperative",
                        },
                    },
                ]
            ),
        )
    return buffer.getvalue()


def ovkml_bytes() -> bytes:
    return kml_bytes(
        [
            {
                "name": "GJ24-25-1216-1422",
                "fields": {
                    "FID": "46",
                    "&#24207;&#21495;": "24",
                    "&#21517;&#31216;": "GJ24-25-1216-1422",
                    "&#38754;&#31215;": "27336.457&#24179;&#26041;&#31859;",
                    "&#38271;&#24230;": "1177.669&#31859;",
                },
            }
        ]
    )


def ovobj_bytes() -> bytes:
    table = """
    <![CDATA[
    <html><body><table>
      <tr><td>FID</td><td>0</td></tr>
      <tr><td>YZDBH</td><td>0350783105206GDYMSY03631</td></tr>
      <tr><td>SYQJSSJ</td><td>2033/6/30</td></tr>
      <tr><td>FBF</td><td>Jianou Xiaoqiao Shangtun Village Committee</td></tr>
      <tr><td>QLXZ</td><td>202</td></tr>
      <tr><td>FZMJ</td><td>56</td></tr>
      <tr><td>ZDSZB</td><td>north</td></tr>
      <tr><td>LZ</td><td>2</td></tr>
    </table></body></html>
    ]]>
    """
    return b"OviO" + b"\x00" * 128 + table.encode("utf-8") + b"\x10\x90\x80"


def test_import_geojson_creates_block_and_persists_report(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("forest.geojson", io.BytesIO(geojson_bytes()), "application/geo+json")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["totalRows"] == 1
    assert body["validRows"] == 1
    assert body["invalidRows"] == 0
    assert body["errors"] == []

    listed = app_client.get("/api/forest-blocks?q=导入林班一")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["blockCode"] == "IMP-001"

    batch_id = body["id"]
    batch = app_client.get(f"/api/imports/{batch_id}", headers={"X-RS-Roles": "admin"})
    report = app_client.get(f"/api/imports/{batch_id}/report", headers={"X-RS-Roles": "admin"})

    assert batch.status_code == 200
    assert report.status_code == 200
    assert batch.json()["id"] == batch_id
    assert report.json()["totalRows"] == 1


def test_import_report_survives_in_memory_cache_clear(app_client):
    from server.modules import imports as imports_module

    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("forest.geojson", io.BytesIO(geojson_bytes(block_code="IMP-CACHE-001")), "application/geo+json")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    assert response.status_code == 200
    batch_id = response.json()["id"]

    imports_module.IMPORT_REPORTS.clear()
    batch = app_client.get(f"/api/imports/{batch_id}", headers={"X-RS-Roles": "admin"})
    report = app_client.get(f"/api/imports/{batch_id}/report", headers={"X-RS-Roles": "admin"})

    assert batch.status_code == 200
    assert batch.json()["id"] == batch_id
    assert batch.json()["fileName"] == "forest.geojson"
    assert report.status_code == 200
    assert report.json()["validRows"] == 1


def test_import_batches_are_listed_filtered_and_soft_deleted(app_client):
    first = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("formal-batch-a.geojson", io.BytesIO(geojson_bytes(block_code="BATCH-LIST-001")), "application/geo+json")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    second = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("formal-batch-b.geojson", io.BytesIO(geojson_bytes(block_code="BATCH-LIST-002")), "application/geo+json")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    assert first.status_code == 200
    assert second.status_code == 200

    listed = app_client.get("/api/imports/forest-blocks/batches?status=completed", headers={"X-RS-Roles": "admin"})
    filtered = app_client.get("/api/imports/forest-blocks/batches?q=formal-batch-a", headers={"X-RS-Roles": "admin"})

    assert listed.status_code == 200
    assert listed.json()["total"] >= 2
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["fileName"] == "formal-batch-a.geojson"
    assert filtered.json()["items"][0]["validRows"] == 1

    denied = app_client.delete(
        f"/api/imports/{first.json()['id']}",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    deleted = app_client.delete(
        f"/api/imports/{first.json()['id']}",
        headers={"X-RS-Roles": "admin"},
    )
    filtered_after_delete = app_client.get(
        "/api/imports/forest-blocks/batches?q=formal-batch-a",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "imports.forestBlocks.delete" in denied.json()["detail"]
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert filtered_after_delete.status_code == 200
    assert filtered_after_delete.json()["total"] == 0


def test_deleted_import_batch_can_be_listed_and_restored(app_client):
    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "restore-batch.geojson",
                io.BytesIO(geojson_bytes(block_code="RESTORE-BATCH-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    assert imported.status_code == 200
    batch_id = imported.json()["id"]

    deleted = app_client.delete(
        f"/api/imports/{batch_id}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "deleter"},
    )
    normal_list = app_client.get(
        "/api/imports/forest-blocks/batches?q=restore-batch",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    denied_deleted_status_list = app_client.get(
        "/api/imports/forest-blocks/batches?status=deleted",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    status_deleted_list = app_client.get(
        "/api/imports/forest-blocks/batches?status=deleted",
        headers={"X-RS-Roles": "admin"},
    )
    deleted_list = app_client.get(
        "/api/imports/forest-blocks/batches?q=restore-batch&includeDeleted=true",
        headers={"X-RS-Roles": "admin"},
    )
    denied_restore = app_client.post(
        f"/api/imports/{batch_id}/restore",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    restored = app_client.post(
        f"/api/imports/{batch_id}/restore",
        headers={"X-RS-Roles": "admin", "X-RS-User": "restorer"},
    )
    active_list = app_client.get(
        "/api/imports/forest-blocks/batches?q=restore-batch",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    report = app_client.get(
        f"/api/imports/{batch_id}/report",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )

    assert deleted.status_code == 200
    assert normal_list.status_code == 200
    assert normal_list.json()["total"] == 0
    assert denied_deleted_status_list.status_code == 403
    assert "imports.forestBlocks.restore" in denied_deleted_status_list.json()["detail"]
    assert status_deleted_list.status_code == 200
    assert status_deleted_list.json()["total"] == 1
    assert status_deleted_list.json()["items"][0]["id"] == batch_id
    assert deleted_list.status_code == 200
    assert deleted_list.json()["total"] == 1
    assert deleted_list.json()["items"][0]["status"] == "deleted"
    assert deleted_list.json()["items"][0]["deletedAt"]
    assert denied_restore.status_code == 403
    assert "imports.forestBlocks.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    assert restored.json()["ok"] is True
    assert restored.json()["restored"] == batch_id
    assert restored.json()["report"]["status"] == "completed"
    assert restored.json()["event"]["action"] == "restore"
    assert restored.json()["event"]["actor"] == "restorer"
    assert active_list.status_code == 200
    assert active_list.json()["total"] == 1
    assert report.json()["deletedAt"] is None
    assert report.json()["auditEvents"][-1]["action"] == "restore"


def test_import_action_permissions_control_batch_workflow(app_client):
    seed_import_scene("scene-import-action-permission")

    denied_create = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "action-permission-denied.geojson",
                io.BytesIO(geojson_bytes(block_code="IMPORT-ACTION-DENIED")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    created = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "action-permission.geojson",
                io.BytesIO(geojson_bytes(block_code="IMPORT-ACTION-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "imports.forestBlocks.create"},
    )
    assert created.status_code == 200
    batch_id = created.json()["id"]

    denied_review = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "ready"},
        headers={"X-RS-Roles": "imports.forestBlocks.create"},
    )
    reviewed = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "ready"},
        headers={"X-RS-Roles": "imports.forestBlocks.review"},
    )
    denied_link = app_client.post(
        f"/api/imports/{batch_id}/publish-readiness",
        json={"sceneId": "scene-import-action-permission", "publishLayer": False},
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    linked = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-import-action-permission", "publishLayer": False},
        headers={"X-RS-Roles": "imports.sceneLayers.link"},
    )
    denied_export = app_client.get(
        f"/api/imports/{batch_id}/errors.csv",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    exported = app_client.get(
        f"/api/imports/{batch_id}/errors.csv",
        headers={"X-RS-Roles": "imports.forestBlocks.export"},
    )
    denied_rollback = app_client.post(
        f"/api/imports/{batch_id}/rollback",
        headers={"X-RS-Roles": "imports.forestBlocks.review"},
    )
    rolled_back = app_client.post(
        f"/api/imports/{batch_id}/rollback",
        headers={"X-RS-Roles": "imports.forestBlocks.rollback"},
    )
    denied_delete = app_client.delete(
        f"/api/imports/{batch_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    deleted = app_client.delete(
        f"/api/imports/{batch_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.delete"},
    )
    denied_restore = app_client.post(
        f"/api/imports/{batch_id}/restore",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    restored = app_client.post(
        f"/api/imports/{batch_id}/restore",
        headers={"X-RS-Roles": "imports.forestBlocks.restore"},
    )

    assert denied_create.status_code == 403
    assert "imports.forestBlocks.create" in denied_create.json()["detail"]
    assert created.status_code == 200
    assert denied_review.status_code == 403
    assert "imports.forestBlocks.review" in denied_review.json()["detail"]
    assert reviewed.status_code == 200
    assert denied_link.status_code == 403
    assert "imports.sceneLayers.link" in denied_link.json()["detail"]
    assert linked.status_code == 200
    assert denied_export.status_code == 403
    assert "imports.forestBlocks.export" in denied_export.json()["detail"]
    assert exported.status_code == 200
    assert denied_rollback.status_code == 403
    assert "imports.forestBlocks.rollback" in denied_rollback.json()["detail"]
    assert rolled_back.status_code == 200
    assert denied_delete.status_code == 403
    assert "imports.forestBlocks.delete" in denied_delete.json()["detail"]
    assert deleted.status_code == 200
    assert denied_restore.status_code == 403
    assert "imports.forestBlocks.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200


def test_import_batch_detail_and_report_require_view_permission(app_client):
    created = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "detail-permission.geojson",
                io.BytesIO(geojson_bytes(block_code="IMPORT-DETAIL-PERM-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "imports.forestBlocks.create"},
    )
    assert created.status_code == 200
    batch_id = created.json()["id"]

    denied_detail = app_client.get(
        f"/api/imports/{batch_id}",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    denied_report = app_client.get(
        f"/api/imports/{batch_id}/report",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    allowed_detail = app_client.get(
        f"/api/imports/{batch_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    allowed_report = app_client.get(
        f"/api/imports/{batch_id}/report",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )

    assert denied_detail.status_code == 403
    assert "imports.forestBlocks.view" in denied_detail.json()["detail"]
    assert denied_report.status_code == 403
    assert "imports.forestBlocks.view" in denied_report.json()["detail"]
    assert allowed_detail.status_code == 200
    assert allowed_detail.json()["id"] == batch_id
    assert allowed_report.status_code == 200
    assert allowed_report.json()["id"] == batch_id


def test_deleted_import_batch_detail_requires_restore_permission(app_client):
    created = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "deleted-detail-permission.geojson",
                io.BytesIO(geojson_bytes(block_code="IMPORT-DELETED-DETAIL-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "imports.forestBlocks.create"},
    )
    assert created.status_code == 200
    batch_id = created.json()["id"]
    deleted = app_client.delete(
        f"/api/imports/{batch_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.delete"},
    )
    assert deleted.status_code == 200

    denied_detail = app_client.get(
        f"/api/imports/{batch_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    denied_report = app_client.get(
        f"/api/imports/{batch_id}/report",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    allowed_detail = app_client.get(
        f"/api/imports/{batch_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.restore"},
    )
    allowed_report = app_client.get(
        f"/api/imports/{batch_id}/report",
        headers={"X-RS-Roles": "imports.forestBlocks.restore"},
    )

    assert denied_detail.status_code == 403
    assert "imports.forestBlocks.restore" in denied_detail.json()["detail"]
    assert denied_report.status_code == 403
    assert "imports.forestBlocks.restore" in denied_report.json()["detail"]
    assert allowed_detail.status_code == 200
    assert allowed_detail.json()["status"] == "deleted"
    assert allowed_report.status_code == 200
    assert allowed_report.json()["status"] == "deleted"


def test_import_batch_list_requires_view_permission(app_client):
    created = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "list-permission.geojson",
                io.BytesIO(geojson_bytes(block_code="IMPORT-LIST-PERM-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "imports.forestBlocks.create"},
    )
    assert created.status_code == 200

    denied = app_client.get(
        "/api/imports/forest-blocks/batches?q=list-permission",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    allowed = app_client.get(
        "/api/imports/forest-blocks/batches?q=list-permission",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )

    assert denied.status_code == 403
    assert "imports.forestBlocks.view" in denied.json()["detail"]
    assert allowed.status_code == 200
    assert allowed.json()["total"] == 1


def test_import_source_listing_requires_view_permission(app_client):
    denied = app_client.get(
        "/api/imports/forest-blocks/sources",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    allowed = app_client.get(
        "/api/imports/forest-blocks/sources",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )

    assert denied.status_code == 403
    assert "imports.forestBlocks.view" in denied.json()["detail"]
    assert allowed.status_code == 200
    assert "items" in allowed.json()


def test_role_data_scopes_limit_import_batches_audit_events_and_quality_issues(app_client):
    from server.modules import imports as imports_module

    app_client.post(
        "/api/admin/roles",
        json={
            "roleCode": "import_scope_viewer",
            "name": "Import Scope Viewer",
            "status": "active",
            "permissions": ["imports.forestBlocks.view"],
            "menuModules": ["imports"],
            "dataScopes": {
                "areas": ["350703"],
                "towns": ["350703101"],
                "blockCodes": ["IMPORT-SCOPE-VISIBLE"],
            },
        },
        headers={"X-RS-Roles": "admin"},
    )
    visible = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "scope-visible.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "blockCode": "IMPORT-SCOPE-VISIBLE",
                            "name": "范围内成果",
                            "countyCode": "350703",
                            "countyName": "建阳区",
                            "townCode": "350703101",
                            "townName": "麻沙镇",
                            "villageCode": "350703101001",
                            "villageName": "黄坑村",
                            "areaMu": 16.8,
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    hidden = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "scope-hidden.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "blockCode": "IMPORT-SCOPE-HIDDEN",
                            "name": "范围外成果",
                            "countyCode": "350784",
                            "countyName": "建瓯市",
                            "townCode": "350784101",
                            "townName": "小桥镇",
                            "villageCode": "350784101001",
                            "villageName": "上屯村",
                            "areaMu": 21.6,
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    assert visible.status_code == 200
    assert hidden.status_code == 200
    visible_id = visible.json()["id"]
    hidden_id = hidden.json()["id"]

    for batch_id, finding in (
        (visible_id, "范围内批次质检待处理"),
        (hidden_id, "范围外批次质检待处理"),
    ):
        report = imports_module.get_report_or_404(batch_id)
        report["qualityStatus"] = "warning"
        report["qualityFindings"] = [finding]
        report["publishRiskStatus"] = "warning"
        imports_module.save_import_report(report)
    imports_module.IMPORT_REPORTS.clear()

    headers = {"X-RS-Roles": "import_scope_viewer"}
    batches = app_client.get("/api/imports/forest-blocks/batches?q=scope-", headers=headers)
    audit_events = app_client.get("/api/imports/forest-blocks/audit-events?q=scope-", headers=headers)
    quality_issues = app_client.get("/api/imports/forest-blocks/quality-issues?q=scope-", headers=headers)
    visible_detail = app_client.get(f"/api/imports/{visible_id}", headers=headers)
    hidden_detail = app_client.get(f"/api/imports/{hidden_id}", headers=headers)

    assert batches.status_code == 200
    assert batches.json()["total"] == 1
    assert [item["id"] for item in batches.json()["items"]] == [visible_id]
    assert audit_events.status_code == 200
    assert audit_events.json()["total"] == 1
    assert {item["batchId"] for item in audit_events.json()["items"]} == {visible_id}
    assert quality_issues.status_code == 200
    assert quality_issues.json()["total"] == 1
    assert {item["batchId"] for item in quality_issues.json()["items"]} == {visible_id}
    assert visible_detail.status_code == 200
    assert hidden_detail.status_code == 404


def test_import_batch_can_be_reviewed_with_audit_events_and_filtered(app_client):
    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "reviewed-batch.geojson",
                io.BytesIO(geojson_bytes(block_code="REVIEW-BLOCK-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    assert imported.status_code == 200
    batch_id = imported.json()["id"]

    denied = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "ok"},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    approved = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "图斑、林权和影像追溯通过"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
    )
    report = app_client.get(f"/api/imports/{batch_id}/report", headers={"X-RS-Roles": "admin"})
    filtered = app_client.get(
        "/api/imports/forest-blocks/batches?reviewStatus=approved",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "imports.forestBlocks.review" in denied.json()["detail"]
    assert approved.status_code == 200
    body = approved.json()
    assert body["ok"] is True
    assert body["id"] == batch_id
    assert body["reviewStatus"] == "approved"
    assert body["event"]["action"] == "review"
    assert body["event"]["decision"] == "approved"
    assert body["event"]["actor"] == "reviewer"
    assert body["report"]["status"] == "completed"
    assert body["report"]["reviewStatus"] == "approved"
    assert body["report"]["reviewComment"] == "图斑、林权和影像追溯通过"
    assert body["report"]["reviewEvents"][-1] == body["event"]
    assert report.status_code == 200
    assert report.json()["reviewStatus"] == "approved"
    assert report.json()["reviewEvents"][-1]["actor"] == "reviewer"
    assert filtered.status_code == 200
    assert any(item["id"] == batch_id for item in filtered.json()["items"])


def test_import_batches_can_filter_by_quality_and_publish_risk(app_client):
    from server.modules import imports as imports_module

    warning_report = imports_module.build_report(
        batch_id="batch-quality-warning",
        file_name="quality-warning.geojson",
        total_rows=2,
        valid_rows=1,
        invalid_rows=1,
        errors=[],
    )
    warning_report.update(
        {
            "qualityStatus": "warning",
            "publishRiskStatus": "warning",
            "reviewRecommendation": "needs_correction",
        }
    )
    clear_report = imports_module.build_report(
        batch_id="batch-quality-clear",
        file_name="quality-clear.geojson",
        total_rows=1,
        valid_rows=1,
        invalid_rows=0,
        errors=[],
    )
    clear_report.update(
        {
            "qualityStatus": "passed",
            "publishRiskStatus": "clear",
            "reviewRecommendation": "approved",
        }
    )
    imports_module.save_import_report(warning_report)
    imports_module.save_import_report(clear_report)
    imports_module.IMPORT_REPORTS.clear()

    filtered = app_client.get(
        "/api/imports/forest-blocks/batches?qualityStatus=warning&publishRiskStatus=warning",
        headers={"X-RS-Roles": "admin"},
    )

    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == "batch-quality-warning"
    assert filtered.json()["items"][0]["reviewRecommendation"] == "needs_correction"


def test_import_workflow_summary_counts_review_link_and_quality_state(app_client):
    from server.modules import imports as imports_module

    pending_report = imports_module.build_report(
        batch_id="workflow-pending-review",
        file_name="pending-review.geojson",
        total_rows=1,
        valid_rows=1,
        invalid_rows=0,
        errors=[],
    )
    approved_unlinked = imports_module.build_report(
        batch_id="workflow-approved-unlinked",
        file_name="approved-unlinked.geojson",
        total_rows=1,
        valid_rows=1,
        invalid_rows=0,
        errors=[],
    )
    approved_unlinked.update(
        {
            "reviewStatus": "approved",
            "qualityStatus": "passed",
            "publishRiskStatus": "clear",
            "reviewRecommendation": "approved",
        }
    )
    linked_report = imports_module.build_report(
        batch_id="workflow-linked",
        file_name="linked.geojson",
        total_rows=1,
        valid_rows=1,
        invalid_rows=0,
        errors=[],
    )
    linked_report.update(
        {
            "reviewStatus": "approved",
            "qualityStatus": "passed",
            "publishRiskStatus": "clear",
            "imageryLinks": [{"sceneId": "scene-workflow-linked", "layerRecordCode": "IMPORT-LAYER-workflow-linked"}],
        }
    )
    blocked_report = imports_module.build_report(
        batch_id="workflow-blocked",
        file_name="blocked.geojson",
        total_rows=2,
        valid_rows=1,
        invalid_rows=1,
        errors=[{"row": 2, "message": "name is required"}],
    )
    blocked_report.update(
        {
            "reviewStatus": "rejected",
            "reviewComment": "fix invalid rows",
            "qualityStatus": "warning",
            "publishRiskStatus": "warning",
        }
    )
    deleted_report = imports_module.build_report(
        batch_id="workflow-deleted",
        file_name="deleted.geojson",
        total_rows=1,
        valid_rows=1,
        invalid_rows=0,
        errors=[],
    )
    deleted_report.update({"status": "deleted", "deletedAt": "2026-07-07T00:00:00+00:00"})
    for report in [pending_report, approved_unlinked, linked_report, blocked_report, deleted_report]:
        imports_module.save_import_report(report)

    denied = app_client.get(
        "/api/imports/forest-blocks/workflow-summary",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    summary = app_client.get(
        "/api/imports/forest-blocks/workflow-summary",
        headers={"X-RS-Roles": "admin"},
    )
    denied_export = app_client.get(
        "/api/imports/forest-blocks/workflow-summary.json",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    exported = app_client.get(
        "/api/imports/forest-blocks/workflow-summary.json",
        headers={"X-RS-Roles": "imports.forestBlocks.export"},
    )

    assert denied.status_code == 403
    assert "imports.forestBlocks.view" in denied.json()["detail"]
    assert summary.status_code == 200
    body = summary.json()
    assert body["activeBatchTotal"] == 4
    assert body["pendingReviewBatches"] == 1
    assert body["approvedUnlinkedBatches"] == 1
    assert body["linkedBatches"] == 1
    assert body["readyForLayerLinkBatches"] == 1
    assert body["openQualityIssues"] >= 2
    assert body["blockedQualityIssues"] >= 2
    assert body["needsAttentionTotal"] >= 4
    assert body["cards"][0]["key"] == "pendingReviewBatches"
    assert body["cards"][1]["key"] == "approvedUnlinkedBatches"
    card_hrefs = {card["key"]: card["href"] for card in body["cards"]}
    assert card_hrefs["pendingReviewBatches"] == "admin-imports.html?reviewStatus=pending"
    assert card_hrefs["approvedUnlinkedBatches"] == "admin-imports.html?workflowQueue=approvedUnlinked"
    assert card_hrefs["readyForLayerLinkBatches"] == "admin-imports.html?workflowQueue=readyForLayerLink"
    assert card_hrefs["blockedQualityIssues"] == "admin-imports.html?qualityIssueStatus=open"
    assert denied_export.status_code == 403
    assert "imports.forestBlocks.export" in denied_export.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "import-workflow-summary.json" in exported.headers["content-disposition"]
    exported_body = exported.json()
    assert exported_body["pendingReviewBatches"] == 1
    assert exported_body["readyForLayerLinkBatches"] == 1
    assert exported_body["exportedAt"]

    approved_queue = app_client.get(
        "/api/imports/forest-blocks/batches?workflowQueue=approvedUnlinked",
        headers={"X-RS-Roles": "admin"},
    )
    ready_queue = app_client.get(
        "/api/imports/forest-blocks/batches?workflowQueue=readyForLayerLink",
        headers={"X-RS-Roles": "admin"},
    )
    assert approved_queue.status_code == 200
    assert [item["id"] for item in approved_queue.json()["items"]] == ["workflow-approved-unlinked"]
    assert ready_queue.status_code == 200
    assert [item["id"] for item in ready_queue.json()["items"]] == ["workflow-approved-unlinked"]


def test_import_batch_acceptance_receipt_can_be_exported(app_client):
    seed_import_scene("scene-acceptance-receipt")
    created = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "acceptance-receipt.geojson",
                io.BytesIO(geojson_bytes(block_code="ACCEPTANCE-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    assert created.status_code == 200
    batch_id = created.json()["id"]
    reviewed = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "ready for delivery receipt"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
    )
    linked = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-acceptance-receipt", "publishLayer": False},
        headers={"X-RS-Roles": "admin", "X-RS-User": "publisher"},
    )

    denied = app_client.get(
        f"/api/imports/{batch_id}/acceptance-receipt.json",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    exported = app_client.get(
        f"/api/imports/{batch_id}/acceptance-receipt.json",
        headers={"X-RS-Roles": "imports.forestBlocks.export", "X-RS-User": "receipt-exporter"},
    )

    assert reviewed.status_code == 200
    assert linked.status_code == 200
    assert denied.status_code == 403
    assert "imports.forestBlocks.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert f"import-acceptance-receipt-{batch_id}.json" in exported.headers["content-disposition"]
    body = exported.json()
    assert body["receiptType"] == "import-batch-acceptance"
    assert body["exportedBy"] == "receipt-exporter"
    assert body["exportPermission"] == "imports.forestBlocks.export"
    assert body["exportRoles"] == ["imports.forestBlocks.export"]
    assert body["exportDataScopes"] == {}
    assert body["batch"]["id"] == batch_id
    assert body["summary"]["validRows"] == 1
    assert body["summary"]["reviewStatus"] == "approved"
    assert body["summary"]["linkedSceneCount"] == 1
    assert body["imageryLinks"][0]["sceneId"] == "scene-acceptance-receipt"
    assert [event["action"] for event in body["auditEvents"]] == [
        "import",
        "review",
        "link-scene-layer",
        "export-acceptance-receipt",
    ]
    assert body["auditEvents"][-1]["actor"] == "receipt-exporter"
    assert body["auditEvents"][-1]["summary"]["permission"] == "imports.forestBlocks.export"
    assert body["qualityIssues"] == []
    assert body["exportedAt"]
    audit_events = app_client.get(
        f"/api/imports/forest-blocks/audit-events?batchId={batch_id}&action=export-acceptance-receipt",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    assert audit_events.status_code == 200
    assert audit_events.json()["total"] == 1
    assert audit_events.json()["items"][0]["actor"] == "receipt-exporter"


def test_import_batch_acceptance_status_can_be_updated_and_receipted(app_client):
    created = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "acceptance-status.geojson",
                io.BytesIO(geojson_bytes(block_code="ACCEPTANCE-STATUS-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    assert created.status_code == 200
    batch_id = created.json()["id"]
    reviewed = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "ready for acceptance"},
        headers={"X-RS-Roles": "imports.forestBlocks.review", "X-RS-User": "reviewer"},
    )

    denied = app_client.post(
        f"/api/imports/{batch_id}/acceptance",
        json={"status": "accepted", "comment": "ok"},
        headers={"X-RS-Roles": "imports.forestBlocks.export"},
    )
    accepted = app_client.post(
        f"/api/imports/{batch_id}/acceptance",
        json={"status": "accepted", "comment": "图档一致，准予入库验收"},
        headers={"X-RS-Roles": "imports.forestBlocks.acceptance", "X-RS-User": "acceptor"},
    )
    report = app_client.get(f"/api/imports/{batch_id}/report", headers={"X-RS-Roles": "admin"})
    receipt = app_client.get(
        f"/api/imports/{batch_id}/acceptance-receipt.json",
        headers={"X-RS-Roles": "imports.forestBlocks.export"},
    )

    assert reviewed.status_code == 200
    assert denied.status_code == 403
    assert "imports.forestBlocks.acceptance" in denied.json()["detail"]
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["ok"] is True
    assert body["acceptanceStatus"] == "accepted"
    assert body["acceptedBy"] == "acceptor"
    assert body["event"]["action"] == "acceptance"
    assert body["event"]["status"] == "accepted"
    assert body["event"]["actor"] == "acceptor"
    assert body["report"]["acceptanceEvents"][-1] == body["event"]
    assert report.status_code == 200
    assert report.json()["acceptanceStatus"] == "accepted"
    assert report.json()["acceptanceComment"] == "图档一致，准予入库验收"
    assert receipt.status_code == 200
    receipt_body = receipt.json()
    assert receipt_body["summary"]["acceptanceStatus"] == "accepted"
    assert receipt_body["summary"]["acceptedBy"] == "acceptor"
    assert receipt_body["acceptanceEvents"][-1]["comment"] == "图档一致，准予入库验收"


def test_import_delivery_packages_roll_up_acceptance_scene_delivery_and_export(app_client):
    scene_id = "scene-delivery-package"
    block_code = "DELIVERY-PKG-001"
    seed_import_scene(scene_id)
    created = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "delivery-package.geojson",
                io.BytesIO(geojson_bytes(block_code=block_code)),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    assert created.status_code == 200
    batch_id = created.json()["id"]

    reviewed = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "ready for delivery package"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
    )
    linked = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": scene_id, "publishLayer": True},
        headers={"X-RS-Roles": "admin", "X-RS-User": "publisher"},
    )
    scene_published = app_client.post(
        f"/api/scenes/{scene_id}/publish-layer",
        json={"name": "Delivery package scene", "linkedBlockCodes": [block_code]},
        headers={"X-RS-Roles": "admin", "X-RS-User": "publisher"},
    )
    accepted = app_client.post(
        f"/api/imports/{batch_id}/acceptance",
        json={"status": "accepted", "comment": "accepted for delivery package"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "acceptor"},
    )
    delivered = app_client.post(
        f"/api/scenes/{scene_id}/delivery",
        json={"status": "delivered", "comment": "delivery materials complete"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "delivery-user"},
    )
    denied_export = app_client.get(
        "/api/imports/forest-blocks/delivery-packages.csv",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    packages = app_client.get(
        "/api/imports/forest-blocks/delivery-packages?status=ready&deliveryStatus=delivered",
        headers={"X-RS-Roles": "admin"},
    )
    linked_block_packages = app_client.get(
        f"/api/imports/forest-blocks/delivery-packages?linkedBlockCode={block_code}",
        headers={"X-RS-Roles": "admin"},
    )
    exported = app_client.get(
        "/api/imports/forest-blocks/delivery-packages.csv?status=ready",
        headers={"X-RS-Roles": "imports.forestBlocks.export"},
    )
    denied_json_export = app_client.get(
        "/api/imports/forest-blocks/delivery-packages.json",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    json_exported = app_client.get(
        "/api/imports/forest-blocks/delivery-packages.json?status=ready",
        headers={"X-RS-Roles": "imports.forestBlocks.export"},
    )
    denied_package_receipt = app_client.get(
        f"/api/imports/{batch_id}/delivery-package-receipt.json",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    package_receipt = app_client.get(
        f"/api/imports/{batch_id}/delivery-package-receipt.json",
        headers={"X-RS-Roles": "imports.forestBlocks.export", "X-RS-User": "package-exporter"},
    )

    assert reviewed.status_code == 200
    assert linked.status_code == 200
    assert scene_published.status_code == 200
    assert accepted.status_code == 200
    assert delivered.status_code == 200
    assert denied_export.status_code == 403
    assert packages.status_code == 200
    body = packages.json()
    assert body["summary"]["packageTotal"] == 1
    assert body["summary"]["readyPackages"] == 1
    assert body["items"][0]["batchId"] == batch_id
    assert body["items"][0]["packageStatus"] == "ready"
    assert body["items"][0]["acceptanceStatus"] == "accepted"
    assert body["items"][0]["deliveryStatus"] == "delivered"
    assert body["items"][0]["linkedBlockCount"] == 1
    assert body["items"][0]["linkedSceneCount"] == 1
    assert body["items"][0]["deliveredSceneCount"] == 1
    assert body["items"][0]["publishedLayerCount"] >= 1
    assert body["items"][0]["blockingReasons"] == []
    assert body["items"][0]["scenes"][0]["sceneId"] == scene_id
    assert body["items"][0]["scenes"][0]["deliveryStatus"] == "delivered"
    assert body["items"][0]["acceptanceReceiptUrl"] == f"/api/imports/{batch_id}/acceptance-receipt.json"
    assert body["items"][0]["primarySceneId"] == scene_id
    assert body["items"][0]["primarySceneDeliveryReceiptUrl"] == f"/api/scenes/{scene_id}/delivery-receipt.json"
    assert body["items"][0]["sceneDeliveryReceiptUrls"] == [
        {"sceneId": scene_id, "url": f"/api/scenes/{scene_id}/delivery-receipt.json"}
    ]
    assert body["items"][0]["scenes"][0]["deliveryReceiptUrl"] == f"/api/scenes/{scene_id}/delivery-receipt.json"
    assert linked_block_packages.status_code == 200
    assert [item["batchId"] for item in linked_block_packages.json()["items"]] == [batch_id]
    assert exported.status_code == 200
    assert "import-delivery-packages.csv" in exported.headers["content-disposition"]
    csv_text = exported.content.decode("utf-8-sig")
    assert "batchId,fileName,status,packageStatus,acceptanceStatus,deliveryStatus" in csv_text.splitlines()[0]
    assert batch_id in csv_text
    assert "ready" in csv_text
    assert denied_json_export.status_code == 403
    assert "imports.forestBlocks.export" in denied_json_export.json()["detail"]
    assert json_exported.status_code == 200
    assert "import-delivery-packages.json" in json_exported.headers["content-disposition"]
    json_body = json_exported.json()
    assert json_body["receiptType"] == "import-delivery-packages"
    assert json_body["summary"]["readyPackages"] == 1
    assert json_body["items"][0]["batchId"] == batch_id
    assert json_body["items"][0]["scenes"][0]["sceneId"] == scene_id
    assert json_body["exportedAt"]
    assert denied_package_receipt.status_code == 403
    assert "imports.forestBlocks.export" in denied_package_receipt.json()["detail"]
    assert package_receipt.status_code == 200
    assert f"import-delivery-package-receipt-{batch_id}.json" in package_receipt.headers["content-disposition"]
    package_body = package_receipt.json()
    assert package_body["receiptType"] == "import-delivery-package"
    assert package_body["exportedBy"] == "package-exporter"
    assert package_body["summary"]["batchId"] == batch_id
    assert package_body["summary"]["packageStatus"] == "ready"
    assert package_body["summary"]["readyForDelivery"] is True
    assert package_body["deliveryPackage"]["batchId"] == batch_id
    assert package_body["deliveryPackage"]["acceptanceReceiptUrl"] == f"/api/imports/{batch_id}/acceptance-receipt.json"
    assert package_body["deliveryPackage"]["sceneDeliveryReceiptUrls"] == [
        {"sceneId": scene_id, "url": f"/api/scenes/{scene_id}/delivery-receipt.json"}
    ]
    assert package_body["deliveryPackage"]["mapLayerPublicationReceiptUrls"]
    assert package_body["auditEvents"][-1]["action"] == "export-delivery-package-receipt"
    assert package_body["auditEvents"][-1]["actor"] == "package-exporter"


def test_import_delivery_packages_explain_pending_blockers(app_client):
    created = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "delivery-package-pending.geojson",
                io.BytesIO(geojson_bytes(block_code="DELIVERY-PENDING-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    assert created.status_code == 200
    batch_id = created.json()["id"]

    packages = app_client.get(
        "/api/imports/forest-blocks/delivery-packages?status=awaiting_review",
        headers={"X-RS-Roles": "admin"},
    )

    assert packages.status_code == 200
    body = packages.json()
    assert [item["batchId"] for item in body["items"]] == [batch_id]
    item = body["items"][0]
    assert item["packageStatus"] == "awaiting_review"
    assert item["deliveryStatus"] == "pending"
    assert item["linkedSceneCount"] == 0
    assert "review_not_approved" in item["blockingReasons"]
    assert "acceptance_not_accepted" in item["blockingReasons"]
    assert "no_linked_scene" in item["blockingReasons"]
    assert body["summary"]["awaitingReviewPackages"] == 1


def test_import_delivery_scene_item_does_not_mask_catalog_outage(monkeypatch):
    from fastapi import HTTPException

    from server.modules import imports as imports_module
    from server.modules.auth import AuthContext

    def unavailable_scene(_scene_id, _context):
        raise HTTPException(status_code=503, detail="Remote sensing catalog database is unavailable")

    monkeypatch.setattr(imports_module, "require_visible_scene", unavailable_scene)
    context = AuthContext(user="admin", roles={"admin"}, projects={"*"}, areas={"*"})

    with pytest.raises(HTTPException) as excinfo:
        imports_module.import_delivery_scene_item(
            {"sceneId": "scene-catalog-outage", "relationType": "coverage"},
            context,
        )

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail == "Remote sensing catalog database is unavailable"


def test_import_operation_queue_rolls_up_delivery_package_work(app_client):
    seed_import_scenes("scene-operation-queue-publish", "scene-operation-queue-delivery")
    pending_review = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "operation-queue-review.geojson",
                io.BytesIO(geojson_bytes(block_code="QUEUE-REVIEW-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    pending_acceptance = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "operation-queue-acceptance.geojson",
                io.BytesIO(geojson_bytes(block_code="QUEUE-ACCEPT-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    pending_publish = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "operation-queue-publish.geojson",
                io.BytesIO(geojson_bytes(block_code="QUEUE-PUBLISH-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    pending_delivery = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "operation-queue-delivery.geojson",
                io.BytesIO(geojson_bytes(block_code="QUEUE-DELIVERY-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    assert pending_review.status_code == 200
    assert pending_acceptance.status_code == 200
    assert pending_publish.status_code == 200
    assert pending_delivery.status_code == 200

    acceptance_id = pending_acceptance.json()["id"]
    publish_id = pending_publish.json()["id"]
    delivery_id = pending_delivery.json()["id"]
    reviewed_acceptance = app_client.post(
        f"/api/imports/{acceptance_id}/review",
        json={"decision": "approved", "comment": "ready for acceptance"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
    )
    reviewed_publish = app_client.post(
        f"/api/imports/{publish_id}/review",
        json={"decision": "approved", "comment": "ready for publish"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
    )
    accepted_publish = app_client.post(
        f"/api/imports/{publish_id}/acceptance",
        json={"status": "accepted", "comment": "accepted"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "acceptor"},
    )
    linked_unpublished = app_client.post(
        f"/api/imports/{publish_id}/link-scene-layer",
        json={"sceneId": "scene-operation-queue-publish", "publishLayer": False},
        headers={"X-RS-Roles": "admin", "X-RS-User": "publisher"},
    )
    reviewed_delivery = app_client.post(
        f"/api/imports/{delivery_id}/review",
        json={"decision": "approved", "comment": "ready for delivery"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
    )
    accepted_delivery = app_client.post(
        f"/api/imports/{delivery_id}/acceptance",
        json={"status": "accepted", "comment": "accepted"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "acceptor"},
    )
    linked_published = app_client.post(
        f"/api/imports/{delivery_id}/link-scene-layer",
        json={"sceneId": "scene-operation-queue-delivery", "publishLayer": True},
        headers={"X-RS-Roles": "admin", "X-RS-User": "publisher"},
    )
    denied = app_client.get(
        "/api/imports/forest-blocks/operation-queue",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    queue = app_client.get(
        "/api/imports/forest-blocks/operation-queue?limit=2",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )

    assert reviewed_acceptance.status_code == 200
    assert reviewed_publish.status_code == 200
    assert accepted_publish.status_code == 200
    assert linked_unpublished.status_code == 200
    assert reviewed_delivery.status_code == 200
    assert accepted_delivery.status_code == 200
    assert linked_published.status_code == 200
    assert denied.status_code == 403
    assert "imports.forestBlocks.view" in denied.json()["detail"]
    assert queue.status_code == 200
    body = queue.json()
    lanes = {item["key"]: item for item in body["items"]}
    assert body["summary"]["operationQueueTotal"] == 4
    assert body["summary"]["actionableQueueTotal"] == 4
    assert lanes["awaiting_review"]["requiredPermission"] == "imports.forestBlocks.review"
    assert lanes["awaiting_acceptance"]["requiredPermission"] == "imports.forestBlocks.acceptance"
    assert lanes["awaiting_publish"]["requiredPermission"] == "imports.sceneLayers.link"
    assert lanes["awaiting_delivery"]["requiredPermission"] == "imagery.scenes.delivery"
    assert lanes["awaiting_review"]["href"] == "admin-imports.html?deliveryPackageStatus=awaiting_review"
    assert lanes["awaiting_acceptance"]["href"] == "admin-imports.html?deliveryPackageStatus=awaiting_acceptance"
    assert lanes["awaiting_publish"]["href"] == "admin-imports.html?deliveryPackageStatus=awaiting_publish"
    assert lanes["awaiting_delivery"]["href"] == "admin-imports.html?deliveryPackageStatus=awaiting_delivery"
    assert lanes["awaiting_review"]["items"][0]["batchId"] == pending_review.json()["id"]
    assert lanes["awaiting_acceptance"]["items"][0]["batchId"] == acceptance_id
    assert lanes["awaiting_publish"]["items"][0]["batchId"] == publish_id
    assert lanes["awaiting_delivery"]["items"][0]["batchId"] == delivery_id
    assert lanes["awaiting_publish"]["items"][0]["primaryAction"] == "publish-layer"
    assert lanes["awaiting_delivery"]["items"][0]["primaryAction"] == "record-delivery"


def test_import_batch_keeps_unified_audit_event_chain(app_client):
    seed_import_scene("scene-audit-chain")
    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "audit-chain-batch.geojson",
                io.BytesIO(geojson_bytes(block_code="AUDIT-CHAIN-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer"},
    )
    assert imported.status_code == 200
    batch_id = imported.json()["id"]

    reviewed = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "统一审计链审核通过"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
    )
    linked = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-audit-chain", "publishLayer": True},
        headers={"X-RS-Roles": "admin", "X-RS-User": "publisher"},
    )
    rolled_back = app_client.post(
        f"/api/imports/{batch_id}/rollback",
        headers={"X-RS-Roles": "admin", "X-RS-User": "rollbacker"},
    )
    deleted = app_client.delete(
        f"/api/imports/{batch_id}",
        headers={"X-RS-Roles": "admin", "X-RS-User": "deleter"},
    )
    report = app_client.get(f"/api/imports/{batch_id}/report", headers={"X-RS-Roles": "admin"})

    assert reviewed.status_code == 200
    assert linked.status_code == 200
    assert rolled_back.status_code == 200
    assert deleted.status_code == 200
    assert report.status_code == 200
    audit_events = report.json()["auditEvents"]
    assert [event["action"] for event in audit_events] == [
        "import",
        "review",
        "link-scene-layer",
        "rollback",
        "delete",
    ]
    assert [event["actor"] for event in audit_events] == [
        "importer",
        "reviewer",
        "publisher",
        "rollbacker",
        "deleter",
    ]
    assert audit_events[0]["summary"]["validRows"] == 1
    assert audit_events[1]["summary"]["reviewStatus"] == "approved"
    assert audit_events[2]["summary"]["sceneId"] == "scene-audit-chain"
    assert audit_events[3]["summary"]["blocksSoftDeleted"] == 1
    assert audit_events[4]["summary"]["status"] == "deleted"
    assert deleted.json()["event"]["action"] == "delete"


def test_import_batch_audit_events_can_be_listed_across_batches(app_client):
    first = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "audit-ledger-first.geojson",
                io.BytesIO(geojson_bytes(block_code="AUDIT-LEDGER-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer-a"},
    )
    second = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "audit-ledger-second.geojson",
                io.BytesIO(geojson_bytes(block_code="AUDIT-LEDGER-002")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "importer-b"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    reviewed = app_client.post(
        f"/api/imports/{first_id}/review",
        json={"decision": "approved", "comment": "audit ledger review"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer-ledger"},
    )
    denied = app_client.get(
        "/api/imports/forest-blocks/audit-events",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    all_events = app_client.get(
        "/api/imports/forest-blocks/audit-events?limit=20",
        headers={"X-RS-Roles": "admin"},
    )
    review_events = app_client.get(
        "/api/imports/forest-blocks/audit-events?action=review",
        headers={"X-RS-Roles": "admin"},
    )
    first_events = app_client.get(
        f"/api/imports/forest-blocks/audit-events?batchId={first_id}",
        headers={"X-RS-Roles": "admin"},
    )
    q_events = app_client.get(
        "/api/imports/forest-blocks/audit-events?q=reviewer-ledger",
        headers={"X-RS-Roles": "admin"},
    )

    assert reviewed.status_code == 200
    assert denied.status_code == 403
    assert "imports.forestBlocks.view" in denied.json()["detail"]
    assert all_events.status_code == 200
    assert all_events.json()["total"] >= 3
    all_items = all_events.json()["items"]
    assert {item["batchId"] for item in all_items} >= {first_id, second_id}
    assert all("fileName" in item and "batchStatus" in item for item in all_items)
    assert review_events.status_code == 200
    assert review_events.json()["total"] == 1
    assert review_events.json()["items"][0]["action"] == "review"
    assert review_events.json()["items"][0]["batchId"] == first_id
    assert first_events.status_code == 200
    assert {item["action"] for item in first_events.json()["items"]} >= {"import", "review"}
    assert all(item["batchId"] == first_id for item in first_events.json()["items"])
    assert q_events.status_code == 200
    assert q_events.json()["total"] == 1
    assert q_events.json()["items"][0]["actor"] == "reviewer-ledger"


def test_import_batch_audit_events_can_be_exported_as_csv(app_client):
    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "audit-export-batch.geojson",
                io.BytesIO(geojson_bytes(block_code="AUDIT-EXPORT-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "import-exporter"},
    )
    assert imported.status_code == 200
    batch_id = imported.json()["id"]

    reviewed = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "audit export review"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "review-exporter"},
    )
    denied = app_client.get(
        f"/api/imports/forest-blocks/audit-events.csv?batchId={batch_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    exported = app_client.get(
        f"/api/imports/forest-blocks/audit-events.csv?batchId={batch_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.export"},
    )

    assert reviewed.status_code == 200
    assert denied.status_code == 403
    assert "imports.forestBlocks.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "import-audit-events.csv" in exported.headers["content-disposition"]
    text = exported.content.decode("utf-8-sig")
    assert (
        "batchId,action,actor,at,batchStatus,acceptanceStatus,fileName,summary"
        in text.splitlines()[0]
    )
    assert batch_id in text
    assert "import-exporter" in text
    assert "review-exporter" in text
    assert "review" in text


def test_import_batches_can_filter_by_acceptance_status_and_export_it_in_audit_csv(app_client):
    accepted = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "acceptance-filter-accepted.geojson",
                io.BytesIO(geojson_bytes(block_code="ACCEPTANCE-FILTER-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "import-acceptance-filter"},
    )
    pending = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "acceptance-filter-pending.geojson",
                io.BytesIO(geojson_bytes(block_code="ACCEPTANCE-FILTER-002")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    assert accepted.status_code == 200
    assert pending.status_code == 200
    accepted_id = accepted.json()["id"]

    reviewed = app_client.post(
        f"/api/imports/{accepted_id}/review",
        json={"decision": "approved", "comment": "ready for acceptance filter"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "acceptance-reviewer"},
    )
    acceptance = app_client.post(
        f"/api/imports/{accepted_id}/acceptance",
        json={"status": "accepted", "comment": "accepted for ledger filter"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "acceptance-filter-user"},
    )
    filtered = app_client.get(
        "/api/imports/forest-blocks/batches?acceptanceStatus=accepted",
        headers={"X-RS-Roles": "admin"},
    )
    exported = app_client.get(
        f"/api/imports/forest-blocks/audit-events.csv?action=acceptance&batchId={accepted_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.export"},
    )

    assert reviewed.status_code == 200
    assert acceptance.status_code == 200
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [accepted_id]
    assert filtered.json()["items"][0]["acceptanceStatus"] == "accepted"
    assert exported.status_code == 200
    csv_text = exported.content.decode("utf-8-sig")
    assert "acceptanceStatus" in csv_text.splitlines()[0]
    assert "accepted" in csv_text
    assert "acceptance-filter-user" in csv_text


def test_deleted_import_audit_events_require_restore_permission(app_client):
    created = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "deleted-audit-events.geojson",
                io.BytesIO(geojson_bytes(block_code="IMPORT-DELETED-AUDIT-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "imports.forestBlocks.create"},
    )
    assert created.status_code == 200
    batch_id = created.json()["id"]
    deleted = app_client.delete(
        f"/api/imports/{batch_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.delete"},
    )
    assert deleted.status_code == 200

    denied = app_client.get(
        "/api/imports/forest-blocks/audit-events?includeDeleted=true",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    allowed = app_client.get(
        f"/api/imports/forest-blocks/audit-events?includeDeleted=true&batchId={batch_id}",
        headers={"X-RS-Roles": "imports.forestBlocks.restore"},
    )

    assert denied.status_code == 403
    assert "imports.forestBlocks.restore" in denied.json()["detail"]
    assert allowed.status_code == 200
    assert allowed.json()["total"] >= 1
    assert {item["batchId"] for item in allowed.json()["items"]} == {batch_id}


def test_import_batch_report_lists_imported_blocks_and_right_archives(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("traceable-batch.geojson", io.BytesIO(geojson_bytes(block_code="TRACE-BLOCK-001")), "application/geo+json")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["importedBlocks"] == [
        {
            "blockCode": "TRACE-BLOCK-001",
            "name": "导入林班一",
            "action": "created",
            "row": 1,
        }
    ]
    assert body["importedRightsArchives"] == [
        {
            "archiveCode": "TRACE-BLOCK-001",
            "linkedBlockCodes": ["TRACE-BLOCK-001"],
            "sourceBlockCode": "TRACE-BLOCK-001",
        }
    ]

    report = app_client.get(f"/api/imports/{body['id']}/report", headers={"X-RS-Roles": "admin"})

    assert report.status_code == 200
    assert report.json()["importedBlocks"][0]["blockCode"] == "TRACE-BLOCK-001"
    assert report.json()["importedRightsArchives"][0]["archiveCode"] == "TRACE-BLOCK-001"

    block_targets = app_client.get(
        f"/api/imports/{body['id']}/targets?kind=blocks&limit=1&offset=0",
        headers={"X-RS-Roles": "admin"},
    )
    right_targets = app_client.get(
        f"/api/imports/{body['id']}/targets?kind=rights&q=TRACE-BLOCK",
        headers={"X-RS-Roles": "admin"},
    )

    assert block_targets.status_code == 200
    assert block_targets.json() == {
        "kind": "blocks",
        "items": body["importedBlocks"],
        "total": 1,
        "limit": 1,
        "offset": 0,
    }
    assert right_targets.status_code == 200
    assert right_targets.json()["kind"] == "rights"
    assert right_targets.json()["total"] == 1
    assert right_targets.json()["items"] == body["importedRightsArchives"]


def test_import_batch_rollback_soft_deletes_created_blocks_and_marks_report(app_client):
    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "rollback-batch.geojson",
                io.BytesIO(geojson_bytes(block_code="ROLLBACK-BLOCK-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert imported.status_code == 200
    batch_id = imported.json()["id"]

    listed = app_client.get("/api/forest-blocks?q=ROLLBACK-BLOCK-001")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["sourceBatchId"] == batch_id

    denied = app_client.post(
        f"/api/imports/{batch_id}/rollback",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    rolled_back = app_client.post(
        f"/api/imports/{batch_id}/rollback",
        headers={"X-RS-Roles": "admin"},
    )
    listed_after = app_client.get("/api/forest-blocks?q=ROLLBACK-BLOCK-001")
    report = app_client.get(f"/api/imports/{batch_id}/report", headers={"X-RS-Roles": "admin"})

    assert denied.status_code == 403
    assert "imports.forestBlocks.rollback" in denied.json()["detail"]
    assert rolled_back.status_code == 200
    assert rolled_back.json()["ok"] is True
    assert rolled_back.json()["status"] == "rolled_back"
    assert rolled_back.json()["rollbackSummary"]["blocksSoftDeleted"] == 1
    assert rolled_back.json()["rolledBackBlocks"] == [
        {"blockCode": "ROLLBACK-BLOCK-001", "action": "soft_deleted"}
    ]
    assert listed_after.status_code == 200
    assert listed_after.json()["total"] == 0
    assert report.status_code == 200
    assert report.json()["status"] == "rolled_back"
    assert report.json()["rollbackSummary"]["blocksSoftDeleted"] == 1
    assert report.json()["rolledBackAt"]


def test_import_batch_scene_layer_publish_requires_approved_review(app_client):
    seed_import_scene("scene-review-gated")
    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "review-gated-batch.geojson",
                io.BytesIO(geojson_bytes(block_code="REVIEW-GATED-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    assert imported.status_code == 200
    batch_id = imported.json()["id"]

    pending_link = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-review-gated"},
        headers={"X-RS-Roles": "admin"},
    )
    needs_correction_review = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "needs_correction", "comment": "先修正林权挂接"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer-a"},
    )
    correction_link = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-review-gated"},
        headers={"X-RS-Roles": "admin"},
    )
    approved_review = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "图斑和档案复核通过"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer-b"},
    )
    approved_link = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-review-gated"},
        headers={"X-RS-Roles": "admin"},
    )

    assert pending_link.status_code == 409
    assert "review approved" in pending_link.json()["detail"]
    assert needs_correction_review.status_code == 200
    assert correction_link.status_code == 409
    assert "review approved" in correction_link.json()["detail"]
    assert approved_review.status_code == 200
    assert approved_link.status_code == 200
    assert approved_link.json()["ok"] is True


def test_import_batch_publish_readiness_reports_blockers_without_mutating(app_client):
    seed_import_scene("scene-readiness-001")
    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "readiness-batch.geojson",
                io.BytesIO(geojson_bytes(block_code="READINESS-BLOCK-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    assert imported.status_code == 200
    batch_id = imported.json()["id"]

    denied_action = app_client.post(
        f"/api/imports/{batch_id}/publish-readiness",
        json={"sceneId": "scene-readiness-001", "publishLayer": True},
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    pending = app_client.post(
        f"/api/imports/{batch_id}/publish-readiness",
        json={"sceneId": "scene-readiness-001", "publishLayer": True},
        headers={"X-RS-Roles": "admin"},
    )
    approved_review = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "ready for publish preflight"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
    )
    ready = app_client.post(
        f"/api/imports/{batch_id}/publish-readiness",
        json={"sceneId": "scene-readiness-001", "publishLayer": True},
        headers={"X-RS-Roles": "admin"},
    )
    report = app_client.get(f"/api/imports/{batch_id}", headers={"X-RS-Roles": "admin"})
    layers = app_client.get(f"/api/map-layers?q=IMPORT-LAYER-{batch_id}")

    assert denied_action.status_code == 403
    assert "imports.sceneLayers.link" in denied_action.json()["detail"]
    assert pending.status_code == 200
    assert pending.json()["ready"] is False
    assert "review_not_approved" in pending.json()["blockingReasons"]
    assert pending.json()["checks"][0]["key"] == "batch_active"
    assert any(check["key"] == "review_approved" and check["status"] == "blocked" for check in pending.json()["checks"])
    assert approved_review.status_code == 200
    assert ready.status_code == 200
    body = ready.json()
    assert body["ok"] is True
    assert body["id"] == batch_id
    assert body["sceneId"] == "scene-readiness-001"
    assert body["ready"] is True
    assert body["blockingReasons"] == []
    assert body["linkedBlockCount"] == 1
    assert body["missingBlockCount"] == 0
    assert body["publishLayer"] is True
    assert body["coverageCheck"]["status"] == "pass"
    assert body["quality"]["publishRiskStatus"] == "clear"
    assert report.status_code == 200
    assert report.json()["imageryLinks"] == []
    assert layers.status_code == 200
    assert layers.json()["total"] == 0


def test_import_quality_issues_can_be_listed_and_filtered(app_client):
    from server.modules import imports as imports_module

    report = imports_module.build_report(
        batch_id="quality-issue-batch",
        file_name="quality-issue.geojson",
        total_rows=3,
        valid_rows=2,
        invalid_rows=1,
        errors=[{"row": 3, "message": "name is required"}],
        imported_blocks=[
            {"blockCode": "QUALITY-MISSING-BLOCK", "action": "created", "row": 1},
            {"blockCode": "QUALITY-MISSING-GEOM", "action": "created", "row": 2},
        ],
    )
    report.update(
        {
            "reviewStatus": "needs_correction",
            "reviewComment": "补齐空间边界后再发布",
            "reviewedBy": "reviewer",
            "qualityStatus": "warning",
            "qualityFindings": ["missing_geometry"],
            "reviewRecommendation": "needs_correction",
            "publishRiskStatus": "warning",
            "imageryLinks": [
                {
                    "sceneId": "scene-quality-issue",
                    "at": "2026-07-07T00:00:00+00:00",
                    "coverageCheck": {
                        "status": "warning",
                        "warnings": ["missing_geometry", "outside_scene_bounds"],
                        "missingGeometryBlockCodes": ["QUALITY-MISSING-GEOM"],
                        "outsideSceneBoundsBlockCodes": ["QUALITY-OUTSIDE"],
                    },
                }
            ],
        }
    )
    imports_module.save_import_report(report)

    denied = app_client.get(
        "/api/imports/forest-blocks/quality-issues",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    listed = app_client.get(
        "/api/imports/forest-blocks/quality-issues?batchId=quality-issue-batch",
        headers={"X-RS-Roles": "admin"},
    )
    missing_only = app_client.get(
        "/api/imports/forest-blocks/quality-issues?issueType=missing_imported_block",
        headers={"X-RS-Roles": "admin"},
    )
    searched = app_client.get(
        "/api/imports/forest-blocks/quality-issues?q=QUALITY-OUTSIDE",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "imports.forestBlocks.view" in denied.json()["detail"]
    assert listed.status_code == 200
    body = listed.json()
    assert body["limit"] == 100
    assert body["offset"] == 0
    issue_types = {item["issueType"] for item in body["items"]}
    assert {
        "import_error",
        "review_decision",
        "missing_imported_block",
        "quality_finding",
        "coverage_warning",
    }.issubset(issue_types)
    missing_issue = next(item for item in body["items"] if item["issueType"] == "missing_imported_block")
    assert missing_issue["severity"] == "blocked"
    assert missing_issue["batchId"] == "quality-issue-batch"
    assert missing_issue["blockCodes"] == ["QUALITY-MISSING-BLOCK", "QUALITY-MISSING-GEOM"]
    assert missing_issue["actionRequired"] == "恢复或重新导入缺失林班后再发布图层"
    coverage_issue = next(
        item
        for item in body["items"]
        if item["issueType"] == "coverage_warning" and item["issueKey"] == "outside_scene_bounds"
    )
    assert coverage_issue["sceneId"] == "scene-quality-issue"
    assert coverage_issue["blockCodes"] == ["QUALITY-OUTSIDE"]
    assert missing_only.status_code == 200
    assert missing_only.json()["total"] == 1
    assert missing_only.json()["items"][0]["issueType"] == "missing_imported_block"
    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert searched.json()["items"][0]["issueKey"] == "outside_scene_bounds"


def test_import_quality_issues_can_be_exported_as_csv(app_client):
    from server.modules import imports as imports_module

    report = imports_module.build_report(
        batch_id="quality-issue-export-batch",
        file_name="quality-issue-export.geojson",
        total_rows=2,
        valid_rows=1,
        invalid_rows=1,
        errors=[{"row": 2, "message": "geometry is required"}],
        imported_blocks=[{"blockCode": "QUALITY-EXPORT-BLOCK", "action": "created", "row": 1}],
    )
    report.update(
        {
            "qualityStatus": "warning",
            "qualityFindings": ["missing_geometry"],
            "publishRiskStatus": "warning",
        }
    )
    imports_module.save_import_report(report)

    denied = app_client.get(
        "/api/imports/forest-blocks/quality-issues.csv?batchId=quality-issue-export-batch",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    exported = app_client.get(
        "/api/imports/forest-blocks/quality-issues.csv?batchId=quality-issue-export-batch",
        headers={"X-RS-Roles": "imports.forestBlocks.export"},
    )

    assert denied.status_code == 403
    assert "imports.forestBlocks.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "import-quality-issues.csv" in exported.headers["content-disposition"]
    text = exported.content.decode("utf-8-sig")
    assert "issueId,batchId,fileName,issueType,issueKey,severity,status,sceneId,blockCodes" in text.splitlines()[0]
    assert "quality-issue-export-batch" in text
    assert "QUALITY-EXPORT-BLOCK" in text
    assert "missing_geometry" in text


def test_deleted_import_quality_issues_require_restore_permission(app_client):
    from server.modules import imports as imports_module

    report = imports_module.build_report(
        batch_id="deleted-quality-issue-batch",
        file_name="deleted-quality-issue.geojson",
        total_rows=1,
        valid_rows=0,
        invalid_rows=1,
        errors=[{"row": 1, "message": "name is required"}],
        imported_blocks=[],
    )
    report["statusBeforeDelete"] = "completed"
    report["status"] = "deleted"
    report["deletedAt"] = "2026-07-08T00:00:00+00:00"
    imports_module.save_import_report(report)

    denied = app_client.get(
        "/api/imports/forest-blocks/quality-issues?includeDeleted=true",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    allowed = app_client.get(
        "/api/imports/forest-blocks/quality-issues?includeDeleted=true&batchId=deleted-quality-issue-batch",
        headers={"X-RS-Roles": "imports.forestBlocks.restore"},
    )

    assert denied.status_code == 403
    assert "imports.forestBlocks.restore" in denied.json()["detail"]
    assert allowed.status_code == 200
    assert allowed.json()["total"] == 1
    assert allowed.json()["items"][0]["batchId"] == "deleted-quality-issue-batch"
    assert allowed.json()["items"][0]["issueType"] == "import_error"


def test_import_batch_scene_link_requires_all_imported_blocks_active(app_client):
    from server.modules import imports as imports_module

    seed_import_scene("scene-partial-link")
    block = app_client.post(
        "/api/forest-blocks",
        json={
            "blockCode": "PARTIAL-LINK-001",
            "name": "Partial link active block",
            "countyCode": "350703",
            "geometry": SAMPLE_POLYGON,
        },
        headers={"X-RS-Roles": "admin"},
    )
    report = imports_module.build_report(
        batch_id="partial-link-batch",
        file_name="partial-link.geojson",
        total_rows=2,
        valid_rows=2,
        invalid_rows=0,
        errors=[],
        imported_blocks=[
            {"blockCode": "PARTIAL-LINK-001", "action": "created", "row": 1},
            {"blockCode": "PARTIAL-LINK-MISSING", "action": "created", "row": 2},
        ],
    )
    imports_module.save_import_report(report)

    approved_review = app_client.post(
        "/api/imports/partial-link-batch/review",
        json={"decision": "approved", "comment": "ready except missing active block"},
        headers={"X-RS-Roles": "admin"},
    )
    readiness = app_client.post(
        "/api/imports/partial-link-batch/publish-readiness",
        json={"sceneId": "scene-partial-link", "publishLayer": True},
        headers={"X-RS-Roles": "admin"},
    )
    linked = app_client.post(
        "/api/imports/partial-link-batch/link-scene-layer",
        json={"sceneId": "scene-partial-link", "publishLayer": True},
        headers={"X-RS-Roles": "admin"},
    )
    block_links = app_client.get(f"/api/forest-blocks/{block.json()['id']}/scenes")
    layers = app_client.get("/api/map-layers?q=IMPORT-LAYER-partial-link-batch")
    stored_report = app_client.get("/api/imports/partial-link-batch", headers={"X-RS-Roles": "admin"})

    assert block.status_code == 200
    assert approved_review.status_code == 200
    assert readiness.status_code == 200
    readiness_body = readiness.json()
    assert readiness_body["ready"] is False
    assert readiness_body["missingBlockCount"] == 1
    assert readiness_body["skippedBlocks"] == [{"blockCode": "PARTIAL-LINK-MISSING", "reason": "block_not_found"}]
    assert "missing_imported_blocks" in readiness_body["blockingReasons"]
    assert any(
        check["key"] == "all_imported_blocks_active" and check["status"] == "blocked"
        for check in readiness_body["checks"]
    )
    assert linked.status_code == 409
    assert "missing imported forest blocks" in linked.json()["detail"]
    assert block_links.status_code == 200
    assert block_links.json()["items"] == []
    assert layers.status_code == 200
    assert layers.json()["total"] == 0
    assert stored_report.json()["imageryLinks"] == []


def test_import_batch_can_link_scene_and_publish_traceable_layer(app_client):
    seed_import_scene()
    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "batch-scene-link.geojson",
                io.BytesIO(geojson_bytes(block_code="BATCH-SCENE-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    assert imported.status_code == 200
    batch_id = imported.json()["id"]
    block = app_client.get("/api/forest-blocks?q=BATCH-SCENE-001").json()["items"][0]

    denied = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-import-batch-001"},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    denied_action = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-import-batch-001"},
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    approved_review = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "图斑和林权复核通过"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
    )
    linked = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={
            "sceneId": "scene-import-batch-001",
            "relationType": "orthophoto",
            "confidence": 0.91,
            "publishLayer": True,
            "zIndex": 42,
        },
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )

    assert denied.status_code == 403
    assert "imports.sceneLayers.link" in denied.json()["detail"]
    assert denied_action.status_code == 403
    assert "imports.sceneLayers.link" in denied_action.json()["detail"]
    assert approved_review.status_code == 200
    assert linked.status_code == 200
    body = linked.json()
    assert body["ok"] is True
    assert body["id"] == batch_id
    assert body["sceneId"] == "scene-import-batch-001"
    assert body["linkedBlocks"] == [
        {
            "blockCode": "BATCH-SCENE-001",
            "blockId": block["id"],
            "sceneId": "scene-import-batch-001",
            "relationType": "orthophoto",
        }
    ]
    assert body["layer"]["recordCode"] == f"IMPORT-LAYER-{batch_id}"
    assert body["layer"]["layerType"] == "imagery"
    assert body["layer"]["linkedBlockCodes"] == ["BATCH-SCENE-001"]
    assert body["layer"]["linkedRightArchiveCodes"] == ["BATCH-SCENE-001"]
    assert body["layer"]["properties"]["importBatchId"] == batch_id
    assert body["layer"]["properties"]["sourceSceneId"] == "scene-import-batch-001"
    assert body["layer"]["sourceType"] == "importBatch"
    assert body["layer"]["adminHref"] == f"admin-map-layers.html?layerCode=IMPORT-LAYER-{batch_id}"
    assert body["layer"]["dashboardHref"] == "zhushan-bigdata.html#mapLayers"
    assert body["layer"]["sourceLinks"] == [
        {
            "type": "importBatch",
            "label": "入库批次",
            "value": batch_id,
            "href": f"admin-imports.html?batchId={batch_id}",
        },
        {
            "type": "imagery",
            "label": "影像场景",
            "value": "scene-import-batch-001",
            "href": "admin-imagery.html?sceneId=scene-import-batch-001",
        },
    ]
    assert body["coverageCheck"]["status"] == "pass"
    assert body["coverageCheck"]["sceneHasBounds"] is True
    assert body["coverageCheck"]["totalBlocks"] == 1
    assert body["coverageCheck"]["missingGeometryCount"] == 0
    assert body["coverageCheck"]["outsideSceneBoundsCount"] == 0
    assert body["event"]["coverageCheck"]["status"] == "pass"
    assert body["layer"]["properties"]["coverageCheck"]["status"] == "pass"

    links = app_client.get(f"/api/forest-blocks/{block['id']}/scenes")
    layers = app_client.get(f"/api/map-layers?q=IMPORT-LAYER-{batch_id}")
    layer_events = app_client.get(
        f"/api/map-layers/events?recordCode=IMPORT-LAYER-{batch_id}&action=publish-from-import&q=alice",
        headers={"X-RS-Roles": "admin"},
    )
    report = app_client.get(f"/api/imports/{batch_id}", headers={"X-RS-Roles": "admin"})
    scene_batches = app_client.get(
        "/api/imports/forest-blocks/batches?sceneId=scene-import-batch-001",
        headers={"X-RS-Roles": "admin"},
    )
    unrelated_scene_batches = app_client.get(
        "/api/imports/forest-blocks/batches?sceneId=scene-import-batch-missing",
        headers={"X-RS-Roles": "admin"},
    )

    assert links.status_code == 200
    assert links.json()["items"] == [
        {
            "forestBlockId": block["id"],
            "sceneId": "scene-import-batch-001",
            "relationType": "orthophoto",
            "capturedAt": "2026-07-07",
            "confidence": 0.91,
        }
    ]
    assert layers.status_code == 200
    assert layers.json()["total"] == 1
    layer_item = layers.json()["items"][0]
    assert layer_item["id"] == body["layer"]["id"]
    assert layer_item["properties"]["auditEvents"][-1]["action"] == "publish-from-import"
    assert layer_item["properties"]["auditEvents"][-1]["actor"] == "alice"
    assert layer_events.status_code == 200
    assert layer_events.json()["total"] == 1
    assert layer_events.json()["items"][0]["actor"] == "alice"
    assert layer_events.json()["items"][0]["sourceType"] == "importBatch"
    assert report.status_code == 200
    assert report.json()["imageryLinks"][-1]["sceneId"] == "scene-import-batch-001"
    assert report.json()["imageryLinks"][-1]["layerId"] == body["layer"]["id"]
    assert report.json()["imageryLinks"][-1]["linkedBlockCodes"] == ["BATCH-SCENE-001"]
    assert report.json()["imageryLinks"][-1]["linkedRightArchiveCodes"] == ["BATCH-SCENE-001"]
    assert scene_batches.status_code == 200
    assert scene_batches.json()["total"] == 1
    assert scene_batches.json()["items"][0]["id"] == batch_id
    assert unrelated_scene_batches.status_code == 200
    assert unrelated_scene_batches.json()["total"] == 0


def test_import_batch_publish_layer_requires_map_layer_write_permissions(app_client):
    seed_import_scene("scene-import-map-permission")
    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "batch-scene-map-permission.geojson",
                io.BytesIO(geojson_bytes(block_code="BATCH-MAP-PERM-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    assert imported.status_code == 200
    batch_id = imported.json()["id"]
    block = app_client.get("/api/forest-blocks?q=BATCH-MAP-PERM-001").json()["items"][0]

    approved_review = app_client.post(
        f"/api/imports/{batch_id}/review",
        json={"decision": "approved", "comment": "ready for map permission check"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
    )
    assert approved_review.status_code == 200

    missing_map_create = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-import-map-permission", "publishLayer": True},
        headers={"X-RS-Roles": "imports.sceneLayers.link"},
    )
    assert missing_map_create.status_code == 403
    assert "map.layers.create" in missing_map_create.json()["detail"]
    report_after_denied = app_client.get(f"/api/imports/{batch_id}", headers={"X-RS-Roles": "admin"})
    links_after_denied = app_client.get(f"/api/forest-blocks/{block['id']}/scenes")
    layers_after_denied = app_client.get(f"/api/map-layers?q=IMPORT-LAYER-{batch_id}")
    assert report_after_denied.json()["imageryLinks"] == []
    assert links_after_denied.json()["items"] == []
    assert layers_after_denied.json()["total"] == 0

    missing_map_publish = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-import-map-permission", "publishLayer": True},
        headers={"X-RS-Roles": "imports.sceneLayers.link,map.layers.create"},
    )
    assert missing_map_publish.status_code == 403
    assert "map.layers.publish" in missing_map_publish.json()["detail"]

    allowed = app_client.post(
        f"/api/imports/{batch_id}/link-scene-layer",
        json={"sceneId": "scene-import-map-permission", "publishLayer": True},
        headers={"X-RS-Roles": "imports.sceneLayers.link,map.layers.create,map.layers.publish"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["layer"]["recordCode"] == f"IMPORT-LAYER-{batch_id}"


def test_import_batch_scene_link_reports_coverage_warnings(app_client):
    from server.modules import database as database_module
    from server.modules import imports as imports_module

    catalog_path = database_module.get_data_dir() / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "id": "scene-coverage-warning",
                        "name": "Coverage warning scene",
                        "cogPath": "cogs/warning.tif",
                        "bounds": [119.0, 28.0, 120.0, 29.0],
                        "projectId": "zhushan",
                        "areaCode": "350703",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    missing_geometry = app_client.post(
        "/api/forest-blocks",
        json={"blockCode": "COVER-MISSING-GEOM", "name": "Missing geometry block", "countyCode": "350703"},
        headers={"X-RS-Roles": "admin"},
    )
    outside_bounds = app_client.post(
        "/api/forest-blocks",
        json={
            "blockCode": "COVER-OUTSIDE-BOUNDS",
            "name": "Outside scene block",
            "countyCode": "350703",
            "geometry": SAMPLE_POLYGON,
        },
        headers={"X-RS-Roles": "admin"},
    )
    report = imports_module.build_report(
        batch_id="coverage-warning-batch",
        file_name="coverage-warning.geojson",
        total_rows=2,
        valid_rows=2,
        invalid_rows=0,
        errors=[],
        imported_blocks=[
            {"blockCode": "COVER-MISSING-GEOM", "action": "created", "row": 1},
            {"blockCode": "COVER-OUTSIDE-BOUNDS", "action": "created", "row": 2},
        ],
    )
    imports_module.save_import_report(report)

    approved_review = app_client.post(
        "/api/imports/coverage-warning-batch/review",
        json={"decision": "approved", "comment": "覆盖预检样例允许发布"},
        headers={"X-RS-Roles": "admin"},
    )
    linked = app_client.post(
        "/api/imports/coverage-warning-batch/link-scene-layer",
        json={"sceneId": "scene-coverage-warning"},
        headers={"X-RS-Roles": "admin"},
    )

    assert missing_geometry.status_code == 200
    assert outside_bounds.status_code == 200
    assert approved_review.status_code == 200
    assert linked.status_code == 200
    coverage = linked.json()["coverageCheck"]
    assert coverage["status"] == "warning"
    assert coverage["sceneHasBounds"] is True
    assert coverage["totalBlocks"] == 2
    assert coverage["missingGeometryCount"] == 1
    assert coverage["outsideSceneBoundsCount"] == 1
    assert coverage["missingGeometryBlockCodes"] == ["COVER-MISSING-GEOM"]
    assert coverage["outsideSceneBoundsBlockCodes"] == ["COVER-OUTSIDE-BOUNDS"]
    assert "missing_geometry" in coverage["warnings"]
    assert "outside_scene_bounds" in coverage["warnings"]
    assert linked.json()["event"]["coverageCheck"] == coverage
    assert linked.json()["layer"]["properties"]["coverageCheck"] == coverage
    assert linked.json()["report"]["qualityStatus"] == "warning"
    assert linked.json()["report"]["qualityFindings"] == ["missing_geometry", "outside_scene_bounds"]
    assert linked.json()["report"]["reviewRecommendation"] == "needs_correction"
    assert linked.json()["report"]["publishRiskStatus"] == "warning"
    assert linked.json()["layer"]["properties"]["qualityStatus"] == "warning"
    assert linked.json()["layer"]["properties"]["publishRiskStatus"] == "warning"
    assert linked.json()["layer"]["properties"]["reviewRecommendation"] == "needs_correction"
    assert linked.json()["event"]["quality"]["publishRiskStatus"] == "warning"


def test_legacy_import_batches_are_normalized_with_trace_lists(app_client):
    from server.modules import imports as imports_module

    batches_path = imports_module.import_batches_json_path()
    batches_path.parent.mkdir(parents=True, exist_ok=True)
    batches_path.write_text(
        json.dumps(
            [
                {
                    "id": "legacy-import-batch",
                    "fileName": "legacy.geojson",
                    "fileType": "geojson",
                    "status": "completed",
                    "totalRows": 1,
                    "validRows": 0,
                    "invalidRows": 1,
                    "errors": [{"row": 1, "message": "name is required"}],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    response = app_client.get("/api/imports/forest-blocks/batches", headers={"X-RS-Roles": "admin"})

    assert response.status_code == 200
    batch = response.json()["items"][0]
    assert batch["importedBlocks"] == []
    assert batch["importedRightsArchives"] == []


def test_import_batch_errors_can_be_downloaded_as_csv(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "missing-name.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "blockCode": "ERROR-CSV-001",
                            "countyCode": "350703",
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    batch_id = response.json()["id"]

    denied = app_client.get(
        f"/api/imports/{batch_id}/errors.csv",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    downloaded = app_client.get(
        f"/api/imports/{batch_id}/errors.csv",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "imports.forestBlocks.export" in denied.json()["detail"]
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("text/csv")
    assert "attachment;" in downloaded.headers["content-disposition"]
    assert "row,message" in downloaded.text
    assert "1,name is required" in downloaded.text


def test_import_batch_report_can_be_downloaded_as_json(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "report-export.geojson",
                io.BytesIO(geojson_bytes(block_code="REPORT-EXPORT-001")),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    batch_id = response.json()["id"]

    denied = app_client.get(
        f"/api/imports/{batch_id}/report.json",
        headers={"X-RS-Roles": "imports.forestBlocks.view"},
    )
    downloaded = app_client.get(
        f"/api/imports/{batch_id}/report.json",
        headers={"X-RS-Roles": "imports.forestBlocks.export"},
    )
    body = json.loads(downloaded.content.decode("utf-8"))

    assert denied.status_code == 403
    assert "imports.forestBlocks.export" in denied.json()["detail"]
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/json")
    assert "attachment;" in downloaded.headers["content-disposition"]
    assert f'import-report-{batch_id}.json' in downloaded.headers["content-disposition"]
    assert body["id"] == batch_id
    assert body["fileName"] == "report-export.geojson"
    assert body["importedBlocks"][0]["blockCode"] == "REPORT-EXPORT-001"


def test_import_quality_issue_can_be_updated_and_filtered(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "quality-issue.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "blockCode": "QUALITY-ISSUE-001",
                            "countyCode": "350703",
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    batch_id = response.json()["id"]
    issue = app_client.get(
        f"/api/imports/forest-blocks/quality-issues?batchId={batch_id}",
        headers={"X-RS-Roles": "admin"},
    ).json()["items"][0]

    denied = app_client.patch(
        f"/api/imports/forest-blocks/quality-issues/{issue['issueId']}",
        json={"status": "resolved", "comment": "Source file corrected"},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    updated = app_client.patch(
        f"/api/imports/forest-blocks/quality-issues/{issue['issueId']}",
        json={"status": "resolved", "comment": "Source file corrected"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "quality-reviewer"},
    )
    resolved_only = app_client.get(
        f"/api/imports/forest-blocks/quality-issues?batchId={batch_id}&status=resolved",
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    assert denied.status_code == 403
    assert "imports.forestBlocks.quality" in denied.json()["detail"]
    assert updated.status_code == 200
    body = updated.json()
    assert body["issue"]["issueId"] == issue["issueId"]
    assert body["issue"]["status"] == "resolved"
    assert body["issue"]["handledBy"] == "quality-reviewer"
    assert body["issue"]["handlingComment"] == "Source file corrected"
    assert body["event"]["status"] == "resolved"
    assert body["report"]["qualityIssueEvents"][-1]["issueId"] == issue["issueId"]
    assert resolved_only.status_code == 200
    assert resolved_only.json()["total"] == 1
    assert resolved_only.json()["items"][0]["status"] == "resolved"


def test_postgis_import_report_uses_database_storage(isolated_env, monkeypatch, reload_platform_modules):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    imports_module = reload_imports_module(reload_platform_modules)
    batch_id = "0174b462-9168-445a-92c9-2d7743894684"
    report = imports_module.build_report(
        batch_id=batch_id,
        file_name="forest.geojson",
        total_rows=1,
        valid_rows=1,
        invalid_rows=0,
        errors=[],
    )
    insert_cursor = FakeCursor()
    select_cursor = FakeCursor(fetchone_result=postgis_import_batch_row(batch_id))
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [insert_cursor, select_cursor], connect_calls)

    imports_module.save_import_report(report)
    imports_module.IMPORT_REPORTS.clear()
    loaded = imports_module.get_report_or_404(batch_id)

    assert loaded["id"] == batch_id
    assert connect_calls == ["postgresql://smart-bamboo", "postgresql://smart-bamboo"]
    assert "INSERT INTO import_batches" in insert_cursor.executed[0][0]
    assert insert_cursor.executed[0][1][0] == batch_id
    assert "FROM import_batches" in select_cursor.executed[0][0]


def test_postgis_import_batch_quality_risk_filters_are_applied_in_database(
    isolated_env, monkeypatch, reload_platform_modules
):
    monkeypatch.setenv("SMART_BAMBOO_DATABASE_URL", "postgresql://smart-bamboo")
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "postgis")
    imports_module = reload_imports_module(reload_platform_modules)
    list_cursor = FakeCursor(fetchall_result=[postgis_import_batch_row("batch-pg-filter")])
    count_cursor = FakeCursor(fetchone_result=(1,))
    connect_calls: list[str] = []
    install_fake_psycopg(monkeypatch, [list_cursor, count_cursor], connect_calls)

    response = imports_module.list_import_reports(
        imports_module.ImportBatchFilters(
            q="forest",
            status="completed",
            reviewStatus="approved",
            qualityStatus="warning",
            publishRiskStatus="warning",
            sceneId="scene-pg",
            limit=20,
            offset=5,
        )
    )

    list_sql, list_params = list_cursor.executed[0]
    count_sql, count_params = count_cursor.executed[0]
    assert response["total"] == 1
    assert response["items"][0]["id"] == "batch-pg-filter"
    assert "COALESCE(report_json->>'qualityStatus', 'pending') = %s" in list_sql
    assert "COALESCE(report_json->>'publishRiskStatus', 'unknown') = %s" in list_sql
    assert "COALESCE(report_json->'imageryLinks', '[]'::jsonb) @> %s::jsonb" in list_sql
    assert "LIMIT %s OFFSET %s" in list_sql
    assert list_params[:4] == ("completed", "approved", "warning", "warning")
    assert list_params[-2:] == (20, 5)
    assert "SELECT COUNT(*) FROM import_batches" in count_sql
    assert count_params[:4] == ("completed", "approved", "warning", "warning")


def test_import_rejects_missing_block_code_with_invalid_report(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("bad.geojson", io.BytesIO(geojson_bytes(include_block_code=False)), "application/geo+json")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validRows"] == 0
    assert body["invalidRows"] == 1
    assert body["report"]["errors"][0]["row"] == 1
    assert "blockCode" in body["report"]["errors"][0]["message"]


def test_mysql_import_writes_only_current_batch_without_loading_full_ledger(monkeypatch):
    from server.modules import imports as imports_module

    saved_blocks: list[dict] = []
    rights_blocks: list[dict] = []
    monkeypatch.setattr(imports_module, "use_mysql", lambda: True)
    monkeypatch.setattr(imports_module, "use_postgis", lambda: False)
    monkeypatch.setattr(
        imports_module,
        "load_all_blocks",
        lambda: (_ for _ in ()).throw(AssertionError("full forest ledger loaded")),
    )
    monkeypatch.setattr(
        imports_module,
        "block_identities_by_codes",
        lambda codes: {
            "IMPORT-EXISTING": {
                "id": "existing-id",
                "blockCode": "IMPORT-EXISTING",
                "createdAt": "2025-01-01T00:00:00+00:00",
                "deletedAt": None,
            }
        },
        raising=False,
    )
    monkeypatch.setattr(imports_module, "save_blocks", lambda blocks: saved_blocks.extend(blocks))
    monkeypatch.setattr(
        imports_module,
        "upsert_right_archives_from_blocks",
        lambda blocks: rights_blocks.extend(blocks) or [],
        raising=False,
    )
    monkeypatch.setattr(imports_module, "save_import_report", lambda _report: None)
    monkeypatch.setattr(imports_module, "require_target_area_allowed", lambda *_args: None)
    records = [
        {"blockCode": "IMPORT-EXISTING", "name": "已有林班", "countyCode": "350703"},
        {"blockCode": "IMPORT-NEW", "name": "新增林班", "countyCode": "350703"},
    ]

    result = imports_module.execute_forest_block_import(
        records=records,
        file_name="mysql-batch.csv",
        strategy="upsert",
        context=SimpleNamespace(user="batch-operator"),
    )

    assert len(saved_blocks) == 2
    assert saved_blocks[0]["id"] == "existing-id"
    assert saved_blocks[0]["createdAt"] == "2025-01-01T00:00:00+00:00"
    assert {item["blockCode"] for item in saved_blocks} == {"IMPORT-EXISTING", "IMPORT-NEW"}
    assert len(rights_blocks) == 2
    assert [item["action"] for item in result["importedBlocks"]] == ["updated", "created"]


def test_import_requires_write_access_for_explicit_read_only_role(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("forest.geojson", io.BytesIO(geojson_bytes()), "application/geo+json")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "viewer"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission required: imports.forestBlocks.create"


def test_import_rejects_missing_name_with_invalid_report(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "missing-name.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "blockCode": "IMP-NAME-001",
                            "countyCode": "350703",
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validRows"] == 0
    assert body["invalidRows"] == 1
    assert body["report"]["errors"][0]["row"] == 1
    assert "name" in body["report"]["errors"][0]["message"]

    listed = app_client.get("/api/forest-blocks?q=IMP-NAME-001")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


def test_import_counts_invalid_rows_once_when_row_has_multiple_errors(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "missing-required-fields.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "countyCode": "350703",
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["totalRows"] == 1
    assert body["validRows"] == 0
    assert body["invalidRows"] == 1
    assert body["report"]["errors"] == [
        {"row": 1, "message": "blockCode is required"},
        {"row": 1, "message": "name is required"},
    ]


def test_database_import_reports_do_not_remain_in_process_cache(
    isolated_env, monkeypatch, reload_platform_modules
):
    imports_module = reload_imports_module(reload_platform_modules)
    report = {
        "id": "large-mysql-import",
        "fileName": "million-acre.geojson",
        "importedBlocks": [{"id": f"block-{index}"} for index in range(1000)],
    }
    persisted: list[dict] = []
    imports_module.IMPORT_REPORTS.clear()
    monkeypatch.setattr(imports_module, "use_mysql", lambda: True)
    monkeypatch.setattr(imports_module, "use_postgis", lambda: False)
    monkeypatch.setattr(imports_module, "upsert_import_report_mysql", persisted.append)

    imports_module.save_import_report(report)

    assert persisted == [report]
    assert "large-mysql-import" not in imports_module.IMPORT_REPORTS


def test_database_import_report_detail_is_not_retained_in_process_cache(
    isolated_env, monkeypatch, reload_platform_modules
):
    imports_module = reload_imports_module(reload_platform_modules)
    report = {"id": "mysql-detail", "fileName": "detail.geojson", "importedBlocks": []}
    imports_module.IMPORT_REPORTS.clear()
    monkeypatch.setattr(imports_module, "use_mysql", lambda: True)
    monkeypatch.setattr(imports_module, "use_postgis", lambda: False)
    monkeypatch.setattr(imports_module, "load_import_report_mysql", lambda _batch_id: report)

    loaded = imports_module.get_report_or_404("mysql-detail")

    assert loaded is report
    assert "mysql-detail" not in imports_module.IMPORT_REPORTS


def test_import_reports_invalid_area_mu_without_saving_block(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "bad-area.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "blockCode": "BAD-AREA-001",
                            "name": "Bad area block",
                            "countyCode": "350703",
                            "areaMu": "not-a-number",
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validRows"] == 0
    assert body["invalidRows"] == 1
    assert body["report"]["errors"] == [{"row": 1, "message": "areaMu must be a number"}]

    listed = app_client.get("/api/forest-blocks?q=BAD-AREA-001")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


def test_import_csv_endpoint_supports_chinese_aliases(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("forest.csv", io.BytesIO(csv_bytes()), "text/csv")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validRows"] == 1
    assert body["invalidRows"] == 0

    listed = app_client.get("/api/forest-blocks?q=导入林班二")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["blockCode"] == "CSV-001"
    assert item["countyCode"] == "350703"
    assert item["areaMu"] == 42.5


def test_import_xlsx_endpoint_supports_chinese_aliases(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "forest.xlsx",
                io.BytesIO(xlsx_bytes()),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validRows"] == 1
    assert body["invalidRows"] == 0

    listed = app_client.get("/api/forest-blocks?q=导入林班三")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["blockCode"] == "XLSX-001"
    assert item["countyName"] == "建阳区"
    assert item["townName"] == "麻沙镇"
    assert item["areaMu"] == 15.8


def test_import_kmz_endpoint_splits_kml_placemarks_into_blocks(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("masha.kmz", io.BytesIO(kmz_bytes()), "application/vnd.google-earth.kmz")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fileType"] == "kmz"
    assert body["totalRows"] == 2
    assert body["validRows"] == 2
    assert body["invalidRows"] == 0

    listed = app_client.get("/api/forest-blocks?q=35078410620204107030")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    item = listed.json()["items"][0]
    assert item["blockCode"] == "35078410620204107030"
    assert item["name"] == "13"
    assert item["countyCode"] == "350784"
    assert item["townCode"] == "106"
    assert item["villageCode"] == "202"
    assert item["areaMu"] == pytest.approx(97.2915, rel=0.001)
    assert item["geometry"]["type"] == "MultiPolygon"
    assert "rights" not in item["properties"]

    rights = app_client.get("/api/forest-rights?q=Jianou%20Masha%20Bamboo%20Cooperative")
    assert rights.status_code == 200
    archive = rights.json()["items"][0]
    assert archive["holder"] == "Jianou Masha Bamboo Cooperative"
    assert "35078410620204107030" in archive["linkedBlockCodes"]


def test_import_ovkml_endpoint_parses_ovital_kml_area_strings(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("kang.ovkml", io.BytesIO(ovkml_bytes()), "application/xml")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fileType"] == "ovkml"
    assert body["totalRows"] == 1
    assert body["validRows"] == 1

    listed = app_client.get("/api/forest-blocks?q=GJ24-25-1216-1422")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["blockCode"] == "GJ24-25-1216-1422"
    assert item["name"] == "GJ24-25-1216-1422"
    assert item["areaMu"] == pytest.approx(41.0047, rel=0.001)
    assert item["geometry"]["type"] == "MultiPolygon"


def test_import_ovobj_endpoint_imports_embedded_rights_archive_table(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("xiaoqiao-shangtun.ovobj", io.BytesIO(ovobj_bytes()), "application/octet-stream")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fileType"] == "ovobj"
    assert body["totalRows"] == 1
    assert body["validRows"] == 1

    listed = app_client.get("/api/forest-blocks?q=0350783105206GDYMSY03631")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["blockCode"] == "0350783105206GDYMSY03631"
    assert item["name"] == "xiaoqiao-shangtun"
    assert item["areaMu"] == 56
    assert item["geometry"] is None
    assert "ownershipStatus" not in item
    assert "managementStatus" not in item
    assert "rights" not in item["properties"]
    assert item["properties"]["source"]["geometryStatus"] == "not_found"

    rights = app_client.get("/api/forest-rights?q=0350783105206GDYMSY03631")
    assert rights.status_code == 200
    archive = rights.json()["items"][0]
    assert archive["certificateNo"] == "0350783105206GDYMSY03631"
    assert archive["holder"] == "Jianou Xiaoqiao Shangtun Village Committee"
    assert archive["linkedBlockCodes"] == ["0350783105206GDYMSY03631"]


def test_parse_import_file_rejects_unsupported_formats():
    from server.modules.imports import parse_import_file

    try:
        parse_import_file("forest.txt", b"hello")
    except Exception as exc:  # pragma: no cover - assertion follows
        assert getattr(exc, "status_code", None) == 400
        assert "Supported formats" in getattr(exc, "detail", "")
        return

    raise AssertionError("Unsupported import format should raise HTTP 400")


def test_parse_import_file_dispatches_zip_to_shapefile_parser(monkeypatch):
    from server.modules import imports as imports_module

    calls: list[bytes] = []

    def fake_parse_shapefile_zip(content: bytes):
        calls.append(content)
        return [{"blockCode": "ZIP-001", "name": "压缩林班"}]

    monkeypatch.setattr(imports_module, "parse_shapefile_zip", fake_parse_shapefile_zip)

    parsed = imports_module.parse_import_file("forest-blocks.zip", b"zip-bytes")

    assert calls == [b"zip-bytes"]
    assert parsed == [{"blockCode": "ZIP-001", "name": "压缩林班"}]


def test_parse_shapefile_zip_rejects_unsafe_member_paths(monkeypatch):
    from server.modules import imports as imports_module

    geometry_module = ModuleType("shapely.geometry")
    geometry_module.mapping = lambda geometry: geometry
    shapely_module = ModuleType("shapely")
    shapely_module.geometry = geometry_module
    monkeypatch.setitem(sys.modules, "shapely", shapely_module)
    monkeypatch.setitem(sys.modules, "shapely.geometry", geometry_module)
    monkeypatch.setitem(
        sys.modules,
        "pyogrio",
        SimpleNamespace(read_dataframe=lambda path: (_ for _ in ()).throw(AssertionError("should not read unsafe ZIP"))),
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.shp", b"not a real shapefile")

    try:
        imports_module.parse_shapefile_zip(buffer.getvalue())
    except Exception as exc:  # pragma: no cover - assertion follows
        assert getattr(exc, "status_code", None) == 400
        assert "unsafe path" in getattr(exc, "detail", "")
        return

    raise AssertionError("Unsafe Shapefile ZIP path should raise HTTP 400")


def test_import_preserves_deleted_records_in_storage(app_client, reload_platform_modules):
    created = app_client.post(
        "/api/forest-blocks",
        json={
            "blockCode": "KEEP-DELETED-001",
            "name": "Deleted block",
            "countyCode": "350703",
        },
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200
    block_id = created.json()["id"]

    deleted = app_client.delete(
        f"/api/forest-blocks/{block_id}",
        headers={"X-RS-Roles": "admin"},
    )
    assert deleted.status_code == 200

    imported = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "replacement.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "blockCode": "NEW-ACTIVE-001",
                            "name": "Replacement block",
                            "countyCode": "350703",
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    assert imported.status_code == 200
    assert imported.json()["invalidRows"] == 0

    _, database_module = reload_platform_modules()
    stored = json.loads(database_module.forest_blocks_json_path().read_text(encoding="utf-8"))

    assert {item["blockCode"] for item in stored} == {"KEEP-DELETED-001", "NEW-ACTIVE-001"}
    assert next(item for item in stored if item["blockCode"] == "KEEP-DELETED-001")["deletedAt"]


def test_import_sources_list_discovers_local_geojson(app_client, tmp_path, monkeypatch):
    from server.modules import imports as imports_module

    source_root = tmp_path / "converted-data"
    source_root.mkdir()
    source_file = source_root / "forest-source.geojson"
    source_file.write_bytes(geojson_bytes(block_code="SRC-LIST-001"))
    monkeypatch.setattr(imports_module, "IMPORT_SOURCE_ROOTS", [source_root])

    response = app_client.get(
        "/api/imports/forest-blocks/sources",
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["fileName"] == "forest-source.geojson"
    assert body["items"][0]["path"].endswith("forest-source.geojson")
    assert body["items"][0]["fileType"] == "geojson"


def test_import_sources_list_discovers_kmz_ovkml_and_ovobj(app_client, tmp_path, monkeypatch):
    from server.modules import imports as imports_module

    source_root = tmp_path / "converted-data"
    source_root.mkdir()
    (source_root / "masha.kmz").write_bytes(kmz_bytes())
    (source_root / "kang.ovkml").write_bytes(ovkml_bytes())
    (source_root / "xiaoqiao.ovobj").write_bytes(ovobj_bytes())
    monkeypatch.setattr(imports_module, "IMPORT_SOURCE_ROOTS", [source_root])

    response = app_client.get(
        "/api/imports/forest-blocks/sources",
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    file_types = {item["fileType"] for item in response.json()["items"]}
    assert {"kmz", "ovkml", "ovobj"} <= file_types


def test_import_source_rejects_path_outside_allowed_roots(app_client, tmp_path, monkeypatch):
    from server.modules import imports as imports_module

    source_root = tmp_path / "converted-data"
    source_root.mkdir()
    outside_file = tmp_path / "outside.geojson"
    outside_file.write_bytes(geojson_bytes(block_code="SRC-OUTSIDE-001"))
    monkeypatch.setattr(imports_module, "IMPORT_SOURCE_ROOTS", [source_root])

    response = app_client.post(
        "/api/imports/forest-blocks/sources/import",
        json={"path": str(outside_file), "strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 400
    assert "allowed import source" in response.json()["detail"]


def test_import_source_imports_discovered_geojson_into_ledger(app_client, tmp_path, monkeypatch):
    from server.modules import imports as imports_module

    source_root = tmp_path / "converted-data"
    source_root.mkdir()
    source_file = source_root / "formal-ledger.geojson"
    source_file.write_bytes(geojson_bytes(block_code="SRC-IMPORT-001"))
    monkeypatch.setattr(imports_module, "IMPORT_SOURCE_ROOTS", [source_root])

    imported = app_client.post(
        "/api/imports/forest-blocks/sources/import",
        json={"path": str(source_file), "strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert imported.status_code == 200
    assert imported.json()["validRows"] == 1

    listed = app_client.get("/api/forest-blocks?q=SRC-IMPORT-001")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["blockCode"] == "SRC-IMPORT-001"


def test_import_splits_forest_rights_archive_fields_from_block_ledger(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "rights.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "blockCode": "RIGHTS-IMPORT-001",
                            "name": "Rights import block",
                            "countyCode": "350703",
                            "ownershipStatus": "certified",
                            "managementStatus": "active",
                            "rights": {
                                "holder": "North Slope Cooperative",
                                "certificateNo": "CERT-IMPORT-001",
                                "archiveStatus": "complete",
                            },
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    assert response.json()["validRows"] == 1

    listed = app_client.get("/api/forest-blocks?q=RIGHTS-IMPORT-001")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["blockCode"] == "RIGHTS-IMPORT-001"
    assert "ownershipStatus" not in item
    assert "managementStatus" not in item
    assert "rights" not in item["properties"]

    rights = app_client.get("/api/forest-rights?q=CERT-IMPORT-001")
    assert rights.status_code == 200
    archive = rights.json()["items"][0]
    assert archive["holder"] == "North Slope Cooperative"
    assert archive["certificateNo"] == "CERT-IMPORT-001"
    assert archive["linkedBlockCodes"] == ["RIGHTS-IMPORT-001"]


def test_import_routes_archive_named_rows_to_rights_archive_only(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "bamboo-rights.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "blockCode": "BAMBOO-RIGHTS-001",
                            "name": "黄坑示范竹林林权档案",
                            "countyCode": "350703",
                            "countyName": "建阳区",
                            "townCode": "350703101",
                            "townName": "麻沙镇",
                            "villageName": "黄坑村",
                            "areaMu": 1260,
                            "rights": {
                                "holder": "黄坑村股份经济合作社",
                                "certificateNo": "闽林权证-350703-2026-0001",
                                "contractNo": "HK-ZL-2026-001",
                                "archiveStatus": "complete",
                            },
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    assert response.json()["validRows"] == 1

    listed = app_client.get("/api/forest-blocks?q=BAMBOO-RIGHTS-001")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0

    rights = app_client.get("/api/forest-rights?q=BAMBOO-RIGHTS-001")
    assert rights.status_code == 200
    assert rights.json()["total"] == 1
    archive = rights.json()["items"][0]
    assert archive["archiveCode"] == "BAMBOO-RIGHTS-001"
    assert archive["holder"] == "黄坑村股份经济合作社"
    assert archive["certificateNo"] == "闽林权证-350703-2026-0001"
    assert archive["linkedBlockCodes"] == []
    assert archive["properties"]["legacyBlockCode"] == "BAMBOO-RIGHTS-001"


def test_area_scoped_import_rejects_rows_outside_allowed_areas_without_saving(
    app_client, monkeypatch
):
    from server.modules import imports as imports_module

    save_calls: list[object] = []

    def fail_on_save(blocks):
        save_calls.append(blocks)
        raise AssertionError("save_blocks should not be called when all rows are rejected")

    monkeypatch.setattr(imports_module, "save_blocks", fail_on_save)

    response = app_client.post(
        "/api/imports/forest-blocks",
        files={
            "file": (
                "forbidden.geojson",
                io.BytesIO(
                    geojson_feature_bytes(
                        {
                            "blockCode": "FORBIDDEN-001",
                            "name": "Forbidden import",
                            "countyCode": "350702",
                        }
                    )
                ),
                "application/geo+json",
            )
        },
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "operator", "X-RS-Areas": "350703"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validRows"] == 0
    assert body["invalidRows"] == 1
    assert body["report"]["errors"][0]["row"] == 1
    assert "Area access denied" in body["report"]["errors"][0]["message"]
    assert save_calls == []

    listed = app_client.get(
        "/api/forest-blocks?q=FORBIDDEN-001",
        headers={"X-RS-Roles": "operator", "X-RS-Areas": "350703"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 0
