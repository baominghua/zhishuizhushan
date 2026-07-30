from pathlib import Path


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
