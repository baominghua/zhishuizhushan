from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from server.modules.database import init_platform_schema, use_postgis as smart_bamboo_use_postgis
from server.modules.forest_blocks import router as forest_blocks_router
from server.modules.forest_scene_links import router as forest_scene_links_router
from server.modules.imports import router as imports_router
from server.modules.settings import get_settings


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data" / "remote-sensing"
UPLOAD_DIR = DATA_DIR / "uploads"
COG_DIR = DATA_DIR / "cogs"
CATALOG_PATH = DATA_DIR / "catalog.json"
SUPPORTED_RASTER_EXTENSIONS = {".tif", ".tiff", ".geotiff"}


app = FastAPI(
    title="Remote Sensing COG Tile Service",
    version="0.2.0",
    description="GDAL + COG + TiTiler-compatible raster service for the satellite imagery manager.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_platform_schema()
app.include_router(forest_blocks_router)
app.include_router(forest_scene_links_router)
app.include_router(imports_router)


def ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    COG_DIR.mkdir(parents=True, exist_ok=True)
    if not CATALOG_PATH.exists():
      CATALOG_PATH.write_text(json.dumps({"scenes": []}, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "-", value.strip(), flags=re.UNICODE)
    return value.strip("-") or "scene"


def load_catalog() -> list[dict[str, Any]]:
    ensure_dirs()
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {"scenes": []}
    return list(data.get("scenes", []))


def save_catalog(scenes: list[dict[str, Any]]) -> None:
    ensure_dirs()
    scenes = sorted(scenes, key=lambda item: str(item.get("createdAt", "")), reverse=True)
    CATALOG_PATH.write_text(json.dumps({"scenes": scenes}, ensure_ascii=False, indent=2), encoding="utf-8")


def dependency_status(module_name: str) -> dict[str, str]:
    try:
        module = __import__(module_name)
        version = getattr(module, "__version__", "installed")
        return {"status": "ok", "version": str(version)}
    except Exception as exc:
        return {"status": "missing", "error": str(exc)}


def require_rasterio():
    try:
        import rasterio

        return rasterio
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"rasterio/GDAL is not available. Install server/requirements.txt first. {exc}",
        ) from exc


def require_rio_tiler():
    try:
        from rio_tiler.io import COGReader

        return COGReader
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"rio-tiler is not available. Install server/requirements.txt first. {exc}",
        ) from exc


def parse_bounds(bounds: str | None) -> list[float] | None:
    if not bounds:
        return None
    values = [item for item in re.split(r"[,\s]+", bounds) if item]
    if len(values) != 4:
        return None
    try:
        west, south, east, north = [float(item) for item in values]
    except ValueError:
        return None
    if west >= east or south >= north:
        return None
    return [west, south, east, north]


def convert_to_cog(source_path: Path, cog_path: Path) -> None:
    rasterio = require_rasterio()
    from rasterio.shutil import copy as rio_copy

    cog_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.Env(GDAL_NUM_THREADS="ALL_CPUS", GDAL_TIFF_INTERNAL_MASK=True):
        rio_copy(
            str(source_path),
            str(cog_path),
            driver="COG",
            compress="DEFLATE",
            blocksize=512,
            overview_resampling="nearest",
            BIGTIFF="IF_SAFER",
            num_threads="ALL_CPUS",
        )


def raster_metadata(cog_path: Path, fallback_bounds: list[float] | None = None) -> dict[str, Any]:
    rasterio = require_rasterio()
    from rasterio.warp import transform_bounds

    with rasterio.open(cog_path) as dataset:
        if dataset.crs:
            west, south, east, north = transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds, densify_pts=21)
            bounds = [west, south, east, north]
            crs = dataset.crs.to_string()
        else:
            bounds = fallback_bounds or [117.55, 26.05, 118.85, 27.2]
            crs = ""

        xres, yres = dataset.res
        return {
            "bounds": [round(float(item), 8) for item in bounds],
            "crs": crs,
            "width": dataset.width,
            "height": dataset.height,
            "bands": dataset.count,
            "dtype": dataset.dtypes[0] if dataset.dtypes else "",
            "resolution": f"{abs(xres):.6g} x {abs(yres):.6g}",
        }


def public_scene(scene: dict[str, Any], request: Request) -> dict[str, Any]:
    base_url = str(request.base_url).rstrip("/")
    scene_id = scene["id"]
    tile_url = f"{base_url}/api/scenes/{scene_id}/tiles/{{z}}/{{x}}/{{y}}.png"
    return {
        **scene,
        "tileUrl": tile_url,
        "tileJsonUrl": f"{base_url}/api/scenes/{scene_id}/tilejson.json",
        "metadataUrl": f"{base_url}/api/scenes/{scene_id}",
    }


def find_scene(scene_id: str) -> dict[str, Any]:
    for scene in load_catalog():
        if scene.get("id") == scene_id:
            return scene
    raise HTTPException(status_code=404, detail="Scene not found")


def mount_optional_titiler() -> bool:
    try:
        from titiler.core.factory import TilerFactory

        cog = TilerFactory()
        app.include_router(cog.router, prefix="/titiler", tags=["TiTiler"])
        return True
    except Exception as exc:
        app.state.titiler_error = str(exc)
        return False


