from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from server.modules.admin_roles import require_permission
from server.modules.auth import AuthContext, request_context


router = APIRouter(prefix="/tools", tags=["v2-tools"])

PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "plugins" / "smart-bamboo-map-publisher"
DOWNLOAD_FILES = (
    ("assets/启动地图发布助手.cmd", "启动地图发布助手.cmd"),
    ("assets/发布说明.md", "发布说明.md"),
    ("assets/发布助手配置.example.json", "assets/发布助手配置.example.json"),
    ("assets/发布说明.md", "assets/发布说明.md"),
    ("scripts/SmartBambooMapPublisher.ps1", "scripts/SmartBambooMapPublisher.ps1"),
    ("scripts/publish-batch.ps1", "scripts/publish-batch.ps1"),
    ("scripts/publish-material.ps1", "scripts/publish-material.ps1"),
)


def build_map_publisher_archive() -> bytes:
    missing = [relative for relative, _ in DOWNLOAD_FILES if not (PLUGIN_ROOT / relative).is_file()]
    if missing:
        raise FileNotFoundError(", ".join(missing))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source_relative, archive_relative in DOWNLOAD_FILES:
            archive.write(PLUGIN_ROOT / source_relative, f"智慧竹山地图发布助手/{archive_relative}")
    return output.getvalue()


@router.get("/map-publisher/download")
def download_map_publisher(context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "imagery.scenes.create")
    try:
        content = build_map_publisher_archive()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="地图发布助手安装包不完整。") from exc
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=smart-bamboo-map-publisher.zip; filename*=UTF-8''%E6%99%BA%E6%85%A7%E7%AB%B9%E5%B1%B1%E5%9C%B0%E5%9B%BE%E5%8F%91%E5%B8%83%E5%8A%A9%E6%89%8B.zip",
            "Cache-Control": "no-store",
        },
    )
