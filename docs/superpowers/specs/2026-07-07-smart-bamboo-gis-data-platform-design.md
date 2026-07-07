# 智慧竹山 GIS 数据底座正式化设计

日期：2026-07-07

## 1. 背景与判断

现有仓库已经有两个可用雏形：

- 智慧竹山大数据页面：`zhushan-bigdata.html`、`zhushan-bigdata.js`、`zhushan-bigdata.css`，已有 OpenLayers 地图、天地图、离线底图、黄坑/康内村边界、林班示例图层、业务弹窗和遥感 SDK 影像同步。
- 卫星图传管理系统：`satellite-manager.html`、`satellite-manager.js`、`satellite-manager.css`，已有 GeoTIFF/TIFF 上传、COG 转换任务、影像目录、图层权限、Token、缓存管理和服务端检索。
- 共享能力：`sdk/remote-sensing-sdk.js` 和 `server/app.py` 已形成 FastAPI + GDAL/rasterio + rio-tiler/TiTiler 的遥感图层服务，并预留 PostGIS、GeoServer、天地图代理缓存。

可研报告给出的长期方向是“全国领先的竹产业综合服务平台”，近期目标是完成南平 100 万亩竹山资源整合与数字化建档，并上线包含资源监管、智慧管护、物流调度、交易撮合、供应链金融的“竹业大脑”。因此第一阶段不应先做一堆独立业务应用，而应把地图、林班、影像、图层、权限和数据管理做成稳定底座。

核心产品判断：

先建设“地图 + 数据管理 + 展示”的企业 GIS 运营工作台，后续所有业务应用都围绕统一林班编码、空间边界、影像资料、权限体系和数据接口扩展。

## 2. 产品目标

第一阶段目标：

1. 让 100 万亩竹山数据可以批量导入、校验、入库、查询、筛选、编辑和地图展示。
2. 让林班边界、权属、经营状态、林种分类、质量等级、风险等级、影像资料和作业数据进入统一数据模型。
3. 让现有智慧竹山地图页从演示数据升级为后端驱动的数据工作台。
4. 让现有卫星图传管理系统成为平台的影像/图层管理模块。
5. 让系统具备 Docker Compose 部署能力，支持本地、NAS、单机服务器和后续拆分部署。

非目标：

- 第一阶段不实现真正的 AI 产量识别模型，只预留模型结果表和 API。
- 第一阶段不实现真正的交易撮合、供应链金融、碳汇备案，只建立这些应用所需的基础数据关系。
- 第一阶段不重写现有地图与遥感 SDK，只在其上工程化扩展。

## 3. 用户与角色

第一阶段角色：

- 平台管理员：维护用户、角色、区县/乡镇权限、系统配置、图层权限。
- 基地运营人员：导入林班、编辑属性、查看影像、维护作业和风险状态。
- GIS/遥感管理员：上传影像、注册 NAS 大文件、维护 COG/GeoServer 图层、清理缓存。
- 领导/汇报用户：查看大屏、统计、分层筛选结果。

后续角色：

- 竹农/林权人：查看托管林班、权益证、收益、管护记录。
- 合作社/村集体：查看加盟基地、服务进度、收益结算。
- 竹企/加工企业：查看可采资源、供给计划、溯源批次。
- 政府/林业监管：查看绩效、生态风险、项目进度、合规红线。

## 4. 可研报告中的应用体系

底座必须支撑以下应用：

1. 竹林资产运营中心
   - 林班档案、林权/经营权、托管协议、权益证、自营基地、加盟基地、竹林等级、资产台账。

2. 智慧竹山一张图
   - 林班边界、行政区划、地形、卫星影像、无人机正射影像、质量等级、土壤墒情、长势、病虫害、产量预测、权属、道路、水池、作业点位分层展示。

3. 基础数据采集与建模
   - 三维激光雷达、专题数据库、竹龄、胸径、树高、健康状况、林分类型、空间边界、影像资料。

4. 物联网监测管控
   - 土壤温湿度、养分、空气温湿度、光照、降雨量、设备状态、无人机、竹材分解机、烘干烤房等设备接入。

5. AI 与智能分析
   - 产量统计与预测、竹笋/成竹识别、长势分析、智能采伐/挖笋/抚育方案。

6. 无人机与低空作业服务
   - 无人机巡护、吊运、航拍、作业路线、任务调度、设备运行、故障预警。

