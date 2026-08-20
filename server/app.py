from __future__ import annotations

import json
import csv
import hashlib
import io
import math
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from fastapi.routing import iter_route_contexts as fastapi_iter_route_contexts
except ImportError:
    fastapi_iter_route_contexts = None
from server.modules.admin_roles import (
    effective_data_scopes_for_context,
    json_download_response,
    require_permission as require_admin_permission,
    role_codes_for_context,
    safe_download_stem,
)
from server.modules.admin_roles import router as admin_roles_router
from server.modules.admin_roles import effective_permissions_for_context
from server.modules.admin_users import router as admin_users_router
from server.modules.admin_organizations import router as admin_organizations_router
from server.modules.basemap_settings import runtime_basemap_settings
from server.modules.auth import (
    AuthContext,
    bearer_token as unified_bearer_token,
    enforce_human_session_policy,
    effective_areas as platform_effective_areas,
    has_admin_role as platform_has_admin_role,
    has_effective_area_scope as platform_has_effective_area_scope,
    request_context as unified_request_context,
    role_data_scope_values as platform_role_data_scope_values,
    token_profiles,
)
from server.modules.auth_store import human_auth_storage_readiness
from server.modules.auth import router as auth_router
from server.modules.human_auth import router as human_auth_router
from server.modules.business import (
    MAP_LAYER_PERMISSIONS,
    append_map_layer_audit_event,
    dashboard_map_layers_payload,
    enrich_map_layer_record,
    layer_records,
    map_layer_changed_fields,
    normalize_record,
    save_layer_records,
)
from server.modules.business import router as business_router
from server.modules.database import (
    admin_roles_json_path,
    admin_users_json_path,
    forest_block_versions_json_path,
    forest_blocks_json_path,
    forest_right_versions_json_path,
    forest_rights_json_path,
    import_batches_json_path,
    init_platform_schema,
    load_json_records,
    map_layers_json_path,
    mysql_connection_kwargs,
    platform_storage_health,
    use_mysql as smart_bamboo_use_mysql,
    use_postgis as smart_bamboo_use_postgis,
)
from server.modules.dictionaries import ensure_system_dictionaries
from server.modules.dictionaries import router as dictionaries_router
from server.modules.mysql_schema import REMOTE_SENSING_MYSQL_TABLES, mysql_catalog_schema_statements
from server.modules.forest_blocks import (
    FOREST_BLOCK_IDENTITY_LOOKUP_BATCH_SIZE,
    FOREST_BLOCK_MYSQL_WRITE_BATCH_SIZE,
    ForestBlockFilters,
    block_by_code,
    filtered_forest_blocks,
    find_block,
    router as forest_blocks_router,
)
from server.modules.forest_rights import router as forest_rights_router
from server.modules.forest_scene_links import delete_scene_links_for_scene, replace_scene_links_for_scene
from server.modules.forest_scene_links import router as forest_scene_links_router
from server.modules.imports import (
    import_workflow_summary,
    list_import_delivery_packages,
    router as imports_router,
)
from server.modules.settings import enforce_production_configuration, get_settings
from server.modules.spatial_assets import (
    SUPPORTED_POINT_CLOUD_EXTENSIONS,
    convert_point_cloud_to_3dtiles,
    convert_point_cloud_to_copc,
    coverage_analysis,
    effective_raster_footprint,
    inspect_3d_tileset,
    normalized_tileset_document,
    point_cloud_collection_metadata,
)
from server.v2 import router as v2_router


ROOT_DIR = Path(__file__).resolve().parents[1]


