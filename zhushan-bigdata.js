const blocks = [];

const SMART_BAMBOO_DASHBOARD_VERSION = "20260716-interaction5";
const DASHBOARD_VERSION_CHECK_INTERVAL_MS = 60_000;

async function verifyDashboardBuildVersion() {
  if (!/^https?:$/.test(window.location.protocol)) return;

  try {
    const response = await fetch("/api/system/frontend-version", { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json();
    const serverVersion = String(payload.dashboardVersion || "").trim();
    if (!serverVersion || serverVersion <= SMART_BAMBOO_DASHBOARD_VERSION) return;

    const nextUrl = new URL(payload.dashboardUrl || "/zhushan-bigdata.html", window.location.origin);
    nextUrl.searchParams.set("v", serverVersion);
    window.location.replace(nextUrl.href);
  } catch (_error) {
    // Version checks must never interrupt map initialization or field operations.
  }
}

function startDashboardVersionMonitor() {
  verifyDashboardBuildVersion();
  window.setInterval(verifyDashboardBuildVersion, DASHBOARD_VERSION_CHECK_INTERVAL_MS);
}

const backendBusinessModules = {
  farmer: {
    endpoint: "/api/business/farmers/dashboard",
    title: "竹农信息卡",
    subtitle: "主体档案、承包林班与作业记录",
    columns: ["姓名", "所属村镇", "关联林班", "状态"],
    adminLinks: [{ label: "竹农后台", href: "admin-farmers.html" }],
  },
  cooperative: {
    endpoint: "/api/business/cooperatives/dashboard",
    title: "合作社信息卡",
    subtitle: "合作社经营、服务能力与订单协同",
    columns: ["合作社", "服务范围", "关联林班", "经营状态"],
    adminLinks: [{ label: "合作社后台", href: "admin-cooperatives.html" }],
  },
  enterprise: {
    endpoint: "/api/business/enterprises/dashboard",
    title: "竹企信息卡",
    subtitle: "加工企业、仓储流转与产销对接",
    columns: ["企业名称", "主营方向", "对接林班", "库存状态"],
    adminLinks: [{ label: "竹企后台", href: "admin-enterprises.html" }],
  },
  plant: {
    endpoint: "/api/business/plant-protection-events/dashboard",
    title: "植保信息卡",
    subtitle: "病虫害、处置工单与防治进度",
    columns: ["林班", "问题类型", "等级", "处置状态"],
    adminLinks: [{ label: "植保后台", href: "admin-plant-protection.html" }],
  },
  material: {
    endpoint: "/api/business/materials/dashboard",
    title: "农资信息卡",
    subtitle: "肥料、药剂、工具与领用记录",
    columns: ["物资名称", "库存", "适用环节", "状态"],
    adminLinks: [{ label: "农资后台", href: "admin-materials.html" }],
  },
  policy: {
    endpoint: "/api/business/policies/dashboard",
    title: "政策法规信息卡",
    subtitle: "补贴政策、采伐规范与生态保护要求",
    columns: ["政策名称", "适用对象", "申报状态", "截止时间"],
    adminLinks: [{ label: "政策后台", href: "admin-policies.html" }],
  },
  carbon: {
    endpoint: "/api/business/carbon-estimates/dashboard",
    title: "碳汇测算信息卡",
    subtitle: "碳储量、碳汇增量、项目边界与核证测算",
    columns: ["测算名称", "核算类型", "核算林班", "测算状态"],
    adminLinks: [{ label: "碳汇后台", href: "admin-carbon-estimates.html" }],
  },
  industry: {
    endpoint: "/api/industry-platform/dashboard",
    title: "产业平台信息卡",
    subtitle: "交易撮合、物流溯源、二维码、供应链金融、价格指数与移动端服务",
    columns: ["模块", "记录名称", "关联林班", "状态"],
    adminLinks: [
      { label: "交易撮合", href: "admin-trade-matches.html" },
      { label: "物流溯源", href: "admin-logistics-traces.html" },
      { label: "二维码", href: "admin-product-qrcodes.html" },
      { label: "供应链金融", href: "admin-supply-chain-finance.html" },
      { label: "价格指数", href: "admin-price-indexes.html" },
      { label: "移动服务", href: "admin-mobile-service-channels.html" },
    ],
  },
};

const leftToolData = {};

const importedOvobj = {
  id: "xiaoqiao-shangtun",
  title: "小桥上屯竹林",
  coord: [118.42, 26.9],
  sourceFile: "小桥上屯竹林.ovobj",
  fields: {
    "发包方": "建瓯市小桥镇上屯村村民委员会",
    "坐落": "建瓯市小桥镇上屯村",
    "小地名": "水北垅",
    "主要树种": "毛竹",
    "林木使用权人": "魏思华",
    "面积": "56",
    "地块代码": "350783006007JE00005",
    "不动产单元号": "350783006007JE00005L00000001",
    "小班": "5-3(3).8",
    "宗地四至东": "窠、3林班7大班1小班界",
    "宗地四至西": "3林班5大班7、6小班界",
    "使用权结束时间": "2033/6/30",
    "入库时间": "2023/9/15",
    "图形面积": "52164.964264",
    "图形周长": "1097.030533",
  },
  images: [
    ["对象文件", "奥维对象属性", "已从 .ovobj 文件中提取林木权属、坐落、面积、树种、小班和图形面积等属性。"],
    ["卫星定位", "小桥镇上屯村附近点位", "该点位按文件坐落信息落入建瓯市小桥镇上屯村附近，后续可替换为精确 KML/GeoJSON/SHP 边界。"],
    ["权属信息", "林木使用权信息", "包含林木使用权人、发包方、不动产单元号、地块代码等字段。"],
    ["林班信息", "毛竹林班档案", "包含小地名、水北垅、小班编号、四至信息、面积和入库时间。"],
  ],
};

const scene = document.querySelector("#mapScene");
const forestBlocks = document.querySelector("#forestBlocks");
const infoCard = document.querySelector("#infoCard");
const closeCard = document.querySelector("#closeCard");
const infoGrid = document.querySelector("#infoGrid");
const cardTitle = document.querySelector("#cardTitle");
const cardSubtitle = document.querySelector("#cardSubtitle");
const imageTabs = document.querySelector("#imageTabs");
const imagePanel = document.querySelector("#imagePanel");
const zoomValue = document.querySelector("#zoomValue");
const businessCard = document.querySelector("#businessCard");
const businessTitle = document.querySelector("#businessTitle");
const businessSubtitle = document.querySelector("#businessSubtitle");
const businessAdminLinks = document.querySelector("#businessAdminLinks");
const businessMetrics = document.querySelector("#businessMetrics");
const businessHead = document.querySelector("#businessHead");
const businessRows = document.querySelector("#businessRows");
const layerCard = document.querySelector("#layerCard");
const forestFilterSummary = document.querySelector("#forestFilterSummary");
const forestFilterToggle = document.querySelector("#forestFilterToggle");
const forestFilterBadge = document.querySelector("#forestFilterBadge");
const forestFilterPanel = document.querySelector("#forestFilterPanel");
const dashboardPublishedLayerControls = document.querySelector("#dashboardPublishedLayerControls");
const dashboardWorkflowStatus = document.querySelector("#dashboardWorkflowStatus");

let zoom = 1;
let gisMap = null;
let activeBusinessData = null;
let activeRenderedRows = [];
let activeRowLocators = [];
const gisLayers = {};
const baseSources = {};
const RS_SDK = window.RemoteSensingSDK;
const ZHUSHAN_SDK_CONFIG = window.SATELLITE_CONFIG || {};
const normalizeZhushanApiBase = (value) => String(value || "").trim().replace(/\/+$/, "");
const resolveZhushanApiBase = () => {
  const configured = normalizeZhushanApiBase(ZHUSHAN_SDK_CONFIG.remoteApiBase);
  if (configured) return configured;
  if (/^https?:$/.test(window.location.protocol)) return window.location.origin;
  if (window.location.protocol === "file:") return "http://127.0.0.1:8010";
  return "http://127.0.0.1:8010";
};
const ZHUSHAN_REMOTE_API_BASE =
  normalizeZhushanApiBase(ZHUSHAN_SDK_CONFIG.remoteApiBase) || localStorage.getItem("remoteSensingApiBase") || resolveZhushanApiBase();
const ZHUSHAN_TIANDITU_PROXY_ENABLED = ZHUSHAN_SDK_CONFIG.tiandituProxy !== false;
const ZHUSHAN_TIANDITU_PROXY_BASE = ZHUSHAN_TIANDITU_PROXY_ENABLED
  ? normalizeZhushanApiBase(ZHUSHAN_SDK_CONFIG.tiandituProxyBaseUrl) || ZHUSHAN_REMOTE_API_BASE
  : "";
const LIVE_FOREST_BLOCK_MAX_FEATURES = Number(ZHUSHAN_SDK_CONFIG.liveForestBlockMaxFeatures || 1200);
const FOREST_VECTOR_TILE_MAX_FEATURES = Number(ZHUSHAN_SDK_CONFIG.forestVectorTileMaxFeatures || 5000);
const FOREST_VECTOR_TILE_RETRY_MS = 60_000;
const MAP_ZOOM_PER_SCALE_UNIT = 7.5;
const ZHUSHAN_API_TOKEN =
  ZHUSHAN_SDK_CONFIG.humanLoginEnabled === false
    ? String(ZHUSHAN_SDK_CONFIG.apiToken || "").trim()
    : "";

function zhushanApiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (ZHUSHAN_API_TOKEN) headers.set("Authorization", `Bearer ${ZHUSHAN_API_TOKEN}`);
  return fetch(url, { credentials: "include", ...options, headers });
}
const SMART_BAMBOO_MAP_STATE_KEY = "smartBambooBigDataMapStateV1";
const restoredDashboardMapState = readDashboardMapState();
const remoteSensing = {
  client: null,
  remote: null,
  layers: null,
  scenes: [],
  visible: true,
  basemaps: {},
  basemapErrorShown: false,
  basemapFailed: false,
  basemapLoaded: false,
  basemapTileErrors: 0,
  currentBasemapMode: "img",
};
const liveForestState = {
  inFlight: null,
  pendingFilters: null,
  debounceTimer: null,
  restoredFilters: { ...(restoredDashboardMapState.filters || {}) },
};
const forestVectorTileState = {
  filterKey: "",
  tileErrors: 0,
  failedAt: 0,
  active: false,
};
const forestFilterLabels = {
  countyCode: "区县",
  townCode: "乡镇",
  villageCode: "村",
  baseType: "基地类型",
  operationType: "经营类型",
  qualityGrade: "质量等级",
  healthStatus: "健康状态",
  riskLevel: "风险等级",
};
let activeInfoCardBlockId = "";

function readDashboardMapState() {
  try {
    const payload = JSON.parse(localStorage.getItem(SMART_BAMBOO_MAP_STATE_KEY) || "{}");
    return payload && typeof payload === "object" ? payload : {};
  } catch (_error) {
    return {};
  }
}

function dashboardLayerVisibility() {
  return Array.from(document.querySelectorAll("[data-layer]")).reduce((result, input) => {
    if (input.dataset.layer) result[input.dataset.layer] = Boolean(input.checked);
    return result;
  }, {});
}

function restoreDashboardLayerState() {
  const layerVisibility = restoredDashboardMapState.layerVisibility || {};
  document.querySelectorAll("[data-layer]").forEach((input) => {
    const stored = layerVisibility[input.dataset.layer];
    if (typeof stored === "boolean") input.checked = stored;
  });
}

function dashboardViewState() {
  if (!window.ol || !gisMap) return restoredDashboardMapState.view || {};
  const view = gisMap.getView();
  const center = view.getCenter();
  return {
    center: center ? ol.proj.toLonLat(center).map((value) => Number(value.toFixed(6))) : undefined,
    zoom: Number((view.getZoom() || 10).toFixed(2)),
  };
}

function persistDashboardMapState() {
  try {
    localStorage.setItem(SMART_BAMBOO_MAP_STATE_KEY, JSON.stringify({
      filters: collectForestFilters(),
      layerVisibility: dashboardLayerVisibility(),
      view: dashboardViewState(),
    }));
  } catch (_error) {
    // Storage can be unavailable in hardened browser profiles; map interactions still work.
  }
}

function dashboardInitialViewOptions() {
  const storedView = restoredDashboardMapState.view || {};
  const center = Array.isArray(storedView.center) && storedView.center.length === 2
    ? storedView.center.map(Number)
    : [118.2, 26.6];
  const storedZoom = Number(storedView.zoom);
  return {
    center: ol.proj.fromLonLat(center.every(Number.isFinite) ? center : [118.2, 26.6]),
    zoom: Number.isFinite(storedZoom) ? Math.min(16, Math.max(8, storedZoom)) : 10,
    minZoom: 8,
    maxZoom: 16,
  };
}

function hasStoredDashboardView() {
  const storedView = restoredDashboardMapState.view || {};
  return (
    Array.isArray(storedView.center) &&
    storedView.center.length === 2 &&
    storedView.center.map(Number).every(Number.isFinite) &&
    Number.isFinite(Number(storedView.zoom))
  );
}

function syncLayerControl(input) {
  if (!input?.dataset?.layer) return;
  const visible = input.checked;
  document.querySelector(`[data-map-layer="${input.dataset.layer}"]`)?.classList.toggle("hidden", !visible);
  gisLayers[input.dataset.layer]?.setVisible(visible);
  if (input.dataset.layer === "bamboo") {
    gisLayers.bambooAggregates?.setVisible(visible && !forestVectorTileState.active);
    gisLayers.bambooTiles?.setVisible(visible && forestVectorTileState.active);
  }
  persistDashboardMapState();
}

function syncAllLayerControls() {
  document.querySelectorAll("[data-layer]").forEach(syncLayerControl);
}

function dashboardPublishedLayerSubtitle(layer = {}) {
  return [
    layer.layerType || "地图图层",
    layer.sourceType || layer.dataSource || "后台配置",
    layer.publishRiskStatus ? `风险 ${layer.publishRiskStatus}` : "",
    layer.visibleOnDashboard === false ? "未发布到大屏" : "发布到大屏",
  ]
    .filter(Boolean)
    .join(" · ");
}

function dashboardPublishedLayerSummary(payload = {}, layers = []) {
  const summary = payload.summary || {};
  const sourceTypes = Object.keys(summary.bySourceType || {}).length;
  const riskTypes = Object.keys(summary.byPublishRiskStatus || {}).length;
  return `
    <div class="dashboard-published-summary" aria-label="后台发布图层摘要">
      <span>发布 ${escapeTableCell(summary.total ?? layers.length)} 层</span>
      <span>关联林班 ${escapeTableCell(summary.linkedBlockTotal ?? 0)} 个</span>
      <span>来源 ${escapeTableCell(sourceTypes)} 类</span>
      <span>风险 ${escapeTableCell(riskTypes)} 类</span>
    </div>
  `;
}

function renderDashboardPublishedLayerControls(payload = {}) {
  if (!dashboardPublishedLayerControls) return;
  const layers = (Array.isArray(payload.items) ? payload.items : []).filter((layer) => !layer.deletedAt && layer.visibleOnDashboard !== false);
  if (!layers.length) {
    dashboardPublishedLayerControls.innerHTML = '<p class="dashboard-published-state">暂无后台发布图层</p>';
    return;
  }
  dashboardPublishedLayerControls.innerHTML = dashboardPublishedLayerSummary(payload, layers) + layers
    .slice(0, 20)
    .map(
      (layer) => `
        <label title="当前展示后台发布目录，渲染器按图层类型逐步接入">
          <input type="checkbox" checked disabled aria-label="${escapeTableCell(layer.name || layer.recordCode || "后台图层")}" />
          <strong>${escapeTableCell(layer.name || layer.recordCode || "后台图层")}</strong>
          <small>${escapeTableCell(dashboardPublishedLayerSubtitle(layer))}</small>
        </label>
      `,
    )
    .join("");
}

function publishedImagerySceneFromLayer(layer = {}) {
  const properties = layer.properties && typeof layer.properties === "object" ? layer.properties : {};
  const tileUrl = layer.tileUrl || properties.tileUrl || layer.url || properties.url || "";
  if (!tileUrl) return null;
  const sourceType = String(layer.sourceType || layer.dataSource || properties.source || "").toLowerCase();
  const layerType = String(layer.layerType || properties.layerType || "").toLowerCase();
  if (sourceType && !["imagery", "scene", "remote-sensing", "remote_sensing"].includes(sourceType) && layerType !== "raster") {
    return null;
  }
  return {
    id: `dashboard-layer-${layer.id || layer.recordCode || properties.sourceSceneId || tileUrl}`,
    name: layer.name || layer.recordCode || properties.sceneName || "后台发布影像",
    tileUrl,
    bounds: layer.bounds || properties.bounds || [],
    opacity: Number(layer.opacity ?? layer.style?.opacity ?? properties.opacity ?? 0.82),
    visible: layer.visibleOnDashboard !== false,
    transferStatus: "cog-ready",
    fileName: layer.fileName || properties.fileName || "published-layer",
    sourceLayerCode: layer.recordCode || "",
  };
}

function syncDashboardPublishedImageryLayers(layers = []) {
  remoteSensing.scenes = layers.map(publishedImagerySceneFromLayer).filter(Boolean);
  renderRemoteSensingScenes();
}

async function loadDashboardPublishedLayers() {
  if (!dashboardPublishedLayerControls) return;
  dashboardPublishedLayerControls.innerHTML = '<p class="dashboard-published-state">正在加载后台发布图层</p>';
  try {
    const response = await zhushanApiFetch(`${ZHUSHAN_REMOTE_API_BASE}/api/map-layers/dashboard`);
    if (!response.ok) throw new Error(`map layers ${response.status}`);
    const payload = await response.json();
    renderDashboardPublishedLayerControls(payload);
    syncDashboardPublishedImageryLayers(payload.items || []);
  } catch (error) {
    dashboardPublishedLayerControls.innerHTML = '<p class="dashboard-published-state">后台图层目录暂不可用</p>';
    console.warn("dashboard published layers unavailable", error);
  }
}

async function fetchDashboardWorkflowJson(endpoint) {
  const response = await zhushanApiFetch(`${ZHUSHAN_REMOTE_API_BASE}${endpoint}`);
  if (!response.ok) throw new Error(`${endpoint} ${response.status}`);
  return response.json();
}

function dashboardWorkflowSummaryCard(payload = {}, key, fallback = {}) {
  return (Array.isArray(payload.cards) ? payload.cards : []).find((card) => card.key === key) || fallback;
}

function dashboardWorkflowCard({ label, value, tone, href, meta } = {}) {
  const safeHref = href || "#";
  return `
    <a class="dashboard-workflow-card ${tone ? `tone-${escapeTableCell(tone)}` : ""}" href="${escapeTableCell(safeHref)}">
      <strong>${escapeTableCell(value ?? 0)}</strong>
      <span>${escapeTableCell(label || "待办")}</span>
      <small>${escapeTableCell(meta || "后台实时汇总")}</small>
    </a>
  `;
}

function dashboardWorkflowPackageHref(item = {}) {
  if (item.adminHref) return item.adminHref;
  const status = item.packageStatus || item.deliveryStatus || "awaiting_delivery";
  return `admin-imports.html?deliveryPackageStatus=${encodeURIComponent(status)}&batchId=${encodeURIComponent(item.batchId || item.id || "")}`;
}

function dashboardWorkflowPackageRows(payload = {}) {
  const items = Array.isArray(payload.items) ? payload.items.filter((item) => !item.deletedAt).slice(0, 3) : [];
  if (!items.length) return '<p class="dashboard-workflow-state">暂无待交付成果包</p>';
  return `
    <div class="dashboard-workflow-packages" aria-label="最近交付包">
      ${items
        .map(
          (item) => `
            <a class="dashboard-workflow-package" href="${escapeTableCell(dashboardWorkflowPackageHref(item))}">
              <strong>${escapeTableCell(item.fileName || item.batchId || item.id || "成果交付包")}</strong>
              <span>${escapeTableCell(item.status || item.deliveryStatus || item.acceptanceStatus || "待交付")}</span>
            </a>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderDashboardWorkflowStatus(payload = {}) {
  if (!dashboardWorkflowStatus) return;
  const importPending = dashboardWorkflowSummaryCard(payload.imports, "pendingReviewBatches", {
    label: "待审核批次",
    value: payload.imports?.pendingReviewBatches ?? 0,
    tone: "warning",
    href: "admin-imports.html?workflowQueue=pendingReview",
  });
  const imageryUnpublished = dashboardWorkflowSummaryCard(payload.imagery, "unpublishedScenes", {
    label: "未发布影像",
    value: payload.imagery?.unpublishedScenes ?? 0,
    tone: "warning",
    href: "admin-imagery.html?published=false",
  });
  const deliveryReady = dashboardWorkflowSummaryCard(payload.imports, "readyDeliveryPackages", {
    label: "待交付成果",
    value: payload.deliveries?.total ?? 0,
    tone: "ready",
    href: "admin-imports.html?deliveryPackageStatus=awaiting_delivery",
  });
  const publishedLayerTotal = payload.layers?.summary?.total ?? (Array.isArray(payload.layers?.items) ? payload.layers.items.length : 0);
  const hasWorkflowData = [payload.imports, payload.imagery, payload.deliveries, payload.layers].some(Boolean);
  if (!hasWorkflowData) {
    dashboardWorkflowStatus.innerHTML = '<p class="dashboard-workflow-state">暂无后台交付闭环数据</p>';
    return;
  }
  dashboardWorkflowStatus.innerHTML = `
    <div class="dashboard-workflow-grid">
      ${dashboardWorkflowCard({ ...importPending, meta: "成果入库审核" })}
      ${dashboardWorkflowCard({ ...imageryUnpublished, meta: "影像发布闭环" })}
      ${dashboardWorkflowCard({ ...deliveryReady, meta: "交付包验收" })}
      ${dashboardWorkflowCard({
        label: "发布图层",
        value: publishedLayerTotal,
        tone: "ready",
        href: "admin-map-layers.html?visibleOnDashboard=true",
        meta: "地图图层发布",
      })}
    </div>
    ${dashboardWorkflowPackageRows(payload.deliveries)}
    ${payload.errors?.length ? `<p class="dashboard-workflow-state">部分后台接口暂不可用：${escapeTableCell(payload.errors.join(" / "))}</p>` : ""}
  `;
}

async function loadDashboardWorkflowStatus() {
  if (!dashboardWorkflowStatus) return;
  dashboardWorkflowStatus.innerHTML = '<p class="dashboard-workflow-state">正在加载后台交付闭环</p>';
  try {
    const payload = await fetchDashboardWorkflowJson("/api/dashboard/workflow-status");
    renderDashboardWorkflowStatus(payload);
  } catch (error) {
    dashboardWorkflowStatus.innerHTML = '<p class="dashboard-workflow-state">后台交付闭环暂不可用</p>';
    console.warn("dashboard workflow status unavailable", error);
  }
}

function normalizeSdkBasemapMode(mode) {
  return (
    {
      imagery: "img",
      image: "img",
      standard: "vec",
      vector: "vec",
      terrain: "ter",
      terrain3d: "ter",
    }[mode] || mode || "img"
  );
}

function localMapExtent() {
  return ol.proj.transformExtent([117.55, 26.15, 118.88, 27.18], "EPSG:4326", "EPSG:3857");
}

function setLayerOrder() {
  [
    [gisLayers.localBase, 0],
    [gisLayers.satellite, 0],
    [gisLayers.hillshade, 1],
    [gisLayers.offlineBase, 2],
    [gisLayers.history, 6],
    [gisLayers.soil, 20],
    [gisLayers.growth, 20],
    [gisLayers.ownership, 20],
    [gisLayers.quality, 22],
    [gisLayers.yield, 22],
    [gisLayers.pest, 23],
    [gisLayers.farmer, 24],
    [gisLayers.cooperative, 24],
    [gisLayers.uav, 25],
    [gisLayers.huangkeng, 28],
    [gisLayers.kangVillage, 28],
    [gisLayers.ovobj, 30],
    [gisLayers.bambooAggregates, 31],
    [gisLayers.bambooTiles, 32],
    [gisLayers.bamboo, 33],
  ].forEach(([layer, zIndex]) => layer?.setZIndex(zIndex));
}

function sdkBasemapGroups() {
  return Object.values(remoteSensing.basemaps).flat();
}

function hasSdkBasemap() {
  return sdkBasemapGroups().length > 0 && !remoteSensing.basemapFailed && remoteSensing.basemapLoaded;
}

function sdkBasemapPending() {
  return sdkBasemapGroups().length > 0 && !remoteSensing.basemapFailed && !remoteSensing.basemapLoaded;
}

function applySdkBasemapMode(mode) {
  const sdkMode = normalizeSdkBasemapMode(mode);
  Object.entries(remoteSensing.basemaps).forEach(([key, layers]) => {
    layers.forEach((layer) => layer.setVisible(!remoteSensing.basemapFailed && key === sdkMode));
  });
}

function markBasemapCanvasLoaded() {
  document.body.classList.add("basemap-loaded");
}

function initSdkBasemap() {
  if (!RS_SDK || !gisMap || !remoteSensing.layers) return;
  const tk = String(ZHUSHAN_SDK_CONFIG.tiandituTk || "").trim();
  if (!tk && !ZHUSHAN_TIANDITU_PROXY_BASE) return;
  remoteSensing.basemapErrorShown = false;
  remoteSensing.basemapFailed = false;
  remoteSensing.basemapLoaded = false;
  remoteSensing.basemapTileErrors = 0;
  const markBasemapLoaded = () => {
    const shouldRefreshMode = !remoteSensing.basemapLoaded || remoteSensing.basemapFailed;
    remoteSensing.basemapLoaded = true;
    remoteSensing.basemapFailed = false;
    remoteSensing.basemapTileErrors = 0;
    remoteSensing.basemapErrorShown = false;
    document.body.classList.remove("basemap-failed");
    markBasemapCanvasLoaded();
    if (shouldRefreshMode) setBasemapMode(remoteSensing.currentBasemapMode);
  };
  const onTileLoadError = () => {
    remoteSensing.basemapTileErrors += 1;
    if (remoteSensing.basemapTileErrors < 4) return;
    if (remoteSensing.basemapErrorShown && remoteSensing.basemapFailed) return;
    remoteSensing.basemapErrorShown = true;
    remoteSensing.basemapFailed = true;
    remoteSensing.basemapLoaded = false;
    document.body.classList.add("basemap-failed");
    document.body.classList.remove("basemap-loaded");
    setBasemapMode(remoteSensing.currentBasemapMode);
    console.warn("天地图底图加载失败，请检查 tk、域名白名单或网络访问。");
  };
  const tiandituOptions = {
    tk,
    proxyBaseUrl: ZHUSHAN_TIANDITU_PROXY_BASE,
    preload: 1,
    onTileLoadError,
    onTileLoadEnd: markBasemapLoaded,
  };
  remoteSensing.basemaps = {
    img: RS_SDK.SourceAdapters.tianditu({ ...tiandituOptions, type: "img" }),
    vec: RS_SDK.SourceAdapters.tianditu({ ...tiandituOptions, type: "vec" }),
    ter: RS_SDK.SourceAdapters.tianditu({ ...tiandituOptions, type: "ter" }),
  };
  Object.entries(remoteSensing.basemaps).forEach(([key, layers]) => {
    remoteSensing.layers.addGroup(`zhushan-basemap-${key}`, layers, {
      ids: ["base", "label"],
      zIndex: 0,
    });
    layers.forEach((layer) => {
      layer.setVisible(false);
    });
  });
  setBasemapMode(remoteSensing.currentBasemapMode);
}

function renderRemoteSensingScenes() {
  if (!remoteSensing.layers) return;
  const renderableScenes = remoteSensing.scenes.filter(isRenderableRemoteScene);
  remoteSensing.layers.syncScenes(
    remoteSensing.visible
      ? renderableScenes.map((scene) => ({
          ...scene,
          opacity: Number.isFinite(Number(scene.opacity)) ? Number(scene.opacity) : 0.82,
          zIndex: 5,
        }))
      : [],
    { group: "zhushan-remote", zIndex: 5 },
  );
}

function isRenderableRemoteScene(scene) {
  if (!scene) return false;
  if (scene.imageUrl || scene.blob) return scene.visible !== false;
  if (!scene.tileUrl) return false;
  return scene.visible !== false && (scene.transferStatus === "cog-ready" || Boolean(scene.fileName || scene.createdAt || scene.updatedAt));
}

function initRemoteSensingSdk() {
  if (!RS_SDK || !gisMap) {
    console.warn("RemoteSensingSDK 未加载，智慧竹山地图将使用原有图层。");
    return;
  }
  remoteSensing.client = new RS_SDK.RemoteSensingClient({
    apiBase: ZHUSHAN_REMOTE_API_BASE,
    token: ZHUSHAN_API_TOKEN,
    map: gisMap,
    layerOptions: { defaultGroup: "zhushan-remote", defaultZIndex: 5 },
  });
  remoteSensing.remote = remoteSensing.client.remote;
  remoteSensing.layers = remoteSensing.client.layers;
  initSdkBasemap();
  gisLayers.remoteSensing = {
    setVisible(visible) {
      remoteSensing.visible = Boolean(visible);
      renderRemoteSensingScenes();
    },
  };
  renderRemoteSensingScenes();
}

function renderBlocks() {
  forestBlocks.innerHTML = "";
}

function blockColor(block) {
  return {
    good: "#51ff66",
    medium: "#fff05a",
    warning: "#ff9d30",
    danger: "#ff4949",
}[block.className] || "#51ff66";
}

function blockStyle(block) {
  const color = blockColor(block);
  return [
    new ol.style.Style({
      stroke: new ol.style.Stroke({ color: "rgba(0, 0, 0, 0.72)", width: 9 }),
    }),
    new ol.style.Style({
      stroke: new ol.style.Stroke({ color: "rgba(239, 255, 255, 0.68)", width: 5 }),
    }),
    new ol.style.Style({
      stroke: new ol.style.Stroke({ color, width: 3 }),
      fill: new ol.style.Fill({ color: "rgba(4, 35, 20, 0.24)" }),
      text: new ol.style.Text({
        text: `${block.code}\n${block.name}`,
        fill: new ol.style.Fill({ color: "#efffff" }),
        stroke: new ol.style.Stroke({ color: "rgba(0, 0, 0, 0.82)", width: 4 }),
        font: "bold 13px Microsoft YaHei",
        offsetY: -2,
      }),
    }),
  ];
}

function liveBlockClassName(props) {
  if (props.riskLevel === "high") return "danger";
  if (props.riskLevel === "medium") return "warning";
  if (props.qualityGrade === "C") return "warning";
  if (props.qualityGrade === "B") return "medium";
  return "good";
}

function formatAreaMu(areaMu) {
  if (areaMu === null || areaMu === undefined || areaMu === "") return "面积未填";
  const numeric = Number(areaMu);
  if (Number.isNaN(numeric)) return String(areaMu);
  return `${numeric.toFixed(numeric % 1 === 0 ? 0 : 1)} 亩`;
}

function forestBlockFromFeature(feature) {
  const props = feature.getProperties();
  const location = [props.countyName, props.townName, props.villageName].filter(Boolean).join("");
  const riskText =
    {
      high: "高风险",
      medium: "中风险",
      low: "低风险",
    }[props.riskLevel] || props.riskLevel || "待评估";
  const images = [
    ["林班档案", "实时林班档案", `${props.blockCode || props.name || "林班"} 已接入森林小班接口。`],
    ["经营属性", "经营与质量信息", `经营类型：${props.baseType || "未填"}；质量等级：${props.qualityGrade || "未填"}；健康状态：${props.healthStatus || "未填"}。`],
    ["空间定位", "区划与位置范围", `区划位置：${location || "未填"}；风险等级：${riskText}。`],
  ];
  return {
    id: props.id || feature.getId?.() || props.blockCode || props.name || "live-block",
    code: props.blockCode || props.code || "林班",
    name: props.name || props.blockCode || "林班",
    area: formatAreaMu(props.areaMu),
    variety: props.forestType || props.operationType || "毛竹",
    level: props.qualityGrade || "未评级",
    owner: location || props.baseType || "区划未填",
    altitude: props.bambooAge || props.countyName || "待补充",
    slope: props.slopeDegree ? `${props.slopeDegree}°` : "待补充",
    health: props.healthStatus || props.managementStatus || riskText,
    images,
    className: liveBlockClassName(props),
    isLive: true,
  };
}

function renderImageTabs(tabs, datasetKey) {
  imageTabs.innerHTML = tabs
    .map(([name], index) => `<button class="${index === 0 ? "active" : ""}" data-${datasetKey}="${index}">${name}</button>`)
    .join("");

  function renderTab(index) {
    const [name, title, desc] = tabs[index];
    imagePanel.innerHTML = `
      <div class="preview">${name}</div>
      <div>
        <strong>${title}</strong>
        <p>${desc}</p>
      </div>
    `;
  }

  imageTabs.querySelectorAll(`[data-${datasetKey}]`).forEach((button) => {
    button.addEventListener("click", () => {
      imageTabs.querySelectorAll("button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      renderTab(Number(button.dataset[datasetKey]));
    });
  });

  renderTab(0);
}

function linkedSceneSummaryTab(items) {
  if (!items.length) {
    return ["关联影像", "暂无关联影像", "当前林班还没有关联到远程感知场景。"];
  }
  const lines = items.map((item) => {
    const parts = [item.sceneId || "未命名场景", item.relationType || "coverage"];
    if (item.capturedAt) parts.push(item.capturedAt);
    if (item.confidence !== null && item.confidence !== undefined) parts.push(`置信度 ${item.confidence}`);
    return parts.join(" · ");
  });
  return ["关联影像", `已关联 ${items.length} 个场景`, lines.join("；")];
}

async function fetchForestSceneLinks(blockId) {
    const response = await zhushanApiFetch(`${ZHUSHAN_REMOTE_API_BASE}/api/forest-blocks/${encodeURIComponent(blockId)}/scenes`);
  if (!response.ok) {
    throw new Error(`scene links ${response.status}`);
  }
  const payload = await response.json();
  return Array.isArray(payload.items) ? payload.items : [];
}

function liveBlockStyle(feature) {
  return blockStyle(forestBlockFromFeature(feature));
}

function setBambooSourceFeatures(features) {
  const source = gisLayers.bamboo?.getSource();
  if (!source) return;
  source.clear();
  source.addFeatures(features);
}

function clearLiveForestBlocks() {
  if (!window.ol || !gisLayers.bamboo) return;
  setBambooSourceFeatures([]);
}

function setBambooAggregateFeatures(features) {
  const source = gisLayers.bambooAggregates?.getSource();
  if (!source) return;
  source.clear();
  source.addFeatures(features);
}

function clearForestAggregateFeatures() {
  if (!window.ol || !gisLayers.bambooAggregates) return;
  setBambooAggregateFeatures([]);
}

function forestVectorTileSupported() {
  return Boolean(window.ol?.source?.VectorTile && window.ol?.format?.MVT && gisLayers.bambooTiles);
}

function forestVectorTileAvailable() {
  if (!forestVectorTileSupported()) return false;
  if (!forestVectorTileState.failedAt) return true;
  if (Date.now() - forestVectorTileState.failedAt < FOREST_VECTOR_TILE_RETRY_MS) return false;
  forestVectorTileState.failedAt = 0;
  forestVectorTileState.filterKey = "";
  return true;
}

function forestVectorTileUrl(filters = {}) {
  const params = new URLSearchParams({ maxFeatures: String(FOREST_VECTOR_TILE_MAX_FEATURES) });
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  if (ZHUSHAN_API_TOKEN) params.set("token", ZHUSHAN_API_TOKEN);
  return `${ZHUSHAN_REMOTE_API_BASE}/api/map/forest-blocks/tiles/{z}/{x}/{y}.pbf?${params.toString()}`;
}

function createForestVectorTileSource(filters = {}) {
  const source = new ol.source.VectorTile({
    format: new ol.format.MVT(),
    url: forestVectorTileUrl(filters),
    minZoom: 14,
    maxZoom: 22,
    transition: 0,
  });
  source.on("tileloadend", () => {
    forestVectorTileState.tileErrors = 0;
  });
  source.on("tileloaderror", () => {
    forestVectorTileState.tileErrors += 1;
    if (forestVectorTileState.tileErrors < 3) return;
    forestVectorTileState.failedAt = Date.now();
    forestVectorTileState.active = false;
    gisLayers.bambooTiles?.setVisible(false);
    scheduleLiveForestBlocksLoad(collectForestFilters());
  });
  return source;
}

function refreshForestVectorTileSource(filters = {}) {
  if (!forestVectorTileSupported()) return false;
  const filterKey = JSON.stringify(filters, Object.keys(filters).sort());
  if (forestVectorTileState.filterKey !== filterKey || !gisLayers.bambooTiles.getSource()) {
    forestVectorTileState.filterKey = filterKey;
    forestVectorTileState.tileErrors = 0;
    forestVectorTileState.failedAt = 0;
    gisLayers.bambooTiles.setSource(createForestVectorTileSource(filters));
  }
  forestVectorTileState.active = true;
  const enabled = document.querySelector('[data-layer="bamboo"]')?.checked !== false;
  gisLayers.bambooTiles.setVisible(enabled);
  return true;
}

function hideForestVectorTiles() {
  forestVectorTileState.active = false;
  gisLayers.bambooTiles?.setVisible(false);
}

function aggregateLevelForZoom(zoomLevel = 10) {
  if (zoomLevel <= 9) return "county";
  if (zoomLevel <= 11) return "town";
  if (zoomLevel <= 13) return "village";
  return "";
}

function forestAggregateStyle(feature) {
  const riskLevel = feature.get("riskLevel") || "unknown";
  const blockCount = Number(feature.get("blockCount") || 0);
  const radius = Math.min(24, 13 + Math.log2(Math.max(1, blockCount)) * 2.2);
  const fillColor = {
    high: "rgba(214, 69, 65, 0.92)",
    medium: "rgba(218, 151, 42, 0.92)",
    low: "rgba(32, 151, 105, 0.94)",
    unknown: "rgba(43, 137, 145, 0.92)",
  }[riskLevel] || "rgba(43, 137, 145, 0.92)";
  return new ol.style.Style({
    image: new ol.style.Circle({
      radius,
      fill: new ol.style.Fill({ color: fillColor }),
      stroke: new ol.style.Stroke({ color: "rgba(235, 255, 247, 0.96)", width: 2 }),
    }),
    text: new ol.style.Text({
      text: String(blockCount),
      fill: new ol.style.Fill({ color: "#ffffff" }),
      stroke: new ol.style.Stroke({ color: "rgba(0, 38, 30, 0.72)", width: 2 }),
      font: "600 12px Microsoft YaHei, sans-serif",
    }),
  });
}

async function loadForestAggregates(filters, bbox, level) {
  const params = new URLSearchParams({ level });
  Object.entries({ ...filters, bbox }).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const response = await zhushanApiFetch(`${ZHUSHAN_REMOTE_API_BASE}/api/map/forest-blocks/aggregates?${params.toString()}`);
  if (!response.ok) throw new Error(`forest aggregate api ${response.status}`);
  const payload = await response.json();
  const features = (Array.isArray(payload.items) ? payload.items : [])
    .filter((item) => Array.isArray(item.centroid) && item.centroid.length === 2)
    .map((item) => {
      const feature = new ol.Feature({
        geometry: new ol.geom.Point(ol.proj.fromLonLat(item.centroid.map(Number))),
      });
      feature.set("aggregateLevel", payload.level || level);
      feature.set("aggregateCode", item.code || "unknown");
      feature.set("aggregateName", item.name || item.code || "未命名区域");
      feature.set("blockCount", Number(item.blockCount || 0));
      feature.set("areaMu", Number(item.areaMu || 0));
      feature.set("riskLevel", item.riskLevel || "unknown");
      feature.set("layerType", "bambooAggregate");
      return feature;
    });
  clearLiveForestBlocks();
  hideForestVectorTiles();
  setBambooAggregateFeatures(features);
  if (forestFilterSummary) {
    const levelLabel = { county: "区县", town: "乡镇", village: "村" }[payload.level || level] || "区域";
    forestFilterSummary.textContent = `${levelLabel}级聚合 ${payload.totalGroups || 0} 个区域，共 ${payload.totalBlocks || 0} 个林班、${payload.totalAreaMu || 0} 亩；放大地图查看边界。`;
  }
  return true;
}

function focusForestAggregate(feature) {
  const level = feature.get("aggregateLevel");
  const code = String(feature.get("aggregateCode") || "");
  const filterKey = { county: "countyCode", town: "townCode", village: "villageCode" }[level];
  const targetZoom = { county: 10, town: 12, village: 14 }[level] || 14;
  const control = filterKey ? document.querySelector(`[data-forest-filter="${filterKey}"]`) : null;
  if (control && Array.from(control.options).some((option) => option.value === code)) {
    control.value = code;
    if (filterKey === "countyCode") {
      const townControl = document.querySelector('[data-forest-filter="townCode"]');
      const villageControl = document.querySelector('[data-forest-filter="villageCode"]');
      if (townControl) townControl.value = "";
      if (villageControl) villageControl.value = "";
    } else if (filterKey === "townCode") {
      const villageControl = document.querySelector('[data-forest-filter="villageCode"]');
      if (villageControl) villageControl.value = "";
    }
  }
  const center = feature.getGeometry()?.getCoordinates();
  if (center) gisMap.getView().animate({ center, zoom: targetZoom, duration: 260 });
  persistDashboardMapState();
  refreshForestLayerByFilters();
}

function currentForestBlockBbox() {
  if (!window.ol || !gisMap) return "";
  const size = gisMap.getSize();
  if (!size) return "";
  return ol.proj.transformExtent(gisMap.getView().calculateExtent(size), "EPSG:3857", "EPSG:4326").join(",");
}

function forestFilterControls() {
  return Array.from(document.querySelectorAll("[data-forest-filter]"));
}

function collectForestFilters() {
  return forestFilterControls().reduce((filters, control) => {
    const key = control.dataset.forestFilter;
    const value = control.value;
    if (key && value) filters[key] = value;
    return filters;
  }, {});
}

function activeForestFilterCount() {
  return Object.keys(collectForestFilters()).length;
}

function syncForestFilterToggleState() {
  const count = activeForestFilterCount();
  if (forestFilterBadge) {
    forestFilterBadge.textContent = String(count);
    forestFilterBadge.hidden = count === 0;
  }
  if (forestFilterToggle) {
    forestFilterToggle.setAttribute("aria-label", count ? `展开林班筛选，已选 ${count} 项` : "展开林班筛选");
  }
}

function setForestFilterPanelOpen(open, { focus = false } = {}) {
  if (!forestFilterPanel || !forestFilterToggle) return;
  forestFilterPanel.hidden = !open;
  forestFilterPanel.classList.toggle("is-open", open);
  forestFilterToggle.classList.toggle("is-active", open);
  layerCard?.classList.toggle("filter-open-hidden", open);
  forestFilterToggle.setAttribute("aria-expanded", String(open));
  forestFilterToggle.setAttribute("aria-label", `${open ? "收起" : "展开"}林班筛选${activeForestFilterCount() ? `，已选 ${activeForestFilterCount()} 项` : ""}`);
  if (open && focus) forestFilterPanel.querySelector("select")?.focus();
}

function renderForestFacets(payload = {}) {
  const facets = payload.facets || {};
  forestFilterControls().forEach((control) => {
    const key = control.dataset.forestFilter;
    const currentValue = control.value || liveForestState.restoredFilters[key] || "";
    const items = Array.isArray(facets[key]) ? facets[key] : [];
    const label = forestFilterLabels[key] || key;
    control.innerHTML = [
      `<option value="">全部${escapeTableCell(label)}</option>`,
      ...items.map((item) => {
        const text = `${item.label || item.value} (${item.count || 0})`;
        return `<option value="${escapeTableCell(item.value)}">${escapeTableCell(text)}</option>`;
      }),
    ].join("");
    if (items.some((item) => String(item.value) === String(currentValue))) {
      control.value = currentValue;
    }
  });
  const restoredFiltersApplied = Object.keys(liveForestState.restoredFilters).length > 0;
  liveForestState.restoredFilters = {};
  if (forestFilterSummary) {
    const total = payload.summary?.total ?? 0;
    forestFilterSummary.textContent = `后台匹配林班 ${total} 个，筛选结果实时刷新地图边界。`;
  }
  syncForestFilterToggleState();
  if (restoredFiltersApplied) {
    persistDashboardMapState();
    scheduleLiveForestBlocksLoad(collectForestFilters());
  }
}

async function loadForestFacets(filters = collectForestFilters()) {
  if (typeof fetch !== "function") return;
  try {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    const queryString = params.toString();
      const response = await zhushanApiFetch(`${ZHUSHAN_REMOTE_API_BASE}/api/map/forest-blocks/facets${queryString ? `?${queryString}` : ""}`);
    if (!response.ok) throw new Error(`forest facets ${response.status}`);
    renderForestFacets(await response.json());
  } catch (error) {
    if (forestFilterSummary) {
      forestFilterSummary.textContent = `后台筛选维度暂不可用：${error.message}`;
    }
  }
}

function refreshForestLayerByFilters() {
  const filters = collectForestFilters();
  syncForestFilterToggleState();
  persistDashboardMapState();
  loadForestFacets(filters);
  scheduleLiveForestBlocksLoad(filters);
}

function initializeForestFilters() {
  forestFilterToggle?.addEventListener("click", () => {
    setForestFilterPanelOpen(forestFilterPanel?.hidden ?? true, { focus: true });
  });
  forestFilterPanel?.addEventListener("click", (event) => event.stopPropagation());
  forestFilterControls().forEach((control) => {
    control.addEventListener("change", refreshForestLayerByFilters);
  });
  document.querySelector("#resetForestFilters")?.addEventListener("click", () => {
    liveForestState.restoredFilters = {};
    forestFilterControls().forEach((control) => {
      control.value = "";
    });
    refreshForestLayerByFilters();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !forestFilterPanel?.hidden) {
      setForestFilterPanelOpen(false);
      forestFilterToggle?.focus();
    }
  });
  syncForestFilterToggleState();
  loadForestFacets();
}

async function loadLiveForestBlocks(filters = {}) {
  if (!window.ol || !gisMap || !gisLayers.bamboo || typeof fetch !== "function") {
    return false;
  }
  if (liveForestState.inFlight) {
    liveForestState.pendingFilters = filters;
    return liveForestState.inFlight;
  }

  liveForestState.inFlight = (async () => {
    try {
      const bbox = currentForestBlockBbox();
      if (!bbox) {
        clearLiveForestBlocks();
        clearForestAggregateFeatures();
        return false;
      }
      const aggregateLevel = aggregateLevelForZoom(gisMap.getView().getZoom());
      if (aggregateLevel) {
        return await loadForestAggregates(filters, bbox, aggregateLevel);
      }
      clearForestAggregateFeatures();
      if (forestVectorTileAvailable() && refreshForestVectorTileSource(filters)) {
        clearLiveForestBlocks();
        if (forestFilterSummary) {
          forestFilterSummary.textContent = "当前高缩放级别按矢量瓦片加载林班边界；筛选条件已同步。";
        }
        return true;
      }
      hideForestVectorTiles();
      const params = new URLSearchParams();
      Object.entries({ ...filters, bbox }).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
      });
      params.set("maxFeatures", String(LIVE_FOREST_BLOCK_MAX_FEATURES));
      params.set("zoom", String(Math.round(gisMap.getView().getZoom())));
      const response = await zhushanApiFetch(`${ZHUSHAN_REMOTE_API_BASE}/api/map/forest-blocks.geojson?${params.toString()}`);
      if (!response.ok) throw new Error(`forest block api ${response.status}`);
      const geojson = await response.json();
      const features = new ol.format.GeoJSON().readFeatures(geojson, {
        dataProjection: "EPSG:4326",
        featureProjection: "EPSG:3857",
      });
      if (!features.length) {
        setBambooSourceFeatures([]);
        return true;
      }
      features.forEach((feature) => {
        feature.set("layerType", "bamboo");
        feature.setStyle(liveBlockStyle(feature));
      });
      setBambooSourceFeatures(features);
      if (forestFilterSummary && geojson.meta?.truncated) {
        forestFilterSummary.textContent = `当前视口匹配 ${geojson.meta.total} 个林班，已显示 ${geojson.meta.returned} 个。请缩小地图范围或增加筛选条件。`;
      }
      return true;
    } catch (error) {
      console.warn("实时林班接口不可用，地图不展示本地演示林班。", error);
      clearLiveForestBlocks();
      if (forestFilterSummary) {
        forestFilterSummary.textContent = `后台林班接口暂不可用：${error.message}。地图不展示本地演示地块。`;
      }
      return false;
    } finally {
      liveForestState.inFlight = null;
      if (liveForestState.pendingFilters) {
        const nextFilters = liveForestState.pendingFilters;
        liveForestState.pendingFilters = null;
        loadLiveForestBlocks(nextFilters);
      }
    }
  })();

  return liveForestState.inFlight;
}

