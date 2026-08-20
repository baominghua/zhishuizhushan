from __future__ import annotations

import importlib
import io
import json

from fastapi.testclient import TestClient

from tests.test_forest_blocks import FakeCursor, install_fake_psycopg


def reload_app_module():
    import server.modules.settings as settings

    settings.get_settings.cache_clear()
    importlib.reload(settings)
    settings.get_settings.cache_clear()
    import server.app as app_module

    importlib.reload(app_module)
    settings.get_settings.cache_clear()
    return app_module


def sample_task(task_id: str = "task-pg-001") -> dict[str, object]:
    return {
        "id": task_id,
        "type": "upload",
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "sceneId": "scene-pg-001",
        "name": "PostGIS test scene",
        "fileName": "scene.tif",
        "sourcePath": "D:/remote/input/scene.tif",
        "cogPath": "D:/remote/cogs/scene.tif",
        "createdAt": "2026-07-07T00:00:00+00:00",
        "updatedAt": "2026-07-07T00:00:00+00:00",
    }


def sample_scene(scene_id: str = "scene-publish-001") -> dict[str, object]:
    return {
        "id": scene_id,
        "source": "server",
        "storage": "COG",
        "name": "Xiaoqiao bamboo orthophoto",
        "fileName": "xiaoqiao.tif",
        "fileType": "image/tiff",
        "size": 1024,
        "satellite": "UAV",
        "sensor": "RGB",
        "capturedAt": "2026-07-07",
        "projectId": "zhushan",
        "areaCode": "350783",
        "allowedRoles": [],
        "allowedUsers": [],
        "resolution": "0.1m",
        "bounds": [117.55, 26.05, 118.85, 27.2],
        "crs": "EPSG:4326",
        "width": 256,
        "height": 256,
        "bands": 3,
        "dtype": "uint8",
        "cogPath": "cogs/xiaoqiao.tif",
        "originalPath": "uploads/xiaoqiao.tif",
        "opacity": 0.9,
        "visible": True,
        "transferStatus": "cog-ready",
        "createdAt": "2026-07-07T00:00:00+00:00",
        "updatedAt": "2026-07-07T00:00:00+00:00",
    }


def test_tianditu_proxy_uses_browser_identity_for_browser_key(isolated_env, monkeypatch):
    app_module = reload_app_module()
    captured = {}

    class FakeResponse:
        status = 200
        headers = {"Content-Type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"png-tile"

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)

    content = app_module.fetch_tianditu_tile(
        "img_w",
        10,
        847,
        432,
        "browser-key",
        referer="http://127.0.0.1:8010/zhushan-bigdata.html",
    )

    assert content == b"png-tile"
    assert captured["request"].get_header("User-agent").startswith("Mozilla/5.0")
    assert captured["request"].get_header("Referer") == "http://127.0.0.1:8010/zhushan-bigdata.html"


def test_tianditu_server_key_request_omits_browser_referer(isolated_env, monkeypatch):
    app_module = reload_app_module()
    captured = {}

    app_module.TIANDITU_TK = "a" * 32

    def fake_fetch(layer, z, x, y, tk, referer=""):
        captured.update(
            {
                "layer": layer,
                "z": z,
                "x": x,
                "y": y,
                "tk": tk,
                "referer": referer,
            }
        )
        return b"png-tile"

    monkeypatch.setattr(app_module, "fetch_tianditu_tile", fake_fetch)

    client = TestClient(app_module.app)
    response = client.get(
        "/api/basemaps/tianditu/img_w/10/847/432.png",
        headers={"Referer": "http://127.0.0.1:8010/zhushan-bigdata.html"},
    )

    assert response.status_code == 200
    assert captured["tk"] == "a" * 32
    assert captured["referer"] == ""


def test_tianditu_upstream_request_does_not_fallback_to_referer_for_server_key(
    isolated_env,
    monkeypatch,
):
    app_module = reload_app_module()
    captured = {}

    class FakeResponse:
        status = 200
        headers = {"Content-Type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"png-tile"

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    app_module.TIANDITU_REFERER = "http://36.140.138.117"
    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)

    content = app_module.fetch_tianditu_tile(
        "img_w",
        10,
        847,
        432,
        "a" * 32,
    )

    assert content == b"png-tile"
    assert captured["request"].get_header("Referer") is None
    assert captured["request"].get_header("User-agent") == "SmartBambooTiandituProxy/1.0"


def test_public_scene_exposes_thumbnail_url(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-thumbnail-url"))
    client = TestClient(app_module.app)

    response = client.get(
        "/api/scenes/scene-thumbnail-url",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["thumbnailUrl"] == "/api/scenes/scene-thumbnail-url/thumbnail.png"
    assert "://" not in payload["thumbnailUrl"]


def test_public_scene_uses_same_origin_paths_for_3d_tiles(isolated_env):
    app_module = reload_app_module()
    scene = sample_scene("scene-3d-same-origin")
    scene.update(
        {
            "assetType": "oblique3d",
            "tilesetPath": "inbox/demo/tileset.json",
        }
    )
    app_module.save_scene(scene)
    client = TestClient(app_module.app, base_url="https://example.test:18081")

    response = client.get(
        "/api/scenes/scene-3d-same-origin",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tilesetUrl"] == (
        "/api/scenes/scene-3d-same-origin/point-cloud/tiles/tileset.json"
    )
    assert "://" not in payload["tilesetUrl"]


def test_public_scene_never_echoes_service_token_in_human_auth_mode(
    isolated_env, monkeypatch
):
    from starlette.requests import Request
    import server.modules.settings as settings

    app_module = reload_app_module()
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "1")
    settings.get_settings.cache_clear()
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/scenes/scene-human",
            "raw_path": b"/api/scenes/scene-human",
            "query_string": b"",
            "headers": [(b"authorization", b"Bearer exposed-token")],
            "server": ("example.test", 443),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
        }
    )
    try:
        payload = app_module.public_scene({"id": "scene-human"}, request)
    finally:
        settings.get_settings.cache_clear()

    assert "exposed-token" not in str(payload)
    assert "?token=" not in payload["tileUrl"]


def test_task_public_never_echoes_service_token_in_human_auth_mode(
    isolated_env, monkeypatch
):
    from starlette.requests import Request
    import server.modules.settings as settings

    app_module = reload_app_module()
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "1")
    settings.get_settings.cache_clear()
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/tasks/task-human",
            "raw_path": b"/api/tasks/task-human",
            "query_string": b"",
            "headers": [(b"authorization", b"Bearer exposed-task-token")],
            "server": ("example.test", 443),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
        }
    )
    try:
        payload = app_module.task_public(
            {
                "id": "task-human",
                "sceneId": "scene-human",
                "status": "failed",
            },
            request,
        )
    finally:
        settings.get_settings.cache_clear()

    assert "exposed-task-token" not in str(payload)
    assert "?token=" not in payload["sceneUrl"]
    assert "?token=" not in payload["retryUrl"]


def test_task_public_preserves_token_query_in_service_token_mode(
    isolated_env, monkeypatch
):
    from starlette.requests import Request
    import server.modules.settings as settings

    app_module = reload_app_module()
    monkeypatch.setenv("REMOTE_SENSING_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SMART_BAMBOO_HUMAN_AUTH_ENABLED", "0")
    settings.get_settings.cache_clear()
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/tasks/task-service",
            "raw_path": b"/api/tasks/task-service",
            "query_string": b"",
            "headers": [(b"authorization", b"Bearer service-task-token")],
            "server": ("example.test", 443),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
        }
    )
    try:
        payload = app_module.task_public(
            {
                "id": "task-service",
                "sceneId": "scene-service",
                "status": "failed",
            },
            request,
        )
    finally:
        settings.get_settings.cache_clear()

    assert payload["sceneUrl"].endswith("?token=service-task-token")
    assert payload["retryUrl"].endswith("?token=service-task-token")


def test_scene_thumbnail_renders_and_uses_file_cache(isolated_env, monkeypatch):
    app_module = reload_app_module()
    cog_path = app_module.COG_DIR / "thumbnail-source.tif"
    cog_path.parent.mkdir(parents=True, exist_ok=True)
    cog_path.write_bytes(b"fake-cog")
    app_module.save_scene(
        sample_scene("scene-thumbnail-cache")
        | {"cogPath": "cogs/thumbnail-source.tif"}
    )
    calls = []

    class FakeImage:
        def render(self, img_format="PNG"):
            assert img_format == "PNG"
            return b"\x89PNG\r\nthumbnail"

    class FakeReader:
        def __init__(self, path):
            calls.append(("open", path))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def preview(self, max_size):
            calls.append(("preview", max_size))
            return FakeImage()

    monkeypatch.setattr(app_module, "require_rio_tiler", lambda: FakeReader)
    client = TestClient(app_module.app)
    headers = {"X-RS-Roles": "imagery.scenes.view"}

    first = client.get(
        "/api/scenes/scene-thumbnail-cache/thumbnail.png?maxSize=320",
        headers=headers,
    )
    second = client.get(
        "/api/scenes/scene-thumbnail-cache/thumbnail.png?maxSize=320",
        headers=headers,
    )

    assert first.status_code == 200
    assert first.content.startswith(b"\x89PNG")
    assert first.headers["X-Thumbnail-Cache"] == "MISS"
    assert second.headers["X-Thumbnail-Cache"] == "HIT"
    assert calls == [("open", str(cog_path)), ("preview", 320)]


