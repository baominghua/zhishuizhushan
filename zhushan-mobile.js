const realPoint = {
  id: "xiaoqiao-shangtun",
  name: "小桥上屯竹林",
  code: "350783006007JE00005",
  coord: [118.42, 26.9],
  level: "真实点位",
  fields: [
    ["坐落", "建瓯市小桥镇上屯村"],
    ["小地名", "水北垅"],
    ["树种", "毛竹"],
    ["面积", "56亩"],
    ["权利人", "魏思华"],
    ["小班", "5-3(3).8"],
  ],
};

const tabText = {
  uav: "无人机航拍用于查看竹冠覆盖、作业道路、林班边界和采伐窗口。",
  satellite: "卫星底图用于年度长势对比、变化检测、边界核验和空间格局分析。",
  carbon: "碳汇服务叠加样方、冠层覆盖率、胸径数据和年度固碳估算结果。",
};

const layerDrawer = document.querySelector("#layerDrawer");
const mobileNav = document.querySelector(".mobile-nav");
const plotSheet = document.querySelector("#plotSheet");
const plotName = document.querySelector("#plotName");
const plotCode = document.querySelector("#plotCode");
const plotLevel = document.querySelector("#plotLevel");
const plotFields = document.querySelector("#plotFields");
const mobileSearch = document.querySelector("#mobileSearch");
const mobileStats = document.querySelector("#mobileStats");
const searchResults = document.querySelector("#searchResults");
const mobileIndustryPanel = document.querySelector("#mobileIndustryPanel");
const mobileIndustryTitle = document.querySelector("#mobileIndustryTitle");
const mobileIndustryAdminLinks = document.querySelector("#mobileIndustryAdminLinks");
const mobileIndustryMetrics = document.querySelector("#mobileIndustryMetrics");
const mobileIndustryRows = document.querySelector("#mobileIndustryRows");
const publishedLayerControls = document.querySelector("#publishedLayerControls");

let mobileMap = null;
let pointLayer = null;
let boundaryLayer = null;
let kangLayer = null;
let liveForestBlockLayer = null;
let selectedBoundaryFeature = null;
let searchRecords = [];
let mobileForestBlockSearchController = null;
let mobileForestBlockLayerTimer = null;
const mobileLayers = {};

const normalizeMobileApiBase = (value) => String(value || "").trim().replace(/\/+$/, "");
const MOBILE_REMOTE_API_BASE =
  normalizeMobileApiBase(window.SATELLITE_CONFIG?.remoteApiBase) ||
  localStorage.getItem("remoteSensingApiBase") ||
  (window.location.protocol === "file:"
    ? "http://127.0.0.1:8010"
    : window.location.port === "8010"
      ? window.location.origin
      : `${window.location.protocol}//${window.location.hostname}:8010`);
const MOBILE_API_TOKEN =
  window.SATELLITE_CONFIG?.humanLoginEnabled === false
    ? String(window.SATELLITE_CONFIG?.apiToken || "").trim()
    : "";

function mobileApiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (MOBILE_API_TOKEN) headers.set("Authorization", `Bearer ${MOBILE_API_TOKEN}`);
  return fetch(url, { credentials: "include", ...options, headers });
}
const MOBILE_FOREST_BLOCK_MAX_FEATURES = 800;

const MOBILE_INDUSTRY_ADMIN_LINKS = [
  { label: "交易撮合", href: "admin-trade-matches.html" },
  { label: "物流溯源", href: "admin-logistics-traces.html" },
  { label: "二维码", href: "admin-product-qrcodes.html" },
  { label: "供应链金融", href: "admin-supply-chain-finance.html" },
  { label: "价格指数", href: "admin-price-indexes.html" },
  { label: "移动服务", href: "admin-mobile-service-channels.html" },
];

const MOBILE_BUSINESS_DASHBOARDS = {
  farmers: {
    title: "竹农信息卡",
    endpoint: "/api/business/farmers/dashboard",
    emptyText: "请在竹农管理后台台账中新增记录后查看。",
    adminLinks: [{ label: "竹农后台", href: "admin-farmers.html" }],
  },
  cooperatives: {
    title: "合作社信息卡",
    endpoint: "/api/business/cooperatives/dashboard",
    emptyText: "请在合作社管理后台台账中新增记录后查看。",
    adminLinks: [{ label: "合作社后台", href: "admin-cooperatives.html" }],
  },
  enterprises: {
    title: "竹企信息卡",
    endpoint: "/api/business/enterprises/dashboard",
    emptyText: "请在竹企管理后台台账中新增记录后查看。",
    adminLinks: [{ label: "竹企后台", href: "admin-enterprises.html" }],
  },
  "plant-protection-events": {
    title: "植保信息卡",
    endpoint: "/api/business/plant-protection-events/dashboard",
    emptyText: "请在植保管理后台台账中新增记录后查看。",
    adminLinks: [{ label: "植保后台", href: "admin-plant-protection.html" }],
  },
  "carbon-estimates": {
    title: "碳汇信息卡",
    endpoint: "/api/business/carbon-estimates/dashboard",
    emptyText: "请在碳汇测算后台台账中新增记录后查看。",
    adminLinks: [{ label: "碳汇后台", href: "admin-carbon-estimates.html" }],
  },
};

function escapeMobileHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function mobileStatElement(key) {
  return mobileStats?.querySelector(`[data-stat="${key}"]`) || null;
}

function setMobileStat(key, value) {
  const target = mobileStatElement(key);
  if (target) target.textContent = value;
}

function formatMobileAreaMu(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "暂无后台数据";
  if (numeric >= 10000) return `${(numeric / 10000).toFixed(numeric >= 100000 ? 1 : 2)} 万亩`;
  return `${numeric.toFixed(numeric >= 100 ? 1 : 2)} 亩`;
}

function renderMobileResourceSummary(payload = {}) {
  const total = Number(payload.total || 0);
  setMobileStat("totalAreaMu", formatMobileAreaMu(payload.totalAreaMu));
  setMobileStat("totalBlocks", total ? `${total} 个` : "0 个");
  setMobileStat("healthyRate", total ? `${Number(payload.healthyRate || 0)}%` : "暂无后台数据");
}

function renderMobileResourceSummaryUnavailable(error) {
  setMobileStat("totalAreaMu", "后台数据不可用");
  setMobileStat("totalBlocks", "后台数据不可用");
  setMobileStat("healthyRate", "后台数据不可用");
  if (error) console.warn("mobile resource summary unavailable", error);
}

async function loadMobileResourceSummary() {
  try {
    const response = await mobileApiFetch(`${MOBILE_REMOTE_API_BASE}/api/map/forest-blocks/summary`);
    if (!response.ok) throw new Error(`forest block summary ${response.status}`);
    renderMobileResourceSummary(await response.json());
  } catch (error) {
    renderMobileResourceSummaryUnavailable(error);
  }
}

function normalizeMobileAdminLinks(payload = {}, fallbackLinks = []) {
  const links = Array.isArray(payload.adminLinks) && payload.adminLinks.length
    ? payload.adminLinks
    : payload.adminHref
      ? [{ label: payload.adminLabel || "后台", href: payload.adminHref }]
      : fallbackLinks;
  return links.filter((link) => link && link.href).map((link) => ({ label: link.label || "后台", href: link.href }));
}

function normalizeMobileIndustryAdminLinks(payload = {}) {
  return normalizeMobileAdminLinks(payload, MOBILE_INDUSTRY_ADMIN_LINKS);
}

function renderMobileIndustryAdminLinks(payload = {}, fallbackLinks = MOBILE_INDUSTRY_ADMIN_LINKS) {
  if (!mobileIndustryAdminLinks) return;
  const links = normalizeMobileAdminLinks(payload, fallbackLinks);
  mobileIndustryAdminLinks.hidden = links.length === 0;
  mobileIndustryAdminLinks.innerHTML = links
    .map((link) => `<a href="${escapeMobileHtml(link.href)}">${escapeMobileHtml(link.label)}</a>`)
    .join("");
}

function mobilePublishedLayerSubtitle(layer = {}) {
  return [
    layer.layerType || "地图图层",
    layer.sourceType || layer.dataSource || "后台配置",
    layer.publishRiskStatus ? `风险 ${layer.publishRiskStatus}` : "",
    layer.visibleOnDashboard === false ? "未发布到大屏" : "已发布到大屏",
  ]
    .filter(Boolean)
    .join(" · ");
}

function mobilePublishedLayerSummary(payload = {}, layers = []) {
  const summary = payload.summary || {};
  const sourceTypes = Object.keys(summary.bySourceType || {}).length;
  return `
    <div class="published-layer-summary" aria-label="后台发布图层摘要">
      <span>发布 ${escapeMobileHtml(summary.total ?? layers.length)} 层</span>
      <span>关联林班 ${escapeMobileHtml(summary.linkedBlockTotal ?? 0)} 个</span>
      <span>来源 ${escapeMobileHtml(sourceTypes)} 类</span>
    </div>
  `;
}