function scheduleLiveForestBlocksLoad(filters = {}) {
  if (liveForestState.debounceTimer) window.clearTimeout(liveForestState.debounceTimer);
  liveForestState.debounceTimer = window.setTimeout(() => {
    liveForestState.debounceTimer = null;
    loadLiveForestBlocks(filters);
  }, 220);
}

function offlineBaseStyle(feature) {
  const kind = feature.get("kind");
  const itemClass = feature.get("class");
  if (kind === "forest") {
    return new ol.style.Style({
      fill: new ol.style.Fill({ color: "rgba(36, 126, 72, 0.2)" }),
      stroke: new ol.style.Stroke({ color: "rgba(76, 190, 118, 0.2)", width: 1 }),
    });
  }
  if (kind === "landuse") {
    return new ol.style.Style({
      fill: new ol.style.Fill({ color: "rgba(70, 122, 78, 0.12)" }),
      stroke: new ol.style.Stroke({ color: "rgba(110, 180, 120, 0.14)", width: 1 }),
    });
  }
  if (kind === "water") {
    return new ol.style.Style({
      fill: new ol.style.Fill({ color: "rgba(54, 154, 190, 0.28)" }),
      stroke: new ol.style.Stroke({ color: "rgba(118, 224, 255, 0.4)", width: 1.4 }),
    });
  }
  if (kind === "waterway") {
    return new ol.style.Style({
      stroke: new ol.style.Stroke({ color: "rgba(92, 216, 255, 0.48)", width: 1.8 }),
    });
  }
  if (kind === "railway") {
    return new ol.style.Style({
      stroke: new ol.style.Stroke({ color: "rgba(218, 224, 214, 0.34)", width: 1.2, lineDash: [8, 6] }),
    });
  }
  if (kind === "building") {
    return new ol.style.Style({
      fill: new ol.style.Fill({ color: "rgba(168, 204, 185, 0.12)" }),
      stroke: new ol.style.Stroke({ color: "rgba(200, 246, 230, 0.16)", width: 1 }),
    });
  }
  const width = itemClass === "primary" || itemClass === "trunk" ? 3.2 : itemClass === "secondary" ? 2.4 : 1.4;
  return new ol.style.Style({
    stroke: new ol.style.Stroke({ color: "rgba(212, 231, 202, 0.46)", width }),
  });
}

