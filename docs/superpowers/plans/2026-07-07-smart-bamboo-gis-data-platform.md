# Smart Bamboo GIS Data Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Formalize the existing Smart Bamboo and satellite imagery prototypes into a deployable GIS data platform with forest-block storage, import, editing, map filtering, imagery links, permissions, and Docker deployment.

**Architecture:** Keep the existing static OpenLayers pages and FastAPI imagery service, then add focused backend modules under `server/modules/` for settings, auth, database, forest blocks, imports, and forest-scene links. Store production forest-block data in PostGIS, keep a JSON fallback for local tests and no-database demos, and expose APIs consumed by a new vanilla `admin.html` workbench and the existing `zhushan-bigdata.html` map.

**Tech Stack:** FastAPI, psycopg 3, PostGIS, OpenLayers, vanilla HTML/CSS/JS, GDAL/rasterio/rio-tiler/TiTiler, pytest, httpx, openpyxl, shapely, pyogrio, Docker Compose.

## Global Constraints

- Preserve existing `zhushan-bigdata.*`, `satellite-manager.*`, `sdk/remote-sensing-sdk.js`, and `server/app.py` behavior unless a task explicitly changes it.
- Do not revert or overwrite existing dirty working-tree changes; read touched files immediately before editing.
- First-stage scope is forest blocks, imports, map, imagery association, permissions, and deployment;托管协议、管护任务、交易、碳汇 only receive empty menu states or extension tables.
- The production storage target is PostGIS; JSON fallback is only for local tests and demonstration when no database is configured.
- Existing remote-sensing APIs under `/api/scenes`, `/api/tasks`, `/api/cache`, `/api/geoserver`, and `/api/basemaps` must remain backward compatible.
- Static frontend files must remain runnable without a Node build step.
- Use ASCII punctuation in code and config files; Chinese UI copy is allowed in HTML/JS/CSS because the existing product is Chinese.
- Add tests before implementation for each backend behavior.
- Every task must leave the app in a runnable state and include its own verification command.

---

## File Structure

Create:

- `server/modules/__init__.py`: module package marker.
- `server/modules/settings.py`: environment parsing and shared platform settings.
- `server/modules/auth.py`: shared token and request-context helpers for new forest APIs.
- `server/modules/database.py`: PostGIS connection, schema initialization, and JSON fallback paths.
- `server/modules/forest_blocks.py`: forest-block Pydantic models, repository functions, and API router.
- `server/modules/imports.py`: CSV, Excel, GeoJSON, and Shapefile ZIP import parsing plus import API router.
- `server/modules/forest_scene_links.py`: forest block to remote-sensing scene link API router.
- `admin.html`: GIS data management workbench entry.
- `admin.css`: workbench layout and table/map-adjacent UI styles.
- `admin.js`: list filters, detail editor, import flow, and imagery link UI.
- `tests/conftest.py`: FastAPI test client and isolated temp data settings.
- `tests/test_forest_blocks.py`: forest block CRUD, filtering, map GeoJSON, and permissions.
- `tests/test_imports.py`: import parser and import endpoint behavior.
- `tests/test_forest_scene_links.py`: forest block to imagery association behavior.
- `Dockerfile`: production app image.
- `docker-compose.yml`: app + PostGIS + optional GeoServer profile.
- `.dockerignore`: keeps local caches, release ZIPs, data, and build artifacts out of Docker builds.
- `deploy/nginx-smart-bamboo.conf`: optional reverse proxy example.
- `docs/deploy-smart-bamboo-platform.md`: deployment and verification guide.
- `data/samples/forest-blocks-sample.geojson`: small sample import dataset.

Modify:

- `server/app.py`: include new routers and initialize new schema without changing existing imagery endpoints.
- `server/requirements.txt`: add test/import/database dependencies.
- `zhushan-bigdata.html`: add `admin` entry link and load any required config unchanged.
- `zhushan-bigdata.js`: load live forest blocks from API, keep current demo layers as fallback.
- `zhushan-bigdata.css`: add restrained GIS workbench filter styles if needed.
- `satellite-manager.html`: add link back to `admin.html`.
- `README_NAS_DEPLOY.md`: add pointer to the new deployment guide only after Docker verification passes.

---

### Task 1: Backend Foundation, Settings, Auth, And Schema

**Files:**
- Create: `server/modules/__init__.py`
- Create: `server/modules/settings.py`
- Create: `server/modules/auth.py`
- Create: `server/modules/database.py`
- Create: `tests/conftest.py`
- Create: `tests/test_forest_blocks.py`
- Modify: `server/requirements.txt`
- Modify: `server/app.py`

**Interfaces:**
- Consumes: Existing FastAPI `app` object in `server/app.py`.
- Produces:
  - `server.modules.settings.get_settings() -> PlatformSettings`
  - `server.modules.auth.request_context(request: Request) -> AuthContext`
  - `server.modules.auth.require_write_access(context: AuthContext) -> None`
  - `server.modules.database.init_platform_schema() -> None`
  - `server.modules.database.get_data_dir() -> Path`
  - `server.modules.database.use_postgis() -> bool`

- [ ] **Step 1: Write failing tests for settings and auth defaults**

Create `tests/conftest.py`:

```python
import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_SENSING_DATA_DIR", str(tmp_path / "remote-sensing"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REMOTE_SENSING_DATABASE_URL", raising=False)
    monkeypatch.delenv("SMART_BAMBOO_DATABASE_URL", raising=False)
    monkeypatch.setenv("SMART_BAMBOO_STORAGE_BACKEND", "json")
    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "0")
    yield tmp_path


@pytest.fixture()
def app_client(isolated_env):
    import server.modules.settings as settings
    import server.modules.database as database
    import server.app as app_module

    importlib.reload(settings)
    importlib.reload(database)
    importlib.reload(app_module)
    return TestClient(app_module.app)
```

Create the first tests in `tests/test_forest_blocks.py`:

```python
from server.modules.auth import request_context
from server.modules.settings import get_settings


def test_platform_settings_use_json_fallback(isolated_env):
    settings = get_settings()
    assert settings.storage_backend == "json"
    assert settings.database_url == ""
    assert settings.data_dir.name == "remote-sensing"


def test_health_includes_platform_schema_status(app_client):
    response = app_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "deployment" in body
    assert "smartBamboo" in body["deployment"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_forest_blocks.py::test_platform_settings_use_json_fallback tests/test_forest_blocks.py::test_health_includes_platform_schema_status -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'server.modules.settings'`.

- [ ] **Step 3: Add dependencies**

Modify `server/requirements.txt` to contain:

```text
fastapi>=0.115
uvicorn[standard]>=0.30
python-multipart>=0.0.9
rasterio>=1.4
rio-tiler>=7.0
titiler.core>=0.22
Pillow>=10
numpy>=2
psycopg[binary]>=3.2
openpyxl>=3.1
shapely>=2.0
pyogrio>=0.9
pytest>=8.2
httpx>=0.27
```

- [ ] **Step 4: Create settings module**

Create `server/modules/__init__.py`:

```python
"""Smart Bamboo platform modules."""
```

Create `server/modules/settings.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class PlatformSettings:
    data_dir: Path
    storage_backend: str
    database_url: str
    auth_required: bool
    cors_origins: list[str]


@lru_cache(maxsize=1)
def get_settings() -> PlatformSettings:
    data_dir = Path(
        os.environ.get("REMOTE_SENSING_DATA_DIR", str(ROOT_DIR / "data" / "remote-sensing"))
    ).expanduser().resolve()
    database_url = (
        os.environ.get("SMART_BAMBOO_DATABASE_URL")
        or os.environ.get("REMOTE_SENSING_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    storage_backend = os.environ.get("SMART_BAMBOO_STORAGE_BACKEND", "").strip().lower()
    if not storage_backend:
        storage_backend = "postgis" if database_url else "json"
    return PlatformSettings(
        data_dir=data_dir,
        storage_backend=storage_backend,
        database_url=database_url,
        auth_required=env_bool("REMOTE_SENSING_AUTH_REQUIRED", False),
        cors_origins=env_list("REMOTE_SENSING_CORS_ORIGINS", ["*"]),
    )
```

- [ ] **Step 5: Create auth module**

Create `server/modules/auth.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class AuthContext:
    user: str
    roles: set[str]
    projects: set[str]
    areas: set[str]


def split_header(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.replace(";", ",").split(",") if item.strip()}


def request_context(request: Request) -> AuthContext:
    return AuthContext(
        user=request.headers.get("X-RS-User", "").strip(),
        roles=split_header(request.headers.get("X-RS-Roles")),
        projects=split_header(request.headers.get("X-RS-Projects")),
        areas=split_header(request.headers.get("X-RS-Areas")),
    )


def has_admin_role(context: AuthContext) -> bool:
    return "*" in context.roles or "admin" in context.roles or "platform-admin" in context.roles


def require_write_access(context: AuthContext) -> None:
    if has_admin_role(context) or "operator" in context.roles or "gis-admin" in context.roles:
        return
    if not context.roles:
        return
    raise HTTPException(status_code=403, detail="Write access denied")


def area_allowed(context: AuthContext, area_code: str | None) -> bool:
    if not area_code or not context.areas or "*" in context.areas:
        return True
    return area_code in context.areas
```

