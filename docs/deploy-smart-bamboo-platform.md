# 智慧竹山平台 Docker Compose 部署说明

本文档用于在一台服务器上部署智慧竹山平台后端、静态前端和 MySQL 8 正式数据库。

## 1. 部署内容

- `app`：FastAPI 服务，启动后同时提供静态页面和 `/api/*` 接口
- `db`：MySQL 8 数据库，承载林班、林权、关系表、权限和业务台账
- `geoserver`：可选服务，按需通过 `geoserver` profile 启动

正式平台数据默认使用 MySQL 8。林班核心属性采用规范化列，边界写入独立几何表并建立空间索引；林权与林班、图层与林班、业务记录与林班均使用关系表挂接。影像目录、空间范围和转换任务同样写入 MySQL。成果审核/验收/质检事件、影像发布/交付事件和转换任务事件分别写入 `import_batch_events`、`remote_sensing_scene_events`、`remote_sensing_task_events`，事件台账不依赖扫描整条 JSON。JSON 列仅用于低频扩展属性和不可变版本快照，不用于替代台账表。遥感影像源文件、COG、瓦片缓存等大文件仍挂载在 `/app/data/remote-sensing/`，数据库只保存目录、任务和业务索引。

平台库与遥感目录库允许使用不同 MySQL 连接串。林班/成果批次挂接影像时，影像存在性和可见性始终按 `REMOTE_SENSING_CATALOG_BACKEND` 与 `REMOTE_SENSING_DATABASE_URL` 查询遥感目录库；MySQL 正式模式不会回落读取 `catalog.json`。目录库不可用时接口返回 503，不得把基础设施故障误报成“影像缺失”。

## 2. 启动前准备

1. 安装 Docker 与 Docker Compose
2. 在项目根目录执行命令
3. 如需调整数据库账号或端口，先准备环境变量

推荐在项目根目录新建 `.env` 文件，例如：

```dotenv
MYSQL_PASSWORD=replace-with-strong-password
MYSQL_ROOT_PASSWORD=replace-with-strong-root-password
SMART_BAMBOO_DEPLOYMENT_MODE=production
SMART_BAMBOO_DATABASE_URL=mysql://smart_bamboo:replace-with-url-encoded-password@db:3306/smart_bamboo?charset=utf8mb4
SMART_BAMBOO_STORAGE_BACKEND=mysql
REMOTE_SENSING_CATALOG_BACKEND=mysql
REMOTE_SENSING_DATABASE_URL=mysql://smart_bamboo:replace-with-url-encoded-password@db:3306/smart_bamboo?charset=utf8mb4
REMOTE_SENSING_DATA_DIR=/app/data/remote-sensing
REMOTE_SENSING_IMPORT_DIRS=/app/data/remote-sensing/inbox
REMOTE_SENSING_POINT_CLOUD_CHUNK_SIZE=16777216
REMOTE_SENSING_PDAL_EXECUTABLE=pdal
REMOTE_SENSING_3DTILES_EXECUTABLE=py3dtiles
REMOTE_SENSING_AUTH_REQUIRED=1
REMOTE_SENSING_API_TOKENS={"replace-with-random-token":{"user":"admin","roles":["admin"],"projects":["*"],"areas":["*"]}}
REMOTE_SENSING_CORS_ORIGINS=https://bamboo.example.gov.cn
SMART_BAMBOO_APP_PORT=8010
```

`SMART_BAMBOO_DEPLOYMENT_MODE=production` 会启用启动前强制校验。平台或影像目录未使用 MySQL、数据库口令仍为占位值、鉴权/token 未配置，或 CORS 仍为 `*` 时，应用会拒绝启动，不会静默回退到 JSON。

后台登录入口为 `/admin-login.html`。登录页通过 `GET /api/auth/me` 校验 Bearer token，并读取该身份的有效角色、菜单、按钮权限和数据范围；默认只保存在当前标签会话，勾选“在此浏览器保持登录”后才写入浏览器持久存储。后台接口返回 `401` 时会自动回到登录页并保留原页面作为安全的站内返回地址。退出登录会同时清除会话与持久 token。

## 3. 启动服务

从旧版 JSON 开发数据迁移前先只读清点：

```powershell
.\.venv\Scripts\python.exe server\scripts\migrate_json_to_mysql.py --dry-run
```

预检会严格解析每个已存在的 JSON 源文件；文件损坏、包装字段错误或记录不是对象时会立即失败并显示文件路径。正式迁移在源清单为 0 条时返回退出码 `3`，防止数据目录挂载错误时出现“空迁移成功”。

确认数量后执行幂等迁移：

