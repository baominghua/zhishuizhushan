from pathlib import Path

import pytest
from fastapi import HTTPException


def test_cached_tianditu_tiles_are_immutable_for_browser_reuse(app_client, monkeypatch, tmp_path):
    import server.app as app_module

    cache_dir = tmp_path / "tianditu"
    monkeypatch.setattr(app_module, "TIANDITU_CACHE_DIR", cache_dir)
    cache_path = cache_dir / "img_w" / "9" / "1" / "2.png"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"\x89PNG\r\n\x1a\ncached")
    monkeypatch.setenv("REMOTE_SENSING_TIANDITU_TK", "test-token")
    monkeypatch.setattr(app_module, "TIANDITU_TK", "test-token")

    response = app_client.get("/api/basemaps/tianditu/img_w/9/1/2.png")

    assert response.status_code == 200
    assert response.headers["x-tianditu-cache"] == "HIT"
    assert response.headers["cache-control"] == (
        "public, max-age=2592000, stale-while-revalidate=86400, immutable"
    )


def test_deployment_readiness_warns_when_tianditu_proxy_has_no_server_key(monkeypatch):
    import server.app as app_module

    monkeypatch.setattr(app_module, "TIANDITU_TK", "")
    deployment = {
        "database": {
            "platform": {"reachable": True, "schemaReady": True},
            "remoteSensingCatalog": {
                "reachable": True,
                "schemaReady": True,
                "backend": "mysql",
                "mysqlEnabled": True,
            },
        },
        "smartBamboo": {
            "storageBackend": "mysql",
            "mysqlEnabled": True,
            "jsonData": {"dataDir": {"path": "data", "exists": True, "writable": True}},
        },
        "imagery": {
            "uploadDir": {"path": "uploads", "exists": True, "writable": True},
            "cogDir": {"path": "cogs", "exists": True, "writable": True},
            "importDirs": [{"path": "inbox", "exists": True, "writable": True}],
        },
        "auth": {"required": True, "tokensConfigured": 2},
        "apiChecks": [],
        "tiandituProxy": {"enabled": True, "hasServerTk": False},
    }

    readiness = app_module.deployment_readiness_summary(deployment)

    issue = next(item for item in readiness["warnings"] if item["key"] == "tianditu_server_key_missing")
    assert issue["section"] == "basemap"
    assert "REMOTE_SENSING_TIANDITU_TK" in issue["actionRequired"]

    deployment["tiandituProxy"]["hasServerTk"] = True
    monkeypatch.setattr(app_module, "TIANDITU_TK", "configured")

    ready = app_module.deployment_readiness_summary(deployment)

    assert all(item["key"] != "tianditu_server_key_missing" for item in ready["warnings"])


def test_tianditu_tiles_can_reuse_a_central_cache_without_distributing_the_key(
    app_client,
    monkeypatch,
    tmp_path,
):
    import server.app as app_module

    cache_dir = tmp_path / "tianditu-relay"
    monkeypatch.setattr(app_module, "TIANDITU_CACHE_DIR", cache_dir)
    monkeypatch.setattr(app_module, "TIANDITU_TK", "")
    monkeypatch.setattr(
        app_module,
        "TIANDITU_UPSTREAM_PROXY_BASE_URL",
        "https://tiles.example.test",
    )
    fetched = []

    def fake_proxy_fetch(layer, z, x, y):
        fetched.append((layer, z, x, y))
        return b"\x89PNG\r\n\x1a\nrelayed"

    monkeypatch.setattr(app_module, "fetch_tianditu_proxy_tile", fake_proxy_fetch)

    first = app_client.get("/api/basemaps/tianditu/img_w/9/1/2.png")
    second = app_client.get("/api/basemaps/tianditu/img_w/9/1/2.png")

    assert first.status_code == 200
    assert first.headers["x-tianditu-cache"] == "MISS"
    assert second.status_code == 200
    assert second.headers["x-tianditu-cache"] == "HIT"
    assert fetched == [("img_w", 9, 1, 2)]
    assert (cache_dir / "img_w" / "9" / "1" / "2.png").exists()


