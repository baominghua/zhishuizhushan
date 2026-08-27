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
  Cesium3DTileStyle,
  Cesium3DTileset,
  GeoJsonDataSource,
  HeightReference,
  HeadingPitchRange,
  HorizontalOrigin,
  ImageryLayer,
  JulianDate,
  LabelGraphics,
  LabelStyle,
  Matrix4,
  Math as CesiumMath,
  NearFarScalar,
  OpenStreetMapImageryProvider,
  PolylineGraphics,
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
import { MAP_ANNOTATION_COLORS, MAP_ANNOTATION_GLYPHS } from "../maps/mapAnnotations";
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
  spatial3dAssets: ImageryAsset[];
  targetSpatialAssetId?: string;
  spatial3dDisplaySettings: Record<string, Spatial3dDisplaySettings>;
  situationAssets: MapSituationAsset[];
  onSelectSituationAsset?: (id: string) => void;
  detailMode: boolean;
  qualityMode?: "smooth" | "standard" | "detail";
  onSpatialLoadProgress?: (progress: { pending: number; processing: number; ready: boolean }) => void;
}

export interface Spatial3dDisplaySettings {
  opacity: number;
  pointSize: number;
  colorMode?: "rgb" | "elevation" | "return" | "intensity";
  returnProperty?: string;
  intensityProperty?: string;
  elevationMinimum?: number;
  elevationMaximum?: number;
  eastOffset?: number;
  northOffset?: number;
  heightOffset?: number;
}

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

// Level 18 imagery still carries useful detail below the former 2.5 km clamp.
// Stop before Cesium starts visibly stretching the final raster level.
const MINIMUM_SHARP_CAMERA_HEIGHT = 450;

function applySpatialTilesetStyle(
  tileset: Cesium3DTileset,
  assetType: string | undefined,
  settings: Spatial3dDisplaySettings,
) {
  const styleProperty = (value: string | undefined, fallback: string) => (
    value && /^[A-Za-z_][A-Za-z0-9_]*$/.test(value) ? value : fallback
  );
  if (assetType === "pointcloud") {
    // Do not assign a constant color here. DJI PNTS tiles carry per-point RGB,
    // and a white style discards the canopy colour that operators need to see.
    if (settings.colorMode === "elevation") {
      const minimum = Number.isFinite(settings.elevationMinimum) ? Number(settings.elevationMinimum) : 0;
      const maximum = Number.isFinite(settings.elevationMaximum) ? Number(settings.elevationMaximum) : minimum + 250;
      const step = Math.max((maximum - minimum) / 5, 1);
      tileset.style = new Cesium3DTileStyle({
        pointSize: String(settings.pointSize),
        color: {
          conditions: [
            [`\${POSITION}.z >= ${minimum + step * 4}`, "color('#d24a43')"],
            [`\${POSITION}.z >= ${minimum + step * 3}`, "color('#f29d49')"],
            [`\${POSITION}.z >= ${minimum + step * 2}`, "color('#e6d45c')"],
            [`\${POSITION}.z >= ${minimum + step}`, "color('#63bf8b')"],
            ["true", "color('#3c8dc5')"],
          ],
        },
      });
    } else if (settings.colorMode === "intensity") {
      const propertyName = styleProperty(settings.intensityProperty, "intensity");
      tileset.style = new Cesium3DTileStyle({
        pointSize: String(settings.pointSize),
        color: {
          conditions: [
            [`\${${propertyName}} >= 49152`, "color('#f7fcf5')"],
            [`\${${propertyName}} >= 32768`, "color('#74c476')"],
            [`\${${propertyName}} >= 16384`, "color('#238b45')"],
            ["true", "color('#00441b')"],
          ],
        },
      });
    } else if (settings.colorMode === "return") {
      const propertyName = styleProperty(settings.returnProperty, "return_number");
      tileset.style = new Cesium3DTileStyle({
        pointSize: String(settings.pointSize),
        color: {
          conditions: [
            [`\${${propertyName}} >= 4`, "color('#984ea3')"],
            [`\${${propertyName}} == 3`, "color('#ff7f00')"],
            [`\${${propertyName}} == 2`, "color('#4daf4a')"],
            ["true", "color('#377eb8')"],
          ],
        },
      });
    } else {
      tileset.style = new Cesium3DTileStyle({ pointSize: String(settings.pointSize) });
    }
    return;
  }
  tileset.style = new Cesium3DTileStyle({
    color: `color('white', ${settings.opacity})`,
  });
}