```powershell
.\.venv\Scripts\python.exe server\scripts\migrate_json_to_mysql.py --database-url "mysql://smart_bamboo:change-me@127.0.0.1:3307/smart_bamboo?charset=utf8mb4"
```

迁移使用主键和唯一键更新，可重复执行；正式切换前仍应备份 `data/remote-sensing` 和 MySQL 数据卷。迁移完成后命令会输出 `sourceInventory`、`targetInventory` 和 `verification`：只有 `verification.verified=true`、`missingRecords=0` 时才算迁移通过；任一第一阶段数据集缺失都会列入 `mismatches` 并以退出码 `2` 终止发布流程。目标库已有的额外历史记录不会被误判为缺失。

迁移后运行索引与导入基准，记录台账、bbox、乡镇聚合和经营类型 facet 的执行计划及 P50/P95；同时测量批次目标复制到影像关系表、地图图层关系表的吞吐。导入和关系写入样本都在同一事务内完成后立即回滚，不会留下验收数据：

```powershell
.\.venv\Scripts\python.exe server\scripts\benchmark_mysql_forest_blocks.py --database-url "mysql://smart_bamboo:change-me@127.0.0.1:3307/smart_bamboo?charset=utf8mb4" --iterations 30 --import-write-rows 1000 --import-write-iterations 3 --relation-link-rows 1000 --relation-link-iterations 3 --min-relation-link-rows-per-second 1000
```

```powershell
docker compose up --build -d
```

也可以使用一键验收脚本完成 Compose 配置校验、构建启动、健康等待、MySQL Schema/索引/外键核验和迁移盘点：

```powershell
.\scripts\verify-production.ps1
```

确认迁移盘点数量无误后，显式执行旧 JSON 数据迁移：

```powershell
.\scripts\verify-production.ps1 -MigrateJson
```

`-MigrateJson` 会在写入后自动比较平台库与遥感目录库的实际记录数。脚本若报告 `JSON to MySQL migration failed`，应先按输出中的 `verification.mismatches` 修复缺失数据，不得继续切换生产存储。

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
| `SMART_BAMBOO_STORAGE_BACKEND` | 平台数据存储方式，正式环境为 `mysql` |
| `SMART_BAMBOO_DATABASE_URL` | MySQL 8 连接串 |
| `REMOTE_SENSING_CATALOG_BACKEND` | 遥感影像目录与任务存储方式，正式环境为 `mysql` |
| `REMOTE_SENSING_DATABASE_URL` | 遥感目录与转换任务使用的 MySQL 8 连接串 |
| `REMOTE_SENSING_DATA_DIR` | 遥感源文件、COG、瓦片缓存和 inbox 挂载目录 |
| `REMOTE_SENSING_IMPORT_DIRS` | 允许注册入库的服务器/NAS GeoTIFF、LAS/LAZ 目录 |
| `REMOTE_SENSING_PORT` | FastAPI 容器监听端口，默认 `8010` |
| `REMOTE_SENSING_SERVE_STATIC` | 是否由 FastAPI 托管静态页面，默认 `1` |

### 可选变量

| 变量 | 作用 |
| --- | --- |
| `SMART_BAMBOO_DB_PORT` | 宿主机暴露的 MySQL 端口，默认 `3307` |
| `REMOTE_SENSING_POINT_CLOUD_CHUNK_SIZE` | 点云断点续传分片大小，默认 16MB，服务端限制 5–128MB |
| `REMOTE_SENSING_PDAL_EXECUTABLE` | COPC 转换命令，镜像默认安装为 `pdal` |
| `REMOTE_SENSING_3DTILES_EXECUTABLE` | 3D Tiles 转换命令，镜像默认由 Python 包提供 `py3dtiles` |
| `SMART_BAMBOO_MYSQL_WRITE_BATCH_SIZE` | 林班 MySQL 批量写入分组大小，默认 `500`；单次导入仍在一个事务内提交 |
| `SMART_BAMBOO_IDENTITY_LOOKUP_BATCH_SIZE` | 导入前按林班编号查询既有记录的分组大小，默认 `500` |
| `SMART_BAMBOO_VECTOR_TILE_CACHE_TTL_SECONDS` | 林班矢量瓦片热缓存 TTL，默认 `300` 秒 |
| `SMART_BAMBOO_VECTOR_TILE_CACHE_MAX_BYTES` | 林班矢量瓦片缓存容量上限，默认 `2147483648`（2 GiB） |
| `SMART_BAMBOO_VECTOR_TILE_CACHE_MAX_AGE_SECONDS` | 林班矢量瓦片最大存活时间，默认 `86400` 秒 |
| `SMART_BAMBOO_VECTOR_TILE_CACHE_PRUNE_INTERVAL_SECONDS` | 缓存清理最短间隔，默认 `60` 秒 |
| `MYSQL_DATABASE` | MySQL 数据库名，默认 `smart_bamboo` |
| `MYSQL_USER` | MySQL 用户名，默认 `smart_bamboo` |
| `MYSQL_PASSWORD` | MySQL 业务账号密码 |
| `MYSQL_ROOT_PASSWORD` | MySQL root 密码，仅用于容器初始化 |
| `GEOSERVER_PORT` | 启用 `geoserver` profile 时宿主机暴露端口，默认 `8080` |
| `GEOSERVER_ADMIN_USER` | GeoServer 管理员用户名 |
| `GEOSERVER_ADMIN_PASSWORD` | GeoServer 管理员密码 |