def test_tianditu_tiles_still_render_when_the_local_cache_is_read_only(
    app_client,
    monkeypatch,
    tmp_path,
):
    import server.app as app_module

    blocked_cache_root = tmp_path / "cache-file"
    blocked_cache_root.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(app_module, "TIANDITU_CACHE_DIR", blocked_cache_root)
    monkeypatch.setattr(app_module, "TIANDITU_TK", "")
    monkeypatch.setattr(
        app_module,
        "TIANDITU_UPSTREAM_PROXY_BASE_URL",
        "https://tiles.example.test",
    )
    monkeypatch.setattr(
        app_module,
        "fetch_tianditu_proxy_tile",
        lambda *_args: b"\x89PNG\r\n\x1a\nrelayed",
    )

    response = app_client.get("/api/basemaps/tianditu/img_w/9/1/2.png")

    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\n\x1a\nrelayed"
    assert response.headers["x-tianditu-cache"] == "BYPASS"


def test_tianditu_prewarm_task_populates_missing_tiles_and_reports_cache_hits(
    app_client,
    monkeypatch,
    tmp_path,
):
    import server.app as app_module

    cache_dir = tmp_path / "tianditu-prewarm"
    monkeypatch.setattr(app_module, "TIANDITU_CACHE_DIR", cache_dir)
    monkeypatch.setattr(app_module, "TIANDITU_TK", "test-token")

    class ImmediateExecutor:
        def submit(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(app_module, "TASK_EXECUTOR", ImmediateExecutor())
    fetched = []

    def fake_fetch(layer, z, x, y, tk, referer=""):
        fetched.append((layer, z, x, y, tk, referer))
        return b"\x89PNG\r\n\x1a\nfresh"

    monkeypatch.setattr(app_module, "fetch_tianditu_tile", fake_fetch)
    tiles = app_module.tianditu_tiles_for_bounds(
        [118.2, 26.6, 118.2001, 26.6001],
        min_zoom=12,
        max_zoom=12,
    )
    assert tiles == [(12, 3392, 1733)]

    cached_path = app_module.tianditu_cache_path("img_w", *tiles[0])
    cached_path.parent.mkdir(parents=True)
    cached_path.write_bytes(b"\x89PNG\r\n\x1a\ncached")

    task = app_module.create_tianditu_prewarm_task(
        bounds=[118.2, 26.6, 118.2001, 26.6001],
        min_zoom=12,
        max_zoom=12,
        layers=["img_w", "cia_w"],
        actor="test-admin",
    )
    assert "tiles" not in task
    app_module.run_tianditu_prewarm_task(task["id"])

    completed = app_module.find_task_record(task["id"])
    assert completed["status"] == "completed"
    assert completed["type"] == "basemap-prewarm"
    assert completed["tileCount"] == 2
    assert completed["cacheHits"] == 1
    assert completed["downloadedTiles"] == 1
    assert completed["failedTiles"] == 0
    assert [item[:4] for item in fetched] == [("cia_w", 12, 3392, 1733)]
    assert "tiles" not in completed


def test_tianditu_prewarm_rejects_excessive_tile_requests(app_client, monkeypatch):
    import server.app as app_module

    monkeypatch.setattr(app_module, "TIANDITU_TK", "test-token")
    monkeypatch.setattr(app_module, "TIANDITU_PREWARM_MAX_TILES", 1)

    with pytest.raises(HTTPException) as exc_info:
        app_module.create_tianditu_prewarm_task(
            bounds=[118.2, 26.6, 118.2001, 26.6001],
            min_zoom=12,
            max_zoom=12,
            layers=["img_w", "cia_w"],
            actor="test-admin",
        )

    assert exc_info.value.status_code == 422
    assert "2 tiles" in str(exc_info.value.detail)
    assert "maximum is 1" in str(exc_info.value.detail)