def test_scene_thumbnail_respects_scene_visibility(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(
        sample_scene("scene-thumbnail-private")
        | {"allowedRoles": ["imagery.private.view"]}
    )
    client = TestClient(app_module.app)

    response = client.get(
        "/api/scenes/scene-thumbnail-private/thumbnail.png",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )

    assert response.status_code == 403


def test_dashboard_satellite_track_summary_is_available_without_imagery_admin_permission(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-dashboard-001"))
    app_module.save_tasks([sample_task("task-dashboard-001")])
    client = TestClient(app_module.app)

    privileged_tasks = client.get("/api/tasks?limit=8", headers={"X-RS-Roles": "business.farmers.view"})
    dashboard = client.get("/api/dashboard/satellite-track", headers={"X-RS-Roles": "business.farmers.view"})

    assert privileged_tasks.status_code == 403
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["title"]
    assert body["columns"] == ["任务编号", "任务状态", "影像场景", "更新时间"]
    assert body["rows"][0][0] == "task-dashboard-001"
    assert body["rows"][0][2] == "scene-pg-001"
    assert ["图传任务", "1 条"] in body["metrics"]
    assert ["影像目录", "1 景"] in body["metrics"]
    assert {"label": "影像后台", "href": "admin-imagery.html"} in body["adminLinks"]


def test_dashboard_workflow_status_is_public_without_opening_admin_endpoints(isolated_env):
    app_module = reload_app_module()
    client = TestClient(app_module.app)
    headers = {"X-RS-Roles": "business.farmers.view"}

    import_admin = client.get("/api/imports/forest-blocks/workflow-summary", headers=headers)
    imagery_admin = client.get("/api/scenes/workflow-summary", headers=headers)
    dashboard = client.get("/api/dashboard/workflow-status", headers=headers)

    assert import_admin.status_code == 403
    assert imagery_admin.status_code == 403
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert set(body) >= {"imports", "imagery", "deliveries", "layers", "generatedAt"}
    assert set(body["deliveries"]) >= {"items", "total", "limit", "offset"}
    for item in body["deliveries"]["items"]:
        assert set(item) <= {
            "batchId",
            "packageStatus",
            "deliveryStatus",
            "acceptanceStatus",
            "adminHref",
        }


def test_role_data_scopes_limit_imagery_scene_visibility_by_project_and_area(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-scope-visible") | {"projectId": "zhushan-core", "areaCode": "350703"})
    app_module.save_scene(sample_scene("scene-scope-hidden-project") | {"projectId": "zhushan-other", "areaCode": "350703"})
    app_module.save_scene(sample_scene("scene-scope-hidden-area") | {"projectId": "zhushan-core", "areaCode": "350784"})
    client = TestClient(app_module.app)

    created_role = client.post(
        "/api/admin/roles",
        json={
            "roleCode": "imagery_scope_viewer",
            "name": "Imagery scope viewer",
            "status": "active",
            "permissions": ["imagery.scenes.view"],
            "menuModules": ["imagery"],
            "dataScopes": {"projects": ["zhushan-core"], "areas": ["350703"]},
        },
        headers={"X-RS-Roles": "admin"},
    )
    visible = client.get("/api/scenes", headers={"X-RS-Roles": "imagery_scope_viewer"})

    assert created_role.status_code == 200
    assert visible.status_code == 200
    assert visible.json()["total"] == 1
    assert visible.json()["scenes"][0]["id"] == "scene-scope-visible"


class FakeExecutor:
    def __init__(self):
        self.calls: list[tuple[object, tuple[object, ...]]] = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))
        return None


def enable_postgis_tasks(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "CATALOG_BACKEND", "postgis")
    monkeypatch.setattr(app_module, "DATABASE_URL", "postgresql://remote-sensing")


def test_postgis_tasks_use_database_for_upsert_and_api_listing(isolated_env, monkeypatch):
    app_module = reload_app_module()
    enable_postgis_tasks(app_module, monkeypatch)
    task = sample_task()

    schema_cursor = FakeCursor()
    upsert_cursor = FakeCursor()
    schema_for_list_cursor = FakeCursor()
    list_cursor = FakeCursor(fetchall_result=[(json.dumps(task, ensure_ascii=False),)])
    connect_calls: list[str] = []
    install_fake_psycopg(
        monkeypatch,
        [schema_cursor, upsert_cursor, schema_for_list_cursor, list_cursor],
        connect_calls,
    )

    app_module.upsert_task(task)
    response = TestClient(app_module.app).get("/api/tasks", headers={"X-RS-Roles": "admin"})

    assert response.status_code == 200
    assert response.json()["tasks"][0]["id"] == "task-pg-001"
    assert any("CREATE TABLE IF NOT EXISTS remote_sensing_tasks" in sql for sql, _ in schema_cursor.executed)
    assert any("INSERT INTO remote_sensing_tasks" in sql for sql, _ in upsert_cursor.executed)
    assert any("FROM remote_sensing_tasks" in sql for sql, _ in list_cursor.executed)
    assert connect_calls == ["postgresql://remote-sensing"] * 4


def test_postgis_update_task_writes_status_change_to_database(isolated_env, monkeypatch):
    app_module = reload_app_module()
    enable_postgis_tasks(app_module, monkeypatch)
    queued = sample_task("task-pg-update")

    schema_for_load_cursor = FakeCursor()
    load_cursor = FakeCursor(fetchall_result=[(queued,)])
    schema_for_update_cursor = FakeCursor()
    upsert_cursor = FakeCursor()
    connect_calls: list[str] = []
    install_fake_psycopg(
        monkeypatch,
        [schema_for_load_cursor, load_cursor, schema_for_update_cursor, upsert_cursor],
        connect_calls,
    )

    updated = app_module.update_task("task-pg-update", status="running", progress=42)

    assert updated["status"] == "running"
    assert updated["progress"] == 42
    assert any("SELECT task FROM remote_sensing_tasks" in sql for sql, _ in load_cursor.executed)
    assert any("INSERT INTO remote_sensing_tasks" in sql for sql, _ in upsert_cursor.executed)
    upsert_params = next(params for sql, params in upsert_cursor.executed if "INSERT INTO remote_sensing_tasks" in sql)
    assert '"status": "running"' in str(upsert_params[-1])
    assert '"progress": 42' in str(upsert_params[-1])
    assert connect_calls == ["postgresql://remote-sensing"] * 4


def test_task_updates_append_operation_events(isolated_env):
    app_module = reload_app_module()
    queued = sample_task("task-events-001")
    app_module.save_tasks([queued])

    running = app_module.update_task("task-events-001", status="running", progress=12, message="Started")
    failed = app_module.update_task("task-events-001", status="failed", progress=100, message="Failed")

    assert [event["status"] for event in running["events"]] == ["running"]
    assert [event["status"] for event in failed["events"]] == ["running", "failed"]
    assert failed["events"][-1]["message"] == "Failed"
    assert failed["events"][-1]["progress"] == 100
    assert failed["events"][-1]["at"]


def test_imagery_task_ledger_requires_view_permission(isolated_env):
    app_module = reload_app_module()
    app_module.save_tasks([sample_task("task-view-permission")])
    client = TestClient(app_module.app)

    denied_list = client.get(
        "/api/tasks",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    denied_detail = client.get(
        "/api/tasks/task-view-permission",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    allowed_list = client.get(
        "/api/tasks",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    allowed_detail = client.get(
        "/api/tasks/task-view-permission",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )

    assert denied_list.status_code == 403
    assert "imagery.scenes.view" in denied_list.json()["detail"]
    assert denied_detail.status_code == 403
    assert "imagery.scenes.view" in denied_detail.json()["detail"]
    assert allowed_list.status_code == 200
    assert allowed_list.json()["tasks"][0]["id"] == "task-view-permission"
    assert allowed_detail.status_code == 200
    assert allowed_detail.json()["id"] == "task-view-permission"


def test_imagery_scene_ledger_requires_view_permission(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-view-permission"))
    client = TestClient(app_module.app)

    denied = client.get(
        "/api/scenes",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    allowed = client.get(
        "/api/scenes",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )

    assert denied.status_code == 403
    assert "imagery.scenes.view" in denied.json()["detail"]
    assert allowed.status_code == 200
    assert allowed.json()["scenes"][0]["id"] == "scene-view-permission"


def test_imagery_task_events_can_be_listed_across_tasks(isolated_env):
    app_module = reload_app_module()
    task_one = sample_task("task-events-ledger-001") | {
        "type": "upload",
        "status": "failed",
        "progress": 100,
        "message": "Conversion failed",
        "events": [
            {
                "at": "2026-07-07T00:00:00+00:00",
                "status": "queued",
                "progress": 0,
                "message": "Queued",
            },
            {
                "at": "2026-07-07T00:03:00+00:00",
                "status": "failed",
                "progress": 100,
                "message": "Conversion failed",
                "action": "update",
                "actor": "worker",
            },
        ],
    }
    task_two = sample_task("task-events-ledger-002") | {
        "type": "register",
        "status": "canceled",
        "progress": 100,
        "message": "Canceled",
        "events": [
            {
                "at": "2026-07-07T00:05:00+00:00",
                "status": "canceled",
                "progress": 100,
                "message": "Canceled",
                "action": "cancel",
                "actor": "operator-a",
            }
        ],
    }
    app_module.save_tasks([task_one, task_two])
    client = TestClient(app_module.app)

    denied = client.get(
        "/api/tasks/events",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    listed = client.get("/api/tasks/events?limit=20", headers={"X-RS-Roles": "admin"})
    failed_only = client.get(
        "/api/tasks/events?status=failed&q=Conversion",
        headers={"X-RS-Roles": "admin"},
    )
    canceled_only = client.get(
        "/api/tasks/events?taskId=task-events-ledger-002&action=cancel",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "imagery.scenes.view" in denied.json()["detail"]
    assert listed.status_code == 200
    body = listed.json()
    assert body["limit"] == 20
    assert body["total"] == 3
    failed_event = next(item for item in body["items"] if item["status"] == "failed")
    assert failed_event["eventId"]
    assert failed_event["taskId"] == "task-events-ledger-001"
    assert failed_event["taskType"] == "upload"
    assert failed_event["progress"] == 100
    assert failed_event["message"] == "Conversion failed"
    assert failed_event["action"] == "update"
    assert failed_event["actor"] == "worker"
    assert failed_event["summary"] == "failed: Conversion failed"
    assert failed_only.status_code == 200
    assert failed_only.json()["total"] == 1
    assert canceled_only.status_code == 200
    assert canceled_only.json()["total"] == 1
    assert canceled_only.json()["items"][0]["actor"] == "operator-a"


def test_imagery_event_ledgers_can_be_exported_as_csv(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-events-export") | {"name": "Exportable scene"})
    app_module.save_tasks(
        [
            sample_task("task-events-export")
            | {
                "type": "upload",
                "status": "failed",
                "progress": 100,
                "message": "Conversion failed",
                "sceneId": "scene-events-export",
                "events": [
                    {
                        "at": "2026-07-07T00:10:00+00:00",
                        "status": "failed",
                        "progress": 100,
                        "message": "Conversion failed",
                        "action": "status",
                        "actor": "task-exporter",
                    }
                ],
            }
        ]
    )
    client = TestClient(app_module.app)

    published = client.post(
        "/api/scenes/scene-events-export/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-EXPORT"], "zIndex": 41},
        headers={"X-RS-Roles": "admin", "X-RS-User": "scene-exporter"},
    )
    denied_scene_export = client.get(
        "/api/scenes/events.csv?sceneId=scene-events-export",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    scene_export = client.get(
        "/api/scenes/events.csv?sceneId=scene-events-export",
        headers={"X-RS-Roles": "imagery.scenes.export"},
    )
    denied_task_export = client.get(
        "/api/tasks/events.csv?taskId=task-events-export",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    task_export = client.get(
        "/api/tasks/events.csv?taskId=task-events-export",
        headers={"X-RS-Roles": "imagery.scenes.export"},
    )

    assert published.status_code == 200
    assert denied_scene_export.status_code == 403
    assert "imagery.scenes.export" in denied_scene_export.json()["detail"]
    assert scene_export.status_code == 200
    assert scene_export.headers["content-type"].startswith("text/csv")
    assert "scene-events.csv" in scene_export.headers["content-disposition"]
    scene_csv = scene_export.content.decode("utf-8-sig")
    assert "eventId,sceneId,eventType,action,status,actor,at,layerRecordCode,comment,summary" in scene_csv.splitlines()[0]
    assert "scene-events-export" in scene_csv
    assert "scene-exporter" in scene_csv

    assert denied_task_export.status_code == 403
    assert "imagery.scenes.export" in denied_task_export.json()["detail"]
    assert task_export.status_code == 200
    assert task_export.headers["content-type"].startswith("text/csv")
    assert "task-events.csv" in task_export.headers["content-disposition"]
    task_csv = task_export.content.decode("utf-8-sig")
    assert "eventId,taskId,taskType,sceneId,status,action,actor,at,progress,message" in task_csv.splitlines()[0]
    assert "task-events-export" in task_csv
    assert "task-exporter" in task_csv


def test_scenes_can_filter_by_delivery_status_and_export_delivery_events(isolated_env):
    app_module = reload_app_module()
    delivered_scene = sample_scene("scene-delivery-filter-delivered") | {
        "deliveryStatus": "delivered",
        "deliveryComment": "delivery accepted",
        "deliveredAt": "2026-07-09T08:00:00+00:00",
        "deliveredBy": "delivery-user",
        "deliveryEvents": [
            {
                "at": "2026-07-09T08:00:00+00:00",
                "action": "delivery",
                "status": "delivered",
                "actor": "delivery-user",
                "comment": "delivery accepted",
            }
        ],
    }
    pending_scene = sample_scene("scene-delivery-filter-pending") | {"deliveryStatus": "pending"}
    app_module.save_scene(delivered_scene)
    app_module.save_scene(pending_scene)
    client = TestClient(app_module.app)

    filtered = client.get(
        "/api/scenes?deliveryStatus=delivered",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    exported = client.get(
        "/api/scenes/events.csv?eventType=delivery&sceneId=scene-delivery-filter-delivered",
        headers={"X-RS-Roles": "imagery.scenes.export"},
    )

    assert filtered.status_code == 200
    assert [scene["id"] for scene in filtered.json()["scenes"]] == ["scene-delivery-filter-delivered"]
    assert filtered.json()["scenes"][0]["deliveryStatus"] == "delivered"
    assert exported.status_code == 200
    csv_text = exported.content.decode("utf-8-sig")
    assert "status" in csv_text.splitlines()[0]
    assert "comment" in csv_text.splitlines()[0]
    assert "delivered" in csv_text
    assert "delivery accepted" in csv_text


def test_imagery_quality_issues_can_be_listed_and_filtered(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(
        sample_scene("scene-quality-missing-bounds")
        | {
            "name": "Missing bounds orthophoto",
            "bounds": [],
        }
    )
    app_module.save_scene(
        sample_scene("scene-quality-missing-cog")
        | {
            "name": "Missing COG orthophoto",
            "cogPath": "",
        }
    )
    failed_task = sample_task("task-quality-failed") | {
        "status": "failed",
        "progress": 100,
        "message": "COG conversion failed",
        "sceneId": "scene-quality-task",
        "events": [
            {
                "at": "2026-07-07T00:03:00+00:00",
                "status": "failed",
                "progress": 100,
                "message": "COG conversion failed",
                "action": "update",
                "actor": "worker",
            }
        ],
    }
    app_module.save_tasks([failed_task])
    client = TestClient(app_module.app)

    denied = client.get(
        "/api/scenes/quality-issues",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    listed = client.get("/api/scenes/quality-issues?limit=20", headers={"X-RS-Roles": "admin"})
    failed_only = client.get(
        "/api/scenes/quality-issues?issueType=task_failure&q=COG",
        headers={"X-RS-Roles": "admin"},
    )
    scene_only = client.get(
        "/api/scenes/quality-issues?sceneId=scene-quality-missing-bounds&severity=blocked",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "imagery.scenes.view" in denied.json()["detail"]
    assert listed.status_code == 200
    body = listed.json()
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["total"] == 3
    issue_types = {item["issueType"] for item in body["items"]}
    assert issue_types == {"task_failure", "missing_bounds", "missing_cog_path"}
    failed_issue = next(item for item in body["items"] if item["issueType"] == "task_failure")
    assert failed_issue["taskId"] == "task-quality-failed"
    assert failed_issue["sceneId"] == "scene-quality-task"
    assert failed_issue["severity"] == "blocked"
    assert failed_issue["message"] == "COG conversion failed"
    assert "重试" in failed_issue["actionRequired"]
    assert failed_only.status_code == 200
    assert failed_only.json()["total"] == 1
    assert failed_only.json()["items"][0]["issueKey"] == "task-quality-failed"
    assert scene_only.status_code == 200
    assert scene_only.json()["total"] == 1
    assert scene_only.json()["items"][0]["sceneId"] == "scene-quality-missing-bounds"


def test_imagery_quality_issues_can_be_exported_as_csv(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(
        sample_scene("scene-quality-export")
        | {
            "name": "Export quality scene",
            "bounds": [],
        }
    )
    archived_task = sample_task("task-quality-export-archived") | {
        "status": "failed",
        "progress": 100,
        "message": "Archived export conversion failed",
        "sceneId": "scene-quality-export",
        "archivedAt": "2026-07-07T01:00:00+00:00",
    }
    app_module.save_tasks([archived_task])
    client = TestClient(app_module.app)

    denied = client.get(
        "/api/scenes/quality-issues.csv?sceneId=scene-quality-export",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    exported = client.get(
        "/api/scenes/quality-issues.csv?sceneId=scene-quality-export",
        headers={"X-RS-Roles": "imagery.scenes.export"},
    )
    archived_denied = client.get(
        "/api/scenes/quality-issues.csv?includeArchived=true",
        headers={"X-RS-Roles": "imagery.scenes.export"},
    )
    archived_exported = client.get(
        "/api/scenes/quality-issues.csv?includeArchived=true&taskId=task-quality-export-archived",
        headers={"X-RS-Roles": "imagery.scenes.export,imagery.tasks.archive"},
    )

    assert denied.status_code == 403
    assert "imagery.scenes.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "imagery-quality-issues.csv" in exported.headers["content-disposition"]
    text = exported.content.decode("utf-8-sig")
    assert "issueId,issueType,issueKey,severity,status,sceneId,sceneName,taskId" in text.splitlines()[0]
    assert "scene-quality-export" in text
    assert "missing_bounds" in text

    assert archived_denied.status_code == 403
    assert "imagery.tasks.archive" in archived_denied.json()["detail"]
    assert archived_exported.status_code == 200
    archived_text = archived_exported.content.decode("utf-8-sig")
    assert "task-quality-export-archived" in archived_text
    assert "Archived export conversion failed" in archived_text


def test_archived_imagery_quality_issues_require_archive_permission(isolated_env):
    app_module = reload_app_module()
    archived_task = sample_task("task-quality-archived") | {
        "status": "failed",
        "progress": 100,
        "message": "Archived conversion failed",
        "sceneId": "scene-quality-archived",
        "archivedAt": "2026-07-09T00:00:00+08:00",
        "archivedBy": "operator-b",
    }
    app_module.save_tasks([archived_task])
    client = TestClient(app_module.app)

    default_list = client.get(
        "/api/scenes/quality-issues?issueType=task_failure",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    denied = client.get(
        "/api/scenes/quality-issues?issueType=task_failure&includeArchived=true",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    allowed = client.get(
        "/api/scenes/quality-issues?issueType=task_failure&includeArchived=true",
        headers={"X-RS-Roles": "imagery.scenes.view,imagery.tasks.archive"},
    )

    assert default_list.status_code == 200
    assert default_list.json()["items"] == []
    assert denied.status_code == 403
    assert "imagery.tasks.archive" in denied.json()["detail"]
    assert allowed.status_code == 200
    assert allowed.json()["items"][0]["taskId"] == "task-quality-archived"


def test_imagery_quality_issue_can_be_updated_and_filtered(isolated_env):
    app_module = reload_app_module()
    failed_task = sample_task("task-quality-close") | {
        "status": "failed",
        "progress": 100,
        "message": "Tile conversion failed",
        "sceneId": "scene-quality-close",
    }
    app_module.save_tasks([failed_task])
    client = TestClient(app_module.app)
    issue = client.get(
        "/api/scenes/quality-issues?issueType=task_failure",
        headers={"X-RS-Roles": "admin"},
    ).json()["items"][0]

    denied = client.patch(
        f"/api/scenes/quality-issues/{issue['issueId']}",
        json={"status": "ignored", "comment": "Superseded by a new upload"},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    updated = client.patch(
        f"/api/scenes/quality-issues/{issue['issueId']}",
        json={"status": "ignored", "comment": "Superseded by a new upload"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "imagery-reviewer"},
    )
    ignored_only = client.get(
        "/api/scenes/quality-issues?status=ignored",
        headers={"X-RS-Roles": "admin"},
    )
    task_events = client.get(
        "/api/tasks/events?action=quality-issue-update&taskId=task-quality-close&q=Superseded",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "imagery.scenes.quality" in denied.json()["detail"]
    assert updated.status_code == 200
    body = updated.json()
    assert body["issue"]["issueId"] == issue["issueId"]
    assert body["issue"]["status"] == "ignored"
    assert body["issue"]["handledBy"] == "imagery-reviewer"
    assert body["issue"]["handlingComment"] == "Superseded by a new upload"
    assert body["event"]["status"] == "ignored"
    assert body["task"]["qualityIssueEvents"][-1]["issueId"] == issue["issueId"]
    assert ignored_only.status_code == 200
    assert ignored_only.json()["total"] == 1
    assert ignored_only.json()["items"][0]["status"] == "ignored"
    assert task_events.status_code == 200
    assert task_events.json()["total"] == 1
    assert task_events.json()["items"][0]["actor"] == "imagery-reviewer"
    assert task_events.json()["items"][0]["action"] == "quality-issue-update"
    assert task_events.json()["items"][0]["status"] == "ignored"


def test_imagery_workflow_summary_counts_publication_tasks_and_quality(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-workflow-unpublished"))
    app_module.save_scene(
        sample_scene("scene-workflow-published")
        | {
            "status": "published",
            "publishedLayerRecordCode": "SCENE-LAYER-scene-workflow-published",
        }
    )
    app_module.save_scene(sample_scene("scene-workflow-missing-bounds") | {"bounds": []})
    app_module.save_scene(sample_scene("scene-workflow-archived") | {"status": "archived", "visible": False})
    app_module.save_tasks(
        [
            sample_task("task-workflow-queued") | {"status": "queued", "sceneId": "scene-workflow-unpublished"},
            sample_task("task-workflow-running") | {"status": "running", "sceneId": "scene-workflow-unpublished"},
            sample_task("task-workflow-failed")
            | {
                "status": "failed",
                "progress": 100,
                "message": "COG conversion failed",
                "sceneId": "scene-workflow-unpublished",
            },
            sample_task("task-workflow-archived")
            | {
                "status": "failed",
                "archivedAt": "2026-07-09T00:00:00+08:00",
                "sceneId": "scene-workflow-archived",
            },
        ]
    )
    client = TestClient(app_module.app)

    denied = client.get(
        "/api/scenes/workflow-summary",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    summary = client.get("/api/scenes/workflow-summary", headers={"X-RS-Roles": "admin"})
    denied_export = client.get(
        "/api/scenes/workflow-summary.json",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    exported = client.get(
        "/api/scenes/workflow-summary.json",
        headers={"X-RS-Roles": "imagery.scenes.export"},
    )

    assert denied.status_code == 403
    assert "imagery.scenes.view" in denied.json()["detail"]
    assert summary.status_code == 200
    body = summary.json()
    assert body["activeSceneTotal"] == 3
    assert body["publishedScenes"] == 1
    assert body["unpublishedScenes"] == 2
    assert body["queuedTasks"] == 1
    assert body["runningTasks"] == 1
    assert body["failedTasks"] == 1
    assert body["openImageryIssues"] == 2
    assert body["blockedImageryIssues"] == 2
    assert body["needsAttentionTotal"] == 4
    assert body["cards"][0]["key"] == "unpublishedScenes"
    assert body["cards"][1]["key"] == "failedTasks"
    card_hrefs = {card["key"]: card["href"] for card in body["cards"]}
    assert card_hrefs["unpublishedScenes"] == "admin-imagery.html?published=false"
    assert card_hrefs["failedTasks"] == "admin-imagery.html?taskStatus=failed"
    assert card_hrefs["runningTasks"] == "admin-imagery.html?taskStatus=running"
    assert card_hrefs["blockedImageryIssues"] == "admin-imagery.html?imageryIssueStatus=open"
    assert denied_export.status_code == 403
    assert "imagery.scenes.export" in denied_export.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "imagery-workflow-summary.json" in exported.headers["content-disposition"]
    exported_body = exported.json()
    assert exported_body["unpublishedScenes"] == 2
    assert exported_body["failedTasks"] == 1
    assert exported_body["exportedAt"]

    unpublished = client.get("/api/scenes?published=false", headers={"X-RS-Roles": "admin"})
    published = client.get("/api/scenes?published=true", headers={"X-RS-Roles": "admin"})
    failed_tasks = client.get("/api/tasks?status=failed", headers={"X-RS-Roles": "admin"})
    assert unpublished.status_code == 200
    assert {scene["id"] for scene in unpublished.json()["scenes"]} == {
        "scene-workflow-unpublished",
        "scene-workflow-missing-bounds",
    }
    assert published.status_code == 200
    assert [scene["id"] for scene in published.json()["scenes"]] == ["scene-workflow-published"]
    assert failed_tasks.status_code == 200
    assert [task["id"] for task in failed_tasks.json()["tasks"]] == ["task-workflow-failed"]


def test_imagery_operation_queue_groups_scene_task_and_delivery_work(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-queue-unpublished") | {"name": "Needs publication"})
    app_module.save_scene(sample_scene("scene-queue-missing-bounds") | {"name": "Needs bounds", "bounds": []})
    app_module.save_scene(
        sample_scene("scene-queue-awaiting-delivery")
        | {
            "name": "Awaiting delivery",
            "status": "published",
            "publishedLayerRecordCode": "SCENE-LAYER-scene-queue-awaiting-delivery",
            "deliveryStatus": "needs_correction",
        }
    )
    app_module.save_scene(
        sample_scene("scene-queue-ready")
        | {
            "name": "Delivered scene",
            "status": "published",
            "publishedLayerRecordCode": "SCENE-LAYER-scene-queue-ready",
            "deliveryStatus": "delivered",
        }
    )
    app_module.save_scene(sample_scene("scene-queue-archived") | {"status": "archived"})
    app_module.save_tasks(
        [
            sample_task("task-queue-failed")
            | {
                "status": "failed",
                "progress": 100,
                "message": "COG conversion failed",
                "sceneId": "scene-queue-unpublished",
            },
            sample_task("task-queue-running") | {"status": "running", "sceneId": "scene-queue-unpublished"},
            sample_task("task-queue-archived")
            | {
                "status": "failed",
                "archivedAt": "2026-07-09T00:00:00+08:00",
                "sceneId": "scene-queue-archived",
            },
        ]
    )
    client = TestClient(app_module.app)

    denied = client.get(
        "/api/scenes/operation-queue",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    response = client.get("/api/scenes/operation-queue?limit=1", headers={"X-RS-Roles": "admin"})

    assert denied.status_code == 403
    assert "imagery.scenes.view" in denied.json()["detail"]
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["operationQueueTotal"] == 6
    assert body["summary"]["actionableQueueTotal"] == 5
    lanes = {lane["key"]: lane for lane in body["items"]}
    assert list(lanes) == [
        "failed_tasks",
        "quality_issues",
        "awaiting_publish",
        "awaiting_delivery",
        "ready",
    ]
    assert lanes["failed_tasks"]["count"] == 1
    assert lanes["failed_tasks"]["items"][0]["taskId"] == "task-queue-failed"
    assert lanes["failed_tasks"]["items"][0]["sceneId"] == "scene-queue-unpublished"
    assert lanes["failed_tasks"]["items"][0]["requiredPermission"] == "imagery.tasks.retry"
    assert "taskId=task-queue-failed" in lanes["failed_tasks"]["items"][0]["adminHref"]
    assert lanes["quality_issues"]["count"] == 2
    assert lanes["quality_issues"]["items"][0]["issueId"]
    assert lanes["quality_issues"]["items"][0]["requiredPermission"] == "imagery.scenes.quality"
    assert lanes["awaiting_publish"]["count"] == 2
    assert lanes["awaiting_publish"]["items"][0]["requiredPermission"] == "imagery.layers.publish"
    assert lanes["awaiting_publish"]["items"][0]["allPermissions"] == "map.layers.publish"
    assert "admin-imagery.html?published=false" in lanes["awaiting_publish"]["href"]
    assert lanes["awaiting_delivery"]["count"] == 1
    assert lanes["awaiting_delivery"]["items"][0]["sceneId"] == "scene-queue-awaiting-delivery"
    assert lanes["ready"]["count"] == 1
    assert lanes["ready"]["items"][0]["sceneId"] == "scene-queue-ready"
    assert lanes["ready"]["items"][0]["requiredPermission"] == "imagery.scenes.export"


def test_imagery_scene_delivery_receipt_can_be_exported(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-delivery-receipt") | {"name": "Receipt orthophoto"})
    client = TestClient(app_module.app)
    published = client.post(
        "/api/scenes/scene-delivery-receipt/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-RECEIPT"], "zIndex": 42},
        headers={"X-RS-Roles": "admin", "X-RS-User": "publisher"},
    )

    denied = client.get(
        "/api/scenes/scene-delivery-receipt/delivery-receipt.json",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    exported = client.get(
        "/api/scenes/scene-delivery-receipt/delivery-receipt.json",
        headers={"X-RS-Roles": "imagery.scenes.export", "X-RS-User": "scene-receipt-exporter"},
    )

    assert published.status_code == 200
    assert denied.status_code == 403
    assert "imagery.scenes.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "scene-delivery-receipt-scene-delivery-receipt.json" in exported.headers["content-disposition"]
    body = exported.json()
    assert body["receiptType"] == "imagery-scene-delivery"
    assert body["exportedBy"] == "scene-receipt-exporter"
    assert body["exportPermission"] == "imagery.scenes.export"
    assert body["exportRoles"] == ["imagery.scenes.export"]
    assert body["exportDataScopes"] == {}
    assert body["scene"]["id"] == "scene-delivery-receipt"
    assert body["summary"]["published"] is True
    assert body["summary"]["qualityIssueCount"] == 0
    assert body["publishedLayer"]["recordCode"] == "SCENE-LAYER-scene-delivery-receipt"
    assert body["publishedLayer"]["linkedBlockCodes"] == ["BLOCK-RECEIPT"]
    assert [event["action"] for event in body["sceneEvents"]] == ["export-delivery-receipt", "publish-layer"]
    assert body["sceneEvents"][0]["eventType"] == "lifecycle"
    assert body["sceneEvents"][0]["actor"] == "scene-receipt-exporter"
    assert body["qualityIssues"] == []
    assert body["exportedAt"]
    events = client.get(
        "/api/scenes/events?sceneId=scene-delivery-receipt&action=export-delivery-receipt",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    assert events.status_code == 200
    assert events.json()["total"] == 1
    assert events.json()["items"][0]["actor"] == "scene-receipt-exporter"


def test_imagery_scene_publication_receipt_can_be_exported(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-publication-receipt") | {"name": "Publication orthophoto"})
    client = TestClient(app_module.app)
    published = client.post(
        "/api/scenes/scene-publication-receipt/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-PUBLICATION"], "zIndex": 44},
        headers={"X-RS-Roles": "admin", "X-RS-User": "publisher"},
    )

    denied = client.get(
        "/api/scenes/scene-publication-receipt/publication-receipt.json",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    exported = client.get(
        "/api/scenes/scene-publication-receipt/publication-receipt.json",
        headers={"X-RS-Roles": "imagery.scenes.export", "X-RS-User": "scene-publication-exporter"},
    )

    assert published.status_code == 200
    assert denied.status_code == 403
    assert "imagery.scenes.export" in denied.json()["detail"]
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "scene-publication-receipt-scene-publication-receipt.json" in exported.headers["content-disposition"]
    body = exported.json()
    assert body["receiptType"] == "imagery-scene-publication"
    assert body["exportedBy"] == "scene-publication-exporter"
    assert body["exportPermission"] == "imagery.scenes.export"
    assert body["scene"]["id"] == "scene-publication-receipt"
    assert body["summary"]["published"] is True
    assert body["summary"]["publishedLayerCount"] == 1
    assert body["summary"]["linkedBlockCount"] == 1
    assert body["summary"]["dashboardHref"] == "zhushan-bigdata.html#mapLayers"
    assert body["mapLayers"][0]["recordCode"] == "SCENE-LAYER-scene-publication-receipt"
    assert body["mapLayers"][0]["linkedBlockCodes"] == ["BLOCK-PUBLICATION"]
    assert [event["action"] for event in body["sceneEvents"]] == ["export-publication-receipt", "publish-layer"]
    assert body["sceneEvents"][0]["actor"] == "scene-publication-exporter"
    assert body["exportedAt"]
    events = client.get(
        "/api/scenes/events?sceneId=scene-publication-receipt&action=export-publication-receipt",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    assert events.status_code == 200
    assert events.json()["total"] == 1
    assert events.json()["items"][0]["actor"] == "scene-publication-exporter"


def test_imagery_scene_delivery_status_can_be_updated_and_receipted(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-delivery-status") | {"name": "Delivery status orthophoto"})
    client = TestClient(app_module.app)
    published = client.post(
        "/api/scenes/scene-delivery-status/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-DELIVERY"], "zIndex": 43},
        headers={"X-RS-Roles": "admin", "X-RS-User": "publisher"},
    )

    denied = client.post(
        "/api/scenes/scene-delivery-status/delivery",
        json={"status": "delivered", "comment": "ok"},
        headers={"X-RS-Roles": "imagery.scenes.export"},
    )
    delivered = client.post(
        "/api/scenes/scene-delivery-status/delivery",
        json={"status": "delivered", "comment": "影像、切片和图层发布均已交付"},
        headers={"X-RS-Roles": "imagery.scenes.delivery", "X-RS-User": "deliverer"},
    )
    scene = client.get("/api/scenes/scene-delivery-status", headers={"X-RS-Roles": "admin"})
    events = client.get(
        "/api/scenes/events?sceneId=scene-delivery-status&eventType=delivery",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    receipt = client.get(
        "/api/scenes/scene-delivery-status/delivery-receipt.json",
        headers={"X-RS-Roles": "imagery.scenes.export"},
    )

    assert published.status_code == 200
    assert denied.status_code == 403
    assert "imagery.scenes.delivery" in denied.json()["detail"]
    assert delivered.status_code == 200
    body = delivered.json()
    assert body["ok"] is True
    assert body["deliveryStatus"] == "delivered"
    assert body["deliveredBy"] == "deliverer"
    assert body["event"]["action"] == "delivery"
    assert body["event"]["status"] == "delivered"
    assert body["event"]["actor"] == "deliverer"
    assert body["scene"]["deliveryEvents"][-1] == body["event"]
    assert scene.status_code == 200
    assert scene.json()["deliveryStatus"] == "delivered"
    assert scene.json()["deliveryComment"] == "影像、切片和图层发布均已交付"
    assert events.status_code == 200
    assert events.json()["total"] == 1
    assert events.json()["items"][0]["eventType"] == "delivery"
    assert receipt.status_code == 200
    receipt_body = receipt.json()
    assert receipt_body["summary"]["deliveryStatus"] == "delivered"
    assert receipt_body["summary"]["deliveredBy"] == "deliverer"
    assert receipt_body["deliveryEvents"][-1]["comment"] == "影像、切片和图层发布均已交付"


def test_scene_quality_issue_update_is_listed_in_scene_events(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(
        sample_scene("scene-quality-event") | {
            "name": "Quality event scene",
            "cogPath": "",
        }
    )
    client = TestClient(app_module.app)
    issue = client.get(
        "/api/scenes/quality-issues?issueType=missing_cog_path&sceneId=scene-quality-event",
        headers={"X-RS-Roles": "admin"},
    ).json()["items"][0]

    updated = client.patch(
        f"/api/scenes/quality-issues/{issue['issueId']}",
        json={"status": "resolved", "comment": "COG generated"},
        headers={"X-RS-Roles": "admin", "X-RS-User": "scene-reviewer"},
    )
    scene_events = client.get(
        "/api/scenes/events?eventType=quality&action=quality-issue-update&sceneId=scene-quality-event&q=COG",
        headers={"X-RS-Roles": "admin"},
    )

    assert updated.status_code == 200
    assert updated.json()["scene"]["qualityIssueEvents"][-1]["issueId"] == issue["issueId"]
    assert scene_events.status_code == 200
    assert scene_events.json()["total"] == 1
    event = scene_events.json()["items"][0]
    assert event["actor"] == "scene-reviewer"
    assert event["status"] == "resolved"
    assert event["action"] == "quality-issue-update"
    assert event["eventType"] == "quality"


def test_failed_imagery_task_can_be_retried_with_permission(isolated_env, monkeypatch):
    app_module = reload_app_module()
    source_path = isolated_env / "failed-source.tif"
    source_path.write_bytes(b"not-a-real-tiff")
    failed_task = sample_task("task-retry-source") | {
        "status": "failed",
        "progress": 100,
        "message": "GDAL conversion failed",
        "sceneId": "scene-retry-001",
        "sourcePath": str(source_path),
        "cogPath": str(isolated_env / "old-output.tif"),
        "retryAttempt": 1,
    }
    executor = FakeExecutor()
    monkeypatch.setattr(app_module, "TASK_EXECUTOR", executor)
    app_module.save_tasks([failed_task])
    client = TestClient(app_module.app)

    denied = client.post(
        "/api/tasks/task-retry-source/retry",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    retried = client.post(
        "/api/tasks/task-retry-source/retry",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "imagery.tasks.retry" in denied.json()["detail"]
    assert retried.status_code == 200
    body = retried.json()
    assert body["accepted"] is True
    assert body["task"]["status"] == "queued"
    assert body["task"]["retryOf"] == "task-retry-source"
    assert body["task"]["retryAttempt"] == 2
    assert body["task"]["sourcePath"] == str(source_path.resolve())
    assert body["task"]["sceneId"] == "scene-retry-001"
    assert executor.calls == [(app_module.run_conversion_task, (body["task"]["id"],))]

    detail = client.get(f"/api/tasks/{body['task']['id']}", headers={"X-RS-Roles": "admin"})
    assert detail.status_code == 200
    assert detail.json()["retryOf"] == "task-retry-source"


def test_queued_imagery_task_can_be_canceled_with_permission(isolated_env):
    app_module = reload_app_module()
    queued_task = sample_task("task-cancel-queued") | {
        "status": "queued",
        "progress": 0,
        "message": "Queued",
    }
    app_module.save_tasks([queued_task])
    client = TestClient(app_module.app)

    denied = client.post(
        "/api/tasks/task-cancel-queued/cancel",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    canceled = client.post(
        "/api/tasks/task-cancel-queued/cancel",
        headers={"X-RS-Roles": "admin", "X-RS-User": "operator-a"},
    )
    detail = client.get("/api/tasks/task-cancel-queued", headers={"X-RS-Roles": "admin"})

    assert denied.status_code == 403
    assert "imagery.tasks.cancel" in denied.json()["detail"]
    assert canceled.status_code == 200
    body = canceled.json()
    assert body["ok"] is True
    assert body["task"]["status"] == "canceled"
    assert body["task"]["progress"] == 100
    assert body["task"]["canceledBy"] == "operator-a"
    assert body["task"]["events"][-1]["action"] == "cancel"
    assert body["task"]["events"][-1]["actor"] == "operator-a"
    assert detail.json()["status"] == "canceled"


def test_terminal_imagery_task_can_be_archived_and_hidden_from_default_list(isolated_env):
    app_module = reload_app_module()
    failed_task = sample_task("task-archive-failed") | {
        "status": "failed",
        "progress": 100,
        "message": "GDAL failed",
    }
    app_module.save_tasks([failed_task])
    client = TestClient(app_module.app)

    denied = client.post(
        "/api/tasks/task-archive-failed/archive",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    archived = client.post(
        "/api/tasks/task-archive-failed/archive",
        headers={"X-RS-Roles": "admin", "X-RS-User": "operator-b"},
    )
    default_list = client.get("/api/tasks", headers={"X-RS-Roles": "admin"})
    archived_list = client.get("/api/tasks?includeArchived=true", headers={"X-RS-Roles": "admin"})

    assert denied.status_code == 403
    assert "imagery.tasks.archive" in denied.json()["detail"]
    assert archived.status_code == 200
    body = archived.json()
    assert body["ok"] is True
    assert body["task"]["status"] == "failed"
    assert body["task"]["archivedBy"] == "operator-b"
    assert body["task"]["events"][-1]["action"] == "archive"
    assert body["task"]["events"][-1]["actor"] == "operator-b"
    assert default_list.status_code == 200
    assert default_list.json()["tasks"] == []
    assert archived_list.status_code == 200
    assert archived_list.json()["tasks"][0]["id"] == "task-archive-failed"
    assert archived_list.json()["tasks"][0]["archivedAt"]


def test_archived_imagery_task_listing_requires_archive_permission(isolated_env):
    app_module = reload_app_module()
    archived_task = sample_task("task-archived-permission") | {
        "status": "failed",
        "progress": 100,
        "message": "GDAL failed",
        "archivedAt": "2026-07-09T00:00:00+08:00",
        "archivedBy": "operator-b",
    }
    app_module.save_tasks([archived_task])
    client = TestClient(app_module.app)

    default_list = client.get("/api/tasks", headers={"X-RS-Roles": "imagery.scenes.view"})
    denied = client.get(
        "/api/tasks?includeArchived=true",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    allowed = client.get(
        "/api/tasks?includeArchived=true",
        headers={"X-RS-Roles": "imagery.scenes.view,imagery.tasks.archive"},
    )

    assert default_list.status_code == 200
    assert default_list.json()["tasks"] == []
    assert denied.status_code == 403
    assert "imagery.tasks.archive" in denied.json()["detail"]
    assert allowed.status_code == 200
    assert allowed.json()["tasks"][0]["id"] == "task-archived-permission"


def test_scene_can_be_published_as_map_layer_with_audit_event(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene())
    client = TestClient(app_module.app)

    denied = client.post(
        "/api/scenes/scene-publish-001/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-001"]},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    managed_publish = client.post(
        "/api/scenes/scene-publish-001/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-001"]},
        headers={"X-RS-Roles": "imagery.scenes.manage,map.layers.create,map.layers.publish"},
    )
    published = client.post(
        "/api/scenes/scene-publish-001/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-001", "BLOCK-002"], "zIndex": 35},
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )

    assert denied.status_code == 403
    assert "imagery.layers.publish" in denied.json()["detail"]
    assert managed_publish.status_code == 200
    assert managed_publish.json()["ok"] is True
    assert published.status_code == 200
    body = published.json()
    assert body["ok"] is True
    assert body["layer"]["recordCode"] == "SCENE-LAYER-scene-publish-001"
    assert body["layer"]["layerType"] == "imagery"
    assert body["layer"]["status"] == "published"
    assert body["layer"]["visibleOnDashboard"] is True
    assert body["layer"]["linkedBlockCodes"] == ["BLOCK-001", "BLOCK-002"]
    assert body["layer"]["zIndex"] == 35
    assert body["layer"]["properties"]["sourceSceneId"] == "scene-publish-001"
    assert body["layer"]["sourceType"] == "imagery"
    assert body["layer"]["adminHref"] == "admin-map-layers.html?layerCode=SCENE-LAYER-scene-publish-001"
    assert body["layer"]["dashboardHref"] == "zhushan-bigdata.html#mapLayers"
    assert body["layer"]["sourceLinks"] == [
        {
            "type": "imagery",
            "label": "影像场景",
            "value": "scene-publish-001",
            "href": "admin-imagery.html?sceneId=scene-publish-001",
        }
    ]
    assert body["layer"]["properties"]["bounds"] == [117.55, 26.05, 118.85, 27.2]
    assert body["event"]["action"] == "publish-layer"
    assert body["event"]["actor"] == "alice"

    layers = client.get("/api/map-layers?q=SCENE-LAYER-scene-publish-001")
    layer_events = client.get(
        "/api/map-layers/events?recordCode=SCENE-LAYER-scene-publish-001&action=publish-from-scene&q=alice",
        headers={"X-RS-Roles": "admin"},
    )
    scene = client.get("/api/scenes/scene-publish-001")

    assert layers.status_code == 200
    assert layers.json()["total"] == 1
    layer_item = layers.json()["items"][0]
    assert layer_item["id"] == body["layer"]["id"]
    assert layer_item["properties"]["auditEvents"][-1]["action"] == "publish-from-scene"
    assert layer_item["properties"]["auditEvents"][-1]["actor"] == "alice"
    assert layer_events.status_code == 200
    assert layer_events.json()["total"] == 1
    assert layer_events.json()["items"][0]["actor"] == "alice"
    assert layer_events.json()["items"][0]["sourceType"] == "imagery"
    assert scene.status_code == 200
    assert scene.json()["publishEvents"][-1]["layerId"] == body["layer"]["id"]
    assert scene.json()["publishedLayerId"] == body["layer"]["id"]


def test_scene_layer_publish_requires_map_layer_write_permissions(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-map-permission-001"))
    client = TestClient(app_module.app)

    missing_map_create = client.post(
        "/api/scenes/scene-map-permission-001/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-001"]},
        headers={"X-RS-Roles": "imagery.layers.publish"},
    )
    assert missing_map_create.status_code == 403
    assert "map.layers.create" in missing_map_create.json()["detail"]

    missing_map_publish = client.post(
        "/api/scenes/scene-map-permission-001/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-001"], "visibleOnDashboard": True},
        headers={"X-RS-Roles": "imagery.layers.publish,map.layers.create"},
    )
    assert missing_map_publish.status_code == 403
    assert "map.layers.publish" in missing_map_publish.json()["detail"]

    allowed = client.post(
        "/api/scenes/scene-map-permission-001/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-001"], "visibleOnDashboard": True},
        headers={"X-RS-Roles": "imagery.layers.publish,map.layers.create,map.layers.publish"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["layer"]["recordCode"] == "SCENE-LAYER-scene-map-permission-001"


def test_archiving_imagery_scene_hides_published_layer_and_records_lifecycle(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-archive-001"))
    client = TestClient(app_module.app)

    published = client.post(
        "/api/scenes/scene-archive-001/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-001"], "zIndex": 31},
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    denied = client.post(
        "/api/scenes/scene-archive-001/archive",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    archived = client.post(
        "/api/scenes/scene-archive-001/archive",
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )
    layers = client.get(
        "/api/map-layers?q=SCENE-LAYER-scene-archive-001",
        headers={"X-RS-Roles": "admin"},
    )
    scene = client.get("/api/scenes/scene-archive-001", headers={"X-RS-Roles": "admin"})

    assert published.status_code == 200
    assert published.json()["layer"]["status"] == "published"
    assert published.json()["layer"]["visibleOnDashboard"] is True
    assert denied.status_code == 403
    assert "imagery.scenes.archive" in denied.json()["detail"]
    assert archived.status_code == 200
    body = archived.json()
    assert body["ok"] is True
    assert body["archived"] == "scene-archive-001"
    assert body["scene"]["status"] == "archived"
    assert body["scene"]["visible"] is False
    assert body["event"]["action"] == "archive"
    assert body["event"]["actor"] == "bob"
    assert body["event"]["layerRecordCode"] == "SCENE-LAYER-scene-archive-001"
    assert body["layer"]["status"] == "archived"
    assert body["layer"]["visibleOnDashboard"] is False
    assert body["layer"]["properties"]["archivedBy"] == "bob"
    assert layers.status_code == 200
    assert layers.json()["total"] == 1
    assert layers.json()["items"][0]["status"] == "archived"
    assert layers.json()["items"][0]["visibleOnDashboard"] is False
    assert scene.status_code == 200
    assert scene.json()["lifecycleEvents"][-1]["action"] == "archive"
    assert scene.json()["publishedLayerId"] == published.json()["layer"]["id"]


def test_imagery_scene_events_can_be_listed_across_scenes(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-events-001") | {"name": "Huangcun bamboo orthophoto"})
    app_module.save_scene(sample_scene("scene-events-002") | {"name": "Deleted bamboo orthophoto"})
    client = TestClient(app_module.app)

    published = client.post(
        "/api/scenes/scene-events-001/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-001"], "zIndex": 31},
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    archived = client.post(
        "/api/scenes/scene-events-001/archive",
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )
    deleted = client.delete(
        "/api/scenes/scene-events-002",
        headers={"X-RS-Roles": "admin", "X-RS-User": "chen"},
    )
    denied = client.get(
        "/api/scenes/events",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    listed = client.get("/api/scenes/events?limit=20", headers={"X-RS-Roles": "admin"})
    publish_only = client.get(
        "/api/scenes/events?eventType=publish&sceneId=scene-events-001",
        headers={"X-RS-Roles": "admin"},
    )
    archive_only = client.get(
        "/api/scenes/events?action=archive&q=bob",
        headers={"X-RS-Roles": "admin"},
    )
    scene_two = client.get(
        "/api/scenes/events?sceneId=scene-events-002",
        headers={"X-RS-Roles": "admin"},
    )

    assert published.status_code == 200
    assert archived.status_code == 200
    assert deleted.status_code == 200
    assert denied.status_code == 403
    assert "imagery.scenes.view" in denied.json()["detail"]
    assert listed.status_code == 200
    body = listed.json()
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["total"] == 3
    actions = {(item["sceneId"], item["eventType"], item["action"]) for item in body["items"]}
    assert ("scene-events-001", "publish", "publish-layer") in actions
    assert ("scene-events-001", "lifecycle", "archive") in actions
    assert ("scene-events-002", "lifecycle", "soft-delete") in actions

    publish_event = next(item for item in body["items"] if item["eventType"] == "publish")
    assert publish_event["eventId"]
    assert publish_event["sceneName"] == "Huangcun bamboo orthophoto"
    assert publish_event["actor"] == "alice"
    assert publish_event["layerRecordCode"] == "SCENE-LAYER-scene-events-001"
    assert publish_event["summary"] == "publish: publish-layer"

    assert publish_only.status_code == 200
    assert publish_only.json()["total"] == 1
    assert publish_only.json()["items"][0]["eventType"] == "publish"
    assert archive_only.status_code == 200
    assert archive_only.json()["total"] == 1
    assert archive_only.json()["items"][0]["actor"] == "bob"
    assert scene_two.status_code == 200
    assert scene_two.json()["total"] == 1
    assert scene_two.json()["items"][0]["action"] == "soft-delete"


def test_scenes_can_be_filtered_by_catalog_status(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-status-active") | {"status": "active"})
    app_module.save_scene(sample_scene("scene-status-archived") | {"status": "archived", "visible": False})
    client = TestClient(app_module.app)

    denied_archived = client.get(
        "/api/scenes?status=archived",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    archived = client.get(
        "/api/scenes?status=archived",
        headers={"X-RS-Roles": "imagery.scenes.view,imagery.scenes.archive"},
    )
    active = client.get("/api/scenes?status=active", headers={"X-RS-Roles": "imagery.scenes.view"})
    default_list = client.get("/api/scenes", headers={"X-RS-Roles": "imagery.scenes.view"})

    assert denied_archived.status_code == 403
    assert "imagery.scenes.archive" in denied_archived.json()["detail"]
    assert archived.status_code == 200
    assert [scene["id"] for scene in archived.json()["scenes"]] == ["scene-status-archived"]
    assert active.status_code == 200
    assert [scene["id"] for scene in active.json()["scenes"]] == ["scene-status-active"]
    assert default_list.status_code == 200
    assert [scene["id"] for scene in default_list.json()["scenes"]] == ["scene-status-active"]


def test_deleting_imagery_scene_soft_deletes_catalog_record_and_preserves_assets(isolated_env):
    app_module = reload_app_module()
    cog_path = app_module.DATA_DIR / "cogs" / "soft-delete-scene.tif"
    cog_path.parent.mkdir(parents=True, exist_ok=True)
    cog_path.write_bytes(b"cog-asset")
    scene = sample_scene("scene-soft-delete-001") | {
        "cogPath": "cogs/soft-delete-scene.tif",
        "originalPath": "uploads/soft-delete-source.tif",
    }
    app_module.save_scene(scene)
    client = TestClient(app_module.app)

    deleted = client.delete(
        "/api/scenes/scene-soft-delete-001",
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    listed = client.get("/api/scenes", headers={"X-RS-Roles": "admin"})
    detail = client.get("/api/scenes/scene-soft-delete-001", headers={"X-RS-Roles": "admin"})
    raw_catalog = json.loads(app_module.CATALOG_PATH.read_text(encoding="utf-8"))

    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert deleted.json()["softDeleted"] is True
    assert deleted.json()["deleted"] == "scene-soft-delete-001"
    assert cog_path.exists()
    assert listed.status_code == 200
    assert listed.json()["total"] == 0
    assert detail.status_code == 404
    stored = raw_catalog["scenes"][0]
    assert stored["id"] == "scene-soft-delete-001"
    assert stored["status"] == "deleted"
    assert stored["deletedAt"]
    assert stored["deletedBy"] == "alice"
    assert stored["lifecycleEvents"][-1]["action"] == "soft-delete"
    assert stored["lifecycleEvents"][-1]["actor"] == "alice"


def test_deleting_published_imagery_scene_archives_its_map_layer(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-delete-layer-001"))
    client = TestClient(app_module.app)

    published = client.post(
        "/api/scenes/scene-delete-layer-001/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-001"], "zIndex": 31},
        headers={"X-RS-Roles": "admin", "X-RS-User": "publisher"},
    )
    deleted = client.delete(
        "/api/scenes/scene-delete-layer-001",
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    layers = client.get(
        "/api/map-layers?q=SCENE-LAYER-scene-delete-layer-001",
        headers={"X-RS-Roles": "admin"},
    )
    deleted_scene = client.get(
        "/api/scenes?status=deleted",
        headers={"X-RS-Roles": "admin"},
    )

    assert published.status_code == 200
    assert published.json()["layer"]["status"] == "published"
    assert deleted.status_code == 200
    body = deleted.json()
    assert body["ok"] is True
    assert body["layer"]["status"] == "archived"
    assert body["layer"]["visibleOnDashboard"] is False
    assert body["layer"]["properties"]["archivedBy"] == "alice"
    assert body["layer"]["properties"]["archiveReason"] == "source-scene-deleted"
    assert body["layer"]["properties"]["deletedSceneId"] == "scene-delete-layer-001"
    assert layers.status_code == 200
    assert layers.json()["total"] == 1
    assert layers.json()["items"][0]["status"] == "archived"
    assert layers.json()["items"][0]["visibleOnDashboard"] is False
    assert deleted_scene.json()["scenes"][0]["lifecycleEvents"][-1]["layerRecordCode"] == "SCENE-LAYER-scene-delete-layer-001"


def test_deleted_imagery_scene_can_be_listed_and_restored_by_manager(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-restore-001"))
    client = TestClient(app_module.app)

    deleted = client.delete(
        "/api/scenes/scene-restore-001",
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    denied_list = client.get(
        "/api/scenes?includeDeleted=true",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    deleted_list = client.get(
        "/api/scenes?includeDeleted=true",
        headers={"X-RS-Roles": "admin"},
    )
    denied_restore = client.post(
        "/api/scenes/scene-restore-001/restore",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    restored = client.post(
        "/api/scenes/scene-restore-001/restore",
        headers={"X-RS-Roles": "admin", "X-RS-User": "bob"},
    )
    active_detail = client.get("/api/scenes/scene-restore-001", headers={"X-RS-Roles": "admin"})
    active_list = client.get("/api/scenes", headers={"X-RS-Roles": "admin"})
    raw_catalog = json.loads(app_module.CATALOG_PATH.read_text(encoding="utf-8"))

    assert deleted.status_code == 200
    assert denied_list.status_code == 403
    assert "imagery.scenes.restore" in denied_list.json()["detail"]
    assert deleted_list.status_code == 200
    assert deleted_list.json()["total"] == 1
    assert deleted_list.json()["scenes"][0]["status"] == "deleted"
    assert denied_restore.status_code == 403
    assert "imagery.scenes.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    body = restored.json()
    assert body["ok"] is True
    assert body["restored"] == "scene-restore-001"
    assert body["scene"]["status"] == "active"
    assert body["scene"].get("deletedAt") is None
    assert body["event"]["action"] == "restore"
    assert body["event"]["actor"] == "bob"
    assert active_detail.status_code == 200
    assert active_list.json()["total"] == 1
    stored = raw_catalog["scenes"][0]
    assert stored["deletedAt"] is None
    assert stored["deletedBy"] == ""
    assert stored["lifecycleEvents"][-1]["action"] == "restore"


def test_deleted_imagery_scene_can_be_filtered_by_status_for_manager(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-status-deleted"))
    client = TestClient(app_module.app)

    deleted = client.delete(
        "/api/scenes/scene-status-deleted",
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    denied = client.get(
        "/api/scenes?status=deleted",
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    listed = client.get(
        "/api/scenes?status=deleted",
        headers={"X-RS-Roles": "admin"},
    )

    assert deleted.status_code == 200
    assert denied.status_code == 403
    assert "imagery.scenes.restore" in denied.json()["detail"]
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["scenes"][0]["id"] == "scene-status-deleted"
    assert listed.json()["scenes"][0]["status"] == "deleted"


def test_imagery_scene_metadata_can_be_updated_by_manager(isolated_env):
    app_module = reload_app_module()
    app_module.save_scene(sample_scene("scene-metadata-001"))
    client = TestClient(app_module.app)

    denied = client.patch(
        "/api/scenes/scene-metadata-001",
        json={"name": "Denied update"},
        headers={"X-RS-Roles": "business.farmers.manage"},
    )
    updated = client.patch(
        "/api/scenes/scene-metadata-001",
        json={
            "name": "Updated bamboo orthophoto",
            "satellite": "DJI Mavic 3M",
            "sensor": "MS/RGB",
            "capturedAt": "2026-07-08",
            "resolution": "0.05m",
            "bounds": [117.6, 26.1, 117.9, 26.4],
            "projectId": "zhushan-ops",
            "areaCode": "350703",
            "allowedRoles": ["admin", "imagery_operator"],
            "allowedUsers": "alice,bob",
            "visible": False,
            "opacity": 0.65,
        },
        headers={"X-RS-Roles": "admin", "X-RS-User": "mapper"},
    )
    detail = client.get(
        "/api/scenes/scene-metadata-001",
        headers={"X-RS-Roles": "admin", "X-RS-User": "alice"},
    )
    events = client.get(
        "/api/scenes/events?action=metadata-update&sceneId=scene-metadata-001",
        headers={"X-RS-Roles": "admin"},
    )

    assert denied.status_code == 403
    assert "imagery.scenes.update" in denied.json()["detail"]
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Updated bamboo orthophoto"
    assert body["satellite"] == "DJI Mavic 3M"
    assert body["sensor"] == "MS/RGB"
    assert body["capturedAt"] == "2026-07-08"
    assert body["resolution"] == "0.05m"
    assert body["bounds"] == [117.6, 26.1, 117.9, 26.4]
    assert body["projectId"] == "zhushan-ops"
    assert body["areaCode"] == "350703"
    assert body["allowedRoles"] == ["admin", "imagery_operator"]
    assert body["allowedUsers"] == ["alice", "bob"]
    assert body["visible"] is False
    assert body["opacity"] == 0.65
    assert body["event"]["action"] == "metadata-update"
    assert body["event"]["actor"] == "mapper"
    assert set(body["event"]["changedFields"]) >= {"name", "satellite", "bounds", "allowedUsers", "opacity"}
    assert detail.status_code == 200
    assert detail.json()["name"] == "Updated bamboo orthophoto"
    assert detail.json()["lifecycleEvents"][-1]["action"] == "metadata-update"
    assert events.status_code == 200
    assert events.json()["total"] == 1
    assert events.json()["items"][0]["actor"] == "mapper"


def test_imagery_scene_keeps_asset_type_mission_and_forest_block_relations(isolated_env):
    app_module = reload_app_module()
    scene = sample_scene("scene-v2-imagery-fields") | {
        "assetType": "orthophoto",
        "missionId": "UAV-2026-001",
        "linkedBlockCodes": ["35078410620204101020"],
        "processingStage": "ready",
    }
    app_module.save_scene(scene)
    client = TestClient(app_module.app)

    response = client.patch(
        "/api/scenes/scene-v2-imagery-fields",
        json={
            "assetType": "dsm",
            "missionId": "UAV-2026-002",
            "linkedBlockCodes": ["35078410620204101020", "35078410620204101021"],
            "processingStage": "ready",
        },
        headers={"X-RS-Roles": "imagery.scenes.update"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["assetType"] == "dsm"
    assert body["missionId"] == "UAV-2026-002"
    assert body["linkedBlockCodes"] == ["35078410620204101020", "35078410620204101021"]
    assert set(body["event"]["changedFields"]) >= {
        "assetType",
        "missionId",
        "linkedBlockCodes",
    }


def test_imagery_action_permissions_control_scene_and_task_workflows(isolated_env):
    app_module = reload_app_module()
    retry_source = isolated_env / "action-retry-source.tif"
    retry_source.write_bytes(b"not-a-real-tiff")
    app_module.save_scene(sample_scene("scene-action-permission-001"))
    app_module.save_scene(sample_scene("scene-action-permission-delete"))
    app_module.save_tasks(
        [
            sample_task("task-action-cancel") | {"status": "queued"},
            sample_task("task-action-retry")
            | {"status": "failed", "progress": 100, "sourcePath": str(retry_source), "retryAttempt": 1},
            sample_task("task-action-archive") | {"status": "completed", "progress": 100},
        ]
    )
    client = TestClient(app_module.app)

    denied_create = client.post(
        "/api/scenes/upload",
        files={"file": ("permission-scene.tif", io.BytesIO(b"tif"), "image/tiff")},
        data={"asyncMode": "true", "name": "Permission scene"},
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    created = client.post(
        "/api/scenes/upload",
        files={"file": ("permission-scene.tif", io.BytesIO(b"tif"), "image/tiff")},
        data={"asyncMode": "true", "name": "Permission scene"},
        headers={"X-RS-Roles": "imagery.scenes.create"},
    )
    denied_update = client.patch(
        "/api/scenes/scene-action-permission-001",
        json={"name": "Denied update"},
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    updated = client.patch(
        "/api/scenes/scene-action-permission-001",
        json={"name": "Allowed update"},
        headers={"X-RS-Roles": "imagery.scenes.update"},
    )
    denied_archive = client.post(
        "/api/scenes/scene-action-permission-001/archive",
        headers={"X-RS-Roles": "imagery.scenes.update"},
    )
    archived = client.post(
        "/api/scenes/scene-action-permission-001/archive",
        headers={"X-RS-Roles": "imagery.scenes.archive"},
    )
    denied_delete = client.delete(
        "/api/scenes/scene-action-permission-delete",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    deleted = client.delete(
        "/api/scenes/scene-action-permission-delete",
        headers={"X-RS-Roles": "imagery.scenes.delete"},
    )
    denied_restore = client.post(
        "/api/scenes/scene-action-permission-delete/restore",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    restored = client.post(
        "/api/scenes/scene-action-permission-delete/restore",
        headers={"X-RS-Roles": "imagery.scenes.restore"},
    )
    denied_cancel = client.post(
        "/api/tasks/task-action-cancel/cancel",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    canceled = client.post(
        "/api/tasks/task-action-cancel/cancel",
        headers={"X-RS-Roles": "imagery.tasks.cancel"},
    )
    denied_retry = client.post(
        "/api/tasks/task-action-retry/retry",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    retried = client.post(
        "/api/tasks/task-action-retry/retry",
        headers={"X-RS-Roles": "imagery.tasks.retry"},
    )
    denied_task_archive = client.post(
        "/api/tasks/task-action-archive/archive",
        headers={"X-RS-Roles": "imagery.scenes.view"},
    )
    task_archived = client.post(
        "/api/tasks/task-action-archive/archive",
        headers={"X-RS-Roles": "imagery.tasks.archive"},
    )
    managed_publish = client.post(
        "/api/scenes/scene-action-permission-delete/publish-layer",
        json={"linkedBlockCodes": ["BLOCK-001"]},
        headers={"X-RS-Roles": "imagery.scenes.manage,map.layers.create,map.layers.publish"},
    )

    assert denied_create.status_code == 403
    assert "imagery.scenes.create" in denied_create.json()["detail"]
    assert created.status_code == 202
    assert denied_update.status_code == 403
    assert "imagery.scenes.update" in denied_update.json()["detail"]
    assert updated.status_code == 200
    assert denied_archive.status_code == 403
    assert "imagery.scenes.archive" in denied_archive.json()["detail"]
    assert archived.status_code == 200
    assert denied_delete.status_code == 403
    assert "imagery.scenes.delete" in denied_delete.json()["detail"]
    assert deleted.status_code == 200
    assert denied_restore.status_code == 403
    assert "imagery.scenes.restore" in denied_restore.json()["detail"]
    assert restored.status_code == 200
    assert denied_cancel.status_code == 403
    assert "imagery.tasks.cancel" in denied_cancel.json()["detail"]
    assert canceled.status_code == 200
    assert denied_retry.status_code == 403
    assert "imagery.tasks.retry" in denied_retry.json()["detail"]
    assert retried.status_code == 200
    assert denied_task_archive.status_code == 403
    assert "imagery.tasks.archive" in denied_task_archive.json()["detail"]
    assert task_archived.status_code == 200
    assert managed_publish.status_code == 200
    assert managed_publish.json()["ok"] is True
