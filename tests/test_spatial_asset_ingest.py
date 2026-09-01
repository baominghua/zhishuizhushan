from __future__ import annotations

import hashlib
import json
import importlib
import struct
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from server.modules.forest_blocks import bbox_intersects
from server.modules.spatial_assets import (
    convert_point_cloud_to_copc,
    convert_point_cloud_to_3dtiles,
    coverage_analysis,
    effective_raster_footprint,
    inspect_3d_tileset,
    is_complete_copc_output,
    normalized_tileset_document,
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


def write_pnts(
    path: Path,
    point_count: int = 12,
    *,
    feature_table: dict | None = None,
    batch_table: dict | None = None,
) -> None:
    feature_json = json.dumps(
        feature_table or {"POINTS_LENGTH": point_count},
        separators=(",", ":"),
    ).encode("utf-8")
    batch_json = json.dumps(batch_table or {}, separators=(",", ":")).encode("utf-8") if batch_table else b""
    byte_length = 28 + len(feature_json) + len(batch_json)
    path.write_bytes(
        b"pnts"
        + struct.pack("<IIIIII", 1, byte_length, len(feature_json), 0, len(batch_json), 0)
        + feature_json
        + batch_json
    )


def write_b3dm(path: Path) -> None:
    path.write_bytes(b"b3dm" + struct.pack("<IIIIII", 1, 28, 0, 0, 0, 0))


def write_tileset(path: Path, content_uri: str = "tile.pnts", *, version: str = "0.0") -> None:
    path.write_text(
        json.dumps(
            {
                "asset": {"version": version},
                "geometricError": 100,
                "root": {
                    "boundingVolume": {
                        "region": [
                            118.10 * np.pi / 180,
                            26.50 * np.pi / 180,
                            118.12 * np.pi / 180,
                            26.52 * np.pi / 180,
                            0,
                            500,
                        ]
                    },
                    "geometricError": 0,
                    "content": {"uri": content_uri},
                },
            }
        ),
        encoding="utf-8",
    )


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
    assert metadata["dimensions"] == [
        "Blue", "Classification", "GpsTime", "Green", "Intensity", "NumberOfReturns",
        "PointSourceId", "Red", "ReturnNumber", "ScanAngle", "UserData", "X", "Y", "Z",
    ]
    assert metadata["attributeModes"] == ["rgb", "elevation", "return", "intensity", "gps-time"]
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
        "--extra-fields",
        "intensity",
        "--extra-fields",
        "return_number",
        "--extra-fields",
        "number_of_returns",
        "--out",
        str(output),
        str(source),
    ]


def test_copc_conversion_recenters_large_projected_coordinates(tmp_path, monkeypatch):
    source = tmp_path / "cloud0.las"
    write_las_14_with_wkt(
        source,
        bounds=(5038000.0, 3002800.0, 514.0, 5039764.81, 3003800.0, 757.0),
    )
    output = tmp_path / "result" / "dataset.copc.laz"
    captured: dict[str, object] = {}

    monkeypatch.setattr("server.modules.spatial_assets.shutil.which", lambda _value: "pdal")

    def fake_converter(command, label, cancel_check=None):
        captured["command"] = command
        captured["label"] = label
        captured["cancel_check"] = cancel_check

    monkeypatch.setattr("server.modules.spatial_assets._run_converter", fake_converter)

    convert_point_cloud_to_copc([source], output)

    pipeline_path = output.with_suffix(".pipeline.json")
    document = json.loads(pipeline_path.read_text(encoding="utf-8"))
    writer = document["pipeline"][-1]
    assert captured["label"] == "PDAL COPC"
    assert writer["forward"] == "vlr"
    assert writer["scale_x"] == pytest.approx(0.001)
    assert writer["offset_x"] == pytest.approx((5038000.0 + 5039764.81) / 2)
    assert abs((5039764.81 - writer["offset_x"]) / writer["scale_x"]) < (2**31) - 1024


def test_completed_copc_validation_requires_copc_vlr_and_matching_point_count(tmp_path, monkeypatch):
    output = tmp_path / "dataset.copc.laz"
    output.write_bytes(b"LASF" + bytes(400))
    monkeypatch.setattr(
        "server.modules.spatial_assets.read_las_header",
        lambda _path: {"isCopc": True, "pointCount": 123, "nativeBounds": [1, 2, 3, 4, 5, 6]},
    )

    assert is_complete_copc_output(output, 123) is True
    assert is_complete_copc_output(output, 124) is False


