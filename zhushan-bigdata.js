const blocks = [
  {
    id: "bp-001",
    code: "BP-001",
    name: "北坡示范林班",
    className: "good",
    left: "31%",
    top: "34%",
    center: [118.05, 26.72],
    area: "1260 亩",
    variety: "毛竹 / 雷竹",
    level: "优质",
    owner: "北坡合作社",
    altitude: "486-732m",
    slope: "18°-32°",
    health: "92%",
    images: [
      ["无人机航拍", "2026 春笋前无人机航拍", "查看竹冠覆盖、作业道路、林班边界和采伐窗口。"],
      ["卫星底图", "GF-2 高分卫星底图", "用于年度长势对比、变化检测和区域空间格局分析。"],
      ["正射影像", "2026 年度 DOM 正射影像", "支持面积量算、边界核验和竹林档案归档。"],
      ["专题影像", "NDVI 长势专题图", "用于识别高长势区、弱长势区和补植提升区。"],
    ],
  },
  {
    id: "dl-014",
    code: "DL-014",
    name: "东岭管护林班",
    className: "medium",
    left: "58%",
    top: "30%",
    center: [118.34, 26.78],
    area: "980 亩",
    variety: "毛竹",
    level: "中等",
    owner: "东岭管护队",
    altitude: "392-618m",
    slope: "12°-27°",
    health: "78%",
    images: [
      ["无人机航拍", "病虫害巡查航拍", "查看虫情灯周边、竹冠缺损和疑似扩散路径。"],
      ["卫星底图", "卫星变化检测底图", "用于对比近 30 天长势变化和裸地区域。"],
      ["正射影像", "东岭 5cm 正射影像", "用于道路、沟谷与林班边界精细判读。"],
      ["专题影像", "病虫害风险专题图", "叠加虫情、湿度、坡向和历史病害数据。"],
    ],
  },
  {
    id: "ng-026",
    code: "NG-026",
    name: "南谷生态林班",
    className: "good",
    left: "50%",
    top: "58%",
    center: [118.22, 26.52],
    area: "1420 亩",
    variety: "苦竹 / 早竹",
    level: "优质",
    owner: "南谷生态办",
    altitude: "318-566m",
    slope: "9°-24°",
    health: "88%",
    images: [
      ["无人机航拍", "生态样方无人机航拍", "查看样方分布、林下植被和水源缓冲区。"],
      ["卫星底图", "碳汇样方卫星底图", "用于碳汇估算、林分密度和冠层覆盖率分析。"],
      ["正射影像", "倾斜摄影实景底图", "支持三维地形、沟谷和建筑物空间核验。"],
      ["专题影像", "碳汇经营专题图", "叠加样方、胸径、冠层覆盖率和固碳估算。"],
    ],
  },
  {
    id: "xa-009",
    code: "XA-009",
    name: "西坳修复林班",
    className: "warning",
    left: "35%",
    top: "67%",
    center: [117.96, 26.42],
    area: "760 亩",
    variety: "毛竹",
    level: "改造提升",
    owner: "西坳修复专班",
    altitude: "524-801m",
    slope: "26°-41°",
    health: "61%",
    images: [
      ["无人机航拍", "灾害复核无人机影像", "查看低湿、坡面侵蚀和修复作业范围。"],
      ["卫星底图", "低湿识别卫星底图", "用于判断修复前后植被恢复趋势。"],
      ["正射影像", "修复前后正射对比", "支持面积复核、边界修正和补植计划制定。"],
      ["专题影像", "坡度风险专题图", "叠加坡度、墒情、道路通达和水源距离。"],
    ],
  },
  {
    id: "hb-032",
    code: "HB-032",
    name: "湖边经营林班",
    className: "danger",
    left: "65%",
    top: "62%",
    center: [118.42, 26.46],
    area: "540 亩",
    variety: "雷竹",
    level: "病虫害预警",
    owner: "湖边镇林业站",
    altitude: "286-511m",
    slope: "8°-21°",
    health: "57%",
    images: [
      ["无人机航拍", "虫害复核航拍", "定位疑似虫害斑块、道路入口和处置路线。"],
      ["卫星底图", "预警斑块卫星底图", "识别异常变色区域和周边扩散风险。"],
      ["正射影像", "湖边林班正射影像", "核验小班边界、村道和作业通道。"],
      ["专题影像", "虫害等级专题图", "叠加诱捕数量、历史虫害和林班健康度。"],
    ],
  },
];