7. 运输与溯源
   - 竹材、竹笋从采伐、运输、加工到成品的追踪，GPS/北斗轨迹、批次二维码、溯源报告。

8. 加盟托管服务平台
   - 申请受理、资源核查、合同签订、管护执行、监测反馈、收益结算。

9. 农资与标准化作业服务
   - 农资集采、配方肥、生物农药、SOP 作业手册、技术培训、专家远程诊断。

10. 交易、供应链金融、价格指数
    - 在线交易、物流协同、供应链金融、质量认证、南平价格指数。

11. 碳汇与生态价值应用
    - 碳汇计量、碳汇备案、生态服务功能、水土保持、固碳释氧、生态绩效评价。

12. 安全与应急管理
    - 森林防火、病虫害、防偷盗、巡护、隐患点、应急预案、风险台账。

## 5. 分期路线

### 阶段 1：GIS 数据底座正式化

交付：

- PostGIS 林班数据库。
- 林班批量导入、字段映射、导入校验和导入报告。
- 林班后台列表、详情、编辑、删除、版本记录。
- 地图分层筛选：区县、乡镇、村、基地类型、经营类型、林种、面积、质量等级、健康状态、风险等级、影像时间。
- 遥感影像与林班关联。
- 基础权限：用户、角色、区域范围、图层/影像/林班可见性。
- Docker Compose：应用服务、PostGIS、可选 GeoServer、可选 Nginx。

### 阶段 2：运营管护应用

交付：

- 托管协议、加盟基地、林农/合作社主体、管护任务、作业记录、巡护记录。
- 无人机任务、设备台账、设备状态、作业轨迹。
- 病虫害预警、隐患点、处置闭环。
- 农资服务、SOP 作业模板、培训记录。

### 阶段 3：经营决策应用

交付：

- 产量预测结果管理、采伐/挖笋计划、收益测算。
- 绩效看板、年度计划、项目进度、亩均收益。
- 碳汇基础测算、生态服务指标、碳汇项目台账。

### 阶段 4：产业平台应用

交付：

- 交易撮合、供应链协同、物流轨迹、二维码溯源。
- 供应链金融、林权抵押增信材料、价格指数。
- 竹农/合作社移动端、政府监管端、企业采购端。

## 6. 第一阶段信息架构

第一阶段保留现有两个入口，并增加一个统一后台入口：

- `zhushan-bigdata.html`：面向展示和运营调度的一张图工作台。
- `satellite-manager.html`：影像、遥感图层、COG、缓存、GeoServer 管理。
- 新增 `admin` 后台：林班数据、导入任务、主体、字典、权限、系统配置。

页面导航建议：

1. 一张图
2. 林班台账
3. 批量导入
4. 影像图层
5. 主体档案
6. 管护任务
7. 统计看板
8. 系统设置

第一阶段只实现 1-4 和最小系统设置；5-8 保留菜单与空状态说明，避免虚假功能。

## 7. 数据模型

### 7.1 核心表

`forest_blocks`

- `id`: UUID。
- `block_code`: 林班/小班唯一编号。
- `name`: 林班名称。
- `county_code`, `county_name`: 区县。
- `town_code`, `town_name`: 乡镇。
- `village_code`, `village_name`: 村。
- `base_type`: `self_operated` 或 `franchise`。
- `operation_type`: `timber`, `dual_regular`, `dual_high_yield`, `understory`, `other`。
- `forest_type`: 毛竹、笋竹两用、竹材用林等。
- `area_mu`: 面积，亩。
- `slope_degree`: 坡度。
- `ownership_status`: 权属状态。
- `management_status`: 已托管、洽谈中、待核查、管护中、暂停。
- `quality_grade`: A/B/C/D 或优/中/改造/风险。
- `health_status`: 正常、关注、预警、严重。
- `risk_level`: low、medium、high、critical。
- `bamboo_age`: 竹龄描述。
- `avg_dbh_cm`: 平均胸径。
- `avg_height_m`: 平均树高。
- `standing_density`: 立竹密度。
- `carbon_estimate_tco2e`: 碳汇估算。
- `yield_estimate`: 产量估算 JSON。
- `tags`: 标签数组。
- `geometry`: MultiPolygon，SRID 4326。
- `centroid`: Point，SRID 4326。
- `source_batch_id`: 最近一次导入批次。
- `created_at`, `updated_at`, `deleted_at`。