- [ ] **Step 6: Create database module with schema initializer**

Create `server/modules/database.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .settings import get_settings


def get_data_dir() -> Path:
    data_dir = get_settings().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "forest-blocks").mkdir(parents=True, exist_ok=True)
    return data_dir


def use_postgis() -> bool:
    settings = get_settings()
    return settings.storage_backend == "postgis" and bool(settings.database_url)


def forest_blocks_json_path() -> Path:
    return get_data_dir() / "forest-blocks" / "forest_blocks.json"


def load_json_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8") or "[]")


def save_json_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def init_platform_schema() -> None:
    get_data_dir()
    if not use_postgis():
        return
    import psycopg

    with psycopg.connect(get_settings().database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS forest_blocks (
                    id uuid PRIMARY KEY,
                    block_code text UNIQUE NOT NULL,
                    name text NOT NULL,
                    county_code text,
                    county_name text,
                    town_code text,
                    town_name text,
                    village_code text,
                    village_name text,
                    base_type text,
                    operation_type text,
                    forest_type text,
                    area_mu numeric,
                    slope_degree numeric,
                    ownership_status text,
                    management_status text,
                    quality_grade text,
                    health_status text,
                    risk_level text,
                    bamboo_age text,
                    avg_dbh_cm numeric,
                    avg_height_m numeric,
                    standing_density numeric,
                    carbon_estimate_tco2e numeric,
                    yield_estimate jsonb DEFAULT '{}'::jsonb,
                    tags jsonb DEFAULT '[]'::jsonb,
                    properties jsonb DEFAULT '{}'::jsonb,
                    geometry geometry(MultiPolygon, 4326),
                    centroid geometry(Point, 4326),
                    source_batch_id uuid,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_blocks_geom ON forest_blocks USING gist (geometry)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_blocks_county ON forest_blocks (county_code)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_blocks_town ON forest_blocks (town_code)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_blocks_status ON forest_blocks (management_status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_blocks_risk ON forest_blocks (risk_level)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS forest_block_versions (
                    id uuid PRIMARY KEY,
                    forest_block_id uuid NOT NULL,
                    change_type text NOT NULL,
                    snapshot jsonb NOT NULL,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS import_batches (
                    id uuid PRIMARY KEY,
                    file_name text NOT NULL,
                    file_type text NOT NULL,
                    status text NOT NULL,
                    total_rows integer NOT NULL DEFAULT 0,
                    valid_rows integer NOT NULL DEFAULT 0,
                    invalid_rows integer NOT NULL DEFAULT 0,
                    created_by text,
                    report_json jsonb DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    completed_at timestamptz
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS forest_block_scene_links (
                    forest_block_id uuid NOT NULL,
                    scene_id text NOT NULL,
                    relation_type text NOT NULL DEFAULT 'coverage',
                    captured_at text,
                    confidence numeric,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (forest_block_id, scene_id, relation_type)
                )
                """
            )
        conn.commit()
```

- [ ] **Step 7: Update health endpoint to expose schema status**

Modify `server/app.py`:

```python
from server.modules.database import init_platform_schema, use_postgis
from server.modules.settings import get_settings
```

In the existing `health()` response, add this under `deployment`:

```python
"smartBamboo": {
    "storageBackend": get_settings().storage_backend,
    "postgisEnabled": use_postgis(),
    "schemaReady": True,
},
```

After the `app = FastAPI(...)` block and before route definitions, call:

```python
init_platform_schema()
```

- [ ] **Step 8: Run tests**

Run:

```powershell
python -m pytest tests/test_forest_blocks.py::test_platform_settings_use_json_fallback tests/test_forest_blocks.py::test_health_includes_platform_schema_status -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add server/modules/__init__.py server/modules/settings.py server/modules/auth.py server/modules/database.py server/requirements.txt server/app.py tests/conftest.py tests/test_forest_blocks.py
git commit -m "feat: add smart bamboo platform backend foundation"
```

---

### Task 2: Forest Block CRUD And Map Query API

**Files:**
- Create: `server/modules/forest_blocks.py`
- Modify: `server/app.py`
- Modify: `tests/test_forest_blocks.py`

**Interfaces:**
- Consumes:
  - `server.modules.database.init_platform_schema()`
  - `server.modules.auth.request_context(request)`
- Produces:
  - `router` mounted at `/api`
  - `ForestBlockIn`, `ForestBlockPatch`, `ForestBlockOut`
  - `list_forest_blocks(filters: ForestBlockFilters, context: AuthContext) -> dict`
  - `forest_block_feature_collection(filters: ForestBlockFilters, context: AuthContext) -> dict`

- [ ] **Step 1: Add failing CRUD and map tests**

Append to `tests/test_forest_blocks.py`:

```python
SAMPLE_GEOMETRY = {
    "type": "MultiPolygon",
    "coordinates": [[[[118.10, 26.50], [118.12, 26.50], [118.12, 26.52], [118.10, 26.52], [118.10, 26.50]]]],
}


def sample_block_payload(code="FB-001"):
    return {
        "blockCode": code,
        "name": "北坡示范林班",
        "countyCode": "350703",
        "countyName": "建阳区",
        "townCode": "350703101",
        "townName": "麻沙镇",
        "villageName": "黄坑村",
        "baseType": "self_operated",
        "operationType": "timber",
        "forestType": "毛竹",
        "areaMu": 126.5,
        "qualityGrade": "A",
        "healthStatus": "normal",
        "riskLevel": "low",
        "geometry": SAMPLE_GEOMETRY,
    }


def test_create_list_patch_and_delete_forest_block(app_client):
    create = app_client.post("/api/forest-blocks", json=sample_block_payload(), headers={"X-RS-Roles": "admin"})
    assert create.status_code == 200
    block = create.json()
    assert block["blockCode"] == "FB-001"
    assert block["areaMu"] == 126.5

    listed = app_client.get("/api/forest-blocks?countyCode=350703&q=北坡")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    patched = app_client.patch(
        f"/api/forest-blocks/{block['id']}",
        json={"riskLevel": "medium", "managementStatus": "管护中"},
        headers={"X-RS-Roles": "admin"},
    )
    assert patched.status_code == 200
    assert patched.json()["riskLevel"] == "medium"

    deleted = app_client.delete(f"/api/forest-blocks/{block['id']}", headers={"X-RS-Roles": "admin"})
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True


def test_map_geojson_filters_by_bbox(app_client):
    app_client.post("/api/forest-blocks", json=sample_block_payload("FB-002"), headers={"X-RS-Roles": "admin"})
    response = app_client.get("/api/map/forest-blocks.geojson?bbox=118.09,26.49,118.13,26.53")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    assert body["features"][0]["properties"]["blockCode"] == "FB-002"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_forest_blocks.py -v
```

Expected: FAIL with `404 Not Found` for `/api/forest-blocks`.

- [ ] **Step 3: Implement forest block module**

Create `server/modules/forest_blocks.py` with Pydantic models, JSON fallback repository, and router. Include these exact public route functions:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .auth import area_allowed, request_context, require_write_access
from .database import forest_blocks_json_path, load_json_records, save_json_records