const businessData = {
  farmer: {
    title: "竹农信息卡",
    subtitle: "主体档案、承包林班与作业记录",
    metrics: [["竹农总数", "1,286 户"], ["绑定林班", "342 个"], ["本月作业", "518 次"]],
    columns: ["姓名", "所属村镇", "关联林班", "近期任务"],
    rows: [
      ["陈顺序", "芳亭村", "BP-001", "春笋前巡护"],
      ["李建华", "湖边镇", "HB-032", "虫害复核"],
      ["周立明", "南谷片区", "NG-026", "碳汇样方补测"],
    ],
  },
  cooperative: {
    title: "合作社信息卡",
    subtitle: "合作社经营、服务能力与订单协同",
    metrics: [["合作社", "46 家"], ["服务面积", "4.8 万亩"], ["活跃订单", "126 单"]],
    columns: ["合作社", "服务范围", "成员数", "经营状态"],
    rows: [
      ["北坡竹业合作社", "北坡示范区", "186 人", "正常"],
      ["东岭联营合作社", "东岭管护区", "142 人", "虫害处置中"],
      ["南谷生态合作社", "南谷生态区", "203 人", "碳汇核算中"],
    ],
  },
  enterprise: {
    title: "竹企信息卡",
    subtitle: "加工企业、仓储流转与产销对接",
    metrics: [["竹企数量", "32 家"], ["年加工能力", "18.6 万吨"], ["在途批次", "74 批"]],
    columns: ["企业名称", "主营方向", "对接林班", "库存状态"],
    rows: [
      ["竹山新材有限公司", "竹板材", "BP-001", "库存充足"],
      ["南平竹制品厂", "日用品", "DL-014", "待入库"],
      ["绿源竹加工中心", "鲜笋加工", "NG-026", "生产中"],
    ],
  },
  plant: {
    title: "植保信息卡",
    subtitle: "病虫害、处置工单与防治进度",
    metrics: [["预警事件", "12 项"], ["处置完成率", "78%"], ["重点林班", "5 个"]],
    columns: ["林班", "问题类型", "等级", "处置建议"],
    rows: [
      ["HB-032", "竹螟风险", "高", "无人机喷防复核"],
      ["DL-014", "虫情灯异常", "中", "样本拍照上传"],
      ["XA-009", "低湿胁迫", "中", "补水与复测"],
    ],
  },
  material: {
    title: "农资信息卡",
    subtitle: "肥料、药剂、工具与领用记录",
    metrics: [["农资品类", "86 类"], ["本月领用", "312 次"], ["库存预警", "9 项"]],
    columns: ["物资名称", "库存", "适用环节", "状态"],
    rows: [
      ["有机复合肥", "28.6 吨", "竹林提升", "正常"],
      ["生物防治药剂", "420 瓶", "病虫害防控", "偏低"],
      ["手持墒情仪", "18 台", "巡护复测", "正常"],
    ],
  },
  policy: {
    title: "政策法规信息卡",
    subtitle: "补贴政策、采伐规范与生态保护要求",
    metrics: [["政策文件", "64 份"], ["可申报事项", "18 项"], ["待审核", "23 件"]],
    columns: ["政策名称", "适用对象", "申报状态", "截止时间"],
    rows: [
      ["退化竹林改造补助", "竹农/合作社", "可申报", "2026-09-30"],
      ["生态公益林保护", "经营主体", "审核中", "2026-08-15"],
      ["竹产品加工奖补", "竹企", "可申报", "2026-10-20"],
    ],
  },
};

