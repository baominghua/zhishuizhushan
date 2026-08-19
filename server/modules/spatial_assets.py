from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any, Iterable

from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union


COVERAGE_ALGORITHM_VERSION = "effective-footprint-v1"
SUPPORTED_POINT_CLOUD_EXTENSIONS = {".las", ".laz"}


def _crs_label(crs: Any, wkt: str = "") -> str:
    epsg = crs.to_epsg() if crs is not None else None
    if epsg:
        return f"EPSG:{epsg}"
    authorities = re.findall(r'AUTHORITY\[\s*"EPSG"\s*,\s*"(\d+)"\s*\]', wkt, flags=re.IGNORECASE)
    if authorities:
        return f"EPSG:{authorities[-1]}"
    return crs.to_string() if crs is not None else ""


def _run_converter(command: list[str], label: str) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = str(exc.stderr or exc.stdout or "").strip()
        if len(detail) > 2000:
            detail = detail[-2000:]
        raise RuntimeError(f"{label} 转换失败{f'：{detail}' if detail else ''}") from exc


def _require_rasterio():
    try:
        import rasterio

        return rasterio
    except Exception as exc:  # pragma: no cover - deployment dependency guard
        raise RuntimeError(f"Raster spatial analysis requires rasterio: {exc}") from exc


def _valid_geometry(value: dict[str, Any] | None):
    if not value:
        return None
    try:
        geometry = shape(value)
    except Exception:
        return None
    if geometry.is_empty:
        return None
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    return None if geometry.is_empty else geometry


def _transform_geometry(value: dict[str, Any], source_crs: Any, target_crs: Any) -> dict[str, Any]:
    rasterio = _require_rasterio()
    from rasterio.warp import transform_geom

    return transform_geom(source_crs, target_crs, value, precision=8)


def effective_raster_footprint(path: Path, *, max_dimension: int = 2048) -> dict[str, Any]:
    """Extract a down-sampled valid-pixel footprint without loading the full raster into memory."""
    rasterio = _require_rasterio()
    from affine import Affine
    from rasterio.enums import Resampling
    from rasterio.features import shapes

    with rasterio.open(path) as dataset:
        if not dataset.crs:
            raise ValueError("GeoTIFF 缺少坐标系，无法自动匹配林班。")
        scale = max(1.0, max(dataset.width, dataset.height) / max(64, int(max_dimension)))
        out_width = max(1, round(dataset.width / scale))
        out_height = max(1, round(dataset.height / scale))
        mask = dataset.dataset_mask(
            out_shape=(out_height, out_width),
            resampling=Resampling.nearest,
        )
        sampled_transform = dataset.transform * Affine.scale(
            dataset.width / out_width,
            dataset.height / out_height,
        )
        polygons = [
            shape(geometry)
            for geometry, value in shapes(mask, mask=mask > 0, transform=sampled_transform)
            if int(value) > 0
        ]
        if polygons:
            native = unary_union(polygons)
        else:
            native = box(*dataset.bounds)
        if not native.is_valid:
            native = native.buffer(0)
        tolerance = max(abs(sampled_transform.a), abs(sampled_transform.e)) * 0.75
        if tolerance > 0:
            native = native.simplify(tolerance, preserve_topology=True)
        footprint_wgs84 = _transform_geometry(mapping(native), dataset.crs, "EPSG:4326")
        bounds_wgs84 = list(_valid_geometry(footprint_wgs84).bounds)
        return {
            "geometry": footprint_wgs84,
            "bounds": [round(float(item), 8) for item in bounds_wgs84],
            "sourceCrs": dataset.crs.to_string(),
            "sampleWidth": out_width,
            "sampleHeight": out_height,
            "algorithmVersion": COVERAGE_ALGORITHM_VERSION,
        }


