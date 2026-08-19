import {
  BoundingSphere,
  Cartesian2,
  Cartesian3,
  Cartographic,
  Color,
  ColorMaterialProperty,
  ConstantPositionProperty,
  ConstantProperty,
  Credit,
  GeoJsonDataSource,
  HeightReference,
  HorizontalOrigin,
  ImageryLayer,
  JulianDate,
  LabelGraphics,
  LabelStyle,
  Math as CesiumMath,
  NearFarScalar,
  OpenStreetMapImageryProvider,
  PolylineGraphics,
  PointGraphics,
  Rectangle,
  SceneTransforms,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  VerticalOrigin,
  Viewer,
  WebMercatorTilingScheme,
} from "cesium";
import { useEffect, useRef } from "react";
import "cesium/Build/Cesium/Widgets/widgets.css";

import type { ForestBlockFeatureCollection, ImageryAsset, MapConfigResponse } from "../api/types";
import type { MapSituationAsset } from "./MapCanvas";
import { forestBlockColor } from "../maps/forestBlocks";
import type {
  MapAreaFocusRequest,
  MapLayerState,
  MapSceneModel,
  MapViewport,
  MapZoomRequest,
} from "../maps/scene";

interface CesiumGlobeProps {
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
  imageryAssets: ImageryAsset[];
  situationAssets: MapSituationAsset[];
  onSelectSituationAsset?: (id: string) => void;
}

const SITUATION_COLORS: Record<MapSituationAsset["kind"], string> = {
  camera: "#ffb84a",
  helmet: "#61e4b1",
  dock: "#63c8ff",
  mission: "#d79bff",
};

// Level 18 imagery still carries useful detail below the former 2.5 km clamp.
// Stop before Cesium starts visibly stretching the final raster level.
const MINIMUM_SHARP_CAMERA_HEIGHT = 450;
const BLOCK_LABEL_MAX_HEIGHT = 120_000;
const BLOCK_LABEL_GAP = 8;
const FAR_VIEW_PITCH_RESET_HEIGHT = 300_000;
const FAR_VIEW_PITCH = CesiumMath.toRadians(-88);
const FAR_VIEW_MAX_TILT = CesiumMath.toRadians(-80);

function restoreFarViewPitch(viewer: Viewer, height: number) {
  if (height < FAR_VIEW_PITCH_RESET_HEIGHT || viewer.camera.pitch <= FAR_VIEW_MAX_TILT) {
    return false;
  }

  const position = viewer.camera.positionCartographic;
  viewer.camera.setView({
    destination: Cartesian3.fromRadians(position.longitude, position.latitude, position.height),
    orientation: {
      heading: 0,
      pitch: FAR_VIEW_PITCH,
      roll: 0,
    },
  });
  viewer.scene.requestRender();
  return true;
}

function performanceResolutionScale() {
  const devicePixelRatio = Math.max(window.devicePixelRatio || 1, 1);
  // Keep enough physical pixels for crisp parcel outlines without asking the
  // globe to refine imagery at the full density of a high-DPI display.
  return Math.min(1.1, 1.25 / devicePixelRatio);
}

type ForestBlockLabelProperties = Record<string, unknown>;

function propertyText(properties: ForestBlockLabelProperties, key: string) {
  const value = properties[key];
  return value === null || value === undefined ? "" : String(value).trim();
}

function forestBlockLabelText(properties: ForestBlockLabelProperties, cameraHeight: number) {
  if (cameraHeight > BLOCK_LABEL_MAX_HEIGHT) return "";
  const name = propertyText(properties, "name");
  const code = propertyText(properties, "blockCode");
  return name || code.slice(-6).replace(/^0+/, "") || code;
}

function polygonLabelPosition(positions: Cartesian3[]) {
  const center = BoundingSphere.fromPoints(positions).center;
  const cartographic = Cartographic.fromCartesian(center);
  return Cartesian3.fromRadians(cartographic.longitude, cartographic.latitude, 12);
}