const leftToolData = {
  search: {
    title: "竹山搜索结果",
    subtitle: "林班、权属、地块与影像资料一体检索",
    searchable: true,
    placeholder: "输入林班名称、编号、镇村、图层类型",
    metrics: [["可检索林班", "486 个"], ["权属档案", "1,286 份"], ["影像资料", "312 组"]],
    columns: ["检索对象", "匹配位置", "关联图层", "状态"],
    rows: [
      ["小桥上屯竹林", "建瓯市小桥镇上屯村", "导入点位 / 林权经营权", "已入库"],
      ["麻沙黄坑竹山", "麻沙镇黄坑片区", "KMZ 边界 / 竹林林班", "已叠加"],
      ["北坡示范林班", "北坡示范区", "无人机航拍 / 质量等级", "可查看"],
      ["东岭管护林班", "东岭管护区", "长势监测 / 病虫害", "可查看"],
      ["南谷生态林班", "南谷生态区", "碳汇服务 / 卫星底图", "核算中"],
      ["西坳修复林班", "西坳修复片区", "地形地貌 / 历史影像", "改造中"],
      ["湖边经营林班", "湖边镇林业站", "病虫害 / 卫星底图", "预警中"],
    ],
  },
  carbon: {
    title: "碳汇服务图",
    subtitle: "竹林碳汇样方、固碳测算与经营提升服务",
    metrics: [["样方数量", "96 个"], ["估算碳储量", "18.7 万 tCO2e"], ["可开发面积", "2.36 万亩"]],
    columns: ["碳汇单元", "监测方式", "年度固碳量", "服务建议"],
    rows: [
      ["南谷生态样方", "卫星 NDVI + 样方复测", "4,260 tCO2e", "纳入碳汇开发储备"],
      ["北坡优质竹林", "无人机冠层识别", "3,180 tCO2e", "提升密度与抚育强度"],
      ["黄坑连片竹山", "KMZ 边界 + 实景底图", "6,940 tCO2e", "开展连片核算"],
      ["西坳修复林班", "坡度风险 + 长势恢复", "980 tCO2e", "先修复后入库"],
    ],
  },
  satelliteTrack: {
    title: "卫星轨道图",
    subtitle: "卫星过境、影像接收与林班变化监测计划",
    metrics: [["今日过境", "7 轨"], ["可用影像", "23 景"], ["变化预警", "12 处"]],
    columns: ["卫星/载荷", "过境窗口", "覆盖区域", "任务内容"],
    rows: [
      ["GF-2 PMS", "09:42-09:49", "建瓯小桥、麻沙黄坑", "高分底图更新"],
      ["Sentinel-2 MSI", "11:16-11:24", "南平北部竹林带", "NDVI 长势反演"],
      ["吉林一号", "14:08-14:14", "北坡、湖边重点林班", "病虫害斑块复核"],
      ["资源三号", "16:31-16:40", "山体地貌与道路廊道", "三维地形修正"],
    ],
  },
};

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
const businessMetrics = document.querySelector("#businessMetrics");
const businessHead = document.querySelector("#businessHead");
const businessRows = document.querySelector("#businessRows");
const layerCard = document.querySelector("#layerCard");

let zoom = 1;
let gisMap = null;
let activeBusinessData = null;
let activeRenderedRows = [];
let activeRowLocators = [];
const gisLayers = {};
const baseSources = {};

function localMapExtent() {
  return ol.proj.transformExtent([117.55, 26.15, 118.88, 27.18], "EPSG:4326", "EPSG:3857");
}

