from __future__ import annotations

import json
import math
import re
import shutil
import struct
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any, Iterable

from shapely.geometry import MultiPoint, box, mapping, shape
from shapely.ops import unary_union


COVERAGE_ALGORITHM_VERSION = "effective-footprint-v1"
SUPPORTED_POINT_CLOUD_EXTENSIONS = {".las", ".laz"}
SUPPORTED_3D_TILE_EXTENSIONS = {".b3dm", ".cmpt", ".glb", ".gltf", ".i3dm", ".pnts"}
MAX_TILESET_JSON_BYTES = 16 * 1024 * 1024
MAX_TILESET_JSON_FILES = 5_000
MAX_TILESET_CONTENT_FILES = 100_000


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
        scale_x, scale_y, scale_z = struct.unpack_from("<ddd", header, 131)
        offset_x, offset_y, offset_z = struct.unpack_from("<ddd", header, 155)
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
    dimensions = [
        "X", "Y", "Z", "Intensity", "ReturnNumber", "NumberOfReturns",
        "Classification", "ScanAngle", "UserData", "PointSourceId",
    ]
    if point_format in {1, 3, 4, 5, 6, 7, 8, 9, 10}:
        dimensions.append("GpsTime")
    if point_format in {2, 3, 5, 7, 8, 10}:
        dimensions.extend(["Red", "Green", "Blue"])
    if point_format in {8, 10}:
        dimensions.append("Infrared")
    if point_format in {4, 5, 9, 10}:
        dimensions.extend(["WavePacketDescriptorIndex", "WaveformDataOffset"])
    return {
        "fileName": path.name,
        "size": path.stat().st_size,
        "version": version,
        "pointFormat": point_format,
        "dimensions": dimensions,
        "pointCount": int(extended_point_count or legacy_point_count),
        "scale": [float(scale_x), float(scale_y), float(scale_z)],
        "offset": [float(offset_x), float(offset_y), float(offset_z)],
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
    dimensions = sorted({dimension for item in items for dimension in item.get("dimensions", [])})
    return {
        "fileCount": len(items),
        "totalSize": sum(int(item["size"]) for item in items),
        "pointCount": sum(int(item["pointCount"]) for item in items),
        "versions": sorted({str(item["version"]) for item in items}),
        "pointFormats": sorted({int(item["pointFormat"]) for item in items}),
        "dimensions": dimensions,
        "attributeModes": [
            mode
            for mode, required in (
                ("rgb", {"Red", "Green", "Blue"}),
                ("elevation", {"Z"}),
                ("return", {"ReturnNumber", "NumberOfReturns"}),
                ("intensity", {"Intensity"}),
                ("gps-time", {"GpsTime"}),
            )
            if required.issubset(dimensions)
        ],
        "crs": _crs_label(first_crs, str(items[0].get("crsWkt") or "")),
        "nativeBounds": [native_min_x, native_min_y, native_min_z, native_max_x, native_max_y, native_max_z],
        "bounds": [round(float(item), 8) for item in footprint.bounds],
        "footprint": mapping(footprint),
        "files": [
            {key: value for key, value in item.items() if key not in {"crs", "crsWkt"}}
            for item in items
        ],
    }


def _tileset_document(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_TILESET_JSON_BYTES:
        raise ValueError(f"3D Tiles JSON 文件过大：{path.name}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 3D Tiles JSON：{path.name}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("root"), dict):
        raise ValueError(f"3D Tiles JSON 缺少 root：{path.name}")
    asset = document.get("asset")
    version = str(asset.get("version") or "") if isinstance(asset, dict) else ""
    if version not in {"0.0", "1.0", "1.1"}:
        raise ValueError(f"不支持的 3D Tiles asset.version：{version or 'missing'}")
    return document


def normalized_tileset_document(path: Path, *, service_token: str = "") -> dict[str, Any]:
    """Return a web-compatible document without mutating DJI Terra output."""
    document = _tileset_document(path)
    asset = dict(document.get("asset") or {})
    if str(asset.get("version") or "") == "0.0":
        asset["version"] = "1.0"
        document = {**document, "asset": asset}
    if service_token:
        pending = [document["root"]]
        while pending:
            tile = pending.pop()
            children = tile.get("children")
            if isinstance(children, list):
                pending.extend(item for item in children if isinstance(item, dict))
            contents = []
            if isinstance(tile.get("content"), dict):
                contents.append(tile["content"])
            if isinstance(tile.get("contents"), list):
                contents.extend(item for item in tile["contents"] if isinstance(item, dict))
            for content in contents:
                key = "uri" if isinstance(content.get("uri"), str) else "url"
                uri = content.get(key)
                if not isinstance(uri, str) or not uri.strip():
                    continue
                parsed = urllib.parse.urlsplit(uri)
                if parsed.scheme or parsed.netloc:
                    continue
                query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
                query["token"] = service_token
                content[key] = urllib.parse.urlunsplit(
                    (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment)
                )
    return document


def _tileset_content_uris(root: dict[str, Any]) -> Iterable[str]:
    pending = [root]
    while pending:
        tile = pending.pop()
        children = tile.get("children")
        if isinstance(children, list):
            pending.extend(item for item in children if isinstance(item, dict))
        content_items: list[Any] = []
        if isinstance(tile.get("content"), dict):
            content_items.append(tile["content"])
        if isinstance(tile.get("contents"), list):
            content_items.extend(item for item in tile["contents"] if isinstance(item, dict))
        for content in content_items:
            uri = content.get("uri") or content.get("url")
            if isinstance(uri, str) and uri.strip():
                yield uri.strip()


def _safe_tileset_target(uri: str, document_path: Path, tiles_root: Path) -> Path:
    parsed = urllib.parse.urlsplit(uri)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"3D Tiles 不允许引用远程资源：{uri}")
    decoded = urllib.parse.unquote(parsed.path).replace("\\", "/")
    if not decoded or decoded.startswith("/") or re.match(r"^[a-zA-Z]:", decoded):
        raise ValueError(f"3D Tiles 包含无效资源路径：{uri}")
    target = (document_path.parent / decoded).resolve()
    try:
        target.relative_to(tiles_root)
    except ValueError as exc:
        raise ValueError(f"3D Tiles 资源越出登记目录：{uri}") from exc
    if not target.is_file():
        raise ValueError(f"3D Tiles 引用文件不存在：{uri}")
    return target


def _tile_header(path: Path) -> dict[str, int | str]:
    suffix = path.suffix.lower()
    if suffix not in {".b3dm", ".cmpt", ".i3dm", ".pnts"}:
        return {"pointCount": 0}
    minimum_header_size = {".b3dm": 28, ".cmpt": 16, ".i3dm": 32, ".pnts": 28}[suffix]
    with path.open("rb") as source:
        header = source.read(minimum_header_size)
        if len(header) < minimum_header_size:
            raise ValueError(f"3D Tiles 瓦片头不完整：{path.name}")
        magic = header[:4].decode("ascii", "replace")
        version, declared_length = struct.unpack_from("<II", header, 4)
        if magic != suffix[1:] or version != 1 or declared_length != path.stat().st_size:
            raise ValueError(f"3D Tiles 瓦片头无效：{path.name}")
        if suffix == ".cmpt" and struct.unpack_from("<I", header, 12)[0] < 1:
            raise ValueError(f"3D Tiles 复合瓦片没有子瓦片：{path.name}")
        if suffix == ".i3dm" and struct.unpack_from("<I", header, 28)[0] not in {0, 1}:
            raise ValueError(f"3D Tiles I3DM glTF 格式标记无效：{path.name}")
        point_count = 0
        if suffix == ".pnts":
            feature_json_length = struct.unpack_from("<I", header, 12)[0]
            if 0 < feature_json_length <= 1024 * 1024:
                feature_json = source.read(feature_json_length).rstrip(b" \t\r\n\0")
                try:
                    feature_table = json.loads(feature_json.decode("utf-8"))
                    point_count = max(0, int(feature_table.get("POINTS_LENGTH") or 0))
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                    point_count = 0
    return {"magic": magic, "version": version, "pointCount": point_count}


def _apply_tileset_transform(point: tuple[float, float, float], transform: list[Any] | None) -> tuple[float, float, float]:
    if not transform:
        return point
    if len(transform) != 16:
        raise ValueError("3D Tiles root.transform 必须包含16个数值。")
    values = [float(item) for item in transform]
    if not all(math.isfinite(item) for item in values):
        raise ValueError("3D Tiles root.transform 包含无效数值。")
    x, y, z = point
    w = values[3] * x + values[7] * y + values[11] * z + values[15]
    if abs(w) < 1e-12:
        raise ValueError("3D Tiles root.transform 产生无效齐次坐标。")
    return (
        (values[0] * x + values[4] * y + values[8] * z + values[12]) / w,
        (values[1] * x + values[5] * y + values[9] * z + values[13]) / w,
        (values[2] * x + values[6] * y + values[10] * z + values[14]) / w,
    )


def _ecef_footprint(points: list[tuple[float, float, float]]) -> dict[str, Any]:
    if not points:
        raise ValueError("3D Tiles 根包围体没有有效坐标。")
    rasterio = _require_rasterio()
    from rasterio.warp import transform

    longitudes, latitudes, _heights = transform(
        "EPSG:4978",
        "EPSG:4326",
        [item[0] for item in points],
        [item[1] for item in points],
        [item[2] for item in points],
    )
    footprint = MultiPoint([
        (float(longitude), float(latitude))
        for longitude, latitude in zip(longitudes, latitudes, strict=True)
    ]).convex_hull
    if footprint.is_empty or footprint.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("3D Tiles 根包围体无法生成有效地理覆盖范围。")
    return mapping(footprint)


def tileset_root_footprint(document: dict[str, Any]) -> dict[str, Any]:
    root = document.get("root") or {}
    volume = root.get("boundingVolume") or {}
    if not isinstance(volume, dict):
        raise ValueError("3D Tiles root 缺少 boundingVolume。")
    region = volume.get("region")
    if isinstance(region, list):
        if len(region) != 6:
            raise ValueError("3D Tiles boundingVolume.region 必须包含6个数值。")
        west, south, east, north = [math.degrees(float(item)) for item in region[:4]]
        if not all(math.isfinite(item) for item in (west, south, east, north)) or west >= east or south >= north:
            raise ValueError("3D Tiles boundingVolume.region 无效。")
        geometry = mapping(box(west, south, east, north))
        return {"geometry": geometry, "bounds": [west, south, east, north], "sourceCrs": "EPSG:4326"}

    transform = root.get("transform") if isinstance(root.get("transform"), list) else None
    points: list[tuple[float, float, float]] = []
    native_bounds: list[float] = []
    volume_box = volume.get("box")
    if isinstance(volume_box, list):
        if len(volume_box) != 12:
            raise ValueError("3D Tiles boundingVolume.box 必须包含12个数值。")
        values = [float(item) for item in volume_box]
        if not all(math.isfinite(item) for item in values):
            raise ValueError("3D Tiles boundingVolume.box 包含无效数值。")
        center = values[:3]
        axes = (values[3:6], values[6:9], values[9:12])
        for first in (-1, 1):
            for second in (-1, 1):
                for third in (-1, 1):
                    point = tuple(
                        center[index]
                        + first * axes[0][index]
                        + second * axes[1][index]
                        + third * axes[2][index]
                        for index in range(3)
                    )
                    points.append(_apply_tileset_transform(point, transform))
        native_bounds = [
            min(point[index] for point in points) for index in range(3)
        ] + [
            max(point[index] for point in points) for index in range(3)
        ]
    else:
        sphere = volume.get("sphere")
        if not isinstance(sphere, list) or len(sphere) != 4:
            raise ValueError("3D Tiles 仅支持 region、box 或 sphere 根包围体。")
        center = [float(item) for item in sphere[:3]]
        radius = float(sphere[3])
        if not all(math.isfinite(item) for item in [*center, radius]) or radius <= 0:
            raise ValueError("3D Tiles boundingVolume.sphere 无效。")
        for axis in range(3):
            for direction in (-1, 1):
                point = list(center)
                point[axis] += radius * direction
                points.append(_apply_tileset_transform(tuple(point), transform))
        native_bounds = [
            min(point[index] for point in points) for index in range(3)
        ] + [
            max(point[index] for point in points) for index in range(3)
        ]

    geometry = _ecef_footprint(points)
    footprint = _valid_geometry(geometry)
    if footprint is None:
        raise ValueError("3D Tiles 根包围体无法生成有效覆盖范围。")
    return {
        "geometry": mapping(footprint),
        "bounds": [round(float(item), 8) for item in footprint.bounds],
        "sourceCrs": "EPSG:4978",
        "nativeBounds": [round(float(item), 3) for item in native_bounds],
    }


def inspect_3d_tileset(root_path: Path) -> dict[str, Any]:
    root_path = root_path.resolve()
    tiles_root = root_path.parent.resolve()
    root_document = _tileset_document(root_path)
    pending = [root_path]
    seen_documents: set[Path] = set()
    referenced_files: set[Path] = set()
    formats: dict[str, int] = {}
    asset_versions: set[str] = set()
    point_count = 0

    while pending:
        document_path = pending.pop().resolve()
        if document_path in seen_documents:
            continue
        if len(seen_documents) >= MAX_TILESET_JSON_FILES:
            raise ValueError(f"3D Tiles JSON 数量超过上限 {MAX_TILESET_JSON_FILES}。")
        document = _tileset_document(document_path)
        seen_documents.add(document_path)
        asset_versions.add(str((document.get("asset") or {}).get("version") or ""))
        for uri in _tileset_content_uris(document["root"]):
            target = _safe_tileset_target(uri, document_path, tiles_root)
            suffix = target.suffix.lower()
            if suffix == ".json":
                pending.append(target)
                continue
            if len(referenced_files) >= MAX_TILESET_CONTENT_FILES and target not in referenced_files:
                raise ValueError(f"3D Tiles 内容文件数量超过上限 {MAX_TILESET_CONTENT_FILES}。")
            if target in referenced_files:
                continue
            header = _tile_header(target)
            referenced_files.add(target)
            key = suffix[1:] if suffix else "other"
            formats[key] = formats.get(key, 0) + 1
            point_count += int(header.get("pointCount") or 0)

    supported_files = [path for path in referenced_files if path.suffix.lower() in SUPPORTED_3D_TILE_EXTENSIONS]
    if not supported_files:
        raise ValueError("3D Tiles 没有引用可支持的 PNTS/B3DM/GLB 内容。")
    footprint = tileset_root_footprint(root_document)
    total_size = sum(path.stat().st_size for path in referenced_files | seen_documents)
    content_type = "mixed" if formats.get("pnts") and formats.get("b3dm") else (
        "pnts" if formats.get("pnts") else "b3dm" if formats.get("b3dm") else "3dtiles"
    )
    return {
        "rootPath": str(root_path),
        "tilesetCount": len(seen_documents),
        "contentFileCount": len(referenced_files),
        "tileCount": len(supported_files),
        "totalSize": total_size,
        "pointCount": point_count,
        "formats": dict(sorted(formats.items())),
        "contentType": content_type,
        "assetVersions": sorted(asset_versions),
        "normalizesDjiVersion": "0.0" in asset_versions,
        "bounds": footprint["bounds"],
        "footprint": footprint["geometry"],
        "crs": footprint["sourceCrs"],
        "nativeBounds": footprint.get("nativeBounds") or [],
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
    headers = [read_las_header(path) for path in source_paths]
    axis_options: dict[str, float] = {}
    axis_names = ("x", "y", "z")
    # LAS stores coordinates as signed int32 values plus scale/offset. DJI data
    # commonly uses large projected northings/eastings with a millimetre scale;
    # forwarding a zero offset can therefore overflow int32 during COPC output.
    # Recenter each axis while preserving the finest source precision that fits.
    max_encoded_coordinate = float((2**31) - 1024)
    for index, axis in enumerate(axis_names):
        minimum = min(float(header["nativeBounds"][index]) for header in headers)
        maximum = max(float(header["nativeBounds"][index + 3]) for header in headers)
        source_scales = [
            abs(float(header["scale"][index]))
            for header in headers
            if abs(float(header["scale"][index])) > 0
        ]
        source_scale = min(source_scales) if source_scales else 0.001
        required_scale = ((maximum - minimum) / 2) / max_encoded_coordinate
        axis_options[f"scale_{axis}"] = max(source_scale, required_scale, 1e-9)
        axis_options[f"offset_{axis}"] = minimum + ((maximum - minimum) / 2)
    pipeline.append(
        {
            "type": "writers.copc",
            "filename": str(output_path),
            "inputs": writer_inputs,
            "forward": "vlr",
            **axis_options,
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
            "--extra-fields",
            "intensity",
            "--extra-fields",
            "return_number",
            "--extra-fields",
            "number_of_returns",
            "--out",
            str(output_dir),
            *[str(path) for path in source_paths],
        ],
        "py3dtiles",
    )
    if not (output_dir / "tileset.json").is_file():
        raise RuntimeError("3D Tiles 转换结束但未生成 tileset.json。")