`forest_block_versions`

- 记录林班每次导入或编辑前后的属性与几何快照。

`import_batches`

- `id`, `file_name`, `file_type`, `status`, `total_rows`, `valid_rows`, `invalid_rows`, `created_by`, `created_at`, `completed_at`, `report_json`。

`map_layers`

- 管理业务图层、遥感图层、GeoServer WMS/WMTS 图层、静态 GeoJSON 图层。

`layer_permissions`

- 用户、角色、区域、项目维度的图层可见性。

`subjects`

- 林农、村集体、合作社、企业、政府单位等主体档案。

`block_subject_links`

- 林班和主体的关系：权属、托管、加盟、服务、采购。

`operation_tasks`

- 管护、巡护、施肥、采伐、挖笋、病虫害处置、无人机航拍、无人机吊运等任务。

`sensor_devices`

- 物联网设备、无人机、机械设备、烘干烤房等设备台账。

`trace_batches`

- 采伐/采收批次、运输轨迹、溯源码关联。

### 7.2 与现有遥感目录的关系

现有 `remote_sensing_scenes` 或 `catalog.json` 继续负责 COG 影像目录。新增关系表：

`forest_block_scene_links`

- `forest_block_id`
- `scene_id`
- `relation_type`: 覆盖、局部覆盖、历史影像、巡护影像、正射影像、专题图。
- `captured_at`
- `confidence`

## 8. 导入设计

支持格式：

- CSV。
- Excel `.xlsx`。
- GeoJSON。
- Shapefile ZIP。
- 后续可支持 GPKG、KML/KMZ。

导入流程：

1. 上传文件。
2. 识别格式和字段。
3. 预览前 20 行。
4. 字段映射：林班编号、名称、行政区、面积、经营类型、质量等级、风险等级、权属、备注、几何。
5. 校验：编号唯一、面积有效、行政区存在、几何合法、几何不为空、坐标系可识别。
6. 入库：新增、更新、跳过三种策略。
7. 生成导入报告。
8. 地图自动刷新对应图层。

错误处理：

- 文件解析失败：返回可读错误，保留上传记录。
- 部分行失败：有效行可入库，失败行写入报告。
- 几何无效：尝试自动修复；修复失败则标记为无效。
- 坐标系未知：默认按 EPSG:4326 处理，并在报告中警告。
- 重复编号：按用户选择新增失败、覆盖更新或跳过。

## 9. 地图与筛选设计

地图保留现有 OpenLayers 架构，新增后端驱动的林班矢量图层。

筛选维度：

- 行政层级：区县、乡镇、村。
- 经营层级：自营、加盟、待核查。
- 林种/用途：竹材用林、常规笋竹两用林、高产笋竹两用林、林下经济。
- 面积范围。
- 质量等级。
- 健康状态。
- 风险等级。
- 影像日期。
- 是否有托管协议。
- 是否有关联主体。
- 是否有近期任务。

地图交互：

- 点击林班打开右侧详情。
- 详情支持只读和编辑模式。
- 切换图层不会清空当前筛选。
- 筛选结果同步更新统计卡片。
- 支持按当前视野 bbox 查询，避免一次性加载全部 100 万亩数据。
- 超过 5000 个面时启用服务端聚合或矢量瓦片策略。

## 10. API 设计

第一阶段新增 API：

- `GET /api/forest-blocks`
- `POST /api/forest-blocks`
- `GET /api/forest-blocks/{id}`
- `PATCH /api/forest-blocks/{id}`
- `DELETE /api/forest-blocks/{id}`
- `GET /api/forest-blocks/{id}/versions`
- `GET /api/forest-blocks/{id}/scenes`
- `POST /api/forest-blocks/{id}/scenes`
- `DELETE /api/forest-blocks/{id}/scenes/{scene_id}`
- `POST /api/imports/forest-blocks`
- `GET /api/imports/{batch_id}`
- `GET /api/imports/{batch_id}/report`
- `GET /api/map/forest-blocks.geojson`
- `GET /api/map/forest-blocks/summary`
- `GET /api/dictionaries`

查询参数：

- `countyCode`
- `townCode`
- `villageCode`
- `baseType`
- `operationType`
- `qualityGrade`
- `healthStatus`
- `riskLevel`
- `q`
- `bbox`
- `limit`
- `offset`

现有遥感 API 保持兼容。

## 11. 权限设计

