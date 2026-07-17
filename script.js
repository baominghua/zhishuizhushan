const plots = [
  {
    id: "north",
    name: "北坡示范区",
    area: 1260,
    variety: "毛竹 / 雷竹",
    health: 92,
    state: "healthy",
    harvest: "2026-10",
    owner: "林业站 张敏",
    position: { left: "16%", top: "22%" },
    boundaryClass: "boundary-north",
    code: "NP-ZS-BP-001",
    altitude: "486-732m",
    slope: "18°-32°",
    imagery: ["无人机春笋前航拍", "GF-2 卫星底图", "2026 正射影像", "NDVI 长势图"],
  },
  {
    id: "east",
    name: "东岭管护区",
    area: 980,
    variety: "毛竹",
    health: 78,
    state: "warning",
    harvest: "2026-08",
    owner: "合作社 陈伟",
    position: { left: "62%", top: "20%" },
    boundaryClass: "boundary-east",
    code: "NP-ZS-DL-014",
    altitude: "392-618m",
    slope: "12°-27°",
    imagery: ["无人机病虫害巡查", "卫星变化检测", "坡向分析图", "高光谱长势图"],
  },
  {
    id: "south",
    name: "南谷生态区",
    area: 1420,
    variety: "苦竹 / 早竹",
    health: 88,
    state: "healthy",
    harvest: "2027-03",
    owner: "管护队 李岚",
    position: { left: "46%", top: "58%" },
    boundaryClass: "boundary-south",
    code: "NP-ZS-NG-026",
    altitude: "318-566m",
    slope: "9°-24°",
    imagery: ["无人机生态样方", "三维倾斜摄影", "水系缓冲区", "碳汇样方影像"],
  },
  {
    id: "west",
    name: "西坳修复区",
    area: 760,
    variety: "毛竹",
    health: 61,
    state: "danger",
    harvest: "暂缓",
    owner: "生态办 周宁",
    position: { left: "21%", top: "66%" },
    boundaryClass: "boundary-west",
    code: "NP-ZS-XA-009",
    altitude: "524-801m",
    slope: "26°-41°",
    imagery: ["无人机灾害复核", "卫星低湿识别", "坡度风险图", "修复前后对比"],
  },
];

const devices = [
  { plotId: "north", name: "北坡 1 号气象站", status: "在线", soil: "31%", temp: "24.8℃", humidity: "73%", battery: "86%" },
  { plotId: "east", name: "东岭虫情灯", status: "关注", soil: "27%", temp: "26.1℃", humidity: "68%", battery: "54%" },
  { plotId: "south", name: "南谷水位计", status: "在线", soil: "35%", temp: "23.6℃", humidity: "76%", battery: "91%" },
  { plotId: "west", name: "西坳土壤墒情仪", status: "异常", soil: "18%", temp: "27.4℃", humidity: "59%", battery: "42%" },
  { plotId: "north", name: "北坡视频哨兵", status: "在线", soil: "30%", temp: "24.6℃", humidity: "74%", battery: "79%" },
  { plotId: "east", name: "东岭边界摄像机", status: "在线", soil: "28%", temp: "25.7℃", humidity: "69%", battery: "82%" },
];

const events = [
  { plotId: "west", level: "danger", title: "西坳修复区土壤湿度低于阈值", time: "09:42", detail: "已建议开启临时灌溉并安排复测。" },
  { plotId: "east", level: "warning", title: "东岭虫情灯诱捕数量上升", time: "08:50", detail: "较昨日增加 18%，需核查是否扩散。" },
  { plotId: "north", level: "healthy", title: "北坡视频哨兵完成自动巡检", time: "07:35", detail: "未发现越界采伐与火点。" },
  { plotId: "south", level: "healthy", title: "南谷生态区碳汇样方数据回传", time: "06:18", detail: "胸径样本与冠层覆盖率已入库。" },
];