function retireSpatialTileset(viewer: Viewer, tileset: Cesium3DTileset) {
  if (viewer.isDestroyed() || tileset.isDestroyed()) return;
  tileset.show = false;
  let stopListening: (() => void) | undefined;
  const removeAfterRender = () => {
    stopListening?.();
    if (!viewer.isDestroyed() && !tileset.isDestroyed()
      && viewer.scene.primitives.contains(tileset)) {
      viewer.scene.primitives.remove(tileset);
    }
  };
  stopListening = viewer.scene.postRender.addEventListener(removeAfterRender);
  viewer.scene.requestRender();
}

function tilesetTuning(assetType: string | undefined, qualityMode: CesiumGlobeProps["qualityMode"], detailMode: boolean) {
  const pointcloud = assetType === "pointcloud";
  if (qualityMode === "smooth") return { error: pointcloud ? 16 : 10, cacheBytes: 256 * 1024 * 1024 };
  if (qualityMode === "detail" || detailMode) return { error: pointcloud ? 4 : 2, cacheBytes: 768 * 1024 * 1024 };
  return { error: pointcloud ? 10 : 6, cacheBytes: 384 * 1024 * 1024 };
}

function spatialAssetType(asset: ImageryAsset) {
  return asset.assetType === "pointcloud"
    || asset.tilesetContentType?.toLowerCase() === "pnts"
    || Boolean(asset.tileFormats?.pnts)
    ? "pointcloud"
    : asset.assetType;
}

function applySpatialTilesetTransform(
  tileset: Cesium3DTileset,
  baseMatrix: Matrix4,
  settings: Spatial3dDisplaySettings,
) {
  const center = tileset.boundingSphere.center;
  const position = Cartographic.fromCartesian(center);
  const east = new Cartesian3(-Math.sin(position.longitude), Math.cos(position.longitude), 0);
  const north = new Cartesian3(
    -Math.sin(position.latitude) * Math.cos(position.longitude),
    -Math.sin(position.latitude) * Math.sin(position.longitude),
    Math.cos(position.latitude),
  );
  const up = new Cartesian3(
    Math.cos(position.latitude) * Math.cos(position.longitude),
    Math.cos(position.latitude) * Math.sin(position.longitude),
    Math.sin(position.latitude),
  );
  const translation = Cartesian3.multiplyByScalar(east, settings.eastOffset ?? 0, new Cartesian3());
  Cartesian3.add(translation, Cartesian3.multiplyByScalar(north, settings.northOffset ?? 0, new Cartesian3()), translation);
  Cartesian3.add(translation, Cartesian3.multiplyByScalar(up, settings.heightOffset ?? 0, new Cartesian3()), translation);
  tileset.modelMatrix = Matrix4.multiply(Matrix4.fromTranslation(translation), baseMatrix, new Matrix4());
}

