# 智慧竹山平台生产上线清单

本文用于把当前 MVP 从“能演示”推进到“可部署、可验收、可继续扩展”的项目状态。当前重点是地图底座、林班数据管理、批量导入、分层筛选和卫星影像关联。

## 1. 上线前环境

生产建议使用 `docker-compose.yml` 启动 FastAPI + MySQL 8。上线前准备 `.env`：

```dotenv
MYSQL_PASSWORD=replace-with-strong-password
MYSQL_ROOT_PASSWORD=replace-with-strong-root-password
SMART_BAMBOO_DEPLOYMENT_MODE=production
SMART_BAMBOO_STORAGE_BACKEND=mysql
SMART_BAMBOO_DATABASE_URL=mysql://smart_bamboo:replace-with-url-encoded-password@db:3306/smart_bamboo?charset=utf8mb4
SMART_BAMBOO_APP_PORT=8010
SMART_BAMBOO_DB_PORT=3307

REMOTE_SENSING_CATALOG_BACKEND=mysql
REMOTE_SENSING_DATABASE_URL=mysql://smart_bamboo:replace-with-url-encoded-password@db:3306/smart_bamboo?charset=utf8mb4

REMOTE_SENSING_AUTH_REQUIRED=1
REMOTE_SENSING_API_TOKENS={"replace-with-random-admin-token":{"user":"admin","roles":["admin"],"projects":["*"],"areas":["*"]}}
REMOTE_SENSING_CORS_ORIGINS=https://bamboo.example.gov.cn
```

生产模式配置不满足 MySQL、强口令、鉴权 token 和受限 CORS 要求时，应用必须启动失败；禁止通过关闭 `SMART_BAMBOO_DEPLOYMENT_MODE=production` 绕过上线检查。

登录验收：访问 `/admin-login.html`，使用配置在 `REMOTE_SENSING_API_TOKENS` 中的 token 登录；确认 `/api/auth/me` 返回当前用户的角色、有效菜单、按钮权限和数据范围。退出后再次访问后台接口应返回 `401` 并跳转登录页，旧 token 不得继续留在浏览器会话中。

注意事项：
- 生产必须修改默认数据库密码和 token。
- `REMOTE_SENSING_AUTH_REQUIRED=1` 后，林班新增、编辑、删除、导入、影像关联写操作都需要有效 token。
- 本地开发可以保持 `REMOTE_SENSING_AUTH_REQUIRED=0`，便于调试页面和导入样例。

## 2. 核心验收入口

启动后依次检查：

```text
GET /api/health
GET /api/forest-blocks
GET /api/map/forest-blocks.geojson
GET /api/map/forest-blocks/summary
GET /api/map/forest-blocks/aggregates?level=town
GET /api/imports/forest-blocks/delivery-packages
GET /api/imports/{batch_id}/targets?kind=blocks&limit=100&offset=0
GET /api/dashboard/satellite-track
GET /api/dashboard/workflow-status
GET /api/scenes
```

页面入口：

```text
/admin.html
/zhushan-bigdata.html
/satellite-manager.html
```

`/api/health` 中需确认：
- `ok` 为 `true`
- `deployment.smartBamboo.storageBackend` 为 `mysql`
- `deployment.smartBamboo.mysqlEnabled` 为 `true`
- `deployment.smartBamboo.schemaReady` 为 `true`
- `deployment.database.platform.reachable` 为 `true`
- `deployment.database.platform.schemaReady` 为 `true`
- `deployment.database.remoteSensingCatalog.reachable` 为 `true`
- `deployment.database.remoteSensingCatalog.schemaReady` 为 `true`
- `deployment.readiness.status` 为 `ready`
- `deployment.readiness.blockingIssues` 为空数组
- `deployment.readiness.warnings` 中没有必须在生产前关闭的存储或鉴权警告
- `deployment.readiness.warnings` 中没有 `database_credentials_default`，平台库与遥感目录库均已替换开发/占位口令
- `deployment.apiChecks` 中所有核心接口均为 `available=true`，尤其要确认 `delivery_packages`、`dashboard_satellite_track` 和 `permission_catalog`