function renderMobilePublishedLayerControls(payload = {}) {
  if (!publishedLayerControls) return;
  const layers = (Array.isArray(payload.items) ? payload.items : []).filter((layer) => !layer.deletedAt);
  if (!layers.length) {
    publishedLayerControls.innerHTML = '<p class="published-layer-state">暂无后台发布图层</p>';
    return;
  }
  publishedLayerControls.innerHTML = mobilePublishedLayerSummary(payload, layers) + layers
    .slice(0, 20)
    .map(
      (layer) => `
        <label title="当前仅展示发布目录，渲染器按图层类型逐步接入">
          <input type="checkbox" checked disabled aria-label="${escapeMobileHtml(layer.name || layer.recordCode || "后台图层")}" />
          <strong>${escapeMobileHtml(layer.name || layer.recordCode || "后台图层")}</strong>
          <small>${escapeMobileHtml(mobilePublishedLayerSubtitle(layer))}</small>
        </label>
      `,
    )
    .join("");
}

async function loadMobilePublishedLayers() {
  if (!publishedLayerControls) return;
  publishedLayerControls.innerHTML = '<p class="published-layer-state">正在加载后台发布图层</p>';
  try {
    const response = await mobileApiFetch(`${MOBILE_REMOTE_API_BASE}/api/map-layers/dashboard`);
    if (!response.ok) throw new Error(`map layers ${response.status}`);
    renderMobilePublishedLayerControls(await response.json());
  } catch (error) {
    publishedLayerControls.innerHTML = '<p class="published-layer-state">后台图层目录暂不可用</p>';
    console.warn("mobile published layers unavailable", error);
  }
}

function localMapExtent() {
  return ol.proj.transformExtent([117.55, 26.15, 118.88, 27.18], "EPSG:4326", "EPSG:3857");
}

function updateViewportVars() {
  const height = window.visualViewport?.height || window.innerHeight;
  document.documentElement.style.setProperty("--app-height", `${height}px`);
  mobileMap?.updateSize();
}

function fitPadding() {
  const navCollapsed = document.body.classList.contains("nav-collapsed");
  return navCollapsed ? [130, 24, 150, 24] : [130, 24, 250, 24];
}

function renderCard(title, code, level, fields) {
  plotName.textContent = title;
  plotCode.textContent = code;
  plotLevel.textContent = level;
  plotFields.innerHTML = fields
    .map(([label, value]) => `<article><span>${escapeMobileHtml(label)}</span><strong>${escapeMobileHtml(value || "-")}</strong></article>`)
    .join("");
  plotSheet.classList.remove("collapsed");
  document.querySelector("#sheetToggle").textContent = "收起";
  document.querySelector("#sheetToggle").setAttribute("aria-expanded", "true");
}

function renderPointCard() {
  renderCard(realPoint.name, realPoint.code, realPoint.level, realPoint.fields);
}

function formatMobileBlockArea(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "-";
  return `${numeric.toFixed(numeric >= 100 ? 1 : 2).replace(/\.0+$/, "")}亩`;
}

function mobileBlockTitle(block = {}) {
  return block.name || block.blockName || block.blockCode || block.id || "后台林班";
}

function mobileBlockLocation(block = {}) {
  return [block.countyName || block.countyCode, block.townName || block.townCode, block.villageName || block.villageCode]
    .filter(Boolean)
    .join(" / ");
}

function backendForestBlockFields(block = {}) {
  return [
    ["区划", mobileBlockLocation(block) || "-"],
    ["面积", formatMobileBlockArea(block.areaMu)],
    ["竹种 / 林种", block.bambooSpecies || block.forestType || "-"],
    ["基地类型", block.baseType || "-"],
    ["经营类型", block.operationType || block.managementType || "-"],
    ["质量等级", block.qualityGrade || "-"],
    ["健康状态", block.healthStatus || "-"],
    ["风险等级", block.riskLevel || "-"],
  ];
}

function renderBackendForestBlockCard(block = {}) {
  renderCard(mobileBlockTitle(block), block.blockCode || block.id || "-", "后台林班", backendForestBlockFields(block));
}

function boundaryTitle(props) {
  return `${props["镇"] || props.XZCNAME || "竹山"}${props["村"] || props.CGQNAME || ""} ${props["林班"] || props.LBH || ""}-${props["大班"] || props.DBH || ""}-${props["小班"] || props.XBH || ""}`;
}

function renderBoundaryCard(feature) {
  const p = feature.getProperties();
  if (p.sourceLayer === "kangVillage") {
    renderCard("康内部分村竹林图斑", p["名称"] || p.name || `KANG-${p.ovkmlIndex}`, "OVKML", [
      ["序号", p["序号"] || p.ovkmlIndex],
      ["名称", p["名称"] || p.name],
      ["日期", p["日期"]],
      ["面积", p["面积"]],
      ["长度", p["长度"]],
      ["面积总价", p["面积总价"]],
    ]);
    return;
  }
  renderCard("麻沙黄坑竹山边界", p.XBNO || p["挂接"] || p.name || `KMZ-${p.kmzIndex}`, `${p["镇"] || p.XZCNAME || "竹山"} · KMZ`, [
    ["镇", p["镇"] || p.XZCNAME],
    ["村", p["村"] || p.CGQNAME],
    ["林班", p["林班"] || p.LBH],
    ["大班", p["大班"] || p.DBH],
    ["小班", p["小班"] || p.XBH],
    ["面积", `${p["面积"] || p.XBMJ || "-"}亩`],
    ["年龄", p["年龄"] || p.NL],
    ["平均胸径", p["平均胸径"] || p.PJXJ],
    ["平均高", p["平均高"] || p.PJSG],
  ]);
}

