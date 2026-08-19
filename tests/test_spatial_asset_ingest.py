from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from server.modules.forest_blocks import bbox_intersects
from server.modules.spatial_assets import (
    convert_point_cloud_to_3dtiles,
    coverage_analysis,
    effective_raster_footprint,
    point_cloud_collection_metadata,
)
from tests.test_forest_blocks import sample_block_payload


def write_test_geotiff(path: Path) -> None:
    pixels = np.zeros((100, 100), dtype=np.uint8)
    pixels[10:90, 10:60] = 120
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=100,
        height=100,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(118.10, 26.52, 0.0003, 0.0002),
        nodata=0,
    ) as dataset:
        dataset.write(pixels, 1)


def write_las_14_with_wkt(path: Path, *, bounds: tuple[float, float, float, float, float, float]) -> None:
    wkt = (
        'PROJCS["CGCS2000 / Gauss-Kruger CM 117E",GEOGCS["China Geodetic Coordinate System 2000",'
        'DATUM["China_2000",SPHEROID["CGCS2000",6378137,298.257222101]],PRIMEM["Greenwich",0],'
        'UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
        'PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",117],PARAMETER["scale_factor",1],'
        'PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG","4509"]]'
    ).encode("utf-8") + b"\0"
    header = bytearray(375)
    header[:4] = b"LASF"
    header[24] = 1
    header[25] = 4
    struct.pack_into("<H", header, 94, 375)
    struct.pack_into("<I", header, 96, 375 + 54 + len(wkt))
    struct.pack_into("<I", header, 100, 1)
    header[104] = 7
    struct.pack_into("<H", header, 105, 36)
    struct.pack_into("<Q", header, 247, 1234)
    min_x, min_y, min_z, max_x, max_y, max_z = bounds
    struct.pack_into("<dddddd", header, 179, max_x, min_x, max_y, min_y, max_z, min_z)
    vlr = bytearray(54)
    vlr[2:18] = b"LASF_Projection\0"
    struct.pack_into("<H", vlr, 18, 2112)
    struct.pack_into("<H", vlr, 20, len(wkt))
    path.write_bytes(header + vlr + wkt)


def test_effective_raster_footprint_uses_nodata_not_full_tiff_extent(tmp_path):
    path = tmp_path / "masked.tif"
    write_test_geotiff(path)

    footprint = effective_raster_footprint(path, max_dimension=256)

    assert footprint["sourceCrs"] == "EPSG:4326"
    assert 118.102 <= footprint["bounds"][0] <= 118.104
    assert 118.117 <= footprint["bounds"][2] <= 118.119
    assert footprint["bounds"][2] < 118.13


def test_coverage_analysis_returns_multi_block_overlap_metrics():
    footprint = {
        "type": "Polygon",
        "coordinates": [[[118.10, 26.50], [118.13, 26.50], [118.13, 26.52], [118.10, 26.52], [118.10, 26.50]]],
    }
    blocks = [
        {"id": "b1", "blockCode": "B-001", "name": "一号林班", "geometry": {"type": "Polygon", "coordinates": [[[118.10, 26.50], [118.115, 26.50], [118.115, 26.52], [118.10, 26.52], [118.10, 26.50]]]}},
        {"id": "b2", "blockCode": "B-002", "name": "二号林班", "geometry": {"type": "Polygon", "coordinates": [[[118.115, 26.50], [118.13, 26.50], [118.13, 26.52], [118.115, 26.52], [118.115, 26.50]]]}},
    ]

    result = coverage_analysis(footprint, blocks)

    assert {item["blockCode"] for item in result["matches"]} == {"B-001", "B-002"}
    assert all(49 <= item["imageryCoveragePercent"] <= 51 for item in result["matches"])
    assert result["suggestedBlockCodes"] == [item["blockCode"] for item in result["matches"]]


def test_bbox_filter_accepts_polygon_and_multipolygon_geometry():
    ring = [[118.10, 26.50], [118.12, 26.50], [118.12, 26.52], [118.10, 26.52], [118.10, 26.50]]

    assert bbox_intersects({"type": "Polygon", "coordinates": [ring]}, [118.11, 26.51, 118.13, 26.53])
    assert bbox_intersects({"type": "MultiPolygon", "coordinates": [[ring]]}, [118.11, 26.51, 118.13, 26.53])


def test_las_collection_metadata_reads_wkt_and_unions_tiles(tmp_path):
    first = tmp_path / "cloud0.las"
    second = tmp_path / "cloud1.las"
    write_las_14_with_wkt(first, bounds=(503000, 3002800, 600, 503500, 3003300, 900))
    write_las_14_with_wkt(second, bounds=(503400, 3003200, 650, 504000, 3003800, 950))

    metadata = point_cloud_collection_metadata([first, second])

    assert metadata["fileCount"] == 2
    assert metadata["pointCount"] == 2468
    assert metadata["crs"] == "EPSG:4509"
    assert metadata["nativeBounds"] == [503000.0, 3002800.0, 600.0, 504000.0, 3003800.0, 950.0]
    assert metadata["bounds"][0] < metadata["bounds"][2]