function renderBlocks() {
  forestBlocks.innerHTML = blocks
    .map(
      (block) => `
        <button class="forest-block ${block.className}" style="left:${block.left};top:${block.top}" data-block="${block.id}">
          <strong>${block.code}</strong>
          <span>${block.name}</span>
        </button>
      `,
    )
    .join("");

  forestBlocks.querySelectorAll("[data-block]").forEach((button) => {
    button.addEventListener("click", () => {
      const block = blocks.find((item) => item.id === button.dataset.block);
      openBlockCard(block);
    });
  });
}

function polygonAround([lon, lat], width, height) {
  const skew = width * 0.28;
  return [
    [
      [lon - width, lat + height * 0.25],
      [lon - width * 0.35, lat + height],
      [lon + width * 0.55, lat + height * 0.76],
      [lon + width, lat + height * 0.08],
      [lon + width * 0.62, lat - height],
      [lon - width * 0.5, lat - height * 0.72],
      [lon - width - skew, lat - height * 0.12],
      [lon - width, lat + height * 0.25],
    ],
  ];
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

  const blockFeatures = blocks.map((block, index) => {
    const feature = new ol.Feature({
      geometry: new ol.geom.Polygon(polygonAround(block.center, 0.045 + index * 0.003, 0.032 + index * 0.002)).transform("EPSG:4326", "EPSG:3857"),
      blockId: block.id,
      layerType: "bamboo",
    });
    feature.setStyle(blockStyle(block));
    return feature;
  });

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
    source: new ol.source.Vector({ features: blockFeatures }),
  });

  gisLayers.quality = createPointLayer("quality", [
    [118.13, 26.66, "#fff05a"],
    [118.31, 26.62, "#ff9d30"],
    [118.42, 26.45, "#ff4949"],
  ]);
  gisLayers.soil = createLineLayer("soil", "#ffe078", [[117.94, 26.46], [118.08, 26.58], [118.23, 26.7], [118.41, 26.81]]);
  gisLayers.growth = createLineLayer("growth", "#58ffa8", [[117.98, 26.72], [118.14, 26.67], [118.32, 26.55], [118.47, 26.48]]);
  gisLayers.yield = createPointLayer("yield", [
    [118.0, 26.41, "#ffc438"],
    [118.2, 26.5, "#ffc438"],
    [118.38, 26.74, "#ffc438"],
  ]);
  gisLayers.pest = createPointLayer("pest", [
    [118.42, 26.46, "#ff2a2a"],
    [118.34, 26.78, "#ff2a2a"],
  ]);
  gisLayers.ownership = createLineLayer("ownership", "#ffffff", [[117.9, 26.6], [118.1, 26.54], [118.27, 26.63], [118.5, 26.58]]);
  gisLayers.farmer = createPointLayer("farmer", [[118.12, 26.51, "#ffffff"]]);
  gisLayers.cooperative = createPointLayer("cooperative", [[118.29, 26.67, "#70ebff"]]);
  gisLayers.uav = createPointLayer("uav", [[118.2, 26.63, "#82ffff"]], 13);
  gisLayers.huangkeng = createHuangKengLayer();
  gisLayers.kangVillage = createKangVillageLayer();
  gisLayers.ovobj = createImportedObjectLayer();
  gisLayers.history = createOverlayLayer("history", "rgba(15, 61, 60, 0.24)");

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
      gisLayers.bamboo,
    ],
    view: new ol.View({
      center: ol.proj.fromLonLat([118.2, 26.6]),
      zoom: 10,
      minZoom: 8,
      maxZoom: 16,
    }),
  });

  gisMap.on("singleclick", (event) => {
    const feature = gisMap.forEachFeatureAtPixel(event.pixel, (item) => item);
    if (!feature) return;
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
    if (!feature?.get("blockId")) return;
    const block = blocks.find((item) => item.id === feature.get("blockId"));
    openBlockCard(block);
  });

  gisMap.on("pointermove", (event) => {
    const hit = gisMap.hasFeatureAtPixel(event.pixel);
    gisMap.getTargetElement().style.cursor = hit ? "pointer" : "";
  });

  const fitExtent = ol.extent.createEmpty();
  [gisLayers.huangkeng, gisLayers.kangVillage].forEach((layer) => {
    const extent = layer?.getSource().getExtent();
    if (extent && !ol.extent.isEmpty(extent)) ol.extent.extend(fitExtent, extent);
  });
  if (!ol.extent.isEmpty(fitExtent)) {
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
  return new ol.layer.Vector({ source: new ol.source.Vector({ features: [feature] }) });
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
  if (gisLayers.offlineBase) {
    gisLayers.offlineBase.setVisible(mode === "terrain3d");
    gisLayers.offlineBase.setOpacity(mode === "terrain3d" ? 0.42 : 0.58);
  }
  if (gisLayers.localBase) {
    gisLayers.localBase.setVisible(mode !== "imagery");
    gisLayers.localBase.setOpacity(mode === "terrain3d" ? 0.86 : 1);
  }
  if (gisLayers.satellite) {
    gisLayers.satellite.setSource(baseSources.imagery);
    gisLayers.satellite.setVisible(mode === "imagery");
    gisLayers.satellite.setOpacity(mode === "imagery" ? 0.92 : 0);
  }
  if (gisLayers.hillshade) {
    gisLayers.hillshade.setOpacity(0);
  }

  document.body.classList.toggle("terrain3d-mode", mode === "terrain3d");
  document.body.classList.toggle("imagery-mode", mode === "imagery");
  document.body.classList.toggle("standard-mode", mode === "standard");
}

