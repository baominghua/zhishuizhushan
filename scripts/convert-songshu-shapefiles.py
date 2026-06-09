import json
import math
import os
import shutil
import struct
import sys
import zipfile
from pathlib import Path


SOURCE_ZIP = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"D:\Users\MECHREUO\Desktop\松树小班.zip")
WORK_DIR = Path("analysis-data/songshu-source")
OUT_DIR = Path("converted-data/songshu-small-classes")

LAYERS = {
    "国外松种": "国外松",
    "湿地松小班": "湿地松",
    "马尾松小班": "马尾松",
}

# CGCS2000 / Gauss-Kruger 3-degree zone 37, central meridian 111E.
A = 6378137.0
F = 1 / 298.257222101
E2 = 2 * F - F * F
EP2 = E2 / (1 - E2)
LON0 = math.radians(111.0)
FALSE_EASTING = 37500000.0


def inverse_gauss_kruger(x, y):
    easting = x - FALSE_EASTING
    meridian_arc = y
    mu = meridian_arc / (A * (1 - E2 / 4 - 3 * E2 * E2 / 64 - 5 * E2**3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    footprint = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )

    sin_fp = math.sin(footprint)
    cos_fp = math.cos(footprint)
    tan_fp = math.tan(footprint)
    c1 = EP2 * cos_fp * cos_fp
    t1 = tan_fp * tan_fp
    n1 = A / math.sqrt(1 - E2 * sin_fp * sin_fp)
    r1 = A * (1 - E2) / ((1 - E2 * sin_fp * sin_fp) ** 1.5)
    d = easting / n1

    lat = footprint - (n1 * tan_fp / r1) * (
        d * d / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * EP2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * EP2 - 3 * c1 * c1) * d**6 / 720
    )
    lon = LON0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * EP2 + 24 * t1 * t1) * d**5 / 120
    ) / cos_fp

    return [round(math.degrees(lon), 7), round(math.degrees(lat), 7)]


def read_dbf(path):
    data = path.read_bytes()
    record_count = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    record_length = struct.unpack("<H", data[10:12])[0]

    fields = []
    offset = 1
    pos = 32
    while pos < header_length - 1:
        descriptor = data[pos : pos + 32]
        if descriptor[0] == 0x0D:
            break
        name = descriptor[0:11].split(b"\x00", 1)[0].decode("utf-8", "replace")
        field_type = chr(descriptor[11])
        field_length = descriptor[16]
        fields.append((name, field_type, offset, field_length))
        offset += field_length
        pos += 32

    records = []
    for index in range(record_count):
        raw = data[header_length + index * record_length : header_length + (index + 1) * record_length]
        if not raw or raw[0:1] == b"*":
            records.append({})
            continue
        record = {}
        for name, field_type, offset, field_length in fields:
            text = raw[offset : offset + field_length].decode("utf-8", "replace").strip()
            if field_type in ("N", "F") and text:
                try:
                    record[name] = float(text) if "." in text else int(text)
                except ValueError:
                    record[name] = text
            else:
                record[name] = text
        records.append(record)
    return records


def signed_area(ring):
    area = 0.0
    for index, point in enumerate(ring):
        next_point = ring[(index + 1) % len(ring)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return area / 2


def parse_polygon_shape(content):
    shape_type = struct.unpack("<i", content[0:4])[0]
    if shape_type == 0:
        return None
    if shape_type != 5:
        raise ValueError(f"Unsupported shape type: {shape_type}")

    num_parts, num_points = struct.unpack("<2i", content[36:44])
    parts_offset = 44
    points_offset = parts_offset + num_parts * 4
    part_starts = list(struct.unpack(f"<{num_parts}i", content[parts_offset:points_offset]))
    part_starts.append(num_points)

    raw_points = [
        struct.unpack("<2d", content[points_offset + index * 16 : points_offset + (index + 1) * 16])
        for index in range(num_points)
    ]

    rings = []
    for index in range(num_parts):
        start = part_starts[index]
        end = part_starts[index + 1]
        ring = [inverse_gauss_kruger(x, y) for x, y in raw_points[start:end]]
        if len(ring) >= 4:
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            rings.append(ring)

    if not rings:
        return None

    polygons = []
    current = None
    for ring in rings:
        # ESRI shapefiles usually store outer rings clockwise and holes counter-clockwise.
        if signed_area(ring) < 0 or current is None:
            current = [ring]
            polygons.append(current)
        else:
            current.append(ring)

    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def read_shp(path):
    data = path.read_bytes()
    offset = 100
    geometries = []
    while offset + 8 <= len(data):
        _, content_words = struct.unpack(">2i", data[offset : offset + 8])
        content_length = content_words * 2
        content = data[offset + 8 : offset + 8 + content_length]
        geometries.append(parse_polygon_shape(content))
        offset += 8 + content_length
    return geometries


def convert_layer(source_dir, layer_name, species_name):
    shp_path = source_dir / f"{layer_name}.shp"
    dbf_path = source_dir / f"{layer_name}.dbf"
    records = read_dbf(dbf_path)
    geometries = read_shp(shp_path)

    features = []
    for index, geometry in enumerate(geometries):
        if not geometry:
            continue
        properties = records[index] if index < len(records) else {}
        properties = {
            **properties,
            "layerName": layer_name,
            "speciesName": species_name,
        }
        features.append({"type": "Feature", "properties": properties, "geometry": geometry})

    collection = {
        "type": "FeatureCollection",
        "name": layer_name,
        "source": str(SOURCE_ZIP),
        "crs_note": "Converted from CGCS2000 3-degree Gauss-Kruger zone 37 to lon/lat.",
        "features": features,
    }
    output = OUT_DIR / f"{layer_name}.geojson"
    output.write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return output, len(features)


def main():
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    WORK_DIR.mkdir(parents=True)
    OUT_DIR.mkdir(parents=True)

    with zipfile.ZipFile(SOURCE_ZIP) as archive:
        archive.extractall(WORK_DIR)

    nested_dirs = [item for item in WORK_DIR.iterdir() if item.is_dir()]
    source_dir = nested_dirs[0] if nested_dirs else WORK_DIR

    summary = []
    for layer_name, species_name in LAYERS.items():
        output, feature_count = convert_layer(source_dir, layer_name, species_name)
        summary.append(
            {
                "layerName": layer_name,
                "speciesName": species_name,
                "features": feature_count,
                "file": output.name,
                "bytes": output.stat().st_size,
            }
        )

    merged_features = []
    for item in summary:
        data = json.loads((OUT_DIR / item["file"]).read_text(encoding="utf-8"))
        merged_features.extend(data["features"])
    merged = {
        "type": "FeatureCollection",
        "name": "松树小班",
        "source": str(SOURCE_ZIP),
        "crs_note": "Converted from CGCS2000 3-degree Gauss-Kruger zone 37 to lon/lat.",
        "features": merged_features,
    }
    merged_output = OUT_DIR / "松树小班-合并.geojson"
    merged_output.write_text(json.dumps(merged, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    summary.append(
        {
            "layerName": "松树小班-合并",
            "speciesName": "全部",
            "features": len(merged_features),
            "file": merged_output.name,
            "bytes": merged_output.stat().st_size,
        }
    )

    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in summary:
        print(f"{item['file']}: {item['features']} features, {item['bytes'] / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