function initWebGIS() {
  if (!window.ol) {
    document.body.classList.add("webgis-fallback");
    return;
  }

  document.body.classList.add("webgis-ready");

  baseSources.standard = new ol.source.XYZ({
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attributions: "© OpenStreetMap contributors",
    crossOrigin: "anonymous",
    maxZoom: 19,
  });
  baseSources.imagery = new ol.source.XYZ({
    url: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attributions: "Tiles © Esri",
  });
  baseSources.hillshade = new ol.source.XYZ({
    url: "https://services.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}",
    attributions: "Terrain © Esri",
  });
  [baseSources.standard, baseSources.imagery, baseSources.hillshade].forEach((source) => {
    source.on("tileloadend", markBasemapCanvasLoaded);
  });

  gisLayers.offlineBase = new ol.layer.Vector({
    source: new ol.source.Vector({
      features: window.FUJIAN_BASEMAP_GEOJSON
        ? new ol.format.GeoJSON().readFeatures(window.FUJIAN_BASEMAP_GEOJSON, {
            dataProjection: "EPSG:4326",
            featureProjection: "EPSG:3857",
          })
        : [],
    }),
    style: offlineBaseStyle,
    opacity: 1,
  });

  gisLayers.localBase = new ol.layer.Tile({
    source: baseSources.standard,
    opacity: 1,
    visible: true,
  });
  gisLayers.satellite = new ol.layer.Tile({
    source: baseSources.imagery,
    className: "ol-satellite-layer",
    opacity: 0,
    visible: false,
  });
  gisLayers.hillshade = new ol.layer.Tile({
    source: baseSources.hillshade,
    opacity: 0,
  });

  gisLayers.bamboo = new ol.layer.Vector({
    source: new ol.source.Vector({ features: [] }),
    declutter: true,
  });
  gisLayers.bambooAggregates = new ol.layer.Vector({
    source: new ol.source.Vector({ features: [] }),
    style: forestAggregateStyle,
    declutter: true,
  });
  gisLayers.bambooTiles = new ol.layer.VectorTile({
    source: createForestVectorTileSource({}),
    style: liveBlockStyle,
    declutter: true,
    visible: false,
  });

  gisLayers.quality = createEmptyDataLayer();
  gisLayers.soil = createEmptyDataLayer();
  gisLayers.growth = createEmptyDataLayer();
  gisLayers.yield = createEmptyDataLayer();
  gisLayers.pest = createEmptyDataLayer();
  gisLayers.ownership = createEmptyDataLayer();
  gisLayers.farmer = createEmptyDataLayer();
  gisLayers.cooperative = createEmptyDataLayer();
  gisLayers.uav = createEmptyDataLayer();
  gisLayers.huangkeng = createHuangKengLayer();
  gisLayers.kangVillage = createKangVillageLayer();
  gisLayers.ovobj = createImportedObjectLayer();
  gisLayers.history = createEmptyDataLayer(false);

  gisMap = new ol.Map({
    target: "webgisMap",
    controls: [],
    layers: [
      gisLayers.offlineBase,
      gisLayers.localBase,
      gisLayers.satellite,
      gisLayers.hillshade,
      gisLayers.history,
      gisLayers.soil,
      gisLayers.growth,
      gisLayers.ownership,
      gisLayers.quality,
      gisLayers.yield,
      gisLayers.pest,
      gisLayers.farmer,
      gisLayers.cooperative,
      gisLayers.uav,
      gisLayers.huangkeng,
      gisLayers.kangVillage,
      gisLayers.ovobj,
      gisLayers.bambooAggregates,
      gisLayers.bambooTiles,
      gisLayers.bamboo,
    ],
    view: new ol.View(dashboardInitialViewOptions()),
  });

  setLayerOrder();
  restoreDashboardLayerState();
  syncAllLayerControls();
  initRemoteSensingSdk();
  scheduleLiveForestBlocksLoad(collectForestFilters());

  gisMap.on("singleclick", (event) => {
    const feature = gisMap.forEachFeatureAtPixel(event.pixel, (item) => item);
    if (!feature) {
      setForestFilterPanelOpen(false);
      return;
    }
    if (feature.get("aggregateLevel")) {
      focusForestAggregate(feature);
      return;
    }
    if (feature?.get("sourceLayer") === "huangkeng") {
      openHuangKengCard(feature);
      return;
    }
    if (feature?.get("sourceLayer") === "kangVillage") {
      openKangVillageCard(feature);
      return;
    }
    if (feature.get("importedId")) {
      openImportedObjectCard();
      return;
    }
    const block =
      feature?.get("blockCode")
        ? forestBlockFromFeature(feature)
        : blocks.find((item) => item.id === feature?.get("blockId"));
    if (!block) return;
    openBlockCard(block);
  });

  gisMap.on("pointermove", (event) => {
    const hit = gisMap.hasFeatureAtPixel(event.pixel);
    gisMap.getTargetElement().style.cursor = hit ? "pointer" : "";
  });
  gisMap.on("moveend", () => {
    syncZoomControlFromMap();
    persistDashboardMapState();
    scheduleLiveForestBlocksLoad(collectForestFilters());
  });

  const fitExtent = ol.extent.createEmpty();
  [gisLayers.huangkeng, gisLayers.kangVillage].forEach((layer) => {
    const extent = layer?.getSource().getExtent();
    if (extent && !ol.extent.isEmpty(extent)) ol.extent.extend(fitExtent, extent);
  });
  if (!ol.extent.isEmpty(fitExtent) && !hasStoredDashboardView()) {
    gisMap.getView().fit(fitExtent, { padding: [140, 360, 150, 260], maxZoom: 12 });
  }
}