一键验收脚本输出的 MySQL 深度检查还需确认：
- `mysqlVersion` 为 MySQL 8+，且 `invalidMysqlVersion` 为空；
- `invalidEngines`、`invalidCollations`、`missingIndexes`、`invalidSpatialIndexes`、`missingForeignKeys` 均为空；
- 林班边界、林班质心、遥感覆盖范围三个空间索引均为 `SPATIAL`；
- 林班/林权挂接、角色/用户挂接、成果/影像/事件表外键均存在。
- `backfill_mysql_business_attributes.py` 已完成历史业务核心字段的分批索引回填；该过程不改写原业务台账，只重建 `business_record_attributes` 投影。

当 `SMART_BAMBOO_DATABASE_URL` 与 `REMOTE_SENSING_DATABASE_URL` 指向不同实例或数据库时，深度验收会分别输出 `platform` 与 `catalog`。平台报告只检查林班、林权、业务、权限、成果和关联表；目录报告只检查影像、影像空间范围、影像事件、任务和任务事件表。两个报告必须同时 `schemaReady=true`，不能用平台库中的空影像表代替真实目录库验收。

执行 `migrate_json_to_mysql.py` 或 `verify-production.ps1 -MigrateJson` 后还需确认：
- `sourceInventory` 覆盖林班、林权、版本、图层、业务主体、角色、用户、导入批次、影像、任务和林班影像关系；
- `targetInventory` 分别来自平台 MySQL 与遥感目录 MySQL 的实际聚合查询；
- `verification.verified=true`、`verification.missingRecords=0`、`verification.mismatches=[]`；
- 任一数据集目标数量小于源数量时命令以非零状态退出，生产脚本必须停止；目标库已有额外历史记录允许保留。

若 `/api/health` 返回 `503`，说明平台库或遥感影像目录库不可达，或关键表未初始化。上线前必须先排查 `deployment.database.*.error` 与 `deployment.database.*.missingTables`，不要只看页面是否能打开。

后台 `admin-deployment.html` 的“生产就绪结论”台账必须逐条清空阻断项。`status=warning` 只代表系统可运行，不代表已经适合正式上线。

## 3. 林班数据验收

林班管理至少验收以下流程：

1. 通过后台导入 CSV、XLSX、GeoJSON 或 Shapefile ZIP。
2. 导入报告能返回总行数、有效行、无效行和逐行错误。
3. 无效面积字段进入错误报告，不导致接口 500。
4. 同一 `blockCode` 在 `upsert` 策略下更新原记录，在 `skip` 策略下跳过。
5. 删除林班后前台列表和地图隐藏，但后端保留软删除记录。
6. 按县区、乡镇、经营类型、质量等级、健康状态、风险等级和 bbox 过滤能返回正确结果。
7. 编辑、删除、恢复林班后，`/api/forest-blocks/{block_id}/versions` 能查看版本历史。
8. 管理员可通过 `/api/forest-blocks/{block_id}/rollback` 回滚到指定版本，回滚操作本身也应形成新的版本记录。
9. 成果审核、验收和质检动作在 MySQL 中生成 `import_batch_events` 记录，审计列表不得依赖全量扫描 `report_json`。

林权档案管理需单独验收：
1. 林权档案新增、编辑、删除、恢复后，`/api/forest-rights/{right_id}/versions` 能查看独立版本历史。
2. 管理员可通过 `/api/forest-rights/{right_id}/rollback` 回滚法律凭证属性，回滚不应写入林班空间字段。
3. 林班台账与林权档案台账通过 `linkedBlockCodes` 挂接，二者仍保持独立 CRUD 与权限控制。

## 4. 地图分层验收

面向 100 万亩竹山，前端地图展示应优先采用分层筛选：

- 行政层级：县区、乡镇、村、小班/林班。
- 经营层级：自营、合作、流转、托管等。
- 风险层级：低、中、高风险。
- 质量层级：A、B、C 或后续项目定义的等级。
- 健康层级：正常、关注、异常。
- 影像层级：林班边界、影像覆盖、变化检测、巡护事件。

当前后端已经提供 `bbox`、分页、摘要统计、县/乡镇/村分级聚合、MySQL 8 空间索引和按缩放级别自适应的几何简化；大屏在低缩放级别显示聚合点，14 级及以上优先加载 `/api/map/forest-blocks/tiles/{z}/{x}/{y}.pbf` 矢量瓦片，并保存筛选、图层开关和地图视图状态。瓦片缓存键包含数据版本、筛选条件和用户有效数据范围，写入林班后自动换代；服务端按 TTL、最大容量和最大存活时间节流清理旧缓存。