项目根目录的 `./data` 会挂载到容器内 `/app/data`。遥感源文件、上传文件、生成后的 COG、COPC、3D Tiles、瓦片缓存和待入库 inbox 都保存在 `/app/data/remote-sensing/` 下。MySQL 保存可检索元数据和业务关系，不保存大型空间二进制文件。

大文件建议先由运维复制或挂载到 `/app/data/remote-sensing/inbox`，再在 V2“影像与点云成果”选择“服务器 / NAS 目录”：GeoTIFF 填文件路径，点云填一次航飞任务的目录。点云会递归接收 `.las/.laz`，自动排除 `.temp` 等隐藏工作目录；上传或注册完成后先计算跨林班交叠，只有业务人员确认后才写入正式林班关系。

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
GET /api/imports/forest-blocks/delivery-packages
GET /api/imports/{batch_id}/targets?kind=blocks&limit=100&offset=0
GET /api/dashboard/satellite-track
GET /api/scenes
```

`/api/health` 返回值中应重点确认：

- `ok` 为 `true`
- `deployment.smartBamboo.storageBackend` 为 `mysql`
- `deployment.smartBamboo.mysqlEnabled` 为 `true`
- `deployment.smartBamboo.importTuning.strategy` 为 `incremental-batch`，两个批量大小均大于 `0`，且 `singleTransaction=true`
- `deployment.smartBamboo.importTuning.mysqlReportTargets` 为 `normalized-relational`，`databaseReportCache` 为 `disabled`，`mysqlTargetRead` 为 `paginated-relational`，`mysqlRollback` 为 `targeted-relational`
- `deployment.smartBamboo.importTuning.mysqlSceneLink` 为 `insert-select-relational`，`mysqlSceneCoverage` 为 `aggregate-bounded-samples`，`mysqlLayerLink` 为 `copy-relational`；影像发布不得逐林班查询或把完整编号数组重复写入批次 JSON
- `deployment.smartBamboo.importTuning.mysqlLayerTargets` 为 `paginated-summary`，`mysqlLayerCrud` 为 `targeted-scalar`；图层列表只返回关系计数，普通发布、删除、恢复和元数据编辑不得加载或重写完整关系集合
- `deployment.smartBamboo.importTuning.mysqlBusinessTargets` 为 `paginated-summary`，`mysqlBusinessCrud` 为 `targeted-scalar`；经营主体列表按需分页读取林班与林权关系，普通字段编辑不得清空既有挂接
- `deployment.smartBamboo.importTuning.mysqlBusinessDashboard` 为 `aggregate-bounded-rows`；业务大屏统计必须由 MySQL 聚合，并且每个模块最多返回 100 条展示样本
- `deployment.smartBamboo.importTuning.mysqlRightTargets` 为 `paginated-summary`，`mysqlRightCrud` 为 `targeted-scalar`；林权列表和详情只返回关系计数，普通档案编辑不得重写完整林班挂接
- `deployment.database.platform.reachable` 为 `true`
- `deployment.database.platform.schemaReady` 为 `true`
- `deployment.database.remoteSensingCatalog.reachable` 为 `true`
- `deployment.database.remoteSensingCatalog.schemaReady` 为 `true`
- `deployment.readiness.status` 为 `ready`
- `deployment.readiness.blockingIssues` 为空数组
- `deployment.readiness.warnings` 中没有生产环境必须处理的安全或存储警告
- `deployment.readiness.warnings` 中没有 `database_credentials_default`；若出现，说明平台库或遥感目录库仍在使用已知开发/占位口令
- `deployment.apiChecks` 中 `forest_blocks`、`forest_rights`、`map_layers`、`import_batches`、`delivery_packages`、`dashboard_satellite_track`、`imagery_scenes`、`permission_catalog` 均为 `available=true`

平台库健康检查会同时覆盖林班、林权档案及其版本历史表；若 `forest_block_versions` 或 `forest_right_versions` 缺失，`deployment.database.platform.schemaReady` 应为 `false`。

一键脚本还会调用 `server/scripts/verify_mysql_production.py` 做比健康接口更严格的数据库验收。验收报告必须满足：

- 数据库为 MySQL 8 或更高版本，MariaDB 不作为等价替代品；
- 平台表全部使用 InnoDB 和 `utf8mb4`；
- 林班边界、林班质心与遥感影像覆盖范围均保留 `SPATIAL` 索引；
- MySQL 8.4 的 SRID 4326 按地理轴顺序存储；平台写入 WKT 时显式使用 `axis-order=long-lat`，质心查询使用 `ST_Longitude/ST_Latitude`，避免经纬互换及 `MULTIPOLYGON ST_Centroid` 方言限制；
- `forest_blocks` 使用 `idx_forest_blocks_town_active_updated`、`idx_forest_blocks_town_active_area` 和 `idx_forest_blocks_operation_active` 覆盖有效林班列表及聚合；既有数据库初始化时会先检查再补建缺失索引；
- 林班、林权、权限、导入批次、影像与事件关系表的关键外键全部存在；
- `missingTables`、`invalidEngines`、`invalidCollations`、`missingIndexes`、`invalidSpatialIndexes`、`missingForeignKeys` 均为空。

任一项不满足时，报告的 `schemaReady` 为 `false`，脚本以非零状态退出，不得继续作为正式上线验收通过。

`/api/map/forest-blocks/facets` 在 MySQL 模式下使用单次 `UNION ALL + COUNT/GROUP BY` 生成县区、乡镇、村、基地类型、经营类型、质量、健康和风险筛选桶，不读取林班几何或把全量林班搬入 Python 内存。服务器验收时应确认基准中的台账、空间、乡镇聚合和经营分面分别使用 `idx_forest_blocks_town_active_updated`、`idx_forest_block_geometry`、`idx_forest_blocks_town_active_area`、`idx_forest_blocks_operation_active`，并记录各自 P95。

如果平台库或遥感影像目录库连接失败、关键表缺失，`/api/health` 会返回 `503`，Docker Compose 的 app healthcheck 会随之变为不健康状态。此时优先查看 `deployment.database.*.error` 和 `deployment.database.*.missingTables`，再检查数据库连接串、MySQL 容器状态和 schema 初始化日志。

`deployment.readiness` 是生产上线总判断：`status=blocked` 表示存在阻断上线项，`status=warning` 表示系统可运行但仍有上线风险，`status=ready` 才能作为正式发布依据。后台 `admin-deployment.html` 会把 `deployment.readiness.blockingIssues` 和 `deployment.readiness.warnings` 渲染成生产就绪结论台账。

健康检查不会回显数据库密码。若检测到 Compose 默认值、`change-me` 等占位口令，只返回 `database_credentials_default` 和受影响的连接名称 `platform/catalog`。修改数据库实际账号口令后，必须同步更新 `SMART_BAMBOO_DATABASE_URL` 与 `REMOTE_SENSING_DATABASE_URL`。

如果启用了 GeoServer profile，还可补充检查：

```text
http://127.0.0.1:8080/geoserver
```

## 8. 常用运维命令

查看配置：

```powershell
docker compose config
```

确认 app healthcheck：
```powershell
docker compose ps
docker inspect --format "{{json .State.Health}}" $(docker compose ps -q app)
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