function createImportedObjectLayer() {
  const feature = new ol.Feature({
    geometry: new ol.geom.Point(ol.proj.fromLonLat(importedOvobj.coord)),
    importedId: importedOvobj.id,
    layerType: "ovobj",
  });
  feature.setStyle(
    new ol.style.Style({
      image: new ol.style.Circle({
        radius: 12,
        fill: new ol.style.Fill({ color: "rgba(255, 238, 89, 0.95)" }),
        stroke: new ol.style.Stroke({ color: "#ffffff", width: 3 }),
      }),
      text: new ol.style.Text({
        text: importedOvobj.title,
        offsetY: -24,
        fill: new ol.style.Fill({ color: "#fff" }),
        stroke: new ol.style.Stroke({ color: "rgba(0,0,0,0.82)", width: 4 }),
        font: "bold 13px Microsoft YaHei",
      }),
    }),
  );
  return new ol.layer.Vector({ source: new ol.source.Vector({ features: [feature] }), declutter: true });
}

function createHuangKengLayer() {
  if (!window.HUANGKENG_BAMBOO_GEOJSON) {
    return new ol.layer.Vector({ source: new ol.source.Vector() });
  }

  const normalized = JSON.parse(JSON.stringify(window.HUANGKENG_BAMBOO_GEOJSON));
  normalized.features.forEach((feature, index) => {
    feature.properties = feature.properties || {};
    feature.properties.sourceLayer = "huangkeng";
    feature.properties.kmzIndex = index + 1;
    if (feature.geometry?.type === "Polygon" && typeof feature.geometry.coordinates?.[0]?.[0] === "number") {
      feature.geometry.coordinates = [feature.geometry.coordinates];
    }
  });

  const features = new ol.format.GeoJSON().readFeatures(normalized, {
    dataProjection: "EPSG:4326",
    featureProjection: "EPSG:3857",
  });

  features.forEach((feature) => {
    feature.set("sourceLayer", "huangkeng");
    feature.setStyle(huangKengStyle(feature));
  });

  return new ol.layer.Vector({
    source: new ol.source.Vector({ features }),
    opacity: 0.95,
    declutter: true,
  });
}

