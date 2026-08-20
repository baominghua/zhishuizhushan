import { useQuery } from "@tanstack/react-query";
import {
  Filter,
  Globe2,
  Layers,
  LocateFixed,
  Map as MapIcon,
  Maximize2,
  Minimize2,
  Search,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { type PointerEvent as ReactPointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type { ForestBlockOption, ForestBlockQuery, ImageryAsset } from "../api/types";
import type { Spatial3dDisplaySettings } from "../components/CesiumGlobe";
import { MapCanvas } from "../components/MapCanvas";
import { QueryState } from "../components/QueryState";
import {
  featureToOption,
  mergeSelectedForestBlock,
  recordToOption,
} from "../maps/forestBlocks";
import {
  createMapScene,
  DEFAULT_MAP_LAYERS,
  DEFAULT_MAP_VIEWPORT,
  type MapAreaFocusRequest,
  type MapLayerState,
  type MapViewport,
  type MapViewMode,
  type MapZoomRequest,
} from "../maps/scene";

const MAP_MODE_STORAGE_KEY = "smart-bamboo-v2-map-mode";

const MAPPED_TOWN_AREAS = [
  { name: "黄坑镇", bbox: [117.68, 27.54, 117.73, 27.59] as MapViewport["bbox"] },
  { name: "麻沙镇", bbox: [117.675, 27.495, 117.75, 27.575] as MapViewport["bbox"] },
];

type MapFilterValues = Pick<
  ForestBlockQuery,
  "countyCode" | "townCode" | "qualityGrade" | "healthStatus" | "riskLevel"
>;

const EMPTY_MAP_FILTERS: MapFilterValues = {
  countyCode: "",
  townCode: "",
  qualityGrade: "",
  healthStatus: "",
  riskLevel: "",
};

function filterQueryString(filters: MapFilterValues) {
  const search = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) search.set(key, value);
  });
  return search.toString();
}

function initialMapMode(): MapViewMode {
  const requestedMode = new URLSearchParams(window.location.search).get("mode");
  if (requestedMode === "2d" || requestedMode === "3d") return requestedMode;
  return window.localStorage.getItem(MAP_MODE_STORAGE_KEY) === "3d" ? "3d" : "2d";
}

function spatialAssetFormat(asset: ImageryAsset) {
  const contentType = asset.tilesetContentType?.toLowerCase();
  if (contentType === "pnts" || asset.tileFormats?.pnts) return "PNTS 点云";
  if (contentType === "b3dm" || asset.tileFormats?.b3dm) return "B3DM 实景模型";
  return asset.assetType === "pointcloud" ? "三维点云" : "三维模型";
}