function normalizeHuangKengGeojson() {
  const source = window.HUANGKENG_BAMBOO_GEOJSON || window.HUANG_KENG_BAMBOO_GEOJSON;
  if (!source) return null;
  const geojson = JSON.parse(JSON.stringify(source));
  geojson.features.forEach((feature, index) => {
    feature.properties = feature.properties || {};
    feature.properties.kmzIndex = index + 1;
    feature.properties.sourceLayer = "huangkeng";
    if (feature.geometry?.type === "Polygon" && typeof feature.geometry.coordinates?.[0]?.[0] === "number") {
      feature.geometry.coordinates = [feature.geometry.coordinates];
    }
  });
  return geojson;
}

function pointStyle(feature) {
  return new ol.style.Style({
    image: new ol.style.Circle({
      radius: 10,
      fill: new ol.style.Fill({ color: "rgba(255, 238, 89, 0.95)" }),
      stroke: new ol.style.Stroke({ color: "#ffffff", width: 3 }),
    }),
    text: new ol.style.Text({
      text: feature.get("name"),
      offsetY: -24,
      fill: new ol.style.Fill({ color: "#ffffff" }),
      stroke: new ol.style.Stroke({ color: "rgba(0, 0, 0, 0.82)", width: 4 }),
      font: "bold 12px Microsoft YaHei",
    }),
  });
}

function boundaryStyle(feature) {
  const selected = feature === selectedBoundaryFeature;
  const isKang = feature.get("sourceLayer") === "kangVillage";
  const isBackend = feature.get("sourceLayer") === "backendForestBlock";
  const color = isBackend ? "#46d37f" : isKang ? "#ffb13b" : "rgba(115, 255, 244, 0.82)";
  return new ol.style.Style({
    stroke: new ol.style.Stroke({ color: selected ? "#ffee59" : color, width: selected ? 3 : 1.3 }),
    fill: new ol.style.Fill({
      color: selected
        ? "rgba(255, 238, 89, 0.16)"
        : isBackend
          ? "rgba(70, 211, 127, 0.11)"
          : isKang
            ? "rgba(255, 177, 59, 0.1)"
            : "rgba(74, 255, 118, 0.08)",
    }),
  });
}

function makePointLayer() {
  const feature = new ol.Feature({
    geometry: new ol.geom.Point(ol.proj.fromLonLat(realPoint.coord)),
    type: "realPoint",
    name: realPoint.name,
  });
  feature.setStyle(pointStyle(feature));
  return new ol.layer.Vector({ source: new ol.source.Vector({ features: [feature] }) });
}

function makeBoundaryLayer() {
  const geojson = normalizeHuangKengGeojson();
  if (!geojson) return new ol.layer.Vector({ source: new ol.source.Vector() });
  const features = new ol.format.GeoJSON().readFeatures(geojson, { dataProjection: "EPSG:4326", featureProjection: "EPSG:3857" });
  features.forEach((feature) => feature.setStyle(boundaryStyle(feature)));
  return new ol.layer.Vector({ source: new ol.source.Vector({ features }) });
}

function makeKangLayer() {
  if (!window.KANG_VILLAGE_GEOJSON) return new ol.layer.Vector({ source: new ol.source.Vector() });
  const features = new ol.format.GeoJSON().readFeatures(window.KANG_VILLAGE_GEOJSON, {
    dataProjection: "EPSG:4326",
    featureProjection: "EPSG:3857",
  });
  features.forEach((feature) => {
    feature.set("sourceLayer", "kangVillage");
    feature.setStyle(boundaryStyle(feature));
  });
  return new ol.layer.Vector({ source: new ol.source.Vector({ features }), opacity: 0.9 });
}

function makeLiveForestBlockLayer() {
  return new ol.layer.Vector({
    source: new ol.source.Vector(),
    opacity: 0.96,
    style: boundaryStyle,
  });
}