function huangKengStyle(feature) {
  const props = feature.getProperties();
  const town = props["镇"] || props.XZCNAME || "";
  const color = town.includes("麻沙") ? "#6ffdf5" : "#ffee59";
  const label = `${props["镇"] || ""}${props["村"] || ""}\n${props["林班"] || ""}-${props["大班"] || ""}-${props["小班"] || props.name || ""}`;
  return [
    new ol.style.Style({
      stroke: new ol.style.Stroke({ color: "rgba(0,0,0,0.78)", width: 7 }),
      fill: new ol.style.Fill({ color: "rgba(0,45,32,0.14)" }),
    }),
    new ol.style.Style({
      stroke: new ol.style.Stroke({ color: "rgba(255,255,255,0.72)", width: 4 }),
    }),
    new ol.style.Style({
      stroke: new ol.style.Stroke({ color, width: 2 }),
      fill: new ol.style.Fill({ color: town.includes("麻沙") ? "rgba(111,253,245,0.12)" : "rgba(255,238,89,0.1)" }),
      text: new ol.style.Text({
        text: label.trim(),
        font: "bold 11px Microsoft YaHei",
        fill: new ol.style.Fill({ color: "#fff" }),
        stroke: new ol.style.Stroke({ color: "rgba(0,0,0,0.85)", width: 3 }),
        overflow: true,
      }),
    }),
  ];
}