第一阶段采用简单但可升级的权限：

- 用户具备角色。
- 用户可绑定可访问行政区。
- 林班、图层、影像都可按行政区和角色过滤。
- 地图查询、列表查询、详情读取、编辑、删除都走同一套权限上下文。
- 继续兼容现有 `X-RS-*` 和 Token 方案，后续升级为正式登录。

操作权限：

- 管理员：全部。
- 运营人员：可导入、编辑授权区域林班。
- GIS 管理员：可管理影像、图层、缓存、GeoServer。
- 只读用户：只能查看授权区域。

## 12. 部署设计

第一阶段提供 Docker Compose：

- `app`: FastAPI 应用，托管 API 和静态页面。
- `db`: PostGIS。
- `geoserver`: 可选。
- `nginx`: 可选，生产反向代理。
- `data`: 影像、导入文件、缓存挂载目录。

环境变量：

- `DATABASE_URL`
- `REMOTE_SENSING_DATA_DIR`
- `REMOTE_SENSING_CATALOG_BACKEND=postgis`
- `REMOTE_SENSING_AUTH_REQUIRED`
- `REMOTE_SENSING_API_TOKENS`
- `REMOTE_SENSING_TIANDITU_TK`
- `REMOTE_SENSING_CORS_ORIGINS`

部署模式：

1. 本地开发：FastAPI + 本地文件目录 + PostGIS 容器。
2. NAS 一体化：静态页面、API、影像数据同机。
3. 正式拆分：应用服务器 + GIS/GDAL 服务器 + 数据盘/NAS + 可选 GeoServer。

## 13. 测试策略

后端测试：

- 林班 CRUD。
- CSV/Excel/GeoJSON/Shapefile ZIP 导入。
- 字段映射和错误报告。
- bbox 空间查询。
- 权限过滤。
- 影像与林班关联。

前端测试：

- 林班列表筛选。
- 地图筛选和图层开关。
- 详情编辑保存。
- 导入流程。
- 影像管理页原有能力回归。

部署验证：

- `docker compose up` 后 `/api/health` 正常。
- PostGIS extension 正常。
- 导入示例林班后地图可见。
- 影像 COG 目录仍可同步。

## 14. 风险与取舍

风险 1：现有 `server/app.py` 已经较大，继续堆功能会难维护。

处理：第一阶段拆出 `server/modules/forest_blocks.py`、`server/modules/imports.py`、`server/modules/auth.py`、`server/modules/database.py`，保留现有遥感接口行为。

风险 2：100 万亩林班面数据可能导致浏览器卡顿。

处理：列表分页，地图按 bbox 查询；超过阈值后进入矢量瓦片或 GeoServer 图层模式。

风险 3：林班原始数据格式不统一。

处理：导入时做字段映射和报告，不强迫所有源文件一次性标准化。

风险 4：天地图、GeoServer、COG、离线地图同时存在，图层来源复杂。

处理：用 `map_layers` 表统一登记图层类型、来源、权限、默认显隐和 z-index。

风险 5：第一阶段范围过大。

处理：第一版只做林班、导入、地图、影像关联、权限、部署；托管协议、管护任务、交易、碳汇只建扩展表或菜单空状态，不做完整业务闭环。

## 15. 第一阶段验收标准

1. 可通过 Docker Compose 启动应用和 PostGIS。
2. 可导入至少 1000 条含几何的林班数据。
3. 导入报告能列出成功、失败、跳过和更新数量。
4. 地图可按行政区、经营类型、质量等级、风险等级筛选林班。
5. 点击林班可查看并编辑属性。
6. 林班编辑保存后，列表和地图详情同步更新。
7. 卫星图传管理系统原有 COG 上传、任务、缓存、目录能力不回退。
8. 林班可关联遥感影像，详情中能看到关联影像列表。
9. 不同角色或区域上下文只能看到授权范围内的林班和影像。
10. 文档说明本地、NAS、一体化和拆分部署方式。

## 16. 后续计划衔接

本设计通过后进入实施计划阶段。实施计划应拆成以下任务：

1. 数据库与模块化后端基础。
2. 林班 CRUD 与空间查询。
3. 批量导入与导入报告。
4. 前端林班管理后台。
5. 智慧竹山地图接入真实林班 API。
6. 影像与林班关联。
7. 权限统一。
8. Docker Compose 与部署文档。
9. 回归测试与示例数据。
