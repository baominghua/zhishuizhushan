# Remote Sensing SDK

这是卫星图传管理系统和智慧竹山管理系统共用的浏览器端遥感 SDK。它不替代 GeoServer、TiTiler、SuperMap 这类 GIS 服务，而是负责在浏览器里统一接入、管理和展示地图数据。

## 职责边界

- **数据处理层**：GDAL 把 GeoTIFF/TIFF 转为 COG。
- **GIS 服务层**：TiTiler/rio-tiler 发布 COG 瓦片接口，后续也可以接 GeoServer WMS/WMTS。
- **SDK 层**：封装 OpenLayers 图层、数据源适配器、天地图底图、COG 场景同步、图层分组和显隐控制。
- **应用层**：卫星图传管理页、智慧竹山页面只处理业务表单、按钮、列表和权限。

## 当前能力

- 本地小图：PNG/JPG/WebP 存入 IndexedDB，并通过 `ImageStatic` 叠加显示。
- 超大影像：GeoTIFF/TIFF 上传后端，GDAL 转 COG，再通过 XYZ 瓦片显示。
- 天地图底图：支持影像、矢量、地形三套底图。
- 图层管理：支持按组注册、移除、显隐、透明度、定位。
- 数据源适配：内置 `XYZ`、`TileWMS`、`WMTS`、`ImageStatic`、`Vector`、`Tianditu`。

## 前端快速使用

```js
const map = RemoteSensingSDK.createMap({
  target: "rsMap",
  center: [118.2, 26.6],
  zoom: 9,
});

const client = new RemoteSensingSDK.RemoteSensingClient({
  apiBase: "http://127.0.0.1:8010",
  map,
  layerOptions: {
    defaultGroup: "remote-cog",
    defaultZIndex: 10,
  },
});

await client.health();
const scenes = await client.syncCogScenes({
  group: "remote-cog",
  zIndex: 10,
});

const taskResult = await client.registerFile({
  path: "inbox/zhushan-2026.tif",
  name: "竹山 2026 正射影像",
});

const tasks = await client.listTasks();

const geoserver = await client.geoserverConfig();
const source = RemoteSensingSDK.SourceAdapters.geoserverWms({
  wmsUrl: geoserver.wmsUrl,
  layer: "workspace:layer",
});

const cache = await client.tileCacheStatus();
```

## 图层管理

```js
const layers = new RemoteSensingSDK.LayerManager(map, {
  defaultGroup: "catalog-scenes",
});

layers.add(scene, { group: "catalog-scenes" });
layers.setVisible(scene.id, true);
layers.setOpacity(scene.id, 0.82);
layers.fit(scene.id);
layers.removeGroup("catalog-scenes");
```

`SceneLayerController` 仍然保留，用于兼容旧代码；新页面建议使用 `LayerManager`。

## 数据源适配器

```js
const source = RemoteSensingSDK.SourceAdapters.tileWms({
  url: "https://example.com/geoserver/wms",
  params: {
    LAYERS: "workspace:layer",
    TILED: true,
  },
});

const layer = new ol.layer.Tile({ source });
layers.addLayer("wms-layer", layer, { group: "business-vector", zIndex: 20 });
```

## 后端服务

后端代码位于 `server/`：

- `POST /api/scenes/upload`：上传 GeoTIFF/TIFF，并转为 COG。
- `POST /api/scenes/register`：注册服务器/NAS 已有文件，创建后台 COG 转换任务。
- `GET /api/tasks`：查询后台转换任务列表。
- `GET /api/geoserver/config`：查询 GeoServer 配置。
- `GET /api/geoserver/layers`：查询 GeoServer 图层。
- `GET /api/cache/tiles`：查询瓦片缓存状态。
- `GET /api/scenes`：返回 COG 场景目录。
- `GET /api/scenes/{id}/tiles/{z}/{x}/{y}.png`：OpenLayers 可加载的 XYZ 瓦片。
- `GET /api/health`：检查 GDAL、rio-tiler、TiTiler 状态。

运行：

```powershell
.\start-cog-server.ps1
```

打开：

```text
http://127.0.0.1:8010/satellite-manager.html
http://127.0.0.1:8010/zhushan-bigdata.html
```
