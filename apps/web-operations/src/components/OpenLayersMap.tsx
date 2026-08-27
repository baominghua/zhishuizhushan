import GeoJSON from "ol/format/GeoJSON";
import MVT from "ol/format/MVT";
import Feature from "ol/Feature";
import Map from "ol/Map";
import type { FeatureLike } from "ol/Feature";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorTileLayer from "ol/layer/VectorTile";
import MouseWheelZoom from "ol/interaction/MouseWheelZoom";
import { defaults as defaultInteractions } from "ol/interaction/defaults";
import Point from "ol/geom/Point";
import { fromLonLat, toLonLat, transformExtent } from "ol/proj";
import VectorSource from "ol/source/Vector";
import VectorTileSource from "ol/source/VectorTile";
import XYZ from "ol/source/XYZ";
import { Circle as CircleStyle, Fill, Stroke, Style, Text } from "ol/style";
import View from "ol/View";
import { useEffect, useRef } from "react";
import "ol/ol.css";

import type { ForestBlockFeatureCollection, ImageryAsset, MapConfigResponse } from "../api/types";
import type { MapSituationAsset } from "./MapCanvas";
import { MAP_ANNOTATION_COLORS } from "../maps/mapAnnotations";
import type {
  MapAreaFocusRequest,
  MapLayerState,
  MapSceneModel,
  MapViewMetrics,
  MapViewport,
  MapZoomRequest,
} from "../maps/scene";

interface OpenLayersMapProps {
  config: MapConfigResponse;
  scene: MapSceneModel;
  layers: MapLayerState;
  homeRequest: number;
  zoomRequest: MapZoomRequest;
  areaFocusRequest: MapAreaFocusRequest;
  featureCollection: ForestBlockFeatureCollection;
  selectedBlockId: string | null;
  onSelectBlock: (id: string) => void;
  onViewportChange: (viewport: MapViewport) => void;
  onViewMetricsChange?: (metrics: MapViewMetrics) => void;
  imageryAssets: ImageryAsset[];
  forestBlockFilterQuery: string;
  situationAssets: MapSituationAsset[];
  onSelectSituationAsset?: (id: string) => void;
  detailMode: boolean;
}

const WEB_MERCATOR_MAX_RESOLUTION = 156543.03392804097;
const BLOCK_LABEL_MIN_ZOOM = 12;
const SITUATION_OFFSETS: Record<MapSituationAsset["kind"], [number, number]> = {
  camera: [-15, 0],
  helmet: [15, 0],
  dock: [-11, -15],
  mission: [11, -15],
  orthophoto: [-20, 18],
  pointcloud: [0, 23],
  mesh: [20, 18],
  demonstration: [0, -28],
};

function createSituationStyle(feature: FeatureLike) {
  const kind = String(feature.get("kind")) as MapSituationAsset["kind"];
  const color = MAP_ANNOTATION_COLORS[kind] || "#ffffff";
  const [offsetX, offsetY] = SITUATION_OFFSETS[kind] || [0, 0];
  return new Style({
    image: new CircleStyle({
      radius: 7,
      fill: new Fill({ color }),
      stroke: new Stroke({ color: "rgba(3, 35, 29, 0.96)", width: 2.5 }),
      displacement: [offsetX, offsetY],
    }),
    zIndex: 80,
  });
}

function featureText(feature: FeatureLike, resolution: number) {
  const zoom = Math.log2(WEB_MERCATOR_MAX_RESOLUTION / resolution);
  if (zoom < BLOCK_LABEL_MIN_ZOOM) return "";
  const blockCode = String(feature.get("blockCode") || "").trim();
  const name = String(feature.get("name") || "").trim();
  return name || blockCode.slice(-6).replace(/^0+/, "") || blockCode;
}