interface LabelRectangle {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

function overlapsLabel(left: LabelRectangle, right: LabelRectangle) {
  return !(
    left.right + BLOCK_LABEL_GAP < right.left ||
    right.right + BLOCK_LABEL_GAP < left.left ||
    left.bottom + BLOCK_LABEL_GAP < right.top ||
    right.bottom + BLOCK_LABEL_GAP < left.top
  );
}

function updateForestBlockLabels(
  viewer: Viewer,
  dataSource: GeoJsonDataSource,
  selectedBlockId: string | null,
) {
  const cameraHeight = viewer.camera.positionCartographic.height;
  const canvas = viewer.scene.canvas;
  const now = JulianDate.now();
  const candidates = dataSource.entities.values
    .map((entity) => {
      const properties = (entity.properties?.getValue(now) ?? {}) as ForestBlockLabelProperties;
      const text = forestBlockLabelText(properties, cameraHeight);
      const position = entity.position?.getValue(now);
      const screen = position
        ? SceneTransforms.worldToWindowCoordinates(viewer.scene, position)
        : undefined;
      const area = Number(properties.areaMu) || 0;
      return { entity, text, screen, area, selected: entity.id === selectedBlockId };
    })
    .sort((left, right) => Number(right.selected) - Number(left.selected) || right.area - left.area);

  const occupied: LabelRectangle[] = [];
  candidates.forEach(({ entity, text, screen }) => {
    if (!entity.label) return;
    const visible = Boolean(
      text &&
        screen &&
        screen.x >= 0 &&
        screen.y >= 0 &&
        screen.x <= canvas.clientWidth &&
        screen.y <= canvas.clientHeight,
    );
    const width = Math.max(28, text.length * 9 + 18);
    const rectangle = screen
      ? {
          left: screen.x - width / 2,
          right: screen.x + width / 2,
          top: screen.y - 15,
          bottom: screen.y + 15,
        }
      : undefined;
    const unobstructed = Boolean(visible && rectangle && !occupied.some((item) => overlapsLabel(item, rectangle)));
    entity.label.text = new ConstantProperty(text);
    entity.label.show = new ConstantProperty(unobstructed);
    if (unobstructed && rectangle) occupied.push(rectangle);
  });
}

function styleForestBlocks(
  dataSource: GeoJsonDataSource,
  selectedBlockId: string | null,
  cameraHeight: number,
) {
  dataSource.entities.values.forEach((entity) => {
    if (!entity.polygon) return;
    const properties = (entity.properties?.getValue(JulianDate.now()) ?? {}) as ForestBlockLabelProperties;
    const base = Color.fromCssColorString(forestBlockColor(propertyText(properties, "riskLevel")));
    const selected = entity.id === selectedBlockId;
    entity.polygon.material = new ColorMaterialProperty(
      selected ? Color.fromCssColorString("#ffe47b").withAlpha(0.52) : base.withAlpha(0.34),
    );
    entity.polygon.outline = new ConstantProperty(false);
    const hierarchy = entity.polygon.hierarchy?.getValue(JulianDate.now());
    if (hierarchy?.positions?.length) {
      entity.position = new ConstantPositionProperty(polygonLabelPosition(hierarchy.positions));
      const labelText = forestBlockLabelText(properties, cameraHeight);
      entity.label = new LabelGraphics({
        text: labelText,
        show: Boolean(labelText),
        font: "600 14px 'Microsoft YaHei', sans-serif",
        style: LabelStyle.FILL_AND_OUTLINE,
        fillColor: Color.WHITE,
        outlineColor: Color.fromCssColorString("#052f27"),
        outlineWidth: 4,
        showBackground: true,
        backgroundColor: Color.fromCssColorString("#062b24").withAlpha(0.82),
        backgroundPadding: new Cartesian2(8, 5),
        horizontalOrigin: HorizontalOrigin.CENTER,
        verticalOrigin: VerticalOrigin.CENTER,
        heightReference: HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance: new NearFarScalar(800, 1.05, BLOCK_LABEL_MAX_HEIGHT, 0.72),
      });
      entity.polyline = new PolylineGraphics({
        positions: new ConstantProperty([...hierarchy.positions, hierarchy.positions[0]]),
        clampToGround: new ConstantProperty(true),
        material: new ColorMaterialProperty(
          selected ? Color.fromCssColorString("#ffe47b") : Color.fromCssColorString("#d9ffed").withAlpha(0.96),
        ),
        width: new ConstantProperty(selected ? 4 : 2.4),
      });
    }
  });
}

export function CesiumGlobe({
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
  imageryAssets,
  situationAssets,
  onSelectSituationAsset,
}: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const imageryLayerRef = useRef<ImageryLayer | null>(null);
  const labelLayerRef = useRef<ImageryLayer | null>(null);
  const labelLayerReadyRef = useRef(false);
  const labelsVisibleRef = useRef(layers.labels);
  const droneImageryLayersRef = useRef<ImageryLayer[]>([]);
  const blockDataSourceRef = useRef<GeoJsonDataSource | null>(null);
  const selectedBlockIdRef = useRef<string | null>(selectedBlockId);
  const forestBlocksVisibleRef = useRef(layers.forestBlocks);
  const selectBlockRef = useRef(onSelectBlock);
  const selectSituationRef = useRef(onSelectSituationAsset);
  const viewportChangeRef = useRef(onViewportChange);
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
    if (!containerRef.current) return;

    const baseLayer = config.available
      ? false
      : ImageryLayer.fromProviderAsync(
          Promise.resolve(
            new OpenStreetMapImageryProvider({
              url: "https://tile.openstreetmap.org/",
              maximumLevel: 19,
              credit: new Credit("© OpenStreetMap contributors"),
            }),
          ),
        );

    const viewer = new Viewer(containerRef.current, {
      animation: false,
      baseLayer,
      baseLayerPicker: false,
      fullscreenButton: false,
      geocoder: false,
      homeButton: false,
      infoBox: false,
      navigationHelpButton: false,
      sceneModePicker: false,
      selectionIndicator: false,
      timeline: false,
    });
    viewerRef.current = viewer;
    // Cap the effective render density so a high-DPI client does not multiply
    // the number of imagery tiles needed for the first useful frame.
    viewer.useBrowserRecommendedResolution = false;
    viewer.resolutionScale = performanceResolutionScale();
    viewer.scene.requestRenderMode = true;
    viewer.scene.maximumRenderTimeChange = Number.POSITIVE_INFINITY;
    viewer.scene.backgroundColor = Color.fromCssColorString("#03130f");
    viewer.scene.globe.baseColor = Color.fromCssColorString("#0a211d");
    viewer.scene.globe.showGroundAtmosphere = true;
    viewer.scene.globe.maximumScreenSpaceError = 2;
    viewer.scene.globe.tileCacheSize = 250;
    viewer.scene.globe.preloadAncestors = true;
    viewer.scene.globe.preloadSiblings = false;
    viewer.scene.fog.enabled = true;
    // Tianditu imagery currently ends at level 18. This limit allows forestry
    // parcel inspection while preventing meaningless over-zoom beyond it.
    viewer.scene.screenSpaceCameraController.minimumZoomDistance = MINIMUM_SHARP_CAMERA_HEIGHT;
    viewer.scene.screenSpaceCameraController.maximumZoomDistance = 28_000_000;

    if (config.available) {
      const credit = new Credit("天地图");
      imageryLayerRef.current = viewer.imageryLayers.addImageryProvider(
        new UrlTemplateImageryProvider({
          url: config.imageryUrl,
          credit,
          maximumLevel: config.maximumLevel,
          tilingScheme: new WebMercatorTilingScheme(),
        }),
      );
      labelLayerRef.current = viewer.imageryLayers.addImageryProvider(
        new UrlTemplateImageryProvider({
          url: config.labelsUrl,
          maximumLevel: config.maximumLevel,
          tilingScheme: new WebMercatorTilingScheme(),
        }),
      );
      // Give the satellite layer the connection first. Labels are useful, but
      // they should not double the critical-path requests for the first frame.
      labelLayerRef.current.show = false;
    }

    const labelLayerTimer = window.setTimeout(() => {
      labelLayerReadyRef.current = true;
      if (labelLayerRef.current) labelLayerRef.current.show = labelsVisibleRef.current;
      viewer.scene.requestRender();
    }, 1_500);

    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(
        scene.home.longitude,
        scene.home.latitude,
        scene.home.height3d,
      ),
      orientation: {
        heading: CesiumMath.toRadians(2),
        pitch: CesiumMath.toRadians(-88),
        roll: 0,
      },
    });

    const reportViewport = () => {
      const height = viewer.camera.positionCartographic.height;
      if (restoreFarViewPitch(viewer, height)) return;
      if (blockDataSourceRef.current) {
        updateForestBlockLabels(viewer, blockDataSourceRef.current, selectedBlockIdRef.current);
        viewer.scene.requestRender();
      }
      if (height >= 3_000_000) return;
      const rectangle = viewer.camera.computeViewRectangle(viewer.scene.globe.ellipsoid);
      if (!rectangle) return;
      const west = CesiumMath.toDegrees(rectangle.west);
      const south = CesiumMath.toDegrees(rectangle.south);
      const east = CesiumMath.toDegrees(rectangle.east);
      const north = CesiumMath.toDegrees(rectangle.north);
      if (![west, south, east, north].every(Number.isFinite) || west >= east || south >= north) return;
      viewportChangeRef.current({
        bbox: [west, south, east, north],
        zoom: Math.max(0, Math.min(20, Math.round(Math.log2(40_000_000 / Math.max(height, 1)) + 3))),
      });
    };

    viewer.camera.moveEnd.addEventListener(reportViewport);
    viewer.screenSpaceEventHandler.setInputAction((movement: { position: Cartesian2 }) => {
      const picked = viewer.scene.pick(movement.position) as { id?: { id?: string } } | undefined;
      const id = picked?.id?.id;
      if (id?.startsWith("situation:")) {
        selectSituationRef.current?.(id.slice("situation:".length));
      } else if (id) {
        selectBlockRef.current(id);
      }
    }, ScreenSpaceEventType.LEFT_CLICK);

    const requestSharpFrame = () => viewer.scene.requestRender();
    viewer.scene.globe.tileLoadProgressEvent.addEventListener(requestSharpFrame);

    const observer = new ResizeObserver(() => {
      viewer.resolutionScale = performanceResolutionScale();
      viewer.resize();
      viewer.scene.requestRender();
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      window.clearTimeout(labelLayerTimer);
      viewer.scene.globe.tileLoadProgressEvent.removeEventListener(requestSharpFrame);
      viewer.camera.moveEnd.removeEventListener(reportViewport);
      viewerRef.current = null;
      imageryLayerRef.current = null;
      labelLayerRef.current = null;
      labelLayerReadyRef.current = false;
      blockDataSourceRef.current = null;
      droneImageryLayersRef.current = [];
      if (!viewer.isDestroyed()) viewer.destroy();
    };
  }, [config, scene.home.height3d, scene.home.latitude, scene.home.longitude]);

  useEffect(() => {
    if (imageryLayerRef.current) imageryLayerRef.current.show = layers.imagery;
    labelsVisibleRef.current = layers.labels;
    if (labelLayerRef.current && labelLayerReadyRef.current) {
      labelLayerRef.current.show = layers.labels;
    }
    forestBlocksVisibleRef.current = layers.forestBlocks;
    if (blockDataSourceRef.current) blockDataSourceRef.current.show = layers.forestBlocks;
    viewerRef.current?.scene.requestRender();
  }, [layers.forestBlocks, layers.imagery, layers.labels]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    droneImageryLayersRef.current.forEach((layer) => {
      if (viewer.imageryLayers.contains(layer)) viewer.imageryLayers.remove(layer, true);
    });
    const nextLayers = imageryAssets.map((asset) => {
      const layer = viewer.imageryLayers.addImageryProvider(new UrlTemplateImageryProvider({
        url: asset.tileUrl,
        maximumLevel: 22,
        tilingScheme: new WebMercatorTilingScheme(),
        credit: new Credit(asset.name),
      }));
      layer.alpha = Number.isFinite(asset.opacity) ? asset.opacity : 0.9;
      layer.show = layers.droneImagery;
      return layer;
    });
    droneImageryLayersRef.current = nextLayers;
    if (labelLayerRef.current) viewer.imageryLayers.raiseToTop(labelLayerRef.current);
    viewer.scene.requestRender();
    return () => nextLayers.forEach((layer) => {
      if (!viewer.isDestroyed() && viewer.imageryLayers.contains(layer)) viewer.imageryLayers.remove(layer, true);
    });
  }, [imageryAssets, layers.droneImagery]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const entities = situationAssets.map((asset) => viewer.entities.add({
      id: `situation:${asset.id}`,
      position: Cartesian3.fromDegrees(asset.longitude, asset.latitude, 8),
      point: new PointGraphics({
        pixelSize: 13,
        color: Color.fromCssColorString(SITUATION_COLORS[asset.kind]),
        outlineColor: Color.fromCssColorString("#062b24"),
        outlineWidth: 3,
        heightReference: HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      }),
      label: new LabelGraphics({
        text: asset.label,
        font: "600 13px 'Microsoft YaHei', sans-serif",
        fillColor: Color.WHITE,
        outlineColor: Color.fromCssColorString("#03241e"),
        outlineWidth: 4,
        style: LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cartesian2(0, -24),
        heightReference: HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance: new NearFarScalar(2_000, 1, 160_000, 0.65),
        translucencyByDistance: new NearFarScalar(80_000, 1, 400_000, 0),
      }),
    }));
    viewer.scene.requestRender();
    return () => entities.forEach((entity) => {
      if (!viewer.isDestroyed()) viewer.entities.remove(entity);
    });
  }, [situationAssets]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    let cancelled = false;
    const previous = blockDataSourceRef.current;

    void GeoJsonDataSource.load(
      featureCollection as Parameters<typeof GeoJsonDataSource.load>[0],
      { clampToGround: true },
    ).then((dataSource) => {
      if (cancelled || viewer.isDestroyed()) return;
      styleForestBlocks(
        dataSource,
        selectedBlockIdRef.current,
        viewer.camera.positionCartographic.height,
      );
      dataSource.show = forestBlocksVisibleRef.current;
      viewer.dataSources.add(dataSource);
      blockDataSourceRef.current = dataSource;
      if (previous) viewer.dataSources.remove(previous, true);
      updateForestBlockLabels(viewer, dataSource, selectedBlockIdRef.current);
      const selectedId = selectedBlockIdRef.current;
      const selectedEntity = selectedId ? dataSource.entities.getById(selectedId) : undefined;
      if (selectedId && selectedEntity && lastFocusedBlockRef.current !== selectedId) {
        lastFocusedBlockRef.current = selectedId;
        void viewer.flyTo(selectedEntity, { duration: 1.2 });
      }
      viewer.scene.requestRender();
    });

    return () => {
      cancelled = true;
    };
  }, [featureCollection]);

  useEffect(() => {
    selectedBlockIdRef.current = selectedBlockId;
    const dataSource = blockDataSourceRef.current;
    const viewer = viewerRef.current;
    if (!dataSource || !viewer) return;
    styleForestBlocks(dataSource, selectedBlockId, viewer.camera.positionCartographic.height);
    updateForestBlockLabels(viewer, dataSource, selectedBlockId);
    viewer.scene.requestRender();
    if (!selectedBlockId) {
      lastFocusedBlockRef.current = null;
      return;
    }
    const entity = dataSource.entities.getById(selectedBlockId);
    if (!entity || lastFocusedBlockRef.current === selectedBlockId) return;
    lastFocusedBlockRef.current = selectedBlockId;
    void viewer.flyTo(entity, { duration: 1.2 });
  }, [featureCollection, selectedBlockId]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || homeRequest === 0) return;
    lastFocusedBlockRef.current = null;
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(
        scene.home.longitude,
        scene.home.latitude,
        scene.home.height3d,
      ),
      duration: 1.2,
      orientation: {
        heading: 0,
        pitch: CesiumMath.toRadians(-88),
        roll: 0,
      },
    });
  }, [homeRequest, scene.home.height3d, scene.home.latitude, scene.home.longitude]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || zoomRequest.sequence === 0) return;

    const position = viewer.camera.positionCartographic;
    const values = [position.longitude, position.latitude, position.height];
    if (!values.every(Number.isFinite)) return;

    const heightFactor = zoomRequest.direction === "in" ? 0.55 : 1.8;
    const targetHeight = Math.min(
      20_000_000,
      Math.max(MINIMUM_SHARP_CAMERA_HEIGHT, position.height * heightFactor),
    );
    viewer.camera.cancelFlight();
    viewer.camera.flyTo({
      destination: Cartesian3.fromRadians(position.longitude, position.latitude, targetHeight),
      duration: 0.45,
      orientation: {
        heading: viewer.camera.heading,
        pitch: targetHeight >= FAR_VIEW_PITCH_RESET_HEIGHT ? FAR_VIEW_PITCH : viewer.camera.pitch,
        roll: targetHeight >= FAR_VIEW_PITCH_RESET_HEIGHT ? 0 : viewer.camera.roll,
      },
    });
  }, [zoomRequest]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || areaFocusRequest.sequence === 0) return;
    const [west, south, east, north] = areaFocusRequest.bbox;
    viewer.camera.flyTo({
      destination: Rectangle.fromDegrees(west, south, east, north),
      duration: 0.9,
    });
  }, [areaFocusRequest]);

  return <div className="cesium-map" ref={containerRef} aria-label="南平市竹林资源三维地球" />;
}
