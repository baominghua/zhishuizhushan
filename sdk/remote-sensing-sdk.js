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
      this.token = options.token || "";
      this.context = options.context || {};
      this.headers = { ...(options.headers || {}) };
      this.csrfToken = options.csrfToken || "";
      this.credentials = options.credentials || "include";
    }

    setBaseUrl(baseUrl) {
      this.baseUrl = normalizeBaseUrl(baseUrl);
    }

    setToken(token = "") {
      this.token = token;
    }

    setContext(context = {}) {
      this.context = { ...this.context, ...context };
    }

    authHeaders() {
      const headers = { ...this.headers };
      if (this.token) headers.Authorization = `Bearer ${this.token}`;
      if (this.context.user) headers["X-RS-User"] = this.context.user;
      if (this.context.roles) headers["X-RS-Roles"] = Array.isArray(this.context.roles) ? this.context.roles.join(",") : this.context.roles;
      if (this.context.projects) headers["X-RS-Projects"] = Array.isArray(this.context.projects) ? this.context.projects.join(",") : this.context.projects;
      if (this.context.areas) headers["X-RS-Areas"] = Array.isArray(this.context.areas) ? this.context.areas.join(",") : this.context.areas;
      return headers;
    }

    url(path, params = null) {
      const base = `${this.baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
      if (!params) return base;
      const query = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value === undefined || value === null || value === "") return;
        query.set(key, value);
      });
      const suffix = query.toString();
      return suffix ? `${base}?${suffix}` : base;
    }

    async request(path, options = {}) {
      const { params, headers, ...fetchOptions } = options;
      const requestHeaders = { ...this.authHeaders(), ...(headers || {}) };
      const method = String(fetchOptions.method || "GET").toUpperCase();
      const csrfToken = typeof this.csrfToken === "function" ? this.csrfToken() : this.csrfToken;
      if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && csrfToken) {
        requestHeaders["X-CSRF-Token"] = csrfToken;
      }
      if (Object.keys(requestHeaders).length) fetchOptions.headers = requestHeaders;
      fetchOptions.credentials ||= this.credentials;
      const response = await fetch(this.url(path, params), fetchOptions);
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

    async list(params = {}) {
      const data = await this.request("/api/scenes", { params });
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
      form.append("projectId", metadata.projectId || "");
      form.append("areaCode", metadata.areaCode || "");
      form.append("allowedRoles", Array.isArray(metadata.allowedRoles) ? metadata.allowedRoles.join(",") : metadata.allowedRoles || "");
      form.append("allowedUsers", Array.isArray(metadata.allowedUsers) ? metadata.allowedUsers.join(",") : metadata.allowedUsers || "");
      if (metadata.asyncMode) form.append("asyncMode", "true");
      const scene = await this.request("/api/scenes/upload", {
        method: "POST",
        body: form,
      });
      if (scene.task) return scene;
      return normalizeServerScene(scene);
    }

    async remove(id) {
      return this.request(`/api/scenes/${encodeURIComponent(id)}`, { method: "DELETE" });
    }

    async updateSceneAccess(id, payload = {}) {
      const scene = await this.request(`/api/scenes/${encodeURIComponent(id)}/access`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return normalizeServerScene(scene);
    }

    async bulkUpdateSceneAccess(payload = {}) {
      return this.request("/api/scenes/access/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    async registerFile(payload = {}) {
      const response = await this.request("/api/scenes/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return response;
    }

    async listTasks() {
      return this.request("/api/tasks");
    }

    async getTask(id) {
      return this.request(`/api/tasks/${encodeURIComponent(id)}`);
    }

    async geoserverConfig() {
      return this.request("/api/geoserver/config");
    }

    async geoserverLayers() {
      const data = await this.request("/api/geoserver/layers");
      return data.layers || [];
    }

    async tileCacheStatus() {
      return this.request("/api/cache/tiles");
    }

    async clearTileCache(sceneId = "") {
      return this.request("/api/cache/tiles", {
        method: "DELETE",
        params: sceneId ? { sceneId } : {},
      });
    }

    async pruneTileCache(options = {}) {
      return this.request("/api/cache/tiles/prune", {
        method: "POST",
        params: options,
      });
    }

    async tiandituCacheStatus() {
      return this.request("/api/cache/tianditu");
    }

    async clearTiandituCache(layer = "") {
      return this.request("/api/cache/tianditu", {
        method: "DELETE",
        params: layer ? { layer } : {},
      });
    }

    async pruneTiandituCache(options = {}) {
      return this.request("/api/cache/tianditu/prune", {
        method: "POST",
        params: options,
      });
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

  function tiandituTileUrls(layer, tk, options = {}) {
    const layerId = `${layer}_w`;
    const proxyBaseUrl = normalizeBaseUrl(options.proxyBaseUrl || "");
    const token = encodeURIComponent(tk || "");
    if (proxyBaseUrl) {
      const query = token ? `?tk=${token}` : "";
      return [`${proxyBaseUrl}/api/basemaps/tianditu/${layerId}/{z}/{x}/{y}.png${query}`];
    }
    if (!token) return [];
    return Array.from({ length: 8 }, (_, index) => {
      return `https://t${index}.tianditu.gov.cn/DataServer?T=${layerId}&x={x}&y={y}&l={z}&tk=${token}`;
    });
  }

  function createTiandituLayers(options = {}) {
    assertOpenLayers();
    const tk = String(options.tk || "").trim();
    const proxyBaseUrl = normalizeBaseUrl(options.proxyBaseUrl || "");
    if (!tk && !proxyBaseUrl) return [];

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
        urls: tiandituTileUrls(layer, tk, { proxyBaseUrl }),
        maxZoom: 18,
        attributions: attribution,
        crossOrigin: options.crossOrigin || "anonymous",
      });
      if (typeof options.onTileLoadError === "function") {
        source.on("tileloaderror", options.onTileLoadError);
      }
      if (typeof options.onTileLoadEnd === "function") {
        source.on("tileloadend", options.onTileLoadEnd);
      }
      const tileLayer = new ol.layer.Tile({
        source,
        opacity: options.opacity ?? 1,
        visible: true,
        preload: options.preload ?? 0,
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

  const SourceAdapters = {
    xyz(options = {}) {
      assertOpenLayers();
      const sourceOptions = {
        maxZoom: options.maxZoom ?? 22,
        minZoom: options.minZoom,
        attributions: options.attributions,
        tileSize: options.tileSize,
      };
      if (options.url) sourceOptions.url = options.url;
      if (options.urls) sourceOptions.urls = options.urls;
      if (options.crossOrigin !== false) sourceOptions.crossOrigin = options.crossOrigin || "anonymous";
      const source = new ol.source.XYZ(sourceOptions);
      if (typeof options.onTileLoadError === "function") {
        source.on("tileloaderror", options.onTileLoadError);
      }
      return source;
    },

    tileWms(options = {}) {
      assertOpenLayers();
      const source = new ol.source.TileWMS({
        url: options.url,
        params: options.params || {},
        serverType: options.serverType,
        crossOrigin: options.crossOrigin || "anonymous",
      });
      if (typeof options.onTileLoadError === "function") {
        source.on("tileloaderror", options.onTileLoadError);
      }
      return source;
    },

    geoserverWms(options = {}) {
      const params = {
        LAYERS: options.layer || options.layers,
        TILED: options.tiled !== false,
        STYLES: options.styles || "",
        FORMAT: options.format || "image/png",
        TRANSPARENT: options.transparent !== false,
        ...(options.params || {}),
      };
      return SourceAdapters.tileWms({
        url: options.url || options.wmsUrl,
        params,
        serverType: "geoserver",
        crossOrigin: options.crossOrigin,
        onTileLoadError: options.onTileLoadError,
      });
    },

    wmts(options = {}) {
      assertOpenLayers();
      return new ol.source.WMTS(options);
    },

    imageStatic(options = {}) {
      assertOpenLayers();
      const bounds = parseBounds(options.bounds);
      return new ol.source.ImageStatic({
        url: options.url,
        imageExtent: ol.proj.transformExtent(bounds, "EPSG:4326", "EPSG:3857"),
        projection: "EPSG:3857",
      });
    },

    vector(options = {}) {
      assertOpenLayers();
      const features = options.geojson
        ? new ol.format.GeoJSON().readFeatures(options.geojson, {
            dataProjection: options.dataProjection || "EPSG:4326",
            featureProjection: options.featureProjection || "EPSG:3857",
          })
        : options.features || [];
      return new ol.source.Vector({ features });
    },

    scene(scene, options = {}) {
      assertOpenLayers();
      const layerType = scene.layerType || scene.sourceType || (scene.tileUrl ? "xyz" : "imageStatic");
      if (layerType === "xyz" || layerType === "cog" || layerType === "tile") {
        return new ol.layer.Tile({
          source: SourceAdapters.xyz({
            url: scene.tileUrl || scene.url,
            urls: scene.tileUrls || scene.urls,
            maxZoom: scene.maxZoom ?? options.maxZoom,
            crossOrigin: scene.crossOrigin ?? options.crossOrigin,
            onTileLoadError: options.onTileLoadError,
          }),
          opacity: scene.opacity ?? options.opacity ?? 0.9,
          visible: scene.visible !== false && options.visible !== false,
        });
      }

      const imageUrl = scene.imageUrl || scene.url || (scene.blob ? URL.createObjectURL(scene.blob) : "");
      if (!imageUrl) throw new Error("Scene needs tileUrl, imageUrl, url or blob.");
      const layer = new ol.layer.Image({
        source: SourceAdapters.imageStatic({
          url: imageUrl,
          bounds: scene.bounds || options.bounds,
        }),
        opacity: scene.opacity ?? options.opacity ?? 0.86,
        visible: scene.visible !== false && options.visible !== false,
      });
      if (scene.blob && !scene.imageUrl && !scene.url) layer.set("objectUrl", imageUrl);
      return layer;
    },

    tianditu(options = {}) {
      return createTiandituLayers(options);
    },
  };

  class LayerManager {
    constructor(map, options = {}) {
      assertOpenLayers();
      this.map = map;
      this.defaultGroup = options.defaultGroup || "remote-sensing";
      this.defaultZIndex = options.defaultZIndex ?? 10;
      this.entries = new Map();
    }

    add(scene, options = {}) {
      return this.addScene(scene, options);
    }

    addScene(scene, options = {}) {
      if (!scene?.id) throw new Error("Scene id is required.");
      const layer = this.createLayerFromScene(scene, options);
      return this.addLayer(scene.id, layer, {
        ...options,
        scene,
        title: scene.name,
        group: options.group || scene.group || this.defaultGroup,
        zIndex: scene.zIndex ?? options.zIndex ?? this.defaultZIndex,
      });
    }

    addLayer(id, layer, metadata = {}) {
      if (!id) throw new Error("Layer id is required.");
      this.remove(id);
      const group = metadata.group || this.defaultGroup;
      const zIndex = metadata.zIndex;
      layer.set("sdkLayerId", id);
      layer.set("sdkGroup", group);
      if (metadata.title) layer.set("title", metadata.title);
      if (metadata.scene?.id) layer.set("sceneId", metadata.scene.id);
      if (metadata.scene?.name) layer.set("sceneName", metadata.scene.name);
      if (zIndex !== undefined && zIndex !== null) layer.setZIndex(zIndex);
      this.map.addLayer(layer);
      const entry = {
        id,
        layer,
        group,
        scene: metadata.scene || null,
        metadata,
        objectUrl: layer.get("objectUrl"),
      };
      this.entries.set(id, entry);
      return layer;
    }

    addGroup(group, layers, options = {}) {
      this.removeGroup(group);
      return layers.map((layer, index) => {
        const id = `${group}:${options.ids?.[index] || index}`;
        return this.addLayer(id, layer, {
          ...options,
          group,
          zIndex: options.zIndex !== undefined ? options.zIndex + index : layer.getZIndex(),
        });
      });
    }

    createLayerFromScene(scene, options = {}) {
      return SourceAdapters.scene(scene, options);
    }

    createTileLayer(scene, options = {}) {
      return SourceAdapters.scene({ ...scene, layerType: "xyz" }, options);
    }

    createStaticImageLayer(scene, options = {}) {
      return SourceAdapters.scene({ ...scene, layerType: "imageStatic" }, options);
    }

    syncScenes(scenes, options = {}) {
      const group = options.group || this.defaultGroup;
      this.removeGroup(group);
      return scenes.map((scene, index) =>
        this.addScene(
          {
            ...scene,
            visible: options.visible === false ? false : scene.visible,
            zIndex: scene.zIndex ?? options.zIndex ?? this.defaultZIndex + index,
          },
          { ...options, group },
        ),
      );
    }

    remove(id) {
      const entry = this.entries.get(id);
      if (!entry) return;
      this.map.removeLayer(entry.layer);
      if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl);
      this.entries.delete(id);
    }

    removeGroup(group) {
      [...this.entries.values()]
        .filter((entry) => entry.group === group)
        .forEach((entry) => this.remove(entry.id));
    }

    setOpacity(id, opacity) {
      this.entries.get(id)?.layer.setOpacity(Number(opacity));
    }

    setVisible(id, visible) {
      this.entries.get(id)?.layer.setVisible(Boolean(visible));
    }

    setGroupVisible(group, visible) {
      [...this.entries.values()]
        .filter((entry) => entry.group === group)
        .forEach((entry) => entry.layer.setVisible(Boolean(visible)));
    }

    get(id) {
      return this.entries.get(id) || null;
    }

    list(group) {
      return [...this.entries.values()].filter((entry) => !group || entry.group === group);
    }

    fit(id, options = {}) {
      const entry = this.entries.get(id);
      if (!entry) return false;
      const extent = this.resolveExtent(entry, options);
      if (!extent) return false;
      this.map.getView().fit(extent, {
        padding: options.padding || [84, 430, 84, 84],
        maxZoom: options.maxZoom || 16,
        duration: options.duration || 260,
      });
      return true;
    }

    resolveExtent(entry, options = {}) {
      const bounds = options.bounds || entry.scene?.bounds || entry.metadata?.bounds;
      if (bounds) return ol.proj.transformExtent(parseBounds(bounds), "EPSG:4326", "EPSG:3857");
      const source = entry.layer.getSource?.();
      const extent = source?.getExtent?.();
      if (extent && !ol.extent.isEmpty(extent)) return extent;
      return null;
    }

    clear() {
      [...this.entries.keys()].forEach((id) => this.remove(id));
    }
  }

  class RemoteSensingClient {
    constructor(options = {}) {
      this.map = options.map || null;
      this.remote =
        options.remote ||
        new RemoteCogCatalog({
          baseUrl: options.apiBase || options.baseUrl || "",
          token: options.token,
          context: options.context,
          headers: options.headers,
          csrfToken: options.csrfToken,
          credentials: options.credentials,
        });
      this.catalog = options.catalog || null;
      this.layers = options.layers || (this.map ? new LayerManager(this.map, options.layerOptions) : null);
      this.scenes = [];
    }

    setMap(map, layerOptions = {}) {
      this.map = map;
      this.layers = new LayerManager(map, layerOptions);
      return this.layers;
    }

    setApiBase(baseUrl) {
      this.remote.setBaseUrl(baseUrl);
    }

    setAuthToken(token = "") {
      this.remote.setToken(token);
    }

    setAuthContext(context = {}) {
      this.remote.setContext(context);
    }

    health() {
      return this.remote.health();
    }

    async listRemoteScenes(params = {}) {
      this.scenes = await this.remote.list(params);
      return this.scenes;
    }

    uploadCog(file, metadata = {}) {
      return this.remote.upload(file, metadata);
    }

    removeRemoteScene(id) {
      return this.remote.remove(id);
    }

    updateSceneAccess(id, payload = {}) {
      return this.remote.updateSceneAccess(id, payload);
    }

    bulkUpdateSceneAccess(payload = {}) {
      return this.remote.bulkUpdateSceneAccess(payload);
    }

    registerFile(payload = {}) {
      return this.remote.registerFile(payload);
    }

    async listTasks() {
      const data = await this.remote.listTasks();
      return data.tasks || [];
    }

    getTask(id) {
      return this.remote.getTask(id);
    }

    geoserverConfig() {
      return this.remote.geoserverConfig();
    }

    geoserverLayers() {
      return this.remote.geoserverLayers();
    }

    tileCacheStatus() {
      return this.remote.tileCacheStatus();
    }

    clearTileCache(sceneId = "") {
      return this.remote.clearTileCache(sceneId);
    }

    pruneTileCache(options = {}) {
      return this.remote.pruneTileCache(options);
    }

    tiandituCacheStatus() {
      return this.remote.tiandituCacheStatus();
    }

    clearTiandituCache(layer = "") {
      return this.remote.clearTiandituCache(layer);
    }

    pruneTiandituCache(options = {}) {
      return this.remote.pruneTiandituCache(options);
    }

    async syncCogScenes(options = {}) {
      if (!this.layers) throw new Error("Map layer manager is not initialized.");
      const scenes = await this.listRemoteScenes(options.params || {});
      this.layers.syncScenes(scenes, {
        group: options.group || "remote-cog",
        visible: options.visible,
        zIndex: options.zIndex ?? 10,
        opacity: options.opacity,
        onTileLoadError: options.onTileLoadError,
      });
      return scenes;
    }

    addScene(scene, options = {}) {
      if (!this.layers) throw new Error("Map layer manager is not initialized.");
      return this.layers.addScene(scene, options);
    }

    addTiandituBasemap(options = {}) {
      if (!this.layers) throw new Error("Map layer manager is not initialized.");
      const group = options.group || `tianditu-${options.type || "img"}`;
      const layers = createTiandituLayers(options);
      this.layers.addGroup(group, layers, {
        group,
        ids: ["base", "label"],
        zIndex: options.zIndex ?? 0,
      });
      this.layers.setGroupVisible(group, options.visible !== false);
      return layers;
    }
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
    LayerManager,
    RemoteSensingClient,
    SceneLayerController,
    SourceAdapters,
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
