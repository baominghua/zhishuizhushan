from __future__ import annotations

import io
import json

from openpyxl import Workbook


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
    batch = app_client.get(f"/api/imports/{batch_id}")
    report = app_client.get(f"/api/imports/{batch_id}/report")

    assert batch.status_code == 200
    assert report.status_code == 200
    assert batch.json()["id"] == batch_id
    assert report.json()["totalRows"] == 1


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


def test_area_scoped_import_rejects_rows_outside_allowed_areas_without_saving(
    app_client, reload_platform_modules
):
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

    listed = app_client.get(
        "/api/forest-blocks?q=FORBIDDEN-001",
        headers={"X-RS-Roles": "operator", "X-RS-Areas": "350703"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 0

    _, database_module = reload_platform_modules()
    stored = json.loads(database_module.forest_blocks_json_path().read_text(encoding="utf-8"))
    assert stored == []