const tasks = [
  { status: "待处理", plotId: "west", title: "复核西坳 4 号墒情点", desc: "携带手持土壤仪，确认低湿是否为设备误差。", priority: "高" },
  { status: "待处理", plotId: "east", title: "东岭虫情灯样本拍照", desc: "上传清晰照片，用于病虫害模型识别。", priority: "中" },
  { status: "处理中", plotId: "north", title: "北坡游步道边界巡查", desc: "核查游客活动是否进入幼竹保护区。", priority: "低" },
  { status: "处理中", plotId: "south", title: "南谷碳汇样方补测", desc: "补采 3 个样方高度与胸径数据。", priority: "中" },
  { status: "已完成", plotId: "north", title: "北坡视频哨兵清洁", desc: "镜头污渍已处理，夜间红外正常。", priority: "低" },
];

const carbonItems = [
  { name: "生态修复增汇", value: "6,830 tCO₂e", percent: 72 },
  { name: "可持续采伐经营", value: "4,960 tCO₂e", percent: 58 },
  { name: "竹产品替代减排", value: "3,420 tCO₂e", percent: 44 },
  { name: "林下经济协同收益", value: "￥286 万", percent: 64 },
];

const mapLayers = [
  { id: "terrain", name: "等高线地形", desc: "坡度、海拔、等高线与山脊线" },
  { id: "landform", name: "地貌分区", desc: "山脊、沟谷、台地、修复斑块" },
  { id: "plots", name: "林班边界", desc: "林班号、小班边界、经营边界" },
  { id: "uav", name: "无人机航拍", desc: "春笋前、病虫害、灾害复核航拍" },
  { id: "satellite", name: "卫星底图", desc: "高分卫星、长势监测、变化检测" },
  { id: "orthophoto", name: "正射影像", desc: "年度正射、倾斜摄影、DOM 底图" },
  { id: "slope", name: "坡度坡向", desc: "坡度分级、坡向、海拔阴影" },
  { id: "ownership", name: "权属经营", desc: "农户、合作社、竹企与集体林权" },
  { id: "buildings", name: "建筑物信息", desc: "管护站、仓储点、加工点、游客中心" },
  { id: "roads", name: "道路路网", desc: "巡护道路、消防通道、生产便道" },
  { id: "water", name: "水系水源", desc: "溪流、蓄水池、灌溉干线" },
  { id: "devices", name: "物联设备", desc: "气象站、摄像机、虫情灯、墒情仪" },
  { id: "risks", name: "预警事件", desc: "病虫害、低湿、火险与越界风险" },
];

const buildings = [
  { id: "station", name: "北坡管护站", type: "建筑物", use: "巡护调度 / 物资补给", staff: "12 人", left: "37%", top: "31%" },
  { id: "warehouse", name: "竹材仓储点", type: "建筑物", use: "竹材分拣 / 临时仓储", staff: "6 人", left: "58%", top: "46%" },
  { id: "center", name: "生态展示中心", type: "建筑物", use: "研学接待 / 数据展示", staff: "9 人", left: "69%", top: "24%" },
  { id: "pump", name: "南谷泵房", type: "建筑物", use: "灌溉控制 / 水压监测", staff: "2 人", left: "48%", top: "72%" },
];

const dispatchState = {
  layers: new Set(mapLayers.map((layer) => layer.id)),
  selected: null,
  zoom: 1,
};

const state = {
  region: "all",
  riskOnly: false,
  query: "",
};