def test_py3dtiles_conversion_leaves_destination_creation_to_converter(tmp_path, monkeypatch):
    source = tmp_path / "cloud0.las"
    source.write_bytes(b"LASF")
    output = tmp_path / "result" / "3dtiles"
    captured: dict[str, object] = {}

    monkeypatch.setattr("server.modules.spatial_assets.shutil.which", lambda _value: "py3dtiles")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        assert not output.exists()
        output.mkdir()
        (output / "tileset.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("server.modules.spatial_assets.subprocess.run", fake_run)

    convert_point_cloud_to_3dtiles([source], output)

    assert captured["command"] == [
        "py3dtiles",
        "convert",
        "--srs_out",
        "4978",
        "--pyproj-always-xy",
        "--out",
        str(output),
        str(source),
    ]


def test_point_cloud_upload_session_is_chunk_idempotent_and_resumable(app_client, monkeypatch):
    import server.app as app_module

    monkeypatch.setattr(app_module.TASK_EXECUTOR, "submit", lambda *_args, **_kwargs: None)
    payload = {
        "name": "邵武 S1 点云",
        "missionId": "DJI-S1",
        "capturedAt": "2026-08-13T12:00:00",
        "outputs": ["copc", "3dtiles"],
        "files": [{"name": "cloud0.las", "size": 10, "lastModified": 1}],
    }
    created = app_client.post("/api/point-clouds/upload-sessions", json=payload, headers={"X-RS-Roles": "admin"})
    assert created.status_code == 200
    session_id = created.json()["id"]
    body = b"0123456789"
    headers = {
        "X-RS-Roles": "admin",
        "Content-Range": "bytes 0-9/10",
        "X-Chunk-SHA256": hashlib.sha256(body).hexdigest(),
        "Content-Type": "application/octet-stream",
    }

    first = app_client.put(f"/api/point-clouds/upload-sessions/{session_id}/files/0/chunks/0", content=body, headers=headers)
    repeated = app_client.put(f"/api/point-clouds/upload-sessions/{session_id}/files/0/chunks/0", content=body, headers=headers)
    status = app_client.get(f"/api/point-clouds/upload-sessions/{session_id}", headers={"X-RS-Roles": "admin"})
    completed = app_client.post(f"/api/point-clouds/upload-sessions/{session_id}/complete", headers={"X-RS-Roles": "admin"})

    assert first.status_code == 200
    assert repeated.status_code == 200
    assert status.json()["uploadedBytes"] == 10
    assert status.json()["files"][0]["receivedChunks"] == [0]
    assert completed.status_code == 202
    assert completed.json()["task"]["assetType"] == "pointcloud"


def test_point_cloud_directory_registration_excludes_hidden_temp_tree(app_client, isolated_env, monkeypatch):
    import server.app as app_module

    import_root = isolated_env / "point-cloud-inbox"
    import_root.mkdir()
    (import_root / "cloud0.las").write_bytes(b"LASF")
    hidden = import_root / ".temp" / "PointCloud"
    hidden.mkdir(parents=True)
    (hidden / "intermediate.las").write_bytes(b"LASF")
    app_module.IMPORT_DIRS = [import_root]
    monkeypatch.setattr(app_module.TASK_EXECUTOR, "submit", lambda *_args, **_kwargs: None)

    response = app_client.post(
        "/api/point-clouds/register",
        headers={"X-RS-Roles": "admin"},
        json={"path": str(import_root), "name": "正式点云", "outputs": ["copc", "3dtiles"]},
    )

    assert response.status_code == 202
    source_paths = response.json()["task"]["sourcePaths"]
    assert len(source_paths) == 1
    assert source_paths[0].endswith("cloud0.las")


def test_confirm_coverage_writes_scene_codes_and_formal_links(app_client):
    import server.app as app_module
    import server.modules.forest_scene_links as scene_links_module

    block = app_client.post(
        "/api/forest-blocks",
        headers={"X-RS-Roles": "admin"},
        json=sample_block_payload("AUTO-COVER-001"),
    ).json()
    scene = {
        "id": "scene-auto-cover",
        "name": "自动匹配影像",
        "assetType": "orthophoto",
        "processingStage": "coverage-review",
        "linkedBlockCodes": [],
        "bounds": [118.10, 26.50, 118.12, 26.52],
        "coverageAnalysis": {"requiresConfirmation": True, "matches": [], "suggestedBlockCodes": []},
        "allowedRoles": [],
        "allowedUsers": [],
    }
    app_module.save_scene(scene)
    scene_links_module.save_scene_links(
        [
            {
                "forestBlockId": block["id"],
                "sceneId": scene["id"],
                "relationType": "source-evidence",
                "capturedAt": None,
                "confidence": None,
            }
        ]
    )

    confirmed = app_client.post(
        "/api/scenes/scene-auto-cover/coverage/confirm",
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
        json={"blockCodes": ["AUTO-COVER-001"]},
    )
    links = app_client.get(f"/api/forest-blocks/{block['id']}/scenes", headers={"X-RS-Roles": "admin"})

    assert confirmed.status_code == 200
    assert confirmed.json()["processingStage"] == "ready"
    assert confirmed.json()["coverageAnalysis"]["confirmedBy"] == "reviewer"
    assert confirmed.json()["linkedBlockCodes"] == ["AUTO-COVER-001"]
    assert links.status_code == 200
    assert {item["relationType"] for item in links.json()["items"]} == {"coverage", "source-evidence"}
    assert {item["sceneId"] for item in links.json()["items"]} == {"scene-auto-cover"}
