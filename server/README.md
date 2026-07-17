# GDAL + COG + TiTiler Service

这是遥感 SDK 的 GIS/GDAL 后端服务，负责：

- 接收 GeoTIFF/TIFF
- 使用 GDAL/rasterio 转为 COG
- 提供 COG 场景目录
- 提供 OpenLayers 可直接加载的 XYZ PNG 瓦片
- 提供后台转换任务与任务进度查询
- 支持注册服务器/NAS 已有 GeoTIFF/TIFF 文件入库
- 支持目录权限过滤、MySQL 8 正式目录库、兼容 PostGIS 迁移路径、GeoServer 图层接入和瓦片缓存
- 可选挂载 TiTiler 通用路由

## 启动

推荐 Python 3.11 或 3.12。

Windows：

```powershell
.\.venv\Scripts\python.exe -m pip install -r server\requirements-dev.txt
.\start-cog-server.ps1
```

Linux：

```bash
sh ./start-cog-server.sh
```

健康检查：

```text
http://服务器IP:8010/api/health
```

## API

- `GET /api/health`：依赖、TiTiler、部署配置状态。
- `POST /api/scenes/upload`：上传 GeoTIFF/TIFF 并转 COG。
- `POST /api/scenes/register`：注册服务器/NAS 已有 GeoTIFF/TIFF，创建后台转换任务。
- `GET /api/tasks`：查询后台转换任务列表。
- `GET /api/tasks/{task_id}`：查询单个后台转换任务。
- `GET /api/geoserver/config`：查看 GeoServer 配置。
- `GET /api/geoserver/layers`：查看 GeoServer 图层。
- `GET /api/cache/tiles`：查看瓦片缓存状态。
- `DELETE /api/cache/tiles`：清理瓦片缓存。
- `GET /api/scenes`：返回 COG 影像目录。
- `GET /api/scenes/{id}`：返回单个 COG 场景元数据。
- `GET /api/scenes/{id}/tiles/{z}/{x}/{y}.png`：返回 PNG 瓦片。
- `GET /api/map/forest-blocks/tiles/{z}/{x}/{y}.pbf`：返回按筛选和数据权限隔离的林班 MVT 矢量瓦片。
- `GET /api/scenes/{id}/tilejson.json`：返回 TileJSON。
- `DELETE /api/scenes/{id}`：删除 COG 和原始上传文件。
- `/titiler/...`：如果安装了 `titiler.core`，会挂载通用 TiTiler 路由。

## 部署配置

环境变量：

| 变量 | 作用 | 默认值 |
| --- | --- | --- |
| `REMOTE_SENSING_DATA_DIR` | 原始影像、COG、目录 JSON 存储位置 | `data/remote-sensing` |
| `REMOTE_SENSING_CORS_ORIGINS` | 允许访问 GIS API 的前端域名，多个用英文逗号分隔 | `*` |
| `REMOTE_SENSING_SERVE_STATIC` | 是否托管前端静态页面，拆分部署建议设为 `0` | `1` |
| `REMOTE_SENSING_STATIC_DIR` | 静态页面目录 | 项目根目录 |
| `REMOTE_SENSING_PORT` | 服务端口 | `8010` |
| `REMOTE_SENSING_IMPORT_DIRS` | 允许注册入库的服务器/NAS 文件目录，多个用英文逗号分隔 | `data/remote-sensing/inbox` |
| `REMOTE_SENSING_TASK_WORKERS` | 后台 COG 转换任务并发数 | `1` |
| `REMOTE_SENSING_CATALOG_BACKEND` | 目录库类型，正式环境使用 `mysql`，本地兼容 `json`，保留 `postgis` 迁移路径 | 本地 `json` / Docker `mysql` |
| `REMOTE_SENSING_DATABASE_URL` | MySQL 8 正式数据库连接串；兼容模式可传 PostGIS 连接串 | 空 |
| `REMOTE_SENSING_TILE_CACHE` | 是否启用瓦片落盘缓存，`1`/`0` | `1` |
| `SMART_BAMBOO_VECTOR_TILE_CACHE_TTL_SECONDS` | 林班 MVT 热缓存 TTL（秒） | `300` |
| `SMART_BAMBOO_VECTOR_TILE_CACHE_MAX_BYTES` | 林班 MVT 缓存容量上限 | `2147483648` |
| `SMART_BAMBOO_VECTOR_TILE_CACHE_MAX_AGE_SECONDS` | 林班 MVT 缓存最大存活时间（秒） | `86400` |
| `SMART_BAMBOO_VECTOR_TILE_CACHE_PRUNE_INTERVAL_SECONDS` | 林班 MVT 缓存清理最短间隔（秒） | `60` |
| `REMOTE_SENSING_GEOSERVER_URL` | GeoServer 服务根地址 | 空 |
| `REMOTE_SENSING_GEOSERVER_LAYERS` | 手工配置的 GeoServer 图层名，多个用英文逗号分隔 | 空 |

一体化测试部署可以直接使用默认值。

应用/GIS 拆分部署时建议：

```bash
export REMOTE_SENSING_SERVE_STATIC=0
export REMOTE_SENSING_DATA_DIR=/data/remote-sensing
export REMOTE_SENSING_CORS_ORIGINS=https://app.example.com
export REMOTE_SENSING_IMPORT_DIRS=/data/remote-sensing/inbox
export REMOTE_SENSING_TASK_WORKERS=1
export REMOTE_SENSING_PORT=8010
sh ./start-cog-server.sh
```

Windows：

```powershell
$env:REMOTE_SENSING_SERVE_STATIC = "0"
$env:REMOTE_SENSING_DATA_DIR = "D:\remote-sensing-data"
$env:REMOTE_SENSING_CORS_ORIGINS = "https://app.example.com"
$env:REMOTE_SENSING_IMPORT_DIRS = "D:\remote-sensing-data\inbox"
$env:REMOTE_SENSING_TASK_WORKERS = "1"
$env:REMOTE_SENSING_PORT = "8010"
.\start-cog-server.ps1
```

## 数据目录

默认数据目录：

```text
data/remote-sensing/
  uploads/      原始上传 GeoTIFF/TIFF
  inbox/        服务器/NAS 已有文件注册入库目录
  cogs/         转换后的 COG
  tile-cache/   PNG 瓦片缓存
  tasks.json    后台任务状态
  catalog.json 影像目录
```

300G 级遥感影像测试时，建议把 `REMOTE_SENSING_DATA_DIR` 指向独立 SSD/NAS 数据盘，并预留至少 2-3 倍原始影像大小的空间。

## Docker Compose 部署

智慧竹山平台的一体化 Docker Compose 部署说明见：

```text
docs/deploy-smart-bamboo-platform.md
```