const metricGrid = document.querySelector("#metricGrid");
const terrainMap = document.querySelector("#terrainMap");
const eventTimeline = document.querySelector("#eventTimeline");
const growthChart = document.querySelector("#growthChart");
const riskList = document.querySelector("#riskList");
const riskCountLabel = document.querySelector("#riskCountLabel");
const assetRows = document.querySelector("#assetRows");
const deviceGrid = document.querySelector("#deviceGrid");
const kanbanBoard = document.querySelector("#kanbanBoard");
const carbonBreakdown = document.querySelector("#carbonBreakdown");
const layerList = document.querySelector("#layerList");
const activeLayerCount = document.querySelector("#activeLayerCount");
const dispatchMap = document.querySelector("#dispatchMap");
const dispatchPlots = document.querySelector("#dispatchPlots");
const dispatchDevices = document.querySelector("#dispatchDevices");
const dispatchRisks = document.querySelector("#dispatchRisks");
const selectedObjectType = document.querySelector("#selectedObjectType");
const selectedObjectCard = document.querySelector("#selectedObjectCard");
const dispatchStats = document.querySelector("#dispatchStats");
const bambooInfoCard = document.querySelector("#bambooInfoCard");
const openInfoCard = document.querySelector("#openInfoCard");
const infoCardTitle = document.querySelector("#infoCardTitle");
const infoCardSubTitle = document.querySelector("#infoCardSubTitle");
const infoTableGrid = document.querySelector("#infoTableGrid");
const imageryTabs = document.querySelector("#imageryTabs");
const imageryPanel = document.querySelector("#imageryPanel");
const zoomLabel = document.querySelector("#zoomLabel");
const toast = document.querySelector("#toast");

function getFilteredPlots() {
  return plots.filter((plot) => {
    const regionMatch = state.region === "all" || plot.id === state.region;
    const riskMatch = !state.riskOnly || plot.state !== "healthy";
    const queryMatch = !state.query || `${plot.name}${plot.variety}${plot.owner}`.toLowerCase().includes(state.query);
    return regionMatch && riskMatch && queryMatch;
  });
}

function getFilteredByPlotId(items) {
  const visibleIds = new Set(getFilteredPlots().map((plot) => plot.id));
  return items.filter((item) => visibleIds.has(item.plotId));
}

function renderMetrics() {
  const visible = getFilteredPlots();
  const totalArea = visible.reduce((sum, plot) => sum + plot.area, 0);
  const avgHealth = visible.length ? Math.round(visible.reduce((sum, plot) => sum + plot.health, 0) / visible.length) : 0;
  const visibleDevices = getFilteredByPlotId(devices);
  const online = visibleDevices.filter((device) => device.status === "在线").length;
  const openTasks = getFilteredByPlotId(tasks).filter((task) => task.status !== "已完成").length;
  const metrics = [
    { label: "纳管竹林面积", value: `${totalArea.toLocaleString()} 亩`, trend: "地块数据已同步" },
    { label: "平均健康度", value: `${avgHealth}%`, trend: avgHealth >= 80 ? "长势稳定" : "需重点干预" },
    { label: "物联设备在线", value: `${online}/${visibleDevices.length}`, trend: "分钟级回传" },
    { label: "待办巡护工单", value: openTasks, trend: "按风险自动排序" },
  ];

  metricGrid.innerHTML = metrics
    .map(
      (metric) => `
        <article class="metric-card">
          <span>${metric.label}</span>
          <strong>${metric.value}</strong>
          <p>${metric.trend}</p>
        </article>
      `,
    )
    .join("");
}

function renderMap() {
  terrainMap.innerHTML = getFilteredPlots()
    .map(
      (plot) => `
        <button class="plot" style="left:${plot.position.left};top:${plot.position.top}" data-state="${plot.state}" data-plot="${plot.id}">
          <strong>${plot.name}</strong>
          <span>健康度 ${plot.health}%</span>
        </button>
      `,
    )
    .join("");

  terrainMap.querySelectorAll(".plot").forEach((button) => {
    button.addEventListener("click", () => {
      const plot = plots.find((item) => item.id === button.dataset.plot);
      showToast(`${plot.name}：${plot.area} 亩，${plot.variety}，责任人 ${plot.owner}`);
    });
  });
}

