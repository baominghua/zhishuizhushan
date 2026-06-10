const SDK = window.RemoteSensingSDK;
const DEFAULT_API_BASE = window.location.port === "8010" ? window.location.origin : "http://127.0.0.1:8010";
const LOCAL_CONFIG = window.SATELLITE_CONFIG || {};
const DEFAULT_TIANDITU_TK = LOCAL_CONFIG.tiandituTk || "";
const DEFAULT_TIANDITU_TYPE = LOCAL_CONFIG.tiandituType || "img";

const state = {
  catalog: null,
  remote: null,
  remoteOnline: false,
  map: null,
  layers: null,
  basemapLayers: [],
  basemapErrorShown: false,
  scenes: [],
  activeId: null,
};

const els = {
  uploadForm: document.querySelector("#uploadForm"),
  imageFile: document.querySelector("#imageFile"),
  dropZone: document.querySelector("#dropZone"),
  fileHint: document.querySelector("#fileHint"),
  sceneName: document.querySelector("#sceneName"),
  satellite: document.querySelector("#satellite"),
  sensor: document.querySelector("#sensor"),
  capturedAt: document.querySelector("#capturedAt"),
  resolution: document.querySelector("#resolution"),
  bounds: document.querySelector("#bounds"),
  sceneList: document.querySelector("#sceneList"),
  sceneCount: document.querySelector("#sceneCount"),
  statusText: document.querySelector("#statusText"),
  detailCard: document.querySelector("#detailCard"),
  catalogFilter: document.querySelector("#catalogFilter"),
  exportCatalog: document.querySelector("#exportCatalog"),
  fitAll: document.querySelector("#fitAll"),
  clearLocal: document.querySelector("#clearLocal"),
  apiBase: document.querySelector("#apiBase"),
  connectApi: document.querySelector("#connectApi"),
  serverStatus: document.querySelector("#serverStatus"),
  syncServer: document.querySelector("#syncServer"),
  tiandituTk: document.querySelector("#tiandituTk"),
  tiandituType: document.querySelector("#tiandituType"),
  applyTianditu: document.querySelector("#applyTianditu"),
  clearBasemap: document.querySelector("#clearBasemap"),
};

function setStatus(message) {
  els.statusText.textContent = message;
}