TITILER_MOUNTED = mount_optional_titiler()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "remote-sensing-cog",
        "titilerMounted": TITILER_MOUNTED,
        "titilerError": getattr(app.state, "titiler_error", ""),
        "dependencies": {
            "rasterio": dependency_status("rasterio"),
            "rio_tiler": dependency_status("rio_tiler"),
            "titiler": dependency_status("titiler"),
        },
        "deployment": {
            "smartBamboo": {
                "storageBackend": get_settings().storage_backend,
                "postgisEnabled": smart_bamboo_use_postgis(),
                "schemaReady": True,
            }
        },
    }


@app.get("/api/scenes")
def list_scenes(request: Request) -> dict[str, Any]:
    return {"scenes": [public_scene(scene, request) for scene in load_catalog()]}


@app.get("/api/scenes/{scene_id}")
def get_scene(scene_id: str, request: Request) -> dict[str, Any]:
    return public_scene(find_scene(scene_id), request)


@app.post("/api/scenes/upload")
async def upload_scene(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(""),
    satellite: str = Form(""),
    sensor: str = Form(""),
    capturedAt: str = Form(""),
    resolution: str = Form(""),
    bounds: str = Form(""),
) -> dict[str, Any]:
    ensure_dirs()
    extension = Path(file.filename or "").suffix.lower()
    if extension not in SUPPORTED_RASTER_EXTENSIONS:
        raise HTTPException(status_code=400, detail="COG 服务仅接收 GeoTIFF/TIFF。PNG/JPG/WebP 请用前端本地直显。")

    scene_id = f"cog-{uuid.uuid4().hex[:12]}"
    safe_name = slugify(Path(file.filename or scene_id).stem)
    source_path = UPLOAD_DIR / f"{scene_id}-{safe_name}{extension}"
    cog_path = COG_DIR / f"{scene_id}-{safe_name}.tif"

    with source_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    fallback_bounds = parse_bounds(bounds)
    try:
        convert_to_cog(source_path, cog_path)
        metadata = raster_metadata(cog_path, fallback_bounds)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"GDAL COG conversion failed: {exc}") from exc

    scene = {
        "id": scene_id,
        "source": "server",
        "storage": "COG",
        "name": name.strip() or Path(file.filename or scene_id).stem,
        "fileName": file.filename,
        "fileType": "image/tiff",
        "size": cog_path.stat().st_size,
        "originalSize": source_path.stat().st_size,
        "satellite": satellite.strip(),
        "sensor": sensor.strip(),
        "capturedAt": capturedAt.strip(),
        "resolution": resolution.strip() or metadata["resolution"],
        "bounds": metadata["bounds"],
        "crs": metadata["crs"],
        "width": metadata["width"],
        "height": metadata["height"],
        "bands": metadata["bands"],
        "dtype": metadata["dtype"],
        "cogPath": str(cog_path.relative_to(DATA_DIR)).replace("\\", "/"),
        "originalPath": str(source_path.relative_to(DATA_DIR)).replace("\\", "/"),
        "opacity": 0.9,
        "visible": True,
        "transferStatus": "cog-ready",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }

    scenes = [item for item in load_catalog() if item.get("id") != scene_id]
    scenes.insert(0, scene)
    save_catalog(scenes)
    return public_scene(scene, request)


@app.get("/api/scenes/{scene_id}/tilejson.json")
def tilejson(scene_id: str, request: Request) -> dict[str, Any]:
    scene = public_scene(find_scene(scene_id), request)
    return {
        "tilejson": "3.0.0",
        "name": scene["name"],
        "bounds": scene["bounds"],
        "minzoom": 0,
        "maxzoom": 22,
        "tiles": [scene["tileUrl"]],
    }


@app.get("/api/scenes/{scene_id}/tiles/{z}/{x}/{y}.png")
def tile(
    scene_id: str,
    z: int,
    x: int,
    y: int,
    bidx: list[int] | None = Query(default=None),
) -> Response:
    scene = find_scene(scene_id)
    cog_path = DATA_DIR / str(scene["cogPath"])
    if not cog_path.exists():
        raise HTTPException(status_code=404, detail="COG file not found")

    COGReader = require_rio_tiler()
    try:
        with COGReader(str(cog_path)) as cog:
            image = cog.tile(x, y, z, indexes=bidx)
            content = image.render(img_format="PNG")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Tile render failed: {exc}") from exc

    return Response(content=content, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.delete("/api/scenes/{scene_id}")
def delete_scene(scene_id: str) -> dict[str, Any]:
    scenes = load_catalog()
    target = None
    remaining = []
    for scene in scenes:
        if scene.get("id") == scene_id:
            target = scene
        else:
            remaining.append(scene)
    if not target:
        raise HTTPException(status_code=404, detail="Scene not found")

    for key in ["cogPath", "originalPath"]:
        value = target.get(key)
        if not value:
            continue
        path = DATA_DIR / str(value)
        if path.exists() and path.resolve().is_relative_to(DATA_DIR.resolve()):
            path.unlink()

    save_catalog(remaining)
    return {"ok": True, "deleted": scene_id}


app.mount("/", StaticFiles(directory=ROOT_DIR, html=True), name="static")