function focusTileset(viewer: Viewer, tileset: Cesium3DTileset, duration = 0.8) {
  const sphere = BoundingSphere.clone(tileset.boundingSphere);
  viewer.camera.flyToBoundingSphere(sphere, {
    duration,
    offset: new HeadingPitchRange(0, CesiumMath.toRadians(-42), Math.max(25, sphere.radius * 2.6)),
  });
}
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
      selected ? Color.fromCssColorString("#ffe47b").withAlpha(0.07) : base.withAlpha(0.022),
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
  spatial3dAssets,
  targetSpatialAssetId,
  spatial3dDisplaySettings,
  situationAssets,
  onSelectSituationAsset,
  detailMode,
  qualityMode,
  onSpatialLoadProgress,
}: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const imageryLayerRef = useRef<ImageryLayer | null>(null);
  const labelLayerRef = useRef<ImageryLayer | null>(null);
  const labelLayerReadyRef = useRef(false);
  const labelsVisibleRef = useRef(layers.labels);
  const droneImageryLayersRef = useRef<Map<string, ImageryLayer>>(new Map());
  const spatial3dTilesetsRef = useRef<Map<string, Cesium3DTileset>>(new Map());
  const desiredSpatial3dAssetIdsRef = useRef<Set<string>>(new Set());
  const pendingSpatial3dLoadsRef = useRef<Map<string, symbol>>(new Map());
  const spatial3dAssetTypesRef = useRef<Map<string, string | undefined>>(new Map());
  const spatial3dBaseMatricesRef = useRef<Map<string, Matrix4>>(new Map());
  const targetSpatialAssetIdRef = useRef(targetSpatialAssetId);
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
    viewer.scene.screenSpaceCameraController.inertiaZoom = 0.65;
    viewer.scene.screenSpaceCameraController.maximumMovementRatio = 0.08;

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
      if (id?.startsWith("map-annotation:")) {
        selectSituationRef.current?.(id.slice("map-annotation:".length));
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
      droneImageryLayersRef.current = new Map();
      spatial3dTilesetsRef.current = new Map();
      desiredSpatial3dAssetIdsRef.current = new Set();
      pendingSpatial3dLoadsRef.current.clear();
      spatial3dAssetTypesRef.current.clear();
      spatial3dBaseMatricesRef.current.clear();
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
    viewer.scene.screenSpaceCameraController.minimumZoomDistance = detailMode ? 10 : MINIMUM_SHARP_CAMERA_HEIGHT;
    spatial3dTilesetsRef.current.forEach((tileset, assetId) => {
      const tuning = tilesetTuning(spatial3dAssetTypesRef.current.get(assetId), qualityMode, detailMode);
      tileset.maximumScreenSpaceError = tuning.error;
      tileset.cacheBytes = tuning.cacheBytes;
    });
    viewer.scene.requestRender();
  }, [detailMode, qualityMode]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const desiredIds = new Set(imageryAssets.map((asset) => asset.id));
    droneImageryLayersRef.current.forEach((layer, assetId) => {
      if (desiredIds.has(assetId)) return;
      if (viewer.imageryLayers.contains(layer)) viewer.imageryLayers.remove(layer, true);
      droneImageryLayersRef.current.delete(assetId);
    });
    imageryAssets.forEach((asset) => {
      const existing = droneImageryLayersRef.current.get(asset.id);
      if (existing) {
        existing.alpha = Number.isFinite(asset.opacity) ? asset.opacity : 0.9;
        existing.show = layers.droneImagery;
        return;
      }
      const [west, south, east, north] = asset.bounds ?? [];
      const rectangle = [west, south, east, north].every(Number.isFinite)
        && west < east && south < north
        ? Rectangle.fromDegrees(west, south, east, north)
        : undefined;
      const layer = viewer.imageryLayers.addImageryProvider(new UrlTemplateImageryProvider({
        url: asset.tileUrl,
        maximumLevel: asset.maximumZoom ?? 22,
        tilingScheme: new WebMercatorTilingScheme(),
        rectangle,
        credit: new Credit(asset.name),
      }));
      layer.alpha = Number.isFinite(asset.opacity) ? asset.opacity : 0.9;
      layer.show = layers.droneImagery;
      droneImageryLayersRef.current.set(asset.id, layer);
    });
    if (labelLayerRef.current) viewer.imageryLayers.raiseToTop(labelLayerRef.current);
    viewer.scene.requestRender();
  }, [imageryAssets, layers.droneImagery]);

  useEffect(() => {
    droneImageryLayersRef.current.forEach((layer) => { layer.show = layers.droneImagery; });
    viewerRef.current?.scene.requestRender();
  }, [layers.droneImagery]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const activeViewer = viewer;
    const desiredIds = new Set(spatial3dAssets.map((asset) => asset.id));
    desiredSpatial3dAssetIdsRef.current = desiredIds;
    spatial3dAssetTypesRef.current = new Map(
      spatial3dAssets.map((asset) => [asset.id, spatialAssetType(asset)]),
    );

    spatial3dTilesetsRef.current.forEach((tileset, assetId) => {
      if (desiredIds.has(assetId)) return;
      spatial3dTilesetsRef.current.delete(assetId);
      spatial3dBaseMatricesRef.current.delete(assetId);
      retireSpatialTileset(activeViewer, tileset);
    });
    pendingSpatial3dLoadsRef.current.forEach((_loadToken, assetId) => {
      if (!desiredIds.has(assetId)) pendingSpatial3dLoadsRef.current.delete(assetId);
    });

    async function loadTilesets() {
      for (const asset of spatial3dAssets) {
        if (!asset.tilesetUrl || spatial3dTilesetsRef.current.has(asset.id)
          || pendingSpatial3dLoadsRef.current.has(asset.id)) continue;
        const loadToken = Symbol(asset.id);
        pendingSpatial3dLoadsRef.current.set(asset.id, loadToken);
        try {
          const resolvedAssetType = spatialAssetType(asset);
          const tuning = tilesetTuning(resolvedAssetType, qualityMode, detailMode);
          const tileset = await Cesium3DTileset.fromUrl(asset.tilesetUrl, {
            // Start with a coarse useful frame and refine only where the user is
            // looking. Point clouds need a looser SSE than textured B3DM models.
            maximumScreenSpaceError: tuning.error,
            cacheBytes: tuning.cacheBytes,
            maximumCacheOverflowBytes: 128 * 1024 * 1024,
            foveatedScreenSpaceError: true,
            foveatedConeSize: 0.2,
            foveatedMinimumScreenSpaceErrorRelaxation: 4,
            preloadWhenHidden: false,
            preloadFlightDestinations: false,
          });
          const loadIsCurrent = pendingSpatial3dLoadsRef.current.get(asset.id) === loadToken;
          if (!loadIsCurrent || !desiredSpatial3dAssetIdsRef.current.has(asset.id)
            || activeViewer.isDestroyed()) {
            if (!tileset.isDestroyed()) tileset.destroy();
            continue;
          }
          tileset.show = layers.spatial3d;
          const settings = spatial3dDisplaySettings[asset.id] ?? { opacity: 1, pointSize: 3 };
          applySpatialTilesetStyle(tileset, resolvedAssetType, settings);
          activeViewer.scene.primitives.add(tileset);
          spatial3dTilesetsRef.current.set(asset.id, tileset);
          spatial3dBaseMatricesRef.current.set(asset.id, Matrix4.clone(tileset.modelMatrix));
          applySpatialTilesetTransform(tileset, spatial3dBaseMatricesRef.current.get(asset.id)!, settings);
          tileset.loadProgress.addEventListener((pending, processing) => {
            onSpatialLoadProgress?.({ pending, processing, ready: pending === 0 && processing === 0 });
          });
          if (asset.id === targetSpatialAssetIdRef.current) {
            focusTileset(activeViewer, tileset, 1.2);
          }
        } catch {
          // Keep loading the remaining registered datasets when one directory is unavailable.
        } finally {
          if (pendingSpatial3dLoadsRef.current.get(asset.id) === loadToken) {
            pendingSpatial3dLoadsRef.current.delete(asset.id);
          }
        }
      }
      if (!activeViewer.isDestroyed()) activeViewer.scene.requestRender();
    }

    void loadTilesets();
  }, [detailMode, onSpatialLoadProgress, qualityMode, spatial3dAssets]);

  useEffect(() => {
    targetSpatialAssetIdRef.current = targetSpatialAssetId;
    const viewer = viewerRef.current;
    const tileset = targetSpatialAssetId
      ? spatial3dTilesetsRef.current.get(targetSpatialAssetId)
      : undefined;
    if (!viewer || viewer.isDestroyed() || !tileset || tileset.isDestroyed()) return;
    focusTileset(viewer, tileset, 1.2);
  }, [targetSpatialAssetId]);

  useEffect(() => {
    spatial3dTilesetsRef.current.forEach((tileset) => {
      tileset.show = layers.spatial3d;
    });
    viewerRef.current?.scene.requestRender();
  }, [layers.spatial3d]);

  useEffect(() => {
    spatial3dTilesetsRef.current.forEach((tileset, assetId) => {
      const settings = spatial3dDisplaySettings[assetId] ?? { opacity: 1, pointSize: 3 };
      try {
        applySpatialTilesetStyle(
          tileset,
          spatial3dAssetTypesRef.current.get(assetId),
          settings,
        );
      } catch {
        // A malformed third-party batch-table property must never tear down the
        // whole viewer. Fall back to the per-point RGB carried by the PNTS tile.
        applySpatialTilesetStyle(
          tileset,
          spatial3dAssetTypesRef.current.get(assetId),
          { ...settings, colorMode: "rgb" },
        );
      }
      const baseMatrix = spatial3dBaseMatricesRef.current.get(assetId);
      if (baseMatrix) applySpatialTilesetTransform(tileset, baseMatrix, settings);
    });
    viewerRef.current?.scene.requestRender();
  }, [spatial3dDisplaySettings]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const entities = situationAssets.map((asset) => {
      const [offsetX, offsetY] = SITUATION_OFFSETS[asset.kind];
      return viewer.entities.add({
        id: `map-annotation:${asset.id}`,
        name: asset.label,
        position: Cartesian3.fromDegrees(asset.longitude, asset.latitude, 8),
        label: new LabelGraphics({
          text: MAP_ANNOTATION_GLYPHS[asset.kind],
          font: "800 20px 'Segoe UI Symbol', system-ui, sans-serif",
          fillColor: Color.fromCssColorString(MAP_ANNOTATION_COLORS[asset.kind]),
          outlineColor: Color.fromCssColorString("#03241e"),
          outlineWidth: 3,
          style: LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cartesian2(offsetX, offsetY),
          heightReference: HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scaleByDistance: new NearFarScalar(2_000, 1, 160_000, 0.7),
          translucencyByDistance: new NearFarScalar(80_000, 1, 400_000, 0),
        }),
      });
    });
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

    const targetTileset = targetSpatialAssetIdRef.current
      ? spatial3dTilesetsRef.current.get(targetSpatialAssetIdRef.current)
      : undefined;
    if (targetTileset && !targetTileset.isDestroyed()) {
      const sphere = targetTileset.boundingSphere;
      const fromCenter = Cartesian3.subtract(viewer.camera.positionWC, sphere.center, new Cartesian3());
      const currentDistance = Cartesian3.magnitude(fromCenter);
      if (Number.isFinite(currentDistance) && currentDistance > 0) {
        const factor = zoomRequest.direction === "in" ? 0.8 : 1.25;
        const targetDistance = Math.min(
          Math.max(sphere.radius * 120, 2_000),
          Math.max(Math.max(sphere.radius * 0.08, 2), currentDistance * factor),
        );
        const destination = Cartesian3.add(
          sphere.center,
          Cartesian3.multiplyByScalar(Cartesian3.normalize(fromCenter, new Cartesian3()), targetDistance, new Cartesian3()),
          new Cartesian3(),
        );
        viewer.camera.cancelFlight();
        viewer.camera.flyTo({
          destination,
          duration: 0.5,
          orientation: {
            direction: Cartesian3.normalize(Cartesian3.subtract(sphere.center, destination, new Cartesian3()), new Cartesian3()),
            up: viewer.camera.upWC,
          },
        });
        return;
      }
    }

    const position = viewer.camera.positionCartographic;
    const values = [position.longitude, position.latitude, position.height];
    if (!values.every(Number.isFinite)) return;

    const heightFactor = zoomRequest.direction === "in" ? 0.78 : 1.28;
    const targetHeight = Math.min(
      20_000_000,
      Math.max(detailMode ? 10 : MINIMUM_SHARP_CAMERA_HEIGHT, position.height * heightFactor),
    );
    viewer.camera.cancelFlight();
    viewer.camera.flyTo({
      destination: Cartesian3.fromRadians(position.longitude, position.latitude, targetHeight),
      duration: 0.55,
      orientation: {
        heading: viewer.camera.heading,
        pitch: targetHeight >= FAR_VIEW_PITCH_RESET_HEIGHT ? FAR_VIEW_PITCH : viewer.camera.pitch,
        roll: targetHeight >= FAR_VIEW_PITCH_RESET_HEIGHT ? 0 : viewer.camera.roll,
      },
    });
  }, [detailMode, zoomRequest]);

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