function renderTimeline() {
  eventTimeline.innerHTML = getFilteredByPlotId(events)
    .map(
      (event) => `
        <article class="event">
          <strong>${event.title}</strong>
          <span>${event.time} · ${event.detail}</span>
        </article>
      `,
    )
    .join("");
}

function renderChart() {
  const values = [68, 74, 71, 83, 79, 86, 81];
  const labels = ["06:00", "08:00", "10:00", "12:00", "14:00", "16:00", "18:00"];
  growthChart.innerHTML = values
    .map(
      (value, index) => `
        <div class="bar" title="环境指数 ${value}">
          <i style="height:${value}%"></i>
          <span>${labels[index]}</span>
        </div>
      `,
    )
    .join("");
}

function renderRisks() {
  const risks = getFilteredByPlotId(events).filter((event) => event.level !== "healthy");
  riskCountLabel.textContent = `${risks.length} 项`;
  riskList.innerHTML = risks.length
    ? risks
        .map(
          (risk) => `
            <article class="risk-item">
              <span class="chip ${risk.level}">${risk.level === "danger" ? "高风险" : "需关注"}</span>
              <strong>${risk.title}</strong>
              <p>${risk.detail}</p>
            </article>
          `,
        )
        .join("")
    : `<article class="risk-item"><strong>暂无风险项</strong><p>当前筛选范围内未发现需要处置的预警。</p></article>`;
}

function renderAssets() {
  assetRows.innerHTML = getFilteredPlots()
    .map(
      (plot) => `
        <tr>
          <td>${plot.name}</td>
          <td>${plot.area.toLocaleString()} 亩</td>
          <td>${plot.variety}</td>
          <td><span class="chip ${plot.state === "healthy" ? "good" : plot.state}">${plot.health}%</span></td>
          <td>${plot.harvest}</td>
          <td>${plot.owner}</td>
        </tr>
      `,
    )
    .join("");
}

function renderDevices() {
  deviceGrid.innerHTML = getFilteredByPlotId(devices)
    .map(
      (device) => {
        const statusClass = device.status === "在线" ? "good" : device.status === "关注" ? "warning" : "danger";
        return `
          <article class="device-card">
            <header>
              <h3>${device.name}</h3>
              <span class="chip ${statusClass}">${device.status}</span>
            </header>
            <div class="device-reading">
              <div class="reading"><span>土壤湿度</span><strong>${device.soil}</strong></div>
              <div class="reading"><span>气温</span><strong>${device.temp}</strong></div>
              <div class="reading"><span>空气湿度</span><strong>${device.humidity}</strong></div>
              <div class="reading"><span>电量</span><strong>${device.battery}</strong></div>
            </div>
          </article>
        `;
      },
    )
    .join("");
}

function renderKanban() {
  const columns = ["待处理", "处理中", "已完成"];
  const visibleTasks = getFilteredByPlotId(tasks);
  kanbanBoard.innerHTML = columns
    .map((column) => {
      const columnTasks = visibleTasks.filter((task) => task.status === column);
      return `
        <section class="kanban-column">
          <header>
            <h3>${column}</h3>
            <span>${columnTasks.length}</span>
          </header>
          ${columnTasks
            .map(
              (task) => `
                <article class="task-card">
                  <span class="chip ${task.priority === "高" ? "danger" : task.priority === "中" ? "warning" : "good"}">${task.priority}优先级</span>
                  <strong>${task.title}</strong>
                  <p>${task.desc}</p>
                </article>
              `,
            )
            .join("")}
        </section>
      `;
    })
    .join("");
}

function renderCarbon() {
  carbonBreakdown.innerHTML = carbonItems
    .map(
      (item) => `
        <article class="carbon-item">
          <header>
            <strong>${item.name}</strong>
            <span>${item.value}</span>
          </header>
          <div class="progress"><i style="width:${item.percent}%"></i></div>
        </article>
      `,
    )
    .join("");
}