def env_bool(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


DATA_DIR = Path(os.environ.get("REMOTE_SENSING_DATA_DIR", str(ROOT_DIR / "data" / "remote-sensing"))).expanduser().resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
COG_DIR = DATA_DIR / "cogs"
INBOX_DIR = DATA_DIR / "inbox"
POINT_CLOUD_DIR = DATA_DIR / "point-clouds"
POINT_CLOUD_UPLOAD_SESSION_DIR = DATA_DIR / "point-cloud-upload-sessions"
CATALOG_PATH = DATA_DIR / "catalog.json"
TASKS_PATH = DATA_DIR / "tasks.json"
CACHE_DIR = DATA_DIR / "tile-cache"
THUMBNAIL_DIR = DATA_DIR / "thumbnail-cache"
TIANDITU_CACHE_DIR = DATA_DIR / "basemap-cache" / "tianditu"
STATIC_DIR = Path(os.environ.get("REMOTE_SENSING_STATIC_DIR", str(ROOT_DIR))).expanduser().resolve()
V2_FRONTEND_DIR = Path(
    os.environ.get(
        "SMART_BAMBOO_V2_STATIC_DIR",
        str(ROOT_DIR / "dist" / "web-operations"),
    )
).expanduser().resolve()
MOBILE_FRONTEND_DIR = Path(
    os.environ.get(
        "SMART_BAMBOO_MOBILE_STATIC_DIR",
        str(ROOT_DIR / "dist" / "mobile-field"),
    )
).expanduser().resolve()
SERVE_STATIC = env_bool("REMOTE_SENSING_SERVE_STATIC", True)
CORS_ORIGINS = env_list("REMOTE_SENSING_CORS_ORIGINS", ["*"])
IMPORT_DIRS = [Path(item).expanduser().resolve() for item in env_list("REMOTE_SENSING_IMPORT_DIRS", [str(INBOX_DIR)])]
TASK_WORKERS = max(1, env_int("REMOTE_SENSING_TASK_WORKERS", 1))
CATALOG_BACKEND = os.environ.get("REMOTE_SENSING_CATALOG_BACKEND", "json").strip().lower()
DATABASE_URL = os.environ.get("REMOTE_SENSING_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
TILE_CACHE_ENABLED = env_bool("REMOTE_SENSING_TILE_CACHE", True)
TILE_CACHE_MAX_BYTES = max(0, env_int("REMOTE_SENSING_TILE_CACHE_MAX_BYTES", 0))
TILE_CACHE_MAX_AGE_DAYS = max(0.0, env_float("REMOTE_SENSING_TILE_CACHE_MAX_AGE_DAYS", 0))
CACHE_PRUNE_INTERVAL = max(5, env_int("REMOTE_SENSING_CACHE_PRUNE_INTERVAL", 60))
GEOSERVER_BASE_URL = os.environ.get("REMOTE_SENSING_GEOSERVER_URL", "").strip().rstrip("/")
GEOSERVER_WMS_URL = os.environ.get("REMOTE_SENSING_GEOSERVER_WMS_URL", "").strip()
GEOSERVER_WFS_URL = os.environ.get("REMOTE_SENSING_GEOSERVER_WFS_URL", "").strip()
GEOSERVER_LAYERS = env_list("REMOTE_SENSING_GEOSERVER_LAYERS", [])
TIANDITU_TK = os.environ.get("REMOTE_SENSING_TIANDITU_TK", "").strip()
TIANDITU_REFERER = os.environ.get("REMOTE_SENSING_TIANDITU_REFERER", "").strip()
TIANDITU_UPSTREAM_PROXY_BASE_URL = os.environ.get(
    "REMOTE_SENSING_TIANDITU_PROXY_BASE_URL",
    "",
).strip().rstrip("/")
TIANDITU_TIMEOUT = max(2, env_int("REMOTE_SENSING_TIANDITU_TIMEOUT", 8))
BASEMAP_CACHE_MAX_BYTES = max(0, env_int("REMOTE_SENSING_BASEMAP_CACHE_MAX_BYTES", 0))
BASEMAP_CACHE_MAX_AGE_DAYS = max(0.0, env_float("REMOTE_SENSING_BASEMAP_CACHE_MAX_AGE_DAYS", 0))
TIANDITU_LAYERS = {"img_w", "cia_w", "vec_w", "cva_w", "ter_w", "cta_w"}
TIANDITU_BROWSER_CACHE_CONTROL = "public, max-age=2592000, stale-while-revalidate=86400, immutable"
TIANDITU_PREWARM_BOUNDS = env_list("REMOTE_SENSING_TIANDITU_PREWARM_BOUNDS", [])
TIANDITU_PREWARM_LAYERS = env_list("REMOTE_SENSING_TIANDITU_PREWARM_LAYERS", ["img_w", "cia_w"])
TIANDITU_PREWARM_MIN_ZOOM = max(0, env_int("REMOTE_SENSING_TIANDITU_PREWARM_MIN_ZOOM", 8))
TIANDITU_PREWARM_MAX_ZOOM = min(18, env_int("REMOTE_SENSING_TIANDITU_PREWARM_MAX_ZOOM", 13))
TIANDITU_DETAIL_PREWARM_BOUNDS = env_list("REMOTE_SENSING_TIANDITU_DETAIL_PREWARM_BOUNDS", [])
TIANDITU_DETAIL_PREWARM_MIN_ZOOM = max(0, env_int("REMOTE_SENSING_TIANDITU_DETAIL_PREWARM_MIN_ZOOM", 14))
TIANDITU_DETAIL_PREWARM_MAX_ZOOM = min(18, env_int("REMOTE_SENSING_TIANDITU_DETAIL_PREWARM_MAX_ZOOM", 16))
TIANDITU_PREWARM_MAX_TILES = max(1, env_int("REMOTE_SENSING_TIANDITU_PREWARM_MAX_TILES", 10000))
SUPPORTED_RASTER_EXTENSIONS = {".tif", ".tiff", ".geotiff"}
POINT_CLOUD_CHUNK_SIZE = min(
    128 * 1024 * 1024,
    max(5 * 1024 * 1024, env_int("REMOTE_SENSING_POINT_CLOUD_CHUNK_SIZE", 16 * 1024 * 1024)),
)
POINT_CLOUD_PDAL_EXECUTABLE = os.environ.get("REMOTE_SENSING_PDAL_EXECUTABLE", "pdal").strip() or "pdal"
POINT_CLOUD_3DTILES_EXECUTABLE = (
    os.environ.get("REMOTE_SENSING_3DTILES_EXECUTABLE", "py3dtiles").strip() or "py3dtiles"
)
IMAGERY_SCENE_VIEW_PERMISSION = "imagery.scenes.view"
IMAGERY_MANAGE_PERMISSION = "imagery.scenes.manage"
IMAGERY_SCENE_CREATE_PERMISSION = "imagery.scenes.create"
IMAGERY_SCENE_UPDATE_PERMISSION = "imagery.scenes.update"
IMAGERY_SCENE_DELETE_PERMISSION = "imagery.scenes.delete"
IMAGERY_SCENE_RESTORE_PERMISSION = "imagery.scenes.restore"
IMAGERY_SCENE_ARCHIVE_PERMISSION = "imagery.scenes.archive"
IMAGERY_SCENE_QUALITY_PERMISSION = "imagery.scenes.quality"
IMAGERY_SCENE_DELIVERY_PERMISSION = "imagery.scenes.delivery"
IMAGERY_SCENE_EXPORT_PERMISSION = "imagery.scenes.export"
IMAGERY_TASK_RETRY_PERMISSION = "imagery.tasks.retry"
IMAGERY_TASK_CANCEL_PERMISSION = "imagery.tasks.cancel"
IMAGERY_TASK_ARCHIVE_PERMISSION = "imagery.tasks.archive"
IMAGERY_LAYER_PUBLISH_PERMISSION = "imagery.layers.publish"
IMAGERY_OPERATION_QUEUE_STAGES = [
    {
        "key": "failed_tasks",
        "label": "转换失败任务",
        "tone": "danger",
        "requiredPermission": IMAGERY_TASK_RETRY_PERMISSION,
        "href": "admin-imagery.html?taskStatus=failed",
        "primaryActionLabel": "重试任务",
    },
    {
        "key": "quality_issues",
        "label": "影像质检问题",
        "tone": "danger",
        "requiredPermission": IMAGERY_SCENE_QUALITY_PERMISSION,
        "href": "admin-imagery.html?imageryIssueStatus=open",
        "primaryActionLabel": "处理问题",
    },
    {
        "key": "awaiting_publish",
        "label": "待发布图层",
        "tone": "warning",
        "requiredPermission": IMAGERY_LAYER_PUBLISH_PERMISSION,
        "allPermissions": "map.layers.publish",
        "anyPermissions": "map.layers.create map.layers.update",
        "href": "admin-imagery.html?published=false",
        "primaryActionLabel": "发布图层",
    },
    {
        "key": "awaiting_delivery",
        "label": "待交付确认",
        "tone": "review",
        "requiredPermission": IMAGERY_SCENE_DELIVERY_PERMISSION,
        "href": "admin-imagery.html?sceneDeliveryStatus=pending",
        "primaryActionLabel": "确认交付",
    },
    {
        "key": "ready",
        "label": "已闭环影像",
        "tone": "ready",
        "requiredPermission": IMAGERY_SCENE_EXPORT_PERMISSION,
        "href": "admin-imagery.html?sceneDeliveryStatus=delivered",
        "primaryActionLabel": "导出回执",
    },
]
QUALITY_ISSUE_STATUSES = {"open", "investigating", "resolved", "ignored"}
SCENE_DELIVERY_STATUSES = {"pending", "delivered", "needs_correction", "rejected"}
CATALOG_LOCK = threading.RLock()
TASK_LOCK = threading.RLock()
CACHE_PRUNE_LOCK = threading.RLock()
POINT_CLOUD_SESSION_LOCK = threading.RLock()
POINT_CLOUD_FILE_LOCKS: dict[str, threading.RLock] = {}
CACHE_LAST_PRUNE: dict[str, float] = {}
TASK_EXECUTOR = ThreadPoolExecutor(max_workers=TASK_WORKERS)


app = FastAPI(
    title="Remote Sensing COG Tile Service",
    version="0.2.0",
    description="GDAL + COG + TiTiler-compatible raster service for the satellite imagery manager.",
)

SMART_BAMBOO_DASHBOARD_VERSION = "20260716-interaction5"
SMART_BAMBOO_DASHBOARD_URL = f"/zhushan-bigdata.html?v={SMART_BAMBOO_DASHBOARD_VERSION}"

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


enforce_production_configuration()


@app.middleware("http")
async def enforce_human_session_policy_for_api(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        try:
            enforce_human_session_policy(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.middleware("http")
async def prevent_stale_application_shells(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path.rstrip("/") or "/"
    suffix = Path(path).suffix.lower()
    if path.startswith("/v2/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path == "/" or suffix in {".html", ".js", ".css"}:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


def record_startup_error(key: str, label: str, exc: Exception) -> None:
    errors = list(getattr(app.state, "startup_errors", []))
    errors.append(
        {
            "key": key,
            "label": label,
            "message": str(exc),
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    app.state.startup_errors = errors


try:
    init_platform_schema()
except Exception as exc:
    record_startup_error("platform_schema_init_failed", "平台数据库 schema 初始化失败", exc)
try:
    ensure_system_dictionaries()
except Exception as exc:
    record_startup_error("dictionary_seed_failed", "系统字典初始化失败", exc)
app.include_router(admin_roles_router)
app.include_router(admin_users_router)
app.include_router(admin_organizations_router)
app.include_router(dictionaries_router)
app.include_router(auth_router)
app.include_router(human_auth_router)
app.include_router(business_router)
app.include_router(forest_blocks_router)
app.include_router(forest_rights_router)
app.include_router(forest_scene_links_router)
app.include_router(imports_router)
app.include_router(v2_router)


def ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    COG_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    POINT_CLOUD_DIR.mkdir(parents=True, exist_ok=True)
    POINT_CLOUD_UPLOAD_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    TIANDITU_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for import_dir in IMPORT_DIRS:
        import_dir.mkdir(parents=True, exist_ok=True)
    if not CATALOG_PATH.exists():
        CATALOG_PATH.write_text(json.dumps({"scenes": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not TASKS_PATH.exists():
        TASKS_PATH.write_text(json.dumps({"tasks": []}, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "-", value.strip(), flags=re.UNICODE)
    return value.strip("-") or "scene"


class RegisterSceneRequest(BaseModel):
    path: str
    name: str = ""
    satellite: str = ""
    sensor: str = ""
    capturedAt: str = ""
    resolution: str = ""
    bounds: str | list[float] | None = None
    projectId: str = ""
    areaCode: str = ""
    allowedRoles: list[str] | str | None = None
    allowedUsers: list[str] | str | None = None
    assetType: str = "orthophoto"
    missionId: str = ""
    linkedBlockCodes: list[str] | str | None = None
    processingStage: str = "ready"


class CoverageConfirmationRequest(BaseModel):
    blockCodes: list[str] = Field(min_length=1)


class PointCloudFileManifest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)
    lastModified: int | None = None


class PointCloudUploadSessionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    missionId: str = Field(default="", max_length=128)
    capturedAt: str = ""
    files: list[PointCloudFileManifest] = Field(min_length=1, max_length=500)
    outputs: list[str] = Field(default_factory=lambda: ["copc", "3dtiles"])


class PointCloudRegisterRequest(BaseModel):
    path: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)
    missionId: str = Field(default="", max_length=128)
    capturedAt: str = ""
    recursive: bool = True
    outputs: list[str] = Field(default_factory=lambda: ["copc", "3dtiles"])


class TilesetRegisterRequest(BaseModel):
    path: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)
    missionId: str = Field(default="", max_length=128)
    capturedAt: str = ""


class SceneAccessUpdateRequest(BaseModel):
    projectId: str | None = None
    areaCode: str | None = None
    allowedRoles: list[str] | str | None = None
    allowedUsers: list[str] | str | None = None


class SceneUpdateRequest(SceneAccessUpdateRequest):
    name: str | None = None
    satellite: str | None = None
    sensor: str | None = None
    capturedAt: str | None = None
    resolution: str | None = None
    bounds: list[float] | str | None = None
    visible: bool | None = None
    opacity: float | None = None
    assetType: str | None = None
    missionId: str | None = None
    linkedBlockCodes: list[str] | str | None = None
    processingStage: str | None = None


class BulkSceneAccessUpdateRequest(SceneAccessUpdateRequest):
    ids: list[str]


class SceneLayerPublishRequest(BaseModel):
    linkedBlockCodes: list[str] | str | None = None
    linkedRightArchiveCodes: list[str] | str | None = None
    name: str | None = None
    status: str | None = "published"
    style: dict[str, Any] | None = None
    zIndex: int | None = None
    visibleOnDashboard: bool = True
    properties: dict[str, Any] | None = None


class QualityIssueUpdateRequest(BaseModel):
    status: str
    comment: str = ""


class SceneDeliveryRequest(BaseModel):
    status: str
    comment: str = ""


class TiandituPrewarmRequest(BaseModel):
    bounds: list[float]
    minZoom: int = 8
    maxZoom: int = 13
    layers: list[str] = ["img_w", "cia_w"]


def split_tokens(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[,;\s]+", value)
    return sorted({str(item).strip() for item in items if str(item).strip()})


def parse_boolean_filter(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def request_context(request: Request) -> dict[str, Any]:
    context = unified_request_context(request)
    return apply_effective_data_scopes({
        "user": context.user,
        "roles": set(context.roles),
        "projects": set(context.projects),
        "areas": set(context.areas),
        "principalType": context.principal_type,
        "token": unified_bearer_token(request),
    })


def platform_auth_context(context: dict[str, Any]) -> AuthContext:
    return AuthContext(
        user=str(context.get("user") or ""),
        roles=set(context.get("roles") or set()),
        projects=set(context.get("projects") or set()),
        areas=set(context.get("areas") or set()),
        principal_type=str(context.get("principalType") or "user"),
    )


def effective_project_scope(context: AuthContext) -> tuple[set[str], bool]:
    request_projects = set(context.projects)
    request_scoped = bool(request_projects) and "*" not in request_projects
    if platform_has_admin_role(context):
        return request_projects, request_scoped

    role_projects = platform_role_data_scope_values(context, "projects")
    role_scoped = bool(role_projects) and "*" not in role_projects
    if not role_projects:
        return request_projects, request_scoped
    if "*" in role_projects:
        return request_projects or {"*"}, request_scoped
    if not request_projects or "*" in request_projects:
        return role_projects, True
    return role_projects & request_projects, role_scoped or request_scoped


def apply_effective_data_scopes(context: dict[str, Any]) -> dict[str, Any]:
    platform_context = platform_auth_context(context)
    projects, project_scoped = effective_project_scope(platform_context)
    areas = platform_effective_areas(platform_context)
    updated = dict(context)
    updated["projects"] = projects
    updated["areas"] = areas
    updated["projectScoped"] = project_scoped
    updated["areaScoped"] = platform_has_effective_area_scope(platform_context)
    return updated


def require_imagery_permission(request: Request, permission: str) -> dict[str, Any]:
    context = request_context(request)
    require_admin_permission(platform_auth_context(context), permission)
    return context


def require_imagery_manage(request: Request) -> dict[str, Any]:
    return require_imagery_permission(request, IMAGERY_MANAGE_PERMISSION)


def require_imagery_layer_publish(request: Request) -> dict[str, Any]:
    return require_imagery_permission(request, IMAGERY_LAYER_PUBLISH_PERMISSION)


def require_map_layer_upsert_permissions(
    context: dict[str, Any],
    *,
    existing: dict[str, Any],
    next_layer: dict[str, Any],
) -> None:
    platform_context = platform_auth_context(context)
    if existing:
        require_admin_permission(platform_context, MAP_LAYER_PERMISSIONS["update"])
    else:
        require_admin_permission(platform_context, MAP_LAYER_PERMISSIONS["create"])
    if bool(next_layer.get("visibleOnDashboard")) or str(next_layer.get("status") or "") == "published":
        require_admin_permission(platform_context, MAP_LAYER_PERMISSIONS["publish"])


def context_matches(values: set[str], required: str, scoped: bool = False) -> bool:
    return (not scoped and not values) or "*" in values or required in values


def parse_query_bounds(value: str | list[float] | None) -> list[float] | None:
    if value in (None, ""):
        return None
    values = value if isinstance(value, list) else re.split(r"[,;\s]+", str(value))
    try:
        bounds = [float(item) for item in values if str(item).strip()]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox must contain numeric W,S,E,N values") from exc
    if len(bounds) != 4:
        raise HTTPException(status_code=400, detail="bbox must be W,S,E,N")
    west, south, east, north = bounds
    if west >= east or south >= north or west < -180 or east > 180 or south < -90 or north > 90:
        raise HTTPException(status_code=400, detail="bbox is outside valid WGS84 bounds")
    return bounds


def scene_query_bounds(scene: dict[str, Any]) -> list[float] | None:
    try:
        return parse_query_bounds(scene.get("bounds"))
    except (HTTPException, ValueError, TypeError):
        return None


def bounds_intersect(a: list[float] | None, b: list[float] | None) -> bool:
    if not a or not b:
        return False
    aw, as_, ae, an = a
    bw, bs, be, bn = b
    return aw <= be and ae >= bw and as_ <= bn and an >= bs


def scene_allowed(scene: dict[str, Any], context: dict[str, Any]) -> bool:
    project_id = str(scene.get("projectId") or "").strip()
    area_code = str(scene.get("areaCode") or "").strip()
    allowed_users = set(split_tokens(scene.get("allowedUsers")))
    allowed_roles = set(split_tokens(scene.get("allowedRoles")))

    if project_id and not context_matches(context["projects"], project_id, bool(context.get("projectScoped"))):
        return False
    if area_code and not context_matches(context["areas"], area_code, bool(context.get("areaScoped"))):
        return False
    if allowed_users and context["user"] not in allowed_users and "*" not in allowed_users:
        return False
    if allowed_roles and "*" not in context["roles"] and not (allowed_roles & context["roles"]):
        return False
    return True


def filter_scenes(
    scenes: list[dict[str, Any]],
    context: dict[str, Any],
    q: str = "",
    status: str = "",
    project_id: str = "",
    area_code: str = "",
    bbox: list[float] | None = None,
    published: str = "",
    delivery_status: str = "",
) -> list[dict[str, Any]]:
    keyword = q.strip().lower()
    status_filter = status.strip()
    delivery_status_filter = delivery_status.strip()
    published_filter = parse_boolean_filter(published)
    result = []
    for scene in scenes:
        scene_status = str(scene.get("status") or "active")
        if status_filter and scene_status != status_filter:
            continue
        if delivery_status_filter and str(scene.get("deliveryStatus") or "pending") != delivery_status_filter:
            continue
        if published_filter is not None and published_workflow_scene(scene) != published_filter:
            continue
        if project_id and str(scene.get("projectId") or "") != project_id:
            continue
        if area_code and str(scene.get("areaCode") or "") != area_code:
            continue
        if bbox and not bounds_intersect(scene_query_bounds(scene), bbox):
            continue
        if keyword:
            text = " ".join(
                str(scene.get(key) or "")
                for key in [
                    "id",
                    "name",
                    "fileName",
                    "satellite",
                    "sensor",
                    "capturedAt",
                    "projectId",
                    "areaCode",
                    "assetType",
                    "missionId",
                    "linkedBlockCodes",
                ]
            ).lower()
            if keyword not in text:
                continue
        if scene_allowed(scene, context):
            result.append(scene)
    return result


def use_postgis_catalog() -> bool:
    return CATALOG_BACKEND == "postgis" and bool(DATABASE_URL)


def use_mysql_catalog() -> bool:
    return CATALOG_BACKEND == "mysql" and bool(DATABASE_URL)


def mysql_catalog_connect():
    try:
        import pymysql
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MySQL imagery catalog requires PyMySQL. {exc}") from exc
    try:
        return pymysql.connect(**mysql_connection_kwargs(DATABASE_URL))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MySQL imagery catalog is unavailable") from exc


def init_mysql_catalog() -> None:
    if not use_mysql_catalog():
        return
    with mysql_catalog_connect() as conn:
        with conn.cursor() as cur:
            for statement in mysql_catalog_schema_statements():
                cur.execute(statement)
        conn.commit()


def mysql_datetime(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value or None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def require_psycopg():
    try:
        import psycopg

        return psycopg
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"PostGIS catalog requires psycopg. {exc}") from exc


def postgis_connect():
    psycopg = require_psycopg()
    return psycopg.connect(DATABASE_URL)


def init_postgis_catalog() -> None:
    if not use_postgis_catalog():
        return
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS remote_sensing_scenes (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  project_id TEXT,
                  area_code TEXT,
                  created_at TIMESTAMPTZ,
                  updated_at TIMESTAMPTZ,
                  geom geometry(Polygon, 4326),
                  scene JSONB NOT NULL
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_remote_sensing_scenes_project ON remote_sensing_scenes(project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_remote_sensing_scenes_area ON remote_sensing_scenes(area_code)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_remote_sensing_scenes_geom ON remote_sensing_scenes USING GIST(geom)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_remote_sensing_scenes_scene ON remote_sensing_scenes USING GIN(scene)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS remote_sensing_tasks (
                  id TEXT PRIMARY KEY,
                  status TEXT,
                  type TEXT,
                  scene_id TEXT,
                  created_at TIMESTAMPTZ,
                  updated_at TIMESTAMPTZ,
                  task JSONB NOT NULL
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_remote_sensing_tasks_status ON remote_sensing_tasks(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_remote_sensing_tasks_scene ON remote_sensing_tasks(scene_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_remote_sensing_tasks_task ON remote_sensing_tasks USING GIN(task)")
        conn.commit()


def scene_envelope(scene: dict[str, Any]) -> list[float] | None:
    bounds = parse_bounds(scene.get("bounds"))
    return bounds


def postgis_upsert_scene(scene: dict[str, Any]) -> None:
    init_postgis_catalog()
    bounds = scene_envelope(scene)
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO remote_sensing_scenes
                  (id, name, project_id, area_code, created_at, updated_at, geom, scene)
                VALUES
                  (%s, %s, %s, %s, %s, %s,
                   CASE WHEN %s IS NULL THEN NULL ELSE ST_MakeEnvelope(%s, %s, %s, %s, 4326) END,
                   %s::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                  name = EXCLUDED.name,
                  project_id = EXCLUDED.project_id,
                  area_code = EXCLUDED.area_code,
                  updated_at = EXCLUDED.updated_at,
                  geom = EXCLUDED.geom,
                  scene = EXCLUDED.scene
                """,
                (
                    scene.get("id"),
                    scene.get("name") or scene.get("id"),
                    scene.get("projectId") or "",
                    scene.get("areaCode") or "",
                    scene.get("createdAt"),
                    scene.get("updatedAt"),
                    bounds,
                    *(bounds or [None, None, None, None]),
                    json.dumps(scene, ensure_ascii=False),
                ),
            )
        conn.commit()


def postgis_load_scenes(
    q: str = "",
    status: str = "",
    project_id: str = "",
    area_code: str = "",
    bbox: list[float] | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    init_postgis_catalog()
    where = []
    params: list[Any] = []
    if not include_deleted:
        where.append("COALESCE(scene->>'deletedAt', '') = '' AND COALESCE(scene->>'status', '') <> 'deleted'")
    if status:
        where.append("COALESCE(scene->>'status', 'active') = %s")
        params.append(status)
    if project_id:
        where.append("project_id = %s")
        params.append(project_id)
    if area_code:
        where.append("area_code = %s")
        params.append(area_code)
    if bbox:
        where.append("geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)")
        params.extend(bbox)
    if q.strip():
        where.append(
            """(
              lower(name) LIKE %s OR
              lower(scene->>'fileName') LIKE %s OR
              lower(scene->>'satellite') LIKE %s OR
              lower(scene->>'sensor') LIKE %s OR
              lower(scene->>'projectId') LIKE %s OR
              lower(scene->>'areaCode') LIKE %s
            )"""
        )
        like = f"%{q.strip().lower()}%"
        params.extend([like] * 6)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT scene FROM remote_sensing_scenes {where_sql} ORDER BY created_at DESC NULLS LAST", params)
            return [row[0] for row in cur.fetchall()]


def postgis_replace_scenes(scenes: list[dict[str, Any]]) -> None:
    init_postgis_catalog()
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM remote_sensing_scenes")
        conn.commit()
    for scene in scenes:
        postgis_upsert_scene(scene)


def postgis_delete_scene(scene_id: str) -> None:
    init_postgis_catalog()
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM remote_sensing_scenes WHERE id = %s", (scene_id,))
        conn.commit()


def task_upsert_params(task: dict[str, Any]) -> tuple[Any, ...]:
    return (
        task.get("id"),
        task.get("status") or "",
        task.get("type") or "",
        task.get("sceneId") or "",
        task.get("createdAt") or None,
        task.get("updatedAt") or None,
        json.dumps(task, ensure_ascii=False),
    )


def execute_postgis_task_upsert(cur, task: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO remote_sensing_tasks
          (id, status, type, scene_id, created_at, updated_at, task)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (id) DO UPDATE SET
          status = EXCLUDED.status,
          type = EXCLUDED.type,
          scene_id = EXCLUDED.scene_id,
          updated_at = EXCLUDED.updated_at,
          task = EXCLUDED.task
        """,
        task_upsert_params(task),
    )


def normalize_postgis_task(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if isinstance(value, dict):
        return dict(value)
    return {}


def postgis_upsert_task(task: dict[str, Any]) -> None:
    init_postgis_catalog()
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            execute_postgis_task_upsert(cur, task)
        conn.commit()


def postgis_load_tasks() -> list[dict[str, Any]]:
    init_postgis_catalog()
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT task FROM remote_sensing_tasks ORDER BY created_at DESC NULLS LAST")
            tasks = []
            for row in cur.fetchall():
                value = row[0] if isinstance(row, (tuple, list)) else row
                task = normalize_postgis_task(value)
                if task:
                    tasks.append(task)
            return tasks


def postgis_replace_tasks(tasks: list[dict[str, Any]]) -> None:
    init_postgis_catalog()
    sorted_tasks = sorted(tasks, key=lambda item: str(item.get("createdAt", "")), reverse=True)
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM remote_sensing_tasks")
            for task in sorted_tasks:
                execute_postgis_task_upsert(cur, task)
        conn.commit()


def normalize_mysql_document(value: Any) -> dict[str, Any]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return dict(value) if isinstance(value, dict) else {}


def sync_mysql_scene_events(cur: Any, scene: dict[str, Any]) -> None:
    scene_id = str(scene.get("id") or "")
    cur.execute("DELETE FROM remote_sensing_scene_events WHERE scene_id = %s", (scene_id,))
    event_collections = [
        ("publish", scene.get("publishEvents") or []),
        ("lifecycle", scene.get("lifecycleEvents") or []),
        ("quality", scene.get("qualityIssueEvents") or []),
        ("delivery", scene.get("deliveryEvents") or []),
    ]
    for event_type, events in event_collections:
        for index, raw_event in enumerate(events, start=1):
            if not isinstance(raw_event, dict):
                continue
            event = dict(raw_event)
            event_id = str(event.get("eventId") or event.get("id") or f"{event_type}-{index}")[:191]
            cur.execute(
                """
                INSERT INTO remote_sensing_scene_events (
                    scene_id, event_type, event_id, action, status, actor,
                    event_at, layer_id, issue_id, message, event_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    scene_id,
                    event_type,
                    event_id,
                    str(event.get("action") or ""),
                    str(event.get("status") or scene.get("status") or ""),
                    str(event.get("actor") or ""),
                    mysql_datetime(event.get("at") or event.get("createdAt") or event.get("updatedAt")),
                    str(event.get("layerId") or event.get("layerRecordCode") or ""),
                    str(event.get("issueId") or ""),
                    str(event.get("message") or event.get("comment") or "")[:1000],
                    json.dumps(event, ensure_ascii=False),
                ),
            )


def execute_mysql_scene_upsert(cur: Any, scene: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO remote_sensing_scenes (
            id, name, status, delivery_status, published,
            project_id, area_code, satellite, sensor, captured_at,
            created_at, updated_at, deleted_at, scene
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            status = VALUES(status),
            delivery_status = VALUES(delivery_status),
            published = VALUES(published),
            project_id = VALUES(project_id),
            area_code = VALUES(area_code),
            satellite = VALUES(satellite),
            sensor = VALUES(sensor),
            captured_at = VALUES(captured_at),
            updated_at = VALUES(updated_at),
            deleted_at = VALUES(deleted_at),
            scene = VALUES(scene)
        """,
        (
            scene.get("id"),
            scene.get("name") or scene.get("id"),
            scene.get("status") or "active",
            scene.get("deliveryStatus") or "pending",
            published_workflow_scene(scene),
            scene.get("projectId") or "",
            scene.get("areaCode") or "",
            scene.get("satellite") or "",
            scene.get("sensor") or "",
            scene.get("capturedAt") or "",
            mysql_datetime(scene.get("createdAt")),
            mysql_datetime(scene.get("updatedAt")),
            mysql_datetime(scene.get("deletedAt")),
            json.dumps(scene, ensure_ascii=False),
        ),
    )
    scene_id = str(scene.get("id") or "")
    sync_mysql_scene_events(cur, scene)
    bounds = scene_envelope(scene)
    if not bounds:
        cur.execute("DELETE FROM remote_sensing_scene_geometries WHERE scene_id = %s", (scene_id,))
        return
    west, south, east, north = bounds
    polygon_wkt = f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
    cur.execute(
        """
        INSERT INTO remote_sensing_scene_geometries (
            scene_id, footprint, min_longitude, min_latitude, max_longitude, max_latitude
        ) VALUES (%s, ST_GeomFromText(%s, 4326, 'axis-order=long-lat'), %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            footprint = VALUES(footprint),
            min_longitude = VALUES(min_longitude),
            min_latitude = VALUES(min_latitude),
            max_longitude = VALUES(max_longitude),
            max_latitude = VALUES(max_latitude)
        """,
        (scene_id, polygon_wkt, west, south, east, north),
    )


def mysql_upsert_scene(scene: dict[str, Any]) -> None:
    init_mysql_catalog()
    with mysql_catalog_connect() as conn:
        with conn.cursor() as cur:
            execute_mysql_scene_upsert(cur, scene)
        conn.commit()


def mysql_load_scenes(
    q: str = "",
    status: str = "",
    project_id: str = "",
    area_code: str = "",
    bbox: list[float] | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    init_mysql_catalog()
    clauses: list[str] = []
    params: list[Any] = []
    if not include_deleted:
        clauses.append("rs.deleted_at IS NULL AND rs.status <> 'deleted'")
    if status:
        clauses.append("rs.status = %s")
        params.append(status)
    if project_id:
        clauses.append("rs.project_id = %s")
        params.append(project_id)
    if area_code:
        clauses.append("rs.area_code = %s")
        params.append(area_code)
    if bbox:
        west, south, east, north = bbox
        polygon_wkt = f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
        clauses.append(
            "MBRIntersects(rsg.footprint, ST_GeomFromText(%s, 4326, 'axis-order=long-lat'))"
        )
        params.append(polygon_wkt)
    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            "(rs.name LIKE %s OR rs.satellite LIKE %s OR rs.sensor LIKE %s "
            "OR rs.project_id LIKE %s OR rs.area_code LIKE %s OR CAST(rs.scene AS CHAR) LIKE %s)"
        )
        params.extend([like] * 6)
    where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = (
        "SELECT rs.scene FROM remote_sensing_scenes rs "
        "LEFT JOIN remote_sensing_scene_geometries rsg ON rsg.scene_id = rs.id"
        f"{where_sql} ORDER BY rs.created_at IS NULL, rs.created_at DESC"
    )
    with mysql_catalog_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [scene for row in cur.fetchall() if (scene := normalize_mysql_document(row[0]))]


def mysql_replace_scenes(scenes: list[dict[str, Any]]) -> None:
    init_mysql_catalog()
    with mysql_catalog_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM remote_sensing_scenes")
            for scene in scenes:
                execute_mysql_scene_upsert(cur, scene)
        conn.commit()


def mysql_delete_scene(scene_id: str) -> None:
    init_mysql_catalog()
    with mysql_catalog_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM remote_sensing_scenes WHERE id = %s", (scene_id,))
        conn.commit()


def sync_mysql_task_events(cur: Any, task: dict[str, Any]) -> None:
    task_id = str(task.get("id") or "")
    cur.execute("DELETE FROM remote_sensing_task_events WHERE task_id = %s", (task_id,))
    for index, raw_event in enumerate(task.get("events") or [], start=1):
        if not isinstance(raw_event, dict):
            continue
        event = dict(raw_event)
        event_id = str(event.get("eventId") or event.get("id") or f"event-{index}")[:191]
        cur.execute(
            """
            INSERT INTO remote_sensing_task_events (
                task_id, event_id, action, status, actor,
                progress, event_at, message, event_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                task_id,
                event_id,
                str(event.get("action") or "status"),
                str(event.get("status") or task.get("status") or ""),
                str(event.get("actor") or ""),
                int(event.get("progress") or task.get("progress") or 0),
                mysql_datetime(event.get("at") or event.get("createdAt") or event.get("updatedAt")),
                str(event.get("message") or task.get("message") or "")[:1000],
                json.dumps(event, ensure_ascii=False),
            ),
        )


def execute_mysql_task_upsert(cur: Any, task: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO remote_sensing_tasks (
            id, status, type, scene_id, progress, archived_at,
            created_at, updated_at, task
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            type = VALUES(type),
            scene_id = VALUES(scene_id),
            progress = VALUES(progress),
            archived_at = VALUES(archived_at),
            updated_at = VALUES(updated_at),
            task = VALUES(task)
        """,
        (
            task.get("id"),
            task.get("status") or "",
            task.get("type") or "",
            task.get("sceneId") or "",
            int(task.get("progress") or 0),
            mysql_datetime(task.get("archivedAt")),
            mysql_datetime(task.get("createdAt")),
            mysql_datetime(task.get("updatedAt")),
            json.dumps(task, ensure_ascii=False),
        ),
    )
    sync_mysql_task_events(cur, task)


def mysql_upsert_task(task: dict[str, Any]) -> None:
    init_mysql_catalog()
    with mysql_catalog_connect() as conn:
        with conn.cursor() as cur:
            execute_mysql_task_upsert(cur, task)
        conn.commit()


def mysql_load_tasks() -> list[dict[str, Any]]:
    init_mysql_catalog()
    with mysql_catalog_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT task FROM remote_sensing_tasks ORDER BY created_at IS NULL, created_at DESC")
            return [task for row in cur.fetchall() if (task := normalize_mysql_document(row[0]))]


def mysql_replace_tasks(tasks: list[dict[str, Any]]) -> None:
    init_mysql_catalog()
    sorted_tasks = sorted(tasks, key=lambda item: str(item.get("createdAt", "")), reverse=True)
    with mysql_catalog_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM remote_sensing_tasks")
            for task in sorted_tasks:
                execute_mysql_task_upsert(cur, task)
        conn.commit()


def load_catalog(
    q: str = "",
    status: str = "",
    project_id: str = "",
    area_code: str = "",
    bbox: list[float] | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    ensure_dirs()
    if use_mysql_catalog():
        return mysql_load_scenes(
            q=q,
            status=status,
            project_id=project_id,
            area_code=area_code,
            bbox=bbox,
            include_deleted=include_deleted,
        )
    if use_postgis_catalog():
        return postgis_load_scenes(q=q, status=status, project_id=project_id, area_code=area_code, bbox=bbox, include_deleted=include_deleted)
    with CATALOG_LOCK:
        try:
            data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"scenes": []}
        scenes = list(data.get("scenes", []))
        if include_deleted:
            return scenes
        return [scene for scene in scenes if not scene.get("deletedAt") and scene.get("status") != "deleted"]


def save_catalog(scenes: list[dict[str, Any]]) -> None:
    ensure_dirs()
    if use_mysql_catalog():
        mysql_replace_scenes(scenes)
        return
    if use_postgis_catalog():
        postgis_replace_scenes(scenes)
        return
    with CATALOG_LOCK:
        scenes = sorted(scenes, key=lambda item: str(item.get("createdAt", "")), reverse=True)
        CATALOG_PATH.write_text(json.dumps({"scenes": scenes}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_tasks() -> list[dict[str, Any]]:
    ensure_dirs()
    if use_mysql_catalog():
        return mysql_load_tasks()
    if use_postgis_catalog():
        return postgis_load_tasks()
    with TASK_LOCK:
        try:
            data = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"tasks": []}
        return list(data.get("tasks", []))


def save_tasks(tasks: list[dict[str, Any]]) -> None:
    ensure_dirs()
    if use_mysql_catalog():
        with TASK_LOCK:
            mysql_replace_tasks(tasks)
        return
    if use_postgis_catalog():
        with TASK_LOCK:
            postgis_replace_tasks(tasks)
        return
    with TASK_LOCK:
        tasks = sorted(tasks, key=lambda item: str(item.get("createdAt", "")), reverse=True)
        TASKS_PATH.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_task(task: dict[str, Any]) -> dict[str, Any]:
    ensure_dirs()
    if use_mysql_catalog():
        with TASK_LOCK:
            mysql_upsert_task(task)
        return task
    if use_postgis_catalog():
        with TASK_LOCK:
            postgis_upsert_task(task)
        return task
    tasks = [item for item in load_tasks() if item.get("id") != task.get("id")]
    tasks.insert(0, task)
    save_tasks(tasks)
    return task


def update_task(task_id: str, **changes: Any) -> dict[str, Any]:
    tasks = load_tasks()
    target: dict[str, Any] | None = None
    for task in tasks:
        if task.get("id") == task_id:
            status_changed = "status" in changes and changes.get("status") != task.get("status")
            message_changed = "message" in changes and changes.get("message") != task.get("message")
            progress_changed = "progress" in changes and changes.get("progress") != task.get("progress")
            task.update(changes)
            task["updatedAt"] = now_iso()
            if status_changed or message_changed or progress_changed:
                event = {
                    "at": task["updatedAt"],
                    "status": task.get("status"),
                    "progress": task.get("progress", 0),
                    "message": task.get("message", ""),
                }
                events = list(task.get("events") or [])
                events.append(event)
                task["events"] = events
            target = task
            break
    if not target:
        raise HTTPException(status_code=404, detail="Task not found")
    if use_mysql_catalog():
        with TASK_LOCK:
            mysql_upsert_task(target)
        return target
    if use_postgis_catalog():
        with TASK_LOCK:
            postgis_upsert_task(target)
        return target
    save_tasks(tasks)
    return target


def annotate_task_event(task: dict[str, Any], action: str, actor: str) -> dict[str, Any]:
    timestamp = task.get("updatedAt") or now_iso()
    event = {
        "at": timestamp,
        "status": task.get("status"),
        "progress": task.get("progress", 0),
        "message": task.get("message", ""),
        "action": action,
        "actor": actor,
    }
    events = list(task.get("events") or [])
    if events and events[-1].get("at") == timestamp:
        events[-1].update({"action": action, "actor": actor})
    else:
        events.append(event)
    task["events"] = events
    upsert_task(task)
    return task


def cancel_task_record(task_id: str, actor: str) -> dict[str, Any]:
    original = find_task_record(task_id)
    if original.get("archivedAt"):
        raise HTTPException(status_code=409, detail="Archived tasks cannot be canceled")
    if original.get("status") != "queued":
        raise HTTPException(status_code=409, detail="Only queued tasks can be canceled")
    canceled = update_task(
        task_id,
        status="canceled",
        progress=100,
        message="Canceled by user",
        canceledAt=now_iso(),
        canceledBy=actor,
    )
    return annotate_task_event(canceled, "cancel", actor)


def archive_task_record(task_id: str, actor: str) -> dict[str, Any]:
    original = find_task_record(task_id)
    if original.get("archivedAt"):
        raise HTTPException(status_code=409, detail="Task is already archived")
    if original.get("status") not in {"completed", "failed", "canceled"}:
        raise HTTPException(status_code=409, detail="Only completed, failed, or canceled tasks can be archived")
    archived = update_task(
        task_id,
        archivedAt=now_iso(),
        archivedBy=actor,
    )
    return annotate_task_event(archived, "archive", actor)


def filter_tasks(
    tasks: list[dict[str, Any]],
    status: str = "",
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    status_filter = status.strip()
    filtered: list[dict[str, Any]] = []
    for task in tasks:
        if task.get("archivedAt") and not include_archived:
            continue
        if status_filter and str(task.get("status") or "") != status_filter:
            continue
        filtered.append(task)
    return filtered


def task_event_record(task: dict[str, Any], event: dict[str, Any], index: int) -> dict[str, Any]:
    task_id = str(task.get("id") or "")
    status = str(event.get("status") or task.get("status") or "")
    action = str(event.get("action") or "status")
    message = str(event.get("message") or task.get("message") or "")
    task_name = str(task.get("name") or task.get("fileName") or task_id)
    return {
        "eventId": f"{task_id}:{index}",
        "taskId": task_id,
        "taskName": task_name,
        "taskType": str(task.get("type") or ""),
        "sceneId": str(task.get("sceneId") or ""),
        "status": status,
        "progress": event.get("progress", task.get("progress", 0)),
        "message": message,
        "action": action,
        "actor": str(event.get("actor") or ""),
        "at": event.get("at") or "",
        "issueId": str(event.get("issueId") or ""),
        "comment": str(event.get("comment") or ""),
        "summary": f"{status or action}: {message or '-'}",
    }


def task_event_matches(
    record: dict[str, Any],
    q: str = "",
    status: str = "",
    action: str = "",
    task_id: str = "",
) -> bool:
    if status and str(record.get("status") or "") != status:
        return False
    if action and str(record.get("action") or "") != action:
        return False
    if task_id and str(record.get("taskId") or "") != task_id:
        return False
    keyword = q.strip().lower()
    if not keyword:
        return True
    haystack = " ".join(
        str(record.get(key) or "")
        for key in [
            "eventId",
            "taskId",
            "taskName",
            "taskType",
            "sceneId",
            "status",
            "message",
            "action",
            "actor",
            "issueId",
            "comment",
            "summary",
        ]
    ).lower()
    return keyword in haystack


def mysql_event_time_iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value or ""


def mysql_list_task_event_records(
    *,
    q: str = "",
    status: str = "",
    action: str = "",
    task_id: str = "",
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("rste.status = %s")
        params.append(status)
    if action:
        clauses.append("rste.action = %s")
        params.append(action)
    if task_id:
        clauses.append("rste.task_id = %s")
        params.append(task_id)
    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            "(rste.event_id LIKE %s OR rste.task_id LIKE %s OR rst.type LIKE %s "
            "OR rst.scene_id LIKE %s OR rste.actor LIKE %s OR rste.message LIKE %s)"
        )
        params.extend([like] * 6)
    where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""
    with mysql_catalog_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rste.event_id, rste.task_id, rst.type, rst.scene_id, rste.status, "
                "rste.progress, rste.message, rste.action, rste.actor, rste.event_at, rste.event_json, rst.task "
                "FROM remote_sensing_task_events rste "
                "JOIN remote_sensing_tasks rst ON rst.id = rste.task_id"
                f"{where_sql} ORDER BY rste.event_at DESC, rste.event_id DESC",
                tuple(params),
            )
            rows = cur.fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        event = normalize_mysql_document(row[10])
        task = normalize_mysql_document(row[11])
        records.append(
            {
                "eventId": row[0],
                "taskId": row[1],
                "taskName": str(task.get("name") or task.get("fileName") or row[1]),
                "taskType": row[2] or "",
                "sceneId": row[3] or "",
                "status": row[4] or "",
                "progress": row[5] or 0,
                "message": row[6] or "",
                "action": row[7] or "status",
                "actor": row[8] or "",
                "at": mysql_event_time_iso(row[9]),
                "issueId": str(event.get("issueId") or ""),
                "comment": str(event.get("comment") or ""),
                "summary": f"{row[4] or row[7] or '-'}: {row[6] or '-'}",
            }
        )
    return records


def list_task_event_records(
    q: str = "",
    status: str = "",
    action: str = "",
    task_id: str = "",
) -> list[dict[str, Any]]:
    if use_mysql_catalog():
        return mysql_list_task_event_records(q=q, status=status, action=action, task_id=task_id)
    records: list[dict[str, Any]] = []
    for task in load_tasks():
        for index, event in enumerate(task.get("events") or [], start=1):
            if isinstance(event, dict):
                records.append(task_event_record(task, event, index))
    matched = [
        record
        for record in records
        if task_event_matches(record, q=q, status=status, action=action, task_id=task_id)
    ]
    return sorted(
        matched,
        key=lambda item: (str(item.get("at") or ""), str(item.get("eventId") or "")),
        reverse=True,
    )


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


def parse_bounds(bounds: str | list[float] | None) -> list[float] | None:
    if not bounds:
        return None
    values = bounds if isinstance(bounds, list) else [item for item in re.split(r"[,\s]+", bounds) if item]
    if len(values) != 4:
        return None
    try:
        west, south, east, north = [float(item) for item in values]
    except ValueError:
        return None
    if west >= east or south >= north:
        return None
    return [west, south, east, north]


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def catalog_path(path: Path) -> str:
    resolved = path.resolve()
    if is_relative_to(resolved, DATA_DIR):
        return str(resolved.relative_to(DATA_DIR)).replace("\\", "/")
    return str(resolved)


def resolve_catalog_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (DATA_DIR / value).resolve()


def resolve_import_path(path_value: str) -> Path:
    if not path_value:
        raise HTTPException(status_code=400, detail="File path is required")
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = INBOX_DIR / path
    resolved = path.resolve()
    allowed = [directory for directory in IMPORT_DIRS if is_relative_to(resolved, directory)]
    if not allowed:
        raise HTTPException(status_code=403, detail="File is outside REMOTE_SENSING_IMPORT_DIRS")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Import file not found")
    extension = resolved.suffix.lower()
    if extension not in SUPPORTED_RASTER_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only GeoTIFF/TIFF files can be registered")
    return resolved


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


def build_scene_record(
    scene_id: str,
    source_path: Path,
    cog_path: Path,
    metadata: dict[str, Any],
    fallback_bounds: list[float] | None,
    delete_original: bool,
) -> dict[str, Any]:
    raster_info = raster_metadata(cog_path, fallback_bounds)
    file_name = metadata.get("fileName") or source_path.name
    return {
        "id": scene_id,
        "source": "server",
        "storage": "COG",
        "name": str(metadata.get("name") or source_path.stem).strip(),
        "fileName": file_name,
        "fileType": "image/tiff",
        "size": cog_path.stat().st_size,
        "originalSize": source_path.stat().st_size,
        "satellite": str(metadata.get("satellite") or "").strip(),
        "sensor": str(metadata.get("sensor") or "").strip(),
        "capturedAt": str(metadata.get("capturedAt") or "").strip(),
        "projectId": str(metadata.get("projectId") or "").strip(),
        "areaCode": str(metadata.get("areaCode") or "").strip(),
        "allowedRoles": split_tokens(metadata.get("allowedRoles")),
        "allowedUsers": split_tokens(metadata.get("allowedUsers")),
        "assetType": str(metadata.get("assetType") or "orthophoto").strip(),
        "missionId": str(metadata.get("missionId") or "").strip(),
        "linkedBlockCodes": split_tokens(metadata.get("linkedBlockCodes")),
        "processingStage": str(metadata.get("processingStage") or "ready").strip(),
        "resolution": str(metadata.get("resolution") or raster_info["resolution"]).strip(),
        "bounds": raster_info["bounds"],
        "crs": raster_info["crs"],
        "width": raster_info["width"],
        "height": raster_info["height"],
        "bands": raster_info["bands"],
        "dtype": raster_info["dtype"],
        "cogPath": catalog_path(cog_path),
        "originalPath": catalog_path(source_path),
        "deleteOriginalOnSceneDelete": delete_original,
        "opacity": 0.9,
        "visible": True,
        "transferStatus": "cog-ready",
        "deliveryStatus": "pending",
        "deliveryComment": "",
        "deliveredAt": None,
        "deliveredBy": "",
        "deliveryEvents": [],
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }


def coverage_blocks_for_footprint(
    footprint_bounds: list[float],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    bbox = ",".join(str(float(value)) for value in footprint_bounds)
    return filtered_forest_blocks(
        ForestBlockFilters(bbox=bbox, limit=1000),
        platform_auth_context(context),
        limit=5000,
    )


def apply_scene_coverage_analysis(
    scene: dict[str, Any],
    footprint: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    analysis = coverage_analysis(
        footprint["geometry"],
        coverage_blocks_for_footprint(footprint["bounds"], context),
    )
    analysis.update(
        {
            "analyzedAt": now_iso(),
            "sourceCrs": footprint.get("sourceCrs") or scene.get("crs") or "",
            "confirmedAt": None,
            "confirmedBy": "",
            "confirmedBlockCodes": [],
        }
    )
    confirmed_codes = split_tokens(scene.get("linkedBlockCodes"))
    if confirmed_codes:
        analysis.update(
            {
                "requiresConfirmation": False,
                "confirmedAt": now_iso(),
                "confirmedBy": str(context.get("user") or ""),
                "confirmedBlockCodes": confirmed_codes,
            }
        )
        scene["processingStage"] = "ready"
    else:
        scene["processingStage"] = "coverage-review"
    scene["coverageAnalysis"] = analysis
    scene["footprint"] = footprint["geometry"]
    scene["updatedAt"] = now_iso()
    return scene


def analyze_raster_scene_coverage(
    scene: dict[str, Any],
    cog_path: Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    try:
        footprint = effective_raster_footprint(cog_path)
        return apply_scene_coverage_analysis(scene, footprint, context)
    except Exception as exc:
        scene["processingStage"] = "coverage-review"
        scene["coverageAnalysis"] = {
            "algorithmVersion": "effective-footprint-v1",
            "analyzedAt": now_iso(),
            "requiresConfirmation": True,
            "matches": [],
            "suggestedBlockCodes": [],
            "error": str(exc),
        }
        scene["updatedAt"] = now_iso()
        return scene


def save_scene(scene: dict[str, Any]) -> None:
    if use_mysql_catalog():
        mysql_upsert_scene(scene)
        return
    if use_postgis_catalog():
        postgis_upsert_scene(scene)
        return
    scenes = [item for item in load_catalog(include_deleted=True) if item.get("id") != scene.get("id")]
    scenes.insert(0, scene)
    save_catalog(scenes)


def apply_access_update(scene: dict[str, Any], payload: SceneAccessUpdateRequest) -> dict[str, Any]:
    updated = dict(scene)
    if payload.projectId is not None:
        updated["projectId"] = payload.projectId.strip()
    if payload.areaCode is not None:
        updated["areaCode"] = payload.areaCode.strip()
    if payload.allowedRoles is not None:
        updated["allowedRoles"] = split_tokens(payload.allowedRoles)
    if payload.allowedUsers is not None:
        updated["allowedUsers"] = split_tokens(payload.allowedUsers)
    updated["updatedAt"] = now_iso()
    return updated


SCENE_METADATA_UPDATE_FIELDS = [
    "name",
    "satellite",
    "sensor",
    "capturedAt",
    "resolution",
    "bounds",
    "projectId",
    "areaCode",
    "allowedRoles",
    "allowedUsers",
    "visible",
    "opacity",
    "assetType",
    "missionId",
    "linkedBlockCodes",
    "processingStage",
]


def scene_metadata_snapshot(scene: dict[str, Any]) -> dict[str, Any]:
    return {field: scene.get(field) for field in SCENE_METADATA_UPDATE_FIELDS}


def apply_scene_update(
    scene: dict[str, Any],
    payload: SceneUpdateRequest,
    actor: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = apply_access_update(scene, payload)
    before = scene_metadata_snapshot(scene)

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        updated["name"] = name
    for field in ["satellite", "sensor", "capturedAt", "resolution", "assetType", "missionId", "processingStage"]:
        value = getattr(payload, field)
        if value is not None:
            updated[field] = value.strip()
    if payload.linkedBlockCodes is not None:
        updated["linkedBlockCodes"] = split_tokens(payload.linkedBlockCodes)
    if payload.bounds is not None:
        bounds = parse_bounds(payload.bounds)
        if bounds is None:
            raise HTTPException(status_code=400, detail="Invalid bounds")
        updated["bounds"] = bounds
    if payload.visible is not None:
        updated["visible"] = bool(payload.visible)
    if payload.opacity is not None:
        opacity = float(payload.opacity)
        if opacity < 0 or opacity > 1:
            raise HTTPException(status_code=400, detail="opacity must be between 0 and 1")
        updated["opacity"] = opacity

    timestamp = now_iso()
    updated["updatedAt"] = timestamp
    after = scene_metadata_snapshot(updated)
    changed_fields = sorted(field for field in SCENE_METADATA_UPDATE_FIELDS if before.get(field) != after.get(field))
    event = {
        "at": timestamp,
        "action": "metadata-update",
        "status": updated.get("status") or "active",
        "actor": actor,
        "changedFields": changed_fields,
    }
    events = list(updated.get("lifecycleEvents") or [])
    events.append(event)
    updated["lifecycleEvents"] = events
    return updated, event


def public_service_token_query(request: Request) -> str:
    settings = get_settings()
    token = (
        unified_bearer_token(request)
        if settings.auth_required and not settings.human_auth_enabled
        else ""
    )
    return f"?token={urllib.parse.quote(token)}" if token else ""


def public_scene(scene: dict[str, Any], request: Request) -> dict[str, Any]:
    scene_id = scene["id"]
    token_query = public_service_token_query(request)
    tile_url = f"/api/scenes/{scene_id}/tiles/{{z}}/{{x}}/{{y}}.png{token_query}"
    is_3d_asset = str(scene.get("assetType") or "") == "pointcloud" or bool(
        str(scene.get("tilesetPath") or "").strip()
    )
    return {
        **scene,
        "tileUrl": "" if is_3d_asset else tile_url,
        "tileJsonUrl": "" if is_3d_asset else f"/api/scenes/{scene_id}/tilejson.json{token_query}",
        "thumbnailUrl": "" if is_3d_asset else f"/api/scenes/{scene_id}/thumbnail.png{token_query}",
        "copcUrl": (
            f"/api/scenes/{scene_id}/point-cloud/copc{token_query}"
            if str(scene.get("copcPath") or "").strip()
            else ""
        ),
        "tilesetUrl": (
            f"/api/scenes/{scene_id}/point-cloud/tiles/tileset.json{token_query}"
            if str(scene.get("tilesetPath") or "").strip()
            else ""
        ),
        "metadataUrl": f"/api/scenes/{scene_id}{token_query}",
    }


def publish_layer_record_for_scene(
    scene: dict[str, Any],
    public_payload: dict[str, Any],
    payload: SceneLayerPublishRequest,
    context: dict[str, Any],
) -> dict[str, Any]:
    scene_id = str(scene.get("id") or "")
    layer_id = f"scene-layer-{slugify(scene_id)}"
    record_code = f"SCENE-LAYER-{scene_id}"
    records = layer_records()
    existing_index: int | None = None
    existing: dict[str, Any] = {}
    for index, record in enumerate(records):
        if str(record.get("id")) == layer_id or str(record.get("recordCode")) == record_code:
            existing_index = index
            existing = record
            break

    linked_blocks = split_tokens(payload.linkedBlockCodes)
    if payload.linkedBlockCodes is None:
        linked_blocks = split_tokens(existing.get("linkedBlockCodes") or scene.get("linkedBlockCodes"))
    linked_rights = split_tokens(payload.linkedRightArchiveCodes)
    if payload.linkedRightArchiveCodes is None:
        linked_rights = split_tokens(
            existing.get("linkedRightArchiveCodes") or scene.get("linkedRightArchiveCodes")
        )

    base_properties = dict(existing.get("properties") or {})
    base_properties.update(payload.properties or {})
    base_properties.update(
        {
            "source": "imagery",
            "sourceSceneId": scene_id,
            "sceneName": scene.get("name") or scene_id,
            "bounds": scene.get("bounds") or [],
            "tileUrl": public_payload.get("tileUrl") or "",
            "tileJsonUrl": public_payload.get("tileJsonUrl") or "",
            "metadataUrl": public_payload.get("metadataUrl") or "",
            "cogPath": scene.get("cogPath") or "",
            "capturedAt": scene.get("capturedAt") or "",
            "projectId": scene.get("projectId") or "",
            "areaCode": scene.get("areaCode") or "",
        }
    )
    style = payload.style if payload.style is not None else existing.get("style") or {}
    if not style:
        style = {"type": "raster", "opacity": scene.get("opacity", 0.9)}

    layer_payload = {
        **existing,
        "id": layer_id,
        "recordCode": record_code,
        "name": (payload.name or scene.get("name") or scene_id),
        "status": payload.status or "published",
        "layerType": "imagery",
        "dataSource": f"scene:{scene_id}",
        "style": style,
        "zIndex": payload.zIndex if payload.zIndex is not None else existing.get("zIndex"),
        "visibleOnDashboard": payload.visibleOnDashboard,
        "linkedBlockCodes": linked_blocks,
        "linkedRightArchiveCodes": linked_rights,
        "properties": base_properties,
        "deletedAt": None,
    }
    normalized = normalize_record(layer_payload, default_status="published")
    require_map_layer_upsert_permissions(context, existing=existing, next_layer=normalized)
    normalized = append_map_layer_audit_event(
        normalized,
        "publish-from-scene",
        platform_auth_context(context),
        before=existing or None,
        changed_fields=map_layer_changed_fields(existing, normalized),
    )
    if existing_index is None:
        records.append(normalized)
    else:
        records[existing_index] = normalized
    save_layer_records(records)
    return enrich_map_layer_record(normalized)


def append_scene_publish_event(
    scene: dict[str, Any],
    layer: dict[str, Any],
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    timestamp = now_iso()
    event = {
        "at": timestamp,
        "action": "publish-layer",
        "status": "published",
        "actor": str(context.get("user") or ""),
        "layerId": layer.get("id"),
        "layerRecordCode": layer.get("recordCode"),
    }
    updated = dict(scene)
    events = list(updated.get("publishEvents") or [])
    events.append(event)
    updated["publishEvents"] = events
    updated["publishedLayerId"] = layer.get("id")
    updated["publishedLayerRecordCode"] = layer.get("recordCode")
    updated["updatedAt"] = timestamp
    save_scene(updated)
    return updated, event


def scene_event_record(
    scene: dict[str, Any],
    event: dict[str, Any],
    event_type: str,
    index: int,
) -> dict[str, Any]:
    scene_id = str(scene.get("id") or "")
    action = str(event.get("action") or "")
    status = str(event.get("status") or scene.get("status") or "")
    return {
        "eventId": f"{scene_id}:{event_type}:{index}",
        "sceneId": scene_id,
        "sceneName": str(scene.get("name") or scene_id),
        "eventType": event_type,
        "action": action,
        "status": status,
        "actor": str(event.get("actor") or ""),
        "at": event.get("at") or "",
        "layerId": event.get("layerId") or "",
        "layerRecordCode": event.get("layerRecordCode") or "",
        "issueId": event.get("issueId") or "",
        "comment": event.get("comment") or "",
        "message": event.get("message") or event.get("comment") or "",
        "summary": f"{event_type}: {action or status or '-'}",
    }


def scene_event_matches(
    record: dict[str, Any],
    q: str = "",
    event_type: str = "",
    action: str = "",
    scene_id: str = "",
) -> bool:
    if event_type and str(record.get("eventType") or "") != event_type:
        return False
    if action and str(record.get("action") or "") != action:
        return False
    if scene_id and str(record.get("sceneId") or "") != scene_id:
        return False
    keyword = q.strip().lower()
    if not keyword:
        return True
    haystack = " ".join(
        str(record.get(key) or "")
        for key in [
            "eventId",
            "sceneId",
            "sceneName",
            "eventType",
            "action",
            "status",
            "actor",
            "layerId",
            "layerRecordCode",
            "issueId",
            "comment",
            "message",
            "summary",
        ]
    ).lower()
    return keyword in haystack


def mysql_list_scene_event_records(
    *,
    q: str = "",
    event_type: str = "",
    action: str = "",
    scene_id: str = "",
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if event_type:
        clauses.append("rsse.event_type = %s")
        params.append(event_type)
    if action:
        clauses.append("rsse.action = %s")
        params.append(action)
    if scene_id:
        clauses.append("rsse.scene_id = %s")
        params.append(scene_id)
    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            "(rsse.event_id LIKE %s OR rsse.scene_id LIKE %s OR rss.name LIKE %s "
            "OR rsse.actor LIKE %s OR rsse.layer_id LIKE %s OR rsse.issue_id LIKE %s OR rsse.message LIKE %s)"
        )
        params.extend([like] * 7)
    where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""
    with mysql_catalog_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rsse.event_id, rsse.scene_id, rss.name, rsse.event_type, rsse.action, "
                "rsse.status, rsse.actor, rsse.event_at, rsse.layer_id, rsse.issue_id, rsse.message, rsse.event_json "
                "FROM remote_sensing_scene_events rsse "
                "JOIN remote_sensing_scenes rss ON rss.id = rsse.scene_id"
                f"{where_sql} ORDER BY rsse.event_at DESC, rsse.event_id DESC",
                tuple(params),
            )
            rows = cur.fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        event = normalize_mysql_document(row[11])
        records.append(
            {
                "eventId": row[0],
                "sceneId": row[1],
                "sceneName": row[2] or row[1],
                "eventType": row[3] or "",
                "action": row[4] or "",
                "status": row[5] or "",
                "actor": row[6] or "",
                "at": mysql_event_time_iso(row[7]),
                "layerId": row[8] or "",
                "layerRecordCode": str(event.get("layerRecordCode") or ""),
                "issueId": row[9] or "",
                "comment": str(event.get("comment") or ""),
                "message": row[10] or "",
                "summary": f"{row[3] or 'event'}: {row[4] or row[5] or '-'}",
            }
        )
    return records


def list_scene_event_records(
    q: str = "",
    event_type: str = "",
    action: str = "",
    scene_id: str = "",
) -> list[dict[str, Any]]:
    if use_mysql_catalog():
        return mysql_list_scene_event_records(q=q, event_type=event_type, action=action, scene_id=scene_id)
    records: list[dict[str, Any]] = []
    for scene in load_catalog(include_deleted=True):
        for index, event in enumerate(scene.get("publishEvents") or [], start=1):
            if isinstance(event, dict):
                records.append(scene_event_record(scene, event, "publish", index))
        for index, event in enumerate(scene.get("lifecycleEvents") or [], start=1):
            if isinstance(event, dict):
                records.append(scene_event_record(scene, event, "lifecycle", index))
        for index, event in enumerate(scene.get("qualityIssueEvents") or [], start=1):
            if isinstance(event, dict):
                records.append(scene_event_record(scene, event, "quality", index))
        for index, event in enumerate(scene.get("deliveryEvents") or [], start=1):
            if isinstance(event, dict):
                records.append(scene_event_record(scene, event, "delivery", index))
    matched = [
        record
        for record in records
        if scene_event_matches(record, q=q, event_type=event_type, action=action, scene_id=scene_id)
    ]
    return sorted(
        matched,
        key=lambda item: (str(item.get("at") or ""), str(item.get("eventId") or "")),
        reverse=True,
    )


def update_scene_delivery_status(
    scene: dict[str, Any],
    payload: SceneDeliveryRequest,
    request: Request,
) -> tuple[dict[str, Any], dict[str, Any]]:
    context = require_imagery_permission(request, IMAGERY_SCENE_DELIVERY_PERMISSION)
    if not scene_allowed(scene, request_context(request)):
        raise HTTPException(status_code=403, detail="Scene is not visible for current context")
    if scene.get("deletedAt") or scene.get("status") == "deleted":
        raise HTTPException(status_code=409, detail="Deleted imagery scene cannot be delivered")

    status = payload.status.strip()
    if status not in SCENE_DELIVERY_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of: {', '.join(sorted(SCENE_DELIVERY_STATUSES))}",
        )
    if status == "delivered" and not published_workflow_scene(scene):
        raise HTTPException(status_code=409, detail="Scene must be published before delivery can be confirmed")

    timestamp = now_iso()
    actor = str(context.get("user") or "")
    previous_status = scene.get("deliveryStatus") or "pending"
    event = {
        "at": timestamp,
        "action": "delivery",
        "status": status,
        "actor": actor,
        "comment": payload.comment.strip(),
        "previousDeliveryStatus": previous_status,
    }
    updated = dict(scene)
    events = list(updated.get("deliveryEvents") or [])
    events.append(event)
    updated["deliveryStatus"] = status
    updated["deliveryComment"] = payload.comment.strip()
    updated["deliveredAt"] = timestamp
    updated["deliveredBy"] = actor
    updated["deliveryEvents"] = events
    updated["updatedAt"] = timestamp
    save_scene(updated)
    return updated, event


def csv_download_response(filename: str, columns: list[str], records: list[dict[str, Any]]) -> Response:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    for record in records:
        writer.writerow(
            [
                json.dumps(record.get(column), ensure_ascii=False, sort_keys=True)
                if isinstance(record.get(column), (dict, list))
                else record.get(column, "")
                for column in columns
            ]
        )
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def imagery_issue_record(
    *,
    issue_type: str,
    issue_key: str,
    severity: str,
    message: str,
    action_required: str,
    source: str,
    scene: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scene = scene or {}
    task = task or {}
    scene_id = str(scene.get("id") or task.get("sceneId") or "")
    task_id = str(task.get("id") or "")
    return {
        "issueId": f"{source}:{issue_type}:{issue_key}",
        "issueType": issue_type,
        "issueKey": issue_key,
        "severity": severity,
        "source": source,
        "sceneId": scene_id,
        "sceneName": str(scene.get("name") or task.get("name") or scene_id),
        "taskId": task_id,
        "taskName": str(task.get("name") or task.get("fileName") or task_id),
        "status": "open",
        "sourceStatus": str(task.get("status") or scene.get("status") or ""),
        "message": message,
        "actionRequired": action_required,
        "at": task.get("updatedAt") or scene.get("updatedAt") or scene.get("createdAt") or "",
    }


def latest_imagery_quality_issue_event(record: dict[str, Any], issue_id: str) -> dict[str, Any] | None:
    for event in reversed(record.get("qualityIssueEvents") or []):
        if isinstance(event, dict) and str(event.get("issueId") or "") == issue_id:
            return event
    return None


def apply_imagery_quality_issue_event(issue: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    event = latest_imagery_quality_issue_event(record, str(issue.get("issueId") or ""))
    if not event:
        return issue
    updated = dict(issue)
    updated["status"] = event.get("status") or updated.get("status") or "open"
    updated["handledBy"] = event.get("actor") or ""
    updated["handledAt"] = event.get("at")
    updated["handlingComment"] = event.get("comment") or ""
    updated["at"] = event.get("at") or updated.get("at")
    return updated


def imagery_quality_issues_for_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    if scene.get("deletedAt") or scene.get("status") == "deleted":
        return []

    issues: list[dict[str, Any]] = []
    scene_id = str(scene.get("id") or "")
    if parse_bounds(scene.get("bounds")) is None:
        issues.append(
            imagery_issue_record(
                issue_type="missing_bounds",
                issue_key=scene_id,
                severity="blocked",
                message="影像缺少有效覆盖范围，无法在地图中准确定位。",
                action_required="补录影像覆盖范围 W,S,E,N，或重新入库带空间参考的 GeoTIFF。",
                source="scene",
                scene=scene,
            )
        )

    if str(scene.get("storage") or "").upper() == "COG" and not str(scene.get("cogPath") or "").strip():
        issues.append(
            imagery_issue_record(
                issue_type="missing_cog_path",
                issue_key=scene_id,
                severity="blocked",
                message="影像目录缺少 COG 文件路径，瓦片服务无法读取源影像。",
                action_required="重新注册/上传影像，或在影像元数据中补齐 COG 路径。",
                source="scene",
                scene=scene,
            )
        )

    if str(scene.get("transferStatus") or "").lower() in {"failed", "error"}:
        issues.append(
            imagery_issue_record(
                issue_type="transfer_failed",
                issue_key=scene_id,
                severity="blocked",
                message=str(scene.get("message") or "影像转换状态为失败。"),
                action_required="检查源文件与 GDAL 转换日志后重新入库。",
                source="scene",
                scene=scene,
            )
        )
    return [apply_imagery_quality_issue_event(issue, scene) for issue in issues]


def imagery_quality_issues_for_task(task: dict[str, Any]) -> list[dict[str, Any]]:
    task_id = str(task.get("id") or "")
    status = str(task.get("status") or "")
    if status == "failed":
        return [
            imagery_issue_record(
                issue_type="task_failure",
                issue_key=task_id,
                severity="blocked",
                message=str(task.get("message") or "影像转换任务失败。"),
                action_required="检查源文件、空间参考和服务依赖后重试转换任务。",
                source="task",
                task=task,
            )
        ]
    if status == "canceled":
        return [
            imagery_issue_record(
                issue_type="task_canceled",
                issue_key=task_id,
                severity="warning",
                message=str(task.get("message") or "影像转换任务已取消。"),
                action_required="确认是否需要重新提交入库任务。",
                source="task",
                task=task,
            )
        ]
    return []


def imagery_issue_matches(
    issue: dict[str, Any],
    *,
    q: str = "",
    issue_type: str = "",
    severity: str = "",
    scene_id: str = "",
    task_id: str = "",
    status: str = "",
) -> bool:
    if issue_type and str(issue.get("issueType") or "") != issue_type:
        return False
    if severity and str(issue.get("severity") or "") != severity:
        return False
    if scene_id and str(issue.get("sceneId") or "") != scene_id:
        return False
    if task_id and str(issue.get("taskId") or "") != task_id:
        return False
    if status and str(issue.get("status") or "open") != status:
        return False
    keyword = q.strip().lower()
    if not keyword:
        return True
    haystack = " ".join(
        str(issue.get(key) or "")
        for key in [
            "issueId",
            "issueType",
            "issueKey",
            "severity",
            "source",
            "sceneId",
            "sceneName",
            "taskId",
            "taskName",
            "status",
            "sourceStatus",
            "message",
            "actionRequired",
        ]
    ).lower()
    return keyword in haystack


def list_imagery_quality_issues(
    *,
    q: str = "",
    issue_type: str = "",
    severity: str = "",
    scene_id: str = "",
    task_id: str = "",
    status: str = "",
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for scene in load_catalog(include_deleted=True):
        issues.extend(imagery_quality_issues_for_scene(scene))
    for task in load_tasks():
        if task.get("archivedAt") and not include_archived:
            continue
        issues.extend(apply_imagery_quality_issue_event(issue, task) for issue in imagery_quality_issues_for_task(task))
    matched = [
        issue
        for issue in issues
        if imagery_issue_matches(
            issue,
            q=q,
            issue_type=issue_type,
            severity=severity,
            scene_id=scene_id,
            task_id=task_id,
            status=status,
        )
    ]
    return sorted(
        matched,
        key=lambda item: (str(item.get("severity") or ""), str(item.get("at") or ""), str(item.get("issueId") or "")),
        reverse=True,
    )


def workflow_summary_card(key: str, label: str, value: int, tone: str, href: str) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "tone": tone, "href": href}


def active_workflow_scene(scene: dict[str, Any]) -> bool:
    status = str(scene.get("status") or "active")
    return not scene.get("deletedAt") and status not in {"deleted", "archived"}


def published_workflow_scene(scene: dict[str, Any]) -> bool:
    return bool(scene.get("publishedLayerRecordCode") or scene.get("publishedLayerId") or scene.get("publishedLayerRecordCode")) or str(
        scene.get("status") or ""
    ) == "published"


def imagery_workflow_summary(
    request: Request,
    context_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context_override or request_context(request)
    scenes = [
        scene
        for scene in filter_scenes(load_catalog(include_deleted=True), context)
        if active_workflow_scene(scene)
    ]
    published_scenes = [scene for scene in scenes if published_workflow_scene(scene)]
    unpublished_scenes = [scene for scene in scenes if not published_workflow_scene(scene)]
    tasks = filter_tasks(load_tasks())
    queued_tasks = [task for task in tasks if str(task.get("status") or "") == "queued"]
    running_tasks = [task for task in tasks if str(task.get("status") or "") == "running"]
    failed_tasks = [task for task in tasks if str(task.get("status") or "") == "failed"]
    issues = [
        issue
        for issue in list_imagery_quality_issues()
        if str(issue.get("status") or "open") not in {"resolved", "ignored"}
    ]
    blocked_issues = [issue for issue in issues if str(issue.get("severity") or "") == "blocked"]
    non_task_issues = [issue for issue in issues if not str(issue.get("taskId") or "").strip()]
    needs_attention = len(unpublished_scenes) + len(failed_tasks) + len(non_task_issues)
    return {
        "activeSceneTotal": len(scenes),
        "publishedScenes": len(published_scenes),
        "unpublishedScenes": len(unpublished_scenes),
        "queuedTasks": len(queued_tasks),
        "runningTasks": len(running_tasks),
        "failedTasks": len(failed_tasks),
        "openImageryIssues": len(issues),
        "blockedImageryIssues": len(blocked_issues),
        "needsAttentionTotal": needs_attention,
        "cards": [
            workflow_summary_card(
                "unpublishedScenes",
                "未发布影像",
                len(unpublished_scenes),
                "warning",
                "admin-imagery.html?published=false",
            ),
            workflow_summary_card(
                "failedTasks",
                "失败任务",
                len(failed_tasks),
                "danger",
                "admin-imagery.html?taskStatus=failed",
            ),
            workflow_summary_card(
                "runningTasks",
                "运行中任务",
                len(running_tasks),
                "ready",
                "admin-imagery.html?taskStatus=running",
            ),
            workflow_summary_card(
                "blockedImageryIssues",
                "阻断影像问题",
                len(blocked_issues),
                "danger",
                "admin-imagery.html?imageryIssueStatus=open",
            ),
        ],
    }


def imagery_operation_admin_href(base: str, **params: Any) -> str:
    query_params = {
        key: value
        for key, value in params.items()
        if str(value or "").strip()
    }
    if not query_params:
        return base
    return f"{base}?{urllib.parse.urlencode(query_params)}"


def imagery_operation_stage(key: str) -> dict[str, Any]:
    for stage in IMAGERY_OPERATION_QUEUE_STAGES:
        if stage["key"] == key:
            return dict(stage)
    return {"key": key, "label": key, "tone": "review", "href": "admin-imagery.html"}


def imagery_operation_queue_scene_item(scene: dict[str, Any], lane: dict[str, Any]) -> dict[str, Any]:
    scene_id = str(scene.get("id") or "")
    href_params: dict[str, Any] = {"sceneId": scene_id}
    if lane.get("key") == "awaiting_publish":
        href_params = {"published": "false", "sceneId": scene_id}
    elif lane.get("key") == "awaiting_delivery":
        href_params = {"sceneDeliveryStatus": str(scene.get("deliveryStatus") or "pending"), "sceneId": scene_id}
    elif lane.get("key") == "ready":
        href_params = {"sceneDeliveryStatus": "delivered", "sceneId": scene_id}
    return {
        "itemType": "scene",
        "sceneId": scene_id,
        "name": scene.get("name") or scene_id,
        "fileName": scene.get("fileName") or "",
        "status": scene.get("status") or "active",
        "deliveryStatus": scene.get("deliveryStatus") or "pending",
        "published": published_workflow_scene(scene),
        "publishedLayerRecordCode": scene.get("publishedLayerRecordCode") or "",
        "updatedAt": scene.get("updatedAt") or scene.get("createdAt") or "",
        "adminHref": imagery_operation_admin_href("admin-imagery.html", **href_params),
        "requiredPermission": lane.get("requiredPermission") or "",
        "allPermissions": lane.get("allPermissions") or "",
        "anyPermissions": lane.get("anyPermissions") or "",
    }


def imagery_operation_queue_task_item(task: dict[str, Any], lane: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("id") or "")
    scene_id = str(task.get("sceneId") or "")
    return {
        "itemType": "task",
        "taskId": task_id,
        "sceneId": scene_id,
        "name": task.get("name") or task.get("fileName") or task_id,
        "fileName": task.get("fileName") or "",
        "status": task.get("status") or "",
        "message": task.get("message") or "",
        "updatedAt": task.get("updatedAt") or task.get("createdAt") or "",
        "adminHref": imagery_operation_admin_href("admin-imagery.html", taskStatus=task.get("status"), taskId=task_id),
        "requiredPermission": lane.get("requiredPermission") or "",
        "allPermissions": lane.get("allPermissions") or "",
        "anyPermissions": lane.get("anyPermissions") or "",
    }


def imagery_operation_queue_issue_item(issue: dict[str, Any], lane: dict[str, Any]) -> dict[str, Any]:
    issue_id = str(issue.get("issueId") or "")
    scene_id = str(issue.get("sceneId") or "")
    task_id = str(issue.get("taskId") or "")
    return {
        "itemType": "quality_issue",
        "issueId": issue_id,
        "issueType": issue.get("issueType") or "",
        "issueKey": issue.get("issueKey") or "",
        "severity": issue.get("severity") or "",
        "status": issue.get("status") or "open",
        "sceneId": scene_id,
        "sceneName": issue.get("sceneName") or "",
        "taskId": task_id,
        "taskName": issue.get("taskName") or "",
        "message": issue.get("message") or "",
        "actionRequired": issue.get("actionRequired") or "",
        "updatedAt": issue.get("updatedAt") or issue.get("handledAt") or issue.get("at") or "",
        "adminHref": issue.get("adminHref")
        or imagery_operation_admin_href(
            "admin-imagery.html",
            imageryIssueStatus=issue.get("status") or "open",
            imageryIssueId=issue_id,
            sceneId=scene_id,
            taskId=task_id,
        ),
        "requiredPermission": lane.get("requiredPermission") or "",
        "allPermissions": lane.get("allPermissions") or "",
        "anyPermissions": lane.get("anyPermissions") or "",
    }


def imagery_operation_queue_lane(key: str, items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    stage = imagery_operation_stage(key)
    limited = items[:limit]
    return {
        **stage,
        "count": len(items),
        "limit": limit,
        "items": limited,
    }


def imagery_operation_queue(request: Request, limit: int = 5) -> dict[str, Any]:
    context = request_context(request)
    scenes = [
        scene
        for scene in filter_scenes(load_catalog(include_deleted=True), context)
        if active_workflow_scene(scene)
    ]
    scene_by_id = {str(scene.get("id") or ""): scene for scene in scenes}
    visible_tasks = []
    for task in filter_tasks(load_tasks()):
        scene_id = str(task.get("sceneId") or "")
        if scene_id and scene_id not in scene_by_id:
            continue
        visible_tasks.append(task)
    visible_task_by_id = {str(task.get("id") or ""): task for task in visible_tasks}

    failed_tasks = [task for task in visible_tasks if str(task.get("status") or "") == "failed"]
    failed_task_ids = {str(task.get("id") or "") for task in failed_tasks}
    open_issues: list[dict[str, Any]] = []
    for issue in list_imagery_quality_issues():
        if str(issue.get("status") or "open") in {"resolved", "ignored"}:
            continue
        scene_id = str(issue.get("sceneId") or "")
        task_id = str(issue.get("taskId") or "")
        if scene_id and scene_id not in scene_by_id:
            continue
        if task_id and task_id not in visible_task_by_id:
            continue
        open_issues.append(issue)

    unpublished_scenes = [scene for scene in scenes if not published_workflow_scene(scene)]
    awaiting_delivery_scenes = [
        scene
        for scene in scenes
        if published_workflow_scene(scene) and str(scene.get("deliveryStatus") or "pending") != "delivered"
    ]
    ready_scenes = [
        scene
        for scene in scenes
        if published_workflow_scene(scene) and str(scene.get("deliveryStatus") or "pending") == "delivered"
    ]

    lane_payloads = {
        "failed_tasks": sorted(
            [imagery_operation_queue_task_item(task, imagery_operation_stage("failed_tasks")) for task in failed_tasks],
            key=lambda item: str(item.get("updatedAt") or ""),
            reverse=True,
        ),
        "quality_issues": sorted(
            [imagery_operation_queue_issue_item(issue, imagery_operation_stage("quality_issues")) for issue in open_issues],
            key=lambda item: (str(item.get("severity") or ""), str(item.get("updatedAt") or ""), str(item.get("issueId") or "")),
            reverse=True,
        ),
        "awaiting_publish": sorted(
            [
                imagery_operation_queue_scene_item(scene, imagery_operation_stage("awaiting_publish"))
                for scene in unpublished_scenes
            ],
            key=lambda item: str(item.get("updatedAt") or ""),
            reverse=True,
        ),
        "awaiting_delivery": sorted(
            [
                imagery_operation_queue_scene_item(scene, imagery_operation_stage("awaiting_delivery"))
                for scene in awaiting_delivery_scenes
            ],
            key=lambda item: str(item.get("updatedAt") or ""),
            reverse=True,
        ),
        "ready": sorted(
            [imagery_operation_queue_scene_item(scene, imagery_operation_stage("ready")) for scene in ready_scenes],
            key=lambda item: str(item.get("updatedAt") or ""),
            reverse=True,
        ),
    }
    non_duplicate_quality_count = len(
        [
            issue
            for issue in open_issues
            if not str(issue.get("taskId") or "").strip() or str(issue.get("taskId") or "") not in failed_task_ids
        ]
    )
    actionable_total = (
        len(failed_tasks)
        + non_duplicate_quality_count
        + len(unpublished_scenes)
        + len(awaiting_delivery_scenes)
    )
    operation_total = actionable_total + len(ready_scenes)
    lanes = [
        imagery_operation_queue_lane(stage["key"], lane_payloads.get(stage["key"], []), limit)
        for stage in IMAGERY_OPERATION_QUEUE_STAGES
    ]
    return {
        "items": lanes,
        "operationQueue": lanes,
        "summary": {
            "operationQueueTotal": operation_total,
            "actionableQueueTotal": actionable_total,
            "failedTaskTotal": len(failed_tasks),
            "openIssueTotal": len(open_issues),
            "awaitingPublishTotal": len(unpublished_scenes),
            "awaitingDeliveryTotal": len(awaiting_delivery_scenes),
            "readyTotal": len(ready_scenes),
        },
        "limit": limit,
    }


def published_layer_for_scene(scene: dict[str, Any]) -> dict[str, Any]:
    scene_id = str(scene.get("id") or "")
    published_layer_id = str(scene.get("publishedLayerId") or "")
    published_record_code = str(scene.get("publishedLayerRecordCode") or "")
    fallback_record_code = f"SCENE-LAYER-{scene_id}"
    for record in layer_records():
        properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
        if (
            (published_layer_id and str(record.get("id")) == published_layer_id)
            or (published_record_code and str(record.get("recordCode")) == published_record_code)
            or str(record.get("recordCode")) == fallback_record_code
            or str(properties.get("sourceSceneId") or "") == scene_id
            or str(record.get("dataSource") or "") == f"scene:{scene_id}"
        ):
            return enrich_map_layer_record(record)
    return {}


def published_layers_for_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    scene_id = str(scene.get("id") or "")
    published_layer_id = str(scene.get("publishedLayerId") or "")
    published_record_code = str(scene.get("publishedLayerRecordCode") or "")
    fallback_record_code = f"SCENE-LAYER-{scene_id}"
    layers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in layer_records():
        properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
        matches = (
            (published_layer_id and str(record.get("id")) == published_layer_id)
            or (published_record_code and str(record.get("recordCode")) == published_record_code)
            or str(record.get("recordCode")) == fallback_record_code
            or str(properties.get("sourceSceneId") or "") == scene_id
            or str(record.get("dataSource") or "") == f"scene:{scene_id}"
        )
        if not matches:
            continue
        enriched = enrich_map_layer_record(record)
        key = str(enriched.get("id") or enriched.get("recordCode") or len(layers))
        if key in seen:
            continue
        seen.add(key)
        layers.append(enriched)
    return sorted(layers, key=lambda item: (str(item.get("recordCode") or ""), str(item.get("id") or "")))


def imagery_receipt_export_metadata(context: dict[str, Any] | None, permission: str) -> dict[str, Any]:
    platform_context = platform_auth_context(context or {})
    return {
        "exportedBy": str((context or {}).get("user") or ""),
        "exportPermission": permission,
        "exportRoles": role_codes_for_context(platform_context) if context else [],
        "exportDataScopes": effective_data_scopes_for_context(platform_context) if context else {},
    }


def append_scene_delivery_receipt_export_event(
    scene: dict[str, Any],
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    timestamp = now_iso()
    event = {
        "at": timestamp,
        "action": "export-delivery-receipt",
        "status": scene.get("deliveryStatus") or scene.get("status") or "active",
        "actor": str(context.get("user") or ""),
        "message": "delivery receipt exported",
        "permission": IMAGERY_SCENE_EXPORT_PERMISSION,
    }
    updated = dict(scene)
    events = list(updated.get("lifecycleEvents") or [])
    events.append(event)
    updated["lifecycleEvents"] = events
    updated["updatedAt"] = timestamp
    save_scene(updated)
    return updated, event


def append_scene_publication_receipt_export_event(
    scene: dict[str, Any],
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    timestamp = now_iso()
    published = bool(published_layers_for_scene(scene)) or published_workflow_scene(scene)
    event = {
        "at": timestamp,
        "action": "export-publication-receipt",
        "status": "published" if published else "unpublished",
        "actor": str(context.get("user") or ""),
        "message": "publication receipt exported",
        "permission": IMAGERY_SCENE_EXPORT_PERMISSION,
    }
    updated = dict(scene)
    events = list(updated.get("lifecycleEvents") or [])
    events.append(event)
    updated["lifecycleEvents"] = events
    updated["updatedAt"] = timestamp
    save_scene(updated)
    return updated, event


def scene_delivery_receipt(
    scene: dict[str, Any],
    request: Request,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scene_id = str(scene.get("id") or "")
    public_payload = public_scene(scene, request)
    quality_issues = list_imagery_quality_issues(scene_id=scene_id)
    scene_events = list_scene_event_records(scene_id=scene_id)
    published_layer = published_layer_for_scene(scene)
    linked_block_codes = split_tokens(published_layer.get("linkedBlockCodes") or scene.get("linkedBlockCodes"))
    published = bool(published_layer) or published_workflow_scene(scene)
    return {
        "receiptType": "imagery-scene-delivery",
        "exportedAt": now_iso(),
        **imagery_receipt_export_metadata(context, IMAGERY_SCENE_EXPORT_PERMISSION),
        "scene": public_payload,
        "summary": {
            "sceneId": scene_id,
            "name": scene.get("name") or scene_id,
            "status": scene.get("status") or "active",
            "deliveryStatus": scene.get("deliveryStatus") or "pending",
            "deliveredBy": scene.get("deliveredBy") or "",
            "deliveredAt": scene.get("deliveredAt"),
            "published": published,
            "qualityIssueCount": len(quality_issues),
            "sceneEventCount": len(scene_events),
            "linkedBlockCount": len(linked_block_codes),
            "publishedLayerRecordCode": published_layer.get("recordCode")
            or scene.get("publishedLayerRecordCode")
            or "",
        },
        "publishedLayer": published_layer,
        "qualityIssues": quality_issues,
        "sceneEvents": scene_events,
        "deliveryEvents": list(scene.get("deliveryEvents") or []),
    }


def scene_publication_receipt(
    scene: dict[str, Any],
    request: Request,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scene_id = str(scene.get("id") or "")
    public_payload = public_scene(scene, request)
    map_layers = published_layers_for_scene(scene)
    scene_events = list_scene_event_records(scene_id=scene_id)
    linked_block_codes = sorted(
        {
            code
            for layer in map_layers
            for code in split_tokens(layer.get("linkedBlockCodes") or [])
        }
    )
    linked_right_codes = sorted(
        {
            code
            for layer in map_layers
            for code in split_tokens(layer.get("linkedRightArchiveCodes") or [])
        }
    )
    published = any(
        str(layer.get("status") or "") == "published" and bool(layer.get("visibleOnDashboard"))
        for layer in map_layers
    ) or published_workflow_scene(scene)
    dashboard_href = next(
        (str(layer.get("dashboardHref") or "") for layer in map_layers if str(layer.get("dashboardHref") or "")),
        "zhushan-bigdata.html#mapLayers" if published else "",
    )
    return {
        "receiptType": "imagery-scene-publication",
        "exportedAt": now_iso(),
        **imagery_receipt_export_metadata(context, IMAGERY_SCENE_EXPORT_PERMISSION),
        "scene": public_payload,
        "summary": {
            "sceneId": scene_id,
            "name": scene.get("name") or scene_id,
            "status": scene.get("status") or "active",
            "published": published,
            "publishedLayerCount": len(map_layers),
            "visibleOnDashboardCount": sum(1 for layer in map_layers if bool(layer.get("visibleOnDashboard"))),
            "linkedBlockCount": len(linked_block_codes),
            "linkedRightArchiveCount": len(linked_right_codes),
            "sceneEventCount": len(scene_events),
            "dashboardHref": dashboard_href,
        },
        "mapLayers": map_layers,
        "linkedBlockCodes": linked_block_codes,
        "linkedRightArchiveCodes": linked_right_codes,
        "sceneEvents": scene_events,
    }


def append_imagery_quality_issue_event(
    record: dict[str, Any],
    *,
    issue_id: str,
    status: str,
    comment: str,
    actor: str,
) -> dict[str, Any]:
    event = {
        "at": now_iso(),
        "action": "quality-issue-update",
        "issueId": issue_id,
        "status": status,
        "comment": comment,
        "message": comment or issue_id,
        "actor": actor,
    }
    events = list(record.get("qualityIssueEvents") or [])
    events.append(event)
    record["qualityIssueEvents"] = events
    record["updatedAt"] = event["at"]
    return event


def update_imagery_quality_issue(issue_id: str, payload: QualityIssueUpdateRequest, context: dict[str, Any]) -> dict[str, Any]:
    status = payload.status.strip()
    if status not in QUALITY_ISSUE_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(sorted(QUALITY_ISSUE_STATUSES))}")

    issue = next((item for item in list_imagery_quality_issues(include_archived=True) if str(item.get("issueId")) == issue_id), None)
    if not issue:
        raise HTTPException(status_code=404, detail="Imagery quality issue not found")

    actor = str(context.get("user") or "")
    comment = payload.comment.strip()
    if issue.get("source") == "task":
        task_id = str(issue.get("taskId") or "")
        tasks = load_tasks()
        task = next((item for item in tasks if str(item.get("id")) == task_id), None)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        event = append_imagery_quality_issue_event(task, issue_id=issue_id, status=status, comment=comment, actor=actor)
        task_events = list(task.get("events") or [])
        task_events.append(event)
        task["events"] = task_events
        save_tasks(tasks)
        return {"ok": True, "issue": apply_imagery_quality_issue_event(issue, task), "event": event, "task": task}

    scene_id = str(issue.get("sceneId") or "")
    scene = find_scene(scene_id, include_deleted=True)
    event = append_imagery_quality_issue_event(scene, issue_id=issue_id, status=status, comment=comment, actor=actor)
    save_scene(scene)
    return {"ok": True, "issue": apply_imagery_quality_issue_event(issue, scene), "event": event, "scene": scene}


def archive_scene_published_layer(
    scene: dict[str, Any],
    timestamp: str,
    actor: str,
    reason: str = "source-scene-archived",
) -> dict[str, Any] | None:
    scene_id = str(scene.get("id") or "")
    published_layer_id = str(scene.get("publishedLayerId") or "")
    published_record_code = str(scene.get("publishedLayerRecordCode") or "")
    fallback_record_code = f"SCENE-LAYER-{scene_id}"
    records = layer_records()
    target_index: int | None = None
    target: dict[str, Any] = {}

    for index, record in enumerate(records):
        properties = record.get("properties") or {}
        if (
            (published_layer_id and str(record.get("id")) == published_layer_id)
            or (published_record_code and str(record.get("recordCode")) == published_record_code)
            or str(record.get("recordCode")) == fallback_record_code
            or str(properties.get("sourceSceneId")) == scene_id
            or str(record.get("dataSource")) == f"scene:{scene_id}"
        ):
            target_index = index
            target = record
            break

    if target_index is None:
        return None

    properties = dict(target.get("properties") or {})
    properties.update(
        {
            "archivedAt": timestamp,
            "archivedBy": actor,
            "archiveReason": reason,
        }
    )
    if reason == "source-scene-deleted":
        properties["deletedSceneId"] = scene_id
    layer_payload = {
        **target,
        "status": "archived",
        "visibleOnDashboard": False,
        "properties": properties,
    }
    archived_layer = normalize_record(layer_payload, default_status="archived")
    records[target_index] = archived_layer
    save_layer_records(records)
    return archived_layer


def find_scene(scene_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
    for scene in load_catalog(include_deleted=include_deleted):
        if scene.get("id") == scene_id:
            return scene
    raise HTTPException(status_code=404, detail="Scene not found")


def find_allowed_scene(scene_id: str, request: Request) -> dict[str, Any]:
    scene = find_scene(scene_id)
    if not scene_allowed(scene, request_context(request)):
        raise HTTPException(status_code=403, detail="Scene is not visible for current context")
    return scene


def task_public(task: dict[str, Any], request: Request | None = None) -> dict[str, Any]:
    if not request or not task.get("sceneId"):
        return task
    token_query = public_service_token_query(request)
    payload = {
        **task,
        "sceneUrl": f"/api/scenes/{task['sceneId']}{token_query}",
    }
    if task.get("status") == "failed":
        payload["retryUrl"] = f"/api/tasks/{task['id']}/retry{token_query}"
    return payload


def dashboard_count(value: Any, unit: str) -> str:
    try:
        numeric = int(value or 0)
    except (TypeError, ValueError):
        numeric = 0
    return f"{numeric} {unit}"


def satellite_track_task_row(task: dict[str, Any]) -> list[str]:
    return [
        str(task.get("id") or task.get("taskId") or task.get("name") or "未命名任务"),
        str(task.get("status") or "待处理"),
        str(task.get("sceneId") or task.get("sceneName") or task.get("sourcePath") or "未关联影像"),
        str(task.get("updatedAt") or task.get("createdAt") or task.get("completedAt") or "-"),
    ]


def satellite_track_dashboard_payload() -> dict[str, Any]:
    tasks = filter_tasks(load_tasks(), include_archived=False)
    scenes = [scene for scene in load_catalog() if str(scene.get("status") or "active") != "archived"]
    return {
        "title": "卫星图传任务",
        "subtitle": "卫星影像入库、图传转换、影像目录与任务闭环",
        "metrics": [
            ["图传任务", dashboard_count(len(tasks), "条")],
            ["影像目录", dashboard_count(len(scenes), "景")],
            ["来源", "后台影像管理"],
        ],
        "columns": ["任务编号", "任务状态", "影像场景", "更新时间"],
        "rows": [satellite_track_task_row(task) for task in tasks[:8]],
        "emptyText": "暂无后台图传任务，请在卫星图传管理系统创建或注册影像任务",
        "adminLinks": [
            {"label": "卫星图传", "href": "satellite-manager.html"},
            {"label": "影像后台", "href": "admin-imagery.html"},
        ],
    }


def tile_cache_path(scene_id: str, z: int, x: int, y: int, bidx: list[int] | None) -> Path:
    band_key = "-".join(str(item) for item in (bidx or [])) or "default"
    return CACHE_DIR / scene_id / str(z) / str(x) / f"{y}-{band_key}.png"


def thumbnail_cache_path(scene_id: str, cog_path: Path, max_size: int) -> Path:
    stat = cog_path.stat()
    fingerprint = f"{stat.st_size}-{stat.st_mtime_ns}-{max_size}"
    return THUMBNAIL_DIR / slugify(scene_id) / f"{fingerprint}.png"


def directory_cache_stats(root: Path, enabled: bool = True, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_dirs()
    count = 0
    size = 0
    for path in root.rglob("*.png"):
        if path.is_file():
            count += 1
            size += path.stat().st_size
    return {"enabled": enabled, "path": str(root), "files": count, "bytes": size, **(extra or {})}


def prune_cache_dir(root: Path, max_bytes: int = 0, max_age_days: float = 0) -> dict[str, Any]:
    ensure_dirs()
    now = time.time()
    max_age_seconds = max_age_days * 86400 if max_age_days else 0
    files = [path for path in root.rglob("*.png") if path.is_file()]
    removed = 0
    removed_bytes = 0

    if max_age_seconds:
        keep = []
        for path in files:
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            if now - stat.st_mtime > max_age_seconds:
                removed_bytes += stat.st_size
                removed += 1
                path.unlink(missing_ok=True)
            else:
                keep.append(path)
        files = keep

    if max_bytes:
        entries = []
        total = 0
        for path in files:
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
            total += stat.st_size
        for _, size, path in sorted(entries):
            if total <= max_bytes:
                break
            path.unlink(missing_ok=True)
            total -= size
            removed += 1
            removed_bytes += size

    return {"removedFiles": removed, "removedBytes": removed_bytes}


def maybe_prune_cache(name: str, root: Path, max_bytes: int = 0, max_age_days: float = 0) -> None:
    if not max_bytes and not max_age_days:
        return
    now = time.time()
    with CACHE_PRUNE_LOCK:
        if now - CACHE_LAST_PRUNE.get(name, 0) < CACHE_PRUNE_INTERVAL:
            return
        CACHE_LAST_PRUNE[name] = now
    prune_cache_dir(root, max_bytes=max_bytes, max_age_days=max_age_days)


def cache_stats() -> dict[str, Any]:
    return directory_cache_stats(
        CACHE_DIR,
        TILE_CACHE_ENABLED,
        {
            "maxBytes": TILE_CACHE_MAX_BYTES,
            "maxAgeDays": TILE_CACHE_MAX_AGE_DAYS,
        },
    )


def clear_tile_cache(scene_id: str | None = None) -> dict[str, Any]:
    ensure_dirs()
    target = CACHE_DIR / scene_id if scene_id else CACHE_DIR
    if not target.exists():
        return cache_stats()
    if target == CACHE_DIR:
        for child in CACHE_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            elif child.is_file():
                child.unlink()
    elif is_relative_to(target, CACHE_DIR):
        shutil.rmtree(target, ignore_errors=True)
    return cache_stats()


def tianditu_cache_path(layer: str, z: int, x: int, y: int) -> Path:
    return TIANDITU_CACHE_DIR / layer / str(z) / str(x) / f"{y}.png"


def tianditu_cache_stats() -> dict[str, Any]:
    return directory_cache_stats(
        TIANDITU_CACHE_DIR,
        True,
        {
            "timeoutSeconds": TIANDITU_TIMEOUT,
            "maxBytes": BASEMAP_CACHE_MAX_BYTES,
            "maxAgeDays": BASEMAP_CACHE_MAX_AGE_DAYS,
        },
    )


def clear_tianditu_cache(layer: str | None = None) -> dict[str, Any]:
    ensure_dirs()
    target = TIANDITU_CACHE_DIR / layer if layer else TIANDITU_CACHE_DIR
    if not target.exists():
        return tianditu_cache_stats()
    if target == TIANDITU_CACHE_DIR:
        for child in TIANDITU_CACHE_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            elif child.is_file():
                child.unlink()
    elif is_relative_to(target, TIANDITU_CACHE_DIR):
        shutil.rmtree(target, ignore_errors=True)
    return tianditu_cache_stats()


def tianditu_proxy_config() -> dict[str, Any]:
    runtime = runtime_basemap_settings()
    return {
        "enabled": True,
        "layers": sorted(TIANDITU_LAYERS),
        "cache": tianditu_cache_stats(),
        "hasServerTk": bool(runtime["serverKey"]),
        "hasUpstreamProxy": bool(runtime["proxyBaseUrl"]),
        "hasFixedReferer": bool(runtime["referer"]),
        "prewarm": {
            "bounds": TIANDITU_PREWARM_BOUNDS,
            "layers": TIANDITU_PREWARM_LAYERS,
            "minZoom": TIANDITU_PREWARM_MIN_ZOOM,
            "maxZoom": TIANDITU_PREWARM_MAX_ZOOM,
            "maxTiles": TIANDITU_PREWARM_MAX_TILES,
            "startupError": str(getattr(app.state, "tianditu_prewarm_error", "")),
        },
    }


def fetch_tianditu_tile(layer: str, z: int, x: int, y: int, tk: str, referer: str = "") -> bytes:
    server_index = (z + x + y) % 8
    params = urllib.parse.urlencode({"T": layer, "x": x, "y": y, "l": z, "tk": tk})
    url = f"https://t{server_index}.tianditu.gov.cn/DataServer?{params}"
    if referer:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 SmartBambooTiandituProxy/1.0"
        )
    else:
        user_agent = "SmartBambooTiandituProxy/1.0"
    headers = {"User-Agent": user_agent}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=TIANDITU_TIMEOUT) as response:
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            content = response.read()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Tianditu tile fetch failed: {exc}") from exc

    if status >= 400:
        raise HTTPException(status_code=502, detail=f"Tianditu tile fetch failed with status {status}")
    if not content:
        raise HTTPException(status_code=502, detail="Tianditu returned an empty tile")
    if "image" not in content_type.lower() and content.lstrip().startswith(b"<"):
        raise HTTPException(status_code=502, detail="Tianditu returned a non-image response")
    return content


def fetch_tianditu_proxy_tile(layer: str, z: int, x: int, y: int) -> bytes:
    base_url = runtime_basemap_settings()["proxyBaseUrl"]
    if not base_url:
        raise HTTPException(status_code=503, detail="Tianditu upstream proxy is not configured")
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=503, detail="Tianditu upstream proxy URL is invalid")
    url = f"{base_url}/api/basemaps/tianditu/{layer}/{z}/{x}/{y}.png"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SmartBambooTiandituCacheRelay/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIANDITU_TIMEOUT) as response:
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            content = response.read()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Tianditu upstream proxy failed: {exc}") from exc

    if status >= 400:
        raise HTTPException(status_code=502, detail=f"Tianditu upstream proxy failed with status {status}")
    if not content:
        raise HTTPException(status_code=502, detail="Tianditu upstream proxy returned an empty tile")
    if "image" not in content_type.lower() and content.lstrip().startswith((b"<", b"{")):
        raise HTTPException(status_code=502, detail="Tianditu upstream proxy returned a non-image response")
    return content


def tianditu_tile_x(longitude: float, zoom: int) -> int:
    tile_count = 1 << zoom
    value = math.floor((longitude + 180.0) / 360.0 * tile_count)
    return min(tile_count - 1, max(0, value))


def tianditu_tile_y(latitude: float, zoom: int) -> int:
    tile_count = 1 << zoom
    clamped = min(85.05112878, max(-85.05112878, latitude))
    radians = math.radians(clamped)
    value = math.floor(
        (1.0 - math.log(math.tan(radians) + (1.0 / math.cos(radians))) / math.pi)
        / 2.0
        * tile_count
    )
    return min(tile_count - 1, max(0, value))


def tianditu_tiles_for_bounds(
    bounds: list[float],
    *,
    min_zoom: int,
    max_zoom: int,
) -> list[tuple[int, int, int]]:
    if len(bounds) != 4:
        raise HTTPException(status_code=422, detail="Bounds must contain west, south, east, north.")
    west, south, east, north = [float(value) for value in bounds]
    if not (-180 <= west < east <= 180 and -85.05112878 <= south < north <= 85.05112878):
        raise HTTPException(status_code=422, detail="Bounds are outside the supported Web Mercator extent.")
    if min_zoom < 0 or max_zoom > 18 or min_zoom > max_zoom:
        raise HTTPException(status_code=422, detail="Zoom range must be between 0 and 18.")

    tiles: list[tuple[int, int, int]] = []
    for zoom in range(min_zoom, max_zoom + 1):
        min_x = tianditu_tile_x(west, zoom)
        max_x = tianditu_tile_x(east, zoom)
        min_y = tianditu_tile_y(north, zoom)
        max_y = tianditu_tile_y(south, zoom)
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                tiles.append((zoom, x, y))
    return tiles


def write_tianditu_cache_tile(cache_path: Path, content: bytes) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_name(f".{cache_path.name}.{uuid.uuid4().hex}.part")
    temporary.write_bytes(content)
    temporary.replace(cache_path)


def run_tianditu_prewarm_task(task_id: str) -> None:
    task = find_task_record(task_id)
    if task.get("status") == "canceled":
        return
    basemap = runtime_basemap_settings()
    server_key = basemap["serverKey"]
    proxy_base_url = basemap["proxyBaseUrl"]
    if not server_key and not proxy_base_url:
        update_task(
            task_id,
            status="failed",
            progress=100,
            message="Tianditu server key or upstream proxy is missing",
            failedAt=now_iso(),
        )
        return

    try:
        coordinates = tianditu_tiles_for_bounds(
            [float(value) for value in list(task.get("bounds") or [])],
            min_zoom=int(task.get("minZoom") or 0),
            max_zoom=int(task.get("maxZoom") or 0),
        )
    except Exception as exc:
        update_task(
            task_id,
            status="failed",
            progress=100,
            message=f"Invalid basemap prewarm task: {exc}",
            failedAt=now_iso(),
        )
        return
    layers = [str(layer) for layer in list(task.get("layers") or [])]
    total = len(coordinates) * len(layers)
    cache_hits = 0
    downloaded = 0
    failed = 0
    errors: list[str] = []
    completed = 0
    update_task(task_id, status="running", progress=0, message="Basemap prewarm started", startedAt=now_iso())

    for layer in layers:
        for zoom, x, y in coordinates:
            cache_path = tianditu_cache_path(layer, zoom, x, y)
            try:
                if cache_path.exists():
                    cache_hits += 1
                else:
                    content = (
                        fetch_tianditu_tile(layer, zoom, x, y, server_key)
                        if server_key
                        else fetch_tianditu_proxy_tile(layer, zoom, x, y)
                    )
                    write_tianditu_cache_tile(cache_path, content)
                    downloaded += 1
            except Exception as exc:
                failed += 1
                if len(errors) < 10:
                    errors.append(f"{layer}/{zoom}/{x}/{y}: {exc}")
            completed += 1
            if completed == total or completed % max(1, total // 100) == 0:
                update_task(
                    task_id,
                    progress=min(99, int(completed * 100 / total)),
                    message=f"Basemap prewarm {completed}/{total}",
                    cacheHits=cache_hits,
                    downloadedTiles=downloaded,
                    failedTiles=failed,
                )

    maybe_prune_cache(
        "tianditu",
        TIANDITU_CACHE_DIR,
        BASEMAP_CACHE_MAX_BYTES,
        BASEMAP_CACHE_MAX_AGE_DAYS,
    )
    all_failed = failed == total and total > 0
    update_task(
        task_id,
        status="failed" if all_failed else "completed",
        progress=100,
        message=(
            f"Basemap prewarm failed for all {total} tiles"
            if all_failed
            else f"Basemap prewarm ready: {cache_hits} cached, {downloaded} downloaded, {failed} failed"
        ),
        cacheHits=cache_hits,
        downloadedTiles=downloaded,
        failedTiles=failed,
        errors=errors,
        completedAt=now_iso(),
    )


def create_tianditu_prewarm_task(
    *,
    bounds: list[float],
    min_zoom: int,
    max_zoom: int,
    layers: list[str],
    actor: str,
) -> dict[str, Any]:
    basemap = runtime_basemap_settings()
    if not basemap["serverKey"] and not basemap["proxyBaseUrl"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Configure REMOTE_SENSING_TIANDITU_TK or "
                "REMOTE_SENSING_TIANDITU_PROXY_BASE_URL before starting basemap prewarm."
            ),
        )
    normalized_layers = list(dict.fromkeys(str(layer).strip() for layer in layers if str(layer).strip()))
    unsupported = [layer for layer in normalized_layers if layer not in TIANDITU_LAYERS]
    if not normalized_layers or unsupported:
        raise HTTPException(status_code=422, detail=f"Unsupported Tianditu layers: {', '.join(unsupported) or 'none'}")
    tiles = tianditu_tiles_for_bounds(bounds, min_zoom=min_zoom, max_zoom=max_zoom)
    tile_count = len(tiles) * len(normalized_layers)
    if tile_count > TIANDITU_PREWARM_MAX_TILES:
        raise HTTPException(
            status_code=422,
            detail=f"Prewarm request contains {tile_count:,} tiles; the maximum is {TIANDITU_PREWARM_MAX_TILES:,}.",
        )

    timestamp = now_iso()
    task = {
        "id": f"task-basemap-{uuid.uuid4().hex[:12]}",
        "type": "basemap-prewarm",
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "bounds": [float(value) for value in bounds],
        "minZoom": int(min_zoom),
        "maxZoom": int(max_zoom),
        "layers": normalized_layers,
        "tileCount": tile_count,
        "cacheHits": 0,
        "downloadedTiles": 0,
        "failedTiles": 0,
        "createdBy": actor,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "events": [{"at": timestamp, "status": "queued", "progress": 0, "message": "Queued"}],
    }
    upsert_task(task)
    TASK_EXECUTOR.submit(run_tianditu_prewarm_task, task["id"])
    return task


def schedule_tianditu_startup_prewarm() -> list[dict[str, Any]]:
    basemap = runtime_basemap_settings()
    if not basemap["serverKey"] and not basemap["proxyBaseUrl"]:
        return []

    profiles = (
        (TIANDITU_PREWARM_BOUNDS, TIANDITU_PREWARM_MIN_ZOOM, TIANDITU_PREWARM_MAX_ZOOM),
        (
            TIANDITU_DETAIL_PREWARM_BOUNDS,
            TIANDITU_DETAIL_PREWARM_MIN_ZOOM,
            TIANDITU_DETAIL_PREWARM_MAX_ZOOM,
        ),
    )
    tasks: list[dict[str, Any]] = []
    for raw_bounds, min_zoom, max_zoom in profiles:
        if len(raw_bounds) != 4:
            continue
        try:
            bounds = [float(value) for value in raw_bounds]
        except ValueError:
            continue
        tasks.append(
            create_tianditu_prewarm_task(
                bounds=bounds,
                min_zoom=min_zoom,
                max_zoom=max_zoom,
                layers=TIANDITU_PREWARM_LAYERS,
                actor="system-startup",
            )
        )
    return tasks


def geoserver_wms_url() -> str:
    if GEOSERVER_WMS_URL:
        return GEOSERVER_WMS_URL
    if GEOSERVER_BASE_URL:
        return f"{GEOSERVER_BASE_URL}/wms"
    return ""


def geoserver_wfs_url() -> str:
    if GEOSERVER_WFS_URL:
        return GEOSERVER_WFS_URL
    if GEOSERVER_BASE_URL:
        return f"{GEOSERVER_BASE_URL}/wfs"
    return ""


def geoserver_config() -> dict[str, Any]:
    wms_url = geoserver_wms_url()
    wfs_url = geoserver_wfs_url()
    return {
        "enabled": bool(wms_url or wfs_url or GEOSERVER_LAYERS),
        "baseUrl": GEOSERVER_BASE_URL,
        "wmsUrl": wms_url,
        "wfsUrl": wfs_url,
        "configuredLayers": GEOSERVER_LAYERS,
    }


def fetch_geoserver_layers() -> list[dict[str, str]]:
    if GEOSERVER_LAYERS:
        return [{"name": layer, "title": layer} for layer in GEOSERVER_LAYERS]
    wms_url = geoserver_wms_url()
    if not wms_url:
        return []
    url = f"{wms_url}?service=WMS&request=GetCapabilities"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            root = ElementTree.fromstring(response.read())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GeoServer GetCapabilities failed: {exc}") from exc

    layers: list[dict[str, str]] = []
    for layer in root.findall(".//{*}Layer"):
        name_node = layer.find("{*}Name")
        if name_node is None or not name_node.text:
            continue
        title_node = layer.find("{*}Title")
        layers.append({"name": name_node.text, "title": title_node.text if title_node is not None and title_node.text else name_node.text})
    return layers


def run_conversion_task(task_id: str) -> None:
    if find_task_record(task_id).get("status") == "canceled":
        return
    task = update_task(task_id, status="running", progress=8, message="Conversion started", startedAt=now_iso())
    source_path = Path(task["sourcePath"]).resolve()
    cog_path = Path(task["cogPath"]).resolve()
    scene_id = str(task["sceneId"])
    fallback_bounds = parse_bounds(task.get("bounds"))
    delete_original = bool(task.get("deleteOriginalOnSceneDelete"))
    metadata = {
        "name": task.get("name") or source_path.stem,
        "fileName": task.get("fileName") or source_path.name,
        "satellite": task.get("satellite") or "",
        "sensor": task.get("sensor") or "",
        "capturedAt": task.get("capturedAt") or "",
        "resolution": task.get("resolution") or "",
        "projectId": task.get("projectId") or "",
        "areaCode": task.get("areaCode") or "",
        "allowedRoles": task.get("allowedRoles") or [],
        "allowedUsers": task.get("allowedUsers") or [],
        "assetType": task.get("assetType") or "orthophoto",
        "missionId": task.get("missionId") or "",
        "linkedBlockCodes": task.get("linkedBlockCodes") or [],
        "processingStage": task.get("processingStage") or "ready",
    }

    try:
        update_task(task_id, progress=18, message="GDAL converting GeoTIFF to COG")
        convert_to_cog(source_path, cog_path)
        update_task(task_id, progress=88, message="Reading raster metadata")
        scene = build_scene_record(scene_id, source_path, cog_path, metadata, fallback_bounds, delete_original)
        update_task(task_id, progress=91, message="Matching effective footprint to forest blocks")
        scene = analyze_raster_scene_coverage(
            scene,
            cog_path,
            dict(task.get("analysisContext") or {}),
        )
        update_task(task_id, progress=94, message="Writing catalog")
        save_scene(scene)
        update_task(
            task_id,
            status="completed",
            progress=100,
            message="COG scene is ready",
            scene=scene,
            completedAt=now_iso(),
        )
    except Exception as exc:
        update_task(task_id, status="failed", progress=100, message=str(exc), failedAt=now_iso())


def create_conversion_task(
    source_path: Path,
    metadata: dict[str, Any],
    fallback_bounds: list[float] | None,
    task_type: str,
    delete_original: bool,
    analysis_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_dirs()
    scene_id = f"cog-{uuid.uuid4().hex[:12]}"
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    safe_name = slugify(Path(metadata.get("name") or source_path.stem).stem)
    cog_path = COG_DIR / f"{scene_id}-{safe_name}.tif"
    task = {
        "id": task_id,
        "type": task_type,
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "sceneId": scene_id,
        "name": str(metadata.get("name") or source_path.stem),
        "fileName": str(metadata.get("fileName") or source_path.name),
        "sourcePath": str(source_path.resolve()),
        "cogPath": str(cog_path.resolve()),
        "satellite": str(metadata.get("satellite") or ""),
        "sensor": str(metadata.get("sensor") or ""),
        "capturedAt": str(metadata.get("capturedAt") or ""),
        "resolution": str(metadata.get("resolution") or ""),
        "projectId": str(metadata.get("projectId") or ""),
        "areaCode": str(metadata.get("areaCode") or ""),
        "allowedRoles": split_tokens(metadata.get("allowedRoles")),
        "allowedUsers": split_tokens(metadata.get("allowedUsers")),
        "assetType": str(metadata.get("assetType") or "orthophoto"),
        "missionId": str(metadata.get("missionId") or ""),
        "linkedBlockCodes": split_tokens(metadata.get("linkedBlockCodes")),
        "processingStage": str(metadata.get("processingStage") or "ready"),
        "analysisContext": {
            "user": str((analysis_context or {}).get("user") or ""),
            "roles": sorted((analysis_context or {}).get("roles") or []),
            "projects": sorted((analysis_context or {}).get("projects") or []),
            "areas": sorted((analysis_context or {}).get("areas") or []),
            "principalType": str((analysis_context or {}).get("principalType") or "user"),
        },
        "bounds": fallback_bounds,
        "deleteOriginalOnSceneDelete": delete_original,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    task["events"] = [
        {
            "at": task["createdAt"],
            "status": "queued",
            "progress": 0,
            "message": "Queued",
        }
    ]
    upsert_task(task)
    TASK_EXECUTOR.submit(run_conversion_task, task_id)
    return task


def point_cloud_outputs(values: list[str] | None) -> list[str]:
    outputs = sorted({str(value).strip().lower() for value in (values or []) if str(value).strip()})
    unsupported = [value for value in outputs if value not in {"copc", "3dtiles"}]
    if unsupported:
        raise HTTPException(status_code=422, detail=f"Unsupported point-cloud outputs: {', '.join(unsupported)}")
    if not outputs:
        raise HTTPException(status_code=422, detail="At least one point-cloud output is required")
    return outputs


def point_cloud_session_dir(session_id: str) -> Path:
    if not re.fullmatch(r"pc-upload-[a-f0-9]{12}", session_id):
        raise HTTPException(status_code=404, detail="Point-cloud upload session not found")
    return (POINT_CLOUD_UPLOAD_SESSION_DIR / session_id).resolve()


def point_cloud_session_manifest_path(session_id: str) -> Path:
    return point_cloud_session_dir(session_id) / "session.json"


def load_point_cloud_session(session_id: str) -> dict[str, Any]:
    path = point_cloud_session_manifest_path(session_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Point-cloud upload session not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail="Point-cloud upload session is corrupted") from exc


def save_point_cloud_session(session: dict[str, Any]) -> None:
    path = point_cloud_session_manifest_path(str(session["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def public_point_cloud_session(session: dict[str, Any]) -> dict[str, Any]:
    files = []
    uploaded_total = 0
    expected_total = 0
    for item in session.get("files") or []:
        expected = int(item.get("size") or 0)
        uploaded = min(expected, int(item.get("uploadedBytes") or 0))
        expected_total += expected
        uploaded_total += uploaded
        files.append(
            {
                "index": item.get("index"),
                "name": item.get("name"),
                "size": expected,
                "chunkSize": item.get("chunkSize"),
                "totalChunks": item.get("totalChunks"),
                "receivedChunks": item.get("receivedChunks") or [],
                "uploadedBytes": uploaded,
            }
        )
    return {
        "id": session.get("id"),
        "name": session.get("name"),
        "missionId": session.get("missionId"),
        "capturedAt": session.get("capturedAt"),
        "status": session.get("status"),
        "outputs": session.get("outputs") or [],
        "files": files,
        "uploadedBytes": uploaded_total,
        "totalBytes": expected_total,
        "progress": round(uploaded_total / expected_total * 100, 2) if expected_total else 0,
        "taskId": session.get("taskId") or "",
        "createdAt": session.get("createdAt"),
        "updatedAt": session.get("updatedAt"),
    }


def require_point_cloud_session_access(
    session: dict[str, Any],
    context: dict[str, Any],
) -> None:
    owner = str(session.get("createdBy") or "").strip()
    current_user = str(context.get("user") or "").strip()
    if owner and owner != current_user and not platform_has_admin_role(platform_auth_context(context)):
        raise HTTPException(status_code=403, detail="Point-cloud upload session belongs to another user")


def point_cloud_file_lock(session_id: str, file_index: int) -> threading.RLock:
    key = f"{session_id}:{file_index}"
    with POINT_CLOUD_SESSION_LOCK:
        return POINT_CLOUD_FILE_LOCKS.setdefault(key, threading.RLock())


def resolve_point_cloud_import_sources(path_value: str, *, recursive: bool) -> list[Path]:
    if not path_value.strip():
        raise HTTPException(status_code=400, detail="Point-cloud import path is required")
    source = Path(path_value).expanduser()
    if not source.is_absolute():
        source = INBOX_DIR / source
    resolved = source.resolve()
    import_root = next((directory.resolve() for directory in IMPORT_DIRS if is_relative_to(resolved, directory.resolve())), None)
    if import_root is None:
        raise HTTPException(status_code=403, detail="Point-cloud path is outside REMOTE_SENSING_IMPORT_DIRS")
    if any(part.startswith(".") for part in resolved.relative_to(import_root).parts):
        raise HTTPException(status_code=422, detail="Hidden point-cloud working directories cannot be registered")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Point-cloud import path not found")
    if resolved.is_file():
        candidates = [resolved]
    else:
        iterator = resolved.rglob("*") if recursive else resolved.glob("*")
        candidates = [item for item in iterator if item.is_file()]
    result = sorted({
        item.resolve()
        for item in candidates
        if item.suffix.lower() in SUPPORTED_POINT_CLOUD_EXTENSIONS
        and is_relative_to(item.resolve(), import_root)
        and not any(part.startswith(".") for part in item.resolve().relative_to(import_root).parts)
    })
    if not result:
        raise HTTPException(status_code=422, detail="Import path does not contain LAS/LAZ files")
    if len(result) > 500:
        raise HTTPException(status_code=422, detail="One point-cloud dataset cannot contain more than 500 files")
    return result


def resolve_3d_tileset_import_root(path_value: str) -> Path:
    if not path_value.strip():
        raise HTTPException(status_code=400, detail="3D Tiles import path is required")
    source = Path(path_value).expanduser()
    if not source.is_absolute():
        source = INBOX_DIR / source
    resolved = source.resolve()
    import_root = next(
        (directory.resolve() for directory in IMPORT_DIRS if is_relative_to(resolved, directory.resolve())),
        None,
    )
    if import_root is None:
        raise HTTPException(status_code=403, detail="3D Tiles path is outside REMOTE_SENSING_IMPORT_DIRS")
    if any(part.startswith(".") for part in resolved.relative_to(import_root).parts):
        raise HTTPException(status_code=422, detail="Hidden 3D Tiles working directories cannot be registered")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="3D Tiles import path not found")
    root_path = (resolved / "tileset.json").resolve() if resolved.is_dir() else resolved
    if root_path.name.lower() != "tileset.json" or not root_path.is_file():
        raise HTTPException(status_code=422, detail="Select a 3D Tiles directory or its root tileset.json")
    if not is_relative_to(root_path, import_root):
        raise HTTPException(status_code=403, detail="3D Tiles root resolves outside REMOTE_SENSING_IMPORT_DIRS")
    return root_path


def build_registered_tileset_scene_record(
    scene_id: str,
    root_path: Path,
    metadata: dict[str, Any],
    tileset: dict[str, Any],
) -> dict[str, Any]:
    content_type = str(tileset.get("contentType") or "3dtiles")
    asset_type = "pointcloud" if content_type == "pnts" else "oblique3d"
    formats = dict(tileset.get("formats") or {})
    timestamp = now_iso()
    return {
        "id": scene_id,
        "source": "server",
        "storage": "DJI 3D Tiles",
        "name": str(metadata.get("name") or root_path.parent.name or scene_id).strip(),
        "fileName": "tileset.json",
        "fileType": "application/json",
        "size": int(tileset.get("totalSize") or 0),
        "originalSize": int(tileset.get("totalSize") or 0),
        "satellite": "",
        "sensor": "DJI Terra",
        "capturedAt": str(metadata.get("capturedAt") or "").strip(),
        "projectId": str(metadata.get("projectId") or "").strip(),
        "areaCode": str(metadata.get("areaCode") or "").strip(),
        "allowedRoles": split_tokens(metadata.get("allowedRoles")),
        "allowedUsers": split_tokens(metadata.get("allowedUsers")),
        "assetType": asset_type,
        "missionId": str(metadata.get("missionId") or "").strip(),
        "linkedBlockCodes": split_tokens(metadata.get("linkedBlockCodes")),
        "processingStage": "coverage-review",
        "resolution": "",
        "bounds": tileset["bounds"],
        "crs": tileset["crs"],
        "width": 0,
        "height": 0,
        "bands": 0,
        "dtype": content_type,
        "pointCount": int(tileset.get("pointCount") or 0),
        "pointCloudFileCount": int(tileset.get("contentFileCount") or 0),
        "tilesetCount": int(tileset.get("tilesetCount") or 0),
        "tileCount": int(tileset.get("tileCount") or 0),
        "tileFormats": formats,
        "tilesetAssetVersions": list(tileset.get("assetVersions") or []),
        "tilesetContentType": content_type,
        "tilesetSource": "dji-terra",
        "tilesetVersionNormalized": bool(tileset.get("normalizesDjiVersion")),
        "nativeBounds": list(tileset.get("nativeBounds") or []),
        "tilesetPath": catalog_path(root_path),
        "deleteOriginalOnSceneDelete": False,
        "opacity": 1.0,
        "visible": True,
        "transferStatus": "tileset-ready",
        "deliveryStatus": "pending",
        "deliveryComment": "",
        "deliveredAt": None,
        "deliveredBy": "",
        "deliveryEvents": [],
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


def run_3d_tileset_registration_task(task_id: str) -> None:
    if find_task_record(task_id).get("status") == "canceled":
        return
    task = update_task(
        task_id,
        status="running",
        progress=5,
        message="Validating DJI 3D Tiles directory",
        startedAt=now_iso(),
    )
    root_path = Path(str(task.get("sourcePath") or "")).resolve()
    scene_id = str(task["sceneId"])
    try:
        tileset = inspect_3d_tileset(root_path)
        update_task(task_id, progress=85, message="Matching 3D footprint to forest blocks")
        scene = build_registered_tileset_scene_record(
            scene_id,
            root_path,
            {
                "name": task.get("name") or scene_id,
                "missionId": task.get("missionId") or "",
                "capturedAt": task.get("capturedAt") or "",
                "projectId": task.get("projectId") or "",
                "areaCode": task.get("areaCode") or "",
                "allowedRoles": task.get("allowedRoles") or [],
                "allowedUsers": task.get("allowedUsers") or [],
                "linkedBlockCodes": task.get("linkedBlockCodes") or [],
            },
            tileset,
        )
        scene = apply_scene_coverage_analysis(
            scene,
            {
                "geometry": tileset["footprint"],
                "bounds": tileset["bounds"],
                "sourceCrs": tileset["crs"],
            },
            dict(task.get("analysisContext") or {}),
        )
        save_scene(scene)
        update_task(
            task_id,
            status="completed",
            progress=100,
            message="DJI 3D Tiles is ready for coverage confirmation",
            scene=scene,
            completedAt=now_iso(),
        )
    except Exception as exc:
        update_task(task_id, status="failed", progress=100, message=str(exc), failedAt=now_iso())


def create_3d_tileset_registration_task(
    root_path: Path,
    metadata: dict[str, Any],
    *,
    analysis_context: dict[str, Any],
) -> dict[str, Any]:
    ensure_dirs()
    scene_id = f"tiles-{uuid.uuid4().hex[:12]}"
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    timestamp = now_iso()
    task = {
        "id": task_id,
        "type": "3dtiles-register",
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "sceneId": scene_id,
        "name": str(metadata.get("name") or root_path.parent.name or scene_id),
        "fileName": "tileset.json",
        "sourcePath": str(root_path.resolve()),
        "assetType": "oblique3d",
        "missionId": str(metadata.get("missionId") or ""),
        "capturedAt": str(metadata.get("capturedAt") or ""),
        "projectId": str(metadata.get("projectId") or ""),
        "areaCode": str(metadata.get("areaCode") or ""),
        "allowedRoles": split_tokens(metadata.get("allowedRoles")),
        "allowedUsers": split_tokens(metadata.get("allowedUsers")),
        "linkedBlockCodes": split_tokens(metadata.get("linkedBlockCodes")),
        "analysisContext": {
            "user": str(analysis_context.get("user") or ""),
            "roles": sorted(analysis_context.get("roles") or []),
            "projects": sorted(analysis_context.get("projects") or []),
            "areas": sorted(analysis_context.get("areas") or []),
            "principalType": str(analysis_context.get("principalType") or "user"),
        },
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "events": [{"at": timestamp, "status": "queued", "progress": 0, "message": "Queued"}],
    }
    upsert_task(task)
    TASK_EXECUTOR.submit(run_3d_tileset_registration_task, task_id)
    return task


def build_point_cloud_scene_record(
    scene_id: str,
    dataset_dir: Path,
    source_paths: list[Path],
    metadata: dict[str, Any],
    point_cloud: dict[str, Any],
    outputs: list[str],
    delete_original: bool,
) -> dict[str, Any]:
    copc_path = dataset_dir / "dataset.copc.laz"
    tiles_path = dataset_dir / "3dtiles" / "tileset.json"
    size = sum(path.stat().st_size for path in source_paths if path.exists())
    return {
        "id": scene_id,
        "source": "server",
        "storage": "+".join(value.upper() for value in outputs),
        "name": str(metadata.get("name") or scene_id).strip(),
        "fileName": f"{slugify(str(metadata.get('name') or scene_id))}.pointcloud",
        "fileType": "application/vnd.las",
        "size": size,
        "originalSize": size,
        "satellite": "",
        "sensor": "LiDAR",
        "capturedAt": str(metadata.get("capturedAt") or "").strip(),
        "projectId": str(metadata.get("projectId") or "").strip(),
        "areaCode": str(metadata.get("areaCode") or "").strip(),
        "allowedRoles": split_tokens(metadata.get("allowedRoles")),
        "allowedUsers": split_tokens(metadata.get("allowedUsers")),
        "assetType": "pointcloud",
        "missionId": str(metadata.get("missionId") or "").strip(),
        "linkedBlockCodes": split_tokens(metadata.get("linkedBlockCodes")),
        "processingStage": "coverage-review",
        "resolution": "",
        "bounds": point_cloud["bounds"],
        "crs": point_cloud["crs"],
        "width": 0,
        "height": 0,
        "bands": 0,
        "dtype": "pointcloud",
        "pointCount": point_cloud["pointCount"],
        "pointCloudFileCount": point_cloud["fileCount"],
        "pointCloudVersions": point_cloud["versions"],
        "pointCloudFormats": point_cloud["pointFormats"],
        "nativeBounds": point_cloud["nativeBounds"],
        "pointCloudFiles": point_cloud["files"],
        "pointCloudSourcePaths": [catalog_path(path) for path in source_paths],
        "copcPath": catalog_path(copc_path) if "copc" in outputs else "",
        "tilesetPath": catalog_path(tiles_path) if "3dtiles" in outputs else "",
        "deleteOriginalOnSceneDelete": delete_original,
        "opacity": 1.0,
        "visible": True,
        "transferStatus": "pointcloud-ready",
        "deliveryStatus": "pending",
        "deliveryComment": "",
        "deliveredAt": None,
        "deliveredBy": "",
        "deliveryEvents": [],
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }


def run_point_cloud_conversion_task(task_id: str) -> None:
    if find_task_record(task_id).get("status") == "canceled":
        return
    task = update_task(task_id, status="running", progress=5, message="Validating LAS/LAZ headers", startedAt=now_iso())
    source_paths = [Path(value).resolve() for value in task.get("sourcePaths") or []]
    scene_id = str(task["sceneId"])
    dataset_dir = Path(str(task["datasetPath"])).resolve()
    delete_original = bool(task.get("deleteOriginalOnSceneDelete"))
    outputs = point_cloud_outputs(task.get("outputs") or [])
    try:
        point_cloud = point_cloud_collection_metadata(source_paths)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        if delete_original and not bool(task.get("sourcesOwned")):
            owned_dir = dataset_dir / "sources"
            owned_dir.mkdir(parents=True, exist_ok=True)
            owned_paths: list[Path] = []
            for index, source_path in enumerate(source_paths):
                target = owned_dir / f"{index:04d}-{slugify(source_path.name)}"
                if source_path != target:
                    shutil.move(str(source_path), str(target))
                owned_paths.append(target)
            source_paths = owned_paths
            update_task(task_id, sourcePaths=[str(path) for path in source_paths], sourcesOwned=True)
        if "copc" in outputs:
            update_task(task_id, progress=25, message="Converting point cloud to COPC")
            copc_path = dataset_dir / "dataset.copc.laz"
            if copc_path.exists():
                copc_path.unlink()
            convert_point_cloud_to_copc(
                source_paths,
                copc_path,
                pdal_executable=POINT_CLOUD_PDAL_EXECUTABLE,
            )
        if "3dtiles" in outputs:
            update_task(task_id, progress=65, message="Converting point cloud to 3D Tiles")
            tiles_dir = dataset_dir / "3dtiles"
            if tiles_dir.exists():
                shutil.rmtree(tiles_dir)
            convert_point_cloud_to_3dtiles(
                source_paths,
                tiles_dir,
                py3dtiles_executable=POINT_CLOUD_3DTILES_EXECUTABLE,
            )
        update_task(task_id, progress=90, message="Matching point-cloud footprint to forest blocks")
        metadata = {
            "name": task.get("name") or scene_id,
            "missionId": task.get("missionId") or "",
            "capturedAt": task.get("capturedAt") or "",
            "projectId": task.get("projectId") or "",
            "areaCode": task.get("areaCode") or "",
            "allowedRoles": task.get("allowedRoles") or [],
            "allowedUsers": task.get("allowedUsers") or [],
            "linkedBlockCodes": task.get("linkedBlockCodes") or [],
        }
        scene = build_point_cloud_scene_record(
            scene_id,
            dataset_dir,
            source_paths,
            metadata,
            point_cloud,
            outputs,
            delete_original,
        )
        scene = apply_scene_coverage_analysis(
            scene,
            {
                "geometry": point_cloud["footprint"],
                "bounds": point_cloud["bounds"],
                "sourceCrs": point_cloud["crs"],
            },
            dict(task.get("analysisContext") or {}),
        )
        update_task(task_id, progress=96, message="Writing point-cloud catalog")
        save_scene(scene)
        update_task(
            task_id,
            status="completed",
            progress=100,
            message="Point-cloud dataset is ready for coverage confirmation",
            scene=scene,
            completedAt=now_iso(),
        )
    except Exception as exc:
        update_task(task_id, status="failed", progress=100, message=str(exc), failedAt=now_iso())


def create_point_cloud_conversion_task(
    source_paths: list[Path],
    metadata: dict[str, Any],
    *,
    outputs: list[str],
    task_type: str,
    delete_original: bool,
    analysis_context: dict[str, Any],
) -> dict[str, Any]:
    ensure_dirs()
    scene_id = f"pc-{uuid.uuid4().hex[:12]}"
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    timestamp = now_iso()
    task = {
        "id": task_id,
        "type": task_type,
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "sceneId": scene_id,
        "name": str(metadata.get("name") or scene_id),
        "fileName": f"{len(source_paths)} LAS/LAZ files",
        "sourcePaths": [str(path.resolve()) for path in source_paths],
        "datasetPath": str((POINT_CLOUD_DIR / scene_id).resolve()),
        "assetType": "pointcloud",
        "missionId": str(metadata.get("missionId") or ""),
        "capturedAt": str(metadata.get("capturedAt") or ""),
        "projectId": str(metadata.get("projectId") or ""),
        "areaCode": str(metadata.get("areaCode") or ""),
        "allowedRoles": split_tokens(metadata.get("allowedRoles")),
        "allowedUsers": split_tokens(metadata.get("allowedUsers")),
        "linkedBlockCodes": split_tokens(metadata.get("linkedBlockCodes")),
        "outputs": point_cloud_outputs(outputs),
        "deleteOriginalOnSceneDelete": delete_original,
        "analysisContext": {
            "user": str(analysis_context.get("user") or ""),
            "roles": sorted(analysis_context.get("roles") or []),
            "projects": sorted(analysis_context.get("projects") or []),
            "areas": sorted(analysis_context.get("areas") or []),
            "principalType": str(analysis_context.get("principalType") or "user"),
        },
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "events": [{"at": timestamp, "status": "queued", "progress": 0, "message": "Queued"}],
    }
    upsert_task(task)
    TASK_EXECUTOR.submit(run_point_cloud_conversion_task, task_id)
    return task


def find_task_record(task_id: str) -> dict[str, Any]:
    for task in load_tasks():
        if str(task.get("id")) == str(task_id):
            return task
    raise HTTPException(status_code=404, detail="Task not found")


def retry_failed_conversion_task(task_id: str) -> dict[str, Any]:
    original = find_task_record(task_id)
    if original.get("status") != "failed":
        raise HTTPException(status_code=400, detail="Only failed tasks can be retried")

    is_tileset_registration = str(original.get("type") or "") == "3dtiles-register"
    is_point_cloud = str(original.get("assetType") or "") == "pointcloud"
    if is_tileset_registration:
        source_path = Path(str(original.get("sourcePath") or "")).resolve()
        if not source_path.is_file():
            raise HTTPException(status_code=400, detail="Original 3D Tiles root is no longer available")
    elif is_point_cloud:
        source_paths = [Path(str(value)).resolve() for value in original.get("sourcePaths") or []]
        if not source_paths or any(not path.exists() for path in source_paths):
            raise HTTPException(status_code=400, detail="Original point-cloud source files are no longer available")
        source_path = None
    else:
        source_path = Path(str(original.get("sourcePath") or "")).resolve()
        if not source_path.exists():
            raise HTTPException(status_code=400, detail="Original source file is no longer available")

    timestamp = now_iso()
    retry_attempt = int(original.get("retryAttempt") or 0) + 1
    retry_task = {
        **original,
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "status": "queued",
        "progress": 0,
        "message": "Queued retry",
        "retryOf": original.get("id"),
        "retryAttempt": retry_attempt,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    if source_path is not None:
        retry_task["sourcePath"] = str(source_path)
    for key in ["startedAt", "completedAt", "failedAt", "scene"]:
        retry_task.pop(key, None)
    retry_task["events"] = [
        {
            "at": timestamp,
            "status": "queued",
            "progress": 0,
            "message": f"Retry queued from {original.get('id')}",
        }
    ]
    upsert_task(retry_task)
    if is_tileset_registration:
        runner = run_3d_tileset_registration_task
    elif is_point_cloud:
        runner = run_point_cloud_conversion_task
    else:
        runner = run_conversion_task
    TASK_EXECUTOR.submit(runner, retry_task["id"])
    return retry_task


def recover_interrupted_tasks() -> None:
    tasks = load_tasks()
    changed = False
    for task in tasks:
        if task.get("status") in {"queued", "running"}:
            task["status"] = "failed"
            task["progress"] = 100
            task["message"] = "Interrupted by service restart; please submit again"
            task["updatedAt"] = now_iso()
            task["failedAt"] = now_iso()
            changed = True
    if changed:
        save_tasks(tasks)


def mount_optional_titiler() -> bool:
    try:
        from titiler.core.factory import TilerFactory

        cog = TilerFactory()
        app.include_router(cog.router, prefix="/titiler", tags=["TiTiler"])
        return True
    except Exception as exc:
        app.state.titiler_error = str(exc)
        return False


try:
    recover_interrupted_tasks()
except Exception as exc:
    record_startup_error("imagery_task_recovery_failed", "影像任务恢复失败", exc)
try:
    schedule_tianditu_startup_prewarm()
except Exception as exc:
    app.state.tianditu_prewarm_error = str(exc)
TITILER_MOUNTED = mount_optional_titiler()


REMOTE_SENSING_POSTGIS_TABLES = ["remote_sensing_scenes", "remote_sensing_tasks"]
def remote_sensing_catalog_health() -> dict[str, Any]:
    if use_mysql_catalog():
        try:
            with mysql_catalog_connect() as conn:
                with conn.cursor() as cur:
                    placeholders = ", ".join(["%s"] * len(REMOTE_SENSING_MYSQL_TABLES))
                    cur.execute(
                        "SELECT table_name FROM information_schema.tables "
                        f"WHERE table_schema = DATABASE() AND table_name IN ({placeholders})",
                        tuple(REMOTE_SENSING_MYSQL_TABLES),
                    )
                    existing = {str(row[0]) for row in cur.fetchall()}
        except Exception as exc:
            return {
                "backend": "mysql",
                "mysqlEnabled": True,
                "postgisEnabled": False,
                "reachable": False,
                "schemaReady": False,
                "missingTables": REMOTE_SENSING_MYSQL_TABLES,
                "error": str(exc),
            }
        missing_tables = [table for table in REMOTE_SENSING_MYSQL_TABLES if table not in existing]
        return {
            "backend": "mysql",
            "mysqlEnabled": True,
            "postgisEnabled": False,
            "reachable": True,
            "schemaReady": not missing_tables,
            "missingTables": missing_tables,
            "error": "",
        }
    if not use_postgis_catalog():
        return {
            "backend": "json",
            "mysqlEnabled": False,
            "postgisEnabled": False,
            "reachable": True,
            "schemaReady": True,
            "missingTables": [],
            "error": "",
        }
    try:
        with postgis_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT "
                    + ", ".join(f"to_regclass('public.{table}')" for table in REMOTE_SENSING_POSTGIS_TABLES)
                )
                row = cur.fetchone() or ()
    except Exception as exc:
        return {
            "backend": "postgis",
            "mysqlEnabled": False,
            "postgisEnabled": True,
            "reachable": False,
            "schemaReady": False,
            "missingTables": REMOTE_SENSING_POSTGIS_TABLES,
            "error": str(exc),
        }

    missing_tables = [
        table
        for table, value in zip(REMOTE_SENSING_POSTGIS_TABLES, row)
        if not value
    ]
    return {
        "backend": "postgis",
        "mysqlEnabled": False,
        "postgisEnabled": True,
        "reachable": True,
        "schemaReady": not missing_tables,
        "missingTables": missing_tables,
        "error": "",
    }


def is_deleted_record(record: dict[str, Any]) -> bool:
    return bool(record.get("deletedAt") or record.get("deleted_at"))


def count_active_records(records: list[dict[str, Any]]) -> dict[str, int]:
    deleted_count = sum(1 for record in records if is_deleted_record(record))
    return {
        "recordCount": len(records) - deleted_count,
        "deletedCount": deleted_count,
        "totalCount": len(records),
    }


def path_writable(path: Path) -> bool:
    target = path if path.is_dir() else path.parent
    return target.exists() and os.access(target, os.W_OK)


def directory_inventory(key: str, path: Path) -> dict[str, Any]:
    return {
        "key": key,
        "path": str(path),
        "exists": path.exists(),
        "writable": path.exists() and path.is_dir() and os.access(path, os.W_OK),
    }


def json_dataset_inventory(key: str, path: Path) -> dict[str, Any]:
    error = ""
    try:
        records = load_json_records(path)
    except Exception as exc:
        records = []
        error = str(exc)
    return {
        "key": key,
        "path": str(path),
        "exists": path.exists(),
        "writable": path_writable(path),
        "error": error,
        **count_active_records(records),
    }


def named_json_collection_inventory(key: str, path: Path, collection_key: str) -> dict[str, Any]:
    error = ""
    try:
        if not path.exists():
            records: list[dict[str, Any]] = []
        else:
            payload = json.loads(path.read_text(encoding="utf-8") or "{}")
            raw_records = payload.get(collection_key, []) if isinstance(payload, dict) else payload
            records = [record for record in raw_records if isinstance(record, dict)] if isinstance(raw_records, list) else []
    except Exception as exc:
        records = []
        error = str(exc)
    return {
        "key": key,
        "path": str(path),
        "exists": path.exists(),
        "writable": path_writable(path),
        "error": error,
        **count_active_records(records),
    }


def business_inventory() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    business_dir = get_settings().data_dir / "business"
    modules = [
        json_dataset_inventory(path.stem, path)
        for path in sorted(business_dir.glob("*.json"))
        if path.is_file()
    ]
    return (
        {
            "key": "businessRecords",
            "path": str(business_dir),
            "exists": business_dir.exists(),
            "writable": path_writable(business_dir),
            "error": "; ".join(item["error"] for item in modules if item["error"]),
            "recordCount": sum(item["recordCount"] for item in modules),
            "deletedCount": sum(item["deletedCount"] for item in modules),
            "totalCount": sum(item["totalCount"] for item in modules),
            "moduleCount": len(modules),
        },
        modules,
    )


def smart_bamboo_data_inventory() -> dict[str, Any]:
    data_dir = get_settings().data_dir
    business_summary, business_modules = business_inventory()
    datasets = [
        json_dataset_inventory("forestBlocks", forest_blocks_json_path()),
        json_dataset_inventory("forestBlockVersions", forest_block_versions_json_path()),
        json_dataset_inventory("forestRights", forest_rights_json_path()),
        json_dataset_inventory("forestRightVersions", forest_right_versions_json_path()),
        json_dataset_inventory("mapLayers", map_layers_json_path()),
        json_dataset_inventory("adminRoles", admin_roles_json_path()),
        json_dataset_inventory("adminUsers", admin_users_json_path()),
        json_dataset_inventory("importBatches", import_batches_json_path()),
        business_summary,
    ]
    return {
        "dataDir": directory_inventory("dataDir", data_dir),
        "coreDirectories": [
            directory_inventory("forestBlocks", data_dir / "forest-blocks"),
            directory_inventory("forestRights", data_dir / "forest-rights"),
            directory_inventory("business", data_dir / "business"),
            directory_inventory("mapLayers", data_dir / "map-layers"),
            directory_inventory("admin", data_dir / "admin"),
            directory_inventory("imports", data_dir / "imports"),
        ],
        "datasets": datasets,
        "businessModules": business_modules,
    }


def imagery_data_inventory() -> dict[str, Any]:
    return {
        "catalog": named_json_collection_inventory("sceneCatalog", CATALOG_PATH, "scenes"),
        "tasks": named_json_collection_inventory("imageryTasks", TASKS_PATH, "tasks"),
        "uploadDir": directory_inventory("uploads", UPLOAD_DIR),
        "cogDir": directory_inventory("cogs", COG_DIR),
        "inboxDir": directory_inventory("inbox", INBOX_DIR),
        "importDirs": [directory_inventory(f"importDir{i + 1}", path) for i, path in enumerate(IMPORT_DIRS)],
    }


CORE_API_READINESS_TARGETS: list[dict[str, str]] = [
    {
        "key": "forest_blocks",
        "group": "spatial-rights",
        "groupLabel": "空间与权属",
        "label": "Forest block ledger",
        "method": "GET",
        "path": "/api/forest-blocks",
        "permission": "forest.blocks.view",
    },
    {
        "key": "forest_block_aggregates",
        "group": "spatial-rights",
        "groupLabel": "空间与权属",
        "label": "Forest block map aggregates",
        "method": "GET",
        "path": "/api/map/forest-blocks/aggregates",
        "permission": "forest.blocks.view",
    },
    {
        "key": "forest_rights",
        "group": "spatial-rights",
        "groupLabel": "空间与权属",
        "label": "Forest rights archive ledger",
        "method": "GET",
        "path": "/api/forest-rights",
        "permission": "forest.rights.view",
    },
    {
        "key": "map_layers",
        "group": "spatial-rights",
        "groupLabel": "空间与权属",
        "label": "Map layer publishing",
        "method": "GET",
        "path": "/api/map-layers",
        "permission": "map.layers.view",
    },
    {
        "key": "dictionaries",
        "group": "data-governance",
        "groupLabel": "数据治理",
        "label": "Dictionary catalog",
        "method": "GET",
        "path": "/api/dictionaries",
        "permission": "system.dictionaries.view",
    },
    {
        "key": "dictionary_options",
        "group": "data-governance",
        "groupLabel": "数据治理",
        "label": "Dictionary form options",
        "method": "GET",
        "path": "/api/dictionary-options/{type_code}",
        "permission": "authenticated",
    },
    {
        "key": "import_batches",
        "group": "imports",
        "groupLabel": "成果入库",
        "label": "Forest block import batches",
        "method": "GET",
        "path": "/api/imports/forest-blocks/batches",
        "permission": "imports.forestBlocks.view",
    },
    {
        "key": "import_batch_targets",
        "group": "imports",
        "groupLabel": "成果入库",
        "label": "Paginated import batch targets",
        "method": "GET",
        "path": "/api/imports/{batch_id}/targets",
        "permission": "imports.forestBlocks.view",
    },
    {
        "key": "delivery_packages",
        "group": "imports",
        "groupLabel": "成果入库",
        "label": "Delivery package ledger",
        "method": "GET",
        "path": "/api/imports/forest-blocks/delivery-packages",
        "permission": "imports.forestBlocks.view",
    },
    {
        "key": "import_workflow_summary",
        "group": "imports",
        "groupLabel": "成果入库",
        "label": "Import workflow summary",
        "method": "GET",
        "path": "/api/imports/forest-blocks/workflow-summary",
        "permission": "imports.forestBlocks.view",
    },
    {
        "key": "import_operation_queue",
        "group": "imports",
        "groupLabel": "成果入库",
        "label": "Import operation queue",
        "method": "GET",
        "path": "/api/imports/forest-blocks/operation-queue",
        "permission": "imports.forestBlocks.view",
    },
    {
        "key": "import_quality_issues",
        "group": "imports",
        "groupLabel": "成果入库",
        "label": "Import quality issue ledger",
        "method": "GET",
        "path": "/api/imports/forest-blocks/quality-issues",
        "permission": "imports.forestBlocks.view",
    },
    {
        "key": "dashboard_satellite_track",
        "group": "dashboard",
        "groupLabel": "大屏展示",
        "label": "Dashboard satellite summary",
        "method": "GET",
        "path": "/api/dashboard/satellite-track",
        "permission": "公开只读",
    },
    {
        "key": "dashboard_workflow_status",
        "group": "dashboard",
        "groupLabel": "大屏展示",
        "label": "Dashboard workflow status",
        "method": "GET",
        "path": "/api/dashboard/workflow-status",
        "permission": "公开只读",
    },
    {
        "key": "imagery_scenes",
        "group": "imagery",
        "groupLabel": "影像管理",
        "label": "Imagery scene catalog",
        "method": "GET",
        "path": "/api/scenes",
        "permission": "imagery.scenes.view",
    },
    {
        "key": "imagery_workflow_summary",
        "group": "imagery",
        "groupLabel": "影像管理",
        "label": "Imagery workflow summary",
        "method": "GET",
        "path": "/api/scenes/workflow-summary",
        "permission": "imagery.scenes.view",
    },
    {
        "key": "imagery_operation_queue",
        "group": "imagery",
        "groupLabel": "影像管理",
        "label": "Imagery operation queue",
        "method": "GET",
        "path": "/api/scenes/operation-queue",
        "permission": "imagery.scenes.view",
    },
    {
        "key": "imagery_quality_issues",
        "group": "imagery",
        "groupLabel": "影像管理",
        "label": "Imagery quality issue ledger",
        "method": "GET",
        "path": "/api/scenes/quality-issues",
        "permission": "imagery.scenes.view",
    },
    {
        "key": "permission_catalog",
        "group": "permission-system",
        "groupLabel": "权限系统",
        "label": "Permission catalog",
        "method": "GET",
        "path": "/api/admin/permission-catalog",
        "permission": "system.roles.manage",
    },
    {
        "key": "role_operation_queue",
        "group": "permission-system",
        "groupLabel": "权限系统",
        "label": "Role permission operation queue",
        "method": "GET",
        "path": "/api/admin/roles/operation-queue",
        "permission": "system.roles.manage",
    },
    {
        "key": "user_operation_queue",
        "group": "permission-system",
        "groupLabel": "权限系统",
        "label": "User access operation queue",
        "method": "GET",
        "path": "/api/admin/users/operation-queue",
        "permission": "system.users.manage",
    },
]


def route_methods_by_path() -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {}
    route_contexts = (
        fastapi_iter_route_contexts(app.routes)
        if fastapi_iter_route_contexts is not None
        else app.routes
    )
    for route in route_contexts:
        path = str(getattr(route, "path", "") or "")
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        routes.setdefault(path, set()).update(str(method).upper() for method in methods)
    return routes


def deployment_api_checks() -> list[dict[str, Any]]:
    route_methods = route_methods_by_path()
    checks: list[dict[str, Any]] = []
    for target in CORE_API_READINESS_TARGETS:
        path = target["path"]
        method = target["method"].upper()
        mounted_methods = sorted(route_methods.get(path, set()))
        checks.append(
            {
                **target,
                "method": method,
                "available": method in mounted_methods,
                "mountedMethods": mounted_methods,
            }
        )
    return checks


def readiness_item(
    key: str,
    label: str,
    status: str,
    message: str,
    *,
    section: str = "deployment",
    action_required: str = "",
) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "section": section,
        "message": message,
        "actionRequired": action_required,
    }


def database_readiness_issue(key_prefix: str, label: str, item: dict[str, Any]) -> dict[str, str] | None:
    if not item.get("reachable"):
        return readiness_item(
            f"{key_prefix}_unreachable",
            f"{label}不可达",
            "blocked",
            str(item.get("error") or "数据库连接失败"),
            section="database",
            action_required="检查数据库连接串、容器网络、账号密码和数据库服务状态。",
        )
    if not item.get("schemaReady"):
        return readiness_item(
            f"{key_prefix}_schema_missing",
            f"{label}表结构未就绪",
            "blocked",
            f"缺失表：{', '.join(item.get('missingTables') or []) or '未知'}",
            section="database",
            action_required="执行 schema 初始化或重新启动应用完成表结构创建。",
        )
    return None


def directory_readiness_issue(key: str, label: str, item: dict[str, Any]) -> dict[str, str] | None:
    if not item.get("exists"):
        return readiness_item(
            f"{key}_missing",
            f"{label}不存在",
            "blocked",
            str(item.get("path") or "目录未配置"),
            section="filesystem",
            action_required="创建目录并挂载到应用容器可访问路径。",
        )
    if not item.get("writable"):
        return readiness_item(
            f"{key}_not_writable",
            f"{label}不可写",
            "blocked",
            str(item.get("path") or "目录不可写"),
            section="filesystem",
            action_required="调整目录权限或 Docker volume 挂载权限。",
        )
    return None


PLACEHOLDER_DATABASE_PASSWORDS = {
    "",
    "admin",
    "change-me",
    "change-root-me",
    "mysql",
    "password",
    "root",
    "smart_bamboo_dev",
    "smart_bamboo_root_dev",
}


def placeholder_database_credential_names(database_urls: dict[str, str]) -> list[str]:
    insecure: list[str] = []
    for name, database_url in database_urls.items():
        value = str(database_url or "").strip()
        if not value:
            continue
        parsed = urllib.parse.urlparse(value.replace("mysql+pymysql://", "mysql://", 1))
        if parsed.scheme != "mysql":
            continue
        password = urllib.parse.unquote(parsed.password or "").strip().lower()
        if password in PLACEHOLDER_DATABASE_PASSWORDS:
            insecure.append(str(name))
    return sorted(set(insecure))


def deployment_readiness_summary(deployment: dict[str, Any]) -> dict[str, Any]:
    database = deployment.get("database") or {}
    smart_bamboo = deployment.get("smartBamboo") or {}
    json_data = smart_bamboo.get("jsonData") or {}
    imagery = deployment.get("imagery") or {}
    auth = deployment.get("auth") or {}
    startup_errors = list(getattr(app.state, "startup_errors", []))
    checks: list[dict[str, str]] = []
    blocking_issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    settings = get_settings()
    if settings.human_auth_enabled and os.environ.get("SMART_BAMBOO_DEPLOYMENT_MODE", "development").strip().lower() in {"prod", "production"}:
        storage = human_auth_storage_readiness()
        human_auth_checks = [
            ("human_auth_https_not_required", "HTTPS enforcement", settings.auth_require_https),
            ("human_auth_proxy_headers_untrusted", "Trusted proxy headers", settings.trust_proxy_headers),
            ("human_auth_session_cookie_not_secure", "Secure session cookie", settings.session_cookie_secure),
            ("human_auth_mysql_unreachable", "Human authentication MySQL", storage["reachable"]),
            ("human_auth_credentials_table_missing", "Credential table", storage["credentialTable"]),
            ("human_auth_sessions_table_missing", "Session table", storage["sessionTable"]),
            ("human_auth_active_admin_credential_missing", "Active administrator credential", storage["activeAdminCredential"]),
        ]
        for key, label, passed in human_auth_checks:
            issue = readiness_item(
                key,
                label,
                "pass" if passed else "blocked",
                f"{label} is configured." if passed else f"{label} must be ready before human authentication is enabled.",
                section="security",
            )
            checks.append(issue)
            if not passed:
                blocking_issues.append(issue)
    elif not settings.human_auth_enabled:
        warning = readiness_item(
            "human_auth_pending_https",
            "Human authentication rollout",
            "warning",
            "Human authentication remains disabled until HTTPS verification is complete.",
            section="security",
        )
        checks.append(warning)
        warnings.append(warning)

    platform_database = database.get("platform") or {}
    platform_issue = database_readiness_issue("platform_database", "平台数据库", platform_database)
    checks.append(
        readiness_item(
            "platform_database",
            "平台数据库",
            "blocked" if platform_issue else "pass",
            platform_issue["message"] if platform_issue else "平台数据库连接和表结构正常。",
            section="database",
        )
    )
    if platform_issue:
        blocking_issues.append(platform_issue)

    catalog_database = database.get("remoteSensingCatalog") or {}
    catalog_issue = database_readiness_issue("remote_sensing_catalog", "遥感影像目录库", catalog_database)
    checks.append(
        readiness_item(
            "remote_sensing_catalog",
            "遥感影像目录库",
            "blocked" if catalog_issue else "pass",
            catalog_issue["message"] if catalog_issue else "遥感影像目录库连接和表结构正常。",
            section="database",
        )
    )
    if catalog_issue:
        blocking_issues.append(catalog_issue)

    data_dir_issue = directory_readiness_issue("data_root", "数据根目录", json_data.get("dataDir") or {})
    checks.append(
        readiness_item(
            "data_root",
            "数据根目录",
            "blocked" if data_dir_issue else "pass",
            data_dir_issue["message"] if data_dir_issue else "数据根目录存在且可写。",
            section="filesystem",
        )
    )
    if data_dir_issue:
        blocking_issues.append(data_dir_issue)

    upload_issue = directory_readiness_issue("imagery_upload_dir", "影像上传目录", imagery.get("uploadDir") or {})
    checks.append(
        readiness_item(
            "imagery_upload_dir",
            "影像上传目录",
            "blocked" if upload_issue else "pass",
            upload_issue["message"] if upload_issue else "影像上传目录存在且可写。",
            section="filesystem",
        )
    )
    if upload_issue:
        blocking_issues.append(upload_issue)

    cog_issue = directory_readiness_issue("imagery_cog_dir", "COG 输出目录", imagery.get("cogDir") or {})
    checks.append(
        readiness_item(
            "imagery_cog_dir",
            "COG 输出目录",
            "blocked" if cog_issue else "pass",
            cog_issue["message"] if cog_issue else "COG 输出目录存在且可写。",
            section="filesystem",
        )
    )
    if cog_issue:
        blocking_issues.append(cog_issue)

    import_dirs = list(imagery.get("importDirs") or [])
    import_dir_issues = [
        issue
        for index, item in enumerate(import_dirs, start=1)
        if (issue := directory_readiness_issue(f"imagery_import_dir_{index}", f"影像入库目录 {index}", item))
    ]
    checks.append(
        readiness_item(
            "imagery_import_dirs",
            "影像入库目录",
            "blocked" if import_dir_issues or not import_dirs else "pass",
            "影像入库目录存在且可写。" if import_dirs and not import_dir_issues else "存在未创建或不可写的影像入库目录。",
            section="filesystem",
        )
    )
    blocking_issues.extend(import_dir_issues)

    tianditu_proxy = deployment.get("tiandituProxy") or {}
    if (
        tianditu_proxy.get("enabled")
        and not tianditu_proxy.get("hasServerTk")
        and not tianditu_proxy.get("hasUpstreamProxy")
    ):
        warning = readiness_item(
            "tianditu_server_key_missing",
            "天地图服务端密钥缺失",
            "warning",
            "天地图代理已启用，但服务端没有可用密钥，瓦片请求将失败且无法建立持久缓存。",
            section="basemap",
            action_required="配置 REMOTE_SENSING_TIANDITU_TK，并重建应用容器后验证缓存命中。",
        )
        warnings.append(warning)
        checks.append(warning)
    else:
        checks.append(
            readiness_item(
                "tianditu_server_key",
                "天地图服务端密钥",
                "pass",
                "天地图代理密钥已配置。",
                section="basemap",
            )
        )

    api_checks = list(deployment.get("apiChecks") or [])
    missing_api_checks = [item for item in api_checks if not item.get("available")]
    api_check_keys = [str(item.get("key") or item.get("path") or "") for item in api_checks]
    api_message = (
        f"Core API routes mounted: {', '.join(api_check_keys) or 'none'}."
        if not missing_api_checks
        else f"Missing core API routes: {', '.join(str(item.get('key') or item.get('path')) for item in missing_api_checks)}."
    )
    checks.append(
        readiness_item(
            "core_api_routes",
            "Core API routes",
            "blocked" if missing_api_checks else "pass",
            api_message,
            section="api",
            action_required="Restore missing routers before production deployment." if missing_api_checks else "",
        )
    )
    if missing_api_checks:
        blocking_issues.append(
            readiness_item(
                "core_api_routes_missing",
                "Core API routes missing",
                "blocked",
                api_message,
                section="api",
                action_required="Check router registration and deployment package completeness.",
            )
        )

    if str(smart_bamboo.get("storageBackend") or "") != "mysql" or not smart_bamboo.get("mysqlEnabled"):
        is_json_storage = str(smart_bamboo.get("storageBackend") or "") == "json"
        warning = readiness_item(
            "storage_backend_json" if is_json_storage else "storage_backend_not_mysql",
            "平台存储仍为 JSON" if is_json_storage else "平台存储尚未切换 MySQL",
            "warning",
            "当前可用于开发和演示，百万亩生产数据应切换到 MySQL 8。",
            section="database",
            action_required="配置 SMART_BAMBOO_STORAGE_BACKEND=mysql 和 SMART_BAMBOO_DATABASE_URL。",
        )
        warnings.append(warning)
        checks.append(warning | {"key": "storage_backend", "label": "平台存储模式"})
    else:
        checks.append(readiness_item("storage_backend", "平台存储模式", "pass", "平台存储已启用 MySQL 8。", section="database"))

    if str(catalog_database.get("backend") or "") != "mysql" or not catalog_database.get("mysqlEnabled"):
        warning = readiness_item(
            "catalog_backend_not_mysql",
            "遥感目录尚未切换 MySQL",
            "warning",
            "影像文件可继续保存在 NAS，但目录、任务和发布状态应写入 MySQL 8。",
            section="database",
            action_required="配置 REMOTE_SENSING_CATALOG_BACKEND=mysql 和 REMOTE_SENSING_DATABASE_URL。",
        )
        warnings.append(warning)
        checks.append(warning | {"key": "catalog_backend", "label": "遥感目录存储模式"})
    else:
        checks.append(readiness_item("catalog_backend", "遥感目录存储模式", "pass", "遥感目录与任务已启用 MySQL 8。", section="database"))

    configured_database_urls: dict[str, str] = {}
    if smart_bamboo.get("mysqlEnabled"):
        configured_database_urls["platform"] = os.environ.get("SMART_BAMBOO_DATABASE_URL", "")
    if catalog_database.get("mysqlEnabled"):
        configured_database_urls["catalog"] = os.environ.get("REMOTE_SENSING_DATABASE_URL", "")
    insecure_database_names = placeholder_database_credential_names(configured_database_urls)
    if insecure_database_names:
        warning = readiness_item(
            "database_credentials_default",
            "数据库仍使用默认口令",
            "warning",
            f"以下数据库连接仍使用开发或占位口令：{', '.join(insecure_database_names)}。",
            section="security",
            action_required="修改数据库账号口令，并同步更新数据库连接串后重新部署。",
        )
        warnings.append(warning)
        checks.append(warning | {"key": "database_credentials", "label": "数据库凭据"})
    else:
        checks.append(
            readiness_item(
                "database_credentials",
                "数据库凭据",
                "pass",
                "未检测到已知的开发或占位数据库口令。",
                section="security",
            )
        )

    if not auth.get("required"):
        warning = readiness_item(
            "auth_disabled",
            "接口鉴权未启用",
            "warning",
            "生产部署应启用 API 鉴权，避免后台接口裸露。",
            section="security",
            action_required="配置 REMOTE_SENSING_AUTH_REQUIRED=1 和 REMOTE_SENSING_API_TOKENS。",
        )
        warnings.append(warning)
        checks.append(warning | {"key": "auth_tokens", "label": "接口鉴权"})
    elif not int(auth.get("tokensConfigured") or 0):
        warning = readiness_item(
            "auth_tokens_missing",
            "接口令牌未配置",
            "warning",
            "鉴权已启用但未检测到令牌配置。",
            section="security",
            action_required="配置 REMOTE_SENSING_API_TOKENS。",
        )
        warnings.append(warning)
        checks.append(warning | {"key": "auth_tokens", "label": "接口鉴权"})
    else:
        checks.append(readiness_item("auth_tokens", "接口鉴权", "pass", "接口鉴权与令牌已配置。", section="security"))

    for error in startup_errors:
        blocking_issues.append(
            readiness_item(
                str(error.get("key") or "startup_error"),
                str(error.get("label") or "启动期错误"),
                "blocked",
                str(error.get("message") or ""),
                section="startup",
                action_required="检查应用启动日志并修复初始化错误。",
            )
        )
    checks.append(
        readiness_item(
            "startup_errors",
            "启动期错误",
            "blocked" if startup_errors else "pass",
            f"{len(startup_errors)} 个启动期错误" if startup_errors else "未检测到启动期错误。",
            section="startup",
        )
    )

    status = "blocked" if blocking_issues else "warning" if warnings else "ready"
    return {
        "status": status,
        "blockingIssueCount": len(blocking_issues),
        "warningCount": len(warnings),
        "checks": checks,
        "blockingIssues": blocking_issues,
        "warnings": warnings,
        "generatedAt": now_iso(),
    }


def deployment_health_payload() -> dict[str, Any]:
    platform_health = platform_storage_health()
    catalog_health = remote_sensing_catalog_health()
    api_checks = deployment_api_checks()
    healthy = (
        platform_health["reachable"]
        and platform_health["schemaReady"]
        and catalog_health["reachable"]
        and catalog_health["schemaReady"]
        and all(check.get("available") for check in api_checks)
    )
    dependencies = {
        "rasterio": dependency_status("rasterio"),
        "rio_tiler": dependency_status("rio_tiler"),
        "titiler": dependency_status("titiler"),
        "psycopg": dependency_status("psycopg"),
        "pymysql": dependency_status("pymysql"),
    }
    deployment = {
        "dataDir": str(DATA_DIR),
        "staticDir": str(STATIC_DIR),
        "serveStatic": SERVE_STATIC,
        "corsOrigins": CORS_ORIGINS,
        "importDirs": [str(path) for path in IMPORT_DIRS],
        "taskWorkers": TASK_WORKERS,
        "catalogBackend": "mysql" if use_mysql_catalog() else "postgis" if use_postgis_catalog() else "json",
        "auth": {
            "required": get_settings().auth_required,
            "tokensConfigured": len(token_profiles()),
        },
        "tileCache": cache_stats(),
        "tiandituProxy": tianditu_proxy_config(),
        "geoserver": geoserver_config(),
        "apiChecks": api_checks,
        "database": {
            "platform": platform_health,
            "remoteSensingCatalog": catalog_health,
        },
        "imagery": imagery_data_inventory(),
        "smartBamboo": {
            "storageBackend": get_settings().storage_backend,
            "mysqlEnabled": smart_bamboo_use_mysql(),
            "postgisEnabled": smart_bamboo_use_postgis(),
            "schemaReady": platform_health["schemaReady"],
            "importTuning": {
                "strategy": "incremental-batch",
                "mysqlWriteBatchSize": FOREST_BLOCK_MYSQL_WRITE_BATCH_SIZE,
                "identityLookupBatchSize": FOREST_BLOCK_IDENTITY_LOOKUP_BATCH_SIZE,
                "singleTransaction": True,
                "mysqlReportTargets": "normalized-relational",
                "databaseReportCache": "disabled",
                "mysqlTargetRead": "paginated-relational",
                "mysqlRollback": "targeted-relational",
                "mysqlSceneLink": "insert-select-relational",
                "mysqlSceneCoverage": "aggregate-bounded-samples",
                "mysqlLayerLink": "copy-relational",
                "mysqlLayerTargets": "paginated-summary",
                "mysqlLayerCrud": "targeted-scalar",
                "mysqlBusinessTargets": "paginated-summary",
                "mysqlBusinessCrud": "targeted-scalar",
                "mysqlBusinessDashboard": "aggregate-bounded-rows",
                "mysqlRightTargets": "paginated-summary",
                "mysqlRightCrud": "targeted-scalar",
            },
            "jsonData": smart_bamboo_data_inventory(),
        },
    }
    deployment["readiness"] = deployment_readiness_summary(deployment)
    payload = {
        "ok": healthy,
        "service": "remote-sensing-cog",
        "titilerMounted": TITILER_MOUNTED,
        "titilerError": getattr(app.state, "titiler_error", ""),
        "dependencies": dependencies,
        "deployment": deployment,
    }
    return payload


@app.get("/satellite-config.local.js", include_in_schema=False)
def public_browser_runtime_config() -> Response:
    settings = get_settings()
    service_token_enabled = settings.auth_required and not settings.human_auth_enabled
    dashboard_token = os.environ.get("SMART_BAMBOO_DASHBOARD_TOKEN", "").strip()
    dashboard_profile = token_profiles().get(dashboard_token)
    dashboard_permissions = (
        set(effective_permissions_for_context(dashboard_profile))
        if dashboard_profile is not None
        else set()
    )
    if (
        not service_token_enabled
        or dashboard_profile is None
        or dashboard_profile.user != "dashboard"
        or dashboard_profile.roles != {"viewer"}
        or not dashboard_permissions
        or any(not code.endswith(".view") for code in dashboard_permissions)
    ):
        dashboard_token = ""
    token_line = (
        f"  apiToken: {json.dumps(dashboard_token)},\n" if dashboard_token else ""
    )
    body = (
        "window.SATELLITE_CONFIG = {\n"
        f"  humanLoginEnabled: {str(settings.human_auth_enabled).lower()},\n"
        '  remoteApiBase: "",\n'
        f"{token_line}"
        "  tiandituProxy: true,\n"
        '  tiandituProxyBaseUrl: "",\n'
        "};\n"
    )
    return Response(
        content=body,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/api/health/live", include_in_schema=False)
def health_live() -> Response:
    return JSONResponse(
        content={"ok": True, "status": "live"},
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/api/health")
def health() -> Any:
    payload = deployment_health_payload()
    healthy = bool(payload.get("ok"))
    if not healthy:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/api/deployment/report.json")
def export_deployment_report(request: Request) -> Response:
    context = request_context(request)
    require_admin_permission(platform_auth_context(context), "system.deployment.view")
    payload = deployment_health_payload()
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="deployment-report.json"'},
    )


@app.get("/api/geoserver/config")
def get_geoserver_config(request: Request) -> dict[str, Any]:
    request_context(request)
    return geoserver_config()


@app.get("/api/geoserver/layers")
def get_geoserver_layers(request: Request) -> dict[str, Any]:
    request_context(request)
    return {"layers": fetch_geoserver_layers()}


@app.get("/api/dashboard/satellite-track")
def get_dashboard_satellite_track(request: Request) -> dict[str, Any]:
    request_context(request)
    return satellite_track_dashboard_payload()


def public_dashboard_platform_context() -> AuthContext:
    return AuthContext(
        user="dashboard",
        roles={"admin"},
        projects={"*"},
        areas={"*"},
    )


def public_dashboard_imagery_context() -> dict[str, Any]:
    return {
        "user": "dashboard",
        "roles": {"admin"},
        "projects": {"*"},
        "areas": {"*"},
        "token": "",
    }


def dashboard_delivery_package_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "batchId",
            "packageStatus",
            "deliveryStatus",
            "acceptanceStatus",
            "adminHref",
        )
        if item.get(key) not in {None, ""}
    }


@app.get("/api/dashboard/workflow-status")
def get_dashboard_workflow_status(request: Request) -> dict[str, Any]:
    context = public_dashboard_platform_context()
    deliveries = list_import_delivery_packages(limit=5, offset=0, context=context)
    return {
        "imports": import_workflow_summary(context),
        "imagery": imagery_workflow_summary(request, context_override=public_dashboard_imagery_context()),
        "deliveries": {
            "items": [dashboard_delivery_package_item(item) for item in deliveries.get("items") or []],
            "total": int(deliveries.get("total") or 0),
            "limit": 5,
            "offset": 0,
        },
        "layers": dashboard_map_layers_payload(),
        "generatedAt": now_iso(),
    }


@app.get("/api/scenes")
def list_scenes(
    request: Request,
    q: str = Query(default=""),
    status: str = Query(default=""),
    projectId: str = Query(default=""),
    areaCode: str = Query(default=""),
    bbox: str = Query(default=""),
    published: str = Query(default=""),
    deliveryStatus: str = Query(default=""),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    include_deleted_records = includeDeleted or status == "deleted"
    if include_deleted_records:
        require_imagery_permission(request, IMAGERY_SCENE_RESTORE_PERMISSION)
    include_archived_records = status == "archived"
    if include_archived_records:
        require_imagery_permission(request, IMAGERY_SCENE_ARCHIVE_PERMISSION)
    require_imagery_permission(request, IMAGERY_SCENE_VIEW_PERMISSION)
    query_bbox = parse_query_bounds(bbox)
    scenes = filter_scenes(
        load_catalog(
            q=q,
            status=status,
            project_id=projectId,
            area_code=areaCode,
            bbox=query_bbox,
            include_deleted=include_deleted_records,
        ),
        request_context(request),
        q=q,
        status=status,
        project_id=projectId,
        area_code=areaCode,
        bbox=query_bbox,
        published=published,
        delivery_status=deliveryStatus,
    )
    if not status:
        scenes = [scene for scene in scenes if str(scene.get("status") or "active") != "archived"]
    page = scenes[offset : offset + limit]
    return {
        "total": len(scenes),
        "limit": limit,
        "offset": offset,
        "bbox": query_bbox,
        "scenes": [public_scene(scene, request) for scene in page],
    }


@app.get("/api/scenes/events")
def list_scene_events(
    request: Request,
    q: str = Query(default=""),
    eventType: str = Query(default=""),
    action: str = Query(default=""),
    sceneId: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    require_imagery_permission(request, IMAGERY_SCENE_VIEW_PERMISSION)
    records = list_scene_event_records(
        q=q,
        event_type=eventType,
        action=action,
        scene_id=sceneId,
    )
    page = records[offset : offset + limit]
    return {
        "items": page,
        "total": len(records),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/scenes/events.csv")
def export_scene_events_csv(
    request: Request,
    q: str = Query(default=""),
    eventType: str = Query(default=""),
    action: str = Query(default=""),
    sceneId: str = Query(default=""),
    limit: int = Query(default=1000, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> Response:
    require_imagery_permission(request, IMAGERY_SCENE_EXPORT_PERMISSION)
    records = list_scene_event_records(
        q=q,
        event_type=eventType,
        action=action,
        scene_id=sceneId,
    )
    page = records[offset : offset + limit]
    return csv_download_response(
        "scene-events.csv",
        ["eventId", "sceneId", "eventType", "action", "status", "actor", "at", "layerRecordCode", "comment", "summary"],
        page,
    )


@app.get("/api/scenes/quality-issues")
def list_scene_quality_issues(
    request: Request,
    q: str = Query(default=""),
    issueType: str = Query(default=""),
    severity: str = Query(default=""),
    sceneId: str = Query(default=""),
    taskId: str = Query(default=""),
    status: str = Query(default=""),
    includeArchived: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    require_imagery_permission(request, IMAGERY_SCENE_VIEW_PERMISSION)
    if includeArchived:
        require_imagery_permission(request, IMAGERY_TASK_ARCHIVE_PERMISSION)
    records = list_imagery_quality_issues(
        q=q,
        issue_type=issueType,
        severity=severity,
        scene_id=sceneId,
        task_id=taskId,
        status=status,
        include_archived=includeArchived,
    )
    page = records[offset : offset + limit]
    return {
        "items": page,
        "total": len(records),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/scenes/quality-issues.csv")
def export_scene_quality_issues_csv(
    request: Request,
    q: str = Query(default=""),
    issueType: str = Query(default=""),
    severity: str = Query(default=""),
    sceneId: str = Query(default=""),
    taskId: str = Query(default=""),
    status: str = Query(default=""),
    includeArchived: bool = Query(default=False),
    limit: int = Query(default=1000, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> Response:
    require_imagery_permission(request, IMAGERY_SCENE_EXPORT_PERMISSION)
    if includeArchived:
        require_imagery_permission(request, IMAGERY_TASK_ARCHIVE_PERMISSION)
    records = list_imagery_quality_issues(
        q=q,
        issue_type=issueType,
        severity=severity,
        scene_id=sceneId,
        task_id=taskId,
        status=status,
        include_archived=includeArchived,
    )
    page = records[offset : offset + limit]
    return csv_download_response(
        "imagery-quality-issues.csv",
        [
            "issueId",
            "issueType",
            "issueKey",
            "severity",
            "status",
            "sceneId",
            "sceneName",
            "taskId",
            "taskName",
            "sourceStatus",
            "message",
            "actionRequired",
            "handledBy",
            "handledAt",
            "handlingComment",
            "adminHref",
        ],
        page,
    )


@app.patch("/api/scenes/quality-issues/{issue_id:path}")
def update_scene_quality_issue(
    issue_id: str,
    payload: QualityIssueUpdateRequest,
    request: Request,
) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_SCENE_QUALITY_PERMISSION)
    return update_imagery_quality_issue(issue_id, payload, context)


@app.get("/api/scenes/workflow-summary")
def get_imagery_workflow_summary(request: Request) -> dict[str, Any]:
    require_imagery_permission(request, IMAGERY_SCENE_VIEW_PERMISSION)
    return imagery_workflow_summary(request)


@app.get("/api/scenes/operation-queue")
def get_imagery_operation_queue(
    request: Request,
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    require_imagery_permission(request, IMAGERY_SCENE_VIEW_PERMISSION)
    return imagery_operation_queue(request, limit=limit)


@app.get("/api/scenes/workflow-summary.json")
def export_imagery_workflow_summary(request: Request) -> Response:
    require_imagery_permission(request, IMAGERY_SCENE_EXPORT_PERMISSION)
    payload = {**imagery_workflow_summary(request), "exportedAt": now_iso()}
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="imagery-workflow-summary.json"'},
    )


@app.get("/api/scenes/{scene_id}/delivery-receipt.json")
def export_scene_delivery_receipt(scene_id: str, request: Request) -> Response:
    context = require_imagery_permission(request, IMAGERY_SCENE_EXPORT_PERMISSION)
    scene = find_allowed_scene(scene_id, request)
    scene, _event = append_scene_delivery_receipt_export_event(scene, context)
    filename = f"scene-delivery-receipt-{safe_download_stem(scene_id, 'scene')}.json"
    return json_download_response(filename, scene_delivery_receipt(scene, request, context))


@app.get("/api/scenes/{scene_id}/publication-receipt.json")
def export_scene_publication_receipt(scene_id: str, request: Request) -> Response:
    context = require_imagery_permission(request, IMAGERY_SCENE_EXPORT_PERMISSION)
    scene = find_allowed_scene(scene_id, request)
    scene, _event = append_scene_publication_receipt_export_event(scene, context)
    filename = f"scene-publication-receipt-{safe_download_stem(scene_id, 'scene')}.json"
    return json_download_response(filename, scene_publication_receipt(scene, request, context))


@app.post("/api/scenes/{scene_id}/delivery")
def update_scene_delivery(scene_id: str, payload: SceneDeliveryRequest, request: Request) -> dict[str, Any]:
    scene = find_scene(scene_id)
    updated, event = update_scene_delivery_status(scene, payload, request)
    return {
        "ok": True,
        "id": scene_id,
        "deliveryStatus": updated.get("deliveryStatus"),
        "deliveredAt": updated.get("deliveredAt"),
        "deliveredBy": updated.get("deliveredBy"),
        "scene": public_scene(updated, request),
        "event": event,
    }


@app.get("/api/scenes/{scene_id}")
def get_scene(scene_id: str, request: Request) -> dict[str, Any]:
    return public_scene(find_allowed_scene(scene_id, request), request)


@app.patch("/api/scenes/{scene_id}")
def update_scene(scene_id: str, payload: SceneUpdateRequest, request: Request) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_SCENE_UPDATE_PERMISSION)
    scene = find_scene(scene_id)
    updated, event = apply_scene_update(scene, payload, str(context.get("user") or ""))
    save_scene(updated)
    clear_tile_cache(scene_id)
    return {**public_scene(updated, request), "event": event}


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
    projectId: str = Form(""),
    areaCode: str = Form(""),
    allowedRoles: str = Form(""),
    allowedUsers: str = Form(""),
    asyncMode: bool = Form(False),
    assetType: str = Form("orthophoto"),
    missionId: str = Form(""),
    linkedBlockCodes: str = Form(""),
    processingStage: str = Form("ready"),
) -> Any:
    context = require_imagery_permission(request, IMAGERY_SCENE_CREATE_PERMISSION)
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
    metadata = {
        "name": name.strip() or Path(file.filename or scene_id).stem,
        "fileName": file.filename,
        "satellite": satellite.strip(),
        "sensor": sensor.strip(),
        "capturedAt": capturedAt.strip(),
        "resolution": resolution.strip(),
        "projectId": projectId.strip(),
        "areaCode": areaCode.strip(),
        "allowedRoles": allowedRoles,
        "allowedUsers": allowedUsers,
        "assetType": assetType.strip() or "orthophoto",
        "missionId": missionId.strip(),
        "linkedBlockCodes": linkedBlockCodes,
        "processingStage": processingStage.strip() or "ready",
    }
    if asyncMode:
        task = create_conversion_task(
            source_path,
            metadata,
            fallback_bounds,
            "upload",
            delete_original=True,
            analysis_context=context,
        )
        return JSONResponse(status_code=202, content={"accepted": True, "task": task_public(task, request)})

    try:
        convert_to_cog(source_path, cog_path)
        scene = build_scene_record(scene_id, source_path, cog_path, metadata, fallback_bounds, delete_original=True)
        scene = analyze_raster_scene_coverage(scene, cog_path, context)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"GDAL COG conversion failed: {exc}") from exc

    save_scene(scene)
    return public_scene(scene, request)


@app.post("/api/scenes/register")
def register_scene(payload: RegisterSceneRequest, request: Request) -> JSONResponse:
    context = require_imagery_permission(request, IMAGERY_SCENE_CREATE_PERMISSION)
    source_path = resolve_import_path(payload.path)
    fallback_bounds = parse_bounds(payload.bounds)
    metadata = {
        "name": payload.name.strip() or source_path.stem,
        "fileName": source_path.name,
        "satellite": payload.satellite.strip(),
        "sensor": payload.sensor.strip(),
        "capturedAt": payload.capturedAt.strip(),
        "resolution": payload.resolution.strip(),
        "projectId": payload.projectId.strip(),
        "areaCode": payload.areaCode.strip(),
        "allowedRoles": payload.allowedRoles,
        "allowedUsers": payload.allowedUsers,
        "assetType": payload.assetType.strip() or "orthophoto",
        "missionId": payload.missionId.strip(),
        "linkedBlockCodes": payload.linkedBlockCodes,
        "processingStage": payload.processingStage.strip() or "ready",
    }
    task = create_conversion_task(
        source_path,
        metadata,
        fallback_bounds,
        "register",
        delete_original=False,
        analysis_context=context,
    )
    return JSONResponse(status_code=202, content={"accepted": True, "task": task_public(task, request)})


@app.post("/api/scenes/{scene_id}/coverage/confirm")
def confirm_scene_coverage(
    scene_id: str,
    payload: CoverageConfirmationRequest,
    request: Request,
) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_SCENE_UPDATE_PERMISSION)
    scene = find_allowed_scene(scene_id, request)
    blocks: list[dict[str, Any]] = []
    for code in split_tokens(payload.blockCodes):
        block = block_by_code(code)
        if not block:
            raise HTTPException(status_code=422, detail=f"Forest block does not exist: {code}")
        blocks.append(find_block(str(block["id"]), platform_auth_context(context)))
    confirmed_codes = [str(block["blockCode"]) for block in blocks]
    analysis = dict(scene.get("coverageAnalysis") or {})
    analysis.update(
        {
            "requiresConfirmation": False,
            "confirmedAt": now_iso(),
            "confirmedBy": str(context.get("user") or ""),
            "confirmedBlockCodes": confirmed_codes,
        }
    )
    updated = {
        **scene,
        "linkedBlockCodes": confirmed_codes,
        "processingStage": "ready",
        "coverageAnalysis": analysis,
        "updatedAt": now_iso(),
    }
    save_scene(updated)
    replace_scene_links_for_scene(
        scene_id,
        [
            {
                "forestBlockId": str(block["id"]),
                "relationType": "coverage",
                "capturedAt": updated.get("capturedAt") or None,
                "confidence": 1.0,
            }
            for block in blocks
        ],
    )
    return public_scene(updated, request)


@app.post("/api/point-clouds/upload-sessions")
def create_point_cloud_upload_session(
    payload: PointCloudUploadSessionRequest,
    request: Request,
) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_SCENE_CREATE_PERMISSION)
    ensure_dirs()
    outputs = point_cloud_outputs(payload.outputs)
    names: set[str] = set()
    validated_files: list[tuple[int, PointCloudFileManifest]] = []
    session_id = f"pc-upload-{uuid.uuid4().hex[:12]}"
    session_path = point_cloud_session_dir(session_id)
    for index, manifest in enumerate(payload.files):
        extension = Path(manifest.name).suffix.lower()
        if extension not in SUPPORTED_POINT_CLOUD_EXTENSIONS:
            raise HTTPException(status_code=422, detail=f"Only LAS/LAZ files are accepted: {manifest.name}")
        normalized_name = manifest.name.strip().lower()
        if normalized_name in names:
            raise HTTPException(status_code=422, detail=f"Duplicate point-cloud file name: {manifest.name}")
        names.add(normalized_name)
        validated_files.append((index, manifest))
    (session_path / "files").mkdir(parents=True, exist_ok=False)
    files: list[dict[str, Any]] = []
    for index, manifest in validated_files:
        total_chunks = math.ceil(manifest.size / POINT_CLOUD_CHUNK_SIZE)
        storage_path = session_path / "files" / f"{index:04d}-{slugify(manifest.name)}"
        files.append(
            {
                "index": index,
                "name": manifest.name.strip(),
                "size": manifest.size,
                "lastModified": manifest.lastModified,
                "chunkSize": POINT_CLOUD_CHUNK_SIZE,
                "totalChunks": total_chunks,
                "receivedChunks": [],
                "chunkHashes": {},
                "uploadedBytes": 0,
                "storagePath": str(storage_path),
            }
        )
    timestamp = now_iso()
    session = {
        "id": session_id,
        "name": payload.name.strip(),
        "missionId": payload.missionId.strip(),
        "capturedAt": payload.capturedAt.strip(),
        "outputs": outputs,
        "status": "uploading",
        "files": files,
        "createdBy": str(context.get("user") or ""),
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    save_point_cloud_session(session)
    return public_point_cloud_session(session)


@app.get("/api/point-clouds/upload-sessions/{session_id}")
def get_point_cloud_upload_session(session_id: str, request: Request) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_SCENE_CREATE_PERMISSION)
    session = load_point_cloud_session(session_id)
    require_point_cloud_session_access(session, context)
    return public_point_cloud_session(session)


@app.put("/api/point-clouds/upload-sessions/{session_id}/files/{file_index}/chunks/{chunk_index}")
async def upload_point_cloud_chunk(
    session_id: str,
    file_index: int,
    chunk_index: int,
    request: Request,
) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_SCENE_CREATE_PERMISSION)
    session = load_point_cloud_session(session_id)
    require_point_cloud_session_access(session, context)
    if session.get("status") != "uploading":
        raise HTTPException(status_code=409, detail="Point-cloud upload session is not accepting chunks")
    files = list(session.get("files") or [])
    if file_index < 0 or file_index >= len(files):
        raise HTTPException(status_code=404, detail="Point-cloud upload file not found")
    item = files[file_index]
    total_chunks = int(item["totalChunks"])
    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=416, detail="Point-cloud chunk index is outside the file range")
    body = await request.body()
    expected_start = chunk_index * int(item["chunkSize"])
    expected_size = min(int(item["chunkSize"]), int(item["size"]) - expected_start)
    if len(body) != expected_size:
        raise HTTPException(status_code=416, detail=f"Chunk size mismatch; expected {expected_size} bytes")
    content_range = request.headers.get("content-range", "")
    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
    if not match:
        raise HTTPException(status_code=400, detail="Content-Range must be bytes start-end/total")
    start, end, total = (int(value) for value in match.groups())
    if start != expected_start or end != expected_start + len(body) - 1 or total != int(item["size"]):
        raise HTTPException(status_code=416, detail="Content-Range does not match the requested chunk")
    digest = hashlib.sha256(body).hexdigest()
    expected_digest = request.headers.get("x-chunk-sha256", "").strip().lower()
    if expected_digest and expected_digest != digest:
        raise HTTPException(status_code=422, detail="Point-cloud chunk checksum mismatch")

    with point_cloud_file_lock(session_id, file_index), POINT_CLOUD_SESSION_LOCK:
        session = load_point_cloud_session(session_id)
        require_point_cloud_session_access(session, context)
        if session.get("status") != "uploading":
            raise HTTPException(status_code=409, detail="Point-cloud upload session is not accepting chunks")
        item = session["files"][file_index]
        storage_path = Path(str(item["storagePath"])).resolve()
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "r+b" if storage_path.exists() else "w+b"
        with storage_path.open(mode) as output:
            if mode == "w+b":
                output.truncate(int(item["size"]))
            output.seek(expected_start)
            output.write(body)
            output.flush()
        received = {int(value) for value in item.get("receivedChunks") or []}
        is_new = chunk_index not in received
        received.add(chunk_index)
        item["receivedChunks"] = sorted(received)
        item.setdefault("chunkHashes", {})[str(chunk_index)] = digest
        if is_new:
            item["uploadedBytes"] = int(item.get("uploadedBytes") or 0) + len(body)
        session["updatedAt"] = now_iso()
        save_point_cloud_session(session)
    return {
        "ok": True,
        "fileIndex": file_index,
        "chunkIndex": chunk_index,
        "sha256": digest,
        "session": public_point_cloud_session(session),
    }


@app.post("/api/point-clouds/upload-sessions/{session_id}/complete")
def complete_point_cloud_upload_session(session_id: str, request: Request) -> JSONResponse:
    context = require_imagery_permission(request, IMAGERY_SCENE_CREATE_PERMISSION)
    with POINT_CLOUD_SESSION_LOCK:
        session = load_point_cloud_session(session_id)
        require_point_cloud_session_access(session, context)
        if session.get("status") == "queued" and session.get("taskId"):
            return JSONResponse(
                status_code=202,
                content={"accepted": True, "task": task_public(find_task_record(str(session["taskId"])), request)},
            )
        incomplete = [
            item["name"]
            for item in session.get("files") or []
            if len(set(item.get("receivedChunks") or [])) != int(item.get("totalChunks") or 0)
        ]
        if incomplete:
            raise HTTPException(status_code=409, detail=f"Point-cloud files are incomplete: {', '.join(incomplete[:5])}")
        source_paths = [Path(str(item["storagePath"])).resolve() for item in session["files"]]
        task = create_point_cloud_conversion_task(
            source_paths,
            {
                "name": session["name"],
                "missionId": session.get("missionId") or "",
                "capturedAt": session.get("capturedAt") or "",
            },
            outputs=list(session.get("outputs") or []),
            task_type="pointcloud-upload",
            delete_original=True,
            analysis_context=context,
        )
        session["status"] = "queued"
        session["taskId"] = task["id"]
        session["updatedAt"] = now_iso()
        save_point_cloud_session(session)
    return JSONResponse(status_code=202, content={"accepted": True, "task": task_public(task, request)})


@app.post("/api/point-clouds/register")
def register_point_cloud(payload: PointCloudRegisterRequest, request: Request) -> JSONResponse:
    context = require_imagery_permission(request, IMAGERY_SCENE_CREATE_PERMISSION)
    source_paths = resolve_point_cloud_import_sources(payload.path, recursive=payload.recursive)
    task = create_point_cloud_conversion_task(
        source_paths,
        {
            "name": payload.name.strip(),
            "missionId": payload.missionId.strip(),
            "capturedAt": payload.capturedAt.strip(),
        },
        outputs=payload.outputs,
        task_type="pointcloud-register",
        delete_original=False,
        analysis_context=context,
    )
    return JSONResponse(status_code=202, content={"accepted": True, "task": task_public(task, request)})


@app.post("/api/3d-tiles/register")
def register_3d_tiles(payload: TilesetRegisterRequest, request: Request) -> JSONResponse:
    context = require_imagery_permission(request, IMAGERY_SCENE_CREATE_PERMISSION)
    root_path = resolve_3d_tileset_import_root(payload.path)
    task = create_3d_tileset_registration_task(
        root_path,
        {
            "name": payload.name.strip(),
            "missionId": payload.missionId.strip(),
            "capturedAt": payload.capturedAt.strip(),
        },
        analysis_context=context,
    )
    return JSONResponse(status_code=202, content={"accepted": True, "task": task_public(task, request)})


@app.patch("/api/scenes/{scene_id}/access")
def update_scene_access(scene_id: str, payload: SceneAccessUpdateRequest, request: Request) -> dict[str, Any]:
    require_imagery_permission(request, IMAGERY_SCENE_UPDATE_PERMISSION)
    scene = find_scene(scene_id)
    updated = apply_access_update(scene, payload)
    save_scene(updated)
    clear_tile_cache(scene_id)
    return public_scene(updated, request)


@app.post("/api/scenes/access/bulk")
def bulk_update_scene_access(payload: BulkSceneAccessUpdateRequest, request: Request) -> dict[str, Any]:
    require_imagery_permission(request, IMAGERY_SCENE_UPDATE_PERMISSION)
    target_ids = set(payload.ids)
    if not target_ids:
        raise HTTPException(status_code=400, detail="ids cannot be empty")

    updated: list[dict[str, Any]] = []
    missing = set(target_ids)
    for scene in load_catalog():
        scene_id = str(scene.get("id") or "")
        if scene_id not in target_ids:
            continue
        next_scene = apply_access_update(scene, payload)
        save_scene(next_scene)
        clear_tile_cache(scene_id)
        updated.append(public_scene(next_scene, request))
        missing.discard(scene_id)

    return {"updated": len(updated), "missing": sorted(missing), "scenes": updated}


@app.post("/api/scenes/{scene_id}/restore")
def restore_scene(scene_id: str, request: Request) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_SCENE_RESTORE_PERMISSION)
    scene = find_scene(scene_id, include_deleted=True)
    timestamp = now_iso()
    restored_scene = dict(scene)
    restored_scene["status"] = "active"
    restored_scene["deletedAt"] = None
    restored_scene["deletedBy"] = ""
    restored_scene["updatedAt"] = timestamp
    event = {
        "at": timestamp,
        "action": "restore",
        "actor": str(context.get("user") or ""),
        "status": "active",
    }
    lifecycle_events = list(restored_scene.get("lifecycleEvents") or [])
    lifecycle_events.append(event)
    restored_scene["lifecycleEvents"] = lifecycle_events
    save_scene(restored_scene)
    return {
        "ok": True,
        "restored": scene_id,
        "scene": public_scene(restored_scene, request),
        "event": event,
    }


@app.post("/api/scenes/{scene_id}/archive")
def archive_scene(scene_id: str, request: Request) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_SCENE_ARCHIVE_PERMISSION)
    scene = find_scene(scene_id)
    timestamp = now_iso()
    actor = str(context.get("user") or "")
    archived_layer = archive_scene_published_layer(scene, timestamp, actor)
    archived_scene = dict(scene)
    archived_scene["status"] = "archived"
    archived_scene["visible"] = False
    archived_scene["archivedAt"] = timestamp
    archived_scene["archivedBy"] = actor
    archived_scene["updatedAt"] = timestamp
    event = {
        "at": timestamp,
        "action": "archive",
        "actor": actor,
        "status": "archived",
        "layerId": archived_layer.get("id") if archived_layer else archived_scene.get("publishedLayerId"),
        "layerRecordCode": archived_layer.get("recordCode")
        if archived_layer
        else archived_scene.get("publishedLayerRecordCode"),
    }
    lifecycle_events = list(archived_scene.get("lifecycleEvents") or [])
    lifecycle_events.append(event)
    archived_scene["lifecycleEvents"] = lifecycle_events
    save_scene(archived_scene)
    return {
        "ok": True,
        "archived": scene_id,
        "scene": public_scene(archived_scene, request),
        "layer": archived_layer,
        "event": event,
    }


@app.post("/api/scenes/{scene_id}/publish-layer")
def publish_scene_layer(scene_id: str, payload: SceneLayerPublishRequest, request: Request) -> dict[str, Any]:
    context = require_imagery_layer_publish(request)
    scene = find_scene(scene_id)
    public_payload = public_scene(scene, request)
    layer = publish_layer_record_for_scene(scene, public_payload, payload, context)
    updated_scene, event = append_scene_publish_event(scene, layer, context)
    return {"ok": True, "layer": layer, "scene": public_scene(updated_scene, request), "event": event}


@app.get("/api/tasks")
def list_tasks(
    request: Request,
    status: str = Query(default=""),
    includeArchived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    require_imagery_permission(request, IMAGERY_SCENE_VIEW_PERMISSION)
    if includeArchived:
        require_imagery_permission(request, IMAGERY_TASK_ARCHIVE_PERMISSION)
    tasks = filter_tasks(load_tasks(), status=status, include_archived=includeArchived)
    page = tasks[offset : offset + limit]
    return {
        "total": len(tasks),
        "limit": limit,
        "offset": offset,
        "tasks": [task_public(task, request) for task in page],
    }


@app.get("/api/tasks/events")
def list_task_events(
    request: Request,
    q: str = Query(default=""),
    status: str = Query(default=""),
    action: str = Query(default=""),
    taskId: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    require_imagery_permission(request, IMAGERY_SCENE_VIEW_PERMISSION)
    records = list_task_event_records(q=q, status=status, action=action, task_id=taskId)
    page = records[offset : offset + limit]
    return {
        "items": page,
        "total": len(records),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/tasks/events.csv")
def export_task_events_csv(
    request: Request,
    q: str = Query(default=""),
    status: str = Query(default=""),
    action: str = Query(default=""),
    taskId: str = Query(default=""),
    limit: int = Query(default=1000, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> Response:
    require_imagery_permission(request, IMAGERY_SCENE_EXPORT_PERMISSION)
    records = list_task_event_records(q=q, status=status, action=action, task_id=taskId)
    page = records[offset : offset + limit]
    return csv_download_response(
        "task-events.csv",
        ["eventId", "taskId", "taskType", "sceneId", "status", "action", "actor", "at", "progress", "message"],
        page,
    )


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, request: Request) -> dict[str, Any]:
    require_imagery_permission(request, IMAGERY_SCENE_VIEW_PERMISSION)
    return task_public(find_task_record(task_id), request)


@app.post("/api/tasks/{task_id}/retry")
def retry_task(task_id: str, request: Request) -> dict[str, Any]:
    require_imagery_permission(request, IMAGERY_TASK_RETRY_PERMISSION)
    task = retry_failed_conversion_task(task_id)
    return {"accepted": True, "task": task_public(task, request)}


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_TASK_CANCEL_PERMISSION)
    task = cancel_task_record(task_id, str(context.get("user") or ""))
    return {"ok": True, "canceled": task_id, "task": task_public(task, request)}


@app.post("/api/tasks/{task_id}/archive")
def archive_task(task_id: str, request: Request) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_TASK_ARCHIVE_PERMISSION)
    task = archive_task_record(task_id, str(context.get("user") or ""))
    return {"ok": True, "archived": task_id, "task": task_public(task, request)}


@app.get("/api/scenes/{scene_id}/point-cloud/copc")
def point_cloud_copc(scene_id: str, request: Request) -> FileResponse:
    scene = find_allowed_scene(scene_id, request)
    if str(scene.get("assetType") or "") != "pointcloud":
        raise HTTPException(status_code=404, detail="Point-cloud asset not found")
    path_value = str(scene.get("copcPath") or "").strip()
    if not path_value:
        raise HTTPException(status_code=404, detail="COPC output is not available")
    path = resolve_catalog_path(path_value)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="COPC file not found")
    return FileResponse(path, media_type="application/vnd.laszip", filename=f"{slugify(scene['name'])}.copc.laz")


@app.get("/api/scenes/{scene_id}/point-cloud/tiles/{asset_path:path}")
def point_cloud_3dtiles(scene_id: str, asset_path: str, request: Request) -> Response:
    scene = find_allowed_scene(scene_id, request)
    if str(scene.get("assetType") or "") not in {"pointcloud", "oblique3d"}:
        raise HTTPException(status_code=404, detail="3D Tiles asset not found")
    tileset_value = str(scene.get("tilesetPath") or "").strip()
    if not tileset_value:
        raise HTTPException(status_code=404, detail="3D Tiles output is not available")
    tiles_root = resolve_catalog_path(tileset_value).parent.resolve()
    target = (tiles_root / asset_path).resolve()
    if not is_relative_to(target, tiles_root) or not target.is_file():
        raise HTTPException(status_code=404, detail="3D Tiles asset not found")
    relative_parts = target.relative_to(tiles_root).parts
    if any(part.startswith(".") for part in relative_parts):
        raise HTTPException(status_code=404, detail="3D Tiles asset not found")
    allowed_extensions = {
        ".json", ".pnts", ".b3dm", ".cmpt", ".i3dm", ".glb", ".gltf", ".bin",
        ".jpg", ".jpeg", ".png", ".webp", ".ktx2",
    }
    if target.suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=404, detail="Unsupported 3D Tiles asset")
    if target.suffix.lower() == ".json":
        return JSONResponse(
            content=normalized_tileset_document(
                target,
                service_token=str(request.query_params.get("token") or ""),
            )
        )
    media_types = {
        ".pnts": "application/octet-stream",
        ".b3dm": "application/octet-stream",
        ".cmpt": "application/octet-stream",
        ".i3dm": "application/octet-stream",
        ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json",
        ".bin": "application/octet-stream",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".ktx2": "image/ktx2",
    }
    return FileResponse(target, media_type=media_types.get(target.suffix.lower(), "application/octet-stream"))


@app.get("/api/scenes/{scene_id}/tilejson.json")
def tilejson(scene_id: str, request: Request) -> dict[str, Any]:
    scene = public_scene(find_allowed_scene(scene_id, request), request)
    return {
        "tilejson": "3.0.0",
        "name": scene["name"],
        "bounds": scene["bounds"],
        "minzoom": 0,
        "maxzoom": 22,
        "tiles": [scene["tileUrl"]],
    }


@app.get("/api/scenes/{scene_id}/thumbnail.png")
def scene_thumbnail(
    scene_id: str,
    request: Request,
    maxSize: int = Query(default=640, ge=128, le=1600),
) -> Response:
    scene = find_allowed_scene(scene_id, request)
    cog_path = resolve_catalog_path(str(scene["cogPath"]))
    if not cog_path.exists():
        raise HTTPException(status_code=404, detail="COG file not found")

    cache_path = thumbnail_cache_path(scene_id, cog_path, maxSize)
    if cache_path.exists():
        return Response(
            content=cache_path.read_bytes(),
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=3600", "X-Thumbnail-Cache": "HIT"},
        )

    COGReader = require_rio_tiler()
    try:
        with COGReader(str(cog_path)) as cog:
            image = cog.preview(max_size=maxSize)
            content = image.render(img_format="PNG")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Thumbnail render failed: {exc}") from exc

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    for stale_path in cache_path.parent.glob("*.png"):
        if stale_path != cache_path:
            stale_path.unlink(missing_ok=True)
    cache_path.write_bytes(content)
    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600", "X-Thumbnail-Cache": "MISS"},
    )


@app.get("/api/scenes/{scene_id}/tiles/{z}/{x}/{y}.png")
def tile(
    request: Request,
    scene_id: str,
    z: int,
    x: int,
    y: int,
    bidx: list[int] | None = Query(default=None),
) -> Response:
    scene = find_allowed_scene(scene_id, request)
    cog_path = resolve_catalog_path(str(scene["cogPath"]))
    if not cog_path.exists():
        raise HTTPException(status_code=404, detail="COG file not found")

    cache_path = tile_cache_path(scene_id, z, x, y, bidx)
    if TILE_CACHE_ENABLED and cache_path.exists():
        return Response(
            content=cache_path.read_bytes(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400", "X-Tile-Cache": "HIT"},
        )

    COGReader = require_rio_tiler()
    try:
        with COGReader(str(cog_path)) as cog:
            image = cog.tile(x, y, z, indexes=bidx)
            content = image.render(img_format="PNG")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Tile render failed: {exc}") from exc

    if TILE_CACHE_ENABLED:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
        maybe_prune_cache("tiles", CACHE_DIR, TILE_CACHE_MAX_BYTES, TILE_CACHE_MAX_AGE_DAYS)
    return Response(content=content, media_type="image/png", headers={"Cache-Control": "public, max-age=86400", "X-Tile-Cache": "MISS"})


@app.get("/api/cache/tiles")
def tile_cache_status(request: Request) -> dict[str, Any]:
    request_context(request)
    return cache_stats()


@app.delete("/api/cache/tiles")
def delete_tile_cache(request: Request, sceneId: str | None = Query(default=None)) -> dict[str, Any]:
    context = request_context(request)
    require_admin_permission(platform_auth_context(context), "imagery.cache.manage")
    return clear_tile_cache(sceneId)


@app.post("/api/cache/tiles/prune")
def prune_tile_cache(
    request: Request,
    maxBytes: int = Query(default=0, ge=0),
    maxAgeDays: float = Query(default=0, ge=0),
) -> dict[str, Any]:
    context = request_context(request)
    require_admin_permission(platform_auth_context(context), "imagery.cache.manage")
    result = prune_cache_dir(
        CACHE_DIR,
        max_bytes=maxBytes or TILE_CACHE_MAX_BYTES,
        max_age_days=maxAgeDays or TILE_CACHE_MAX_AGE_DAYS,
    )
    return {**cache_stats(), **result}


@app.get("/api/basemaps/tianditu/{layer}/{z}/{x}/{y}.png")
def tianditu_tile(request: Request, layer: str, z: int, x: int, y: int, tk: str = Query(default="")) -> Response:
    if layer not in TIANDITU_LAYERS:
        raise HTTPException(status_code=400, detail=f"Unsupported Tianditu layer: {layer}")
    if z < 0 or z > 22 or x < 0 or y < 0:
        raise HTTPException(status_code=400, detail="Invalid tile coordinate")

    runtime = runtime_basemap_settings()
    browser_token = tk.strip()
    # Keep the process-level value as a fallback for deployments and tests that
    # inject the server key without persisting a runtime basemap settings file.
    token = browser_token or runtime["serverKey"] or TIANDITU_TK
    if not token and not runtime["proxyBaseUrl"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Tianditu source is required. Pass ?tk=..., set REMOTE_SENSING_TIANDITU_TK, "
                "or set REMOTE_SENSING_TIANDITU_PROXY_BASE_URL."
            ),
        )

    cache_path = tianditu_cache_path(layer, z, x, y)
    try:
        if cache_path.exists():
            return Response(
                content=cache_path.read_bytes(),
                media_type="image/png",
                headers={"Cache-Control": TIANDITU_BROWSER_CACHE_CONTROL, "X-Tianditu-Cache": "HIT"},
            )
    except OSError:
        # A read-only cache must not make the basemap unavailable.
        pass

    referer = ""
    if browser_token:
        referer = (
            request.headers.get("referer")
            or request.headers.get("origin")
            or runtime["referer"]
        )
    content = (
        fetch_tianditu_tile(layer, z, x, y, token, referer=referer)
        if token
        else fetch_tianditu_proxy_tile(layer, z, x, y)
    )
    cache_status = "MISS"
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
        maybe_prune_cache("tianditu", TIANDITU_CACHE_DIR, BASEMAP_CACHE_MAX_BYTES, BASEMAP_CACHE_MAX_AGE_DAYS)
    except OSError:
        cache_status = "BYPASS"
    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": TIANDITU_BROWSER_CACHE_CONTROL, "X-Tianditu-Cache": cache_status},
    )


@app.get("/api/cache/tianditu")
def tianditu_cache_status(request: Request) -> dict[str, Any]:
    request_context(request)
    return tianditu_cache_stats()


@app.delete("/api/cache/tianditu")
def delete_tianditu_cache(request: Request, layer: str | None = Query(default=None)) -> dict[str, Any]:
    context = request_context(request)
    require_admin_permission(platform_auth_context(context), "imagery.cache.manage")
    if layer and layer not in TIANDITU_LAYERS:
        raise HTTPException(status_code=400, detail=f"Unsupported Tianditu layer: {layer}")
    return clear_tianditu_cache(layer)


@app.post("/api/cache/tianditu/prune")
def prune_tianditu_cache(
    request: Request,
    maxBytes: int = Query(default=0, ge=0),
    maxAgeDays: float = Query(default=0, ge=0),
) -> dict[str, Any]:
    context = request_context(request)
    require_admin_permission(platform_auth_context(context), "imagery.cache.manage")
    result = prune_cache_dir(
        TIANDITU_CACHE_DIR,
        max_bytes=maxBytes or BASEMAP_CACHE_MAX_BYTES,
        max_age_days=maxAgeDays or BASEMAP_CACHE_MAX_AGE_DAYS,
    )
    return {**tianditu_cache_stats(), **result}


@app.post("/api/cache/tianditu/prewarm")
def start_tianditu_prewarm(
    payload: TiandituPrewarmRequest,
    request: Request,
) -> dict[str, Any]:
    context = request_context(request)
    require_admin_permission(platform_auth_context(context), "imagery.cache.manage")
    task = create_tianditu_prewarm_task(
        bounds=payload.bounds,
        min_zoom=payload.minZoom,
        max_zoom=payload.maxZoom,
        layers=payload.layers,
        actor=str(context.get("user") or ""),
    )
    return {"ok": True, "task": task}


@app.delete("/api/scenes/{scene_id}")
def delete_scene(scene_id: str, request: Request) -> dict[str, Any]:
    context = require_imagery_permission(request, IMAGERY_SCENE_DELETE_PERMISSION)
    scenes = load_catalog(include_deleted=True)
    target = None
    for scene in scenes:
        if scene.get("id") == scene_id:
            target = scene
    if not target:
        raise HTTPException(status_code=404, detail="Scene not found")

    timestamp = now_iso()
    actor = str(context.get("user") or "")
    archived_layer = archive_scene_published_layer(
        target,
        timestamp,
        actor,
        reason="source-scene-deleted",
    )
    updated_scene = dict(target)
    updated_scene["status"] = "deleted"
    updated_scene["deletedAt"] = timestamp
    updated_scene["deletedBy"] = actor
    updated_scene["updatedAt"] = timestamp
    updated_scene["visible"] = False
    lifecycle_events = list(updated_scene.get("lifecycleEvents") or [])
    lifecycle_events.append(
        {
            "at": timestamp,
            "action": "soft-delete",
            "actor": updated_scene["deletedBy"],
            "status": "deleted",
            "layerId": archived_layer.get("id") if archived_layer else updated_scene.get("publishedLayerId"),
            "layerRecordCode": archived_layer.get("recordCode")
            if archived_layer
            else updated_scene.get("publishedLayerRecordCode"),
        }
    )
    updated_scene["lifecycleEvents"] = lifecycle_events
    save_scene(updated_scene)
    deleted_links = delete_scene_links_for_scene(scene_id)
    clear_tile_cache(scene_id)
    return {
        "ok": True,
        "deleted": scene_id,
        "softDeleted": True,
        "deletedAt": timestamp,
        "deletedSceneLinks": deleted_links,
        "layer": archived_layer,
    }


@app.get("/api/system/frontend-version", include_in_schema=False)
def smart_bamboo_frontend_version() -> dict[str, str]:
    return {
        "dashboardVersion": SMART_BAMBOO_DASHBOARD_VERSION,
        "dashboardUrl": SMART_BAMBOO_DASHBOARD_URL,
    }


@app.get("/", include_in_schema=False)
def smart_bamboo_dashboard() -> RedirectResponse:
    return RedirectResponse(
        url=SMART_BAMBOO_DASHBOARD_URL,
        status_code=302,
        headers={"Clear-Site-Data": '"cache"'},
    )


@app.get("/index.html", include_in_schema=False)
def legacy_smart_bamboo_dashboard() -> RedirectResponse:
    return RedirectResponse(
        url=SMART_BAMBOO_DASHBOARD_URL,
        status_code=302,
        headers={"Clear-Site-Data": '"cache"'},
    )


def v2_frontend_response(path: str = "") -> FileResponse:
    index_path = V2_FRONTEND_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(
            status_code=503,
            detail="Smart Bamboo V2 frontend has not been built.",
        )

    requested_path = path.strip("/")
    if requested_path:
        candidate = (V2_FRONTEND_DIR / requested_path).resolve()
        try:
            candidate.relative_to(V2_FRONTEND_DIR)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="V2 asset not found.") from exc
        if candidate.is_file():
            return FileResponse(candidate)
        if Path(requested_path).suffix:
            raise HTTPException(status_code=404, detail="V2 asset not found.")
    return FileResponse(index_path)


@app.get("/v2", include_in_schema=False)
@app.get("/v2/", include_in_schema=False)
def smart_bamboo_v2_root() -> FileResponse:
    return v2_frontend_response()


@app.get("/v2/{path:path}", include_in_schema=False)
def smart_bamboo_v2_spa(path: str) -> FileResponse:
    return v2_frontend_response(path)


def mobile_frontend_response(path: str = "") -> FileResponse:
    index_path = MOBILE_FRONTEND_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(
            status_code=503,
            detail="Smart Bamboo mobile field frontend has not been built.",
        )
    requested_path = path.strip("/")
    if requested_path:
        candidate = (MOBILE_FRONTEND_DIR / requested_path).resolve()
        try:
            candidate.relative_to(MOBILE_FRONTEND_DIR)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Mobile asset not found.") from exc
        if candidate.is_file():
            return FileResponse(candidate)
        if Path(requested_path).suffix:
            raise HTTPException(status_code=404, detail="Mobile asset not found.")
    return FileResponse(index_path)


@app.get("/mobile", include_in_schema=False)
@app.get("/mobile/", include_in_schema=False)
def smart_bamboo_mobile_root() -> FileResponse:
    return mobile_frontend_response()


@app.get("/mobile/{path:path}", include_in_schema=False)
def smart_bamboo_mobile_spa(path: str) -> FileResponse:
    return mobile_frontend_response(path)


if SERVE_STATIC:
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
