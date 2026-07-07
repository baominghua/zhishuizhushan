# GDAL + COG + TiTiler 服务

这个目录是卫星图传管理系统的后端服务。它负责接收 GeoTIFF/TIFF，使用 GDAL COG Driver 转成 Cloud Optimized GeoTIFF，再提供 OpenLayers 可直接加载的 XYZ PNG 瓦片。

## 启动

建议使用 Python 3.11 或 3.12。若 Python 3.14 上安装 `rasterio` 失败，请切换到 3.11/3.12，因为 GDAL 生态通常更早提供这些版本的 Windows wheel。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r server\requirements.txt
.\.venv\Scripts\python -m uvicorn server.app:app --host 0.0.0.0 --port 8010
```

然后打开：

```text
http://NAS-IP:8010/satellite-manager.html
```

## API

- `GET /api/health`：依赖和 TiTiler 挂载状态。
- `POST /api/scenes/upload`：上传 GeoTIFF/TIFF 并转 COG。
- `GET /api/scenes`：返回 COG 影像目录。
- `GET /api/scenes/{id}/tiles/{z}/{x}/{y}.png`：返回 PNG 瓦片。
- `GET /api/scenes/{id}/tilejson.json`：返回 TileJSON。
- `DELETE /api/scenes/{id}`：删除 COG 和原始上传文件。
- `/titiler/...`：如果安装了 `titiler.core`，会挂载通用 TiTiler COG 路由。

运行时数据位于 `data/remote-sensing/`，包括原始上传、COG 文件和目录 JSON。

## Docker Compose 部署

智慧竹山平台的一体化 Docker Compose 部署说明见：

```text
docs/deploy-smart-bamboo-platform.md
```