export function MapPage() {
  const targetSceneId = useMemo(() => new URLSearchParams(window.location.search).get("sceneId") || "", []);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [draftFilters, setDraftFilters] = useState<MapFilterValues>(EMPTY_MAP_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<MapFilterValues>(EMPTY_MAP_FILTERS);
  const [activeTown, setActiveTown] = useState<string | null>("黄坑镇");
  const [selected, setSelected] = useState<ForestBlockOption | null>(null);
  const [detailPosition, setDetailPosition] = useState<{ x: number; y: number } | null>(null);
  const [detailMaximized, setDetailMaximized] = useState(false);
  const mapStageRef = useRef<HTMLDivElement>(null);
  const detailRef = useRef<HTMLElement>(null);
  const detailDragRef = useRef<{ pointerId: number; offsetX: number; offsetY: number } | null>(null);
  const [mode, setMode] = useState<MapViewMode>(initialMapMode);
  const [layers, setLayers] = useState<MapLayerState>(DEFAULT_MAP_LAYERS);
  const [enabledSpatialAssetIds, setEnabledSpatialAssetIds] = useState<Set<string> | null>(null);
  const [focusedSpatialAssetId, setFocusedSpatialAssetId] = useState(targetSceneId);
  const [spatial3dDisplaySettings, setSpatial3dDisplaySettings] = useState<Record<string, Spatial3dDisplaySettings>>({});
  const [homeRequest, setHomeRequest] = useState(0);
  const [zoomRequest, setZoomRequest] = useState<MapZoomRequest>({ sequence: 0, direction: "in" });
  const [areaFocusRequest, setAreaFocusRequest] = useState<MapAreaFocusRequest>({
    sequence: 0,
    bbox: DEFAULT_MAP_VIEWPORT.bbox,
  });
  const [viewport, setViewport] = useState<MapViewport>(DEFAULT_MAP_VIEWPORT);
  const scene = useMemo(() => createMapScene(selected), [selected]);

  const appliedFilterQuery = useMemo(() => filterQueryString(appliedFilters), [appliedFilters]);
  const appliedFilterCount = Object.values(appliedFilters).filter(Boolean).length;
  const filterFacets = useQuery({
    queryKey: ["forest-block-filter-facets"],
    queryFn: api.forestBlockFacets,
    enabled: filtersOpen,
    staleTime: 60_000,
  });
  const blocks = useQuery({
    queryKey: ["map-blocks", query, appliedFilters],
    queryFn: () => api.forestBlocks({ q: query, ...appliedFilters, limit: 100 }),
    enabled: resultsOpen,
    staleTime: 30_000,
  });
  const filterPreview = useQuery({
    queryKey: ["map-filter-preview", query, draftFilters],
    queryFn: () => api.forestBlocks({ q: query, ...draftFilters, limit: 1 }),
    enabled: filtersOpen,
    staleTime: 15_000,
  });
  const mapConfig = useQuery({
    queryKey: ["map-config"],
    queryFn: api.mapConfig,
    staleTime: 60_000,
  });
  const mapBlocks = useQuery({
    queryKey: ["forest-block-map", viewport.bbox.join(","), viewport.zoom, appliedFilters],
    queryFn: () => api.forestBlockMap({
      bbox: viewport.bbox.join(","),
      zoom: viewport.zoom,
      maxFeatures: 2000,
      ...appliedFilters,
    }),
    enabled: layers.forestBlocks && mode === "3d",
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });
  const imageryAssets = useQuery({
    queryKey: ["published-imagery-assets", viewport.bbox.join(",")],
    queryFn: () => api.imageryAssets({ published: true, bbox: viewport.bbox.join(","), limit: 30 }),
    enabled: layers.droneImagery,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  });
  const visibleImageryAssets = useMemo(
    () => (imageryAssets.data?.scenes ?? []).filter((asset) =>
      // DSM/DTM are elevation products, not colour basemaps. Rendering them as
      // ordinary RGB imagery creates opaque grey seams and doubles tile traffic.
      asset.visible !== false && (asset.assetType || "orthophoto") === "orthophoto"),
    [imageryAssets.data?.scenes],
  );
  const spatial3dAssetsQuery = useQuery({
    queryKey: ["spatial-3d-assets", viewport.bbox.join(",")],
    queryFn: () => api.imageryAssets({ bbox: viewport.bbox.join(","), limit: 100 }),
    enabled: mode === "3d" && layers.spatial3d,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  });
  const targetSpatialAsset = useQuery({
    queryKey: ["imagery-asset", targetSceneId],
    queryFn: () => api.imageryAsset(targetSceneId),
    enabled: Boolean(targetSceneId),
    staleTime: 60_000,
  });
  const visibleSpatial3dAssets = useMemo(() => {
    const items: ImageryAsset[] = [...(spatial3dAssetsQuery.data?.scenes ?? [])];
    if (targetSpatialAsset.data && !items.some((item) => item.id === targetSpatialAsset.data?.id)) {
      items.unshift(targetSpatialAsset.data);
    }
    return items.filter((asset) =>
      asset.visible !== false && Boolean(asset.tilesetUrl) && asset.processingStage !== "coverage-review"
      && ["pointcloud", "oblique3d"].includes(asset.assetType));
  }, [spatial3dAssetsQuery.data?.scenes, targetSpatialAsset.data]);
  const displayedSpatial3dAssets = useMemo(
    () => enabledSpatialAssetIds === null
      ? []
      : visibleSpatial3dAssets.filter((asset) => enabledSpatialAssetIds.has(asset.id)),
    [enabledSpatialAssetIds, visibleSpatial3dAssets],
  );
  const selectedDetail = useQuery({
    queryKey: ["forest-block-detail", selected?.id],
    queryFn: () => api.forestBlockDetail(selected!.id),
    enabled: Boolean(selected?.id && selected.hasGeometry),
    staleTime: 30_000,
  });
  const mapFeatures = useMemo(
    () => mergeSelectedForestBlock(mode === "3d" ? mapBlocks.data : undefined, selectedDetail.data),
    [mapBlocks.data, mode, selectedDetail.data],
  );

  useEffect(() => {
    window.localStorage.setItem(MAP_MODE_STORAGE_KEY, mode);
  }, [mode]);

  useEffect(() => {
    const blockId = new URLSearchParams(window.location.search).get("blockId");
    if (!blockId) return;
    let active = true;
    api.forestBlockDetail(blockId).then((record) => {
      if (!active) return;
      setSelected(recordToOption(record));
      setResultsOpen(false);
      setFiltersOpen(false);
      setLayers((current) => ({ ...current, forestBlocks: true }));
      const bbox = geometryBounds(record.geometry);
      if (bbox) setAreaFocusRequest((current) => ({ sequence: current.sequence + 1, bbox }));
    }).catch(() => {
      if (active) setResultsOpen(true);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const asset = targetSpatialAsset.data;
    if (!asset) return;
    if (asset.tilesetUrl) {
      if (asset.processingStage === "coverage-review") return;
      setMode("3d");
      setLayers((current) => ({ ...current, spatial3d: true }));
    } else if (asset.assetType === "orthophoto") {
      setLayers((current) => ({ ...current, droneImagery: true }));
    } else {
      return;
    }
    if (asset.bounds?.length === 4) {
      setAreaFocusRequest((current) => ({ sequence: current.sequence + 1, bbox: asset.bounds }));
    }
  }, [targetSpatialAsset.data]);

  useEffect(() => {
    if (enabledSpatialAssetIds !== null || visibleSpatial3dAssets.length === 0) return;
    const initialId = visibleSpatial3dAssets.some((asset) => asset.id === targetSceneId)
      ? targetSceneId
      : visibleSpatial3dAssets[0].id;
    setEnabledSpatialAssetIds(new Set([initialId]));
    setFocusedSpatialAssetId(initialId);
  }, [enabledSpatialAssetIds, targetSceneId, visibleSpatial3dAssets]);

  useEffect(() => {
    setDetailPosition(null);
    setDetailMaximized(false);
  }, [selected?.id]);

  function chooseMode(nextMode: MapViewMode) {
    setMode(nextMode);
    setHomeRequest((value) => value + 1);
  }

  function toggleLayer(layer: keyof MapLayerState) {
    setLayers((current) => ({ ...current, [layer]: !current[layer] }));
  }

  function toggleSpatialAsset(id: string) {
    setEnabledSpatialAssetIds((current) => {
      const next = new Set(current ?? []);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function showOnlySpatialAsset(id: string) {
    setEnabledSpatialAssetIds(new Set([id]));
    setFocusedSpatialAssetId(id);
    setLayers((current) => ({ ...current, spatial3d: true }));
  }

  function updateSpatialAssetDisplay(id: string, patch: Partial<Spatial3dDisplaySettings>) {
    setSpatial3dDisplaySettings((current) => {
      const existing = current[id] ?? { opacity: 1, pointSize: 3 };
      return { ...current, [id]: { ...existing, ...patch } };
    });
  }

  function requestZoom(direction: MapZoomRequest["direction"]) {
    setZoomRequest((current) => ({ sequence: current.sequence + 1, direction }));
  }

  function updateDraftFilter(key: keyof MapFilterValues, value: string) {
    setDraftFilters((current) => ({
      ...current,
      [key]: value,
      ...(key === "countyCode" ? { townCode: "" } : {}),
    }));
  }

  function applyMapFilters() {
    setAppliedFilters({ ...draftFilters });
    setSelected(null);
    setResultsOpen(true);
    setFiltersOpen(false);
  }

  function resetMapFilters() {
    setDraftFilters(EMPTY_MAP_FILTERS);
    setAppliedFilters(EMPTY_MAP_FILTERS);
    setSelected(null);
  }

  const availableTowns = (filterFacets.data?.towns ?? []).filter(
    (town) => !draftFilters.countyCode || town.countyCode === draftFilters.countyCode,
  );

  function focusMappedTown(name: string, bbox: MapViewport["bbox"]) {
    setQuery(name);
    setActiveTown(name);
    setSelected(null);
    setResultsOpen(false);
    setFiltersOpen(false);
    setLayersOpen(false);
    setAreaFocusRequest((current) => ({ sequence: current.sequence + 1, bbox }));
  }

  function openPendingTown(name: string) {
    setQuery(name);
    setActiveTown(name);
    setResultsOpen(true);
    setFiltersOpen(false);
    setLayersOpen(false);
  }

  const updateViewport = useCallback((next: MapViewport) => {
    const bbox = next.bbox.map((value) => Number(value.toFixed(5))) as MapViewport["bbox"];
    setViewport((current) => {
      const unchanged = current.zoom === next.zoom
        && current.bbox.every((value, index) => value === bbox[index]);
      return unchanged ? current : { bbox, zoom: next.zoom };
    });
  }, []);

  const selectMapBlock = useCallback(async (id: string) => {
    const feature = mapFeatures.features.find((candidate) => candidate.id === id);
    if (feature) {
      setSelected(featureToOption(feature));
      return;
    }
    try {
      setSelected(recordToOption(await api.forestBlockDetail(id)));
    } catch {
      // A tile may have gone stale between selection and detail loading.
    }
  }, [mapFeatures.features]);

  function startDetailDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (detailMaximized || !mapStageRef.current || !detailRef.current) return;
    const stage = mapStageRef.current.getBoundingClientRect();
    const detail = detailRef.current.getBoundingClientRect();
    detailDragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - detail.left,
      offsetY: event.clientY - detail.top,
    };
    setDetailPosition({ x: detail.left - stage.left, y: detail.top - stage.top });
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveDetail(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = detailDragRef.current;
    const stage = mapStageRef.current;
    const detail = detailRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !stage || !detail) return;
    const stageRect = stage.getBoundingClientRect();
    const maxX = Math.max(8, stageRect.width - detail.offsetWidth - 8);
    const maxY = Math.max(8, stageRect.height - detail.offsetHeight - 8);
    setDetailPosition({
      x: Math.min(maxX, Math.max(8, event.clientX - stageRect.left - drag.offsetX)),
      y: Math.min(maxY, Math.max(8, event.clientY - stageRect.top - drag.offsetY)),
    });
  }

  function stopDetailDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (detailDragRef.current?.pointerId !== event.pointerId) return;
    detailDragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  return (
    <div className="map-page">
      <div className="map-toolbar">
        <label className="map-search">
          <Search aria-hidden="true" />
          <input
            value={query}
            onFocus={() => setResultsOpen(true)}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveTown(null);
              setResultsOpen(true);
            }}
            placeholder="搜索林班编号、村名或乡镇"
          />
        </label>
        <div className="map-toolbar-actions">
          <div className="map-mode-switch" aria-label="地图视角">
            <button
              className={mode === "2d" ? "active" : ""}
              type="button"
              onClick={() => chooseMode("2d")}
              aria-pressed={mode === "2d"}
              title="切换到二维地图"
            >
              <MapIcon aria-hidden="true" />
              <span>二维</span>
            </button>
            <button
              className={mode === "3d" ? "active" : ""}
              type="button"
              onClick={() => chooseMode("3d")}
              aria-pressed={mode === "3d"}
              title="切换到三维地球"
            >
              <Globe2 aria-hidden="true" />
              <span>三维</span>
            </button>
          </div>
          <div className="map-zoom-controls" aria-label="地图缩放">
            <button
              className="icon-button"
              type="button"
              onClick={() => requestZoom("in")}
              aria-label="放大地图"
              title="放大地图"
            >
              <ZoomIn aria-hidden="true" />
            </button>
            <button
              className="icon-button"
              type="button"
              onClick={() => requestZoom("out")}
              aria-label="缩小地图"
              title="缩小地图"
            >
              <ZoomOut aria-hidden="true" />
            </button>
          </div>
          <button
            className="icon-button map-home-button"
            type="button"
            onClick={() => setHomeRequest((value) => value + 1)}
            aria-label="回到南平市全域"
            title="回到南平市全域"
          >
            <LocateFixed aria-hidden="true" />
          </button>
          <button
            className={`button secondary ${resultsOpen ? "active" : ""}`}
            type="button"
            onClick={() => {
              setResultsOpen((value) => !value);
              setFiltersOpen(false);
              setLayersOpen(false);
            }}
            aria-expanded={resultsOpen}
          >
            <Search aria-hidden="true" />结果
          </button>
          <button
            className={`button secondary ${filtersOpen ? "active" : ""}`}
            type="button"
            onClick={() => {
              setFiltersOpen((value) => !value);
              setResultsOpen(false);
              setLayersOpen(false);
            }}
            aria-expanded={filtersOpen}
          >
            <Filter aria-hidden="true" />筛选
            {appliedFilterCount > 0 && <span className="filter-count">{appliedFilterCount}</span>}
          </button>
          <button
            className={`button secondary ${layersOpen ? "active" : ""}`}
            type="button"
            onClick={() => {
              setLayersOpen((value) => !value);
              setResultsOpen(false);
              setFiltersOpen(false);
            }}
            aria-expanded={layersOpen}
          >
            <Layers aria-hidden="true" />图层
          </button>
        </div>
      </div>
      <div className="map-stage" ref={mapStageRef}>
        <nav className="map-town-shortcuts" aria-label="林班乡镇快速定位">
          {MAPPED_TOWN_AREAS.map((area) => (
            <button
              type="button"
              key={area.name}
              className={activeTown === area.name ? "active" : ""}
              onClick={() => focusMappedTown(area.name, area.bbox)}
              aria-pressed={activeTown === area.name}
            >
              {area.name}
            </button>
          ))}
          <button
            type="button"
            className={`pending ${activeTown === "小桥镇" ? "active" : ""}`}
            onClick={() => openPendingTown("小桥镇")}
            aria-pressed={activeTown === "小桥镇"}
          >
            小桥镇 <small>待补图</small>
          </button>
        </nav>
        <MapCanvas
          config={mapConfig.data}
          loading={mapConfig.isLoading}
          mode={mode}
          scene={scene}
          layers={layers}
          homeRequest={homeRequest}
          zoomRequest={zoomRequest}
          areaFocusRequest={areaFocusRequest}
          featureCollection={mapFeatures}
          selectedBlockId={selected?.id ?? null}
          onSelectBlock={selectMapBlock}
          onViewportChange={updateViewport}
          imageryAssets={visibleImageryAssets}
          spatial3dAssets={displayedSpatial3dAssets}
          targetSpatialAssetId={focusedSpatialAssetId || undefined}
          spatial3dDisplaySettings={spatial3dDisplaySettings}
          forestBlockFilterQuery={appliedFilterQuery}
        />
        {resultsOpen && (
          <aside className="map-results">
            <header>
              <div><strong>林班检索结果</strong><small>共 {blocks.data?.total ?? 0} 条</small></div>
              <button
                className="icon-button"
                type="button"
                onClick={() => setResultsOpen(false)}
                aria-label="关闭林班检索结果"
                title="关闭林班检索结果"
              >
                <X aria-hidden="true" />
              </button>
            </header>
            <QueryState loading={blocks.isLoading} error={blocks.error}>
              <div className="map-result-list">
                {(blocks.data?.items ?? []).map((block) => (
                  <button
                    type="button"
                    key={block.id}
                    className={selected?.id === block.id ? "selected" : ""}
                    onClick={() => {
                      setSelected(block);
                      setResultsOpen(false);
                    }}
                  >
                    <strong>{block.name}</strong>
                    <small>
                      {block.code} · {block.areaMu == null ? "面积待补" : `${block.areaMu} 亩`}
                      {!block.hasGeometry && " · 待补图"}
                    </small>
                  </button>
                ))}
                {blocks.data?.items.length === 0 && <p className="map-empty">当前条件下暂无林班数据</p>}
              </div>
            </QueryState>
          </aside>
        )}
        {filtersOpen && (
          <aside className="map-filter">
            <header>
              <div><strong>分层筛选</strong><small>按林班属性筛选地图</small></div>
              <button className="icon-button" type="button" onClick={() => setFiltersOpen(false)} aria-label="关闭筛选">
                <X aria-hidden="true" />
              </button>
            </header>
            <div className="map-filter-grid">
              <label><span>区县</span><select value={draftFilters.countyCode} onChange={(event) => updateDraftFilter("countyCode", event.target.value)}><option value="">全部区县</option>{(filterFacets.data?.counties ?? []).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
              <label><span>乡镇</span><select value={draftFilters.townCode} onChange={(event) => updateDraftFilter("townCode", event.target.value)}><option value="">全部乡镇</option>{availableTowns.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
              <label><span>质量等级</span><select value={draftFilters.qualityGrade} onChange={(event) => updateDraftFilter("qualityGrade", event.target.value)}><option value="">全部质量</option>{(filterFacets.data?.qualityGrades ?? []).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
              <label><span>健康状态</span><select value={draftFilters.healthStatus} onChange={(event) => updateDraftFilter("healthStatus", event.target.value)}><option value="">全部状态</option>{(filterFacets.data?.healthStatuses ?? []).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
              <label><span>风险等级</span><select value={draftFilters.riskLevel} onChange={(event) => updateDraftFilter("riskLevel", event.target.value)}><option value="">全部风险</option>{(filterFacets.data?.riskLevels ?? []).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            </div>
            {filterFacets.error && <p className="map-filter-error">筛选选项读取失败，请稍后重试</p>}
            <div className="map-filter-summary"><span>当前条件命中</span><strong>{filterPreview.isFetching ? "读取中" : `${filterPreview.data?.total ?? 0} 个林班`}</strong></div>
            <footer>
              <button className="button secondary" type="button" onClick={resetMapFilters} disabled={!Object.values(draftFilters).some(Boolean) && appliedFilterCount === 0}>重置</button>
              <button className="button primary" type="button" onClick={applyMapFilters}>应用筛选</button>
            </footer>
          </aside>
        )}
        {layersOpen && (
          <aside className="map-layer-panel">
            <header>
              <strong>地图图层</strong>
              <button className="icon-button" type="button" onClick={() => setLayersOpen(false)} aria-label="关闭图层面板">
                <X aria-hidden="true" />
              </button>
            </header>
            <label>
              <input type="checkbox" checked={layers.forestBlocks} onChange={() => toggleLayer("forestBlocks")} />
              <span>
                <strong>林班边界</strong>
                <small>
                  {mapBlocks.isFetching
                    ? "正在读取当前视窗"
                    : mode === "2d"
                      ? "矢量瓦片按视窗与层级加载"
                      : `${mapFeatures.meta.returned} 个空间地块${mapFeatures.meta.truncated ? "，已分层限流" : ""}`}
                </small>
              </span>
            </label>
            <label>
              <input type="checkbox" checked={layers.imagery} onChange={() => toggleLayer("imagery")} />
              <span><strong>卫星影像</strong><small>天地图影像底图</small></span>
            </label>
            <label>
              <input type="checkbox" checked={layers.droneImagery} onChange={() => toggleLayer("droneImagery")} />
              <span><strong>无人机正射成果</strong><small>{imageryAssets.isFetching ? "正在读取当前视窗" : `${visibleImageryAssets.length} 个已发布成果`}</small></span>
            </label>
            <label>
              <input type="checkbox" checked={layers.spatial3d} disabled={mode !== "3d"} onChange={() => toggleLayer("spatial3d")} />
              <span><strong>三维点云与模型</strong><small>{mode !== "3d" ? "切换到三维地球后可用" : spatial3dAssetsQuery.isFetching ? "正在校验当前视窗" : `${displayedSpatial3dAssets.length}/${visibleSpatial3dAssets.length} 个已显示`}</small></span>
            </label>
            {mode === "3d" && layers.spatial3d && visibleSpatial3dAssets.length > 0 && (
              <div className="map-spatial-assets" aria-label="三维成果列表">
                <small>同一区域默认只显示一项，可手动叠加对比</small>
                {visibleSpatial3dAssets.map((asset) => (
                  <div className="map-spatial-asset" key={asset.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={enabledSpatialAssetIds?.has(asset.id) ?? false}
                        onChange={() => toggleSpatialAsset(asset.id)}
                      />
                      <span><strong>{asset.name}</strong><small>{spatialAssetFormat(asset)}</small></span>
                    </label>
                    <button type="button" onClick={() => showOnlySpatialAsset(asset.id)}>仅看此项</button>
                    {(enabledSpatialAssetIds?.has(asset.id) ?? false) && (
                      <div className="map-spatial-controls">
                        <label>
                          <span>透明度</span>
                          <input
                            type="range"
                            min="0.1"
                            max="1"
                            step="0.1"
                            value={spatial3dDisplaySettings[asset.id]?.opacity ?? 1}
                            onChange={(event) => updateSpatialAssetDisplay(asset.id, { opacity: Number(event.target.value) })}
                          />
                        </label>
                        {spatialAssetFormat(asset).startsWith("PNTS") && (
                          <label>
                            <span>点大小</span>
                            <input
                              type="range"
                              min="1"
                              max="8"
                              step="1"
                              value={spatial3dDisplaySettings[asset.id]?.pointSize ?? 3}
                              onChange={(event) => updateSpatialAssetDisplay(asset.id, { pointSize: Number(event.target.value) })}
                            />
                          </label>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <label>
              <input type="checkbox" checked={layers.labels} onChange={() => toggleLayer("labels")} />
              <span><strong>地名注记</strong><small>道路与行政区注记</small></span>
            </label>
            {mapBlocks.error && <p className="map-layer-error">林班边界读取失败，请稍后重试</p>}
          </aside>
        )}
        {selected && (
          <aside
            className={`map-object ${detailPosition ? "positioned" : "centered"} ${detailMaximized ? "maximized" : ""}`}
            ref={detailRef}
            style={detailPosition && !detailMaximized ? { left: detailPosition.x, top: detailPosition.y } : undefined}
            aria-label="林班详情浮动窗口"
          >
            <div
              className="map-object-titlebar"
              onPointerDown={startDetailDrag}
              onPointerMove={moveDetail}
              onPointerUp={stopDetailDrag}
              onPointerCancel={stopDetailDrag}
            >
              <div><small>林班空间对象</small><strong>{selected.name}</strong></div>
              <div className="map-object-actions">
                <button
                  className="icon-button"
                  type="button"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={() => setDetailMaximized((value) => !value)}
                  aria-label={detailMaximized ? "还原详情窗口" : "放大详情窗口"}
                  title={detailMaximized ? "还原" : "放大"}
                >
                  {detailMaximized ? <Minimize2 aria-hidden="true" /> : <Maximize2 aria-hidden="true" />}
                </button>
                <button
                  className="icon-button"
                  type="button"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={() => setSelected(null)}
                  aria-label="关闭详情"
                  title="关闭"
                >
                  <X aria-hidden="true" />
                </button>
              </div>
            </div>
            <div className="map-object-body">
              <dl>
                <div><dt>林班编号</dt><dd>{selected.code}</dd></div>
                <div><dt>行政区划</dt><dd>{selected.location || "待补充"}</dd></div>
                <div><dt>面积</dt><dd>{selected.areaMu == null ? "待补充" : `${selected.areaMu} 亩`}</dd></div>
                <div><dt>空间边界</dt><dd>{selected.hasGeometry ? "已入库" : "待补图"}</dd></div>
              </dl>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

function geometryBounds(geometry: Record<string, unknown> | null): MapViewport["bbox"] | null {
  const coordinates = geometry?.coordinates;
  if (!Array.isArray(coordinates)) return null;
  let west = Infinity; let south = Infinity; let east = -Infinity; let north = -Infinity;
  const visit = (value: unknown) => {
    if (!Array.isArray(value)) return;
    if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") {
      west = Math.min(west, value[0]); south = Math.min(south, value[1]);
      east = Math.max(east, value[0]); north = Math.max(north, value[1]);
      return;
    }
    value.forEach(visit);
  };
  visit(coordinates);
  if (![west, south, east, north].every(Number.isFinite)) return null;
  const longitudePadding = Math.max((east - west) * 0.35, 0.002);
  const latitudePadding = Math.max((north - south) * 0.35, 0.002);
  return [west - longitudePadding, south - latitudePadding, east + longitudePadding, north + latitudePadding];
}
