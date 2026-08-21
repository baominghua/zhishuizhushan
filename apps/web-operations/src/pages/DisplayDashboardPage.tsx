import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  Activity,
  Battery,
  Building2,
  Camera,
  Check,
  CircleDollarSign,
  Clock3,
  Expand,
  ExternalLink,
  Globe2,
  HardHat,
  Leaf,
  Layers,
  Map as MapIcon,
  MapPinned,
  Minimize,
  MonitorCog,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Plane,
  Play,
  Radio,
  RefreshCw,
  Route,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Trees,
  UsersRound,
  Warehouse,
  Wifi,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "../api/client";
import type { CockpitMetric, CockpitRankingItem, ForestBlockFeatureCollection, ForestBlockOption, ImageryAsset, SituationAssetKind, SituationAssetRecord } from "../api/types";
import type { Spatial3dDisplaySettings } from "../components/CesiumGlobe";
import { MapCanvas } from "../components/MapCanvas";
import { createMapScene, DEFAULT_MAP_LAYERS, DEFAULT_MAP_VIEWPORT, type MapLayerState, type MapViewport, type MapViewMode } from "../maps/scene";
import {
  buildMapAnnotations,
  DEFAULT_MAP_ANNOTATION_VISIBILITY,
  filterMapAnnotations,
  MAP_ANNOTATION_KINDS,
  MAP_ANNOTATION_LABELS,
  type MapAnnotation,
  type MapAnnotationKind,
} from "../maps/mapAnnotations";

const EMPTY_FEATURES: ForestBlockFeatureCollection = {
  type: "FeatureCollection",
  meta: { total: 0, returned: 0, maxFeatures: 0, truncated: false, zoom: 10, geometryMode: "full", simplificationTolerance: 0 },
  features: [],
};

const OVERVIEW_METRICS: Array<[string, string, LucideIcon]> = [
  ["forestAreaMu", "竹林资源面积", Trees],
  ["forestBlockCount", "正式林班", MapPinned],
  ["annualYieldTons", "年度预测产量", Activity],
  ["annualOutputValue", "年度预计产值", CircleDollarSign],
];

const CARBON_METRICS: Array<[string, string, LucideIcon]> = [
  ["totalCarbonStock", "碳储量", Trees],
  ["annualSequestration", "年度碳汇量", Leaf],
  ["projectCount", "碳汇项目", Activity],
  ["ccerRegisteredAmount", "CCER 核证量", ShieldAlert],
];

function spatialAssetFormat(asset: ImageryAsset) {
  if (asset.tilesetContentType?.toLowerCase() === "pnts" || asset.tileFormats?.pnts) return "PNTS 点云";
  if (asset.tilesetContentType?.toLowerCase() === "b3dm" || asset.tileFormats?.b3dm) return "B3DM 实景模型";
  return asset.assetType === "pointcloud" ? "三维点云" : "三维模型";
}

function isPointCloudAsset(asset: ImageryAsset) {
  return asset.assetType === "pointcloud" || asset.tilesetContentType?.toLowerCase() === "pnts" || Boolean(asset.tileFormats?.pnts);
}