function renderLayerControls() {
  layerList.innerHTML = mapLayers
    .map(
      (layer) => `
        <label class="layer-toggle">
          <input type="checkbox" data-layer-toggle="${layer.id}" ${dispatchState.layers.has(layer.id) ? "checked" : ""} />
          <span>
            <strong>${layer.name}</strong>
            <span>${layer.desc}</span>
          </span>
        </label>
      `,
    )
    .join("");

  layerList.querySelectorAll("[data-layer-toggle]").forEach((input) => {
    input.addEventListener("change", (event) => {
      const layerId = event.target.dataset.layerToggle;
      if (event.target.checked) {
        dispatchState.layers.add(layerId);
      } else {
        dispatchState.layers.delete(layerId);
      }
      renderDispatchLayers();
    });
  });
}

function renderDispatchLayers() {
  activeLayerCount.textContent = `${dispatchState.layers.size}/${mapLayers.length} 已开启`;
  document.querySelectorAll(".map-layer").forEach((layer) => {
    layer.classList.toggle("hidden", !dispatchState.layers.has(layer.dataset.layer));
  });
}

function renderDispatchBuildings() {
  const buildingLayer = document.querySelector('[data-layer="buildings"]');
  buildingLayer.innerHTML = buildings
    .map(
      (building) => `
        <button class="building" style="left:${building.left};top:${building.top}" data-building="${building.id}">
          ${building.name}
        </button>
      `,
    )
    .join("");

  buildingLayer.querySelectorAll("[data-building]").forEach((button) => {
    button.addEventListener("click", () => {
      const building = buildings.find((item) => item.id === button.dataset.building);
      selectDispatchObject({
        type: building.type,
        name: building.name,
        desc: building.use,
        meta: [
          ["用途", building.use],
          ["值守人员", building.staff],
          ["接入状态", "已接入调度"],
        ],
      });
    });
  });
}

function renderDispatchPlots() {
  dispatchPlots.innerHTML = plots
    .map(
      (plot) => `
        <button class="dispatch-plot ${plot.boundaryClass}" style="left:${plot.position.left};top:${plot.position.top}" data-state="${plot.state}" data-dispatch-plot="${plot.id}">
          <strong>${plot.code}</strong>
          <span>${plot.name}</span>
        </button>
      `,
    )
    .join("");

  dispatchPlots.querySelectorAll("[data-dispatch-plot]").forEach((button) => {
    button.addEventListener("click", () => {
      const plot = plots.find((item) => item.id === button.dataset.dispatchPlot);
      selectDispatchObject({
        type: "林班信息",
        name: plot.name,
        desc: `${plot.variety}，当前健康度 ${plot.health}%。`,
        meta: [
          ["林班编号", plot.code],
          ["经营面积", `${plot.area.toLocaleString()} 亩`],
          ["海拔范围", plot.altitude],
          ["坡度范围", plot.slope],
          ["采伐窗口", plot.harvest],
          ["责任人", plot.owner],
        ],
        plot,
      });
    });
  });
}

function renderDispatchDevices() {
  dispatchDevices.innerHTML = devices
    .map((device, index) => {
      const positions = [
        ["31%", "25%"],
        ["65%", "30%"],
        ["52%", "62%"],
        ["28%", "72%"],
        ["22%", "38%"],
        ["74%", "42%"],
      ];
      const [left, top] = positions[index];
      return `
        <button class="device-pin" style="left:${left};top:${top}" title="${device.name}" data-dispatch-device="${index}">
          ◌
        </button>
      `;
    })
    .join("");

  dispatchDevices.querySelectorAll("[data-dispatch-device]").forEach((button) => {
    button.addEventListener("click", () => {
      const device = devices[Number(button.dataset.dispatchDevice)];
      selectDispatchObject({
        type: "物联设备",
        name: device.name,
        desc: `设备状态：${device.status}。`,
        meta: [
          ["土壤湿度", device.soil],
          ["气温", device.temp],
          ["电量", device.battery],
        ],
      });
    });
  });
}

