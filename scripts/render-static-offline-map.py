import html
import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "zhushan-offline-static.html"
WIDTH = 1600
HEIGHT = 960
BBOX = [117.55, 26.05, 118.85, 27.2]


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_js_json(path, variable_name):
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"window\.{re.escape(variable_name)}\s*=\s*(.*)\s*;?\s*$", text, re.S)
    if not match:
        raise ValueError(f"{path} does not define window.{variable_name}")
    payload = match.group(1).strip()
    if payload.endswith(";"):
        payload = payload[:-1]
    return json.loads(payload)


def iter_coords(geometry):
    yield from iter_coord_tree(geometry.get("coordinates") or [])


def iter_coord_tree(value):
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from iter_coord_tree(item)


def data_bbox(collections):
    coords = []
    for collection in collections:
        for feature in collection.get("features", []):
            coords.extend(iter_coords(feature.get("geometry") or {}))
    lon_values = [coord[0] for coord in coords if isinstance(coord, list) and len(coord) >= 2]
    lat_values = [coord[1] for coord in coords if isinstance(coord, list) and len(coord) >= 2]
    if not lon_values or not lat_values:
        return BBOX
    min_lon, max_lon = min(lon_values), max(lon_values)
    min_lat, max_lat = min(lat_values), max(lat_values)
    lon_pad = max((max_lon - min_lon) * 0.08, 0.02)
    lat_pad = max((max_lat - min_lat) * 0.08, 0.02)
    return [min_lon - lon_pad, min_lat - lat_pad, max_lon + lon_pad, max_lat + lat_pad]


def project(coord):
    lon, lat = coord
    x = (lon - BBOX[0]) / (BBOX[2] - BBOX[0]) * WIDTH
    y = (BBOX[3] - lat) / (BBOX[3] - BBOX[1]) * HEIGHT
    return x, y


def path_for_line(coords):
    if not coords:
        return ""
    points = [project(coord) for coord in coords]
    first = points[0]
    rest = points[1:]
    d = [f"M{first[0]:.1f},{first[1]:.1f}"]
    d.extend(f"L{x:.1f},{y:.1f}" for x, y in rest)
    return " ".join(d)


def path_for_polygon(rings):
    if rings and rings[0] and isinstance(rings[0][0], (int, float)):
        rings = [rings]
    parts = []
    for ring in rings:
        d = path_for_line(ring)
        if d:
            parts.append(f"{d} Z")
    return " ".join(parts)


def feature_path(feature):
    geom = feature.get("geometry") or {}
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "LineString":
        return path_for_line(coords)
    if gtype == "Polygon":
        return path_for_polygon(coords)
    if gtype == "MultiPolygon":
        return " ".join(path_for_polygon(poly) for poly in coords)
    return ""