def coverage_analysis(
    footprint_wgs84: dict[str, Any],
    blocks: Iterable[dict[str, Any]],
    *,
    minimum_suggested_area_m2: float = 100.0,
) -> dict[str, Any]:
    footprint = _valid_geometry(footprint_wgs84)
    if footprint is None:
        raise ValueError("成果缺少有效空间覆盖范围。")
    footprint_equal_area = _valid_geometry(
        _transform_geometry(mapping(footprint), "EPSG:4326", "EPSG:6933")
    )
    if footprint_equal_area is None or footprint_equal_area.area <= 0:
        raise ValueError("成果空间覆盖范围无效。")

    matches: list[dict[str, Any]] = []
    for block in blocks:
        block_geometry = _valid_geometry(block.get("geometry"))
        if block_geometry is None or not footprint.intersects(block_geometry):
            continue
        block_equal_area = _valid_geometry(
            _transform_geometry(mapping(block_geometry), "EPSG:4326", "EPSG:6933")
        )
        if block_equal_area is None or block_equal_area.area <= 0:
            continue
        intersection = footprint_equal_area.intersection(block_equal_area)
        area_m2 = float(intersection.area)
        if area_m2 <= 0:
            continue
        block_percent = min(100.0, area_m2 / float(block_equal_area.area) * 100)
        imagery_percent = min(100.0, area_m2 / float(footprint_equal_area.area) * 100)
        suggested = area_m2 >= minimum_suggested_area_m2 or block_percent >= 0.5 or imagery_percent >= 0.5
        matches.append(
            {
                "blockId": str(block.get("id") or ""),
                "blockCode": str(block.get("blockCode") or ""),
                "blockName": str(block.get("name") or block.get("blockCode") or ""),
                "location": " / ".join(
                    str(block.get(field) or "").strip()
                    for field in ("countyName", "townName", "villageName")
                    if str(block.get(field) or "").strip()
                ),
                "blockAreaMu": block.get("areaMu"),
                "intersectionAreaHa": round(area_m2 / 10_000, 4),
                "blockCoveragePercent": round(block_percent, 2),
                "imageryCoveragePercent": round(imagery_percent, 2),
                "suggested": suggested,
            }
        )
    matches.sort(
        key=lambda item: (
            -float(item["intersectionAreaHa"]),
            str(item["blockCode"]),
        )
    )
    return {
        "algorithmVersion": COVERAGE_ALGORITHM_VERSION,
        "footprint": mapping(footprint),
        "footprintBounds": [round(float(item), 8) for item in footprint.bounds],
        "effectiveAreaHa": round(float(footprint_equal_area.area) / 10_000, 4),
        "matches": matches,
        "suggestedBlockCodes": [item["blockCode"] for item in matches if item["suggested"]],
        "requiresConfirmation": True,
    }


def _decode_las_text(value: bytes) -> str:
    return value.split(b"\0", 1)[0].decode("utf-8", "replace").strip()


def read_las_header(path: Path) -> dict[str, Any]:
    """Read LAS/LAZ public header and WKT VLR without loading point records."""
    with path.open("rb") as source:
        header = source.read(375)
        if len(header) < 227 or header[:4] != b"LASF":
            raise ValueError(f"{path.name} 不是有效的 LAS/LAZ 文件。")
        version = f"{header[24]}.{header[25]}"
        header_size = struct.unpack_from("<H", header, 94)[0]
        variable_length_records = struct.unpack_from("<I", header, 100)[0]
        point_format = int(header[104] & 0x3F)
        legacy_point_count = struct.unpack_from("<I", header, 107)[0]
        extended_point_count = (
            struct.unpack_from("<Q", header, 247)[0]
            if version == "1.4" and len(header) >= 255
            else 0
        )
        max_x, min_x, max_y, min_y, max_z, min_z = struct.unpack_from("<dddddd", header, 179)
        wkt = ""
        source.seek(header_size)
        for _ in range(variable_length_records):
            record_header = source.read(54)
            if len(record_header) != 54:
                break
            user_id = _decode_las_text(record_header[2:18])
            record_id = struct.unpack_from("<H", record_header, 18)[0]
            record_length = struct.unpack_from("<H", record_header, 20)[0]
            record = source.read(record_length)
            if user_id == "LASF_Projection" and record_id in {2111, 2112}:
                wkt = _decode_las_text(record)
    crs = None
    if wkt:
        rasterio = _require_rasterio()
        try:
            crs = rasterio.crs.CRS.from_wkt(wkt)
        except Exception:
            crs = None
    return {
        "fileName": path.name,
        "size": path.stat().st_size,
        "version": version,
        "pointFormat": point_format,
        "pointCount": int(extended_point_count or legacy_point_count),
        "nativeBounds": [float(min_x), float(min_y), float(min_z), float(max_x), float(max_y), float(max_z)],
        "crs": crs,
        "crsWkt": wkt,
    }


