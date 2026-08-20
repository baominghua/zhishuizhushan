from __future__ import annotations

import io
import zipfile
from pathlib import Path

from server.v2.tools import build_map_publisher_archive


ROOT = Path(__file__).resolve().parents[1]


def test_map_publisher_archive_contains_runnable_windows_assistant():
    content = build_map_publisher_archive()
    assert len(content) > 10_000
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        assert "智慧竹山地图发布助手/启动地图发布助手.cmd" in names
        assert "智慧竹山地图发布助手/发布说明.md" in names
        assert "智慧竹山地图发布助手/scripts/SmartBambooMapPublisher.ps1" in names
        assert "智慧竹山地图发布助手/scripts/publish-batch.ps1" in names
        assert "智慧竹山地图发布助手/scripts/publish-material.ps1" in names


def test_map_publisher_download_endpoint_and_imagery_management_entry(app_client):
    response = app_client.get(
        "/api/v2/tools/map-publisher/download",
        headers={"X-RS-User": "publisher", "X-RS-Roles": "admin", "X-RS-Areas": "*"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "smart-bamboo-map-publisher.zip" in response.headers["content-disposition"]

    page = (ROOT / "apps" / "web-operations" / "src" / "pages" / "ImageryAssetsPage.tsx").read_text(encoding="utf-8")
    assert "地图发布助手" in page
    assert "/api/v2/tools/map-publisher/download" in page
