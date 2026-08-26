import { LidarControl, type LidarState, type PointCloudInfo } from "maplibre-gl-lidar";
import { GeoJSONSource, Map as MapLibreMap, NavigationControl } from "maplibre-gl";
import { useEffect, useRef } from "react";

import "maplibre-gl/dist/maplibre-gl.css";
import "maplibre-gl-lidar/style.css";

import type { ForestBlockFeatureCollection } from "../api/types";
import type { MapViewport, MapZoomRequest } from "../maps/scene";
import type { Spatial3dDisplaySettings } from "./CesiumGlobe";

export interface CopcViewerStatus {
  loading: boolean;
  ready: boolean;
  streaming: boolean;
  loadedNodes: number;
  loadedPoints: number;
  queueSize: number;
  budgetReached: boolean;
  error: string;
  pointCloud: PointCloudInfo | null;
}

interface CopcPointCloudViewerProps {
  url: string;
  bounds?: [number, number, number, number];
  featureCollection: ForestBlockFeatureCollection;
  settings: Spatial3dDisplaySettings;
  quality: "smooth" | "standard" | "detail";
  homeRequest: number;
  zoomRequest: MapZoomRequest;
  onStatusChange: (status: CopcViewerStatus) => void;
  onViewportChange: (viewport: MapViewport) => void;
}

const EMPTY_GEOJSON = { type: "FeatureCollection" as const, features: [] };
const POINT_BUDGETS = { smooth: 750_000, standard: 1_500_000, detail: 3_000_000 } as const;

function initialCenter(bounds?: CopcPointCloudViewerProps["bounds"]): [number, number] {
  if (!bounds || bounds.length !== 4) return [117.7135, 27.5448];
  return [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2];
}

function viewportForMap(map: MapLibreMap): MapViewport {
  const bounds = map.getBounds();
  return {
    bbox: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()],
    zoom: map.getZoom(),
  };
}

function statusFromState(state: LidarState, pointCloud: PointCloudInfo | null, error = "", budgetReached = false): CopcViewerStatus {
  const progress = state.streamingProgress;
  return {
    loading: state.loading,
    ready: Boolean(pointCloud) && !state.loading,
    streaming: Boolean(state.streamingActive),
    loadedNodes: progress?.loadedNodes ?? 0,
    loadedPoints: progress?.loadedPoints ?? pointCloud?.pointCount ?? 0,
    queueSize: progress?.queueSize ?? 0,
    budgetReached,
    error: error || state.error || "",
    pointCloud,
  };
}