def test_dji_tileset_inspection_reads_pnts_and_normalizes_legacy_asset_version(tmp_path):
    root = tmp_path / "tileset.json"
    write_pnts(tmp_path / "tile.pnts", point_count=321)
    write_tileset(root)

    metadata = inspect_3d_tileset(root)
    normalized = normalized_tileset_document(root)
    authenticated = normalized_tileset_document(root, service_token="secret token")

    assert metadata["contentType"] == "pnts"
    assert metadata["pointCount"] == 321
    assert metadata["tileCount"] == 1
    assert metadata["formats"] == {"pnts": 1}
    assert metadata["assetVersions"] == ["0.0"]
    assert metadata["normalizesDjiVersion"] is True
    assert metadata["bounds"] == pytest.approx([118.10, 26.50, 118.12, 26.52])
    assert normalized["asset"]["version"] == "1.0"
    assert authenticated["root"]["content"]["uri"] == "tile.pnts?token=secret+token"
    assert json.loads(root.read_text(encoding="utf-8"))["asset"]["version"] == "0.0"


def test_dji_tileset_inspection_reports_actual_renderable_batch_properties(tmp_path):
    root = tmp_path / "tileset.json"
    write_pnts(
        tmp_path / "tile.pnts",
        point_count=321,
        feature_table={"POINTS_LENGTH": 321, "POSITION": {"byteOffset": 0}, "RGB": {"byteOffset": 100}},
        batch_table={
            "ECHO": {"byteOffset": 0, "componentType": "UNSIGNED_BYTE", "type": "SCALAR"},
            "INTENSITY": {"byteOffset": 321, "componentType": "UNSIGNED_BYTE", "type": "SCALAR"},
        },
    )
    write_tileset(root)

    metadata = inspect_3d_tileset(root)

    assert metadata["pointCloudRenderableModes"] == ["elevation", "intensity", "return", "rgb"]
    assert metadata["pointCloudRenderableProperties"] == {
        "return": "ECHO",
        "intensity": "INTENSITY",
    }


def test_dji_tileset_inspection_identifies_b3dm_oblique_model(tmp_path):
    root = tmp_path / "tileset.json"
    write_b3dm(tmp_path / "tile.b3dm")
    write_tileset(root, "tile.b3dm", version="1.0")

    metadata = inspect_3d_tileset(root)

    assert metadata["contentType"] == "b3dm"
    assert metadata["pointCount"] == 0
    assert metadata["formats"] == {"b3dm": 1}
    assert metadata["normalizesDjiVersion"] is False


def test_dji_tileset_inspection_rejects_truncated_binary_tile(tmp_path):
    root = tmp_path / "tileset.json"
    (tmp_path / "tile.pnts").write_bytes(b"pnts" + struct.pack("<II", 1, 12))
    write_tileset(root)

    with pytest.raises(ValueError, match="瓦片头不完整"):
        inspect_3d_tileset(root)


@pytest.mark.parametrize("content_uri", ["../outside.pnts", "missing.pnts", "https://example.com/tile.pnts"])
def test_dji_tileset_inspection_rejects_unsafe_or_missing_references(tmp_path, content_uri):
    write_pnts(tmp_path.parent / "outside.pnts")
    root = tmp_path / "tileset.json"
    write_tileset(root, content_uri)

    with pytest.raises(ValueError):
        inspect_3d_tileset(root)


def test_dji_tileset_registration_accepts_allowed_directory_without_copying(app_client, isolated_env, monkeypatch):
    import server.app as app_module

    import_root = isolated_env / "tiles-inbox"
    tiles_dir = import_root / "terra_pnts"
    tiles_dir.mkdir(parents=True)
    write_pnts(tiles_dir / "tile.pnts")
    write_tileset(tiles_dir / "tileset.json")
    app_module.IMPORT_DIRS = [import_root]
    monkeypatch.setattr(app_module.TASK_EXECUTOR, "submit", lambda *_args, **_kwargs: None)

    response = app_client.post(
        "/api/3d-tiles/register",
        headers={"X-RS-Roles": "admin"},
        json={"path": str(tiles_dir), "name": "DJI 已生成点云"},
    )

    assert response.status_code == 202
    task = response.json()["task"]
    assert task["type"] == "3dtiles-register"
    assert task["sourcePath"] == str((tiles_dir / "tileset.json").resolve())
    assert task["assetType"] == "oblique3d"
    assert not (isolated_env / "point-clouds" / task["sceneId"]).exists()