export function DisplayDashboardPage() {
  const [now, setNow] = useState(() => new Date());
  const [topic, setTopic] = useState<"overview" | "carbon">("overview");
  const [fullscreen, setFullscreen] = useState(Boolean(document.fullscreenElement));
  const [mode, setMode] = useState<MapViewMode>("2d");
  const [detailMode, setDetailMode] = useState(false);
  const [leftRailOpen, setLeftRailOpen] = useState(true);
  const [rightRailOpen, setRightRailOpen] = useState(true);
  const [filterOpen, setFilterOpen] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [searchDraft, setSearchDraft] = useState("");
  const [searchKeyword, setSearchKeyword] = useState("");
  const [visibleKinds, setVisibleKinds] = useState<Record<MapAnnotationKind, boolean>>(DEFAULT_MAP_ANNOTATION_VISIBILITY);
  const [selectedSituationAsset, setSelectedSituationAsset] = useState<SituationAssetRecord | null>(null);
  const [selectedMapAnnotation, setSelectedMapAnnotation] = useState<MapAnnotation | null>(null);
  const [cameraPlaying, setCameraPlaying] = useState(true);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [viewport, setViewport] = useState<MapViewport>(DEFAULT_MAP_VIEWPORT);
  const [layers, setLayers] = useState<MapLayerState>(DEFAULT_MAP_LAYERS);
  const [enabledImageryAssetIds, setEnabledImageryAssetIds] = useState<Set<string> | null>(null);
  const [enabledSpatialAssetIds, setEnabledSpatialAssetIds] = useState<Set<string> | null>(null);
  const [focusedSpatialAssetId, setFocusedSpatialAssetId] = useState("");
  const [spatial3dDisplaySettings, setSpatial3dDisplaySettings] = useState<Record<string, Spatial3dDisplaySettings>>({});
  const dashboard = useQuery({ queryKey: ["display-dashboard"], queryFn: api.leadershipCockpit, refetchInterval: 60_000 });
  const mapConfig = useQuery({ queryKey: ["map-config"], queryFn: api.mapConfig, staleTime: 60_000 });
  const situationLedger = useQuery({ queryKey: ["display-situation-assets"], queryFn: api.situationAssets, refetchInterval: 30_000 });
  const annotationAssets = useQuery({
    queryKey: ["display-annotation-assets", viewport.bbox.join(",")],
    queryFn: () => api.imageryAssets({ bbox: viewport.bbox.join(","), limit: 100 }),
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  });
  const imageryAssets = useQuery({
    queryKey: ["display-published-imagery-assets", viewport.bbox.join(",")],
    queryFn: () => api.imageryAssets({ published: true, bbox: viewport.bbox.join(","), limit: 30 }),
    enabled: layers.droneImagery,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  });
  const spatial3dAssetsQuery = useQuery({
    queryKey: ["display-spatial-3d-assets", viewport.bbox.join(",")],
    queryFn: () => api.imageryAssets({ bbox: viewport.bbox.join(","), limit: 100 }),
    enabled: mode === "3d" && layers.spatial3d,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  });
  const mapBlocks = useQuery({
    queryKey: ["display-map-blocks", viewport.bbox.join(","), viewport.zoom, searchKeyword],
    queryFn: () => api.forestBlockMap({ bbox: viewport.bbox.join(","), zoom: viewport.zoom, maxFeatures: 2500, q: searchKeyword || undefined }),
    enabled: layers.forestBlocks,
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });
  const situationBlocks = useQuery({
    queryKey: ["display-situation-blocks", viewport.bbox.join(","), viewport.zoom],
    queryFn: () => api.forestBlockMap({ bbox: viewport.bbox.join(","), zoom: viewport.zoom, maxFeatures: 2500 }),
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });
  const selectedBlock = useQuery({
    queryKey: ["display-block", selectedBlockId],
    queryFn: () => api.forestBlockDetail(selectedBlockId!),
    enabled: Boolean(selectedBlockId),
  });
  const blockSearch = useQuery({
    queryKey: ["display-block-search", searchDraft],
    queryFn: () => api.forestBlocks({ q: searchDraft.trim(), limit: 8 }),
    enabled: filterOpen && searchDraft.trim().length > 0,
    staleTime: 30_000,
  });
  const scene = useMemo(() => createMapScene(null), []);
  const data = dashboard.data;
  const metrics = topic === "overview" ? OVERVIEW_METRICS : CARBON_METRICS;
  const ranking = (data?.carbon.districtRanking ?? []) as CockpitRankingItem[];
  const allMapAnnotations = useMemo(() => buildMapAnnotations({
    blocks: situationBlocks.data,
    situationRecords: situationLedger.data?.items,
    imageryAssets: annotationAssets.data?.scenes,
  }), [annotationAssets.data?.scenes, situationBlocks.data, situationLedger.data?.items]);
  const situationAssets = useMemo(
    () => filterMapAnnotations(allMapAnnotations, visibleKinds, searchKeyword),
    [allMapAnnotations, searchKeyword, visibleKinds],
  );
  const selectedBlockAnnotations = useMemo(
    () => selectedBlock.data
      ? allMapAnnotations.filter((annotation) => annotation.blockCode === selectedBlock.data.blockCode)
      : [],
    [allMapAnnotations, selectedBlock.data],
  );
  const visibleImageryAssets = useMemo(
    () => (imageryAssets.data?.scenes ?? []).filter((asset) => asset.visible !== false && (asset.assetType || "orthophoto") === "orthophoto"),
    [imageryAssets.data?.scenes],
  );
  const displayedImageryAssets = useMemo(
    () => enabledImageryAssetIds === null ? [] : visibleImageryAssets.filter((asset) => enabledImageryAssetIds.has(asset.id)),
    [enabledImageryAssetIds, visibleImageryAssets],
  );
  const visibleSpatial3dAssets = useMemo(
    () => (spatial3dAssetsQuery.data?.scenes ?? []).filter((asset) => asset.visible !== false && Boolean(asset.tilesetUrl)
      && asset.processingStage !== "coverage-review" && ["pointcloud", "oblique3d"].includes(asset.assetType)),
    [spatial3dAssetsQuery.data?.scenes],
  );
  const displayedSpatial3dAssets = useMemo(
    () => enabledSpatialAssetIds === null ? [] : visibleSpatial3dAssets.filter((asset) => enabledSpatialAssetIds.has(asset.id)),
    [enabledSpatialAssetIds, visibleSpatial3dAssets],
  );
  const selectedAnnotationAssets = useMemo(() => {
    if (selectedMapAnnotation?.sourceType !== "imagery") return [];
    const ids = new Set(selectedMapAnnotation.sourceIds ?? (selectedMapAnnotation.sourceId ? [selectedMapAnnotation.sourceId] : []));
    return (annotationAssets.data?.scenes ?? []).filter((asset) => ids.has(asset.id));
  }, [annotationAssets.data?.scenes, selectedMapAnnotation]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1_000);
    const updateFullscreen = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", updateFullscreen);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("fullscreenchange", updateFullscreen);
    };
  }, []);

  useEffect(() => {
    if (visibleImageryAssets.length === 0) return;
    setEnabledImageryAssetIds((current) => {
      if (current && visibleImageryAssets.some((asset) => current.has(asset.id))) return current;
      return new Set([visibleImageryAssets[0].id]);
    });
  }, [visibleImageryAssets]);

  useEffect(() => {
    if (enabledSpatialAssetIds !== null || visibleSpatial3dAssets.length === 0) return;
    const initialId = visibleSpatial3dAssets[0].id;
    setEnabledSpatialAssetIds(new Set([initialId]));
    setFocusedSpatialAssetId(initialId);
  }, [enabledSpatialAssetIds, visibleSpatial3dAssets]);

  async function toggleFullscreen() {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  }

  function refreshAll() {
    dashboard.refetch();
    mapConfig.refetch();
    annotationAssets.refetch();
    imageryAssets.refetch();
    spatial3dAssetsQuery.refetch();
  }

  function toggleLayer(layer: keyof MapLayerState) {
    setLayers((current) => ({ ...current, [layer]: !current[layer] }));
  }

  function toggleImageryAsset(id: string) {
    setEnabledImageryAssetIds((current) => {
      const next = new Set(current ?? []);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleSpatialAsset(id: string) {
    setEnabledSpatialAssetIds((current) => {
      const next = new Set(current ?? []);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function showOnlyImageryAsset(id: string) {
    setEnabledImageryAssetIds(new Set([id]));
    setLayers((current) => ({ ...current, droneImagery: true }));
  }

  function showOnlySpatialAsset(id: string) {
    setEnabledSpatialAssetIds(new Set([id]));
    setFocusedSpatialAssetId(id);
    setLayers((current) => ({ ...current, spatial3d: true }));
  }

  function updateSpatialAssetDisplay(id: string, patch: Partial<Spatial3dDisplaySettings>) {
    setSpatial3dDisplaySettings((current) => ({
      ...current,
      [id]: { ...(current[id] ?? { opacity: 1, pointSize: 3 }), ...patch },
    }));
  }

  function applySearch() {
    setSearchKeyword(searchDraft.trim());
  }

  function resetSearch() {
    setSearchDraft("");
    setSearchKeyword("");
    setVisibleKinds(DEFAULT_MAP_ANNOTATION_VISIBILITY);
  }

  function selectSearchResult(block: ForestBlockOption) {
    setSelectedBlockId(block.id);
    setSearchDraft(block.name || block.code);
    setSearchKeyword(block.name || block.code);
    setFilterOpen(false);
  }

  return (
    <main className="display-dashboard">
      <header className="display-header">
        <Link className="display-brand" to="/workspace" aria-label="返回工作台"><span>竹</span><strong>南平市智慧竹山综合运营平台</strong></Link>
        <nav className="display-topic-tabs" aria-label="大屏专题">
          <button className={topic === "overview" ? "active" : ""} type="button" onClick={() => setTopic("overview")}>综合态势</button>
          <button className={topic === "carbon" ? "active" : ""} type="button" onClick={() => setTopic("carbon")}>碳汇专题</button>
        </nav>
        <div className="display-head-actions">
          <time><Clock3 aria-hidden="true" />{now.toLocaleString("zh-CN", { hour12: false })}</time>
          <span className={dashboard.isError ? "offline" : "online"}><i />{dashboard.isError ? "数据异常" : "数据在线"}</span>
          <Link className="display-admin-link" to="/workspace"><MonitorCog /><span>进入运营后台</span></Link>
          <button type="button" onClick={toggleFullscreen} title={fullscreen ? "退出全屏" : "进入全屏"} aria-label={fullscreen ? "退出全屏" : "进入全屏"}>{fullscreen ? <Minimize /> : <Expand />}</button>
          <button type="button" onClick={refreshAll} title="刷新数据" aria-label="刷新数据"><RefreshCw /></button>
        </div>
      </header>

      <section className={`display-body ${leftRailOpen ? "left-rail-open" : ""} ${rightRailOpen ? "right-rail-open" : ""}`}>
        <aside className={`display-rail display-left-rail ${leftRailOpen ? "" : "is-collapsed"}`} aria-hidden={!leftRailOpen}>
          <RailHeading action={<button type="button" onClick={() => setLeftRailOpen(false)} title="收起左侧看板" aria-label="收起左侧看板"><PanelLeftClose /></button>}>竹林资源概况</RailHeading>
          <div className="display-metrics">
            {metrics.map(([key, label, icon]) => <DisplayMetric key={key} icon={icon} label={label} metric={(topic === "overview" ? data?.overview[key] : data?.carbon[key]) as CockpitMetric | undefined} />)}
          </div>
          <div className="display-legend">
            <strong>图例</strong><span><i className="normal" />林班边界</span><span><i className="risk" />风险林班</span><span><i className="selected" />当前选中</span>
          </div>
        </aside>

        <section className="display-map" aria-label="竹林资源 GIS 态势图">
          {!leftRailOpen && <button className="display-rail-reopen left" type="button" onClick={() => setLeftRailOpen(true)} title="展开左侧看板" aria-label="展开左侧看板"><PanelLeftOpen /></button>}
          {!rightRailOpen && <button className="display-rail-reopen right" type="button" onClick={() => setRightRailOpen(true)} title="展开右侧看板" aria-label="展开右侧看板"><PanelRightOpen /></button>}
          <div className="display-map-mode" aria-label="地图视角">
            <button className={mode === "2d" ? "active" : ""} type="button" onClick={() => setMode("2d")} aria-pressed={mode === "2d"}><MapIcon /><span>二维</span></button>
            <button className={mode === "3d" ? "active" : ""} type="button" onClick={() => setMode("3d")} aria-pressed={mode === "3d"}><Globe2 /><span>三维</span></button>
            <button className={detailMode ? "active" : ""} type="button" onClick={() => setDetailMode((value) => !value)} aria-pressed={detailMode} title="继续放大并提高三维细节"><Search /><span>精细</span></button>
          </div>
          <button className={`display-filter-trigger ${filterOpen ? "active" : ""}`} type="button" onClick={() => { setFilterOpen((current) => !current); setLayersOpen(false); }} aria-expanded={filterOpen} aria-controls="display-map-filter"><SlidersHorizontal /><span>搜索筛选</span>{searchKeyword && <i />}</button>
          <button className={`display-layer-trigger ${layersOpen ? "active" : ""}`} type="button" onClick={() => { setLayersOpen((current) => !current); setFilterOpen(false); }} aria-expanded={layersOpen} aria-controls="display-map-layers"><Layers /><span>地图图层</span></button>
          {filterOpen && <section className="display-map-filter" id="display-map-filter" aria-label="地图搜索筛选">
            <header><strong>搜索与图层</strong><button type="button" onClick={() => setFilterOpen(false)} aria-label="关闭搜索筛选"><X /></button></header>
            <form onSubmit={(event) => { event.preventDefault(); applySearch(); }}>
              <label><Search /><input value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="林班编号、名称、乡镇或设备" autoFocus /></label>
              <button type="submit">搜索</button>
            </form>
            {searchDraft.trim() && <div className="display-search-results">
              {blockSearch.isLoading && <span>正在检索正式林班</span>}
              {(blockSearch.data?.items ?? []).map((block) => <button key={block.id} type="button" onClick={() => selectSearchResult(block)}><span><strong>{block.name}</strong><small>{block.code} · {block.location || "区划待补"}</small></span><MapPinned /></button>)}
              {!blockSearch.isLoading && blockSearch.data?.items.length === 0 && <span>未找到匹配的正式林班</span>}
            </div>}
            <fieldset><legend>设备、影像与示范点</legend>{MAP_ANNOTATION_KINDS.map((kind) => <label key={kind}><input type="checkbox" checked={visibleKinds[kind]} onChange={() => setVisibleKinds((current) => ({ ...current, [kind]: !current[kind] }))} /><span><Check />{MAP_ANNOTATION_LABELS[kind]}</span></label>)}</fieldset>
            <footer><button type="button" onClick={resetSearch}>重置</button><small>与 GIS 一张图使用同一套成果关联和示范点标签</small></footer>
          </section>}
          {layersOpen && <section className="display-map-layers" id="display-map-layers" aria-label="地图图层">
            <header><div><strong>地图图层</strong><small>与 GIS 一张图共享正式成果</small></div><button type="button" onClick={() => setLayersOpen(false)} aria-label="关闭地图图层"><X /></button></header>
            <div className="display-layer-list">
              <label><input type="checkbox" checked={layers.imagery} onChange={() => toggleLayer("imagery")} /><span><strong>卫星影像</strong><small>天地遥感底图</small></span></label>
              <label><input type="checkbox" checked={layers.forestBlocks} onChange={() => toggleLayer("forestBlocks")} /><span><strong>林班边界</strong><small>正式空间地块</small></span></label>
              <label><input type="checkbox" checked={layers.labels} onChange={() => toggleLayer("labels")} /><span><strong>地名注记</strong><small>道路与行政区注记</small></span></label>
              <label><input type="checkbox" checked={layers.droneImagery} onChange={() => toggleLayer("droneImagery")} /><span><strong>无人机正射成果</strong><small>{visibleImageryAssets.length} 个可用成果</small></span></label>
              {layers.droneImagery && visibleImageryAssets.map((asset) => <div className="display-layer-asset" key={asset.id}><label><input type="checkbox" checked={enabledImageryAssetIds?.has(asset.id) ?? false} onChange={() => toggleImageryAsset(asset.id)} /><span><strong>{asset.name}</strong><small>最高 {asset.maximumZoom ?? 22} 级</small></span></label><button type="button" onClick={() => showOnlyImageryAsset(asset.id)}>仅看此项</button><a href={`/v2/asset-viewer?sceneId=${encodeURIComponent(asset.id)}&mode=2d`} target="_blank" rel="noreferrer" title="独立查看"><ExternalLink /></a></div>)}
              <label><input type="checkbox" checked={layers.spatial3d} disabled={mode !== "3d"} onChange={() => toggleLayer("spatial3d")} /><span><strong>三维点云与模型</strong><small>{mode !== "3d" ? "切换到三维后可用" : `${visibleSpatial3dAssets.length} 个可用成果`}</small></span></label>
              {mode === "3d" && layers.spatial3d && visibleSpatial3dAssets.map((asset) => <div className="display-layer-asset spatial" key={asset.id}><label><input type="checkbox" checked={enabledSpatialAssetIds?.has(asset.id) ?? false} onChange={() => toggleSpatialAsset(asset.id)} /><span><strong>{asset.name}</strong><small>{spatialAssetFormat(asset)}</small></span></label><button type="button" onClick={() => showOnlySpatialAsset(asset.id)}>仅看此项</button><a href={`/v2/asset-viewer?sceneId=${encodeURIComponent(asset.id)}&mode=3d`} target="_blank" rel="noreferrer" title="独立查看"><ExternalLink /></a>{enabledSpatialAssetIds?.has(asset.id) && <label className="display-layer-slider"><span>{isPointCloudAsset(asset) ? "点大小" : "透明度"}</span><input type="range" min={isPointCloudAsset(asset) ? 1 : 0.1} max={isPointCloudAsset(asset) ? 8 : 1} step={isPointCloudAsset(asset) ? 1 : 0.1} value={isPointCloudAsset(asset) ? spatial3dDisplaySettings[asset.id]?.pointSize ?? 3 : spatial3dDisplaySettings[asset.id]?.opacity ?? 1} onChange={(event) => updateSpatialAssetDisplay(asset.id, isPointCloudAsset(asset) ? { pointSize: Number(event.target.value) } : { opacity: Number(event.target.value) })} /></label>}</div>)}
            </div>
          </section>}
          <MapCanvas
            config={mapConfig.data}
            loading={mapConfig.isLoading}
            mode={mode}
            scene={scene}
            layers={layers}
            homeRequest={0}
            zoomRequest={{ sequence: 0, direction: "in" }}
            areaFocusRequest={{ sequence: 0, bbox: DEFAULT_MAP_VIEWPORT.bbox }}
            featureCollection={layers.forestBlocks ? mapBlocks.data ?? EMPTY_FEATURES : EMPTY_FEATURES}
            selectedBlockId={selectedBlockId}
            onSelectBlock={(id) => { setSelectedMapAnnotation(null); setSelectedBlockId(id); }}
            onViewportChange={setViewport}
            imageryAssets={displayedImageryAssets}
            spatial3dAssets={displayedSpatial3dAssets}
            targetSpatialAssetId={focusedSpatialAssetId || undefined}
            spatial3dDisplaySettings={spatial3dDisplaySettings}
            forestBlockFilterQuery={searchKeyword ? new URLSearchParams({ q: searchKeyword }).toString() : ""}
            situationAssets={situationAssets}
            onSelectSituationAsset={(id) => {
              const annotation = allMapAnnotations.find((item) => item.id === id);
              const asset = annotation?.sourceType === "situation"
                ? situationLedger.data?.items.find((item) => item.id === annotation.sourceId)
                : undefined;
              if (asset) {
                setSelectedSituationAsset(asset as SituationAssetRecord);
                setCameraPlaying(true);
                setSelectedBlockId(null);
                setSelectedMapAnnotation(null);
              } else if (annotation) {
                setSelectedMapAnnotation(annotation);
                setSelectedBlockId(null);
              }
            }}
            detailMode={detailMode}
          />
          <div className="display-map-title"><span>竹林资源一张图</span><small>{mode === "3d" ? "三维地球" : "二维地图"} · 当前层级 {viewport.zoom} · 点击林班查看空间台账</small></div>
          <div className="display-demo-note"><Radio /><span>统一空间标注</span><small>{situationAssets.length} 个设备、影像或示范点</small></div>
          {selectedBlockId && <article className="display-block-popover">
            <button type="button" onClick={() => setSelectedBlockId(null)} aria-label="关闭林班详情"><X /></button>
            {selectedBlock.isLoading ? <p>正在读取林班详情</p> : selectedBlock.data ? <>
              <small>当前林班</small><h2>{selectedBlock.data.name || selectedBlock.data.blockCode}</h2>
              {selectedBlockAnnotations.length > 0 && <div className="map-object-badges">{selectedBlockAnnotations.map((annotation) => <span className={`map-object-badge ${annotation.kind}`} key={annotation.id}>{MAP_ANNOTATION_LABELS[annotation.kind]}</span>)}</div>}
              <dl><div><dt>林班编号</dt><dd>{selectedBlock.data.blockCode}</dd></div><div><dt>行政区划</dt><dd>{[selectedBlock.data.townName, selectedBlock.data.villageName].filter(Boolean).join(" / ") || "未填写"}</dd></div><div><dt>面积</dt><dd>{selectedBlock.data.areaMu ?? "--"} 亩</dd></div><div><dt>风险等级</dt><dd>{selectedBlock.data.riskLevel || "未填写"}</dd></div></dl>
              <a href={`/v2/map?blockId=${encodeURIComponent(selectedBlock.data.id)}`}>进入 GIS 详情</a>
            </> : <p>该林班详情暂时无法读取</p>}
          </article>}
        </section>

        <aside className={`display-rail display-right-rail ${rightRailOpen ? "" : "is-collapsed"}`} aria-hidden={!rightRailOpen}>
          <RailHeading action={<button type="button" onClick={() => setRightRailOpen(false)} title="收起右侧看板" aria-label="收起右侧看板"><PanelRightClose /></button>}>运行监测</RailHeading>
          <div className="display-operations">
            <Operation icon={ShieldAlert} label="安全事件" metric={data?.operations.openSafetyEvents} tone="amber" />
            <Operation icon={Plane} label="无人机任务" metric={data?.operations.activeDroneMissions} tone="cyan" />
            <Operation icon={Leaf} label="年度碳汇量" metric={data?.carbon.annualSequestration as CockpitMetric | undefined} tone="green" />
          </div>
          <RailHeading>区划碳汇排名</RailHeading>
          {ranking.length ? <div className="display-ranking">{ranking.slice(0, 5).map((item, index) => <div key={item.name}><b>{String(index + 1).padStart(2, "0")}</b><span>{item.name}</span><em>{item.annualSequestration.toLocaleString("zh-CN")} tCO₂e</em></div>)}</div> : <div className="display-empty"><Leaf /><strong>暂无排名数据</strong><span>碳汇项目关联林班后自动汇总</span></div>}
        </aside>
      </section>

      {selectedSituationAsset && <SituationAssetDialog asset={selectedSituationAsset} playing={cameraPlaying} onTogglePlaying={() => setCameraPlaying((current) => !current)} onClose={() => setSelectedSituationAsset(null)} />}
      {selectedMapAnnotation && <DisplayAnnotationDialog annotation={selectedMapAnnotation} imageryAssets={selectedAnnotationAssets} onClose={() => setSelectedMapAnnotation(null)} onOpenBlock={selectedMapAnnotation.blockId ? () => { setSelectedBlockId(selectedMapAnnotation.blockId!); setSelectedMapAnnotation(null); } : undefined} />}

      <footer className="display-footer">
        <strong>运行动态</strong><span className="display-ticker"><i />数据范围：{data?.scope.areas.includes("*") ? "全市" : data?.scope.areas.join("、") || "读取中"}</span><span>林班、经营、安全、碳汇数据统一汇聚</span><time>数据时间：{data ? new Date(data.asOf).toLocaleString("zh-CN", { hour12: false }) : "同步中"}</time>
      </footer>
    </main>
  );
}

function DisplayAnnotationDialog({ annotation, imageryAssets, onClose, onOpenBlock }: { annotation: MapAnnotation; imageryAssets: ImageryAsset[]; onClose: () => void; onOpenBlock?: () => void }) {
  return <div className="display-device-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="display-device-dialog display-annotation-dialog" role="dialog" aria-modal="true" aria-labelledby="display-annotation-title">
      <header><span><Layers /></span><div><small>{MAP_ANNOTATION_LABELS[annotation.kind]} · 空间成果</small><h2 id="display-annotation-title">{annotation.label}</h2><p>{annotation.subtitle || "已纳入统一 GIS 空间台账"}</p></div><button type="button" onClick={onClose} aria-label="关闭空间成果详情"><X /></button></header>
      <dl>{annotation.blockCode && <div><dt>关联林班</dt><dd>{annotation.blockCode}</dd></div>}<div><dt>经度</dt><dd>{annotation.longitude.toFixed(6)}</dd></div><div><dt>纬度</dt><dd>{annotation.latitude.toFixed(6)}</dd></div><div><dt>成果数量</dt><dd>{imageryAssets.length || 1} 项</dd></div></dl>
      {imageryAssets.length > 0 && <div className="display-annotation-links">{imageryAssets.map((asset) => <a key={asset.id} href={`/v2/asset-viewer?sceneId=${encodeURIComponent(asset.id)}&mode=${asset.assetType === "orthophoto" ? "2d" : "3d"}`} target="_blank" rel="noreferrer"><ExternalLink />{asset.name}</a>)}</div>}
      <footer><span className="display-device-status online"><i />已入库</span><div>{onOpenBlock && <button type="button" onClick={onOpenBlock}>查看关联林班</button>}</div></footer>
    </section>
  </div>;
}

function SituationAssetIcon({ kind }: { kind: SituationAssetKind }) {
  if (kind === "camera") return <Camera />;
  if (kind === "helmet") return <HardHat />;
  if (kind === "dock") return <Warehouse />;
  return <Plane />;
}

function SituationAssetDialog({ asset, playing, onTogglePlaying, onClose }: { asset: SituationAssetRecord; playing: boolean; onTogglePlaying: () => void; onClose: () => void }) {
  return <div className="display-device-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="display-device-dialog" role="dialog" aria-modal="true" aria-labelledby="display-device-title">
      <header><span><SituationAssetIcon kind={asset.kind} /></span><div><small>{MAP_ANNOTATION_LABELS[asset.kind]} · 后台台账</small><h2 id="display-device-title">{asset.name}</h2><p>{asset.subtitle}</p></div><button type="button" onClick={onClose} aria-label="关闭设备详情"><X /></button></header>
      {asset.kind === "camera" && <div className={`display-camera-feed ${playing ? "is-playing" : "is-paused"}`}>
        <div className="camera-feed-scene"><Trees /><span className="camera-road" /><span className="camera-person"><UsersRound /></span></div>
        <div className="camera-feed-top"><span><i />LIVE</span><time>{new Date().toLocaleString("zh-CN", { hour12: false })}</time></div>
        <button type="button" onClick={onTogglePlaying}><Play />{playing ? "暂停画面" : "继续播放"}</button>
        <small>实时视频播放窗口为界面示范，接入 RTSP/GB28181 后替换为真实码流。</small>
      </div>}
      {asset.kind === "helmet" && <div className="display-track-preview"><Route /><div><strong>实时移动轨迹</strong><span>北向巡护路线 · 最近 28 分钟</span></div><svg viewBox="0 0 420 90" preserveAspectRatio="none" aria-hidden="true"><path d="M8 72 C65 28 112 64 165 38 S254 14 303 49 S361 76 412 18" /><circle cx="412" cy="18" r="6" /></svg></div>}
      {asset.kind === "mission" && <div className="display-mission-progress"><Plane /><span><i style={{ width: "68%" }} /></span><strong>68%</strong><small>任务航线持续回传中</small></div>}
      {asset.kind === "dock" && <div className="display-dock-status"><Warehouse /><div><strong>机巢待命正常</strong><span><Wifi />通信在线</span><span><Battery />充电 92%</span></div></div>}
      <dl>{asset.parameters.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <footer><span className={`display-device-status ${asset.status === "在线" || asset.status === "作业中" || asset.status === "飞行中" ? "online" : ""}`}><i />{asset.status}</span><a href={asset.managementPath}>打开后台台账</a></footer>
    </section>
  </div>;
}

function RailHeading({ children, action }: { children: string; action?: ReactNode }) { return <div className="display-rail-heading"><h2>{children}</h2>{action}</div>; }
function DisplayMetric({ icon: Icon, label, metric }: { icon: LucideIcon; label: string; metric?: CockpitMetric }) { return <article className="display-metric"><Icon /><span>{label}</span><strong>{metric?.available ? Number(metric.value || 0).toLocaleString("zh-CN") : "暂无数据"}</strong><small>{metric?.available ? `${metric.unit} · ${metric.source}` : "等待正式数据源"}</small></article>; }
function Operation({ icon: Icon, label, metric, tone }: { icon: LucideIcon; label: string; metric?: CockpitMetric; tone: string }) { return <article className={`display-operation ${tone}`}><Icon /><span>{label}</span><strong>{metric?.available ? `${metric.value || 0} ${metric.unit}` : "暂无数据"}</strong><small>{metric?.source || "等待正式数据源"}</small></article>; }