router = APIRouter(prefix="/api", tags=["forest-blocks"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ForestBlockBase(BaseModel):
    blockCode: str = Field(min_length=1)
    name: str = Field(min_length=1)
    countyCode: str | None = None
    countyName: str | None = None
    townCode: str | None = None
    townName: str | None = None
    villageCode: str | None = None
    villageName: str | None = None
    baseType: str | None = None
    operationType: str | None = None
    forestType: str | None = None
    areaMu: float | None = None
    slopeDegree: float | None = None
    ownershipStatus: str | None = None
    managementStatus: str | None = None
    qualityGrade: str | None = None
    healthStatus: str | None = None
    riskLevel: str | None = None
    bambooAge: str | None = None
    avgDbhCm: float | None = None
    avgHeightM: float | None = None
    standingDensity: float | None = None
    carbonEstimateTco2e: float | None = None
    yieldEstimate: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any] | None = None


class ForestBlockIn(ForestBlockBase):
    pass


class ForestBlockPatch(BaseModel):
    name: str | None = None
    countyCode: str | None = None
    countyName: str | None = None
    townCode: str | None = None
    townName: str | None = None
    villageCode: str | None = None
    villageName: str | None = None
    baseType: str | None = None
    operationType: str | None = None
    forestType: str | None = None
    areaMu: float | None = None
    slopeDegree: float | None = None
    ownershipStatus: str | None = None
    managementStatus: str | None = None
    qualityGrade: str | None = None
    healthStatus: str | None = None
    riskLevel: str | None = None
    bambooAge: str | None = None
    avgDbhCm: float | None = None
    avgHeightM: float | None = None
    standingDensity: float | None = None
    carbonEstimateTco2e: float | None = None
    yieldEstimate: dict[str, Any] | None = None
    tags: list[str] | None = None
    properties: dict[str, Any] | None = None
    geometry: dict[str, Any] | None = None


def normalize_block(payload: dict[str, Any]) -> dict[str, Any]:
    block = dict(payload)
    block.setdefault("id", str(uuid.uuid4()))
    block.setdefault("createdAt", now_iso())
    block["updatedAt"] = now_iso()
    block.setdefault("deletedAt", None)
    return block


def bbox_intersects(geometry: dict[str, Any] | None, bbox: list[float] | None) -> bool:
    if not bbox or not geometry:
        return True
    coords: list[tuple[float, float]] = []
    for polygon in geometry.get("coordinates", []):
        for ring in polygon:
            for point in ring:
                coords.append((float(point[0]), float(point[1])))
    if not coords:
        return False
    west, south, east, north = bbox
    xs = [point[0] for point in coords]
    ys = [point[1] for point in coords]
    return max(xs) >= west and min(xs) <= east and max(ys) >= south and min(ys) <= north


def parse_bbox(value: str | None) -> list[float] | None:
    if not value:
        return None
    parts = [float(item.strip()) for item in value.split(",")]
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be west,south,east,north")
    return parts


def load_blocks() -> list[dict[str, Any]]:
    return [item for item in load_json_records(forest_blocks_json_path()) if not item.get("deletedAt")]


def save_blocks(blocks: list[dict[str, Any]]) -> None:
    save_json_records(forest_blocks_json_path(), blocks)


def filter_blocks(blocks: list[dict[str, Any]], request: Request, bbox: list[float] | None = None) -> list[dict[str, Any]]:
    context = request_context(request)
    query = request.query_params
    q = (query.get("q") or "").lower()
    result = []
    for block in blocks:
        if not area_allowed(context, block.get("countyCode")):
            continue
        if query.get("countyCode") and block.get("countyCode") != query.get("countyCode"):
            continue
        if query.get("townCode") and block.get("townCode") != query.get("townCode"):
            continue
        if query.get("baseType") and block.get("baseType") != query.get("baseType"):
            continue
        if query.get("operationType") and block.get("operationType") != query.get("operationType"):
            continue
        if query.get("qualityGrade") and block.get("qualityGrade") != query.get("qualityGrade"):
            continue
        if query.get("healthStatus") and block.get("healthStatus") != query.get("healthStatus"):
            continue
        if query.get("riskLevel") and block.get("riskLevel") != query.get("riskLevel"):
            continue
        if q and q not in " ".join(str(block.get(key, "")) for key in ("blockCode", "name", "countyName", "townName", "villageName")).lower():
            continue
        if not bbox_intersects(block.get("geometry"), bbox):
            continue
        result.append(block)
    return result


@router.get("/forest-blocks")
def list_forest_blocks(request: Request, limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    blocks = filter_blocks(load_blocks(), request, parse_bbox(request.query_params.get("bbox")))
    return {"items": blocks[offset : offset + limit], "total": len(blocks), "limit": limit, "offset": offset}


@router.post("/forest-blocks")
def create_forest_block(payload: ForestBlockIn, request: Request) -> dict[str, Any]:
    require_write_access(request_context(request))
    blocks = load_blocks()
    if any(item["blockCode"] == payload.blockCode for item in blocks):
        raise HTTPException(status_code=409, detail="blockCode already exists")
    block = normalize_block(payload.model_dump())
    blocks.append(block)
    save_blocks(blocks)
    return block


@router.get("/forest-blocks/{block_id}")
def get_forest_block(block_id: str, request: Request) -> dict[str, Any]:
    for block in filter_blocks(load_blocks(), request):
        if block["id"] == block_id:
            return block
    raise HTTPException(status_code=404, detail="Forest block not found")


@router.patch("/forest-blocks/{block_id}")
def patch_forest_block(block_id: str, payload: ForestBlockPatch, request: Request) -> dict[str, Any]:
    require_write_access(request_context(request))
    blocks = load_blocks()
    for index, block in enumerate(blocks):
        if block["id"] == block_id:
            changes = payload.model_dump(exclude_unset=True)
            blocks[index] = normalize_block({**block, **changes, "id": block_id, "createdAt": block.get("createdAt", now_iso())})
            save_blocks(blocks)
            return blocks[index]
    raise HTTPException(status_code=404, detail="Forest block not found")


@router.delete("/forest-blocks/{block_id}")
def delete_forest_block(block_id: str, request: Request) -> dict[str, Any]:
    require_write_access(request_context(request))
    blocks = load_blocks()
    for block in blocks:
        if block["id"] == block_id:
            block["deletedAt"] = now_iso()
            save_blocks(blocks)
            return {"ok": True, "deleted": block_id}
    raise HTTPException(status_code=404, detail="Forest block not found")


@router.get("/map/forest-blocks.geojson")
def forest_blocks_geojson(request: Request) -> dict[str, Any]:
    bbox = parse_bbox(request.query_params.get("bbox"))
    features = []
    for block in filter_blocks(load_blocks(), request, bbox):
        features.append({
            "type": "Feature",
            "id": block["id"],
            "geometry": block.get("geometry"),
            "properties": {key: value for key, value in block.items() if key != "geometry"},
        })
    return {"type": "FeatureCollection", "features": features}
```

- [ ] **Step 4: Mount router**

Modify `server/app.py`:

```python
from server.modules.forest_blocks import router as forest_blocks_router
```

After `app = FastAPI(...)` and middleware setup:

```python
app.include_router(forest_blocks_router)
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest tests/test_forest_blocks.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add server/modules/forest_blocks.py server/app.py tests/test_forest_blocks.py
git commit -m "feat: add forest block CRUD and map API"
```

---

### Task 3: Forest Block Import Pipeline

**Files:**
- Create: `server/modules/imports.py`
- Create: `tests/test_imports.py`
- Create: `data/samples/forest-blocks-sample.geojson`
- Modify: `server/app.py`

**Interfaces:**
- Consumes:
  - `server.modules.forest_blocks.create_forest_block`
  - `server.modules.forest_blocks.load_blocks`
  - `server.modules.forest_blocks.save_blocks`
- Produces:
  - `parse_import_file(file_name: str, content: bytes) -> list[ParsedForestBlock]`
  - `POST /api/imports/forest-blocks`
  - `GET /api/imports/{batch_id}`
  - `GET /api/imports/{batch_id}/report`

- [ ] **Step 1: Add failing import tests**

Create `tests/test_imports.py`:

```python
import io
import json


def geojson_bytes():
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "blockCode": "IMP-001",
                        "name": "导入林班一",
                        "countyCode": "350703",
                        "countyName": "建阳区",
                        "townName": "麻沙镇",
                        "baseType": "franchise",
                        "operationType": "dual_regular",
                        "areaMu": 88.2,
                        "qualityGrade": "B",
                        "riskLevel": "medium",
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[118.20, 26.60], [118.21, 26.60], [118.21, 26.61], [118.20, 26.61], [118.20, 26.60]]],
                    },
                }
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


def test_import_geojson_creates_blocks_and_report(app_client):
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("forest.geojson", io.BytesIO(geojson_bytes()), "application/geo+json")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["validRows"] == 1
    assert body["invalidRows"] == 0

    listed = app_client.get("/api/forest-blocks?q=导入林班一")
    assert listed.json()["total"] == 1