function offlineBaseStyle(feature) {
  const kind = feature.get("kind");
  const itemClass = feature.get("class");
  if (kind === "forest") {
    return new ol.style.Style({
      fill: new ol.style.Fill({ color: "rgba(34, 128, 74, 0.2)" }),
      stroke: new ol.style.Stroke({ color: "rgba(86, 210, 130, 0.2)", width: 1 }),
    });
  }
  if (kind === "landuse") {
    return new ol.style.Style({
      fill: new ol.style.Fill({ color: "rgba(76, 132, 82, 0.12)" }),
      stroke: new ol.style.Stroke({ color: "rgba(120, 196, 136, 0.14)", width: 1 }),
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
  const width = itemClass === "primary" || itemClass === "trunk" ? 3 : itemClass === "secondary" ? 2.2 : 1.3;
  return new ol.style.Style({
    stroke: new ol.style.Stroke({ color: "rgba(212, 231, 202, 0.46)", width }),
  });
}

function makeOfflineBaseLayer() {
  const features = window.FUJIAN_BASEMAP_GEOJSON
    ? new ol.format.GeoJSON().readFeatures(window.FUJIAN_BASEMAP_GEOJSON, {
        dataProjection: "EPSG:4326",
        featureProjection: "EPSG:3857",
      })
    : [];
  return new ol.layer.Vector({
    source: new ol.source.Vector({ features }),
    style: offlineBaseStyle,
  });
}

function restyleBoundaryLayers() {
  [boundaryLayer, kangLayer, liveForestBlockLayer].forEach((layer) => {
    layer?.getSource().getFeatures().forEach((item) => item.setStyle(boundaryStyle(item)));
  });
}

function openBoundaryFeature(feature) {
  selectedBoundaryFeature = feature;
  restyleBoundaryLayers();
  renderBoundaryCard(feature);
  mobileMap.getView().fit(feature.getGeometry().getExtent(), { padding: fitPadding(), maxZoom: 15, duration: 260 });
}

function openBackendForestBlockFeature(feature) {
  selectedBoundaryFeature = feature;
  restyleBoundaryLayers();
  renderBackendForestBlockCard(feature.getProperties());
  mobileMap.getView().fit(feature.getGeometry().getExtent(), { padding: fitPadding(), maxZoom: 15, duration: 260 });
}

function findLoadedBackendFeature(block = {}) {
  const blockCode = String(block.blockCode || "").trim();
  const id = String(block.id || "").trim();
  if (!blockCode && !id) return null;
  return (
    liveForestBlockLayer
      ?.getSource()
      .getFeatures()
      .find((feature) => {
        const p = feature.getProperties();
        return (blockCode && p.blockCode === blockCode) || (id && (p.id === id || feature.getId() === id));
      }) || null
  );
}

function openBackendForestBlockRecord(block = {}) {
  const feature = findLoadedBackendFeature(block);
  if (feature) {
    openBackendForestBlockFeature(feature);
    return;
  }
  selectedBoundaryFeature = null;
  restyleBoundaryLayers();
  renderBackendForestBlockCard(block);
}

function openRealPoint() {
  selectedBoundaryFeature = null;
  restyleBoundaryLayers();
  renderPointCard();
  mobileMap.getView().animate({ center: ol.proj.fromLonLat(realPoint.coord), zoom: 14, duration: 260 });
}

function buildSearchRecords() {
  const records = [
    {
      type: "真实点位",
      title: realPoint.name,
      subtitle: `${realPoint.fields[0][1]} · ${realPoint.code}`,
      keywords: [realPoint.name, realPoint.code, realPoint.level, ...realPoint.fields.flat()].join(" ").toLowerCase(),
      open: openRealPoint,
    },
  ];

  boundaryLayer.getSource().getFeatures().forEach((feature) => {
    const p = feature.getProperties();
    const title = boundaryTitle(p);
    records.push({
      type: "KMZ边界",
      title,
      subtitle: `${p.XBNO || p["挂接"] || ""} · 面积${p["面积"] || p.XBMJ || "-"}亩`,
      keywords: Object.values(p).join(" ").toLowerCase(),
      open: () => openBoundaryFeature(feature),
    });
  });
  kangLayer.getSource().getFeatures().forEach((feature) => {
    const p = feature.getProperties();
    const title = p["名称"] || p.name || `KANG-${p.ovkmlIndex}`;
    records.push({
      type: "康内部分村",
      title,
      subtitle: `${p["日期"] || ""} · 面积${p["面积"] || "-"}`,
      keywords: Object.values(p).join(" ").toLowerCase(),
      open: () => openBoundaryFeature(feature),
    });
  });
  liveForestBlockLayer?.getSource().getFeatures().forEach((feature) => {
    const p = feature.getProperties();
    records.push({
      type: "后台林班",
      title: mobileBlockTitle(p),
      subtitle: `${p.blockCode || p.id || ""} · ${mobileBlockLocation(p) || "后台空间图层"}`,
      keywords: Object.values(p).join(" ").toLowerCase(),
      open: () => openBackendForestBlockFeature(feature),
    });
  });
  searchRecords = records;
}

function renderSearchResultButtons(matches, emptyText = "换一个林班、小班、村镇或地块编号试试") {
  searchResults.innerHTML = matches.length
    ? matches
        .map(
          (record, index) =>
            `<button data-result="${index}"><strong>${escapeMobileHtml(record.title)}</strong><em>${escapeMobileHtml(record.type)}</em><span>${escapeMobileHtml(record.subtitle)}</span></button>`,
        )
        .join("")
    : `<button type="button"><strong>未找到匹配结果</strong><span>${escapeMobileHtml(emptyText)}</span></button>`;
  searchResults.classList.add("open");
  searchResults.querySelectorAll("[data-result]").forEach((button) => {
    button.addEventListener("click", () => {
      matches[Number(button.dataset.result)].open();
      searchResults.classList.remove("open");
    });
  });
}

function uniqueSearchRecords(records) {
  const seen = new Set();
  return records.filter((record) => {
    const key = `${record.type}:${record.title}:${record.subtitle}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function localSearchMatches(q) {
  return searchRecords.filter((record) => record.keywords.includes(q) || record.title.toLowerCase().includes(q));
}

async function loadMobileForestBlockSearch(keyword) {
  const q = keyword.trim();
  if (!q) return [];
  mobileForestBlockSearchController?.abort();
  mobileForestBlockSearchController = new AbortController();
  const params = new URLSearchParams({
    q,
    limit: "20",
    offset: "0",
  });
  const response = await mobileApiFetch(`${MOBILE_REMOTE_API_BASE}/api/forest-blocks?${params.toString()}`, {
    signal: mobileForestBlockSearchController.signal,
  });
  if (!response.ok) throw new Error(`forest block search ${response.status}`);
  const payload = await response.json();
  const items = Array.isArray(payload.items) ? payload.items : [];
  return items.map((block) => ({
    type: "后台林班",
    title: mobileBlockTitle(block),
    subtitle: `${block.blockCode || block.id || ""} · ${mobileBlockLocation(block) || "空间台账"}`,
    keywords: Object.values(block).join(" ").toLowerCase(),
    open: () => openBackendForestBlockRecord(block),
  }));
}

function renderSearchResults(keyword) {
  const q = keyword.trim().toLowerCase();
  if (!q) {
    searchResults.classList.remove("open");
    searchResults.innerHTML = "";
    return;
  }
  const localMatches = localSearchMatches(q).slice(0, 20);
  renderSearchResultButtons(localMatches, localMatches.length ? "正在继续匹配后台林班" : "正在搜索后台林班台账");
  loadMobileForestBlockSearch(keyword)
    .then((remoteMatches) => {
      if (mobileSearch.value.trim().toLowerCase() !== q) return;
      const matches = uniqueSearchRecords([...localSearchMatches(q), ...remoteMatches]).slice(0, 20);
      renderSearchResultButtons(matches);
    })
    .catch((error) => {
      if (error.name === "AbortError") return;
      if (!localMatches.length) renderSearchResultButtons([], "后台林班接口暂不可用，请稍后再试");
      console.warn("mobile forest block search unavailable", error);
    });
}

function renderMobileBusinessDashboard(payload, options = {}) {
  const metrics = Array.isArray(payload.metrics) ? payload.metrics : [];
  const rows = Array.isArray(payload.rows) ? payload.rows : [];
  mobileIndustryTitle.textContent = payload.title || options.title || "业务模块信息卡";
  renderMobileIndustryAdminLinks(payload, options.adminLinks || []);
  mobileIndustryMetrics.innerHTML = metrics.length
    ? metrics
        .map(
          ([label, value]) =>
            `<article><span>${escapeMobileHtml(label)}</span><strong>${escapeMobileHtml(value)}</strong></article>`,
        )
        .join("")
    : `<article><span>后台数据</span><strong>暂无后台数据</strong></article>`;
  mobileIndustryRows.innerHTML = rows.length
    ? rows
        .slice(0, 8)
        .map(
          ([moduleName, recordName, linkedBlock, status]) => `
            <article class="mobile-industry-card">
              <span>${escapeMobileHtml(moduleName)}</span>
              <strong>${escapeMobileHtml(recordName)}</strong>
              <p>${escapeMobileHtml(linkedBlock)} / ${escapeMobileHtml(status)}</p>
            </article>
          `,
        )
        .join("")
    : `<article class="mobile-industry-card"><strong>暂无后台数据</strong><p>${escapeMobileHtml(payload.emptyText || options.emptyText || "请在对应后台台账中新增记录后查看。")}</p></article>`;
  mobileIndustryPanel.classList.remove("hidden");
}

function renderMobileIndustryDashboard(payload) {
  renderMobileBusinessDashboard(payload, {
    title: "产业平台信息卡",
    emptyText: "请在产业平台后台台账中新增记录后查看。",
    adminLinks: MOBILE_INDUSTRY_ADMIN_LINKS,
  });
}

async function loadMobileBusinessDashboard(navKey) {
  const config = MOBILE_BUSINESS_DASHBOARDS[navKey];
  if (!config) return;
  mobileIndustryPanel.classList.remove("hidden");
  mobileIndustryTitle.textContent = config.title;
  renderMobileIndustryAdminLinks({ adminLinks: config.adminLinks }, config.adminLinks);
  mobileIndustryMetrics.innerHTML = `<article><span>后台数据</span><strong>加载中</strong></article>`;
  mobileIndustryRows.innerHTML = `<article class="mobile-industry-card"><strong>正在读取${escapeMobileHtml(config.title)}</strong><p>${escapeMobileHtml(MOBILE_REMOTE_API_BASE)}</p></article>`;
  try {
    const response = await mobileApiFetch(`${MOBILE_REMOTE_API_BASE}${config.endpoint}`);
    if (!response.ok) throw new Error(`${navKey} dashboard ${response.status}`);
    renderMobileBusinessDashboard(await response.json(), config);
  } catch (error) {
    renderMobileBusinessDashboard(
      {
        title: config.title,
        metrics: [["后台数据", "不可用"]],
        rows: [],
        adminLinks: config.adminLinks,
      },
      config,
    );
    mobileIndustryRows.innerHTML = `<article class="mobile-industry-card"><strong>后台接口暂不可用</strong><p>${escapeMobileHtml(error.message)}</p></article>`;
  }
}

async function loadMobileIndustryDashboard() {
  mobileIndustryPanel.classList.remove("hidden");
  mobileIndustryTitle.textContent = "产业平台信息卡";
  mobileIndustryMetrics.innerHTML = `<article><span>后台数据</span><strong>加载中</strong></article>`;
  mobileIndustryRows.innerHTML = `<article class="mobile-industry-card"><strong>正在读取产业平台数据</strong><p>${escapeMobileHtml(MOBILE_REMOTE_API_BASE)}</p></article>`;
  try {
    const response = await mobileApiFetch(`${MOBILE_REMOTE_API_BASE}/api/industry-platform/dashboard`);
    if (!response.ok) throw new Error(`industry dashboard ${response.status}`);
    renderMobileIndustryDashboard(await response.json());
  } catch (error) {
    renderMobileIndustryDashboard({
      title: "产业平台信息卡",
      metrics: [["后台数据", "不可用"]],
      rows: [],
    });
    mobileIndustryRows.innerHTML = `<article class="mobile-industry-card"><strong>后台接口暂不可用</strong><p>${escapeMobileHtml(error.message)}</p></article>`;
  }
}

function mobileMapBboxParam() {
  if (!mobileMap) return "";
  const size = mobileMap.getSize();
  if (!size) return "";
  const extent = mobileMap.getView().calculateExtent(size);
  const bbox = ol.proj.transformExtent(extent, "EPSG:3857", "EPSG:4326");
  return bbox.map((value) => Number(value).toFixed(6)).join(",");
}

async function loadMobileForestBlockLayer() {
  if (!liveForestBlockLayer || !mobileMap) return;
  const params = new URLSearchParams({
    maxFeatures: String(MOBILE_FOREST_BLOCK_MAX_FEATURES),
  });
  const bbox = mobileMapBboxParam();
  if (bbox) params.set("bbox", bbox);
  try {
    const response = await mobileApiFetch(`${MOBILE_REMOTE_API_BASE}/api/map/forest-blocks.geojson?${params.toString()}`);
    if (!response.ok) throw new Error(`forest block layer ${response.status}`);
    const geojson = await response.json();
    const features = new ol.format.GeoJSON().readFeatures(geojson, {
      dataProjection: "EPSG:4326",
      featureProjection: "EPSG:3857",
    });
    features.forEach((feature) => {
      feature.set("sourceLayer", "backendForestBlock");
      feature.setStyle(boundaryStyle(feature));
    });
    liveForestBlockLayer.getSource().clear();
    liveForestBlockLayer.getSource().addFeatures(features);
    buildSearchRecords();
    if (mobileSearch.value.trim()) renderSearchResults(mobileSearch.value);
  } catch (error) {
    console.warn("mobile forest block layer unavailable", error);
  }
}

function scheduleMobileForestBlockLayerLoad() {
  window.clearTimeout(mobileForestBlockLayerTimer);
  mobileForestBlockLayerTimer = window.setTimeout(loadMobileForestBlockLayer, 220);
}

function initMobileGIS() {
  if (!window.ol) return;
  const localBase = new ol.layer.Tile({
    source: new ol.source.XYZ({
      url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      crossOrigin: "anonymous",
      attributions: "© OpenStreetMap contributors",
      maxZoom: 19,
    }),
    opacity: 1,
    visible: true,
  });
  const offlineBase = makeOfflineBaseLayer();
  offlineBase.setVisible(false);
  const imagery = new ol.layer.Tile({
    source: new ol.source.XYZ({
      url: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      crossOrigin: "anonymous",
    }),
    opacity: 0,
    visible: false,
  });
  pointLayer = makePointLayer();
  boundaryLayer = makeBoundaryLayer();
  kangLayer = makeKangLayer();
  liveForestBlockLayer = makeLiveForestBlockLayer();
  mobileLayers.imagery = imagery;
  mobileLayers.points = pointLayer;
  mobileLayers.boundary = boundaryLayer;
  mobileLayers.kangVillage = kangLayer;
  mobileLayers.backendBlocks = liveForestBlockLayer;

  mobileMap = new ol.Map({
    target: "mobileGisMap",
    controls: [],
    layers: [offlineBase, localBase, imagery, boundaryLayer, kangLayer, liveForestBlockLayer, pointLayer],
    view: new ol.View({
      center: ol.proj.fromLonLat([118.2, 26.6]),
      zoom: 9.5,
      minZoom: 8,
      maxZoom: 16,
    }),
  });

  mobileMap.on("singleclick", (event) => {
    const feature = mobileMap.forEachFeatureAtPixel(event.pixel, (item) => item);
    if (!feature) return;
    if (feature.get("type") === "realPoint") {
      openRealPoint();
      return;
    }
    if (feature.get("sourceLayer") === "backendForestBlock") {
      openBackendForestBlockFeature(feature);
      return;
    }
    openBoundaryFeature(feature);
  });

  mobileMap.on("moveend", scheduleMobileForestBlockLayerLoad);

  const extent = ol.extent.createEmpty();
  [boundaryLayer, kangLayer].forEach((layer) => {
    const layerExtent = layer.getSource().getExtent();
    if (layerExtent && !ol.extent.isEmpty(layerExtent)) ol.extent.extend(extent, layerExtent);
  });
  if (!ol.extent.isEmpty(extent)) {
    mobileMap.getView().fit(extent, { padding: fitPadding(), maxZoom: 12 });
  }
  buildSearchRecords();
  loadMobileForestBlockLayer();
  renderPointCard();
}

document.querySelectorAll("[data-mobile-layer]").forEach((input) => {
  input.addEventListener("change", () => {
    const layer = mobileLayers[input.dataset.mobileLayer];
    layer?.setVisible(input.checked);
    if (input.dataset.mobileLayer === "imagery") layer?.setOpacity(input.checked ? 0.92 : 0);
  });
});

document.querySelector("#layerToggle").addEventListener("click", () => {
  layerDrawer.classList.toggle("open");
});

document.querySelector("#navToggle").addEventListener("click", () => {
  const collapsed = mobileNav.classList.toggle("collapsed");
  document.body.classList.toggle("nav-collapsed", collapsed);
  document.querySelector("#navToggle").textContent = collapsed ? "展开" : "菜单";
  document.querySelector("#navToggle").setAttribute("aria-expanded", String(!collapsed));
  window.setTimeout(() => mobileMap?.updateSize(), 80);
});

document.querySelector("#closeLayer").addEventListener("click", () => {
  layerDrawer.classList.remove("open");
});

document.querySelector("#sheetToggle").addEventListener("click", () => {
  const collapsed = plotSheet.classList.toggle("collapsed");
  document.querySelector("#sheetToggle").textContent = collapsed ? "展开" : "收起";
  document.querySelector("#sheetToggle").setAttribute("aria-expanded", String(!collapsed));
});

document.querySelector("#searchClear").addEventListener("click", () => {
  mobileSearch.value = "";
  searchResults.classList.remove("open");
  searchResults.innerHTML = "";
});

mobileSearch.addEventListener("input", () => {
  renderSearchResults(mobileSearch.value);
});

document.querySelectorAll("[data-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    document.querySelector("#tabText").textContent = tabText[button.dataset.tab];
  });
});

document.querySelectorAll("[data-nav]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-nav]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    const navKey = button.dataset.nav;
    if (navKey === "industry") {
      loadMobileIndustryDashboard();
    } else if (MOBILE_BUSINESS_DASHBOARDS[navKey]) {
      loadMobileBusinessDashboard(navKey);
    } else {
      mobileIndustryPanel.classList.add("hidden");
    }
  });
});

document.querySelector("#closeIndustryPanel").addEventListener("click", () => {
  mobileIndustryPanel.classList.add("hidden");
});

updateViewportVars();
loadMobileResourceSummary();
loadMobilePublishedLayers();
window.addEventListener("resize", updateViewportVars);
window.visualViewport?.addEventListener("resize", updateViewportVars);
window.visualViewport?.addEventListener("scroll", updateViewportVars);
initMobileGIS();