function createBlockStyle(feature: FeatureLike, selectedBlockId: string | null, resolution: number) {
  const selected = String(feature.getId() ?? feature.get("id") ?? "") === selectedBlockId;
  const label = featureText(feature, resolution);
  const casing = new Style({
    fill: new Fill({ color: selected ? "rgba(255, 217, 92, 0.055)" : "rgba(20, 103, 77, 0.018)" }),
    stroke: new Stroke({ color: "rgba(2, 34, 27, 0.94)", width: selected ? 6 : 4.8 }),
    zIndex: selected ? 19 : 4,
  });
  const line = new Style({
    stroke: new Stroke({ color: selected ? "#ffe47b" : "rgba(205, 255, 234, 0.98)", width: selected ? 2.8 : 2 }),
    text: label
      ? new Text({
          text: label,
          font: selected ? "600 13px system-ui, sans-serif" : "600 12px system-ui, sans-serif",
          fill: new Fill({ color: "#f7fffb" }),
          stroke: new Stroke({ color: "rgba(4, 43, 34, 0.96)", width: 3.5 }),
          backgroundFill: new Fill({ color: selected ? "rgba(82, 67, 8, 0.88)" : "rgba(5, 49, 39, 0.82)" }),
          backgroundStroke: new Stroke({ color: selected ? "#ffe47b" : "rgba(184, 246, 216, 0.72)", width: 1 }),
          padding: [4, 6, 4, 6],
          textAlign: "center",
          overflow: true,
        })
      : undefined,
    zIndex: selected ? 20 : 5,
  });
  return [casing, line];
}

