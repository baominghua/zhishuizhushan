const SDK = window.RemoteSensingSDK;
const LOCAL_CONFIG = window.SATELLITE_CONFIG || {};
const normalizeApiBase = (value) => String(value || "").trim().replace(/\/+$/, "");
const resolveDefaultApiBase = () => {
  const configured = normalizeApiBase(LOCAL_CONFIG.remoteApiBase);
  if (configured) return configured;
  if (window.location.protocol === "file:") return "http://127.0.0.1:8010";
  if (window.location.port === "8010") return window.location.origin;
  if (window.location.hostname) return `${window.location.protocol}//${window.location.hostname}:8010`;
  return "http://127.0.0.1:8010";
};
const DEFAULT_API_BASE = resolveDefaultApiBase();
const DEFAULT_TIANDITU_TK = LOCAL_CONFIG.tiandituTk || "";
const DEFAULT_TIANDITU_TYPE = LOCAL_CONFIG.tiandituType || "img";
const DEFAULT_TIANDITU_PROXY = LOCAL_CONFIG.tiandituProxy !== false;

const state = {
  catalog: null,
  remote: null,
  client: null,
  remoteOnline: false,
  map: null,
  layers: null,
  basemapLayers: [],
  basemapErrorShown: false,
  scenes: [],
  tasks: [],
  taskPoller: null,
  completedTaskScenes: new Set(),
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
  projectId: document.querySelector("#projectId"),
  areaCode: document.querySelector("#areaCode"),
  allowedRoles: document.querySelector("#allowedRoles"),
  allowedUsers: document.querySelector("#allowedUsers"),
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
  authToken: document.querySelector("#authToken"),
  authUser: document.querySelector("#authUser"),
  authRoles: document.querySelector("#authRoles"),
  authScope: document.querySelector("#authScope"),
  tiandituTk: document.querySelector("#tiandituTk"),
  tiandituType: document.querySelector("#tiandituType"),
  applyTianditu: document.querySelector("#applyTianditu"),
  clearBasemap: document.querySelector("#clearBasemap"),
  serverFilePath: document.querySelector("#serverFilePath"),
  registerServerFile: document.querySelector("#registerServerFile"),
  taskList: document.querySelector("#taskList"),
  taskCount: document.querySelector("#taskCount"),
  refreshTasks: document.querySelector("#refreshTasks"),
  saveAccess: document.querySelector("#saveAccess"),
  bulkAccess: document.querySelector("#bulkAccess"),
  catalogBbox: document.querySelector("#catalogBbox"),
  searchServer: document.querySelector("#searchServer"),
  cacheStatus: document.querySelector("#cacheStatus"),
  cacheMaxMb: document.querySelector("#cacheMaxMb"),
  cacheMaxAge: document.querySelector("#cacheMaxAge"),
  refreshCache: document.querySelector("#refreshCache"),
  pruneCache: document.querySelector("#pruneCache"),
  clearCogCache: document.querySelector("#clearCogCache"),
  clearTdtCache: document.querySelector("#clearTdtCache"),
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

function splitInput(value) {
  return String(value || "")
    .split(/[,;\s/]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function cookieValue(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const part = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix));
  return part ? decodeURIComponent(part.slice(prefix.length)) : "";
}

function clearLegacyPersistedAuth() {
  localStorage.removeItem("remoteSensingAuthToken");
  localStorage.removeItem("remoteSensingAuthUser");
  localStorage.removeItem("remoteSensingAuthRoles");
  localStorage.removeItem("remoteSensingAuthScope");
}

function applyAuthSettings() {
  const scope = splitInput(els.authScope?.value || "");
  state.client.setAuthToken(els.authToken?.value?.trim() || "");
  state.client.setAuthContext({
    user: els.authUser?.value?.trim() || "",
    roles: splitInput(els.authRoles?.value || ""),
    projects: scope[0] ? [scope[0]] : [],
    areas: scope[1] ? [scope[1]] : [],
  });
}

function serverSearchParams() {
  const params = {};
  const keyword = els.catalogFilter?.value?.trim();
  const bbox = els.catalogBbox?.value?.trim();
  if (keyword) params.q = keyword;
  if (bbox) params.bbox = bbox;
  if (els.projectId?.value?.trim()) params.projectId = els.projectId.value.trim();
  if (els.areaCode?.value?.trim()) params.areaCode = els.areaCode.value.trim();
  return params;
}

function activeScene() {
  return state.scenes.find((item) => item.id === state.activeId) || null;
}

function accessPayload() {
  return {
    projectId: els.projectId.value.trim(),
    areaCode: els.areaCode.value.trim(),
    allowedRoles: els.allowedRoles.value.trim(),
    allowedUsers: els.allowedUsers.value.trim(),
  };
}

function cachePruneParams() {
  const maxMb = Number(els.cacheMaxMb?.value || 0);
  const maxAgeDays = Number(els.cacheMaxAge?.value || 0);
  return {
    maxBytes: Number.isFinite(maxMb) && maxMb > 0 ? Math.round(maxMb * 1024 * 1024) : 0,
    maxAgeDays: Number.isFinite(maxAgeDays) && maxAgeDays > 0 ? maxAgeDays : 0,
  };
}

function formatSceneSummary(scene) {
  const satellite = scene.satellite || "未填平台";
  const sensor = scene.sensor || "未填传感器";
  const capturedAt = scene.capturedAt || "未填日期";
  return `${satellite} / ${sensor} / ${capturedAt}`;
}

function formatAccessSummary(scene) {
  const project = scene.projectId || "-";
  const area = scene.areaCode || "-";
  const roles = (Array.isArray(scene.allowedRoles) ? scene.allowedRoles.join(",") : scene.allowedRoles) || "公开角色";
  const users = (Array.isArray(scene.allowedUsers) ? scene.allowedUsers.join(",") : scene.allowedUsers) || "公开用户";
  return `项目 ${project} / 区域 ${area} / 角色 ${roles} / 用户 ${users}`;
}

function fillAccessForm(scene) {
  if (!scene) return;
  els.projectId.value = scene.projectId || "";
  els.areaCode.value = scene.areaCode || "";
  els.allowedRoles.value = Array.isArray(scene.allowedRoles) ? scene.allowedRoles.join(",") : scene.allowedRoles || "";
  els.allowedUsers.value = Array.isArray(scene.allowedUsers) ? scene.allowedUsers.join(",") : scene.allowedUsers || "";
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
    ${escapeHtml(formatAccessSummary(scene))}<br />
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
          ${escapeHtml(formatSceneSummary(scene))}<br />
          ${escapeHtml(formatAccessSummary(scene))}</p>
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

function taskLabel(status) {
  return (
    {
      queued: "排队中",
      running: "转换中",
      completed: "已完成",
      failed: "失败",
    }[status] || status || "-"
  );
}

function renderTasks() {
  if (!els.taskList) return;
  els.taskCount.textContent = `${state.tasks.length} 个`;
  els.taskList.innerHTML = state.tasks.length
    ? state.tasks
        .map((task) => {
          const progress = Math.max(0, Math.min(100, Number(task.progress) || 0));
          return `
            <article class="task-card ${escapeHtml(task.status || "")}">
              <header>
                <div>
                  <strong>${escapeHtml(task.name || task.fileName || task.id)}</strong>
                  <p>${escapeHtml(task.fileName || task.sourcePath || "")}<br />${escapeHtml(task.message || "")}</p>
                </div>
                <span class="task-status">${escapeHtml(taskLabel(task.status))}</span>
              </header>
              <div class="task-progress" style="--progress:${progress}%"><span></span></div>
            </article>
          `;
        })
        .join("")
    : `<div class="empty-state"><strong>暂无转换任务</strong><p>可以上传 GeoTIFF，或填写服务器/NAS 文件路径后注册入库。</p></div>`;
}

async function refreshTasks(showMessage = false) {
  if (!state.remoteOnline || !state.client?.listTasks) {
    state.tasks = [];
    renderTasks();
    return;
  }
  try {
    state.tasks = await state.client.listTasks();
    const newCompleted = state.tasks.filter((task) => task.status === "completed" && task.sceneId && !state.completedTaskScenes.has(task.sceneId));
    newCompleted.forEach((task) => state.completedTaskScenes.add(task.sceneId));
    renderTasks();
    if (newCompleted.length) await reloadScenes();
    if (showMessage) setStatus("转换任务已刷新");
  } catch (error) {
    setStatus(error.message || "转换任务刷新失败");
  }
}

function startTaskPolling() {
  if (state.taskPoller) window.clearInterval(state.taskPoller);
  state.taskPoller = window.setInterval(() => refreshTasks(false), 5000);
}

function addVisibleScenes() {
  state.layers.removeGroup("catalog-scenes");
  state.scenes.forEach((scene) => {
    if (scene.visible !== false) state.layers.add(scene, { group: "catalog-scenes" });
  });
}

function removeBasemap() {
  if (state.layers) {
    state.layers.removeGroup("tianditu-basemap");
  } else {
    state.basemapLayers.forEach((layer) => state.map.removeLayer(layer));
  }
  state.basemapLayers = [];
}

function applyTiandituBasemap(showMessage = true) {
  const tk = els.tiandituTk.value.trim();
  const type = els.tiandituType.value || "img";
  const proxyBaseUrl = DEFAULT_TIANDITU_PROXY
    ? normalizeApiBase(LOCAL_CONFIG.tiandituProxyBaseUrl) || normalizeApiBase(els.apiBase.value) || DEFAULT_API_BASE
    : "";
  removeBasemap();
  state.basemapErrorShown = false;

  if (!tk && !proxyBaseUrl) {
    if (showMessage) setStatus("请先填写天地图 tk。");
    return;
  }

  state.basemapLayers = SDK.SourceAdapters.tianditu({
    tk,
    type,
    proxyBaseUrl,
    preload: 1,
    onTileLoadError: () => {
      if (state.basemapErrorShown) return;
      state.basemapErrorShown = true;
      setStatus("天地图瓦片加载失败，请检查 tk 是否允许 127.0.0.1 或当前域名访问。");
    },
  });
  state.layers.addGroup("tianditu-basemap", state.basemapLayers, {
    ids: ["base", "label"],
    zIndex: 0,
  });
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
    return await state.client.listRemoteScenes(serverSearchParams());
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
    projectId: els.projectId.value.trim(),
    areaCode: els.areaCode.value.trim(),
    allowedRoles: els.allowedRoles.value.trim(),
    allowedUsers: els.allowedUsers.value.trim(),
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
  const authToken = els.authToken.value;
  const authUser = els.authUser.value;
  const authRoles = els.authRoles.value;
  const authScope = els.authScope.value;
  const catalogBbox = els.catalogBbox.value;
  els.uploadForm.reset();
  els.apiBase.value = apiBase;
  els.tiandituTk.value = tiandituTk;
  els.tiandituType.value = tiandituType;
  els.authToken.value = authToken;
  els.authUser.value = authUser;
  els.authRoles.value = authRoles;
  els.authScope.value = authScope;
  els.catalogBbox.value = catalogBbox;
  els.bounds.value = SDK.DEFAULT_BOUNDS.join(",");
  els.fileHint.textContent = "GeoTIFF/TIFF 走 COG 入库；PNG/JPG/WebP 可本地直显";
}

async function uploadRemoteCog(file, metadata) {
  if (!state.remoteOnline) {
    throw new Error("请先连接 COG 瓦片服务，再上传 GeoTIFF/TIFF。");
  }
  setStatus("GDAL 正在转换 COG 并建立瓦片入口...");
  return state.client.uploadCog(file, { ...metadata, asyncMode: true });
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

    if (scene.task) {
      await refreshTasks(false);
      setStatus(`后台任务已创建：${scene.task.id}`);
      resetUploadForm();
      return;
    }

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

async function registerServerFile() {
  try {
    if (!state.remoteOnline) throw new Error("请先连接 COG 瓦片服务。");
    const path = els.serverFilePath.value.trim();
    if (!path) throw new Error("请填写服务器/NAS 文件路径。");
    const metadata = formMetadata();
    const result = await state.client.registerFile({
      path,
      name: metadata.name,
      satellite: metadata.satellite,
      sensor: metadata.sensor,
      capturedAt: metadata.capturedAt,
      resolution: metadata.resolution,
      bounds: metadata.bounds,
      projectId: metadata.projectId,
      areaCode: metadata.areaCode,
      allowedRoles: metadata.allowedRoles,
      allowedUsers: metadata.allowedUsers,
    });
    els.serverFilePath.value = "";
    await refreshTasks(false);
    setStatus(`服务器文件已进入后台任务：${result.task?.id || ""}`);
  } catch (error) {
    setStatus(error.message || "服务器文件注册失败");
  }
}

async function updateScene(scene) {
  if (scene.source === "local") {
    await state.catalog.put(scene);
  }
  renderList();
}

async function saveActiveAccess() {
  const scene = activeScene();
  if (!scene) {
    setStatus("请先在目录里选择一景影像");
    return;
  }
  const payload = accessPayload();
  try {
    let updated;
    if (scene.source === "server") {
      updated = await state.client.updateSceneAccess(scene.id, payload);
    } else {
      updated = {
        ...scene,
        ...payload,
        allowedRoles: splitInput(payload.allowedRoles),
        allowedUsers: splitInput(payload.allowedUsers),
      };
      await state.catalog.put(updated);
    }
    state.scenes = state.scenes.map((item) => (item.id === scene.id ? { ...item, ...updated } : item));
    setDetail(updated);
    renderList();
    setStatus(`权限已保存：${updated.name}`);
  } catch (error) {
    setStatus(error.message || "权限保存失败");
  }
}

async function bulkApplyAccess() {
  const payload = accessPayload();
  const targets = state.scenes.filter((scene) => scene.source === "server").map((scene) => scene.id);
  if (!targets.length) {
    setStatus("当前没有可批量更新的服务端 COG 影像");
    return;
  }
  if (!confirm(`把当前权限套用到 ${targets.length} 景服务端影像？`)) return;
  try {
    await state.client.bulkUpdateSceneAccess({ ids: targets, ...payload });
    await reloadScenes();
    setStatus(`已批量更新 ${targets.length} 景服务端影像权限`);
  } catch (error) {
    setStatus(error.message || "批量权限更新失败");
  }
}

async function refreshCacheStatus(showMessage = false) {
  if (!state.remoteOnline) return;
  try {
    const [cog, tdt] = await Promise.all([state.client.tileCacheStatus(), state.client.tiandituCacheStatus()]);
    const cogSize = SDK.formatBytes(cog.bytes || 0);
    const tdtSize = SDK.formatBytes(tdt.bytes || 0);
    els.cacheStatus.textContent = `COG ${cog.files || 0}/${cogSize}，底图 ${tdt.files || 0}/${tdtSize}`;
    if (showMessage) setStatus("缓存状态已刷新");
  } catch (error) {
    els.cacheStatus.textContent = "读取失败";
    setStatus(error.message || "缓存状态读取失败");
  }
}

async function pruneCaches() {
  if (!state.remoteOnline) return;
  try {
    const params = cachePruneParams();
    await Promise.all([state.client.pruneTileCache(params), state.client.pruneTiandituCache(params)]);
    await refreshCacheStatus(false);
    setStatus("缓存淘汰已执行");
  } catch (error) {
    setStatus(error.message || "缓存淘汰失败");
  }
}

async function clearCogCache() {
  if (!state.remoteOnline) return;
  if (!confirm("清理全部 COG 动态瓦片缓存？")) return;
  try {
    await state.client.clearTileCache();
    await refreshCacheStatus(false);
    setStatus("COG 瓦片缓存已清理");
  } catch (error) {
    setStatus(error.message || "COG 缓存清理失败");
  }
}

async function clearTiandituCache() {
  if (!state.remoteOnline) return;
  if (!confirm("清理全部天地图底图缓存？")) return;
  try {
    await state.client.clearTiandituCache();
    await refreshCacheStatus(false);
    setStatus("天地图底图缓存已清理");
  } catch (error) {
    setStatus(error.message || "底图缓存清理失败");
  }
}

async function handleSceneAction(event) {
  const card = event.target.closest("[data-scene-id]");
  if (!card) return;

  const scene = state.scenes.find((item) => item.id === card.dataset.sceneId);
  if (!scene) return;

  const action = event.target.dataset.action;
  state.activeId = scene.id;
  setDetail(scene);
  fillAccessForm(scene);

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
      await state.client.removeRemoteScene(scene.id);
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
  state.client.setApiBase(baseUrl || DEFAULT_API_BASE);
  applyAuthSettings();
  localStorage.setItem("remoteSensingApiBase", state.remote.baseUrl);

  try {
    const health = await state.remote.health();
    const tiler = health.titilerMounted ? "TiTiler 已挂载" : "COG 瓦片 API";
    setServerStatus("服务已连接", true);
    if (showSuccess) setStatus(`${tiler}：${state.remote.baseUrl}`);
    await reloadScenes();
    await refreshTasks(false);
    await refreshCacheStatus(false);
  } catch (error) {
    setServerStatus("服务未连接", false);
    setStatus(error.message || "COG 服务连接失败");
    await reloadScenes();
    await refreshTasks(false);
  }
}

async function init() {
  try {
    if (!SDK) throw new Error("RemoteSensingSDK 未加载");

    const apiBase = normalizeApiBase(LOCAL_CONFIG.remoteApiBase) || localStorage.getItem("remoteSensingApiBase") || DEFAULT_API_BASE;
    els.apiBase.value = apiBase;
    els.tiandituTk.value = DEFAULT_TIANDITU_TK || localStorage.getItem("tiandituTk") || "";
    els.tiandituType.value = localStorage.getItem("tiandituType") || DEFAULT_TIANDITU_TYPE;
    clearLegacyPersistedAuth();
    els.authToken.value = "";
    els.authUser.value = "";
    els.authRoles.value = "";
    els.authScope.value = "";
    state.catalog = new SDK.RasterCatalog();
    await state.catalog.open();
    state.map = SDK.createMap({
      target: "rsMap",
      center: [118.2, 26.6],
      zoom: 9,
    });
    state.layers = new SDK.LayerManager(state.map, { defaultGroup: "catalog-scenes", defaultZIndex: 10 });
    state.client = new SDK.RemoteSensingClient({
      apiBase,
      map: state.map,
      layers: state.layers,
      csrfToken: () => cookieValue("smart_bamboo_session_csrf"),
    });
    state.remote = state.client.remote;

    bindDropZone();
    els.uploadForm.addEventListener("submit", handleUpload);
    els.sceneList.addEventListener("click", handleSceneAction);
    els.sceneList.addEventListener("input", handleSceneAction);
    els.catalogFilter.addEventListener("input", renderList);
    els.searchServer.addEventListener("click", () => connectRemote(true));
    els.exportCatalog.addEventListener("click", exportCatalog);
    els.saveAccess.addEventListener("click", saveActiveAccess);
    els.bulkAccess.addEventListener("click", bulkApplyAccess);
    els.fitAll.addEventListener("click", fitAll);
    els.clearLocal.addEventListener("click", clearLocal);
    els.connectApi.addEventListener("click", () => connectRemote(true));
    els.syncServer.addEventListener("click", () => connectRemote(true));
    els.applyTianditu.addEventListener("click", () => applyTiandituBasemap(true));
    els.clearBasemap.addEventListener("click", clearTiandituBasemap);
    els.registerServerFile.addEventListener("click", registerServerFile);
    els.refreshTasks.addEventListener("click", () => refreshTasks(true));
    els.refreshCache.addEventListener("click", () => refreshCacheStatus(true));
    els.pruneCache.addEventListener("click", pruneCaches);
    els.clearCogCache.addEventListener("click", clearCogCache);
    els.clearTdtCache.addEventListener("click", clearTiandituCache);

    applyTiandituBasemap(false);
    startTaskPolling();
    await connectRemote(false);
    fitAll();
  } catch (error) {
    setStatus(error.message || "SDK 初始化失败");
  }
}

init();
