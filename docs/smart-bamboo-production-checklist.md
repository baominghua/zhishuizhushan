# 智慧竹山平台生产上线清单

本文用于把当前 MVP 从“能演示”推进到“可部署、可验收、可继续扩展”的项目状态。当前重点是地图底座、林班数据管理、批量导入、分层筛选和卫星影像关联。

## 1. 上线前环境

生产建议使用 `docker-compose.yml` 启动 FastAPI + PostGIS。上线前准备 `.env`：

```dotenv
SMART_BAMBOO_STORAGE_BACKEND=postgis
SMART_BAMBOO_DATABASE_URL=postgresql://smart_bamboo:change-me@db:5432/smart_bamboo
SMART_BAMBOO_APP_PORT=8010
SMART_BAMBOO_DB_PORT=5433

REMOTE_SENSING_AUTH_REQUIRED=1
REMOTE_SENSING_API_TOKENS={"admin-token":{"user":"admin","roles":["admin"],"projects":["*"],"areas":["*"]},"viewer-token":{"user":"viewer","roles":["viewer"],"projects":["*"],"areas":["*"]}}
```

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
- `deployment.smartBamboo.storageBackend` 为 `postgis`
- `deployment.smartBamboo.postgisEnabled` 为 `true`
- `deployment.smartBamboo.schemaReady` 为 `true`

## 3. 林班数据验收

林班管理至少验收以下流程：

1. 通过后台导入 CSV、XLSX、GeoJSON 或 Shapefile ZIP。
2. 导入报告能返回总行数、有效行、无效行和逐行错误。
3. 无效面积字段进入错误报告，不导致接口 500。
4. 同一 `blockCode` 在 `upsert` 策略下更新原记录，在 `skip` 策略下跳过。
5. 删除林班后前台列表和地图隐藏，但后端保留软删除记录。
6. 按县区、乡镇、经营类型、质量等级、健康状态、风险等级和 bbox 过滤能返回正确结果。

## 4. 地图分层验收

面向 100 万亩竹山，前端地图展示应优先采用分层筛选：

- 行政层级：县区、乡镇、村、小班/林班。
- 经营层级：自营、合作、流转、托管等。
- 风险层级：低、中、高风险。
- 质量层级：A、B、C 或后续项目定义的等级。
- 健康层级：正常、关注、异常。
- 影像层级：林班边界、影像覆盖、变化检测、巡护事件。

当前后端已经提供 `bbox`、分页、摘要统计和 PostGIS 空间索引基础，下一阶段可继续做瓦片化、聚合和大比例尺按需加载。

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
- 同一林班、同一 scene、同一 relationType 重复提交时应更新原关联。

## 7. 发布验证命令

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check admin.js
node --check zhushan-bigdata.js
node --check satellite-manager.js
docker compose config
```

当前开发机没有可用 Docker 命令时，`docker compose config` 需要在服务器或安装 Docker Desktop 后补验。

## 8. 下一阶段推荐顺序

1. 地图大数据性能：矢量瓦片、按 bbox 聚合、分级抽稀、前端图层状态持久化。
2. 生产权限体系：用户、角色、区域、项目、操作日志和审计。
3. 林班版本管理：导入批次、编辑历史、回滚和差异对比。
4. 卫星影像生产流：上传、COG 转换、金字塔、缩略图、覆盖范围自动入库。
5. 业务应用层：巡护、采收运输、托管收益、交易结算、碳汇金融和移动端角色应用。