def test_import_rejects_missing_block_code(app_client):
    payload = json.loads(geojson_bytes().decode("utf-8"))
    payload["features"][0]["properties"].pop("blockCode")
    response = app_client.post(
        "/api/imports/forest-blocks",
        files={"file": ("bad.geojson", io.BytesIO(json.dumps(payload).encode("utf-8")), "application/geo+json")},
        data={"strategy": "upsert"},
        headers={"X-RS-Roles": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["validRows"] == 0
    assert body["invalidRows"] == 1
    assert "blockCode" in body["report"]["errors"][0]["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_imports.py -v
```

Expected: FAIL with `404 Not Found` for `/api/imports/forest-blocks`.

- [ ] **Step 3: Implement import module**

Create `server/modules/imports.py`:

```python
from __future__ import annotations

import csv
import io
import json
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from .auth import request_context, require_write_access
from .forest_blocks import load_blocks, normalize_block, save_blocks


router = APIRouter(prefix="/api", tags=["forest-imports"])
IMPORT_REPORTS: dict[str, dict[str, Any]] = {}


FIELD_ALIASES = {
    "blockCode": ["blockCode", "林班编号", "小班编号", "编号", "block_code"],
    "name": ["name", "林班名称", "小班名称", "名称"],
    "countyCode": ["countyCode", "区县编码"],
    "countyName": ["countyName", "区县", "县", "行政区"],
    "townCode": ["townCode", "乡镇编码"],
    "townName": ["townName", "乡镇", "镇"],
    "villageCode": ["villageCode", "村编码"],
    "villageName": ["villageName", "村", "行政村"],
    "baseType": ["baseType", "基地类型"],
    "operationType": ["operationType", "经营类型", "用途"],
    "forestType": ["forestType", "林种", "竹种"],
    "areaMu": ["areaMu", "面积", "亩", "面积亩"],
    "qualityGrade": ["qualityGrade", "质量等级"],
    "healthStatus": ["healthStatus", "健康状态"],
    "riskLevel": ["riskLevel", "风险等级"],
}


def pick(properties: dict[str, Any], field: str) -> Any:
    for alias in FIELD_ALIASES[field]:
        if alias in properties and properties[alias] not in (None, ""):
            return properties[alias]
    return None


def polygon_to_multi(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not geometry:
        return None
    if geometry.get("type") == "Polygon":
        return {"type": "MultiPolygon", "coordinates": [geometry.get("coordinates", [])]}
    if geometry.get("type") == "MultiPolygon":
        return geometry
    return None


def normalize_import_record(properties: dict[str, Any], geometry: dict[str, Any] | None) -> dict[str, Any]:
    record = {field: pick(properties, field) for field in FIELD_ALIASES}
    if record["areaMu"] not in (None, ""):
        record["areaMu"] = float(record["areaMu"])
    record["geometry"] = polygon_to_multi(geometry)
    record["properties"] = properties
    return record


def parse_geojson(content: bytes) -> list[dict[str, Any]]:
    body = json.loads(content.decode("utf-8-sig"))
    records = []
    for feature in body.get("features", []):
        records.append(normalize_import_record(feature.get("properties") or {}, feature.get("geometry")))
    return records


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig")
    rows = csv.DictReader(io.StringIO(text))
    return [normalize_import_record(dict(row), None) for row in rows]


def parse_xlsx(content: bytes) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.active
    headers = [str(cell.value or "").strip() for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    records = []
    for row in sheet.iter_rows(min_row=2):
        values = {headers[index]: cell.value for index, cell in enumerate(row) if index < len(headers)}
        records.append(normalize_import_record(values, None))
    return records


def parse_shapefile_zip(content: bytes) -> list[dict[str, Any]]:
    import tempfile
    import zipfile
    from pathlib import Path

    import pyogrio
    from shapely.geometry import mapping

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            archive.extractall(tmp_path)
        shapefiles = list(tmp_path.rglob("*.shp"))
        if not shapefiles:
            raise HTTPException(status_code=400, detail="Shapefile ZIP must contain a .shp file")
        frame = pyogrio.read_dataframe(shapefiles[0])
        if frame.crs:
            frame = frame.to_crs("EPSG:4326")
        records = []
        for _, row in frame.iterrows():
            values = row.to_dict()
            geometry = values.pop("geometry", None)
            records.append(
                normalize_import_record(values, mapping(geometry) if geometry is not None else None)
            )
        return records


def parse_import_file(file_name: str, content: bytes) -> list[dict[str, Any]]:
    lower = file_name.lower()
    if lower.endswith(".geojson") or lower.endswith(".json"):
        return parse_geojson(content)
    if lower.endswith(".csv"):
        return parse_csv(content)
    if lower.endswith(".xlsx"):
        return parse_xlsx(content)
    if lower.endswith(".zip"):
        return parse_shapefile_zip(content)
    raise HTTPException(status_code=400, detail="Supported formats: CSV, XLSX, GeoJSON, Shapefile ZIP")


def validate_record(record: dict[str, Any], row_number: int) -> list[str]:
    errors = []
    if not record.get("blockCode"):
        errors.append(f"row {row_number}: blockCode is required")
    if not record.get("name"):
        errors.append(f"row {row_number}: name is required")
    if record.get("geometry") is None:
        errors.append(f"row {row_number}: geometry is required for map display")
    return errors


@router.post("/imports/forest-blocks")
async def import_forest_blocks(
    request: Request,
    file: UploadFile = File(...),
    strategy: str = Form(default="upsert"),
) -> dict[str, Any]:
    require_write_access(request_context(request))
    content = await file.read()
    records = parse_import_file(file.filename or "upload", content)
    batch_id = str(uuid.uuid4())
    current = load_blocks()
    by_code = {item["blockCode"]: item for item in current}
    errors = []
    valid_rows = 0
    for row_number, record in enumerate(records, start=1):
        row_errors = validate_record(record, row_number)
        if row_errors:
            errors.extend({"row": row_number, "message": message} for message in row_errors)
            continue
        valid_rows += 1
        if record["blockCode"] in by_code and strategy == "skip":
            continue
        normalized = normalize_block(record)
        if record["blockCode"] in by_code:
            normalized["id"] = by_code[record["blockCode"]]["id"]
            normalized["createdAt"] = by_code[record["blockCode"]].get("createdAt", normalized["createdAt"])
            current = [normalized if item["blockCode"] == record["blockCode"] else item for item in current]
        else:
            current.append(normalized)
    save_blocks(current)
    report = {
        "id": batch_id,
        "fileName": file.filename,
        "fileType": (file.filename or "").split(".")[-1].lower(),
        "status": "completed",
        "totalRows": len(records),
        "validRows": valid_rows,
        "invalidRows": len(errors),
        "errors": errors,
    }
    IMPORT_REPORTS[batch_id] = report
    return {"status": "completed", **report, "report": report}


@router.get("/imports/{batch_id}")
def get_import_batch(batch_id: str) -> dict[str, Any]:
    if batch_id not in IMPORT_REPORTS:
        raise HTTPException(status_code=404, detail="Import batch not found")
    return IMPORT_REPORTS[batch_id]


@router.get("/imports/{batch_id}/report")
def get_import_report(batch_id: str) -> dict[str, Any]:
    if batch_id not in IMPORT_REPORTS:
        raise HTTPException(status_code=404, detail="Import batch not found")
    return IMPORT_REPORTS[batch_id]
```

- [ ] **Step 4: Mount import router**

Modify `server/app.py`:

```python
from server.modules.imports import router as forest_imports_router
```

After forest block router include:

```python
app.include_router(forest_imports_router)
```

- [ ] **Step 5: Add sample GeoJSON**

Create `data/samples/forest-blocks-sample.geojson`:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "blockCode": "SAMPLE-001",
        "name": "黄坑示范林班",
        "countyCode": "350703",
        "countyName": "建阳区",
        "townName": "麻沙镇",
        "villageName": "黄坑村",
        "baseType": "self_operated",
        "operationType": "timber",
        "forestType": "毛竹",
        "areaMu": 126.5,
        "qualityGrade": "A",
        "healthStatus": "normal",
        "riskLevel": "low"
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [118.10, 26.50],
            [118.12, 26.50],
            [118.12, 26.52],
            [118.10, 26.52],
            [118.10, 26.50]
          ]
        ]
      }
    }
  ]
}
```

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest tests/test_imports.py tests/test_forest_blocks.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add server/modules/imports.py server/app.py tests/test_imports.py data/samples/forest-blocks-sample.geojson
git commit -m "feat: add forest block import pipeline"
```

---

### Task 4: Admin Workbench For Forest Blocks And Imports

**Files:**
- Create: `admin.html`
- Create: `admin.css`
- Create: `admin.js`
- Modify: `zhushan-bigdata.html`
- Modify: `satellite-manager.html`

**Interfaces:**
- Consumes:
  - `GET /api/forest-blocks`
  - `POST /api/forest-blocks`
  - `PATCH /api/forest-blocks/{id}`
  - `POST /api/imports/forest-blocks`
- Produces:
  - Static admin workbench at `/admin.html`
  - `window.SmartBambooAdmin` with `loadBlocks()`, `saveActiveBlock()`, `importForestBlocks()`

- [ ] **Step 1: Create admin HTML**

Create `admin.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>智慧竹山数据管理</title>
    <link rel="stylesheet" href="admin.css" />
  </head>
  <body>
    <main class="admin-shell">
      <aside class="admin-nav">
        <header>
          <span>Smart Bamboo GIS</span>
          <h1>数据管理</h1>
        </header>
        <a href="zhushan-bigdata.html">一张图</a>
        <a href="satellite-manager.html">影像图层</a>
        <button class="active" data-view="blocks">林班台账</button>
        <button data-view="imports">批量导入</button>
      </aside>
      <section class="admin-main">
        <header class="toolbar">
          <div>
            <strong>林班台账</strong>
            <span id="statusText">等待加载</span>
          </div>
          <div class="toolbar-actions">
            <input id="apiBase" type="url" value="http://127.0.0.1:8010" />
            <input id="authRoles" type="text" placeholder="角色 admin,operator" />
            <button id="connectApi" type="button">连接</button>
          </div>
        </header>
        <section class="filters">
          <input id="keyword" type="search" placeholder="搜索林班编号、名称、乡镇、村" />
          <select id="baseType">
            <option value="">全部基地</option>
            <option value="self_operated">自营</option>
            <option value="franchise">加盟</option>
          </select>
          <select id="operationType">
            <option value="">全部用途</option>
            <option value="timber">竹材用林</option>
            <option value="dual_regular">常规笋竹两用林</option>
            <option value="dual_high_yield">高产笋竹两用林</option>
            <option value="understory">林下经济</option>
          </select>
          <select id="riskLevel">
            <option value="">全部风险</option>
            <option value="low">低</option>
            <option value="medium">中</option>
            <option value="high">高</option>
            <option value="critical">严重</option>
          </select>
        </section>
        <section class="content-grid">
          <div class="table-panel">
            <div class="panel-title">
              <h2>林班列表</h2>
              <button id="newBlock" type="button">新增</button>
            </div>
            <table>
              <thead>
                <tr>
                  <th>编号</th>
                  <th>名称</th>
                  <th>区县</th>
                  <th>乡镇</th>
                  <th>面积</th>
                  <th>风险</th>
                </tr>
              </thead>
              <tbody id="blockRows"></tbody>
            </table>
          </div>
          <form class="detail-panel" id="blockForm">
            <div class="panel-title">
              <h2>林班详情</h2>
              <button type="submit">保存</button>
            </div>
            <input id="blockId" type="hidden" />
            <label>编号<input id="blockCode" required /></label>
            <label>名称<input id="name" required /></label>
            <label>区县编码<input id="countyCode" /></label>
            <label>区县名称<input id="countyName" /></label>
            <label>乡镇名称<input id="townName" /></label>
            <label>村名<input id="villageName" /></label>
            <label>基地类型<input id="baseTypeEdit" /></label>
            <label>经营类型<input id="operationTypeEdit" /></label>
            <label>面积亩<input id="areaMu" type="number" step="0.01" /></label>
            <label>质量等级<input id="qualityGrade" /></label>
            <label>健康状态<input id="healthStatus" /></label>
            <label>风险等级<input id="riskLevelEdit" /></label>
            <label>GeoJSON 几何<textarea id="geometry" rows="8"></textarea></label>
          </form>
        </section>
        <section class="import-panel">
          <h2>批量导入</h2>
          <form id="importForm">
            <input id="importFile" type="file" accept=".geojson,.json,.csv,.xlsx,.zip" />
            <select id="strategy">
              <option value="upsert">重复编号时更新</option>
              <option value="skip">重复编号时跳过</option>
            </select>
            <button type="submit">上传导入</button>
          </form>
          <pre id="importReport"></pre>
        </section>
      </section>
    </main>
    <script src="admin.js"></script>
  </body>
</html>
```

- [ ] **Step 2: Create admin CSS**

Create `admin.css` with stable, dense operations styling:

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: "Microsoft YaHei", Arial, sans-serif; background: #eef3f2; color: #172521; }
button, input, select, textarea { font: inherit; }
.admin-shell { min-height: 100vh; display: grid; grid-template-columns: 220px 1fr; }
.admin-nav { background: #0e2d28; color: #fff; padding: 20px 16px; display: flex; flex-direction: column; gap: 10px; }
.admin-nav header span { color: #8ed8bf; font-size: 12px; }
.admin-nav h1 { margin: 4px 0 16px; font-size: 22px; }
.admin-nav a, .admin-nav button { color: #e7fff5; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12); padding: 10px 12px; border-radius: 6px; text-align: left; text-decoration: none; cursor: pointer; }
.admin-nav .active { background: #1f7a5f; }
.admin-main { padding: 18px; display: grid; gap: 14px; }
.toolbar, .filters, .panel-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.toolbar { background: #fff; border: 1px solid #d5dfdc; padding: 12px 14px; border-radius: 8px; }
.toolbar span { display: block; color: #5e716b; font-size: 13px; margin-top: 3px; }
.toolbar-actions { display: flex; gap: 8px; }
.toolbar-actions input { width: 220px; }
.filters { background: #fff; border: 1px solid #d5dfdc; padding: 10px; border-radius: 8px; justify-content: flex-start; }
.filters input { width: 320px; }
input, select, textarea { border: 1px solid #bfd0cb; border-radius: 6px; padding: 8px 10px; background: #fff; min-height: 36px; }
button { border: 0; border-radius: 6px; padding: 8px 12px; background: #176f56; color: #fff; cursor: pointer; }
.content-grid { display: grid; grid-template-columns: minmax(520px, 1fr) 380px; gap: 14px; align-items: start; }
.table-panel, .detail-panel, .import-panel { background: #fff; border: 1px solid #d5dfdc; border-radius: 8px; padding: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { border-bottom: 1px solid #e4ece9; padding: 9px 8px; text-align: left; }
tbody tr { cursor: pointer; }
tbody tr:hover, tbody tr.active { background: #edf8f3; }
.detail-panel { display: grid; gap: 10px; }
.detail-panel label { display: grid; gap: 5px; color: #4f625c; font-size: 13px; }
.detail-panel input, .detail-panel textarea { color: #172521; }
.import-panel { display: grid; gap: 10px; }
.import-panel form { display: flex; gap: 10px; align-items: center; }
pre { margin: 0; background: #0f1f1c; color: #c8f7e3; border-radius: 6px; padding: 12px; min-height: 96px; overflow: auto; }
@media (max-width: 960px) {
  .admin-shell { grid-template-columns: 1fr; }
  .admin-nav { position: static; }
  .content-grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 3: Create admin JS**

Create `admin.js`:

```javascript
const state = { apiBase: "http://127.0.0.1:8010", blocks: [], active: null };

const $ = (id) => document.querySelector(id);
const els = {
  apiBase: $("#apiBase"),
  authRoles: $("#authRoles"),
  connectApi: $("#connectApi"),
  statusText: $("#statusText"),
  keyword: $("#keyword"),
  baseType: $("#baseType"),
  operationType: $("#operationType"),
  riskLevel: $("#riskLevel"),
  blockRows: $("#blockRows"),
  blockForm: $("#blockForm"),
  blockId: $("#blockId"),
  blockCode: $("#blockCode"),
  name: $("#name"),
  countyCode: $("#countyCode"),
  countyName: $("#countyName"),
  townName: $("#townName"),
  villageName: $("#villageName"),
  baseTypeEdit: $("#baseTypeEdit"),
  operationTypeEdit: $("#operationTypeEdit"),
  areaMu: $("#areaMu"),
  qualityGrade: $("#qualityGrade"),
  healthStatus: $("#healthStatus"),
  riskLevelEdit: $("#riskLevelEdit"),
  geometry: $("#geometry"),
  newBlock: $("#newBlock"),
  importForm: $("#importForm"),
  importFile: $("#importFile"),
  strategy: $("#strategy"),
  importReport: $("#importReport"),
};

function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-RS-Roles", els.authRoles.value.trim() || "admin");
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  return fetch(`${state.apiBase}${path}`, { ...options, headers }).then(async (response) => {
    if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
    return response.json();
  });
}

function params() {
  const query = new URLSearchParams();
  if (els.keyword.value.trim()) query.set("q", els.keyword.value.trim());
  if (els.baseType.value) query.set("baseType", els.baseType.value);
  if (els.operationType.value) query.set("operationType", els.operationType.value);
  if (els.riskLevel.value) query.set("riskLevel", els.riskLevel.value);
  query.set("limit", "500");
  return query.toString();
}

function renderRows() {
  els.blockRows.innerHTML = state.blocks.map((block) => `
    <tr data-id="${block.id}" class="${state.active && state.active.id === block.id ? "active" : ""}">
      <td>${block.blockCode || ""}</td>
      <td>${block.name || ""}</td>
      <td>${block.countyName || ""}</td>
      <td>${block.townName || ""}</td>
      <td>${block.areaMu || ""}</td>
      <td>${block.riskLevel || ""}</td>
    </tr>
  `).join("");
}

function fillForm(block) {
  state.active = block;
  els.blockId.value = block?.id || "";
  els.blockCode.value = block?.blockCode || "";
  els.name.value = block?.name || "";
  els.countyCode.value = block?.countyCode || "";
  els.countyName.value = block?.countyName || "";
  els.townName.value = block?.townName || "";
  els.villageName.value = block?.villageName || "";
  els.baseTypeEdit.value = block?.baseType || "";
  els.operationTypeEdit.value = block?.operationType || "";
  els.areaMu.value = block?.areaMu || "";
  els.qualityGrade.value = block?.qualityGrade || "";
  els.healthStatus.value = block?.healthStatus || "";
  els.riskLevelEdit.value = block?.riskLevel || "";
  els.geometry.value = JSON.stringify(block?.geometry || null, null, 2);
  renderRows();
}

async function loadBlocks() {
  state.apiBase = els.apiBase.value.replace(/\/+$/, "");
  els.statusText.textContent = "加载中";
  const body = await api(`/api/forest-blocks?${params()}`);
  state.blocks = body.items || [];
  els.statusText.textContent = `${body.total || 0} 个林班`;
  renderRows();
}

function formPayload() {
  return {
    blockCode: els.blockCode.value.trim(),
    name: els.name.value.trim(),
    countyCode: els.countyCode.value.trim(),
    countyName: els.countyName.value.trim(),
    townName: els.townName.value.trim(),
    villageName: els.villageName.value.trim(),
    baseType: els.baseTypeEdit.value.trim(),
    operationType: els.operationTypeEdit.value.trim(),
    areaMu: els.areaMu.value ? Number(els.areaMu.value) : null,
    qualityGrade: els.qualityGrade.value.trim(),
    healthStatus: els.healthStatus.value.trim(),
    riskLevel: els.riskLevelEdit.value.trim(),
    geometry: JSON.parse(els.geometry.value || "null"),
  };
}

async function saveActiveBlock(event) {
  event.preventDefault();
  const payload = formPayload();
  const saved = els.blockId.value
    ? await api(`/api/forest-blocks/${els.blockId.value}`, { method: "PATCH", body: JSON.stringify(payload) })
    : await api("/api/forest-blocks", { method: "POST", body: JSON.stringify(payload) });
  await loadBlocks();
  fillForm(saved);
}

async function importForestBlocks(event) {
  event.preventDefault();
  const file = els.importFile.files[0];
  if (!file) return;
  const data = new FormData();
  data.set("file", file);
  data.set("strategy", els.strategy.value);
  const report = await api("/api/imports/forest-blocks", { method: "POST", body: data });
  els.importReport.textContent = JSON.stringify(report.report || report, null, 2);
  await loadBlocks();
}

els.connectApi.addEventListener("click", loadBlocks);
[els.keyword, els.baseType, els.operationType, els.riskLevel].forEach((el) => el.addEventListener("change", loadBlocks));
els.keyword.addEventListener("input", () => window.clearTimeout(window.__blockSearchTimer) || (window.__blockSearchTimer = window.setTimeout(loadBlocks, 250)));
els.blockRows.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-id]");
  if (!row) return;
  fillForm(state.blocks.find((block) => block.id === row.dataset.id));
});
els.newBlock.addEventListener("click", () => fillForm({ geometry: null }));
els.blockForm.addEventListener("submit", saveActiveBlock);
els.importForm.addEventListener("submit", importForestBlocks);
loadBlocks().catch((error) => {
  els.statusText.textContent = `连接失败：${error.message}`;
});

window.SmartBambooAdmin = { loadBlocks, saveActiveBlock, importForestBlocks };
```

- [ ] **Step 4: Link admin from existing pages**

Modify `zhushan-bigdata.html` inside `<nav class="bottom-dock">`:

```html
<button onclick="window.location.href='admin.html'" type="button"><span>▦</span>数据</button>
```

Modify `satellite-manager.html` inside `.toolbar-actions`:

```html
<button onclick="window.location.href='admin.html'" type="button">数据管理</button>
```

- [ ] **Step 5: Run smoke test**

Run:

```powershell
python -m pytest tests/test_forest_blocks.py tests/test_imports.py -v
python -m uvicorn server.app:app --host 127.0.0.1 --port 8010
```

Expected: tests PASS; `http://127.0.0.1:8010/admin.html` opens and can list imported forest blocks.

- [ ] **Step 6: Commit**

```powershell
git add admin.html admin.css admin.js zhushan-bigdata.html satellite-manager.html
git commit -m "feat: add forest block admin workbench"
```

---

### Task 5: Smart Bamboo Map Uses Live Forest Blocks

**Files:**
- Modify: `zhushan-bigdata.js`
- Modify: `zhushan-bigdata.css`
- Modify: `server/modules/forest_blocks.py`
- Modify: `tests/test_forest_blocks.py`

**Interfaces:**
- Consumes:
  - `GET /api/map/forest-blocks.geojson`
  - Existing `gisMap`, `gisLayers`, and OpenLayers setup in `zhushan-bigdata.js`
- Produces:
  - `loadLiveForestBlocks(filters) -> Promise<void>`
  - Live vector source replacing static forest block polygons when API is available
  - Existing demo data fallback when API is unavailable

- [ ] **Step 1: Add backend summary test**

Append to `tests/test_forest_blocks.py`:

```python
def test_forest_block_summary_counts_by_risk(app_client):
    app_client.post("/api/forest-blocks", json=sample_block_payload("FB-SUM-1"), headers={"X-RS-Roles": "admin"})
    risky = sample_block_payload("FB-SUM-2")
    risky["riskLevel"] = "high"
    risky["qualityGrade"] = "C"
    app_client.post("/api/forest-blocks", json=risky, headers={"X-RS-Roles": "admin"})
    response = app_client.get("/api/map/forest-blocks/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["riskLevel"]["low"] == 1
    assert body["riskLevel"]["high"] == 1
```

- [ ] **Step 2: Implement summary endpoint**

Add to `server/modules/forest_blocks.py`:

```python
@router.get("/map/forest-blocks/summary")
def forest_blocks_summary(request: Request) -> dict[str, Any]:
    blocks = filter_blocks(load_blocks(), request, parse_bbox(request.query_params.get("bbox")))
    summary: dict[str, Any] = {"total": len(blocks), "riskLevel": {}, "qualityGrade": {}, "baseType": {}}
    for block in blocks:
        for key in ("riskLevel", "qualityGrade", "baseType"):
            value = block.get(key) or "unknown"
            summary[key][value] = summary[key].get(value, 0) + 1
    return summary
```

- [ ] **Step 3: Run backend tests**

Run:

```powershell
python -m pytest tests/test_forest_blocks.py -v
```

Expected: PASS.

- [ ] **Step 4: Add live map loader**

In `zhushan-bigdata.js`, add this function near existing map initialization helpers:

```javascript
async function loadLiveForestBlocks() {
  if (!gisMap || !gisLayers.bamboo) return;
  const apiBase = ZHUSHAN_REMOTE_API_BASE || "http://127.0.0.1:8010";
  const extent = ol.proj.transformExtent(gisMap.getView().calculateExtent(gisMap.getSize()), "EPSG:3857", "EPSG:4326");
  const params = new URLSearchParams({ bbox: extent.join(",") });
  const response = await fetch(`${apiBase}/api/map/forest-blocks.geojson?${params.toString()}`);
  if (!response.ok) throw new Error(`林班接口错误 ${response.status}`);
  const geojson = await response.json();
  const features = new ol.format.GeoJSON().readFeatures(geojson, {
    dataProjection: "EPSG:4326",
    featureProjection: "EPSG:3857",
  });
  const source = gisLayers.bamboo.getSource();
  source.clear();
  source.addFeatures(features);
}
```

After `initRemoteSensingSdk();` in `initMap()` or the closest existing map init function, call:

```javascript
loadLiveForestBlocks().catch((error) => console.warn("林班 API 不可用，保留本地示例林班", error));
gisMap.on("moveend", () => loadLiveForestBlocks().catch(() => {}));
```

- [ ] **Step 5: Keep click detail working**

In the existing map click handler, when a clicked feature has `blockCode`, call the same info card renderer used for demo blocks. Add this adapter:

```javascript
function forestBlockFromFeature(feature) {
  const props = feature.getProperties();
  return {
    id: props.id,
    name: props.name || props.blockCode || "林班",
    code: props.blockCode,
    status: props.managementStatus || props.healthStatus || "已建档",
    area: props.areaMu ? `${props.areaMu} 亩` : "面积未填",
    town: `${props.countyName || ""}${props.townName || ""}${props.villageName || ""}`,
    grade: props.qualityGrade || "-",
    risk: props.riskLevel || "-",
    properties: props,
  };
}
```

- [ ] **Step 6: Run smoke test**

Run:

```powershell
python -m pytest tests/test_forest_blocks.py -v
python -m uvicorn server.app:app --host 127.0.0.1 --port 8010
```

Expected: tests PASS; `zhushan-bigdata.html` still opens; if forest blocks are imported, the bamboo layer is API-driven; if API is offline, demo polygons remain.

- [ ] **Step 7: Commit**

```powershell
git add server/modules/forest_blocks.py tests/test_forest_blocks.py zhushan-bigdata.js zhushan-bigdata.css
git commit -m "feat: connect smart bamboo map to forest block API"
```

---

### Task 6: Forest Block To Imagery Links

**Files:**
- Create: `server/modules/forest_scene_links.py`
- Create: `tests/test_forest_scene_links.py`
- Modify: `server/app.py`
- Modify: `admin.html`
- Modify: `admin.js`
- Modify: `zhushan-bigdata.js`

**Interfaces:**
- Consumes:
  - Existing scene catalog API `/api/scenes`
  - Existing forest block CRUD API
- Produces:
  - `GET /api/forest-blocks/{id}/scenes`
  - `POST /api/forest-blocks/{id}/scenes`
  - `DELETE /api/forest-blocks/{id}/scenes/{scene_id}`

- [ ] **Step 1: Add failing link tests**

Create `tests/test_forest_scene_links.py`:

```python
from tests.test_forest_blocks import sample_block_payload


def test_link_scene_to_forest_block(app_client):
    block = app_client.post("/api/forest-blocks", json=sample_block_payload("LINK-001"), headers={"X-RS-Roles": "admin"}).json()
    response = app_client.post(
        f"/api/forest-blocks/{block['id']}/scenes",
        json={"sceneId": "cog-demo-001", "relationType": "orthophoto", "capturedAt": "2026-06-10", "confidence": 0.92},
        headers={"X-RS-Roles": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["sceneId"] == "cog-demo-001"

    listed = app_client.get(f"/api/forest-blocks/{block['id']}/scenes")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["relationType"] == "orthophoto"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_forest_scene_links.py -v
```

Expected: FAIL with `404 Not Found` for scene link endpoint.

- [ ] **Step 3: Implement link module**

Create `server/modules/forest_scene_links.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import request_context, require_write_access
from .database import get_data_dir, load_json_records, save_json_records
from .forest_blocks import load_blocks


router = APIRouter(prefix="/api", tags=["forest-scene-links"])


class SceneLinkIn(BaseModel):
    sceneId: str = Field(min_length=1)
    relationType: str = "coverage"
    capturedAt: str | None = None
    confidence: float | None = None


def link_path() -> Path:
    return get_data_dir() / "forest-blocks" / "forest_block_scene_links.json"


def block_exists(block_id: str) -> bool:
    return any(block["id"] == block_id for block in load_blocks())


@router.get("/forest-blocks/{block_id}/scenes")
def list_block_scenes(block_id: str) -> dict[str, Any]:
    if not block_exists(block_id):
        raise HTTPException(status_code=404, detail="Forest block not found")
    links = [item for item in load_json_records(link_path()) if item["forestBlockId"] == block_id]
    return {"items": links, "total": len(links)}


@router.post("/forest-blocks/{block_id}/scenes")
def link_block_scene(block_id: str, payload: SceneLinkIn, request: Request) -> dict[str, Any]:
    require_write_access(request_context(request))
    if not block_exists(block_id):
        raise HTTPException(status_code=404, detail="Forest block not found")
    links = load_json_records(link_path())
    link = {"forestBlockId": block_id, **payload.model_dump()}
    links = [
        item
        for item in links
        if not (
            item["forestBlockId"] == block_id
            and item["sceneId"] == payload.sceneId
            and item["relationType"] == payload.relationType
        )
    ]
    links.append(link)
    save_json_records(link_path(), links)
    return link


@router.delete("/forest-blocks/{block_id}/scenes/{scene_id}")
def unlink_block_scene(block_id: str, scene_id: str, request: Request) -> dict[str, Any]:
    require_write_access(request_context(request))
    links = load_json_records(link_path())
    kept = [item for item in links if not (item["forestBlockId"] == block_id and item["sceneId"] == scene_id)]
    save_json_records(link_path(), kept)
    return {"ok": True, "deleted": scene_id}
```

- [ ] **Step 4: Mount link router**

Modify `server/app.py`:

```python
from server.modules.forest_scene_links import router as forest_scene_links_router
```

After import router include:

```python
app.include_router(forest_scene_links_router)
```

- [ ] **Step 5: Add admin imagery UI**

In `admin.html`, inside the detail panel after `geometry` label, add:

```html
<section class="scene-link-panel">
  <h3>关联影像</h3>
  <div class="scene-link-row">
    <input id="sceneId" placeholder="scene id，例如 cog-xxxx" />
    <input id="relationType" placeholder="关系 orthophoto/coverage" />
    <button id="linkScene" type="button">关联</button>
  </div>
  <div id="linkedScenes"></div>
</section>
```

In `admin.js`, add elements:

```javascript
sceneId: $("#sceneId"),
relationType: $("#relationType"),
linkScene: $("#linkScene"),
linkedScenes: $("#linkedScenes"),
```

Add functions:

```javascript
async function loadSceneLinks(block) {
  if (!block?.id) {
    els.linkedScenes.innerHTML = "";
    return;
  }
  const body = await api(`/api/forest-blocks/${block.id}/scenes`);
  els.linkedScenes.innerHTML = (body.items || []).map((item) => `<p>${item.sceneId} · ${item.relationType}</p>`).join("");
}

async function linkSceneToActive() {
  if (!state.active?.id || !els.sceneId.value.trim()) return;
  await api(`/api/forest-blocks/${state.active.id}/scenes`, {
    method: "POST",
    body: JSON.stringify({
      sceneId: els.sceneId.value.trim(),
      relationType: els.relationType.value.trim() || "coverage",
    }),
  });
  await loadSceneLinks(state.active);
}
```

At the end of `fillForm(block)`, call:

```javascript
loadSceneLinks(block).catch(() => {});
```

Bind:

```javascript
els.linkScene.addEventListener("click", linkSceneToActive);
```

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest tests/test_forest_scene_links.py tests/test_forest_blocks.py tests/test_imports.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add server/modules/forest_scene_links.py server/app.py tests/test_forest_scene_links.py admin.html admin.js zhushan-bigdata.js
git commit -m "feat: link forest blocks to imagery scenes"
```

---

### Task 7: Permissions Consistency For New APIs

**Files:**
- Modify: `server/modules/auth.py`
- Modify: `server/modules/forest_blocks.py`
- Modify: `server/modules/imports.py`
- Modify: `server/modules/forest_scene_links.py`
- Modify: `tests/test_forest_blocks.py`
- Modify: `tests/test_imports.py`

**Interfaces:**
- Consumes:
  - `AuthContext`
  - Forest block `countyCode`
- Produces:
  - Read filtering by `X-RS-Areas`
  - Write protection by `X-RS-Roles`

- [ ] **Step 1: Add failing permission tests**

Append to `tests/test_forest_blocks.py`:

```python
def test_area_context_filters_forest_blocks(app_client):
    app_client.post("/api/forest-blocks", json=sample_block_payload("AREA-001"), headers={"X-RS-Roles": "admin"})
    other = sample_block_payload("AREA-002")
    other["countyCode"] = "350702"
    other["countyName"] = "延平区"
    app_client.post("/api/forest-blocks", json=other, headers={"X-RS-Roles": "admin"})

    response = app_client.get("/api/forest-blocks", headers={"X-RS-Areas": "350703"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["countyCode"] == "350703"


def test_non_writer_role_cannot_patch(app_client):
    block = app_client.post("/api/forest-blocks", json=sample_block_payload("PERM-001"), headers={"X-RS-Roles": "admin"}).json()
    response = app_client.patch(
        f"/api/forest-blocks/{block['id']}",
        json={"riskLevel": "high"},
        headers={"X-RS-Roles": "viewer"},
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run tests to verify behavior**

Run:

```powershell
python -m pytest tests/test_forest_blocks.py::test_area_context_filters_forest_blocks tests/test_forest_blocks.py::test_non_writer_role_cannot_patch -v
```

Expected: first test may PASS from Task 2; second must PASS after `require_write_access` is active. If either fails, continue with Step 3.

- [ ] **Step 3: Tighten write roles**

Modify `server/modules/auth.py` `require_write_access`:

```python
def require_write_access(context: AuthContext) -> None:
    if not context.roles:
        return
    if has_admin_role(context) or "operator" in context.roles or "gis-admin" in context.roles:
        return
    raise HTTPException(status_code=403, detail="Write access denied")
```

This keeps local no-header development open, but denies explicit read-only roles.

- [ ] **Step 4: Ensure imports and scene links use write checks**

Confirm these calls exist:

```python
require_write_access(request_context(request))
```

in:

- `create_forest_block`
- `patch_forest_block`
- `delete_forest_block`
- `import_forest_blocks`
- `link_block_scene`
- `unlink_block_scene`

- [ ] **Step 5: Run all backend tests**

Run:

```powershell
python -m pytest tests/test_forest_blocks.py tests/test_imports.py tests/test_forest_scene_links.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add server/modules/auth.py server/modules/forest_blocks.py server/modules/imports.py server/modules/forest_scene_links.py tests/test_forest_blocks.py tests/test_imports.py
git commit -m "feat: enforce forest data permissions"
```

---

### Task 8: Docker Compose Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Create: `deploy/nginx-smart-bamboo.conf`
- Create: `docs/deploy-smart-bamboo-platform.md`
- Modify: `server/README.md`
- Modify: `README_NAS_DEPLOY.md`

**Interfaces:**
- Consumes:
  - FastAPI app at `server.app:app`
  - PostGIS image `postgis/postgis:16-3.4`
- Produces:
  - `docker compose up --build` deployment
  - `/api/health` working with PostGIS env vars

- [ ] **Step 1: Create Dockerfile**

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin libgdal-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt

COPY . /app

EXPOSE 8010
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8010"]
```

- [ ] **Step 2: Create docker ignore**

Create `.dockerignore`:

```text
.git
.venv
node_modules
.android-tools
.edge-test-profile
data/remote-sensing/uploads
data/remote-sensing/cogs
data/remote-sensing/tile-cache
data/remote-sensing/basemap-cache
*.zip
*.apk
__pycache__
.pytest_cache
```

- [ ] **Step 3: Create compose file**

Create `docker-compose.yml`:

```yaml
services:
  db:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: smart_bamboo
      POSTGRES_USER: smart_bamboo
      POSTGRES_PASSWORD: smart_bamboo_dev
    ports:
      - "5433:5432"
    volumes:
      - smart_bamboo_pg:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U smart_bamboo -d smart_bamboo"]
      interval: 10s
      timeout: 5s
      retries: 10

  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
    environment:
      REMOTE_SENSING_PORT: "8010"
      REMOTE_SENSING_DATA_DIR: /data/remote-sensing
      SMART_BAMBOO_STORAGE_BACKEND: postgis
      SMART_BAMBOO_DATABASE_URL: postgresql://smart_bamboo:smart_bamboo_dev@db:5432/smart_bamboo
      REMOTE_SENSING_CATALOG_BACKEND: postgis
      REMOTE_SENSING_DATABASE_URL: postgresql://smart_bamboo:smart_bamboo_dev@db:5432/smart_bamboo
      REMOTE_SENSING_SERVE_STATIC: "1"
      REMOTE_SENSING_CORS_ORIGINS: "*"
    ports:
      - "8010:8010"
    volumes:
      - ./data:/data

  geoserver:
    image: docker.osgeo.org/geoserver:2.25.x
    profiles: ["geoserver"]
    ports:
      - "8080:8080"
    volumes:
      - geoserver_data:/opt/geoserver_data

volumes:
  smart_bamboo_pg:
  geoserver_data:
```

- [ ] **Step 4: Create nginx sample**

Create `deploy/nginx-smart-bamboo.conf`:

```nginx
server {
    listen 80;
    server_name smart-bamboo.example.com;

    client_max_body_size 0;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    location / {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

- [ ] **Step 5: Create deployment guide**

Create `docs/deploy-smart-bamboo-platform.md`:

```markdown
# 智慧竹山 GIS 数据底座部署说明

## 本地 Docker 启动

```powershell
docker compose up --build
```

打开：

```text
http://127.0.0.1:8010/admin.html
http://127.0.0.1:8010/zhushan-bigdata.html
http://127.0.0.1:8010/satellite-manager.html
http://127.0.0.1:8010/api/health
```

## 导入示例林班

在 `admin.html` 的批量导入中选择：

```text
data/samples/forest-blocks-sample.geojson
```

导入后刷新一张图，竹林林班图层会显示示例面。

## 生产环境变量

```text
SMART_BAMBOO_STORAGE_BACKEND=postgis
SMART_BAMBOO_DATABASE_URL=postgresql://user:password@db:5432/smart_bamboo
REMOTE_SENSING_DATA_DIR=/data/remote-sensing
REMOTE_SENSING_CATALOG_BACKEND=postgis
REMOTE_SENSING_DATABASE_URL=postgresql://user:password@db:5432/smart_bamboo
REMOTE_SENSING_AUTH_REQUIRED=1
REMOTE_SENSING_API_TOKENS={"admin-token":{"user":"admin","roles":["admin"],"projects":["*"],"areas":["*"]}}
REMOTE_SENSING_TIANDITU_TK=your-tianditu-key
```

## 验收检查

```text
GET /api/health
GET /api/forest-blocks
GET /api/map/forest-blocks.geojson
GET /api/scenes
```
```

- [ ] **Step 6: Link docs**

Append to `server/README.md`:

```markdown
## 智慧竹山 GIS 数据底座

林班、导入、地图筛选与 Docker Compose 部署说明见：

```text
docs/deploy-smart-bamboo-platform.md
```
```

Append to `README_NAS_DEPLOY.md`:

```markdown
## 智慧竹山 GIS 数据底座

正式化后的林班数据管理、PostGIS、Docker Compose 和部署检查见：

```text
docs/deploy-smart-bamboo-platform.md
```
```

- [ ] **Step 7: Run Docker verification**

Run:

```powershell
docker compose config
```

Expected: configuration renders without errors.

If Docker is available, run:

```powershell
docker compose up --build -d
Start-Sleep -Seconds 20
Invoke-RestMethod http://127.0.0.1:8010/api/health
docker compose down
```

Expected: health response includes `ok: true` and `deployment.smartBamboo.storageBackend` as `postgis`.

- [ ] **Step 8: Commit**

```powershell
git add Dockerfile docker-compose.yml .dockerignore deploy/nginx-smart-bamboo.conf docs/deploy-smart-bamboo-platform.md server/README.md README_NAS_DEPLOY.md
git commit -m "feat: add smart bamboo docker deployment"
```

---

### Task 9: Regression, Polish, And Release Notes

**Files:**
- Modify: `admin.html`
- Modify: `admin.css`
- Modify: `admin.js`
- Modify: `zhushan-bigdata.js`
- Modify: `satellite-manager.js`
- Create: `docs/smart-bamboo-gis-mvp-release.md`

**Interfaces:**
- Consumes all completed APIs and static pages.
- Produces final user-facing MVP notes and verification evidence.

- [ ] **Step 1: Run full backend test suite**

Run:

```powershell
python -m pytest tests/test_forest_blocks.py tests/test_imports.py tests/test_forest_scene_links.py -v
```

Expected: PASS.

- [ ] **Step 2: Run local app health check**

Run:

```powershell
python -m uvicorn server.app:app --host 127.0.0.1 --port 8010
```

Open these URLs:

```text
http://127.0.0.1:8010/api/health
http://127.0.0.1:8010/admin.html
http://127.0.0.1:8010/zhushan-bigdata.html
http://127.0.0.1:8010/satellite-manager.html
```

Expected: all load; console has no fatal JavaScript errors; existing satellite manager still connects.

- [ ] **Step 3: Manually verify forest data workflow**

Use `admin.html`:

1. Import `data/samples/forest-blocks-sample.geojson`.
2. Confirm report shows `validRows: 1`.
3. Search `黄坑`.
4. Edit risk level from `low` to `medium`.
5. Save.
6. Open `zhushan-bigdata.html`.
7. Confirm bamboo layer loads from API and the clicked feature shows updated risk.

- [ ] **Step 4: Manually verify satellite workflow remains intact**

Use `satellite-manager.html`:

1. Click `连接`.
2. Confirm `/api/health` status is online.
3. Click `同步 COG`.
4. Confirm empty catalog does not break the page.
5. Confirm cache status loads.

- [ ] **Step 5: Create release notes**

Create `docs/smart-bamboo-gis-mvp-release.md`:

```markdown
# 智慧竹山 GIS 数据底座 MVP 发布说明

## 已完成

- 林班数据 API：新增、查询、编辑、删除、地图 GeoJSON。
- 批量导入：GeoJSON、CSV、XLSX。
- 数据管理后台：林班列表、筛选、详情编辑、导入报告。
- 智慧竹山一张图：支持从后端林班 API 加载数据，保留本地演示兜底。
- 林班与遥感影像关联：支持按林班记录 scene id。
- 权限：支持角色和区域上下文。
- 部署：Docker Compose 启动 FastAPI + PostGIS。

## 验收命令

```powershell
python -m pytest tests/test_forest_blocks.py tests/test_imports.py tests/test_forest_scene_links.py -v
docker compose config
```

## 入口

```text
admin.html
zhushan-bigdata.html
satellite-manager.html
```
```

- [ ] **Step 6: Final status check**

Run:

```powershell
git status --short
```

Expected: only intended release-note and polish files are modified.

- [ ] **Step 7: Commit**

```powershell
git add admin.html admin.css admin.js zhushan-bigdata.js satellite-manager.js docs/smart-bamboo-gis-mvp-release.md
git commit -m "docs: record smart bamboo GIS MVP verification"
```

---

## Self-Review

Spec coverage:

- Forest-block PostGIS and JSON fallback: Task 1 and Task 2.
- CRUD and map query API: Task 2.
- Import and report: Task 3.
- Admin backend UI: Task 4.
- Smart Bamboo map integration: Task 5.
- Imagery association: Task 6.
- Permissions: Task 7.
- Docker Compose deployment: Task 8.
- Regression and release notes: Task 9.

Completion scan:

- The plan has no unresolved markers or unspecified file references.

Type consistency:

- Frontend uses camelCase API fields: `blockCode`, `areaMu`, `riskLevel`.
- Backend JSON fallback stores the same camelCase fields returned by APIs.
- API route prefixes are consistently `/api/forest-blocks`, `/api/imports`, and `/api/map/forest-blocks`.

Scope:

- The plan implements first-stage GIS data底座 only. 托管协议、交易、碳汇、AI 模型 and mobile role-specific apps remain outside this implementation plan.