## 9. Deployment Health Inventory

`GET /api/health` also exposes a first-stage data inventory for operations:

- `deployment.smartBamboo.jsonData.datasets`: JSON fallback inventory for forest blocks, forest rights, map layers, admin roles/users, import batches, and aggregated business records.
- `deployment.smartBamboo.jsonData.businessModules`: per-business-module JSON record counts, useful when checking farmers, cooperatives, enterprises, plant protection, materials, policies, and later modules.
- `deployment.imagery.catalog.recordCount`: active remote-sensing scene count in the imagery catalog.
- `deployment.imagery.tasks.recordCount`: active imagery conversion or registration task count.
- `deployment.imagery.importDirs`: server/NAS imagery inbox directories with `exists` and `writable` status.
- `deployment.apiChecks`: mounted core API route checks for forest blocks, rights archives, map layers, import batches, delivery packages, dashboard satellite summary, imagery scenes, and permission catalog.
- `deployment.readiness.status`: production readiness state, one of `ready`, `warning`, or `blocked`.
- `deployment.readiness.blockingIssues`: blocking deployment issues that must be fixed before release.
- `deployment.readiness.warnings`: non-blocking production warnings, such as JSON fallback storage or disabled API auth.

In MySQL production mode, `deployment.database.*` remains the source of truth for schema readiness. The JSON inventory is only a migration and development fallback inventory; it is not the production data source.