export function OpenLayersMap({
  config,
  scene,
  layers,
  homeRequest,
  zoomRequest,
  areaFocusRequest,
  featureCollection,
  selectedBlockId,
  onSelectBlock,
  onViewportChange,
  onViewMetricsChange,
  imageryAssets,
  forestBlockFilterQuery,
  situationAssets,
  onSelectSituationAsset,
  detailMode,
}: OpenLayersMapProps) {
  const mapElement = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const imageryLayerRef = useRef<TileLayer<XYZ> | null>(null);
  const labelLayerRef = useRef<TileLayer<XYZ> | null>(null);
  const blockLayerRef = useRef<VectorTileLayer | null>(null);
  const selectedLayerRef = useRef<VectorLayer<VectorSource> | null>(null);
  const situationLayerRef = useRef<VectorLayer<VectorSource> | null>(null);
  const situationSourceRef = useRef(new VectorSource());
  const droneImageryLayersRef = useRef(new globalThis.Map<string, TileLayer<XYZ>>());
  const selectedSourceRef = useRef(new VectorSource());
  const selectedBlockIdRef = useRef<string | null>(selectedBlockId);
  const selectBlockRef = useRef(onSelectBlock);
  const selectSituationRef = useRef(onSelectSituationAsset);
  const viewportChangeRef = useRef(onViewportChange);
  const viewMetricsChangeRef = useRef(onViewMetricsChange);
  const lastFocusedBlockRef = useRef<string | null>(null);

  useEffect(() => {
    selectBlockRef.current = onSelectBlock;
  }, [onSelectBlock]);

  useEffect(() => {
    selectSituationRef.current = onSelectSituationAsset;
  }, [onSelectSituationAsset]);

  useEffect(() => {
    viewportChangeRef.current = onViewportChange;
  }, [onViewportChange]);

  useEffect(() => {
    viewMetricsChangeRef.current = onViewMetricsChange;
  }, [onViewMetricsChange]);

  useEffect(() => {
    if (!mapElement.current) return;
    const imagery = new TileLayer({
      source: new XYZ({ url: config.imageryUrl, maxZoom: config.maximumLevel }),
      zIndex: 0,
    });
    const labels = new TileLayer({
      source: new XYZ({ url: config.labelsUrl, maxZoom: config.maximumLevel }),
      zIndex: 20,
    });
    const blockLayer = new VectorTileLayer({
      source: new VectorTileSource({
        format: new MVT({ idProperty: "id" }),
        url: `/api/map/forest-blocks/tiles/{z}/{x}/{y}.pbf?maxFeatures=5000${forestBlockFilterQuery ? `&${forestBlockFilterQuery}` : ""}`,
        maxZoom: 20,
        transition: 0,
      }),
      declutter: "forest-block-labels",
      zIndex: 30,
      style: (feature, resolution) => createBlockStyle(feature, selectedBlockIdRef.current, resolution),
    });
    const selectedLayer = new VectorLayer({
      source: selectedSourceRef.current,
      declutter: "forest-block-labels",
      zIndex: 40,
      style: (feature, resolution) => createBlockStyle(feature, selectedBlockIdRef.current, resolution),
    });
    const situationLayer = new VectorLayer({
      source: situationSourceRef.current,
      zIndex: 80,
      style: createSituationStyle,
    });
    const map = new Map({
      target: mapElement.current,
      layers: [imagery, labels, blockLayer, selectedLayer, situationLayer],
      interactions: defaultInteractions({ mouseWheelZoom: false }).extend([
        new MouseWheelZoom({
          constrainResolution: true,
          duration: 360,
          maxDelta: 1,
          timeout: 140,
          useAnchor: true,
        }),
      ]),
      view: new View({
        center: fromLonLat([scene.home.longitude, scene.home.latitude]),
        zoom: scene.home.zoom2d,
        maxZoom: 28,
        constrainResolution: true,
        smoothResolutionConstraint: true,
      }),
    });

    const reportViewport = () => {
      const size = map.getSize();
      if (!size) return;
      const bbox = transformExtent(map.getView().calculateExtent(size), "EPSG:3857", "EPSG:4326");
      if (bbox.length !== 4 || bbox.some((value) => !Number.isFinite(value))) return;
      viewportChangeRef.current({
        bbox: [bbox[0], bbox[1], bbox[2], bbox[3]],
        zoom: Math.round(map.getView().getZoom() ?? scene.home.zoom2d),
      });
    };

    const reportViewMetrics = () => {
      const view = map.getView();
      const zoom = view.getZoom() ?? scene.home.zoom2d;
      const projectedResolution = view.getResolution() ?? WEB_MERCATOR_MAX_RESOLUTION / (2 ** zoom);
      const center = view.getCenter();
      const latitude = center ? toLonLat(center)[1] : scene.home.latitude;
      viewMetricsChangeRef.current?.({
        zoom,
        latitude,
        metresPerPixel: projectedResolution * Math.max(0.01, Math.cos(latitude * Math.PI / 180)),
      });
    };

    map.on("singleclick", (event) => {
      const situation = map.forEachFeatureAtPixel(event.pixel, (candidate, layer) =>
        layer === situationLayer ? candidate : undefined,
      );
      const situationId = situation?.get("situationAssetId");
      if (situationId) {
        selectSituationRef.current?.(String(situationId));
        return;
      }
      const feature = map.forEachFeatureAtPixel(event.pixel, (candidate, layer) =>
        layer === blockLayer || layer === selectedLayer ? candidate : undefined,
      );
      const id = feature?.getId() ?? feature?.get("id");
      if (id != null) selectBlockRef.current(String(id));
    });

    map.on("moveend", reportViewport);
    map.on("moveend", reportViewMetrics);
    map.on("pointermove", (event) => {
      if (!mapElement.current) return;
      mapElement.current.style.cursor = map.hasFeatureAtPixel(event.pixel, {
        layerFilter: (layer) => layer === blockLayer || layer === selectedLayer || layer === situationLayer,
      }) ? "pointer" : "";
    });
    mapRef.current = map;
    imageryLayerRef.current = imagery;
    labelLayerRef.current = labels;
    blockLayerRef.current = blockLayer;
    selectedLayerRef.current = selectedLayer;
    situationLayerRef.current = situationLayer;
    reportViewport();
    reportViewMetrics();

    return () => {
      map.setTarget(undefined);
      mapRef.current = null;
      imageryLayerRef.current = null;
      labelLayerRef.current = null;
      blockLayerRef.current = null;
      selectedLayerRef.current = null;
      situationLayerRef.current = null;
      droneImageryLayersRef.current.clear();
    };
  }, [config, scene.home.latitude, scene.home.longitude, scene.home.zoom2d]);

  useEffect(() => {
    const layer = blockLayerRef.current;
    if (!layer) return;
    layer.setSource(new VectorTileSource({
      format: new MVT({ idProperty: "id" }),
      url: `/api/map/forest-blocks/tiles/{z}/{x}/{y}.pbf?maxFeatures=5000${forestBlockFilterQuery ? `&${forestBlockFilterQuery}` : ""}`,
      maxZoom: 20,
      transition: 0,
    }));
  }, [forestBlockFilterQuery]);

  useEffect(() => {
    imageryLayerRef.current?.setVisible(layers.imagery);
    labelLayerRef.current?.setVisible(layers.labels);
    blockLayerRef.current?.setVisible(layers.forestBlocks);
    selectedLayerRef.current?.setVisible(layers.forestBlocks);
  }, [layers.forestBlocks, layers.imagery, layers.labels]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const desiredIds = new Set(imageryAssets.map((asset) => asset.id));
    droneImageryLayersRef.current.forEach((layer, assetId) => {
      if (desiredIds.has(assetId)) return;
      map.removeLayer(layer);
      droneImageryLayersRef.current.delete(assetId);
    });
    imageryAssets.forEach((asset, index) => {
      const existing = droneImageryLayersRef.current.get(asset.id);
      if (existing) {
        existing.setOpacity(Number.isFinite(asset.opacity) ? asset.opacity : 0.9);
        existing.setVisible(layers.droneImagery);
        existing.setZIndex(10 + index);
        return;
      }
      const layer = new TileLayer({
        source: new XYZ({
          url: asset.tileUrl,
          maxZoom: asset.maximumZoom ?? 22,
          transition: 180,
          cacheSize: 768,
          interpolate: !detailMode,
        }),
        opacity: Number.isFinite(asset.opacity) ? asset.opacity : 0.9,
        visible: layers.droneImagery,
        zIndex: 10 + index,
        preload: 0,
        extent: asset.bounds?.length === 4
          ? transformExtent(asset.bounds, "EPSG:4326", "EPSG:3857")
          : undefined,
        properties: { title: asset.name, assetId: asset.id },
      });
      droneImageryLayersRef.current.set(asset.id, layer);
      map.addLayer(layer);
    });
  }, [detailMode, imageryAssets, layers.droneImagery]);

  useEffect(() => {
    const view = mapRef.current?.getView();
    if (!view) return;
    const maximumZoom = detailMode ? 28 : 23;
    view.setMaxZoom(maximumZoom);
    if ((view.getZoom() ?? 0) > maximumZoom) view.animate({ zoom: maximumZoom, duration: 260 });
  }, [detailMode]);

  useEffect(() => {
    droneImageryLayersRef.current.forEach((layer) => layer.setVisible(layers.droneImagery));
  }, [layers.droneImagery]);

  useEffect(() => {
    const source = situationSourceRef.current;
    source.clear();
    source.addFeatures(situationAssets.map((asset) => new Feature({
      geometry: new Point(fromLonLat([asset.longitude, asset.latitude])),
      situationAssetId: asset.id,
      kind: asset.kind,
      label: asset.mapLabel ?? asset.label,
    })));
  }, [situationAssets]);

  useEffect(() => {
    const source = selectedSourceRef.current;
    source.clear();
    source.addFeatures(new GeoJSON().readFeatures(featureCollection, {
      featureProjection: "EPSG:3857",
    }));
  }, [featureCollection]);

  useEffect(() => {
    selectedBlockIdRef.current = selectedBlockId;
    blockLayerRef.current?.changed();
    selectedLayerRef.current?.changed();
    if (!selectedBlockId) {
      lastFocusedBlockRef.current = null;
      return;
    }
    const feature = selectedSourceRef.current.getFeatureById(selectedBlockId);
    const map = mapRef.current;
    if (!feature || !map || lastFocusedBlockRef.current === selectedBlockId) return;
    lastFocusedBlockRef.current = selectedBlockId;
    map.getView().fit(feature.getGeometry()!.getExtent(), {
      duration: 700,
      maxZoom: 16,
      padding: [120, 120, 120, 120],
    });
  }, [featureCollection, selectedBlockId]);

  useEffect(() => {
    if (!mapRef.current || homeRequest === 0) return;
    lastFocusedBlockRef.current = null;
    mapRef.current.getView().animate({
      center: fromLonLat([scene.home.longitude, scene.home.latitude]),
      zoom: scene.home.zoom2d,
      duration: 600,
    });
  }, [homeRequest, scene.home.latitude, scene.home.longitude, scene.home.zoom2d]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || zoomRequest.sequence === 0) return;
    const view = map.getView();
    const currentZoom = view.getZoom() ?? scene.home.zoom2d;
    const delta = zoomRequest.direction === "in" ? 1 : -1;
    view.animate({ zoom: Math.min(detailMode ? 28 : 23, Math.max(2, currentZoom + delta)), duration: 260 });
  }, [detailMode, scene.home.zoom2d, zoomRequest]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || areaFocusRequest.sequence === 0) return;
    map.getView().fit(
      transformExtent(areaFocusRequest.bbox, "EPSG:4326", "EPSG:3857"),
      { duration: 700, maxZoom: 18, padding: [88, 88, 88, 88] },
    );
  }, [areaFocusRequest]);

  return <div className="ol-map" ref={mapElement} aria-label="南平市竹林资源地图" />;
}
