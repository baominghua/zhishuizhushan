import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Box, Crosshair, Database, Globe2, Layers3, Minus, Plus, RotateCcw, Save, ScanSearch } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { ForestBlockFeatureCollection, ImageryAsset } from "../api/types";
import type { Spatial3dDisplaySettings } from "../components/CesiumGlobe";
import { ImageClarityStatus } from "../components/ImageClarityStatus";
import { OpenLayersMap } from "../components/OpenLayersMap";
import { QueryState } from "../components/QueryState";
import type { MapAreaFocusRequest, MapLayerState, MapSceneModel, MapViewMetrics, MapViewport, MapZoomRequest } from "../maps/scene";

const CesiumGlobe = lazy(async () => ({ default: (await import("../components/CesiumGlobe")).CesiumGlobe }));

const EMPTY_FEATURES: ForestBlockFeatureCollection = {
  type: "FeatureCollection",
  meta: { total: 0, returned: 0, maxFeatures: 0, truncated: false, zoom: 16, geometryMode: "full", simplificationTolerance: 0 },
  features: [],
};

const DEFAULT_VIEWPORT: MapViewport = { bbox: [117.65, 27.47, 117.78, 27.62], zoom: 16 };
const DEFAULT_SETTINGS: Spatial3dDisplaySettings = { opacity: 1, pointSize: 3, colorMode: "rgb", eastOffset: 0, northOffset: 0, heightOffset: 0 };
type PointInformationMode = "rgb" | "elevation" | "return" | "intensity" | "trajectory";

function viewerMode(asset?: ImageryAsset) {
  const requested = new URLSearchParams(window.location.search).get("mode");
  if (requested === "2d" || requested === "3d") return requested;
  return asset?.tilesetUrl ? "3d" : "2d";
}

function sceneForAsset(asset?: ImageryAsset): MapSceneModel {
  const bounds = asset?.bounds;
  const longitude = bounds?.length === 4 ? (bounds[0] + bounds[2]) / 2 : 117.7135;
  const latitude = bounds?.length === 4 ? (bounds[1] + bounds[3]) / 2 : 27.5448;
  return { home: { longitude, latitude, zoom2d: 16, height3d: 3_000 }, selectedBlock: null };
}

function formatNumber(value?: number) {
  return value ? new Intl.NumberFormat("zh-CN").format(value) : "未提供";
}

function formatBytes(value?: number) {
  if (!value) return "未提供";
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
}

function formatElevationRange(bounds?: ImageryAsset["nativeBounds"]) {
  if (!bounds || bounds.length !== 6) return "未提供";
  const minimum = Number(bounds[2]);
  const maximum = Number(bounds[5]);
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) return "未提供";
  return `${minimum.toFixed(2)}–${maximum.toFixed(2)} 米`;
}

function calibrationKey(assetId: string) {
  return `smart-bamboo-v2-spatial-calibration:${assetId}`;
}