def point_cloud_collection_metadata(paths: Iterable[Path]) -> dict[str, Any]:
    items = [read_las_header(path) for path in paths]
    if not items:
        raise ValueError("没有找到 LAS/LAZ 点云文件。")
    first_crs = items[0]["crs"]
    if first_crs is None:
        raise ValueError(f"{items[0]['fileName']} 缺少可识别的坐标系。")
    for item in items[1:]:
        if item["crs"] is None:
            raise ValueError(f"{item['fileName']} 缺少可识别的坐标系。")
        if item["crs"] != first_crs:
            raise ValueError("同一批点云包含不同坐标系，必须先统一坐标系。")
    native_min_x = min(item["nativeBounds"][0] for item in items)
    native_min_y = min(item["nativeBounds"][1] for item in items)
    native_min_z = min(item["nativeBounds"][2] for item in items)
    native_max_x = max(item["nativeBounds"][3] for item in items)
    native_max_y = max(item["nativeBounds"][4] for item in items)
    native_max_z = max(item["nativeBounds"][5] for item in items)

    footprints = []
    for item in items:
        min_x, min_y, _min_z, max_x, max_y, _max_z = item["nativeBounds"]
        footprints.append(
            _valid_geometry(
                _transform_geometry(mapping(box(min_x, min_y, max_x, max_y)), first_crs, "EPSG:4326")
            )
        )
    footprint = unary_union([item for item in footprints if item is not None])
    return {
        "fileCount": len(items),
        "totalSize": sum(int(item["size"]) for item in items),
        "pointCount": sum(int(item["pointCount"]) for item in items),
        "versions": sorted({str(item["version"]) for item in items}),
        "pointFormats": sorted({int(item["pointFormat"]) for item in items}),
        "crs": _crs_label(first_crs, str(items[0].get("crsWkt") or "")),
        "nativeBounds": [native_min_x, native_min_y, native_min_z, native_max_x, native_max_y, native_max_z],
        "bounds": [round(float(item), 8) for item in footprint.bounds],
        "footprint": mapping(footprint),
        "files": [
            {key: value for key, value in item.items() if key not in {"crs", "crsWkt"}}
            for item in items
        ],
    }


def convert_point_cloud_to_copc(
    source_paths: list[Path],
    output_path: Path,
    *,
    pdal_executable: str = "pdal",
) -> None:
    executable = shutil.which(pdal_executable)
    if not executable:
        raise RuntimeError("服务器未安装 PDAL，无法生成 COPC。")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    readers = [
        {"type": "readers.las", "filename": str(path), "tag": f"source{index}"}
        for index, path in enumerate(source_paths)
    ]
    pipeline: list[dict[str, Any]] = list(readers)
    writer_inputs = [item["tag"] for item in readers]
    if len(readers) > 1:
        pipeline.append({"type": "filters.merge", "tag": "merged", "inputs": writer_inputs})
        writer_inputs = ["merged"]
    pipeline.append(
        {
            "type": "writers.copc",
            "filename": str(output_path),
            "inputs": writer_inputs,
            "forward": "all",
        }
    )
    pipeline_path = output_path.with_suffix(".pipeline.json")
    pipeline_path.write_text(json.dumps({"pipeline": pipeline}, ensure_ascii=False, indent=2), encoding="utf-8")
    _run_converter([executable, "pipeline", str(pipeline_path)], "PDAL COPC")


def convert_point_cloud_to_3dtiles(
    source_paths: list[Path],
    output_dir: Path,
    *,
    py3dtiles_executable: str = "py3dtiles",
) -> None:
    executable = shutil.which(py3dtiles_executable)
    if not executable:
        raise RuntimeError("服务器未安装 py3dtiles，无法生成 3D Tiles。")
    # py3dtiles creates the destination itself and rejects a pre-existing
    # directory unless --overwrite is explicitly requested.
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    _run_converter(
        [
            executable,
            "convert",
            "--srs_out",
            "4978",
            "--pyproj-always-xy",
            "--out",
            str(output_dir),
            *[str(path) for path in source_paths],
        ],
        "py3dtiles",
    )
    if not (output_dir / "tileset.json").is_file():
        raise RuntimeError("3D Tiles 转换结束但未生成 tileset.json。")