function createPointLayer(layerType, points, radius = 9) {
  return new ol.layer.Vector({
    source: new ol.source.Vector({
      features: points.map(([lon, lat, color]) => {
        const feature = new ol.Feature({
          geometry: new ol.geom.Point(ol.proj.fromLonLat([lon, lat])),
          layerType,
        });
        feature.setStyle(
          new ol.style.Style({
            image: new ol.style.Circle({
              radius,
              fill: new ol.style.Fill({ color: color || "#6ffdf5" }),
              stroke: new ol.style.Stroke({ color: "#efffff", width: 2 }),
            }),
          }),
        );
        return feature;
      }),
    }),
  });
}

function createLineLayer(layerType, color, coordinates) {
  const feature = new ol.Feature({
    geometry: new ol.geom.LineString(coordinates).transform("EPSG:4326", "EPSG:3857"),
    layerType,
  });
  feature.setStyle(new ol.style.Style({ stroke: new ol.style.Stroke({ color, width: 3 }) }));
  return new ol.layer.Vector({ source: new ol.source.Vector({ features: [feature] }) });
}

function createOverlayLayer(layerType, color) {
  const feature = new ol.Feature({
    geometry: new ol.geom.Polygon([
      [
        ol.proj.fromLonLat([117.84, 26.34]),
        ol.proj.fromLonLat([118.56, 26.34]),
        ol.proj.fromLonLat([118.56, 26.9]),
        ol.proj.fromLonLat([117.84, 26.9]),
        ol.proj.fromLonLat([117.84, 26.34]),
      ],
    ]),
    layerType,
  });
  feature.setStyle(new ol.style.Style({ fill: new ol.style.Fill({ color }) }));
  return new ol.layer.Vector({ source: new ol.source.Vector({ features: [feature] }), visible: false });
}