function renderDispatchRisks() {
  const risks = events.filter((event) => event.level !== "healthy");
  const positions = {
    west: ["30%", "78%"],
    east: ["70%", "28%"],
  };
  dispatchRisks.innerHTML = risks
    .map((risk, index) => {
      const [left, top] = positions[risk.plotId] || ["50%", "50%"];
      return `
        <button class="risk-pin" style="left:${left};top:${top}" title="${risk.title}" data-dispatch-risk="${index}">
          !
        </button>
      `;
    })
    .join("");

  dispatchRisks.querySelectorAll("[data-dispatch-risk]").forEach((button) => {
    button.addEventListener("click", () => {
      const risk = risks[Number(button.dataset.dispatchRisk)];
      selectDispatchObject({
        type: "预警事件",
        name: risk.title,
        desc: risk.detail,
        meta: [
          ["预警等级", risk.level === "danger" ? "高风险" : "需关注"],
          ["发生时间", risk.time],
          ["建议动作", "派发巡护工单"],
        ],
      });
    });
  });
}

function selectDispatchObject(object) {
  dispatchState.selected = object;
  bambooInfoCard?.classList.remove("hidden");
  openInfoCard?.classList.add("hidden");
  infoCardTitle.textContent = object.type === "林班信息" ? "林班电子信息卡" : object.type;
  infoCardSubTitle.textContent = object.type === "林班信息" ? "影像与分等定级因子表" : "空间对象属性表";
  infoTableGrid.innerHTML = object.meta
    .slice(0, 10)
    .map(([label, value]) => `<span>${label}</span><b>${value}</b>`)
    .join("");
  renderImageryTabs(object.plot);
  selectedObjectType.textContent = object.type;
  selectedObjectCard.innerHTML = `
    <strong>${object.name}</strong>
    <p>${object.desc}</p>
    <div class="object-meta">
      ${object.meta.map(([label, value]) => `<span>${label}<b>${value}</b></span>`).join("")}
    </div>
  `;
}

function renderImageryTabs(plot) {
  const imageryItems = plot
    ? [
        { name: "无人机航拍", value: plot.imagery[0], desc: `${plot.name} 低空航拍成果，可用于查看林班边界、竹冠覆盖和道路通达情况。` },
        { name: "卫星底图", value: plot.imagery[1], desc: `${plot.name} 高分辨率卫星底图，用于长势识别、变化检测和区域对比。` },
        { name: "正射影像", value: plot.imagery[2], desc: `${plot.name} 年度正射影像，支持林班边界校核、面积量算和地块存档。` },
        { name: "专题影像", value: plot.imagery[3], desc: `${plot.name} 专题遥感成果，结合 NDVI、坡度坡向、灾害复核等指标。` },
      ]
    : [
        { name: "无人机航拍", value: "林班低空航拍", desc: "点击地图上的林班边界后展示对应地块航拍资料。" },
        { name: "卫星底图", value: "卫星遥感底图", desc: "用于查看竹山整体空间格局和年度变化。" },
      ];

  imageryTabs.innerHTML = imageryItems
    .map((item, index) => `<button class="${index === 0 ? "active" : ""}" data-imagery-index="${index}">${item.name}</button>`)
    .join("");

  function renderPanel(index) {
    const item = imageryItems[index];
    imageryPanel.innerHTML = `
      <div class="imagery-preview">
        <span>${item.name}</span>
      </div>
      <div>
        <strong>${item.value}</strong>
        <p>${item.desc}</p>
      </div>
    `;
  }

  imageryTabs.querySelectorAll("[data-imagery-index]").forEach((button) => {
    button.addEventListener("click", () => {
      imageryTabs.querySelectorAll("button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      renderPanel(Number(button.dataset.imageryIndex));
    });
  });

  renderPanel(0);
}

function renderDispatchStats() {
  const stats = [
    ["地形地貌图层", "2 类"],
    ["建筑物对象", `${buildings.length} 个`],
    ["物联设备点位", `${devices.length} 个`],
    ["实时预警", `${events.filter((event) => event.level !== "healthy").length} 项`],
  ];

  dispatchStats.innerHTML = stats
    .map(
      ([label, value]) => `
        <article class="dispatch-stat">
          <span>${label}</span>
          <strong>${value}</strong>
        </article>
      `,
    )
    .join("");
}

function renderDispatchCenter() {
  renderLayerControls();
  renderDispatchBuildings();
  renderDispatchPlots();
  renderDispatchDevices();
  renderDispatchRisks();
  renderDispatchLayers();
  renderDispatchStats();
  applyMapZoom();
}

function renderAll() {
  renderMetrics();
  renderMap();
  renderTimeline();
  renderChart();
  renderRisks();
  renderAssets();
  renderDevices();
  renderKanban();
  renderCarbon();
  renderDispatchCenter();
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}

function applyMapZoom() {
  const percent = Math.round(dispatchState.zoom * 100);
  document.body.style.setProperty("--map-zoom", dispatchState.zoom);
  document.body.style.setProperty("--map-bg-size", `${Math.round(dispatchState.zoom * 160)}%`);
  zoomLabel.textContent = `${percent}%`;
}

function changeMapZoom(delta) {
  dispatchState.zoom = Math.min(1.8, Math.max(0.72, Number((dispatchState.zoom + delta).toFixed(2))));
  applyMapZoom();
}

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-view]").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#${button.dataset.view}`).classList.add("active");
  });
});

