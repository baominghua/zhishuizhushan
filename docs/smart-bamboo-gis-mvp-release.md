# 智慧竹山 GIS 数据底座 MVP 发布说明

## 本次完成范围

本次 MVP 已完成首阶段 GIS 数据底座能力，覆盖以下模块：

- 林班数据 API：支持新增、查询、编辑、删除、GeoJSON 地图输出。
- 林班批量导入：支持 GeoJSON、CSV、XLSX、Shapefile ZIP，并产出导入报告。
- 林班管理后台：提供 `admin.html` 入口，支持筛选、详情编辑、导入、影像关联。
- 智慧竹山一张图：`zhushan-bigdata.html` 已接入林班 API，保留离线/演示兜底能力。
- 林班与遥感影像关联：支持以 scene id 维护林班关联影像。
- 权限上下文：新林班与关联接口已纳入 `X-RS-Roles`、`X-RS-Areas` 约束。
- Docker Compose 部署文档：已补齐 FastAPI + PostGIS + 可选 GeoServer 的部署说明。

## 入口地址

本地默认入口如下：

- `http://127.0.0.1:8010/admin.html`
- `http://127.0.0.1:8010/zhushan-bigdata.html`
- `http://127.0.0.1:8010/satellite-manager.html`
- `http://127.0.0.1:8010/api/health`

## 部署说明

- 本地或服务器部署以 `docker-compose.yml` 和 `docs/deploy-smart-bamboo-platform.md` 为准。
- 当前分支的林班平台数据生产存储目标为 PostGIS。
- 当前遥感场景目录 `/api/scenes` 仍以 JSON 目录文件为主，不依赖真实影像目录即可完成基础联调。
- 本次在当前工作站未实际执行 Docker 运行验证，因为本机缺少可用的 Docker 命令。

## 验证证据

### 1. 后端回归

执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_forest_blocks.py tests/test_imports.py tests/test_forest_scene_links.py -v
```

结果：

- `57 passed in 10.00s`

### 2. 前端脚本语法检查

执行：

```powershell
node --check admin.js
node --check zhushan-bigdata.js
node --check satellite-manager.js
```

结果：

- 三条命令均退出码 `0`

### 3. 本地服务与 HTTP 冒烟

本次使用隐藏窗口启动：

```powershell
Start-Process -WindowStyle Hidden .\.venv\Scripts\python.exe -ArgumentList '-m','uvicorn','server.app:app','--host','127.0.0.1','--port','8010'
```

以下校验均为 HTTP 状态与接口响应冒烟，不等同于浏览器内的人工视觉验收：

- `GET /api/health` 返回 `ok: true`
- `GET /admin.html` 返回 `HTTP/1.1 200 OK`
- `GET /zhushan-bigdata.html` 返回 `HTTP/1.1 200 OK`
- `GET /satellite-manager.html` 返回 `HTTP/1.1 200 OK`
- `GET /api/scenes` 返回 `total: 0`，空目录不报错
- `GET /api/cache/tiles` 返回缓存文件数 `0`
- `GET /api/cache/tianditu` 返回缓存文件数 `0`

### 4. 林班 API 工作流验证

在不打开浏览器的前提下，已通过 HTTP/API 验证以下流程：

1. 向 `/api/imports/forest-blocks` 导入 `data/samples/forest-blocks-sample.geojson`
2. 导入返回：
   - `status: completed`
   - `totalRows: 1`
   - `validRows: 1`
   - `invalidRows: 0`
3. 通过 `/api/forest-blocks?q=SAMPLE-001` 验证可检索到导入林班
4. 通过 `PATCH /api/forest-blocks/{id}` 将 `riskLevel` 从 `low` 更新为 `medium`
5. 通过 `/api/map/forest-blocks.geojson` 验证返回要素中的 `riskLevel` 已变为 `medium`

## 已知限制

- 本机 Docker 不可用，因此未执行 `docker compose up` 或容器内联调。
- 本次未使用浏览器做人工视觉验收，因此没有直接确认页面上的交互布局、地图点选弹窗和控制台可视化状态。
- 卫星管理页仅完成接口级冒烟与脚本语法检查，未接入真实影像目录、真实 COG 转换任务或可视地图操作。

## 下一阶段路线图

基于可研与实施计划，后续建议按以下方向扩展：

1. 运营与托管：托管协议、主体档案、收益结算、运营台账。
2. 巡护与 IoT：巡护工单、设备在线监测、告警闭环、无人机作业台账。
3. 运输与溯源：采收批次、运输轨迹、二维码追溯、到货核销。
4. 交易与结算：交易撮合、合同执行、供应链协同、结算对账。
5. 碳汇与金融：碳汇测算、生态价值评估、授信材料与金融接口。
6. 移动角色应用：竹农端、合作社端、企业端、监管端等移动化角色入口。