export function AssetViewerPage() {
  const viewerContext = useMemo(() => {
    const search = new URLSearchParams(window.location.search);
    return {
      sceneId: search.get("sceneId") || "",
      blockId: search.get("blockId") || "",
    };
  }, []);
  const { sceneId, blockId } = viewerContext;
  const returnHref = blockId ? `/v2/map?blockId=${encodeURIComponent(blockId)}` : "/v2/map";
  const assetQuery = useQuery({ queryKey: ["imagery-asset-viewer", sceneId], queryFn: () => api.imageryAsset(sceneId), enabled: Boolean(sceneId), staleTime: 60_000 });
  const mapConfig = useQuery({ queryKey: ["map-config"], queryFn: api.mapConfig, staleTime: 60_000 });
  const asset = assetQuery.data;
  const mode = viewerMode(asset);
  const [showBasemap, setShowBasemap] = useState(false);
  const [metrics, setMetrics] = useState<MapViewMetrics | null>(null);
  const [quality, setQuality] = useState<"smooth" | "standard" | "detail">("standard");
  const [zoomRequest, setZoomRequest] = useState<MapZoomRequest>({ sequence: 0, direction: "in" });
  const [homeRequest, setHomeRequest] = useState(0);
  const [viewport, setViewport] = useState(DEFAULT_VIEWPORT);
  const [loadProgress, setLoadProgress] = useState({ pending: 0, processing: 0, ready: false });
  const [settings, setSettings] = useState<Spatial3dDisplaySettings>(DEFAULT_SETTINGS);
  const [pointInformationMode, setPointInformationMode] = useState<PointInformationMode>("rgb");
  const scene = useMemo(() => sceneForAsset(asset), [asset]);
  const focusRequest = useMemo<MapAreaFocusRequest>(() => ({
    sequence: asset?.bounds?.length === 4 ? 1 : 0,
    bbox: asset?.bounds?.length === 4 ? asset.bounds : DEFAULT_VIEWPORT.bbox,
  }), [asset]);
  const layers = useMemo<MapLayerState>(() => ({
    imagery: mode === "2d" && showBasemap,
    labels: false,
    forestBlocks: false,
    droneImagery: mode === "2d",
    spatial3d: mode === "3d",
  }), [mode, showBasemap]);

  useEffect(() => {
    if (!asset) return;
    const assetSettings = {
      ...DEFAULT_SETTINGS,
      elevationMinimum: asset.nativeBounds?.[2],
      elevationMaximum: asset.nativeBounds?.[5],
      returnProperty: asset.pointCloudRenderableProperties?.return,
      intensityProperty: asset.pointCloudRenderableProperties?.intensity,
    };
    try {
      const saved = window.localStorage.getItem(calibrationKey(asset.id));
      setSettings(saved ? { ...assetSettings, ...JSON.parse(saved) } : assetSettings);
    } catch {
      setSettings(assetSettings);
    }
    setPointInformationMode("rgb");
  }, [asset]);

  const pointAttributeModes = useMemo(() => new Set(asset?.pointCloudAttributeModes ?? []), [asset?.pointCloudAttributeModes]);
  const pointRenderableModes = useMemo(() => new Set(asset?.pointCloudRenderableModes ?? ["rgb", "elevation"]), [asset?.pointCloudRenderableModes]);
  const pointDimensionSummary = useMemo(() => {
    const labels: string[] = [];
    if (pointAttributeModes.has("rgb")) labels.push("RGB");
    if (pointAttributeModes.has("elevation")) labels.push("高程");
    if (pointAttributeModes.has("return")) labels.push("回波");
    if (pointAttributeModes.has("intensity")) labels.push("反射强度");
    if (pointAttributeModes.has("gps-time")) labels.push("GPS 时间");
    return labels;
  }, [pointAttributeModes]);

  const selectPointInformationMode = (mode: PointInformationMode) => {
    setPointInformationMode(mode);
    if (mode === "rgb" || mode === "elevation" || mode === "return" || mode === "intensity") {
      setSettings((current) => ({ ...current, colorMode: mode }));
    }
  };

  const requestZoom = (direction: MapZoomRequest["direction"]) => setZoomRequest((current) => ({ sequence: current.sequence + 1, direction }));
  const onSpatialLoadProgress = useCallback((progress: { pending: number; processing: number; ready: boolean }) => setLoadProgress(progress), []);
  const updateOffset = (key: "eastOffset" | "northOffset" | "heightOffset", value: string) => {
    const number = Number(value);
    setSettings((current) => ({ ...current, [key]: Number.isFinite(number) ? number : 0 }));
  };
  const saveCalibration = () => {
    if (!asset) return;
    window.localStorage.setItem(calibrationKey(asset.id), JSON.stringify(settings));
  };
  const resetCalibration = () => {
    setSettings({
      ...DEFAULT_SETTINGS,
      elevationMinimum: asset?.nativeBounds?.[2],
      elevationMaximum: asset?.nativeBounds?.[5],
    });
    if (asset) window.localStorage.removeItem(calibrationKey(asset.id));
  };

  return (
    <main className="asset-viewer-page">
      <header className="asset-viewer-header">
        <div>
          <a href={returnHref} className="icon-button" aria-label={blockId ? "返回林班详情" : "返回 GIS 一张图"} title={blockId ? "返回林班详情" : "返回 GIS 一张图"}><ArrowLeft aria-hidden="true" /></a>
          <span><small>{mode === "3d" ? "独立三维场景" : "独立二维影像"}</small><strong>{asset?.name || "成果查看器"}</strong></span>
        </div>
        <div className="asset-viewer-actions">
          {mode === "2d" ? (
            <button className={`button secondary ${showBasemap ? "active" : ""}`} type="button" onClick={() => setShowBasemap((value) => !value)}>
              <Globe2 aria-hidden="true" />{showBasemap ? "关闭参考底图" : "显示参考底图"}
            </button>
          ) : (
            <div className="asset-quality-switch" aria-label="三维画质">
              {(["smooth", "standard", "detail"] as const).map((item) => <button type="button" className={quality === item ? "active" : ""} onClick={() => setQuality(item)} key={item}>{item === "smooth" ? "流畅" : item === "standard" ? "标准" : "精细"}</button>)}
            </div>
          )}
          <button className="icon-button" type="button" onClick={() => requestZoom("out")} aria-label="缩小"><Minus /></button>
          <button className="icon-button" type="button" onClick={() => requestZoom("in")} aria-label="放大"><Plus /></button>
          <button className="button secondary" type="button" onClick={() => setHomeRequest((value) => value + 1)}><Crosshair />回到成果</button>
        </div>
      </header>

      <QueryState loading={assetQuery.isLoading || mapConfig.isLoading} error={assetQuery.error || mapConfig.error}>
        {asset && mapConfig.data ? (
          <div className="asset-viewer-layout">
            <section className="asset-viewer-stage">
              {mode === "2d" ? (
                <OpenLayersMap
                  config={mapConfig.data}
                  scene={scene}
                  layers={layers}
                  homeRequest={homeRequest}
                  zoomRequest={zoomRequest}
                  areaFocusRequest={focusRequest}
                  featureCollection={EMPTY_FEATURES}
                  selectedBlockId={null}
                  onSelectBlock={() => undefined}
                  onViewportChange={setViewport}
                  onViewMetricsChange={setMetrics}
                  imageryAssets={[asset]}
                  forestBlockFilterQuery=""
                  situationAssets={[]}
                  detailMode
                />
              ) : (
                <Suspense fallback={<div className="map-service-state">正在启动独立三维查看器</div>}>
                  <CesiumGlobe
                    config={mapConfig.data}
                    scene={scene}
                    layers={layers}
                    homeRequest={homeRequest}
                    zoomRequest={zoomRequest}
                    areaFocusRequest={{ sequence: 0, bbox: viewport.bbox }}
                    featureCollection={EMPTY_FEATURES}
                    selectedBlockId={null}
                    onSelectBlock={() => undefined}
                    onViewportChange={setViewport}
                    imageryAssets={[]}
                    spatial3dAssets={[asset]}
                    targetSpatialAssetId={asset.id}
                    spatial3dDisplaySettings={{ [asset.id]: settings }}
                    situationAssets={[]}
                    detailMode={quality === "detail"}
                    qualityMode={quality}
                    onSpatialLoadProgress={onSpatialLoadProgress}
                  />
                </Suspense>
              )}
              {mode === "2d" ? <ImageClarityStatus metrics={metrics} asset={asset} /> : (
                <div className={`asset-load-status ${loadProgress.ready ? "ready" : ""}`}><Layers3 /><span>{loadProgress.ready ? "当前视野已精细化" : `正在加载：${loadProgress.pending} 个请求，${loadProgress.processing} 个瓦片处理中`}</span></div>
              )}
            </section>

            <aside className="asset-viewer-panel">
              <section><header><Database /><div><small>成果信息</small><strong>{asset.name}</strong></div></header><dl>
                <div><dt>坐标系</dt><dd>{asset.crs || "未识别"}</dd></div>
                <div><dt>成果格式</dt><dd>{mode === "3d" ? asset.tilesetContentType?.toUpperCase() || "3D Tiles" : "COG / WebP 瓦片"}</dd></div>
                <div><dt>数据容量</dt><dd>{formatBytes(asset.size)}</dd></div>
                {mode === "2d" ? <><div><dt>原图像素</dt><dd>{asset.width} × {asset.height}</dd></div><div><dt>地面分辨率</dt><dd>{asset.metresPerPixel ? `${asset.metresPerPixel} 米/像素` : asset.resolution}</dd></div><div><dt>最高有效层级</dt><dd>Z {asset.maximumZoom ?? 22}</dd></div></> : <><div><dt>点数量</dt><dd>{formatNumber(asset.pointCount)}</dd></div><div><dt>内容瓦片</dt><dd>{formatNumber(asset.tileCount)}</dd></div><div><dt>原始高程范围</dt><dd>{formatElevationRange(asset.nativeBounds)}</dd></div></>}
              </dl></section>

              {mode === "3d" && <>
                <section><header><ScanSearch /><div><small>点云显示</small><strong>大疆信息视图</strong></div></header><div className="point-attribute-switch">
                  <button className={pointInformationMode === "rgb" ? "active" : ""} type="button" onClick={() => selectPointInformationMode("rgb")}>RGB</button>
                  <button className={pointInformationMode === "elevation" ? "active" : ""} type="button" disabled={!pointRenderableModes.has("elevation")} onClick={() => selectPointInformationMode("elevation")}>高程</button>
                  <button className={pointInformationMode === "return" ? "active" : ""} type="button" disabled={!pointRenderableModes.has("return")} title={pointRenderableModes.has("return") ? "按当前 PNTS 的回波字段分级着色" : "原始 LAS 有回波，但当前网页瓦片未保留该字段"} onClick={() => selectPointInformationMode("return")}>回波</button>
                  <button className={pointInformationMode === "intensity" ? "active" : ""} type="button" disabled={!pointRenderableModes.has("intensity")} title={pointRenderableModes.has("intensity") ? "按当前 PNTS 的反射强度字段分级着色" : "原始 LAS 有反射强度，但当前网页瓦片未保留该字段"} onClick={() => selectPointInformationMode("intensity")}>反射强度</button>
                  <button className={pointInformationMode === "trajectory" ? "active" : ""} type="button" disabled={!asset.trajectoryAvailable} onClick={() => selectPointInformationMode("trajectory")}>轨迹</button>
                </div>
                <div className="point-source-summary"><strong>PNTS 与 LAS 已合并关联</strong><span>{pointDimensionSummary.length ? `原始 LAS：${pointDimensionSummary.join(" · ")}` : "当前成果仅含网页瓦片，尚未登记原始 LAS"}</span><small>{asset.pointCloudSourcePaths?.length ? `${asset.pointCloudSourcePaths.length} 个 LAS/LAZ 源文件 · ` : ""}{asset.trajectoryAvailable ? `DJI 轨迹：${asset.trajectoryFileCount ?? 0} 个文件（${asset.trajectoryFormats?.join(" / ") || "POS"}）` : "未发现 terra_trajectory 轨迹侧车目录"}</small></div>
                <p className="asset-viewer-hint">{pointInformationMode === "trajectory" ? "轨迹资料已登记；POS/SBET 可用于后续抽稀航迹叠加。" : `当前 PNTS 可直接显示：${["rgb", "elevation", "return", "intensity"].filter((item) => pointRenderableModes.has(item as "rgb" | "elevation" | "return" | "intensity")).map((item) => ({ rgb: "RGB", elevation: "高程", return: "回波", intensity: "反射强度" })[item]).join("、") || "RGB"}。LAS 仅作为源数据，不会与 PNTS 重复绘制。`}</p><label className="asset-range"><span>点大小 <strong>{settings.pointSize.toFixed(1)}</strong></span><input type="range" min="1" max="10" step="0.5" value={settings.pointSize} onChange={(event) => setSettings((current) => ({ ...current, pointSize: Number(event.target.value) }))} /></label></section>
                <section><header><Box /><div><small>模型校准</small><strong>本地坐标偏移</strong></div></header><div className="calibration-grid"><label><span>向东（米）</span><input type="number" step="0.1" value={settings.eastOffset ?? 0} onChange={(event) => updateOffset("eastOffset", event.target.value)} /></label><label><span>向北（米）</span><input type="number" step="0.1" value={settings.northOffset ?? 0} onChange={(event) => updateOffset("northOffset", event.target.value)} /></label><label><span>高程（米）</span><input type="number" step="0.1" value={settings.heightOffset ?? 0} onChange={(event) => updateOffset("heightOffset", event.target.value)} /></label></div><div className="calibration-actions"><button className="button primary" type="button" onClick={saveCalibration}><Save />保存本机校准</button><button className="button secondary" type="button" onClick={resetCalibration}><RotateCcw />恢复原值</button></div><p className="asset-viewer-hint">当前先保存到本机浏览器；正式控制点配准通过后再写入平台资产版本。</p></section>
              </>}
            </aside>
          </div>
        ) : null}
      </QueryState>
    </main>
  );
}