MySQL 模式下的 `/api/map/forest-blocks/facets` 必须由数据库分组统计，禁止读取全量林班及几何到应用内存。验收需确认 `idx_forest_blocks_operation` 存在，并使用 `server/scripts/benchmark_mysql_forest_blocks.py` 记录 `operation-facet` 的 `EXPLAIN ANALYZE` 与 P95。

成果批量导入在 MySQL 模式下必须只查询本批涉及的 `block_code`，不得先加载全量林班台账；林班属性和空间边界按 `SMART_BAMBOO_MYSQL_WRITE_BATCH_SIZE` 分组执行 `executemany`，但整个批次只提交一次事务。导入批次与林班、林权的关系表按 500 条合并写入，避免十万级逐条数据库往返。关系表通过 `target_json` 保留单条来源元数据，`import_batches.report_json` 只保存摘要和工作流状态，不得重复保存完整 `importedBlocks`、`importedRightsArchives` 数组；数据库模式不得将完整报告长期驻留进程内存。后台通过 `/api/imports/{batch_id}/targets` 分页读取林班与林权明细，批次回滚必须按关系表定向软删除，不得扫描全量林班。可通过 `SMART_BAMBOO_IDENTITY_LOOKUP_BATCH_SIZE` 调整既有编号查询分组，默认值均为 `500`。

百万亩正式数据迁移完成后，在部署服务器执行：

```powershell
.\scripts\verify-production.ps1 -MigrateJson -BenchmarkMillionAcre
```

基准默认要求有效林班面积合计不少于 `1,000,000` 亩、所有查询命中预期索引、单项查询 P95 不超过 `500ms`，并在事务内写入 1,000 条临时林班及批次关系，吞吐不低于每秒 500 条，完成后必须回滚且不留下测试数据。验收同时要求没有批次继续在 `report_json` 中保存完整目标数组。可通过 `-MinimumAreaMu`、`-MaximumP95Ms`、`-BenchmarkIterations`、`-ImportWriteRows`、`-ImportWriteIterations` 和 `-MinimumImportWriteRowsPerSecond` 调整阈值；任一条件不满足时脚本以非零状态停止，不能视为生产验收通过。

## 5. 权限验收

建议至少准备两个 token：

- 管理员：`roles=["admin"]`，可写所有区域。
- 查看用户：`roles=["viewer"]`，只能读。

区域权限建议用 `areas` 控制，例如：

```json
{"user":"operator-a","roles":["operator"],"areas":["350703"],"projects":["*"]}
```

验收点：
- 无 token 写接口返回 `401`。
- `viewer` 写接口返回 `403`。
- 区域受限用户不能创建或移动林班到未授权县区。
- 区域受限用户只能看到授权县区数据。
- 角色权限页入口使用 `system.roles.view`；新增、编辑、删除、恢复、导出分别校验 `system.roles.create/update/delete/restore/export`。
- 用户账号页入口使用 `system.users.view`；新增、编辑、删除、恢复、导出分别校验 `system.users.create/update/delete/restore/export`。
- `system.roles.manage` 与 `system.users.manage` 仅作为兼容总权限，并必须在权限目录中展开显示其隐含动作权限。
- 只有查看权限时，台账与详情可读，新增、编辑、删除、恢复按钮应按动作权限分别禁用。

## 6. 卫星影像关联验收

当前林班可通过 scene id 关联遥感影像目录：

```text
GET    /api/forest-blocks/{block_id}/scenes
POST   /api/forest-blocks/{block_id}/scenes
DELETE /api/forest-blocks/{block_id}/scenes/{scene_id}
```

验收点：
- 不存在的 scene id 不能关联。
- 当前用户不可见的 scene 不能关联或删除。
- `REMOTE_SENSING_CATALOG_BACKEND=mysql` 时，影像存在性必须从 `REMOTE_SENSING_DATABASE_URL` 指向的 `remote_sensing_scenes` 查询，不得依赖本地 `catalog.json`。
- 平台库和遥感目录库使用不同连接串时，林班关联仍能读取目录库并写入平台库；目录库不可用时返回 503，交付包不得显示为“影像缺失”。
- 同一林班、同一 scene、同一 relationType 重复提交时应更新原关联。
- 影像发布、生命周期、质检、交付动作写入 `remote_sensing_scene_events`，转换任务状态变化写入 `remote_sensing_task_events`。
- `/api/scenes/events` 与 `/api/tasks/events` 在 MySQL 模式下直接读取事件关系表并支持条件筛选。

