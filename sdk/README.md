# Remote Sensing SDK

`remote-sensing-sdk.js` 是卫星图传管理系统的浏览器侧 SDK，当前已经支持两条影像链路：

- 小图直显：PNG/JPG/WebP 存入 IndexedDB，并用 OpenLayers `ImageStatic` 叠加显示。
- 超大图链路：GeoTIFF/TIFF 上传到后端，后端用 GDAL 转 COG，再通过 TiTiler/rio-tiler 风格 XYZ 瓦片接口给 OpenLayers 加载。
- 天地图底图：填写天地图 `tk` 后，可加载影像、矢量或地形 WMTS 底图。

## 前端 API

```js
const localCatalog = new RemoteSensingSDK.RasterCatalog();
await localCatalog.open();

const remoteCatalog = new RemoteSensingSDK.RemoteCogCatalog({
  baseUrl: "http://127.0.0.1:8010",
});

const health = await remoteCatalog.health();
const serverScenes = await remoteCatalog.list();

const scene = await remoteCatalog.upload(file, {
  name: "竹山春季正射影像",
  satellite: "GF-2",
  sensor: "PMS",
  bounds: [117.55, 26.05, 118.85, 27.2],
});

const map = RemoteSensingSDK.createMap({
  target: "rsMap",
  offlineGeojson: window.FUJIAN_BASEMAP_GEOJSON,
});

const layers = new RemoteSensingSDK.SceneLayerController(map);
layers.add(scene);
layers.fit(scene.id);
```

## 关键对象

- `RasterCatalog`：浏览器 IndexedDB 本地影像目录。
- `RemoteCogCatalog`：后端 COG/TiTiler 服务客户端。
- `SceneLayerController`：统一管理本地静态图层和远端 XYZ 瓦片图层。
- `createSceneFromFile()`：把 PNG/JPG/WebP 转成本地场景对象。
- `createTiandituLayers()`：创建天地图底图和注记图层。
- `isGeoRasterFile()`：识别 GeoTIFF/TIFF，决定是否走 COG 后端。

## 后端

后端代码位于 `server/`：

- `POST /api/scenes/upload`：上传 GeoTIFF/TIFF 并转 COG。
- `GET /api/scenes/{id}/tiles/{z}/{x}/{y}.png`：OpenLayers XYZ 瓦片。
- `GET /api/health`：GDAL、rio-tiler、TiTiler 状态。

运行：

```powershell
.\start-cog-server.ps1
```

打开：

```text
http://127.0.0.1:8010/satellite-manager.html
```