function createKangVillageLayer() {
  if (!window.KANG_VILLAGE_GEOJSON) {
    return new ol.layer.Vector({ source: new ol.source.Vector() });
  }
  const features = new ol.format.GeoJSON().readFeatures(window.KANG_VILLAGE_GEOJSON, {
    dataProjection: "EPSG:4326",
    featureProjection: "EPSG:3857",
  });
  features.forEach((feature) => {
    feature.set("sourceLayer", "kangVillage");
    feature.setStyle(kangVillageStyle(feature));
  });
  return new ol.layer.Vector({
    source: new ol.source.Vector({ features }),
    opacity: 0.9,
    declutter: true,
  });
}

function kangVillageStyle(feature) {
  const props = feature.getProperties();
  return [
    new ol.style.Style({
      stroke: new ol.style.Stroke({ color: "rgba(0,0,0,0.72)", width: 6 }),
      fill: new ol.style.Fill({ color: "rgba(255, 157, 48, 0.12)" }),
    }),
    new ol.style.Style({
      stroke: new ol.style.Stroke({ color: "#ffb13b", width: 2 }),
      fill: new ol.style.Fill({ color: "rgba(255, 177, 59, 0.08)" }),
      text: new ol.style.Text({
        text: props["名称"] || props.name || "",
        fill: new ol.style.Fill({ color: "#fff6d6" }),
        stroke: new ol.style.Stroke({ color: "rgba(0,0,0,0.82)", width: 4 }),
        font: "bold 12px Microsoft YaHei",
        overflow: true,
      }),
    }),
  ];
}

function setBasemapMode(mode) {
  const sdkMode = normalizeSdkBasemapMode(mode);
  remoteSensing.currentBasemapMode = sdkMode;
  const sdkBasemapReady = hasSdkBasemap();
  const sdkBasemapWaiting = sdkBasemapPending();
  applySdkBasemapMode(sdkMode);
  if (gisLayers.offlineBase) {
    gisLayers.offlineBase.setVisible(sdkBasemapWaiting || (!sdkBasemapReady && sdkMode === "ter"));
    gisLayers.offlineBase.setOpacity(sdkBasemapWaiting ? 0.55 : sdkMode === "ter" ? 0.42 : 0.58);
  }
  if (gisLayers.localBase) {
    gisLayers.localBase.setVisible(!sdkBasemapReady && !sdkBasemapWaiting && sdkMode !== "img");
    gisLayers.localBase.setOpacity(sdkMode === "ter" ? 0.86 : 1);
  }
  if (gisLayers.satellite) {
    gisLayers.satellite.setSource(baseSources.imagery);
    gisLayers.satellite.setVisible(!sdkBasemapReady && !sdkBasemapWaiting && sdkMode === "img");
    gisLayers.satellite.setOpacity(sdkMode === "img" ? 0.92 : 0);
  }
  if (gisLayers.hillshade) {
    gisLayers.hillshade.setOpacity(0);
  }

  document.body.classList.toggle("terrain3d-mode", sdkMode === "ter");
  document.body.classList.toggle("imagery-mode", sdkMode === "img");
  document.body.classList.toggle("standard-mode", sdkMode === "vec");
}

function createEmptyDataLayer(visible = true) {
  return new ol.layer.Vector({
    source: new ol.source.Vector({ features: [] }),
    visible,
  });
}

function openBlockCard(block) {
  cardTitle.textContent = "林班电子信息卡";
  cardSubtitle.textContent = `${block.name} · 影像信息`;
  activeInfoCardBlockId = String(block.id || "");
  infoGrid.innerHTML = [
    ["林班编号", block.code],
    ["林班名称", block.name],
    ["面积", block.area],
    ["竹种", block.variety],
    ["质量等级", block.level],
    ["经营主体", block.owner],
    ["海拔范围", block.altitude],
    ["坡度范围", block.slope],
    ["健康度", block.health],
    ["数据状态", "已入库"],
  ]
    .map(([label, value]) => `<span>${label}</span><b>${value}</b>`)
    .join("");

  renderImageTabs(block.images, "image");
  infoCard.classList.remove("hidden");
  businessCard.classList.add("hidden");

  if (!block.isLive || !block.id) {
    return;
  }

  const cardBlockId = activeInfoCardBlockId;
  renderImageTabs([...block.images, ["关联影像", "正在加载关联影像", "正在获取该林班关联的远程感知场景。"]], "image");

  fetchForestSceneLinks(block.id)
    .then((items) => {
      if (activeInfoCardBlockId !== cardBlockId) return;
      renderImageTabs([...block.images, linkedSceneSummaryTab(items)], "image");
    })
    .catch(() => {
      if (activeInfoCardBlockId !== cardBlockId) return;
      renderImageTabs(
        [...block.images, ["关联影像", "关联影像暂不可用", `林班 ${block.code || block.name} 的关联影像接口暂不可用。`]],
        "image"
      );
    });
}

function focusPoint(coord, nextZoom = 14) {
  if (!gisMap || !window.ol) return;
  gisMap.getView().animate({
    center: ol.proj.fromLonLat(coord),
    zoom: nextZoom,
    duration: 300,
  });
}

function focusFeature(feature, maxZoom = 14) {
  if (!gisMap || !feature?.getGeometry()) return;
  gisMap.getView().fit(feature.getGeometry().getExtent(), {
    padding: [150, 420, 170, 280],
    maxZoom,
    duration: 300,
  });
}

function focusLayer(layer, maxZoom = 13) {
  const extent = layer?.getSource().getExtent();
  if (!gisMap || !extent || ol.extent.isEmpty(extent)) return false;
  gisMap.getView().fit(extent, {
    padding: [150, 420, 170, 280],
    maxZoom,
    duration: 300,
  });
  return true;
}

function rowText(row) {
  return row.map((cell) => String(cell)).join(" ").toLowerCase();
}

function textTokens(text) {
  const value = String(text).toLowerCase();
  const tokens = value.split(/[\s/,\-·|]+/).filter((token) => token.length >= 2);
  const cjkGroups = value.match(/[\u3400-\u9fff]{2,}/g) || [];
  cjkGroups.forEach((group) => {
    tokens.push(group);
    for (let index = 0; index < group.length - 1; index += 1) {
      tokens.push(group.slice(index, index + 2));
    }
  });
  return [...new Set(tokens)].filter((token) => !["竹山", "边界", "图层", "资料", "已叠加", "可查看"].includes(token));
}

function rowTokens(row) {
  return [...new Set(row.flatMap((cell) => textTokens(cell)))];
}

function locateBlockRow(row) {
  const text = rowText(row);
  const block = blocks.find((item) => text.includes(item.code.toLowerCase()) || text.includes(item.name.toLowerCase()) || text.includes(item.owner.toLowerCase()));
  if (!block) return false;
  openBlockCard(block);
  focusPoint(block.center, 14);
  return true;
}

function locateImportedRow(row) {
  const text = rowText(row);
  const haystack = [importedOvobj.title, importedOvobj.id, importedOvobj.sourceFile, ...Object.values(importedOvobj.fields)].join(" ").toLowerCase();
  if (!rowTokens(row).some((token) => haystack.includes(token)) && !text.includes(importedOvobj.title.toLowerCase())) return false;
  openImportedObjectCard();
  focusPoint(importedOvobj.coord, 14);
  return true;
}

function findFeatureByRow(layer, row) {
  const tokens = rowTokens(row);
  if (!tokens.length) return null;
  let best = null;
  let bestScore = 0;
  layer
    ?.getSource()
    .getFeatures()
    .forEach((feature) => {
      const props = feature.getProperties();
      const values = Object.entries(props)
        .filter(([key]) => key !== "geometry")
        .map(([, value]) => String(value))
        .join(" ")
        .toLowerCase();
      const score = tokens.reduce((total, token) => total + (values.includes(token) ? 1 : 0), 0);
      if (score > bestScore) {
        best = feature;
        bestScore = score;
      }
    });
  return bestScore > 0 ? best : null;
}

function locateFeatureRow(row) {
  const feature = findFeatureByRow(gisLayers.huangkeng, row) || findFeatureByRow(gisLayers.kangVillage, row);
  if (!feature) {
    const text = rowText(row);
    if ((text.includes("麻沙") || text.includes("黄坑")) && focusLayer(gisLayers.huangkeng)) return true;
    if ((text.includes("康") || text.includes("内部分村")) && focusLayer(gisLayers.kangVillage)) return true;
    return false;
  }
  if (feature.get("sourceLayer") === "huangkeng") {
    openHuangKengCard(feature);
  } else if (feature.get("sourceLayer") === "kangVillage") {
    openKangVillageCard(feature);
  }
  focusFeature(feature, 15);
  return true;
}

function locateBusinessRow(row) {
  return locateImportedRow(row) || locateBlockRow(row) || locateFeatureRow(row);
}

function featureValues(feature) {
  const props = feature.getProperties();
  return Object.entries(props)
    .filter(([key]) => key !== "geometry")
    .map(([, value]) => String(value))
    .join(" ");
}

function scoreText(values, tokens) {
  const haystack = values.toLowerCase();
  return tokens.reduce((total, token) => total + (haystack.includes(token) ? 1 : 0), 0);
}

function huangKengRow(feature) {
  const p = feature.getProperties();
  const title = p["挂接"] || p["不不不"] || `${p["镇"] || p.XZCNAME || ""}${p["村"] || p.CGQNAME || ""}${p.LBH || ""}${p.DBH || ""}${p.XBH || ""}`;
  const location = `${p["镇"] || p.XZCNAME || ""}${p["村"] || p.CGQNAME || ""}`;
  const code = p.XBNO || [p["林班"] || p.LBH, p["大班"] || p.DBH, p["小班"] || p.XBH].filter(Boolean).join("-");
  return [title || code || "黄坑图斑", location || "黄坑镇", `KMZ边界 / ${code || "小班"}`, p["面积"] ? `面积${p["面积"]}亩` : "已叠加"];
}

function kangVillageRow(feature) {
  const p = feature.getProperties();
  const title = p["名称"] || p.name || `康内部分村-${p.ovkmlIndex || ""}`;
  return [title, "麻沙镇溪头村", "OVKML边界 / 康内部分村", p["面积"] || "已叠加"];
}

