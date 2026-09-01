import { useQuery } from "@tanstack/react-query";
import {
  BrainCircuit,
  Filter,
  ExternalLink,
  Globe2,
  Layers,
  LocateFixed,
  Map as MapIcon,
  ScanSearch,
  Maximize2,
  Minimize2,
  Search,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { type PointerEvent as ReactPointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type { ForestBlockOption, ForestBlockQuery, ForestRoadFeatureCollection, ImageryAsset, MosoInventoryEstimate, SituationAssetRecord } from "../api/types";
import type { Spatial3dDisplaySettings } from "../components/CesiumGlobe";
import { MapCanvas } from "../components/MapCanvas";
import { ImageClarityStatus } from "../components/ImageClarityStatus";
import { QueryState } from "../components/QueryState";
import {
  EMPTY_FOREST_BLOCK_COLLECTION,
  featureToOption,
  mergeForestBlockCollections,
  mergeSelectedForestBlock,
  recordToOption,
} from "../maps/forestBlocks";
import {
  createMapScene,
  DEFAULT_MAP_LAYERS,
  DEFAULT_MAP_VIEWPORT,
  type MapAreaFocusRequest,
  type MapLayerState,
  type MapViewMetrics,
  type MapViewport,
  type MapViewMode,
  type MapZoomRequest,
} from "../maps/scene";
import {
  buildMapAnnotations,
  DEFAULT_MAP_ANNOTATION_VISIBILITY,
  filterMapAnnotations,
  MAP_ANNOTATION_KINDS,
  MAP_ANNOTATION_LABELS,
  type MapAnnotation,
  type MapAnnotationKind,
} from "../maps/mapAnnotations";

const MAP_MODE_STORAGE_KEY = "smart-bamboo-v2-map-mode";

const EMPTY_FOREST_ROAD_COLLECTION: ForestRoadFeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

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

function expandViewportBbox(bbox: MapViewport["bbox"], ratio = 0.32): MapViewport["bbox"] {
  const [west, south, east, north] = bbox;
  const longitudePadding = Math.max(0.003, (east - west) * ratio);
  const latitudePadding = Math.max(0.003, (north - south) * ratio);
  return [
    Math.max(-180, west - longitudePadding),
    Math.max(-90, south - latitudePadding),
    Math.min(180, east + longitudePadding),
    Math.min(90, north + latitudePadding),
  ];
}

function townFocusBbox(centroid: [number, number]): MapViewport["bbox"] {
  const [longitude, latitude] = centroid;
  return [longitude - 0.038, latitude - 0.032, longitude + 0.038, latitude + 0.032];
}

function spatialAssetFormat(asset: ImageryAsset) {
  const contentType = asset.tilesetContentType?.toLowerCase();
  if (contentType === "pnts" || asset.tileFormats?.pnts) return "PNTS 点云";
  if (contentType === "b3dm" || asset.tileFormats?.b3dm) return "B3DM 实景模型";
  return asset.assetType === "pointcloud" ? "三维点云" : "三维模型";
}

function isPointCloudAsset(asset: ImageryAsset) {
  return asset.assetType === "pointcloud"
    || asset.tilesetContentType?.toLowerCase() === "pnts"
    || Boolean(asset.tileFormats?.pnts);
}

function assetViewerHref(sceneId: string, mode: "2d" | "3d", blockId?: string) {
  const search = new URLSearchParams({ sceneId, mode });
  if (blockId) search.set("blockId", blockId);
  return `/v2/asset-viewer?${search.toString()}`;
}

function mosoSandboxHref(blockId: string) {
  return `/v2/ai/moso-inventory-sandbox?${new URLSearchParams({ blockId }).toString()}`;
}

export function MapPage() {
  const targetSceneId = useMemo(() => new URLSearchParams(window.location.search).get("sceneId") || "", []);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [draftFilters, setDraftFilters] = useState<MapFilterValues>(EMPTY_MAP_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<MapFilterValues>(EMPTY_MAP_FILTERS);
  const [activeTown, setActiveTown] = useState<string | null>(null);
  const [selected, setSelected] = useState<ForestBlockOption | null>(null);
  const [selectedMapAnnotationId, setSelectedMapAnnotationId] = useState<string | null>(null);
  const [detailPosition, setDetailPosition] = useState<{ x: number; y: number } | null>(null);
  const [detailMaximized, setDetailMaximized] = useState(false);
  const mapStageRef = useRef<HTMLDivElement>(null);
  const detailRef = useRef<HTMLElement>(null);
  const detailDragRef = useRef<{ pointerId: number; offsetX: number; offsetY: number } | null>(null);
  const [mode, setMode] = useState<MapViewMode>(initialMapMode);
  const [detailMode, setDetailMode] = useState(false);
  const [showMapAnnotations, setShowMapAnnotations] = useState(true);
  const [annotationVisibility, setAnnotationVisibility] = useState<Record<MapAnnotationKind, boolean>>(
    DEFAULT_MAP_ANNOTATION_VISIBILITY,
  );
  const [layers, setLayers] = useState<MapLayerState>(DEFAULT_MAP_LAYERS);
  const [enabledImageryAssetIds, setEnabledImageryAssetIds] = useState<Set<string> | null>(null);
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
  const [viewMetrics, setViewMetrics] = useState<MapViewMetrics | null>(null);
  const scene = useMemo(() => createMapScene(selected), [selected]);
  const bufferedViewportBbox = useMemo(() => expandViewportBbox(viewport.bbox), [viewport.bbox]);

  const appliedFilterQuery = useMemo(() => filterQueryString(appliedFilters), [appliedFilters]);
  const appliedFilterCount = Object.values(appliedFilters).filter(Boolean).length;
  const filterFacets = useQuery({
    queryKey: ["forest-block-filter-facets"],
    queryFn: api.forestBlockFacets,
    enabled: filtersOpen,
    staleTime: 60_000,
  });
  const townAggregates = useQuery({
    queryKey: ["forest-block-town-aggregates"],
    queryFn: () => api.forestBlockAggregates("town"),
    staleTime: 5 * 60_000,
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
    queryKey: ["forest-block-map", bufferedViewportBbox.join(","), viewport.zoom, appliedFilters],
    queryFn: () => api.forestBlockMap({
      bbox: bufferedViewportBbox.join(","),
      zoom: viewport.zoom,
      maxFeatures: 2000,
      ...appliedFilters,
    }),
    enabled: layers.forestBlocks,
    staleTime: 30_000,
    gcTime: 15 * 60_000,
    placeholderData: (previous) => previous,
  });
  const [cachedMapBlocks, setCachedMapBlocks] = useState(EMPTY_FOREST_BLOCK_COLLECTION);
  const boundaryCacheFilterRef = useRef(appliedFilterQuery);
  const forestRoadMap = useQuery({
    queryKey: ["forest-road-map"],
    queryFn: api.forestRoadMap,
    enabled: layers.forestRoads,
    staleTime: 60_000,
    gcTime: 15 * 60_000,
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
  const displayedImageryAssets = useMemo(
    () => enabledImageryAssetIds === null
      ? []
      : visibleImageryAssets.filter((asset) => enabledImageryAssetIds.has(asset.id)),
    [enabledImageryAssetIds, visibleImageryAssets],
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
  const situationLedger = useQuery({
    queryKey: ["map-situation-assets"],
    queryFn: api.situationAssets,
    refetchInterval: 30_000,
  });
  const annotationAssets = useQuery({
    queryKey: ["map-annotation-assets"],
    // Asset tiles stay viewport-scoped, but relationship badges and map symbols must
    // also include legacy assets whose spatial index has not yet been backfilled.
    queryFn: () => api.imageryAssets({ limit: 1000 }),
    staleTime: 60_000,
    placeholderData: (previous) => previous,
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
  const selectedMosoInventory = selectedDetail.data?.yieldEstimate?.mosoInventory as MosoInventoryEstimate | undefined;
  const mapFeatures = useMemo(
    () => mergeSelectedForestBlock(mode === "3d" ? cachedMapBlocks : undefined, selectedDetail.data),
    [cachedMapBlocks, mode, selectedDetail.data],
  );
  const allMapAnnotations = useMemo(() => buildMapAnnotations({
    blocks: mapBlocks.data,
    situationRecords: situationLedger.data?.items,
    imageryAssets: annotationAssets.data?.scenes,
  }), [annotationAssets.data?.scenes, mapBlocks.data, situationLedger.data?.items]);
  const visibleMapAnnotations = useMemo(
    () => showMapAnnotations ? filterMapAnnotations(allMapAnnotations, annotationVisibility, query) : [],
    [allMapAnnotations, annotationVisibility, query, showMapAnnotations],
  );
  const selectedAnnotations = useMemo(
    () => selected ? allMapAnnotations.filter((annotation) => annotation.blockCode === selected.code) : [],
    [allMapAnnotations, selected],
  );
  const selectedMapAnnotation = useMemo(
    () => allMapAnnotations.find((annotation) => annotation.id === selectedMapAnnotationId) ?? null,
    [allMapAnnotations, selectedMapAnnotationId],
  );
  const selectedSituationRecord = useMemo(
    () => selectedMapAnnotation?.sourceType === "situation"
      ? situationLedger.data?.items.find((item) => item.id === selectedMapAnnotation.sourceId) ?? null
      : null,
    [selectedMapAnnotation, situationLedger.data?.items],
  );
  const selectedAnnotationAssets = useMemo(() => {
    if (selectedMapAnnotation?.sourceType !== "imagery") return [];
    const ids = new Set(selectedMapAnnotation.sourceIds ?? (selectedMapAnnotation.sourceId ? [selectedMapAnnotation.sourceId] : []));
    return (annotationAssets.data?.scenes ?? []).filter((asset) => ids.has(asset.id));
  }, [annotationAssets.data?.scenes, selectedMapAnnotation]);
  const selectedViewerLinks = useMemo(() => {
    const seen = new Set<string>();
    const assetsById = new Map((annotationAssets.data?.scenes ?? []).map((asset) => [asset.id, asset]));
    return selectedAnnotations.flatMap((annotation) => {
      if (annotation.sourceType !== "imagery") return [];
      return (annotation.sourceIds ?? (annotation.sourceId ? [annotation.sourceId] : [])).flatMap((id, index) => {
        if (seen.has(id)) return [];
        seen.add(id);
        const asset = assetsById.get(id);
        return [{
          id,
          label: index === 0 ? MAP_ANNOTATION_LABELS[annotation.kind] : `${MAP_ANNOTATION_LABELS[annotation.kind]} ${index + 1}`,
          assetName: asset?.name || "未命名影像成果",
          assetDetail: asset ? `${spatialAssetFormat(asset)} · ${asset.fileName || "成果文件"}` : "成果详情待补充",
          mode: annotation.kind === "orthophoto" ? "2d" as const : "3d" as const,
        }];
      });
    });
  }, [annotationAssets.data?.scenes, selectedAnnotations]);

  useEffect(() => {
    window.localStorage.setItem(MAP_MODE_STORAGE_KEY, mode);
  }, [mode]);

  useEffect(() => {
    const filterChanged = boundaryCacheFilterRef.current !== appliedFilterQuery;
    // Keep the last successful boundary layer visible while a new filter or
    // viewport request is in flight. Replace it atomically only after fresh
    // data arrives, avoiding the blank-map flash seen on slower connections.
    if (!mapBlocks.data || (filterChanged && mapBlocks.isPlaceholderData)) return;
    boundaryCacheFilterRef.current = appliedFilterQuery;
    setCachedMapBlocks((current) => mergeForestBlockCollections(
      filterChanged ? EMPTY_FOREST_BLOCK_COLLECTION : current,
      mapBlocks.data,
    ));
  }, [appliedFilterQuery, mapBlocks.data, mapBlocks.isPlaceholderData]);

  useEffect(() => {
    const selectedTownName = selectedDetail.data?.townName?.trim();
    if (selectedTownName) {
      setActiveTown(selectedTownName);
      return;
    }
    const counts = new Map<string, number>();
    mapBlocks.data?.features.forEach((feature) => {
      const townName = feature.properties.townName?.trim();
      if (townName) counts.set(townName, (counts.get(townName) ?? 0) + 1);
    });
    const currentTownName = [...counts.entries()].sort((left, right) => right[1] - left[1])[0]?.[0];
    if (currentTownName) setActiveTown(currentTownName);
  }, [mapBlocks.data, selectedDetail.data?.townName]);

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
    if (visibleImageryAssets.length === 0) return;
    setEnabledImageryAssetIds((current) => {
      if (current && visibleImageryAssets.some((asset) => current.has(asset.id))) return current;
      const initialId = visibleImageryAssets.some((asset) => asset.id === targetSceneId)
        ? targetSceneId
        : visibleImageryAssets[0].id;
      return new Set([initialId]);
    });
  }, [targetSceneId, visibleImageryAssets]);

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

  function toggleImageryAsset(id: string) {
    setEnabledImageryAssetIds((current) => {
      const next = new Set(current ?? []);
      if (next.has(id)) next.delete(id);
      else next.add(id);
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

  function focusMappedTown(name: string, centroid: [number, number]) {
    setQuery(name);
    setActiveTown(name);
    setSelected(null);
    setResultsOpen(false);
    setFiltersOpen(false);
    setLayersOpen(false);
    setAreaFocusRequest((current) => ({ sequence: current.sequence + 1, bbox: townFocusBbox(centroid) }));
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
    setSelectedMapAnnotationId(null);
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

  function selectMapAnnotation(id: string) {
    setSelectedMapAnnotationId(id);
    setSelected(null);
    setResultsOpen(false);
    setFiltersOpen(false);
  }

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
            className={`button secondary map-detail-mode ${detailMode ? "active" : ""}`}
            type="button"
            onClick={() => setDetailMode((value) => !value)}
            aria-pressed={detailMode}
            title={detailMode ? "关闭精细查看，恢复常规资源占用" : "允许继续放大并提高三维模型精度"}
          >
            <ScanSearch aria-hidden="true" />精细查看
          </button>
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
        <nav className="map-town-shortcuts" aria-label="正式林班乡镇快速定位">
          {(townAggregates.data?.items ?? []).map((town) => (
            <button
              type="button"
              key={town.code}
              className={`${town.centroid ? "" : "pending"} ${activeTown === town.name ? "active" : ""}`.trim()}
              onClick={() => town.centroid ? focusMappedTown(town.name, town.centroid) : openPendingTown(town.name)}
              aria-pressed={activeTown === town.name}
              title={`${town.name} · ${town.blockCount} 个正式林班${town.centroid ? "" : " · 边界待补"}`}
            >
              {town.name}{!town.centroid && <small>待补图</small>}
            </button>
          ))}
          {townAggregates.isLoading && <span className="map-town-loading">正在读取乡镇</span>}
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
          roadFeatureCollection={forestRoadMap.data ?? EMPTY_FOREST_ROAD_COLLECTION}
          selectedBlockId={selected?.id ?? null}
          onSelectBlock={selectMapBlock}
          onViewportChange={updateViewport}
          onViewMetricsChange={setViewMetrics}
          imageryAssets={displayedImageryAssets}
          spatial3dAssets={displayedSpatial3dAssets}
          targetSpatialAssetId={focusedSpatialAssetId || undefined}
          spatial3dDisplaySettings={spatial3dDisplaySettings}
          forestBlockFilterQuery={appliedFilterQuery}
          situationAssets={visibleMapAnnotations}
          onSelectSituationAsset={selectMapAnnotation}
          detailMode={detailMode}
          forestBlockLoading={mapBlocks.isFetching}
          forestBlockError={Boolean(mapBlocks.error)}
          forestBlockRequestDurationMs={mapBlocks.data?.meta.requestDurationMs}
        />
        {mode === "2d" && (
          <ImageClarityStatus metrics={viewMetrics} asset={displayedImageryAssets[0]} />
        )}
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
            <fieldset className="map-annotation-filter">
              <legend>空间成果与示范点</legend>
              <div>
                {MAP_ANNOTATION_KINDS.map((kind) => (
                  <label key={kind}>
                    <input
                      type="checkbox"
                      checked={annotationVisibility[kind]}
                      onChange={() => setAnnotationVisibility((current) => ({ ...current, [kind]: !current[kind] }))}
                    />
                    <span>{MAP_ANNOTATION_LABELS[kind]}</span>
                    <small>{allMapAnnotations.filter((annotation) => annotation.kind === kind).length}</small>
                  </label>
                ))}
              </div>
            </fieldset>
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
              <input type="checkbox" checked={layers.forestRoads} onChange={() => toggleLayer("forestRoads")} />
              <span>
                <strong>林区道路</strong>
                <small>{forestRoadMap.isFetching ? "正在读取道路空间台账" : `${forestRoadMap.data?.features.length ?? 0} 条正式道路`}</small>
              </span>
            </label>
            <label>
              <input type="checkbox" checked={layers.imagery} onChange={() => toggleLayer("imagery")} />
              <span><strong>卫星影像</strong><small>天地图影像底图</small></span>
            </label>
            <label>
              <input type="checkbox" checked={showMapAnnotations} onChange={() => setShowMapAnnotations((value) => !value)} />
              <span><strong>成果与示范标注</strong><small>{visibleMapAnnotations.length} 个当前可见提示，GIS 与前端大屏口径一致</small></span>
            </label>
            <label>
              <input type="checkbox" checked={layers.droneImagery} onChange={() => toggleLayer("droneImagery")} />
              <span><strong>无人机正射成果</strong><small>{imageryAssets.isFetching ? "正在读取当前视窗" : `${displayedImageryAssets.length}/${visibleImageryAssets.length} 个已显示`}</small></span>
            </label>
            {layers.droneImagery && visibleImageryAssets.length > 0 && (
              <div className="map-spatial-assets" aria-label="二维正射成果列表">
                <small>默认只显示一项，减少大影像并发；需要时可手动叠加对比</small>
                {visibleImageryAssets.map((asset) => (
                  <div className="map-spatial-asset" key={asset.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={enabledImageryAssetIds?.has(asset.id) ?? false}
                        onChange={() => toggleImageryAsset(asset.id)}
                      />
                      <span>
                        <strong>{asset.name}</strong>
                        <small>WebP 瓦片 · 最高 {asset.maximumZoom ?? 22} 级</small>
                      </span>
                    </label>
                    <button type="button" onClick={() => showOnlyImageryAsset(asset.id)}>仅看此项</button>
                  </div>
                ))}
              </div>
            )}
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
                        {!isPointCloudAsset(asset) && (
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
                        )}
                        {isPointCloudAsset(asset) && (
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
            {forestRoadMap.error && <p className="map-layer-error">林区道路读取失败，请稍后重试</p>}
          </aside>
        )}
        {selectedMapAnnotation && (
          <MapAnnotationCard
            annotation={selectedMapAnnotation}
            situation={selectedSituationRecord}
            imageryAssets={selectedAnnotationAssets}
            onClose={() => setSelectedMapAnnotationId(null)}
            onOpenBlock={selectedMapAnnotation.blockId
              ? () => void selectMapBlock(selectedMapAnnotation.blockId!)
              : undefined}
          />
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
              {selectedAnnotations.length > 0 && (
                <div className="map-object-badges" aria-label="林班空间成果">
                  {selectedAnnotations.map((annotation) => (
                    <span className={`map-object-badge ${annotation.kind}`} key={annotation.id}>
                      {MAP_ANNOTATION_LABELS[annotation.kind]}
                      {annotation.subtitle && <small>{annotation.subtitle}</small>}
                    </span>
                  ))}
                </div>
              )}
              <dl>
                <div><dt>林班编号</dt><dd>{selected.code}</dd></div>
                <div><dt>行政区划</dt><dd>{selected.location || "待补充"}</dd></div>
                <div><dt>面积</dt><dd>{selected.areaMu == null ? "待补充" : `${selected.areaMu} 亩`}</dd></div>
                <div><dt>空间边界</dt><dd>{selected.hasGeometry ? "已入库" : "待补图"}</dd></div>
              </dl>
              {selectedViewerLinks.length > 0 && (
                <div className="map-object-viewer-links map-object-viewer-links-priority">
                  <strong>关联影像成果</strong>
                  <small>在独立窗口查看，不改变当前 GIS 位置</small>
                  <div>
                    {selectedViewerLinks.map((item) => (
                      <a
                        className="button secondary map-object-viewer-link"
                        href={assetViewerHref(item.id, item.mode, selected.id)}
                        target="_blank"
                        rel="noreferrer"
                        title={`${item.label}：${item.assetName}（${item.assetDetail}）`}
                        key={item.id}
                      >
                        <ExternalLink aria-hidden="true" />
                        <span><strong>{item.label}</strong><small>{item.assetName}</small></span>
                      </a>
                    ))}
                  </div>
                </div>
              )}
              {selectedMosoInventory && (
                <section className="map-object-ai-summary">
                  <header><div><BrainCircuit /><span><small>AI 科研试算</small><strong>毛竹资源估算</strong></span></div><em>{selectedMosoInventory.confidence.level}置信度</em></header>
                  <div className="map-object-ai-metrics">
                    <span><small>模型估算株数</small><strong>{selectedMosoInventory.resourceStock.value.toLocaleString("zh-CN")} 株</strong></span>
                    <span><small>密度</small><strong>{selectedMosoInventory.stemDensity.value.toLocaleString("zh-CN", { maximumFractionDigits: 1 })} 株/亩</strong></span>
                    <span><small>冠层覆盖</small><strong>{selectedMosoInventory.canopyClosure.value.toLocaleString("zh-CN", { maximumFractionDigits: 1 })}%</strong></span>
                    <span><small>地上生物量</small><strong>{selectedMosoInventory.abovegroundBiomass.value.toLocaleString("zh-CN", { maximumFractionDigits: 1 })} t</strong></span>
                  </div>
                  <a className="button primary map-object-ai-link" href={mosoSandboxHref(selected.id)} target="_blank" rel="noreferrer"><ScanSearch />打开 AI 估算沙盘<ExternalLink /></a>
                  <p>影像候选点与模型外推值分开呈现；科研试算值不替代逐株调查。</p>
                </section>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

function MapAnnotationCard({
  annotation,
  situation,
  imageryAssets,
  onClose,
  onOpenBlock,
}: {
  annotation: MapAnnotation;
  situation: SituationAssetRecord | null;
  imageryAssets: ImageryAsset[];
  onClose: () => void;
  onOpenBlock?: () => void;
}) {
  return <aside className="map-annotation-card" aria-label="空间点位详情">
    <header>
      <div><small>{MAP_ANNOTATION_LABELS[annotation.kind]}</small><strong>{annotation.label}</strong></div>
      <button className="icon-button" type="button" onClick={onClose} aria-label="关闭点位详情"><X /></button>
    </header>
    {annotation.subtitle && <p>{annotation.subtitle}</p>}
    <dl>
      {annotation.blockCode && <div><dt>关联林班</dt><dd>{annotation.blockCode}</dd></div>}
      <div><dt>空间位置</dt><dd>{annotation.longitude.toFixed(6)}, {annotation.latitude.toFixed(6)}</dd></div>
      {situation && <><div><dt>运行状态</dt><dd>{situation.status}</dd></div>{situation.parameters.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</>}
    </dl>
    {imageryAssets.length > 0 && <div className="map-annotation-viewers">
      <strong>影像成果</strong>
      {imageryAssets.map((asset) => <a key={asset.id} href={`/v2/asset-viewer?sceneId=${encodeURIComponent(asset.id)}&mode=${asset.assetType === "orthophoto" ? "2d" : "3d"}`} target="_blank" rel="noreferrer"><ExternalLink />{asset.name}</a>)}
    </div>}
    <footer>
      {situation && <a className="button secondary" href={situation.managementPath}>打开后台台账</a>}
      {onOpenBlock && <button className="button secondary" type="button" onClick={onOpenBlock}>查看关联林班</button>}
    </footer>
  </aside>;
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