function openBlockCard(block) {
  cardTitle.textContent = "林班电子信息卡";
  cardSubtitle.textContent = `${block.name} · 影像信息`;
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

  imageTabs.innerHTML = block.images
    .map(([name], index) => `<button class="${index === 0 ? "active" : ""}" data-image="${index}">${name}</button>`)
    .join("");

  function renderImage(index) {
    const [name, title, desc] = block.images[index];
    imagePanel.innerHTML = `
      <div class="preview">${name}</div>
      <div>
        <strong>${title}</strong>
        <p>${desc}</p>
      </div>
    `;
  }

  imageTabs.querySelectorAll("[data-image]").forEach((button) => {
    button.addEventListener("click", () => {
      imageTabs.querySelectorAll("button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      renderImage(Number(button.dataset.image));
    });
  });

  renderImage(0);
  infoCard.classList.remove("hidden");
  businessCard.classList.add("hidden");
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
  if (!tokens.length) return { rows: leftToolData.search.rows, locators: leftToolData.search.rows.map(() => null) };

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

function renderBusinessRows(data, rows = data.rows, locators = []) {
  activeRenderedRows = rows;
  activeRowLocators = locators;
  if (rows.length === 0) {
    businessRows.innerHTML = `<tr><td colspan="${data.columns.length}">未检索到匹配林班</td></tr>`;
    return;
  }
  businessRows.innerHTML = rows
    .map((row, index) => `<tr data-row-index="${index}">${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("");
}

function openBusinessCard(key) {
  const data = businessData[key] || leftToolData[key];
  if (!data) return;
  activeBusinessData = data;
  businessTitle.textContent = data.title;
  businessSubtitle.textContent = data.subtitle;
  businessMetrics.innerHTML = `
    ${data.metrics.map(([label, value]) => `<article><span>${label}</span><strong>${value}</strong></article>`).join("")}
    ${
      data.searchable
        ? `<label class="business-search"><span>林班搜索</span><input id="forestSearchInput" type="search" placeholder="${data.placeholder}" autocomplete="off" /></label>`
        : ""
    }
  `;
  businessHead.innerHTML = `<tr>${data.columns.map((column) => `<th>${column}</th>`).join("")}</tr>`;
  renderBusinessRows(data);
  businessCard.classList.remove("hidden");
  infoCard.classList.add("hidden");

  if (data.searchable) {
    const searchInput = document.querySelector("#forestSearchInput");
    searchInput?.focus();
    searchInput?.addEventListener("input", () => {
      const keyword = searchInput.value.trim().toLowerCase();
      if (data === leftToolData.search) {
        const result = buildLayerSearchRows(keyword);
        renderBusinessRows(data, result.rows, result.locators);
        return;
      }
      const rows = keyword
        ? data.rows.filter((row) => row.some((cell) => String(cell).toLowerCase().includes(keyword)))
        : data.rows;
      renderBusinessRows(data, rows);
    });
  }
}

function setZoom(nextZoom) {
  zoom = Math.min(1.8, Math.max(0.72, Number(nextZoom.toFixed(2))));
  document.documentElement.style.setProperty("--zoom", zoom);
  document.documentElement.style.setProperty("--bg-size", `${Math.round(zoom * 160)}%`);
  zoomValue.textContent = `${Math.round(zoom * 100)}%`;
  if (gisMap) {
    gisMap.getView().animate({ zoom: 10 + (zoom - 1) * 4, duration: 160 });
  }
}

document.querySelectorAll("[data-layer]").forEach((input) => {
  input.addEventListener("change", () => {
    document.querySelector(`[data-map-layer="${input.dataset.layer}"]`)?.classList.toggle("hidden", !input.checked);
    gisLayers[input.dataset.layer]?.setVisible(input.checked);
  });
});

document.querySelector("#zoomIn").addEventListener("click", () => setZoom(zoom + 0.12));
document.querySelector("#zoomOut").addEventListener("click", () => setZoom(zoom - 0.12));

document.querySelectorAll("[data-basemap]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-basemap]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    setBasemapMode(button.dataset.basemap);
  });
});

scene.addEventListener("wheel", (event) => {
  event.preventDefault();
  setZoom(zoom + (event.deltaY < 0 ? 0.08 : -0.08));
});

window.addEventListener("resize", () => {
  gisMap?.updateSize();
});

closeCard.addEventListener("click", () => infoCard.classList.add("hidden"));

document.querySelector("#closeBusinessCard").addEventListener("click", () => businessCard.classList.add("hidden"));

businessRows.addEventListener("click", (event) => {
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
initWebGIS();
setBasemapMode("standard");
setZoom(1);
