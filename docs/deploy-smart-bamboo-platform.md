# 智慧竹山平台 Docker Compose 部署说明

本文档用于在一台服务器上部署智慧竹山平台后端、静态前端和森林数据 PostGIS。

## 1. 部署内容

- `app`：FastAPI 服务，启动后同时提供静态页面和 `/api/*` 接口
- `db`：PostGIS 数据库，承载森林班块等平台数据
- `geoserver`：可选服务，按需通过 `geoserver` profile 启动

默认情况下，森林班块/平台数据使用 PostGIS；当前分支的遥感 COG 场景目录 `/api/scenes` 仍使用 JSON 文件目录，不支持通过 Compose 环境变量切换到 PostGIS。当前目录文件固定保存在 `/app/data/remote-sensing/catalog.json`。

## 2. 启动前准备

1. 安装 Docker 与 Docker Compose
2. 在项目根目录执行命令
3. 如需调整数据库账号或端口，先准备环境变量

推荐在项目根目录新建 `.env` 文件，例如：

```dotenv
SMART_BAMBOO_DATABASE_URL=postgresql://smart_bamboo:smart_bamboo_dev@db:5432/smart_bamboo
SMART_BAMBOO_STORAGE_BACKEND=postgis
SMART_BAMBOO_APP_PORT=8010
```

## 3. 启动服务

```powershell
docker compose up --build -d
```

如需同时启动 GeoServer：

```powershell
docker compose --profile geoserver up --build -d
```

## 4. 访问入口

默认服务地址：

```text
http://127.0.0.1:8010/admin.html
http://127.0.0.1:8010/zhushan-bigdata.html
http://127.0.0.1:8010/satellite-manager.html
http://127.0.0.1:8010/api/health
```

## 5. 数据与环境变量说明

### 必要变量

| 变量 | 作用 |
| --- | --- |
| `SMART_BAMBOO_STORAGE_BACKEND` | 平台森林数据存储方式，默认 `postgis` |
| `SMART_BAMBOO_DATABASE_URL` | 森林数据 PostGIS 连接串 |
| `REMOTE_SENSING_PORT` | FastAPI 容器监听端口，默认 `8010` |
| `REMOTE_SENSING_SERVE_STATIC` | 是否由 FastAPI 托管静态页面，默认 `1` |

### 可选变量

| 变量 | 作用 |
| --- | --- |
| `SMART_BAMBOO_DB_PORT` | 宿主机暴露的 PostGIS 端口，默认 `5433` |
| `POSTGRES_DB` | PostGIS 数据库名，默认 `smart_bamboo` |
| `POSTGRES_USER` | PostGIS 用户名，默认 `smart_bamboo` |
| `POSTGRES_PASSWORD` | PostGIS 密码，默认 `smart_bamboo_dev` |
| `GEOSERVER_PORT` | 启用 `geoserver` profile 时宿主机暴露端口，默认 `8080` |
| `GEOSERVER_ADMIN_USER` | GeoServer 管理员用户名 |
| `GEOSERVER_ADMIN_PASSWORD` | GeoServer 管理员密码 |

项目根目录的 `./data` 会挂载到容器内 `/app/data`。当前分支中，遥感场景目录、上传文件和生成后的 COG 都保存在 `/app/data/remote-sensing/` 下，其中目录清单文件为 `/app/data/remote-sensing/catalog.json`。

## 6. Nginx 反向代理

示例配置文件：

```text
deploy/nginx-smart-bamboo.conf
```

将其中的 `server_name` 改为实际域名后，可把 80 端口请求反向代理到 `127.0.0.1:8010`。

## 7. 健康检查与验收

建议依次检查：

```text
GET /api/health
GET /api/forest-blocks
GET /api/map/forest-blocks.geojson
GET /api/scenes
```

`/api/health` 返回值中应重点确认：

- `ok` 为 `true`
- `deployment.smartBamboo.storageBackend` 为 `postgis`
- `deployment.smartBamboo.postgisEnabled` 为 `true`

如果启用了 GeoServer profile，还可补充检查：

```text
http://127.0.0.1:8080/geoserver
```

## 8. 常用运维命令

查看配置：

```powershell
docker compose config
```

查看日志：

```powershell
docker compose logs -f app
docker compose logs -f db
```

停止并删除容器：

```powershell
docker compose down
```