document.querySelectorAll("[data-view-target]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector(`[data-view="${button.dataset.viewTarget}"]`).click();
  });
});

document.querySelector("#regionFilter").addEventListener("change", (event) => {
  state.region = event.target.value;
  renderAll();
});

document.querySelector("#riskOnly").addEventListener("change", (event) => {
  state.riskOnly = event.target.checked;
  renderAll();
});

document.querySelector("#globalSearch").addEventListener("input", (event) => {
  state.query = event.target.value.trim().toLowerCase();
  renderAll();
});

document.querySelector("#refreshBtn").addEventListener("click", () => {
  showToast("数据已刷新，最新监测时间 10:18");
});

document.querySelector("#newTaskBtn").addEventListener("click", () => {
  document.querySelector('[data-view="patrol"]').click();
  showToast("已打开巡护工单，可继续派发任务");
});

document.querySelector("#resetLayersBtn")?.addEventListener("click", () => {
  dispatchState.layers = new Set(mapLayers.map((layer) => layer.id));
  renderDispatchCenter();
  showToast("地图图层已全部开启");
});

document.querySelector("#dispatchTaskBtn")?.addEventListener("click", () => {
  document.querySelector('[data-view="patrol"]').click();
  showToast("已根据当前预警生成调度派单入口");
});

document.querySelector("#closeInfoCard").addEventListener("click", () => {
  bambooInfoCard.classList.add("hidden");
  openInfoCard.classList.remove("hidden");
});

openInfoCard.addEventListener("click", () => {
  bambooInfoCard.classList.remove("hidden");
  openInfoCard.classList.add("hidden");
});

document.querySelector("#toggleLayerPanel").addEventListener("click", () => {
  document.querySelector(".layer-panel").classList.toggle("collapsed");
});

document.querySelector("#zoomInBtn").addEventListener("click", () => changeMapZoom(0.12));

document.querySelector("#zoomOutBtn").addEventListener("click", () => changeMapZoom(-0.12));

dispatchMap.addEventListener("wheel", (event) => {
  event.preventDefault();
  changeMapZoom(event.deltaY < 0 ? 0.08 : -0.08);
});

document.querySelectorAll("[data-map-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-map-mode]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    dispatchMap.classList.remove("standard", "terrain", "satellite");
    dispatchMap.classList.add(button.dataset.mapMode);
  });
});

renderAll();
