# 智慧竹山平台 Docker Compose 部署说明

本文档用于在一台服务器上部署智慧竹山平台后端、静态前端和森林数据 PostGIS。

## 1. 部署内容

- `app`：FastAPI 服务，启动后同时提供静态页面和 `/api/*` 接口
- `db`：PostGIS 数据库，承载森林班块等平台数据
- `geoserver`：可选服务，按需通过 `geoserver` profile 启动

默认情况下，森林数据使用 PostGIS；遥感场景目录 `/api/scenes` 仍保持 JSON 目录模式。若需要把遥感场景目录也切到 PostGIS，可额外设置 `REMOTE_SENSING_CATALOG_BACKEND=postgis`。

## 2. 启动前准备

1. 安装 Docker 与 Docker Compose
2. 在项目根目录执行命令
3. 如需代理天地图或启用鉴权，先准备环境变量

推荐在项目根目录新建 `.env` 文件，例如：

```dotenv
SMART_BAMBOO_DATABASE_URL=postgresql://smart_bamboo:smart_bamboo_dev@db:5432/smart_bamboo
REMOTE_SENSING_TIANDITU_TK=你的天地图密钥
REMOTE_SENSING_CORS_ORIGINS=*
REMOTE_SENSING_AUTH_REQUIRED=0
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
| `REMOTE_SENSING_DATA_DIR` | 遥感数据目录，容器内默认 `/data/remote-sensing` |
| `REMOTE_SENSING_SERVE_STATIC` | 是否由 FastAPI 托管静态页面，默认 `1` |

### 可选变量

| 变量 | 作用 |
| --- | --- |
| `REMOTE_SENSING_CATALOG_BACKEND` | 遥感场景目录后端，默认 `json`，可改为 `postgis` |
| `REMOTE_SENSING_DATABASE_URL` | 遥感场景目录切到 PostGIS 时使用的连接串 |
| `REMOTE_SENSING_GEOSERVER_URL` | 接入外部 GeoServer 时的基础地址 |
| `REMOTE_SENSING_TIANDITU_TK` | 天地图密钥 |
| `REMOTE_SENSING_AUTH_REQUIRED` | 是否开启遥感接口鉴权 |
| `REMOTE_SENSING_API_TOKENS` | 遥感接口令牌配置，开启鉴权时使用 |

项目根目录的 `./data` 会挂载到容器内 `/data`，因此数据库外的遥感数据、缓存和导入文件都保存在宿主机本地。

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