def test_registered_dji_tileset_service_normalizes_json_and_serves_binary(app_client, isolated_env):
    import server.app as app_module

    tiles_dir = isolated_env / "registered-tiles"
    tiles_dir.mkdir()
    write_pnts(tiles_dir / "tile.pnts", point_count=7)
    write_tileset(tiles_dir / "tileset.json")
    app_module.save_scene(
        {
            "id": "tiles-direct-service",
            "name": "直接登记三维成果",
            "assetType": "pointcloud",
            "tilesetPath": str(tiles_dir / "tileset.json"),
            "allowedRoles": [],
            "allowedUsers": [],
            "linkedBlockCodes": [],
            "processingStage": "ready",
        }
    )

    document = app_client.get(
        "/api/scenes/tiles-direct-service/point-cloud/tiles/tileset.json?token=visual-token",
        headers={"X-RS-Roles": "admin"},
    )
    binary = app_client.get(
        "/api/scenes/tiles-direct-service/point-cloud/tiles/tile.pnts",
        headers={"X-RS-Roles": "admin"},
    )

    assert document.status_code == 200
    assert document.json()["asset"]["version"] == "1.0"
    assert document.json()["root"]["content"]["uri"] == "tile.pnts?token=visual-token"
    assert binary.status_code == 200
    assert binary.content[:4] == b"pnts"


def test_copc_scene_exposes_streamable_filename_and_byte_ranges(app_client, isolated_env):
    import server.app as app_module

    copc_path = isolated_env / "streamable.copc.laz"
    copc_path.write_bytes(b"LASF" + bytes(range(64)))
    app_module.save_scene(
        {
            "id": "copc-stream-service",
            "name": "COPC 流式成果",
            "assetType": "pointcloud",
            "copcPath": str(copc_path),
            "allowedRoles": [],
            "allowedUsers": [],
            "linkedBlockCodes": [],
            "processingStage": "ready",
        }
    )

    detail = app_client.get("/api/scenes/copc-stream-service", headers={"X-RS-Roles": "admin"})
    ranged = app_client.get(
        "/api/scenes/copc-stream-service/point-cloud/data.copc.laz",
        headers={"X-RS-Roles": "admin", "Range": "bytes=4-11"},
    )

    assert detail.status_code == 200
    assert detail.json()["copcUrl"] == "/api/scenes/copc-stream-service/point-cloud/data.copc.laz"
    assert ranged.status_code == 206
    assert ranged.headers["accept-ranges"] == "bytes"
    assert ranged.headers["content-range"] == f"bytes 4-11/{copc_path.stat().st_size}"
    assert ranged.content == bytes(range(8))


