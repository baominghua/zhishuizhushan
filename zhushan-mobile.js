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
const searchResults = document.querySelector("#searchResults");

let mobileMap = null;
let pointLayer = null;
let boundaryLayer = null;
let kangLayer = null;
let selectedBoundaryFeature = null;
let searchRecords = [];
const mobileLayers = {};

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
  plotFields.innerHTML = fields.map(([label, value]) => `<article><span>${label}</span><strong>${value || "-"}</strong></article>`).join("");
  plotSheet.classList.remove("collapsed");
  document.querySelector("#sheetToggle").textContent = "收起";
  document.querySelector("#sheetToggle").setAttribute("aria-expanded", "true");
}

function renderPointCard() {
  renderCard(realPoint.name, realPoint.code, realPoint.level, realPoint.fields);
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
  const color = isKang ? "#ffb13b" : "rgba(115, 255, 244, 0.82)";
  return new ol.style.Style({
    stroke: new ol.style.Stroke({ color: selected ? "#ffee59" : color, width: selected ? 3 : 1.3 }),
    fill: new ol.style.Fill({ color: selected ? "rgba(255, 238, 89, 0.16)" : isKang ? "rgba(255, 177, 59, 0.1)" : "rgba(74, 255, 118, 0.08)" }),
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

function openBoundaryFeature(feature) {
  selectedBoundaryFeature = feature;
  boundaryLayer?.getSource().getFeatures().forEach((item) => item.setStyle(boundaryStyle(item)));
  kangLayer?.getSource().getFeatures().forEach((item) => item.setStyle(boundaryStyle(item)));
  renderBoundaryCard(feature);
  mobileMap.getView().fit(feature.getGeometry().getExtent(), { padding: fitPadding(), maxZoom: 15, duration: 260 });
}

function openRealPoint() {
  selectedBoundaryFeature = null;
  boundaryLayer?.getSource().getFeatures().forEach((item) => item.setStyle(boundaryStyle(item)));
  kangLayer?.getSource().getFeatures().forEach((item) => item.setStyle(boundaryStyle(item)));
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
  searchRecords = records;
}

function renderSearchResults(keyword) {
  const q = keyword.trim().toLowerCase();
  if (!q) {
    searchResults.classList.remove("open");
    searchResults.innerHTML = "";
    return;
  }
  const matches = searchRecords.filter((record) => record.keywords.includes(q) || record.title.toLowerCase().includes(q)).slice(0, 20);
  searchResults.innerHTML = matches.length
    ? matches.map((record, index) => `<button data-result="${index}"><strong>${record.title}</strong><em>${record.type}</em><span>${record.subtitle}</span></button>`).join("")
    : `<button type="button"><strong>未找到匹配结果</strong><span>换一个林班、小班、村镇或地块编号试试</span></button>`;
  searchResults.classList.add("open");
  searchResults.querySelectorAll("[data-result]").forEach((button) => {
    button.addEventListener("click", () => {
      matches[Number(button.dataset.result)].open();
      searchResults.classList.remove("open");
    });
  });
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
  mobileLayers.imagery = imagery;
  mobileLayers.points = pointLayer;
  mobileLayers.boundary = boundaryLayer;
  mobileLayers.kangVillage = kangLayer;

  mobileMap = new ol.Map({
    target: "mobileGisMap",
    controls: [],
    layers: [offlineBase, localBase, imagery, boundaryLayer, kangLayer, pointLayer],
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
    openBoundaryFeature(feature);
  });

  const extent = ol.extent.createEmpty();
  [boundaryLayer, kangLayer].forEach((layer) => {
    const layerExtent = layer.getSource().getExtent();
    if (layerExtent && !ol.extent.isEmpty(layerExtent)) ol.extent.extend(extent, layerExtent);
  });
  if (!ol.extent.isEmpty(extent)) {
    mobileMap.getView().fit(extent, { padding: fitPadding(), maxZoom: 12 });
  }
  buildSearchRecords();
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
  });
});

updateViewportVars();
window.addEventListener("resize", updateViewportVars);
window.visualViewport?.addEventListener("resize", updateViewportVars);
window.visualViewport?.addEventListener("scroll", updateViewportVars);
initMobileGIS();
