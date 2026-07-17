# 智慧竹山后台模块矩阵

原则：大屏和移动端只负责展示、交互和业务办理入口；后台负责数据维护、审核、关联、发布和权限配置。所有业务模块都要能通过林班编号、林权档案编号、主体编号互相关联。

## 第一阶段：数据库底座

| 能力 | 后台模块 | 页面 | 接口/数据路径 | 权限码 |
| --- | --- | --- | --- | --- |
| 林班空间地理单元 | 林班空间台账 | `admin-blocks.html` | `/api/forest-blocks` | `forest.blocks.manage` |
| 林权法律凭证档案 | 林权档案台账 | `admin-rights.html` | `/api/forest-rights` | `forest.rights.manage` |
| 图档证一致挂接 | 图档关联管理 | `admin-linkages.html` | 林班与林权 `linkedBlockCodes` | `forest.linkages.manage` |
| KMZ/OVKML/OVOBJ/GeoJSON 入库 | 成果入库 | `admin-imports.html` | `/api/imports/forest-blocks` | `imports.forestBlocks.manage` |
| 成果交付包验收 | 成果入库 | `admin-imports.html` | `/api/imports/forest-blocks/delivery-packages` | `imports.forestBlocks.view` / `imports.forestBlocks.export` |
| 影像与林班关联 | 影像管理 | `admin-imagery.html` | `/api/scenes`、`/api/tasks` | `imagery.scenes.manage` |
| 大屏卫星图传摘要 | 智慧竹山大屏 | `zhushan-bigdata.html` | `/api/dashboard/satellite-track` | 只读展示聚合 |
| 大屏成果/影像/图层闭环 | 智慧竹山大屏 | `zhushan-bigdata.html` | `/api/dashboard/workflow-status` | 公开只读汇总 |
| 百万亩林班分级聚合 | 智慧竹山大屏 | `zhushan-bigdata.html` | `/api/map/forest-blocks/aggregates` | `forest.blocks.view` |
| 地图专题发布 | 地图图层发布 | `admin-map-layers.html` | `/api/map-layers` | `map.layers.publish` |
| 菜单和按钮权限 | 角色权限管理 | `admin-roles.html` | `/api/admin/roles` | `system.roles.view/create/update/delete/restore/export`，`manage` 为兼容总权限 |
| 账号与角色分配 | 用户账号管理 | `admin-users.html` | `/api/admin/users` | `system.users.view/create/update/delete/restore/export`，`manage` 为兼容总权限 |
| 部署健康与上线验收 | 部署诊断 | `admin-deployment.html` | `/api/health`、`/api/deployment/report.json` | `system.deployment.view` |

## 第二阶段：运营管护应用

| 能力 | 后台模块 | 页面 | 接口 | 权限码 |
| --- | --- | --- | --- | --- |
| 托管经营协议 | 托管协议 | `admin-stewardship-agreements.html` | `/api/business/stewardship-agreements` | `business.stewardshipAgreements.manage` |
| 加盟/合作基地 | 加盟基地 | `admin-franchise-bases.html` | `/api/business/franchise-bases` | `business.franchiseBases.manage` |
| 巡护抚育任务 | 管护任务 | `admin-maintenance-tasks.html` | `/api/business/maintenance-tasks` | `business.maintenanceTasks.manage` |
| 现场作业台账 | 作业记录 | `admin-work-logs.html` | `/api/business/work-logs` | `business.workLogs.manage` |
| 无人机任务 | 无人机任务 | `admin-drone-tasks.html` | `/api/business/drone-tasks` | `business.droneTasks.manage` |
| 设备资产运维 | 设备台账 | `admin-equipment.html` | `/api/business/equipment` | `business.equipment.manage` |
| 病虫害预警 | 病虫害预警 | `admin-pest-warnings.html` | `/api/business/pest-warnings` | `business.pestWarnings.manage` |
| 农资配送服务 | 农资服务 | `admin-material-services.html` | `/api/business/material-services` | `business.materialServices.manage` |

## 第三阶段：经营决策应用

| 能力 | 后台模块 | 页面 | 接口 | 权限码 |
| --- | --- | --- | --- | --- |
| 产量预测 | 产量预测 | `admin-yield-forecasts.html` | `/api/business/yield-forecasts` | `business.yieldForecasts.manage` |
| 采伐/挖笋计划 | 采挖计划 | `admin-harvest-plans.html` | `/api/business/harvest-plans` | `business.harvestPlans.manage` |
| 收益测算 | 收益测算 | `admin-income-estimates.html` | `/api/business/income-estimates` | `business.incomeEstimates.manage` |
| 管护和经营绩效 | 绩效看板 | `admin-performance-dashboards.html` | `/api/business/performance-dashboards` | `business.performanceDashboards.manage` |
| 碳汇核算 | 碳汇测算 | `admin-carbon-estimates.html` | `/api/business/carbon-estimates` | `business.carbonEstimates.manage` |

## 第四阶段：产业平台应用

| 能力 | 后台模块 | 页面 | 接口 | 权限码 |
| --- | --- | --- | --- | --- |
| 供需与订单撮合 | 交易撮合 | `admin-trade-matches.html` | `/api/business/trade-matches` | `business.tradeMatches.manage` |
| 批次物流和质量追溯 | 物流溯源 | `admin-logistics-traces.html` | `/api/business/logistics-traces` | `business.logisticsTraces.manage` |
| 产品/批次/林班二维码 | 二维码管理 | `admin-product-qrcodes.html` | `/api/business/product-qrcodes` | `business.productQrcodes.manage` |
| 订单融资和库存质押 | 供应链金融 | `admin-supply-chain-finance.html` | `/api/business/supply-chain-finance` | `business.supplyChainFinance.manage` |
| 市场行情和价格指数 | 价格指数 | `admin-price-indexes.html` | `/api/business/price-indexes` | `business.priceIndexes.manage` |
| 林农/合作社/企业移动端服务 | 移动端服务 | `admin-mobile-service-channels.html` | `/api/business/mobile-service-channels` | `business.mobileServiceChannels.manage` |

## 关联规则

| 对象 | 管理边界 | 关联字段 |
| --- | --- | --- |
| 林班 | 只维护空间、资源、经营、风险等地理单元属性 | `blockCode` |
| 林权档案 | 只维护证照、合同、权利人、期限、流转、争议和附件 | `archiveCode`、`linkedBlockCodes` |
| 经营主体 | 维护竹农、合作社、竹企等主体档案 | `recordCode`、`linkedBlockCodes`、`linkedRightArchiveCodes` |
| 业务应用 | 维护生产、运营、经营、交易、溯源、金融等业务记录 | `recordCode`、`linkedBlockCodes`、`linkedRightArchiveCodes`、`properties` |
| 地图图层 | 维护专题图层发布、样式、层级和大屏展示状态 | `linkedBlockCodes`、`visibleOnDashboard` |

## 当前验收口径

1. 每个左侧菜单都是独立后台页面，不再把多个业务混在一个页面里。
2. 每个业务页面都是台账列表为主体，查看、编辑、删除在行级操作栏，新增是独立入口。
3. 写操作必须有对应权限码；查看列表和详情保留为可读能力。
4. 正式数据统一写入 MySQL 8 的规范化台账和关系表；JSON 仅用于本地开发兼容与一次性迁移来源。
5. 角色、用户、林班、林权、图层、业务台账均以列表为首屏主体；诊断摘要和操作队列位于主台账之后。
6. 大屏、移动端和后续应用只从后台数据聚合展示，不再把固定演示数字当真实业务数据。