function buildLayerSearchRows(keyword) {
  const tokens = textTokens(keyword);
  if (!tokens.length) return { rows: [], locators: [] };

  const rows = [];
  const locators = [];

  const push = (row, locator) => {
    rows.push(row);
    locators.push(locator);
  };

  blocks.forEach((block) => {
    const values = [block.code, block.name, block.owner, block.level].join(" ");
    if (scoreText(values, tokens) > 0) push([block.name, block.owner, "竹林林班 / 样例小班", block.level], () => {
      openBlockCard(block);
      focusPoint(block.center, 14);
    });
  });

  if (scoreText([importedOvobj.title, importedOvobj.id, importedOvobj.sourceFile, ...Object.values(importedOvobj.fields)].join(" "), tokens) > 0) {
    push([importedOvobj.title, importedOvobj.fields["坐落"] || "小桥镇上岔村", "导入点位 / 权属档案", "已入库"], () => {
      openImportedObjectCard();
      focusPoint(importedOvobj.coord, 14);
    });
  }

  gisLayers.huangkeng
    ?.getSource()
    .getFeatures()
    .map((feature) => ({ feature, score: scoreText(featureValues(feature), tokens) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 40)
    .forEach(({ feature }) => push(huangKengRow(feature), () => {
      openHuangKengCard(feature);
      focusFeature(feature, 15);
    }));

  gisLayers.kangVillage
    ?.getSource()
    .getFeatures()
    .map((feature) => ({ feature, score: scoreText(featureValues(feature), tokens) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 40)
    .forEach(({ feature }) => push(kangVillageRow(feature), () => {
      openKangVillageCard(feature);
      focusFeature(feature, 15);
    }));

  return { rows, locators };
}

function openImportedObjectCard() {
  cardTitle.textContent = importedOvobj.title;
  cardSubtitle.textContent = `${importedOvobj.sourceFile} · 导入点位信息`;
  infoGrid.innerHTML = Object.entries(importedOvobj.fields)
    .map(([label, value]) => `<span>${label}</span><b>${value}</b>`)
    .join("");
  imageTabs.innerHTML = importedOvobj.images
    .map(([name], index) => `<button class="${index === 0 ? "active" : ""}" data-import-image="${index}">${name}</button>`)
    .join("");

  function renderImportedImage(index) {
    const [name, title, desc] = importedOvobj.images[index];
    imagePanel.innerHTML = `
      <div class="preview">${name}</div>
      <div>
        <strong>${title}</strong>
        <p>${desc}</p>
      </div>
    `;
  }

  imageTabs.querySelectorAll("[data-import-image]").forEach((button) => {
    button.addEventListener("click", () => {
      imageTabs.querySelectorAll("button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      renderImportedImage(Number(button.dataset.importImage));
    });
  });

  renderImportedImage(0);
  businessCard.classList.add("hidden");
  infoCard.classList.remove("hidden");
}

function openHuangKengCard(feature) {
  const p = feature.getProperties();
  cardTitle.textContent = "麻沙镇黄坑镇竹山边界";
  cardSubtitle.textContent = `${p["镇"] || p.XZCNAME || "竹山"} ${p["村"] || p.CGQNAME || ""} · KMZ 边界属性`;
  const fields = [
    ["序号", p["序号"] || p.name || p.kmzIndex],
    ["小班编号", p.XBNO],
    ["镇", p["镇"] || p.XZCNAME],
    ["村", p["村"] || p.CGQNAME],
    ["林班", p["林班"] || p.LBH],
    ["大班", p["大班"] || p.DBH],
    ["小班", p["小班"] || p.XBH],
    ["面积", p["面积"] || p.XBMJ],
    ["树种代码", p.YSSZ],
    ["年龄", p["年龄"] || p.NL],
    ["平均胸径", p["平均胸径"] || p.PJXJ],
    ["平均高", p["平均高"] || p.PJSG],
    ["亩株数", p["亩株数"] || p.MMMZZS],
    ["海拔", `${p.HB1 || ""}-${p.HB2 || ""}`],
    ["坡度", p.PD],
    ["调查人", p.DCZ],
  ].filter(([, value]) => value !== undefined && value !== "");

  infoGrid.innerHTML = fields.map(([label, value]) => `<span>${label}</span><b>${value}</b>`).join("");
  const tabs = [
    ["KMZ边界", "真实边界面", "该图斑由 KMZ 文件解析生成，已作为 OpenLayers 矢量面叠加到底图。"],
    ["林班属性", "小班调查属性", "展示镇、村、林班、大班、小班、面积、树种、年龄、胸径、平均高等字段。"],
    ["影像核查", "卫星/三维底图核查", "可切换实景或三维底图查看边界与山体、道路、林地纹理的叠合关系。"],
  ];
  imageTabs.innerHTML = tabs.map(([name], index) => `<button class="${index === 0 ? "active" : ""}" data-hk-image="${index}">${name}</button>`).join("");

  function renderTab(index) {
    const [name, title, desc] = tabs[index];
    imagePanel.innerHTML = `
      <div class="preview">${name}</div>
      <div>
        <strong>${title}</strong>
        <p>${desc}</p>
      </div>
    `;
  }

  imageTabs.querySelectorAll("[data-hk-image]").forEach((button) => {
    button.addEventListener("click", () => {
      imageTabs.querySelectorAll("button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      renderTab(Number(button.dataset.hkImage));
    });
  });

  renderTab(0);
  businessCard.classList.add("hidden");
  infoCard.classList.remove("hidden");
}

function openKangVillageCard(feature) {
  const p = feature.getProperties();
  cardTitle.textContent = "康内部分村竹林图斑";
  cardSubtitle.textContent = `${p["名称"] || p.name || "康图斑"} · OVKML 图斑属性`;
  const fields = [
    ["序号", p["序号"] || p.ovkmlIndex],
    ["名称", p["名称"] || p.name],
    ["日期", p["日期"]],
    ["面积", p["面积"]],
    ["长度", p["长度"]],
    ["面积单价", p["面积单价"]],
    ["长度单价", p["长度单价"]],
    ["面积总价", p["面积总价"]],
    ["长度总价", p["长度总价"]],
  ].filter(([, value]) => value !== undefined && value !== "");

  infoGrid.innerHTML = fields.map(([label, value]) => `<span>${label}</span><b>${value}</b>`).join("");
  const tabs = [
    ["OVKML图斑", "康内部分村图斑边界", "该图斑由康（总内部分村）.ovkml 解析生成，已作为独立矢量图层叠加到 WebGIS 底图。"],
    ["边界核查", "实景/卫星底图核查", "可与卫星影像、黄坑边界、导入点位等图层叠加，用于核验边界与山体、道路、林地纹理关系。"],
    ["属性档案", "面积、长度与采集时间", "保留原始 OVKML 表格中的面积、长度、日期、总价等字段，后续可继续扩展村名、权属等字段。"],
  ];
  imageTabs.innerHTML = tabs.map(([name], index) => `<button class="${index === 0 ? "active" : ""}" data-kang-image="${index}">${name}</button>`).join("");

  function renderTab(index) {
    const [name, title, desc] = tabs[index];
    imagePanel.innerHTML = `
      <div class="preview">${name}</div>
      <div>
        <strong>${title}</strong>
        <p>${desc}</p>
      </div>
    `;
  }

  imageTabs.querySelectorAll("[data-kang-image]").forEach((button) => {
    button.addEventListener("click", () => {
      imageTabs.querySelectorAll("button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      renderTab(Number(button.dataset.kangImage));
    });
  });

  renderTab(0);
  businessCard.classList.add("hidden");
  infoCard.classList.remove("hidden");
}

function escapeTableCell(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderBusinessRows(data, rows = data.rows, locators = []) {
  activeRenderedRows = rows;
  activeRowLocators = locators;
  if (rows.length === 0) {
    businessRows.innerHTML = `<tr><td colspan="${data.columns.length}">${escapeTableCell(data.emptyText || "暂无后台数据")}</td></tr>`;
    return;
  }
  businessRows.innerHTML = rows
    .map((row, index) => `<tr data-row-index="${index}">${row.map((cell) => `<td>${escapeTableCell(cell)}</td>`).join("")}</tr>`)
    .join("");
}

function normalizeBusinessAdminLinks(data) {
  if (Array.isArray(data.adminLinks) && data.adminLinks.length) {
    return data.adminLinks
      .filter((link) => link && link.href)
      .map((link) => ({ label: link.label || "后台管理", href: link.href }));
  }
  if (data.adminHref) {
    return [{ label: data.adminLabel || "后台管理", href: data.adminHref }];
  }
  return [];
}

function renderBusinessAdminLinks(data) {
  if (!businessAdminLinks) return;
  const links = normalizeBusinessAdminLinks(data);
  businessAdminLinks.hidden = links.length === 0;
  businessAdminLinks.innerHTML = links
    .map((link) => `<a href="${escapeTableCell(link.href)}">${escapeTableCell(link.label)}</a>`)
    .join("");
}

function businessDashboardAdminLinks(payload, config) {
  if (Array.isArray(payload.adminLinks) && payload.adminLinks.length) return payload.adminLinks;
  if (payload.adminHref) return [{ label: payload.adminLabel || "后台管理", href: payload.adminHref }];
  return config.adminLinks || [];
}

async function fetchDashboardJson(endpoint) {
  const response = await zhushanApiFetch(`${ZHUSHAN_REMOTE_API_BASE}${endpoint}`);
  if (!response.ok) throw new Error(`${endpoint} ${response.status}`);
  return response.json();
}

function formatDashboardCount(value, unit = "") {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return `0${unit}`;
  return `${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(numeric)}${unit}`;
}

function textOrFallback(value, fallback = "未填") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function joinFilled(values, fallback = "未填") {
  const text = values.map((value) => String(value ?? "").trim()).filter(Boolean).join(" / ");
  return text || fallback;
}

function forestSearchLocation(block) {
  return joinFilled([block.countyName || block.countyCode, block.townName || block.townCode, block.villageName || block.villageCode], "区划未填");
}

function forestSearchResource(block) {
  return joinFilled(
    [
      block.forestType || block.operationType || block.baseType,
      block.areaMu !== null && block.areaMu !== undefined && block.areaMu !== "" ? formatAreaMu(block.areaMu) : "",
      block.qualityGrade,
    ],
    "资源未填"
  );
}

function forestSearchStatus(block) {
  return joinFilled([block.ownershipStatus, block.managementStatus, block.healthStatus || block.riskLevel], "待完善");
}

function forestSearchRows(blocks) {
  return blocks.map((block) => [
    joinFilled([block.blockCode || block.code || block.id, block.name], "未命名林班"),
    forestSearchLocation(block),
    forestSearchResource(block),
    forestSearchStatus(block),
  ]);
}

function ledgerBlockCard(block) {
  const status = forestSearchStatus(block);
  return {
    id: block.id || block.blockCode || block.code || block.name || "forest-block",
    code: block.blockCode || block.code || block.id || "林班",
    name: block.name || block.blockCode || block.code || "未命名林班",
    area: block.areaMu !== null && block.areaMu !== undefined ? formatAreaMu(block.areaMu) : "面积未填",
    variety: block.forestType || block.operationType || "未填",
    level: block.qualityGrade || "未评级",
    owner: forestSearchLocation(block),
    altitude: block.bambooAge || block.countyName || "待补充",
    slope: block.slopeDegree ? `${block.slopeDegree}°` : "待补充",
    health: status,
    images: [
      ["空间台账", "后台林班台账", `${block.blockCode || block.name || "林班"} 来自后台林班空间台账。`],
      ["资源属性", "资源与经营信息", `资源：${forestSearchResource(block)}；状态：${status}。`],
      ["图档关联", "图档联动状态", `区划：${forestSearchLocation(block)}；林权档案请在林权档案后台挂接查看。`],
    ],
    isLive: false,
  };
}

function findLiveForestFeature(block) {
  const source = gisLayers.bamboo?.getSource?.();
  if (!source) return null;
  const keys = [block.id, block.blockCode, block.code, block.name].map((value) => String(value || "").trim()).filter(Boolean);
  if (!keys.length) return null;
  return (
    source
      .getFeatures()
      .find((feature) =>
        [feature.get("id"), feature.get("blockCode"), feature.get("code"), feature.get("name"), feature.getId?.()]
          .map((value) => String(value || "").trim())
          .some((value) => keys.includes(value))
      ) || null
  );
}

function forestSearchLocators(blocks) {
  return blocks.map((block) => () => {
    const feature = findLiveForestFeature(block);
    if (feature) {
      openBlockCard(forestBlockFromFeature(feature));
      focusFeature(feature, 15);
      return;
    }
    openBlockCard(ledgerBlockCard(block));
  });
}

async function fetchForestSearchBlocks(keyword = "") {
  const params = new URLSearchParams({ limit: "8" });
  if (keyword) params.set("q", keyword);
  const payload = await fetchDashboardJson(`/api/forest-blocks?${params.toString()}`);
  const items = Array.isArray(payload.items) ? payload.items : [];
  return { items, total: Number(payload.total ?? items.length) || 0 };
}

function forestSearchMetrics(summary = {}, totalFallback = 0) {
  const total = Number(summary.total ?? totalFallback) || 0;
  return [
    ["后台林班", `${formatDashboardCount(total, " 个")}`],
    ["面积合计", `${formatDashboardCount(summary.totalAreaMu, " 亩")}`],
    ["健康率", total ? `${Number(summary.healthyRate || 0)}%` : "暂无后台数据"],
  ];
}

async function loadForestSearchCard() {
  let searchTimer = null;
  const data = {
    title: "竹山搜索结果",
    subtitle: "林班台账、权属关联与地图图层一体检索",
    searchable: true,
    placeholder: "输入林班编号、名称、乡镇、村",
    metrics: [["后台林班", "加载中"], ["面积合计", "加载中"], ["健康率", "加载中"]],
    columns: ["检索对象", "坐落位置", "资源属性", "状态"],
    rows: [],
    rowLocators: [],
    emptyText: "正在加载后台林班数据",
    adminLinks: [
      { label: "林班后台", href: "admin-blocks.html" },
      { label: "林权后台", href: "admin-rights.html" },
    ],
  };

  async function updateRows(keyword = "") {
    try {
      data.emptyText = keyword ? "正在检索后台林班数据" : "正在加载后台林班数据";
      renderBusinessRows(data, [], []);
      const result = await fetchForestSearchBlocks(keyword);
      data.rows = forestSearchRows(result.items);
      data.rowLocators = forestSearchLocators(result.items);
      data.emptyText = keyword ? "未检索到匹配的后台林班数据" : "暂无后台林班数据，请先在林班空间台账导入或新增";
      if (activeBusinessData === data) renderBusinessRows(data, data.rows, data.rowLocators);
    } catch (error) {
      data.rows = [];
      data.rowLocators = [];
      data.emptyText = `后台林班接口暂不可用：${error.message}`;
      if (activeBusinessData === data) renderBusinessRows(data, data.rows, data.rowLocators);
    }
  }

  data.onSearch = (keyword) => {
    if (searchTimer) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => updateRows(keyword), 220);
  };

  renderBusinessCard(data);

  try {
    const [summary, result] = await Promise.all([fetchDashboardJson("/api/map/forest-blocks/summary"), fetchForestSearchBlocks("")]);
    data.metrics = forestSearchMetrics(summary, result.total);
    data.rows = forestSearchRows(result.items);
    data.rowLocators = forestSearchLocators(result.items);
    data.emptyText = "暂无后台林班数据，请先在林班空间台账导入或新增";
    if (activeBusinessData === data) renderBusinessCard(data);
  } catch (error) {
    renderBusinessCard({
      ...data,
      metrics: [["后台林班", "不可用"], ["面积合计", "不可用"], ["健康率", "请检查接口"]],
      rows: [],
      rowLocators: [],
      emptyText: `后台林班接口暂不可用：${error.message}`,
    });
  }
}

async function loadSatelliteTrackCard() {
  const config = {
    title: "卫星图传任务",
    subtitle: "卫星影像入库、图传转换、影像目录与任务闭环",
    columns: ["任务编号", "任务状态", "影像场景", "更新时间"],
    adminLinks: [
      { label: "卫星图传", href: "satellite-manager.html" },
      { label: "影像后台", href: "admin-imagery.html" },
    ],
  };
  renderBusinessCard({
    ...config,
    metrics: [["图传任务", "加载中"], ["影像目录", "加载中"], ["来源", "后台影像管理"]],
    rows: [],
    emptyText: "正在加载后台图传任务",
  });

  try {
    const payload = await fetchDashboardJson("/api/dashboard/satellite-track");
    renderBusinessCard({
      ...config,
      title: payload.title || config.title,
      subtitle: payload.subtitle || config.subtitle,
      metrics: Array.isArray(payload.metrics) ? payload.metrics : [["图传任务", "0 条"], ["影像目录", "0 景"], ["来源", "后台影像管理"]],
      columns: Array.isArray(payload.columns) ? payload.columns : config.columns,
      rows: Array.isArray(payload.rows) ? payload.rows : [],
      emptyText: payload.emptyText || "暂无后台图传任务，请在卫星图传管理系统创建或注册影像任务",
      adminLinks: Array.isArray(payload.adminLinks) ? payload.adminLinks : config.adminLinks,
    });
  } catch (error) {
    renderBusinessCard({
      ...config,
      metrics: [["图传任务", "不可用"], ["影像目录", "不可用"], ["状态", "请检查接口"]],
      rows: [],
      emptyText: `后台图传接口暂不可用：${error.message}`,
    });
  }
}

function renderBusinessCard(data) {
  activeBusinessData = data;
  businessTitle.textContent = data.title;
  businessSubtitle.textContent = data.subtitle;
  renderBusinessAdminLinks(data);
  businessMetrics.innerHTML = `
    ${data.metrics.map(([label, value]) => `<article><span>${escapeTableCell(label)}</span><strong>${escapeTableCell(value)}</strong></article>`).join("")}
    ${
      data.searchable
        ? `<label class="business-search"><span>林班搜索</span><input id="forestSearchInput" type="search" placeholder="${escapeTableCell(data.placeholder)}" autocomplete="off" /></label>`
        : ""
    }
  `;
  businessHead.innerHTML = `<tr>${data.columns.map((column) => `<th>${escapeTableCell(column)}</th>`).join("")}</tr>`;
  renderBusinessRows(data, data.rows, data.rowLocators || []);
  businessCard.classList.remove("hidden");
  infoCard.classList.add("hidden");

  if (data.searchable) {
    const searchInput = document.querySelector("#forestSearchInput");
    searchInput?.focus();
    searchInput?.addEventListener("input", () => {
      const keyword = searchInput.value.trim().toLowerCase();
      if (typeof data.onSearch === "function") {
        data.onSearch(keyword);
        return;
      }
      const rows = keyword
        ? data.rows.filter((row) => row.some((cell) => String(cell).toLowerCase().includes(keyword)))
        : data.rows;
      renderBusinessRows(data, rows);
    });
  }
}

async function loadBackendBusinessCard(key, config) {
  const loadingData = {
    title: config.title,
    subtitle: config.subtitle,
    metrics: [["后台数据", "加载中"], ["来源", "业务管理模块"], ["状态", "实时读取"]],
    columns: config.columns,
    rows: [],
    emptyText: "正在加载后台业务数据",
    adminLinks: config.adminLinks,
  };
  renderBusinessCard(loadingData);

  try {
    const response = await zhushanApiFetch(`${ZHUSHAN_REMOTE_API_BASE}${config.endpoint}`);
    if (!response.ok) throw new Error(`business dashboard ${response.status}`);
    const payload = await response.json();
    renderBusinessCard({
      title: payload.title || config.title,
      subtitle: payload.subtitle || config.subtitle,
      metrics: Array.isArray(payload.metrics) ? payload.metrics : [],
      columns: Array.isArray(payload.columns) ? payload.columns : config.columns,
      rows: Array.isArray(payload.rows) ? payload.rows : [],
      emptyText: payload.emptyText || "暂无后台数据，请在管理台账中新增后发布到大屏",
      adminLinks: businessDashboardAdminLinks(payload, config),
      adminHref: payload.adminHref || "",
      adminLabel: payload.adminLabel || "",
    });
  } catch (error) {
    renderBusinessCard({
      title: config.title,
      subtitle: config.subtitle,
      metrics: [["后台数据", "不可用"], ["来源", "业务管理模块"], ["状态", "请检查接口"]],
      columns: config.columns,
      rows: [],
      emptyText: `后台业务接口暂不可用：${error.message}`,
      adminLinks: config.adminLinks,
    });
  }
}

const backendToolLoaders = {
  search: loadForestSearchCard,
  satelliteTrack: loadSatelliteTrackCard,
};

function openBusinessCard(key) {
  const backendToolLoader = backendToolLoaders[key];
  if (backendToolLoader) {
    backendToolLoader();
    return;
  }

  const backendConfig = backendBusinessModules[key];
  if (backendConfig) {
    loadBackendBusinessCard(key, backendConfig);
    return;
  }

  const data = leftToolData[key];
  if (!data) return;
  renderBusinessCard(data);
}

function setZoom(nextZoom) {
  zoom = Math.min(1.8, Math.max(0.72, Number(nextZoom.toFixed(2))));
  document.documentElement.style.setProperty("--zoom", zoom);
  document.documentElement.style.setProperty("--bg-size", `${Math.round(zoom * 160)}%`);
  zoomValue.textContent = `${Math.round(zoom * 100)}%`;
  if (gisMap) {
    gisMap.getView().animate({ zoom: 10 + (zoom - 1) * MAP_ZOOM_PER_SCALE_UNIT, duration: 160 });
  }
}

function syncZoomControlFromMap() {
  const mapZoom = Number(gisMap?.getView?.().getZoom?.() ?? 10);
  zoom = Math.min(1.8, Math.max(0.72, 1 + (mapZoom - 10) / MAP_ZOOM_PER_SCALE_UNIT));
  document.documentElement.style.setProperty("--zoom", Number(zoom.toFixed(2)));
  document.documentElement.style.setProperty("--bg-size", `${Math.round(zoom * 160)}%`);
  zoomValue.textContent = `${Math.round(zoom * 100)}%`;
}

document.querySelectorAll("[data-layer]").forEach((input) => {
  input.addEventListener("change", () => syncLayerControl(input));
});
restoreDashboardLayerState();
syncAllLayerControls();
loadDashboardPublishedLayers();
loadDashboardWorkflowStatus();

document.querySelector("#zoomIn")?.addEventListener("click", () => setZoom(zoom + 0.12));
document.querySelector("#zoomOut")?.addEventListener("click", () => setZoom(zoom - 0.12));

document.querySelectorAll("[data-basemap]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-basemap]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    setBasemapMode(button.dataset.basemap);
  });
});

scene?.addEventListener("wheel", (event) => {
  event.preventDefault();
  setZoom(zoom + (event.deltaY < 0 ? 0.08 : -0.08));
});

window.addEventListener("resize", () => {
  gisMap?.updateSize();
});

closeCard?.addEventListener("click", () => infoCard.classList.add("hidden"));

document.querySelector("#closeBusinessCard")?.addEventListener("click", () => businessCard.classList.add("hidden"));

businessRows?.addEventListener("click", (event) => {
  const rowEl = event.target.closest("tr[data-row-index]");
  if (!rowEl || !activeBusinessData) return;
  const rowIndex = Number(rowEl.dataset.rowIndex);
  const row = activeRenderedRows[rowIndex];
  if (!row) return;
  if (activeRowLocators[rowIndex]) {
    activeRowLocators[rowIndex]();
    return;
  }
  locateBusinessRow(row);
});

document.querySelectorAll("[data-tool]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-tool]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    if (button.dataset.tool === "layers") {
      const collapsed = layerCard.classList.toggle("collapsed");
      button.setAttribute("aria-expanded", String(!collapsed));
      businessCard.classList.add("hidden");
      return;
    }
    document.querySelectorAll("[data-business]").forEach((item) => item.classList.remove("active"));
    openBusinessCard(button.dataset.tool);
  });
});

document.querySelectorAll("[data-business]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-business]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    document.querySelectorAll("[data-tool]").forEach((item) => item.classList.toggle("active", item.dataset.tool === "layers"));
    openBusinessCard(button.dataset.business);
  });
});

renderBlocks();
initializeForestFilters();
initWebGIS();
setBasemapMode("img");
syncZoomControlFromMap();
startDashboardVersionMonitor();