## 7. 发布验证命令

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check admin.js
node --check zhushan-bigdata.js
node --check satellite-manager.js
docker compose config
```

Health inventory must also be reviewed before release:

- `deployment.smartBamboo.jsonData.datasets` contains forest blocks, forest rights, map layers, admin roles/users, import batches, and aggregated business records.
- `deployment.smartBamboo.importTuning` confirms `incremental-batch`, positive MySQL write/identity lookup batch sizes, one transaction per forest-block batch, normalized relational report targets, and disabled database report caching.
- `deployment.imagery.catalog.recordCount` reflects the active imagery catalog count.
- `deployment.imagery.importDirs` shows every configured imagery inbox path with `exists` and `writable`.
- `deployment.apiChecks` confirms mounted core API routes for forest blocks, rights archives, map layers, import batches, delivery packages, dashboard satellite summary, imagery scenes, and permission catalog.
- `deployment.readiness.status` is `ready`, with `deployment.readiness.blockingIssues` empty.

当前开发机没有可用 Docker 命令时，`docker compose config` 需要在服务器或安装 Docker Desktop 后补验。

## 8. 下一阶段推荐顺序

1. 生产权限体系：在现有角色/用户独立 CRUD 权限、菜单入口权限和数据范围基础上，补登录会话、密码/单点登录、token 生命周期和登录审计。
2. 林班版本管理：导入批次、编辑历史、回滚和差异对比。
3. 卫星影像生产流：上传、COG 转换、金字塔、缩略图、覆盖范围自动入库。
4. 地图生产压测：在真实 MySQL 8 与百万亩级数据上记录聚合、矢量瓦片冷/热缓存和筛选查询 P95。
5. 业务应用层：巡护、采收运输、托管收益、交易结算、碳汇金融和移动端角色应用。

## 9. 管理员密码认证上线 gate

管理员密码认证按 `docs/admin-password-authentication-runbook.md` 分阶段上线。主节点固定使用 `/srv/smart-bamboo/config/primary.env` 与 `ops/compose.primary.yml`，热备固定使用 `/srv/smart-bamboo-dr/config/standby.env` 与 `ops/compose.standby.yml`。

上线顺序不得跳过：

1. 在主节点执行 `bash ops/scripts/backup-mysql.sh` 并保留生成的 `.sql.gz` 与 `.sha256`；云控制台同时建立发布前快照。
2. 拉取已审批提交并执行主、备 `docker compose ... config`。主节点先构建启动，但确认 `SMART_BAMBOO_HUMAN_AUTH_ENABLED=0`；热备只 pull/build 和验证复制，不启动 failover profile。
3. 通过 `/api/health` 和 `bash ops/scripts/verify-cluster.sh primary` 确认 MySQL schema、credential/session 表和应用 readiness；有旧私有数据时先 `--dry-run` 再运行 `server/scripts/migrate_json_to_mysql.py`，任何退出码非零或盘点不一致都停止。
4. 在主节点 app 容器中仅执行一次 `ops/scripts/bootstrap-admin-password.py`；自动产生的临时密码只显示一次，立即离线保存，首次登录后必须强制改密。
5. 在真实 HTTPS 和 Nginx proxy header 验收完成前不把 `SMART_BAMBOO_HUMAN_AUTH_ENABLED` 改为 `1`。启用后检查 secure cookie、受信 `X-Forwarded-Proto`、active admin credential、`deployment.readiness.status=ready`。
6. 人工验收临时登录、强制改密、用户/角色动作权限、projects/areas data scope、会话撤销、审计事件和只读 dashboard service token；确认后从 `REMOTE_SENSING_API_TOKENS` 撤销旧管理员 service token。
7. 认证回滚只能将主节点 `SMART_BAMBOO_HUMAN_AUTH_ENABLED=0` 后重建 app；严禁删除 credential/session 表或审计记录。

本机没有 Docker CLI 时，`docker compose config`、主/备 readiness、HTTPS 及浏览器验收均为云主机发布 gate，不能记录为本地通过。