def test_registered_pnts_scene_auto_associates_sibling_las_and_real_render_fields(app_client, isolated_env):
    import server.app as app_module

    project = isolated_env / "inbox" / "尤溪项目地块"
    tiles_dir = project / "terra_pnts"
    las_dir = project / "terra_las_1_4"
    tiles_dir.mkdir(parents=True)
    las_dir.mkdir(parents=True)
    write_pnts(
        tiles_dir / "tile.pnts",
        point_count=19,
        feature_table={"POINTS_LENGTH": 19, "POSITION": {"byteOffset": 0}, "RGB": {"byteOffset": 228}},
        batch_table={
            "ECHO": {"byteOffset": 0, "componentType": "UNSIGNED_BYTE", "type": "SCALAR"},
            "INTENSITY": {"byteOffset": 19, "componentType": "UNSIGNED_SHORT", "type": "SCALAR"},
        },
    )
    write_tileset(tiles_dir / "tileset.json")
    write_las_14_with_wkt(
        las_dir / "cloud0.las",
        bounds=(503000, 3002800, 600, 503500, 3003300, 900),
    )
    app_module.IMPORT_DIRS = [isolated_env]
    app_module.cached_3d_tileset_metadata.cache_clear()
    app_module.cached_sibling_las_metadata.cache_clear()
    app_module.save_scene(
        {
            "id": "tiles-auto-associated",
            "name": "尤溪项目点云",
            "assetType": "pointcloud",
            "tilesetPath": str(tiles_dir / "tileset.json"),
            "allowedRoles": [],
            "allowedUsers": [],
            "linkedBlockCodes": [],
            "processingStage": "ready",
        }
    )

    response = app_client.get(
        "/api/scenes/tiles-auto-associated",
        headers={"X-RS-Roles": "admin"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pointCloudRenderableModes"] == ["elevation", "intensity", "return", "rgb"]
    assert payload["pointCloudRenderableProperties"] == {"return": "ECHO", "intensity": "INTENSITY"}
    assert payload["pointCloudFileCount"] == 1
    assert payload["pointCloudSourcePaths"] == [str((las_dir / "cloud0.las").resolve())]
    assert payload["pointCloudAttributeModes"] == ["rgb", "elevation", "return", "intensity", "gps-time"]


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


def test_point_cloud_task_keeps_completed_copc_when_optional_pnts_conversion_fails(app_client, isolated_env, monkeypatch):
    import server.app as app_module

    source = isolated_env / "large-cloud.las"
    source.write_bytes(b"LASF-large-point-cloud")
    dataset_dir = isolated_env / "point-cloud-result"
    task_id = "task-copc-primary"
    scene_id = "pc-copc-primary"
    point_cloud = {
        "bounds": [118.0, 26.0, 118.1, 26.1],
        "nativeBounds": [500000.0, 2876000.0, 0.0, 510000.0, 2887000.0, 900.0],
        "crs": "EPSG:4509",
        "footprint": {
            "type": "Polygon",
            "coordinates": [[[118.0, 26.0], [118.1, 26.0], [118.1, 26.1], [118.0, 26.1], [118.0, 26.0]]],
        },
        "pointCount": 73_904_650,
        "fileCount": 1,
        "versions": ["1.4"],
        "pointFormats": [7],
        "dimensions": ["X", "Y", "Z", "Red", "Green", "Blue", "Intensity", "ReturnNumber"],
        "attributeModes": ["rgb", "elevation", "return", "intensity"],
        "files": [{"name": source.name, "size": source.stat().st_size}],
    }
    trajectory = {
        "available": False,
        "fileCount": 0,
        "totalSize": 0,
        "formats": [],
        "path": "",
        "files": [],
    }
    app_module.upsert_task(
        {
            "id": task_id,
            "type": "pointcloud-register",
            "status": "queued",
            "progress": 0,
            "message": "Queued",
            "sceneId": scene_id,
            "name": "S7 LAS",
            "sourcePaths": [str(source)],
            "datasetPath": str(dataset_dir),
            "outputs": ["copc", "3dtiles"],
            "deleteOriginalOnSceneDelete": False,
            "analysisContext": {},
            "events": [],
        }
    )
    monkeypatch.setattr(app_module, "point_cloud_collection_metadata", lambda _paths: dict(point_cloud))
    monkeypatch.setattr(app_module, "discover_dji_trajectory_metadata", lambda _paths: dict(trajectory))
    monkeypatch.setattr(app_module, "apply_scene_coverage_analysis", lambda scene, *_args: scene)

    def create_copc(_sources, output, **_kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"COPC-ready")

    monkeypatch.setattr(app_module, "convert_point_cloud_to_copc", create_copc)
    monkeypatch.setattr(
        app_module,
        "convert_point_cloud_to_3dtiles",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("too many PNTS content files")),
    )

    app_module.run_point_cloud_conversion_task(task_id)

    task = app_module.find_task_record(task_id)
    scene = next(item for item in app_module.load_catalog() if item["id"] == scene_id)
    assert task["status"] == "completed"
    assert task["conversionWarnings"] == ["PNTS compatibility output was skipped: too many PNTS content files"]
    assert scene["storage"] == "COPC"
    assert scene["copcPath"].endswith("dataset.copc.laz")
    assert scene["tilesetPath"] == ""
    assert scene["transferStatus"] == "pointcloud-ready-with-warnings"


def test_point_cloud_retry_reuses_completed_copc_and_discards_partial_pnts(app_client, isolated_env, monkeypatch):
    import server.app as app_module

    source = isolated_env / "s7-cloud.las"
    source.write_bytes(b"LASF-source")
    dataset_dir = isolated_env / "s7-result"
    dataset_dir.mkdir()
    (dataset_dir / "dataset.copc.laz").write_bytes(b"complete-copc")
    partial_tiles = dataset_dir / "3dtiles"
    partial_tiles.mkdir()
    (partial_tiles / "partial.pnts").write_bytes(b"partial")
    point_cloud = {
        "bounds": [118.0, 26.0, 118.1, 26.1],
        "nativeBounds": [500000.0, 2876000.0, 0.0, 510000.0, 2887000.0, 900.0],
        "crs": "EPSG:4509",
        "footprint": {"type": "Polygon", "coordinates": [[[118.0, 26.0], [118.1, 26.0], [118.1, 26.1], [118.0, 26.1], [118.0, 26.0]]]},
        "pointCount": 73_904_650,
        "fileCount": 1,
        "versions": ["1.4"],
        "pointFormats": [7],
        "dimensions": ["X", "Y", "Z", "Red", "Green", "Blue"],
        "attributeModes": ["rgb", "elevation"],
        "files": [{"name": source.name, "size": source.stat().st_size}],
        "trajectory": {"available": False, "fileCount": 0, "totalSize": 0, "formats": [], "path": "", "files": []},
    }
    app_module.upsert_task({
        "id": "task-s7-resume", "type": "pointcloud-register", "status": "queued", "progress": 0,
        "message": "Queued retry", "sceneId": "pc-s7-resume", "name": "S7 LAS",
        "sourcePaths": [str(source)], "datasetPath": str(dataset_dir), "outputs": ["copc", "3dtiles"],
        "deleteOriginalOnSceneDelete": False, "analysisContext": {}, "events": [],
    })
    monkeypatch.setattr(app_module, "point_cloud_collection_metadata", lambda _paths: dict(point_cloud))
    monkeypatch.setattr(app_module, "discover_dji_trajectory_metadata", lambda _paths: dict(point_cloud["trajectory"]))
    monkeypatch.setattr(app_module, "apply_scene_coverage_analysis", lambda scene, *_args: scene)
    monkeypatch.setattr(app_module, "is_complete_copc_output", lambda *_args: True)
    monkeypatch.setattr(app_module, "convert_point_cloud_to_copc", lambda *_args, **_kwargs: pytest.fail("COPC must be reused"))
    monkeypatch.setattr(app_module, "convert_point_cloud_to_3dtiles", lambda *_args, **_kwargs: pytest.fail("partial PNTS must not restart"))

    app_module.run_point_cloud_conversion_task("task-s7-resume")

    task = app_module.find_task_record("task-s7-resume")
    scene = next(item for item in app_module.load_catalog() if item["id"] == "pc-s7-resume")
    assert task["status"] == "completed"
    assert task["reusedCopc"] is True
    assert "未完成的 PNTS" in task["conversionWarnings"][0]
    assert scene["storage"] == "COPC"
    assert not partial_tiles.exists()


def test_confirm_coverage_writes_scene_codes_and_formal_links(app_client, monkeypatch):
    import server.app as app_module
    import server.modules.forest_scene_links as scene_links_module

    # Other storage-backend tests reload this module with temporary settings.
    # Reload it here so the JSON-backed app client and direct setup helper share
    # the same isolated data directory during a full-suite run.
    importlib.reload(scene_links_module)

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
    app_module.save_tasks(
        [
            {
                "id": "task-scene-auto-cover",
                "sceneId": scene["id"],
                "type": "raster-conversion",
                "status": "completed",
                "progress": 100,
                "message": "COG scene is ready",
                "createdAt": "2026-08-27T16:00:00+08:00",
                "updatedAt": "2026-08-27T16:01:00+08:00",
                "events": [],
            }
        ]
    )
    monkeypatch.setattr(scene_links_module, "require_catalog_scene", lambda _scene_id: scene)
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
    archived_task = app_module.find_task_record("task-scene-auto-cover")
    assert archived_task["archivedAt"]
    assert archived_task["archivedBy"] == "reviewer"


def test_imagery_inventory_aggregates_full_catalog(app_client, monkeypatch):
    import server.app as app_module

    scenes = [
        {"id": "inventory-1", "assetType": "orthophoto", "status": "active", "originalSize": 1_000, "coverageAnalysis": {"effectiveAreaHa": 2}},
        {"id": "inventory-2", "assetType": "orthophoto", "status": "active", "size": 500, "coverageAnalysis": {"effectiveAreaHa": 1}},
        {"id": "inventory-3", "assetType": "pointcloud", "status": "active", "originalSize": 2_000},
        {"id": "inventory-4", "assetType": "dsm", "status": "archived", "originalSize": 9_999},
        {"id": "inventory-5", "assetType": "orthophoto", "fileName": "dsm.tif", "status": "active", "originalSize": 250, "coverageAnalysis": {"effectiveAreaHa": 2}},
    ]
    monkeypatch.setattr(app_module, "load_catalog", lambda **_kwargs: scenes)
    monkeypatch.setattr(app_module, "filter_scenes", lambda records, _context, **_kwargs: records)
    monkeypatch.setattr(app_module, "bamboo_resource_inventory", lambda _context: {"formal": {"available": False}, "estimated": {"available": False}, "policy": "test"})

    response = app_client.get("/api/scenes/inventory", headers={"X-RS-Roles": "admin"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["typeCount"] == 3
    assert payload["totalAreaMu"] == 75
    assert payload["totalSizeBytes"] == 3_750
    assert payload["items"][0] == {"assetType": "orthophoto", "count": 2, "areaMu": 45.0, "sizeBytes": 1_500}
    assert {item["assetType"]: item for item in payload["items"]}["dsm"] == {"assetType": "dsm", "count": 1, "areaMu": 30.0, "sizeBytes": 250}


def test_bamboo_resource_inventory_separates_formal_and_ai_estimates(monkeypatch):
    import server.app as app_module

    blocks = [
        {
            "id": "block-formal",
            "properties": {"bambooResourceSurvey": {"resourceStock": 800}},
            "yieldEstimate": {},
        },
        {
            "id": "block-estimated",
            "properties": {},
            "yieldEstimate": {
                "mosoInventory": {
                    "resourceStock": {"value": 1_200},
                    "abovegroundBiomass": {"value": 18.5},
                    "estimatedAt": "2026-08-28T10:00:00+08:00",
                },
                "mosoInventoryHistory": [{"resourceStock": {"value": 999_999}}],
            },
        },
    ]
    monkeypatch.setattr(app_module, "filtered_forest_blocks", lambda *_args, **_kwargs: blocks)
    monkeypatch.setattr(
        app_module,
        "formal_resource_snapshot_inventory",
        lambda _context: {
            "available": False,
            "stock": None,
            "stockAvailable": False,
            "standingVolumeM3": None,
            "biomassTons": None,
            "surveyedAreaMu": None,
            "blockIds": set(),
            "blockCount": 0,
            "snapshotCount": 0,
        },
    )

    payload = app_module.bamboo_resource_inventory(app_module.AuthContext("tester", {"admin"}, {"*"}, {"*"}))

    assert payload["formal"]["stock"] == 800
    assert payload["formal"]["blockCount"] == 1
    assert payload["estimated"]["stock"] == 1_200
    assert payload["estimated"]["biomassTons"] == 18.5
    assert payload["estimated"]["blockCount"] == 1


def test_formal_resource_snapshot_inventory_uses_latest_subcompartment_rows(monkeypatch):
    import server.app as app_module

    records = [
        {
            "id": "snapshot-old",
            "forestSubcompartmentId": "sub-1",
            "forestBlockId": "block-1",
            "sampledAt": "2026-01-01T00:00:00+08:00",
            "areaMu": 10,
            "bambooDensityPerMu": 10,
            "standingVolumeM3": 5,
            "biomassT": 1,
        },
        {
            "id": "snapshot-new",
            "forestSubcompartmentId": "sub-1",
            "forestBlockId": "block-1",
            "sampledAt": "2026-08-01T00:00:00+08:00",
            "areaMu": 10,
            "bambooDensityPerMu": 20,
            "standingVolumeM3": 12,
            "biomassT": 2.5,
        },
        {
            "id": "snapshot-2",
            "forestSubcompartmentId": "sub-2",
            "forestBlockId": "block-2",
            "sampledAt": "2026-07-01T00:00:00+08:00",
            "areaMu": 5,
            "bambooDensityPerMu": None,
            "standingVolumeM3": 8,
            "biomassT": 1.5,
        },
    ]
    monkeypatch.setattr(
        app_module,
        "list_resource_snapshots",
        lambda **kwargs: {"items": records if kwargs["offset"] == 0 else [], "total": len(records)},
    )

    payload = app_module.formal_resource_snapshot_inventory(
        app_module.AuthContext("tester", {"admin"}, {"*"}, {"*"})
    )

    assert payload["available"] is True
    assert payload["stock"] == 200
    assert payload["standingVolumeM3"] == 20
    assert payload["biomassTons"] == 4
    assert payload["surveyedAreaMu"] == 15
    assert payload["blockCount"] == 2
    assert payload["snapshotCount"] == 2


def test_normalize_scene_asset_record_repairs_legacy_dji_dsm():
    import server.app as app_module

    legacy = {
        "id": "legacy-dsm",
        "assetType": "orthophoto",
        "fileName": "dsm.tif",
        "originalPath": "inbox/flight/geotiff/dsm.tif",
    }

    normalized = app_module.normalize_scene_asset_record(legacy)

    assert normalized["assetType"] == "dsm"
    assert legacy["assetType"] == "orthophoto"


def test_confirm_coverage_allows_independent_facility_point(app_client):
    import server.app as app_module

    scene = {
        "id": "scene-independent-facility",
        "name": "大横厂房可见光",
        "assetType": "orthophoto",
        "processingStage": "coverage-review",
        "linkedBlockCodes": [],
        "bounds": [117.10, 27.20, 117.12, 27.22],
        "coverageAnalysis": {"requiresConfirmation": True, "matches": [], "suggestedBlockCodes": []},
        "allowedRoles": [],
        "allowedUsers": [],
    }
    app_module.save_scene(scene)

    confirmed = app_client.post(
        "/api/scenes/scene-independent-facility/coverage/confirm",
        headers={"X-RS-Roles": "admin", "X-RS-User": "reviewer"},
        json={
            "blockCodes": [],
            "relationType": "independent-point",
            "pointName": "大横竹材加工厂",
            "pointCategory": "竹材加工厂",
        },
    )

    assert confirmed.status_code == 200
    payload = confirmed.json()
    assert payload["processingStage"] == "ready"
    assert payload["linkedBlockCodes"] == []
    assert payload["coverageAnalysis"]["requiresConfirmation"] is False
    assert payload["spatialRelation"] == {
        "type": "independent-point",
        "pointName": "大横竹材加工厂",
        "pointCategory": "竹材加工厂",
        "longitude": pytest.approx(117.11),
        "latitude": pytest.approx(27.21),
    }


def test_trajectory_sidecar_creates_one_partial_historical_drone_mission(monkeypatch):
    import server.app as app_module

    created_records = []
    monkeypatch.setattr(app_module, "list_missions", lambda **_kwargs: [])
    monkeypatch.setattr(
        app_module,
        "block_by_code",
        lambda code: {"id": f"id-{code}", "blockCode": code},
    )
    monkeypatch.setattr(
        app_module,
        "create_mission",
        lambda record, timeline: created_records.append({**record, "timeline": [timeline]}) or created_records[-1],
    )
    scene = {
        "id": "scene-trajectory-1",
        "name": "邵武S9地块pnts",
        "missionId": "DJI-S9-20260827",
        "assetType": "pointcloud",
        "processingStage": "ready",
        "linkedBlockCodes": ["GJ9-001"],
        "trajectoryAvailable": True,
        "trajectoryPath": "inbox/S9/terra_trajectory",
        "trajectoryFileCount": 3,
        "trajectorySize": 1_024,
        "trajectoryFormats": ["POS", "SBET", "SMRMSG"],
        "trajectoryFiles": ["inbox/S9/terra_trajectory/POS_demo.csv"],
    }

    result = app_module.sync_scene_trajectory_mission(scene, "reviewer")

    assert result["status"] == "created"
    assert len(created_records) == 1
    record = created_records[0]
    assert record["missionNo"].startswith("WRJ-IMP-")
    assert record["status"] == "completed"
    assert record["droneDeviceId"] == ""
    assert record["plannedStartAt"] is None
    assert record["actualStartAt"] is None
    assert record["blocks"] == [{"id": "id-GJ9-001", "code": "GJ9-001"}]
    assert record["flightSummary"]["recordOrigin"] == "trajectory-auto-import"
    assert "droneDevice" in record["flightSummary"]["missingFields"]


def test_pos_trajectory_is_parsed_and_downsampled_for_map_overlay(tmp_path):
    import server.app as app_module

    path = tmp_path / "POS_DJI_demo.csv"
    path.write_text(
        "# time,longitude,latitude,height\n"
        "1,117.1000,27.2000,801\n"
        "2,117.1010,27.2010,803\n"
        "3,117.1020,27.2020,805\n",
        encoding="utf-8",
    )

    points = app_module.parse_text_trajectory(path, "EPSG:4326")

    assert points == [
        [117.1, 27.2, 801.0],
        [117.101, 27.201, 803.0],
        [117.102, 27.202, 805.0],
    ]
    assert app_module.downsample_trajectory(points, 2) == [points[0], points[-1]]
    assert app_module.trajectory_distance_km(points) > 0


def test_large_pos_text_trajectory_uses_bounded_even_sampling(tmp_path):
    import server.app as app_module

    path = tmp_path / "POS_DJI_large.csv"
    rows = ["# time,x,y,z"] + [f"{index},117.{index:04d},27.{index:04d},{800 + index}" for index in range(1, 501)]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    points = app_module.parse_text_trajectory(path, "EPSG:4326", limit=20)

    assert len(points) <= 23
    assert points[0] == pytest.approx([117.0001, 27.0001, 801])
    assert points[-1] == pytest.approx([117.05, 27.05, 1300])


def test_sbet_trajectory_reads_standard_seventeen_double_records(tmp_path):
    import struct
    import server.app as app_module

    path = tmp_path / "demo_sbet.out"
    records = []
    for index in range(2):
        values = [0.0] * 17
        values[0] = index
        values[1] = app_module.math.radians(27.2 + index * 0.001)
        values[2] = app_module.math.radians(117.1 + index * 0.001)
        values[3] = 800 + index
        records.append(struct.pack("<17d", *values))
    path.write_bytes(b"".join(records))

    points = app_module.parse_sbet_trajectory(path)

    assert len(points) == 2
    assert points[0] == pytest.approx([117.1, 27.2, 800])


def test_large_sbet_trajectory_is_sampled_without_losing_endpoints(tmp_path):
    import struct
    import server.app as app_module

    path = tmp_path / "large_sbet.out"
    records = []
    for index in range(100):
        values = [0.0] * 17
        values[1] = app_module.math.radians(27.2 + index * 0.00001)
        values[2] = app_module.math.radians(117.1 + index * 0.00001)
        values[3] = 800 + index
        records.append(struct.pack("<17d", *values))
    path.write_bytes(b"".join(records))

    points = app_module.parse_sbet_trajectory(path, limit=10)

    assert len(points) <= 11
    assert points[0] == pytest.approx([117.1, 27.2, 800])
    assert points[-1] == pytest.approx([117.10099, 27.20099, 899])


def test_dji_sbet_text_trajectory_converts_radians_to_degrees(tmp_path):
    import server.app as app_module

    path = tmp_path / "DJI_demo_sbet.txt"
    path.write_text(
        " %      Time       Latitude      Longitude     Altitude\n"
        " %     (SOW)      (radians)      (radians)     (meters)\n"
        f"442633.90 {app_module.math.radians(27.2)} {app_module.math.radians(117.1)} 981.02 0 0 0\n"
        f"442633.91 {app_module.math.radians(27.201)} {app_module.math.radians(117.101)} 982.02 0 0 0\n",
        encoding="utf-8",
    )

    points = app_module.parse_sbet_text_trajectory(path)

    assert len(points) == 2
    assert points[0] == pytest.approx([117.1, 27.2, 981.02])


def test_scene_trajectory_geojson_contains_path_endpoints_and_statistics(tmp_path, monkeypatch):
    import server.app as app_module

    path = tmp_path / "POS_DJI_demo.csv"
    path.write_text("x,y,z\n117.1,27.2,800\n117.11,27.21,805\n", encoding="utf-8")
    monkeypatch.setattr(app_module, "resolve_catalog_path", lambda _value: path)
    monkeypatch.setattr(
        app_module,
        "scene_trajectory_evidence",
        lambda _scene: {"available": True, "fileCount": 1, "formats": ["POS"], "files": ["trajectory/POS_DJI_demo.csv"]},
    )

    payload = app_module.scene_trajectory_geojson({"crs": "EPSG:4326"})

    assert payload["type"] == "FeatureCollection"
    assert [feature["id"] for feature in payload["features"]] == ["flight-path-1", "flight-start", "flight-end"]
    assert payload["meta"]["available"] is True
    assert payload["meta"]["sourceFormat"] == "POS"
    assert payload["meta"]["sourcePointCount"] == 2
    assert payload["meta"]["distanceKm"] > 0


def test_scene_trajectory_endpoint_returns_renderable_geojson(app_client, monkeypatch):
    import server.app as app_module

    monkeypatch.setattr(
        app_module,
        "find_allowed_scene",
        lambda scene_id, _request: {"id": scene_id, "assetType": "pointcloud"},
    )
    monkeypatch.setattr(
        app_module,
        "scene_trajectory_geojson",
        lambda _scene: {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "id": "flight-path-1", "properties": {"kind": "path"}, "geometry": {"type": "LineString", "coordinates": [[117.1, 27.2, 800], [117.2, 27.3, 810]]}}],
            "meta": {"available": True, "sourceFormat": "POS", "sourcePointCount": 2, "returnedPointCount": 2, "segmentCount": 1, "distanceKm": 1.2, "fileCount": 1, "formats": ["POS"]},
        },
    )

    response = app_client.get("/api/scenes/scene-trajectory/trajectory.geojson")

    assert response.status_code == 200
    assert response.json()["features"][0]["id"] == "flight-path-1"


def test_trajectory_sidecar_deduplicates_pnts_and_copc_scene_records(monkeypatch):
    import server.app as app_module

    trajectory = {
        "available": True,
        "path": "inbox/S9/terra_trajectory",
        "fileCount": 1,
        "totalSize": 100,
        "formats": ["POS"],
        "files": ["inbox/S9/terra_trajectory/POS_demo.csv"],
    }
    source_key = app_module.trajectory_mission_source_key(trajectory)
    existing = {
        "id": "mission-imported",
        "missionNo": "WRJ-IMP-EXISTING",
        "status": "completed",
        "blocks": [{"id": "id-GJ9-001", "code": "GJ9-001"}],
        "flightSummary": {
            "recordOrigin": "trajectory-auto-import",
            "trajectorySourceKey": source_key,
            "sourceSceneIds": ["scene-pnts"],
        },
    }
    updates = []
    monkeypatch.setattr(app_module, "scene_trajectory_evidence", lambda _scene: trajectory)
    monkeypatch.setattr(app_module, "list_missions", lambda **_kwargs: [existing])
    monkeypatch.setattr(app_module, "block_by_code", lambda code: {"id": f"id-{code}", "blockCode": code})
    monkeypatch.setattr(
        app_module,
        "update_mission",
        lambda record, timeline: updates.append({**record, "timeline": [timeline]}) or updates[-1],
    )

    result = app_module.sync_scene_trajectory_mission(
        {
            "id": "scene-copc",
            "name": "同航次COPC",
            "linkedBlockCodes": ["GJ9-001", "GJ9-002"],
        },
        "reviewer",
    )

    assert result == {"status": "updated", "missionId": "mission-imported", "missionNo": "WRJ-IMP-EXISTING"}
    assert len(updates) == 1
    assert updates[0]["flightSummary"]["sourceSceneIds"] == ["scene-pnts", "scene-copc"]
    assert {item["code"] for item in updates[0]["blocks"]} == {"GJ9-001", "GJ9-002"}