function setServerStatus(message, online = false) {
  state.remoteOnline = online;
  els.serverStatus.textContent = message;
  els.serverStatus.classList.toggle("online", online);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatSceneSummary(scene) {
  const satellite = scene.satellite || "未填平台";
  const sensor = scene.sensor || "未填传感器";
  const capturedAt = scene.capturedAt || "未填日期";
  return `${satellite} / ${sensor} / ${capturedAt}`;
}

function setDetail(scene) {
  if (!scene) {
    els.detailCard.innerHTML = `
      <span>当前影像</span>
      <strong>未选择</strong>
      <p>上传影像后，可在目录中控制显示、透明度和定位。</p>
    `;
    return;
  }

  const bounds = scene.bounds.map((value) => Number(value).toFixed(4)).join(", ");
  const size = SDK.formatBytes(scene.size);
  const storage = scene.storage || (scene.source === "server" ? "COG" : "IndexedDB");
  const rasterInfo = scene.width && scene.height ? `${scene.width} x ${scene.height} / ${scene.bands || "-"} 波段` : "浏览器直显";
  els.detailCard.innerHTML = `
    <span>当前影像</span>
    <strong>${escapeHtml(scene.name)}</strong>
    <p>${escapeHtml(formatSceneSummary(scene))}<br />
    ${escapeHtml(storage)} · ${escapeHtml(rasterInfo)} · ${size}<br />
    分辨率：${escapeHtml(scene.resolution || "未填")}　范围：${bounds}</p>
  `;
}

function sceneMatches(scene, keyword) {
  if (!keyword) return true;
  const text = [
    scene.name,
    scene.fileName,
    scene.satellite,
    scene.sensor,
    scene.capturedAt,
    scene.resolution,
    scene.bands,
    scene.storage,
    scene.source,
  ]
    .join(" ")
    .toLowerCase();
  return text.includes(keyword.toLowerCase());
}

function sceneCard(scene) {
  const activeClass = scene.id === state.activeId ? " active" : "";
  const checked = scene.visible !== false ? "checked" : "";
  const opacity = Number.isFinite(Number(scene.opacity)) ? Number(scene.opacity) : 0.86;
  const badge = scene.source === "server" ? "COG 瓦片" : "本地直显";
  const remoteClass = scene.source === "server" ? " server" : "";
  const rasterLine = scene.width && scene.height ? `${scene.width} x ${scene.height} · ${scene.bands || "-"} 波段` : SDK.formatBytes(scene.size);

  return `
    <article class="scene-card${activeClass}" data-scene-id="${escapeHtml(scene.id)}">
      <header>
        <div>
          <h3>${escapeHtml(scene.name)}</h3>
          <p>${escapeHtml(scene.fileName || scene.id)} · ${escapeHtml(rasterLine)}<br />
          ${escapeHtml(formatSceneSummary(scene))}</p>
        </div>
        <span class="scene-badge${remoteClass}">${badge}</span>
      </header>
      <div class="scene-tools">
        <label class="toggle" title="显示/隐藏">
          <input type="checkbox" data-action="visible" ${checked} />
          <span>显示</span>
        </label>
        <input title="透明度" type="range" min="0" max="1" step="0.05" value="${opacity}" data-action="opacity" />
        <button type="button" data-action="fit">定位</button>
        <button type="button" data-action="delete">删除</button>
      </div>
    </article>
  `;
}

function renderList() {
  const keyword = els.catalogFilter.value.trim();
  const filtered = state.scenes.filter((scene) => sceneMatches(scene, keyword));

  els.sceneCount.textContent = `${state.scenes.length} 景`;
  els.sceneList.innerHTML = filtered.length
    ? filtered.map(sceneCard).join("")
    : `<div class="empty-state">
        <strong>暂无影像</strong>
        <p>上传 GeoTIFF/COG 或 PNG/JPG/WebP 后，会显示在这里并叠加到地图上。</p>
      </div>`;
}

function addVisibleScenes() {
  state.layers.clear();
  state.scenes.forEach((scene) => {
    if (scene.visible !== false) state.layers.add(scene);
  });
}

function removeBasemap() {
  state.basemapLayers.forEach((layer) => state.map.removeLayer(layer));
  state.basemapLayers = [];
}

function applyTiandituBasemap(showMessage = true) {
  const tk = els.tiandituTk.value.trim();
  const type = els.tiandituType.value || "img";
  removeBasemap();
  state.basemapErrorShown = false;

  if (!tk) {
    if (showMessage) setStatus("请先填写天地图 tk。");
    return;
  }

  state.basemapLayers = SDK.createTiandituLayers({
    tk,
    type,
    onTileLoadError: () => {
      if (state.basemapErrorShown) return;
      state.basemapErrorShown = true;
      setStatus("天地图瓦片加载失败，请检查 tk 是否允许 127.0.0.1 或当前域名访问。");
    },
  });
  state.basemapLayers.forEach((layer) => state.map.addLayer(layer));
  localStorage.setItem("tiandituTk", tk);
  localStorage.setItem("tiandituType", type);

  if (showMessage) {
    const label = { img: "影像", vec: "矢量", ter: "地形" }[type] || "影像";
    setStatus(`已启用天地图${label}底图`);
  }
}

function clearTiandituBasemap() {
  removeBasemap();
  localStorage.removeItem("tiandituTk");
  localStorage.removeItem("tiandituType");
  setStatus("已关闭天地图底图");
}

async function loadRemoteScenes() {
  if (!state.remoteOnline) return [];
  try {
    return await state.remote.list();
  } catch (error) {
    setServerStatus("服务断开", false);
    setStatus(error.message || "COG 服务同步失败");
    return [];
  }
}

async function reloadScenes() {
  const localScenes = await state.catalog.list();
  const remoteScenes = await loadRemoteScenes();
  state.scenes = [...remoteScenes, ...localScenes];
  addVisibleScenes();
  renderList();
  setStatus(`已加载 ${state.scenes.length} 景影像`);
}

function formMetadata() {
  const file = els.imageFile.files[0];
  return {
    name: els.sceneName.value.trim() || file?.name?.replace(/\.[^.]+$/, "") || "",
    satellite: els.satellite.value.trim(),
    sensor: els.sensor.value.trim(),
    capturedAt: els.capturedAt.value,
    resolution: els.resolution.value.trim(),
    bounds: SDK.parseBounds(els.bounds.value),
    opacity: 0.86,
    visible: true,
  };
}

async function saveLocalScene(scene) {
  await state.catalog.put(scene);
  state.scenes = state.scenes.filter((item) => item.id !== scene.id);
  state.scenes.unshift(scene);
}

function resetUploadForm() {
  const apiBase = state.remote.baseUrl || DEFAULT_API_BASE;
  const tiandituTk = els.tiandituTk.value;
  const tiandituType = els.tiandituType.value;
  els.uploadForm.reset();
  els.apiBase.value = apiBase;
  els.tiandituTk.value = tiandituTk;
  els.tiandituType.value = tiandituType;
  els.bounds.value = SDK.DEFAULT_BOUNDS.join(",");
  els.fileHint.textContent = "GeoTIFF/TIFF 走 COG 入库；PNG/JPG/WebP 可本地直显";
}

async function uploadRemoteCog(file, metadata) {
  if (!state.remoteOnline) {
    throw new Error("请先连接 COG 瓦片服务，再上传 GeoTIFF/TIFF。");
  }
  setStatus("GDAL 正在转换 COG 并建立瓦片入口...");
  return state.remote.upload(file, metadata);
}

async function handleUpload(event) {
  event.preventDefault();
  try {
    const file = els.imageFile.files[0];
    if (!file) throw new Error("请选择需要上传的影像文件。");
    const metadata = formMetadata();
    const scene = SDK.isGeoRasterFile(file)
      ? await uploadRemoteCog(file, metadata)
      : await SDK.createSceneFromFile(file, metadata);

    if (scene.source === "server") {
      state.scenes = state.scenes.filter((item) => item.id !== scene.id);
      state.scenes.unshift(scene);
    } else {
      await saveLocalScene(scene);
    }

    state.layers.add(scene);
    state.layers.fit(scene.id);
    state.activeId = scene.id;
    setDetail(scene);
    renderList();
    setStatus(`上传完成：${scene.name}`);
    resetUploadForm();
  } catch (error) {
    setStatus(error.message || "上传失败");
  }
}

async function updateScene(scene) {
  if (scene.source === "local") {
    await state.catalog.put(scene);
  }
  renderList();
}

async function handleSceneAction(event) {
  const card = event.target.closest("[data-scene-id]");
  if (!card) return;

  const scene = state.scenes.find((item) => item.id === card.dataset.sceneId);
  if (!scene) return;

  const action = event.target.dataset.action;
  state.activeId = scene.id;
  setDetail(scene);

  if (!action) {
    renderList();
    return;
  }

  if (action === "visible") {
    scene.visible = event.target.checked;
    if (scene.visible) {
      state.layers.add(scene);
    } else {
      state.layers.remove(scene.id);
    }
    await updateScene(scene);
    setStatus(`${scene.visible ? "显示" : "隐藏"}：${scene.name}`);
    return;
  }

  if (action === "opacity") {
    scene.opacity = Number(event.target.value);
    state.layers.setOpacity(scene.id, scene.opacity);
    if (scene.source === "local") await state.catalog.put(scene);
    setDetail(scene);
    return;
  }

  if (action === "fit") {
    if (!state.layers.entries.has(scene.id)) state.layers.add(scene);
    scene.visible = true;
    await updateScene(scene);
    state.layers.fit(scene.id);
    setStatus(`定位：${scene.name}`);
    return;
  }

  if (action === "delete") {
    if (!confirm(`删除影像：${scene.name}？`)) return;
    state.layers.remove(scene.id);
    if (scene.source === "server") {
      await state.remote.remove(scene.id);
    } else {
      await state.catalog.remove(scene.id);
    }
    state.scenes = state.scenes.filter((item) => item.id !== scene.id);
    if (state.activeId === scene.id) {
      state.activeId = null;
      setDetail(null);
    }
    renderList();
    setStatus(`已删除：${scene.name}`);
  }
}

function exportCatalog() {
  const metadata = state.scenes.map(SDK.sceneMetadata);
  const blob = new Blob([JSON.stringify({ exportedAt: new Date().toISOString(), scenes: metadata }, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `satellite-catalog-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
  setStatus("已导出影像目录元数据");
}

function fitAll() {
  state.map.getView().fit(ol.proj.transformExtent(SDK.DEFAULT_BOUNDS, "EPSG:4326", "EPSG:3857"), {
    padding: [84, 430, 84, 84],
    duration: 240,
  });
}

async function clearLocal() {
  const localCount = state.scenes.filter((scene) => scene.source === "local").length;
  if (!localCount) return;
  if (!confirm("确定清空浏览器 IndexedDB 中的本地直显影像？COG 服务影像不会被清空。")) return;
  state.scenes
    .filter((scene) => scene.source === "local")
    .forEach((scene) => state.layers.remove(scene.id));
  await state.catalog.clear();
  state.scenes = state.scenes.filter((scene) => scene.source !== "local");
  if (!state.scenes.some((scene) => scene.id === state.activeId)) {
    state.activeId = null;
    setDetail(null);
  }
  renderList();
  setStatus("已清空本地直显影像库");
}

function acceptFile(file, syncInput = false) {
  if (!file) return;
  if (syncInput) {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    els.imageFile.files = transfer.files;
  }
  const mode = SDK.isGeoRasterFile(file) ? "COG 入库" : "本地直显";
  els.fileHint.textContent = `${file.name} · ${SDK.formatBytes(file.size)} · ${mode}`;
  if (!els.sceneName.value) els.sceneName.value = file.name.replace(/\.[^.]+$/, "");
}

function bindDropZone() {
  ["dragenter", "dragover"].forEach((name) => {
    els.dropZone.addEventListener(name, (event) => {
      event.preventDefault();
      els.dropZone.classList.add("dragging");
    });
  });

  ["dragleave", "drop"].forEach((name) => {
    els.dropZone.addEventListener(name, (event) => {
      event.preventDefault();
      els.dropZone.classList.remove("dragging");
    });
  });

  els.dropZone.addEventListener("drop", (event) => {
    acceptFile(event.dataTransfer.files[0], true);
  });

  els.imageFile.addEventListener("change", () => {
    acceptFile(els.imageFile.files[0]);
  });
}

async function connectRemote(showSuccess = true) {
  const baseUrl = els.apiBase.value.trim().replace(/\/+$/, "");
  state.remote.setBaseUrl(baseUrl || DEFAULT_API_BASE);
  localStorage.setItem("remoteSensingApiBase", state.remote.baseUrl);

  try {
    const health = await state.remote.health();
    const tiler = health.titilerMounted ? "TiTiler 已挂载" : "COG 瓦片 API";
    setServerStatus("服务已连接", true);
    if (showSuccess) setStatus(`${tiler}：${state.remote.baseUrl}`);
    await reloadScenes();
  } catch (error) {
    setServerStatus("服务未连接", false);
    setStatus(error.message || "COG 服务连接失败");
    await reloadScenes();
  }
}

async function init() {
  try {
    if (!SDK) throw new Error("RemoteSensingSDK 未加载");

    const apiBase = localStorage.getItem("remoteSensingApiBase") || DEFAULT_API_BASE;
    els.apiBase.value = apiBase;
    els.tiandituTk.value = DEFAULT_TIANDITU_TK || localStorage.getItem("tiandituTk") || "";
    els.tiandituType.value = localStorage.getItem("tiandituType") || DEFAULT_TIANDITU_TYPE;
    state.remote = new SDK.RemoteCogCatalog({ baseUrl: apiBase });
    state.catalog = new SDK.RasterCatalog();
    await state.catalog.open();
    state.map = SDK.createMap({
      target: "rsMap",
      center: [118.2, 26.6],
      zoom: 9,
    });
    state.layers = new SDK.SceneLayerController(state.map);

    bindDropZone();
    els.uploadForm.addEventListener("submit", handleUpload);
    els.sceneList.addEventListener("click", handleSceneAction);
    els.sceneList.addEventListener("input", handleSceneAction);
    els.catalogFilter.addEventListener("input", renderList);
    els.exportCatalog.addEventListener("click", exportCatalog);
    els.fitAll.addEventListener("click", fitAll);
    els.clearLocal.addEventListener("click", clearLocal);
    els.connectApi.addEventListener("click", () => connectRemote(true));
    els.syncServer.addEventListener("click", () => connectRemote(true));
    els.applyTianditu.addEventListener("click", () => applyTiandituBasemap(true));
    els.clearBasemap.addEventListener("click", clearTiandituBasemap);

    applyTiandituBasemap(false);
    await connectRemote(false);
    fitAll();
  } catch (error) {
    setStatus(error.message || "SDK 初始化失败");
  }
}

init();