export function CopcPointCloudViewer({
  url,
  bounds,
  featureCollection,
  settings,
  quality,
  homeRequest,
  zoomRequest,
  onStatusChange,
  onViewportChange,
}: CopcPointCloudViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const controlRef = useRef<LidarControl | null>(null);
  const pointCloudRef = useRef<PointCloudInfo | null>(null);

  useEffect(() => {
    if (!containerRef.current || !url) return;
    let disposed = false;
    const sourceUrl = new URL(url, window.location.origin).toString();
    const map = new MapLibreMap({
      container: containerRef.current,
      center: initialCenter(bounds),
      zoom: bounds ? 15 : 11,
      pitch: 62,
      bearing: 0,
      maxPitch: 85,
      maxZoom: 24,
      canvasContextAttributes: { antialias: true, powerPreference: "high-performance" },
      attributionControl: false,
      style: {
        version: 8,
        sources: {
          "forest-blocks": { type: "geojson", data: EMPTY_GEOJSON },
        },
        layers: [
          { id: "point-cloud-background", type: "background", paint: { "background-color": "#061b16" } },
          { id: "forest-block-fill", type: "fill", source: "forest-blocks", paint: { "fill-color": "#55d5a8", "fill-opacity": 0.08 } },
          { id: "forest-block-line", type: "line", source: "forest-blocks", paint: { "line-color": "#b8ffe4", "line-width": 1.6, "line-opacity": 0.92 } },
        ],
      },
    });
    const control = new LidarControl({
      title: "智慧竹山 COPC 点云",
      collapsed: true,
      theme: "dark",
      pointSize: settings.pointSize,
      opacity: settings.opacity,
      colorScheme: settings.colorMode === "intensity" ? "intensity" : settings.colorMode === "elevation" ? "elevation" : "rgb",
      colormap: "turbo",
      colorRange: { mode: "percentile", percentileLow: 2, percentileHigh: 98 },
      pointBudget: POINT_BUDGETS[quality],
      pickable: true,
      pickInfoFields: ["X", "Y", "Z", "Intensity", "Classification", "Red", "Green", "Blue", "GpsTime", "ReturnNumber", "NumberOfReturns", "ScanAngle"],
      autoZoom: true,
      autoZOffset: false,
      zOffsetEnabled: Boolean(settings.heightOffset),
      zOffset: settings.heightOffset ?? 0,
      copcLoadingMode: "dynamic",
      streamingPointBudget: 3_000_000,
      streamingMaxConcurrentRequests: 4,
      streamingViewportDebounceMs: 260,
      shareUrl: false,
      restoreFromUrl: false,
      closeOnOutsideClick: false,
    });
    const reportState = (budgetReached = false, error = "") => {
      if (!disposed) onStatusChange(statusFromState(control.getState(), pointCloudRef.current, error, budgetReached));
    };
    const onLoad = (event: { pointCloud?: PointCloudInfo | { id: string } }) => {
      if (event.pointCloud && "pointCount" in event.pointCloud) pointCloudRef.current = event.pointCloud;
      reportState();
    };
    const onLoadError = (event: { error?: Error }) => reportState(false, event.error?.message || "COPC 点云加载失败");
    const onBudgetReached = () => reportState(true);
    const onStateChange = () => reportState();
    const onMoveEnd = () => onViewportChange(viewportForMap(map));

    mapRef.current = map;
    controlRef.current = control;
    map.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(control, "top-right");
    const controlContainer = control.getContainer();
    if (controlContainer) controlContainer.style.display = "none";
    control.on("statechange", onStateChange);
    control.on("streamingprogress", onStateChange);
    control.on("load", onLoad);
    control.on("loaderror", onLoadError);
    control.on("budgetreached", onBudgetReached);
    map.on("moveend", onMoveEnd);
    map.once("load", () => {
      if (disposed) return;
      onMoveEnd();
      reportState();
      void control.loadPointCloud(sourceUrl, { loadingMode: "dynamic" }).then((pointCloud) => {
        if (disposed) return;
        pointCloudRef.current = pointCloud;
        reportState();
      }).catch((error: unknown) => {
        reportState(false, error instanceof Error ? error.message : "COPC 点云加载失败");
      });
    });

    return () => {
      disposed = true;
      control.off("statechange", onStateChange);
      control.off("streamingprogress", onStateChange);
      control.off("load", onLoad);
      control.off("loaderror", onLoadError);
      control.off("budgetreached", onBudgetReached);
      control.stopStreaming();
      map.off("moveend", onMoveEnd);
      map.remove();
      mapRef.current = null;
      controlRef.current = null;
      pointCloudRef.current = null;
    };
  }, [bounds, onStatusChange, onViewportChange, url]);

  useEffect(() => {
    const source = mapRef.current?.getSource("forest-blocks");
    if (source instanceof GeoJSONSource) source.setData(featureCollection as never);
  }, [featureCollection]);

  useEffect(() => {
    const control = controlRef.current;
    if (!control) return;
    control.setPointSize(settings.pointSize);
    control.setOpacity(settings.opacity);
    control.setPointBudget(POINT_BUDGETS[quality]);
    control.setZOffsetEnabled(Boolean(settings.heightOffset));
    control.setZOffset(settings.heightOffset ?? 0);
    if (settings.colorMode === "rgb" || settings.colorMode === "elevation" || settings.colorMode === "intensity") {
      control.setColorScheme(settings.colorMode);
    }
  }, [quality, settings.colorMode, settings.heightOffset, settings.opacity, settings.pointSize]);

  useEffect(() => {
    if (!homeRequest) return;
    controlRef.current?.flyToPointCloud();
  }, [homeRequest]);

  useEffect(() => {
    if (!zoomRequest.sequence) return;
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({ zoom: map.getZoom() + (zoomRequest.direction === "in" ? 0.75 : -0.75), duration: 320 });
  }, [zoomRequest]);

  return <div className="copc-point-cloud-viewer" ref={containerRef} aria-label="COPC 点云独立流式查看器" />;
}
