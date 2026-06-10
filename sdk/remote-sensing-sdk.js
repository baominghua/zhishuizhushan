(function (global) {
  const DB_NAME = "zhushan-remote-sensing";
  const DB_VERSION = 1;
  const STORE_NAME = "scenes";
  const DEFAULT_BOUNDS = [117.55, 26.05, 118.85, 27.2];
  const SUPPORTED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];
  const GEORASTER_EXTENSIONS = [".tif", ".tiff", ".geotiff"];

  function uid(prefix = "scene") {
    return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return "-";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
      value /= 1024;
      index += 1;
    }
    return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
  }

  function parseBounds(input, fallback = DEFAULT_BOUNDS) {
    const values = Array.isArray(input)
      ? input
      : String(input || "")
          .split(/[,\s]+/)
          .filter(Boolean);
    const bounds = values.map(Number);
    if (bounds.length !== 4 || bounds.some((value) => !Number.isFinite(value))) return [...fallback];
    const [west, south, east, north] = bounds;
    if (west >= east || south >= north) return [...fallback];
    if (west < -180 || east > 180 || south < -90 || north > 90) return [...fallback];
    return [west, south, east, north];
  }

  function sceneMetadata(scene) {
    const { blob, objectUrl, layer, ...metadata } = scene;
    return metadata;
  }

  function assertOpenLayers() {
    if (!global.ol) {
      throw new Error("OpenLayers 必须在 RemoteSensingSDK 之前加载。");
    }
  }

  function fileExtension(name = "") {
    const index = name.lastIndexOf(".");
    return index >= 0 ? name.slice(index).toLowerCase() : "";
  }

  function isGeoRasterFile(file) {
    if (!file) return false;
    const ext = fileExtension(file.name);
    return GEORASTER_EXTENSIONS.includes(ext) || ["image/tiff", "image/geotiff"].includes(file.type);
  }

  class RasterCatalog {
    constructor(options = {}) {
      this.dbName = options.dbName || DB_NAME;
      this.db = null;
    }

    open() {
      if (this.db) return Promise.resolve(this.db);
      return new Promise((resolve, reject) => {
        const request = indexedDB.open(this.dbName, DB_VERSION);
        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains(STORE_NAME)) {
            const store = db.createObjectStore(STORE_NAME, { keyPath: "id" });
            store.createIndex("createdAt", "createdAt");
            store.createIndex("name", "name");
          }
        };
        request.onsuccess = () => {
          this.db = request.result;
          resolve(this.db);
        };
        request.onerror = () => reject(request.error);
      });
    }

    store(mode = "readonly") {
      if (!this.db) throw new Error("请先调用 RasterCatalog.open()。");
      return this.db.transaction(STORE_NAME, mode).objectStore(STORE_NAME);
    }

    put(scene) {
      return new Promise((resolve, reject) => {
        const request = this.store("readwrite").put({ ...scene, updatedAt: new Date().toISOString() });
        request.onsuccess = () => resolve(scene);
        request.onerror = () => reject(request.error);
      });
    }

    get(id) {
      return new Promise((resolve, reject) => {
        const request = this.store().get(id);
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = () => reject(request.error);
      });
    }

    list() {
      return new Promise((resolve, reject) => {
        const request = this.store().getAll();
        request.onsuccess = () => {
          const scenes = request.result || [];
          scenes.sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
          resolve(scenes.map((scene) => ({ ...scene, source: scene.source || "local" })));
        };
        request.onerror = () => reject(request.error);
      });
    }

    remove(id) {
      return new Promise((resolve, reject) => {
        const request = this.store("readwrite").delete(id);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
      });
    }

    clear() {
      return new Promise((resolve, reject) => {
        const request = this.store("readwrite").clear();
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
      });
    }
  }

  class RemoteCogCatalog {
    constructor(options = {}) {
      this.baseUrl = normalizeBaseUrl(options.baseUrl || "");
    }

    setBaseUrl(baseUrl) {
      this.baseUrl = normalizeBaseUrl(baseUrl);
    }

    url(path) {
      return `${this.baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
    }

    async request(path, options = {}) {
      const response = await fetch(this.url(path), options);
      if (!response.ok) {
        let detail = response.statusText;
        try {
          const data = await response.json();
          detail = data.detail || data.message || detail;
        } catch (error) {
          detail = await response.text();
        }
        throw new Error(detail || `请求失败：${response.status}`);
      }
      return response.json();
    }

    async health() {
      return this.request("/api/health");
    }

    async list() {
      const data = await this.request("/api/scenes");
      return (data.scenes || []).map((scene) => normalizeServerScene(scene));
    }

    async upload(file, metadata = {}) {
      const form = new FormData();
      form.append("file", file);
      form.append("name", metadata.name || "");
      form.append("satellite", metadata.satellite || "");
      form.append("sensor", metadata.sensor || "");
      form.append("capturedAt", metadata.capturedAt || "");
      form.append("resolution", metadata.resolution || "");
      form.append("bounds", (metadata.bounds || []).join(","));
      const scene = await this.request("/api/scenes/upload", {
        method: "POST",
        body: form,
      });
      return normalizeServerScene(scene);
    }

    async remove(id) {
      return this.request(`/api/scenes/${encodeURIComponent(id)}`, { method: "DELETE" });
    }
  }

  function normalizeBaseUrl(baseUrl) {
    return String(baseUrl || "").replace(/\/+$/, "");
  }

  function normalizeServerScene(scene) {
    return {
      ...scene,
      source: "server",
      storage: scene.storage || "COG",
      visible: scene.visible !== false,
      opacity: Number.isFinite(Number(scene.opacity)) ? Number(scene.opacity) : 0.9,
      bounds: parseBounds(scene.bounds),
    };
  }

  async function createSceneFromFile(file, metadata = {}) {
    if (!file) throw new Error("请选择需要上传的卫星影像文件。");
    if (!SUPPORTED_IMAGE_TYPES.includes(file.type)) {
      throw new Error("PNG/JPG/WebP 可本地直显；GeoTIFF/TIFF 请连接后端 COG 服务后上传。");
    }

    const now = new Date().toISOString();
    return {
      id: metadata.id || uid("rs"),
      source: "local",
      storage: "IndexedDB",
      name: metadata.name || file.name.replace(/\.[^.]+$/, ""),
      fileName: file.name,
      fileType: file.type,
      size: file.size,
      satellite: metadata.satellite || "",
      sensor: metadata.sensor || "",
      capturedAt: metadata.capturedAt || "",
      resolution: metadata.resolution || "",
      cloud: metadata.cloud || "",
      bands: metadata.bands || "RGB",
      bounds: parseBounds(metadata.bounds),
      opacity: Number.isFinite(Number(metadata.opacity)) ? Number(metadata.opacity) : 0.86,
      visible: metadata.visible !== false,
      transferStatus: metadata.transferStatus || "stored",
      createdAt: metadata.createdAt || now,
      updatedAt: now,
      blob: file,
    };
  }

  function createOfflineBaseLayer(geojson) {
    assertOpenLayers();
    const features = geojson
      ? new ol.format.GeoJSON().readFeatures(geojson, {
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:3857",
        })
      : [];

    const style = (feature) => {
      const kind = feature.get("kind");
      if (kind === "water" || kind === "waterway") {
        return new ol.style.Style({
          stroke: new ol.style.Stroke({ color: "rgba(82, 202, 255, 0.62)", width: kind === "waterway" ? 1.7 : 1 }),
          fill: new ol.style.Fill({ color: "rgba(42, 126, 166, 0.26)" }),
        });
      }
      if (kind === "road") {
        return new ol.style.Style({
          stroke: new ol.style.Stroke({ color: "rgba(232, 236, 210, 0.38)", width: 1.2 }),
        });
      }
      if (kind === "forest" || kind === "landuse") {
        return new ol.style.Style({
          stroke: new ol.style.Stroke({ color: "rgba(90, 160, 102, 0.16)", width: 1 }),
          fill: new ol.style.Fill({ color: kind === "forest" ? "rgba(38, 118, 66, 0.22)" : "rgba(62, 104, 72, 0.15)" }),
        });
      }
      return new ol.style.Style({
        stroke: new ol.style.Stroke({ color: "rgba(180, 220, 198, 0.14)", width: 1 }),
        fill: new ol.style.Fill({ color: "rgba(120, 150, 130, 0.08)" }),
      });
    };

    return new ol.layer.Vector({
      source: new ol.source.Vector({ features }),
      style,
      opacity: 0.72,
    });
  }

  function tiandituTileUrls(layer, tk) {
    const token = encodeURIComponent(tk);
    return Array.from({ length: 8 }, (_, index) => {
      return `https://t${index}.tianditu.gov.cn/DataServer?T=${layer}_w&x={x}&y={y}&l={z}&tk=${token}`;
    });
  }

  function createTiandituLayers(options = {}) {
    assertOpenLayers();
    const tk = String(options.tk || "").trim();
    if (!tk) return [];

    const type = options.type || "img";
    const pairs = {
      vec: ["vec", "cva"],
      img: ["img", "cia"],
      ter: ["ter", "cta"],
    };
    const [baseLayer, labelLayer] = pairs[type] || pairs.img;
    const attribution = "© 天地图";

    const createLayer = (layer, zIndex) => {
      const source = new ol.source.XYZ({
        urls: tiandituTileUrls(layer, tk),
        maxZoom: 18,
        attributions: attribution,
      });
      if (typeof options.onTileLoadError === "function") {
        source.on("tileloaderror", options.onTileLoadError);
      }
      const tileLayer = new ol.layer.Tile({
        source,
        opacity: options.opacity ?? 1,
        visible: true,
      });
      tileLayer.setZIndex(zIndex);
      tileLayer.set("basemap", "tianditu");
      return tileLayer;
    };

    return [createLayer(baseLayer, 0), createLayer(labelLayer, 1)];
  }

  function createMap(options = {}) {
    assertOpenLayers();
    const layers = [];
    if (options.offlineGeojson) layers.push(createOfflineBaseLayer(options.offlineGeojson));
    return new ol.Map({
      target: options.target,
      controls: options.controls || [],
      layers,
      view: new ol.View({
        center: ol.proj.fromLonLat(options.center || [118.2, 26.6]),
        zoom: options.zoom || 9,
        minZoom: options.minZoom || 6,
        maxZoom: options.maxZoom || 20,
      }),
    });
  }

  class SceneLayerController {
    constructor(map) {
      assertOpenLayers();
      this.map = map;
      this.entries = new Map();
    }

    add(scene) {
      this.remove(scene.id);
      const layer = scene.tileUrl ? this.createTileLayer(scene) : this.createStaticImageLayer(scene);
      layer.set("sceneId", scene.id);
      layer.set("sceneName", scene.name);
      layer.setZIndex(scene.zIndex ?? 10);
      this.map.addLayer(layer);
      this.entries.set(scene.id, { layer, scene, objectUrl: layer.get("objectUrl") });
      return layer;
    }

    createTileLayer(scene) {
      return new ol.layer.Tile({
        source: new ol.source.XYZ({
          url: scene.tileUrl,
          crossOrigin: "anonymous",
          maxZoom: scene.maxZoom || 22,
        }),
        opacity: scene.opacity ?? 0.9,
        visible: scene.visible !== false,
      });
    }

    createStaticImageLayer(scene) {
      if (!scene?.blob) throw new Error("影像缺少可显示的 Blob 数据。");
      const objectUrl = URL.createObjectURL(scene.blob);
      const imageExtent = ol.proj.transformExtent(scene.bounds, "EPSG:4326", "EPSG:3857");
      const layer = new ol.layer.Image({
        source: new ol.source.ImageStatic({
          url: objectUrl,
          imageExtent,
          projection: "EPSG:3857",
        }),
        opacity: scene.opacity ?? 0.86,
        visible: scene.visible !== false,
      });
      layer.set("objectUrl", objectUrl);
      return layer;
    }

    remove(id) {
      const entry = this.entries.get(id);
      if (!entry) return;
      this.map.removeLayer(entry.layer);
      if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl);
      this.entries.delete(id);
    }

    setOpacity(id, opacity) {
      this.entries.get(id)?.layer.setOpacity(Number(opacity));
    }

    setVisible(id, visible) {
      this.entries.get(id)?.layer.setVisible(Boolean(visible));
    }

    fit(id, options = {}) {
      const entry = this.entries.get(id);
      if (!entry) return;
      const extent = ol.proj.transformExtent(entry.scene.bounds, "EPSG:4326", "EPSG:3857");
      this.map.getView().fit(extent, {
        padding: options.padding || [84, 430, 84, 84],
        maxZoom: options.maxZoom || 16,
        duration: options.duration || 260,
      });
    }

    clear() {
      [...this.entries.keys()].forEach((id) => this.remove(id));
    }
  }

  global.RemoteSensingSDK = {
    DEFAULT_BOUNDS,
    GEORASTER_EXTENSIONS,
    SUPPORTED_IMAGE_TYPES,
    RasterCatalog,
    RemoteCogCatalog,
    SceneLayerController,
    createSceneFromFile,
    createOfflineBaseLayer,
    createTiandituLayers,
    createMap,
    formatBytes,
    isGeoRasterFile,
    parseBounds,
    sceneMetadata,
  };
})(window);