def point_for_feature(feature):
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if geom.get("type") == "Point":
        return project(coords)
    ring = first_ring(coords)
    if ring:
        xs, ys = zip(*(project(coord) for coord in ring))
        return sum(xs) / len(xs), sum(ys) / len(ys)
    if geom.get("type") == "LineString" and coords:
        return project(coords[len(coords) // 2])
    return WIDTH / 2, HEIGHT / 2


def first_ring(coords):
    current = coords
    while current:
        if isinstance(current[0], (int, float)):
            return None
        if len(current[0]) >= 2 and isinstance(current[0][0], (int, float)) and isinstance(current[0][1], (int, float)):
            return current
        current = current[0]
    return None


def class_for_base(feature):
    kind = feature.get("properties", {}).get("kind", "other")
    return {
        "forest": "base-forest",
        "landuse": "base-landuse",
        "water": "base-water",
        "waterway": "base-waterway",
        "railway": "base-railway",
        "building": "base-building",
        "road": "base-road",
    }.get(kind, "base-other")


def cjk_tokens(text):
    text = str(text).lower()
    pieces = [part for part in re.split(r"[\s/,\-|·]+", text) if len(part) >= 2]
    for group in re.findall(r"[\u3400-\u9fff]{2,}", text):
        pieces.append(group)
        pieces.extend(group[i : i + 2] for i in range(len(group) - 1))
    stop = {"竹山", "边界", "图层", "资料", "已叠加", "小班"}
    return sorted({piece for piece in pieces if piece not in stop})


def score(values, tokens):
    haystack = " ".join(str(value) for value in values if value is not None).lower()
    return sum(1 for token in tokens if token in haystack)


def safe_text(value):
    return html.escape(str(value or ""), quote=True)


def render_base(base):
    chunks = []
    for feature in base["features"]:
        d = feature_path(feature)
        if d:
            chunks.append(f'<path class="{class_for_base(feature)}" d="{d}"/>')
    return "\n".join(chunks)


def render_named_polygons(features, class_name, source):
    chunks = []
    records = []
    for index, feature in enumerate(features):
        d = feature_path(feature)
        if not d:
            continue
        props = feature.get("properties") or {}
        if source == "huangkeng":
            title = props.get("挂接") or props.get("不不不") or props.get("XBNO") or f"黄坑图斑-{index + 1}"
            location = f"{props.get('镇') or props.get('XZCNAME') or ''}{props.get('村') or props.get('CGQNAME') or ''}"
            code = props.get("XBNO") or "-".join(str(props.get(key) or "") for key in ("林班", "大班", "小班")).strip("-")
            status = f"面积{props.get('面积')}亩" if props.get("面积") else "已叠加"
            label = f"{location}\n{code}"
        else:
            title = props.get("名称") or props.get("name") or f"康内部分村-{index + 1}"
            location = "麻沙镇溪头村"
            code = props.get("日期") or ""
            status = props.get("面积") or "已叠加"
            label = title
        x, y = point_for_feature(feature)
        feature_id = f"{source}-{index}"
        chunks.append(f'<path id="{feature_id}" class="{class_name}" d="{d}"/>')
        chunks.append(
            f'<text class="map-label {source}-label" x="{x:.1f}" y="{y:.1f}">'
            f"{safe_text(label)}</text>"
        )
        records.append(
            {
                "id": feature_id,
                "title": title,
                "location": location,
                "layer": "KMZ边界 / 竹林林班" if source == "huangkeng" else "OVKML边界 / 康内部分村",
                "status": status,
                "source": source,
                "keywords": " ".join(str(v) for v in props.values()),
            }
        )
    return "\n".join(chunks), records


def main():
    global BBOX
    base = load_json(ROOT / "offline-maps" / "fujian-basemap.geojson")
    huangkeng = load_js_json(ROOT / "assets" / "huang-keng-bamboo-geojson.js", "HUANGKENG_BAMBOO_GEOJSON")
    kang = load_js_json(ROOT / "assets" / "kang-village-geojson.js", "KANG_VILLAGE_GEOJSON")
    BBOX = data_bbox([base, huangkeng, kang])

    base_svg = render_base(base)
    huangkeng_svg, huangkeng_records = render_named_polygons(huangkeng["features"], "hk-polygon", "huangkeng")
    kang_svg, kang_records = render_named_polygons(kang["features"], "kang-polygon", "kang")
    records = huangkeng_records + kang_records

    records_json = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>智慧竹山离线静态地图</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #061a16;
      color: #efffff;
      font-family: "Microsoft YaHei", Arial, sans-serif;
      overflow: hidden;
    }}
    .app {{ position: fixed; inset: 0; background: #06221b; }}
    .map-wrap {{ position: absolute; inset: 0; overflow: hidden; }}
    svg {{ width: 100%; height: 100%; display: block; background: #0f2f25; cursor: grab; }}
    svg.dragging {{ cursor: grabbing; }}
    .base-forest {{ fill: rgba(40, 120, 68, .34); stroke: rgba(63, 148, 84, .18); stroke-width: 1; }}
    .base-landuse {{ fill: rgba(63, 110, 70, .18); stroke: rgba(86, 142, 96, .13); stroke-width: 1; }}
    .base-water {{ fill: rgba(48, 126, 156, .42); stroke: rgba(94, 200, 238, .5); stroke-width: 1.4; }}
    .base-waterway {{ fill: none; stroke: rgba(68, 172, 218, .72); stroke-width: 2.1; }}
    .base-road {{ fill: none; stroke: rgba(218, 222, 200, .48); stroke-width: 1.4; stroke-linecap: round; }}
    .base-railway {{ fill: none; stroke: rgba(232, 232, 220, .34); stroke-width: 1.2; stroke-dasharray: 8 6; }}
    .base-building {{ fill: rgba(184, 205, 188, .18); stroke: rgba(230, 255, 244, .18); stroke-width: 1; }}
    .base-other {{ fill: none; stroke: rgba(160, 190, 170, .2); stroke-width: 1; }}
    .hk-polygon {{ fill: rgba(148, 214, 74, .28); stroke: #17220f; stroke-width: 6; paint-order: stroke fill; }}
    .kang-polygon {{ fill: rgba(86, 208, 242, .22); stroke: #0c2630; stroke-width: 6; paint-order: stroke fill; }}
    .map-label {{
      fill: #f7fff5;
      stroke: rgba(0, 0, 0, .9);
      stroke-width: 4px;
      paint-order: stroke fill;
      font-size: 13px;
      font-weight: 700;
      text-anchor: middle;
      white-space: pre;
      pointer-events: none;
    }}
    .kang-label {{ fill: #d8fbff; }}
    .selected {{ filter: drop-shadow(0 0 10px #fff65e); stroke: #fff65e !important; stroke-width: 9 !important; }}
    .title {{
      position: absolute; top: 22px; left: 50%; transform: translateX(-50%);
      min-width: 420px; text-align: center; padding: 14px 42px;
      border: 1px solid rgba(111, 253, 245, .62);
      background: linear-gradient(90deg, rgba(17, 94, 86, .7), rgba(24, 132, 123, .72));
      box-shadow: 0 0 34px rgba(111, 253, 245, .16);
      font-size: 34px; font-weight: 900;
      z-index: 3;
    }}
    .panel {{
      position: absolute; left: 26px; top: 92px; width: 380px; max-height: calc(100vh - 130px);
      border: 1px solid rgba(111, 253, 245, .5);
      background: rgba(18, 95, 86, .86);
      box-shadow: 0 16px 60px rgba(0, 0, 0, .36);
      z-index: 4; display: flex; flex-direction: column;
    }}
    .panel header {{ padding: 18px 20px 8px; font-size: 22px; font-weight: 900; }}
    .panel .search {{ display: grid; gap: 8px; padding: 10px 16px 14px; }}
    .panel input {{
      width: 100%; border: 1px solid rgba(111, 253, 245, .4); outline: none;
      background: rgba(0, 22, 24, .82); color: #efffff; font-size: 18px; padding: 12px 14px;
    }}
    .meta {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding: 0 16px 12px; }}
    .meta article {{ border: 1px solid rgba(220,255,253,.25); padding: 10px; text-align: center; }}
    .meta span {{ display: block; font-size: 12px; opacity: .8; }}
    .meta b {{ font-size: 20px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
    thead {{ position: sticky; top: 0; background: rgba(16, 83, 76, .96); }}
    th, td {{ border: 1px solid rgba(220,255,253,.22); padding: 9px 8px; text-align: center; }}
    tbody tr {{ cursor: pointer; }}
    tbody tr:hover {{ background: rgba(111, 253, 245, .16); }}
    .table-wrap {{ overflow: auto; padding: 0 16px 16px; }}
    .controls {{
      position: absolute; right: 24px; bottom: 28px; display: grid; gap: 8px; z-index: 4;
    }}
    .controls button {{
      border: 1px solid rgba(111, 253, 245, .45); background: rgba(18, 95, 86, .92);
      color: #efffff; width: 46px; height: 42px; font-size: 22px; font-weight: 800;
    }}
  </style>
</head>
<body>
  <main class="app">
    <div class="map-wrap">
      <svg id="mapSvg" viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg">
        <g id="viewport">
          <rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="#103025"/>
          <g id="base">{base_svg}</g>
          <g id="huangkeng">{huangkeng_svg}</g>
          <g id="kang">{kang_svg}</g>
        </g>
      </svg>
    </div>
    <div class="title">智慧竹山离线静态地图</div>
    <section class="panel">
      <header>竹山图斑搜索</header>
      <div class="meta">
        <article><span>黄坑 KMZ</span><b>{len(huangkeng_records)}</b></article>
        <article><span>康内部分村</span><b>{len(kang_records)}</b></article>
        <article><span>离线底图要素</span><b>{len(base["features"])}</b></article>
      </div>
      <label class="search">
        <input id="searchInput" type="search" value="黄坑" placeholder="输入黄坑、麻沙、新峰村、编号..." />
      </label>
      <div class="table-wrap">
        <table>
          <thead><tr><th>检索对象</th><th>位置</th><th>图层</th><th>状态</th></tr></thead>
          <tbody id="resultRows"></tbody>
        </table>
      </div>
    </section>
    <div class="controls">
      <button id="zoomIn">+</button>
      <button id="zoomOut">-</button>
      <button id="reset">⌂</button>
    </div>
  </main>
  <script>
    const records = {records_json};
    const svg = document.querySelector("#mapSvg");
    const viewport = document.querySelector("#viewport");
    const rows = document.querySelector("#resultRows");
    const searchInput = document.querySelector("#searchInput");
    let viewBox = [0, 0, {WIDTH}, {HEIGHT}];
    let selected = null;

    function setViewBox(next) {{
      viewBox = next;
      svg.setAttribute("viewBox", viewBox.join(" "));
    }}
    function tokens(text) {{
      const value = String(text || "").toLowerCase();
      const out = value.split(/[\\s/,\\-|·]+/).filter((part) => part.length >= 2);
      const groups = value.match(/[\\u3400-\\u9fff]{{2,}}/g) || [];
      groups.forEach((group) => {{
        out.push(group);
        for (let i = 0; i < group.length - 1; i += 1) out.push(group.slice(i, i + 2));
      }});
      return [...new Set(out)].filter((part) => !["竹山", "边界", "图层", "资料", "已叠加"].includes(part));
    }}
    function score(record, queryTokens) {{
      const text = `${{record.title}} ${{record.location}} ${{record.layer}} ${{record.status}} ${{record.keywords}}`.toLowerCase();
      return queryTokens.reduce((total, token) => total + (text.includes(token) ? 1 : 0), 0);
    }}
    function render() {{
      const q = tokens(searchInput.value);
      const matches = (q.length ? records.map((record) => [record, score(record, q)]).filter(([, s]) => s > 0).sort((a, b) => b[1] - a[1]).map(([record]) => record) : records).slice(0, 80);
      rows.innerHTML = matches.length ? matches.map((record) => `
        <tr data-id="${{record.id}}">
          <td>${{record.title}}</td><td>${{record.location}}</td><td>${{record.layer}}</td><td>${{record.status}}</td>
        </tr>`).join("") : `<tr><td colspan="4">未检索到匹配图斑</td></tr>`;
    }}
    function focusRecord(id) {{
      const el = document.getElementById(id);
      if (!el) return;
      selected?.classList.remove("selected");
      selected = el;
      selected.classList.add("selected");
      const box = el.getBBox();
      const pad = Math.max(box.width, box.height, 90) * 1.8;
      setViewBox([box.x - pad, box.y - pad, box.width + pad * 2, box.height + pad * 2]);
    }}
    rows.addEventListener("click", (event) => {{
      const tr = event.target.closest("tr[data-id]");
      if (tr) focusRecord(tr.dataset.id);
    }});
    searchInput.addEventListener("input", render);
    document.querySelector("#zoomIn").addEventListener("click", () => {{
      const [x, y, w, h] = viewBox;
      setViewBox([x + w * .125, y + h * .125, w * .75, h * .75]);
    }});
    document.querySelector("#zoomOut").addEventListener("click", () => {{
      const [x, y, w, h] = viewBox;
      setViewBox([x - w * .166, y - h * .166, w * 1.332, h * 1.332]);
    }});
    document.querySelector("#reset").addEventListener("click", () => setViewBox([0, 0, {WIDTH}, {HEIGHT}]));

    let dragging = false;
    let start = null;
    svg.addEventListener("pointerdown", (event) => {{
      dragging = true;
      start = [event.clientX, event.clientY, ...viewBox];
      svg.classList.add("dragging");
      svg.setPointerCapture(event.pointerId);
    }});
    svg.addEventListener("pointermove", (event) => {{
      if (!dragging) return;
      const dx = (event.clientX - start[0]) / svg.clientWidth * start[4];
      const dy = (event.clientY - start[1]) / svg.clientHeight * start[5];
      setViewBox([start[2] - dx, start[3] - dy, start[4], start[5]]);
    }});
    svg.addEventListener("pointerup", () => {{
      dragging = false;
      svg.classList.remove("dragging");
    }});
    render();
  </script>
</body>
</html>
"""
    OUTPUT.write_text(html_text, encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    print(f"{OUTPUT.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"Embedded features: base={len(base['features'])}, huangkeng={len(huangkeng_records)}, kang={len(kang_records)}")


if __name__ == "__main__":
    main()
