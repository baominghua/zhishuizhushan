import { Globe2, Map as MapIcon, Unplug } from "lucide-react";
import { lazy, Suspense } from "react";

import type { ForestBlockFeatureCollection, ForestRoadFeatureCollection, ImageryAsset, MapConfigResponse } from "../api/types";
import type {
  MapAreaFocusRequest,
  MapLayerState,
  MapSceneModel,
  MapViewMetrics,
  MapViewMode,
  MapViewport,
  MapZoomRequest,
} from "../maps/scene";
import { OpenLayersMap } from "./OpenLayersMap";
import type { Spatial3dDisplaySettings } from "./CesiumGlobe";
import type { MapAnnotation } from "../maps/mapAnnotations";
import { MapAnnotationLegend } from "./MapAnnotationLegend";

const CesiumGlobe = lazy(async () => ({
  default: (await import("./CesiumGlobe")).CesiumGlobe,
}));

const EMPTY_ROAD_FEATURES: ForestRoadFeatureCollection = { type: "FeatureCollection", features: [] };

interface MapCanvasProps {
  config?: MapConfigResponse;
  loading: boolean;
  mode: MapViewMode;
  scene: MapSceneModel;
  layers: MapLayerState;
  homeRequest: number;
  zoomRequest: MapZoomRequest;
  areaFocusRequest: MapAreaFocusRequest;
  featureCollection: ForestBlockFeatureCollection;
  roadFeatureCollection?: ForestRoadFeatureCollection;
  selectedBlockId: string | null;
  onSelectBlock: (id: string) => void;
  onViewportChange: (viewport: MapViewport) => void;
  onViewMetricsChange?: (metrics: MapViewMetrics) => void;
  imageryAssets: ImageryAsset[];
  spatial3dAssets: ImageryAsset[];
  targetSpatialAssetId?: string;
  spatial3dDisplaySettings?: Record<string, Spatial3dDisplaySettings>;
  forestBlockFilterQuery: string;
  situationAssets?: MapSituationAsset[];
  onSelectSituationAsset?: (id: string) => void;
  detailMode?: boolean;
}

export type MapSituationAsset = MapAnnotation;

function LoadingState({ children }: { children: string }) {
  return <div className="map-service-state" role="status">{children}</div>;
}

export function MapCanvas({
  config,
  loading,
  mode,
  scene,
  layers,
  homeRequest,
  zoomRequest,
  areaFocusRequest,
  featureCollection,
  roadFeatureCollection = EMPTY_ROAD_FEATURES,
  selectedBlockId,
  onSelectBlock,
  onViewportChange,
  onViewMetricsChange,
  imageryAssets,
  spatial3dAssets,
  targetSpatialAssetId,
  spatial3dDisplaySettings = {},
  forestBlockFilterQuery,
  situationAssets = [],
  onSelectSituationAsset,
  detailMode = false,
}: MapCanvasProps) {
  if (loading) return <LoadingState>正在连接地图服务</LoadingState>;

  if (!config) {
    return (
      <div className="map-service-state unavailable">
        <Unplug aria-hidden="true" />
        <strong>地图配置暂不可用</strong>
        <p>无法读取地图服务配置</p>
      </div>
    );
  }

  if (!config.available && mode === "2d") {
    return (
      <div className="map-service-state unavailable">
        <Unplug aria-hidden="true" />
        <strong>天地图服务未连接</strong>
        <p>{config.message || "请先配置服务端天地图密钥"}</p>
      </div>
    );
  }

  return (
    <div className={`map-engine-canvas map-engine-${mode}`}>
      {mode === "2d" ? (
        <OpenLayersMap
          config={config}
          scene={scene}
          layers={layers}
          homeRequest={homeRequest}
          zoomRequest={zoomRequest}
          areaFocusRequest={areaFocusRequest}
          featureCollection={featureCollection}
          roadFeatureCollection={roadFeatureCollection}
          selectedBlockId={selectedBlockId}
          onSelectBlock={onSelectBlock}
          onViewportChange={onViewportChange}
          onViewMetricsChange={onViewMetricsChange}
          imageryAssets={imageryAssets}
          forestBlockFilterQuery={forestBlockFilterQuery}
          situationAssets={situationAssets}
          onSelectSituationAsset={onSelectSituationAsset}
          detailMode={detailMode}
        />
      ) : (
        <Suspense fallback={<LoadingState>正在启动三维地球</LoadingState>}>
          <CesiumGlobe
            config={config}
            scene={scene}
            layers={layers}
            homeRequest={homeRequest}
            zoomRequest={zoomRequest}
            areaFocusRequest={areaFocusRequest}
            featureCollection={featureCollection}
            roadFeatureCollection={roadFeatureCollection}
            selectedBlockId={selectedBlockId}
            onSelectBlock={onSelectBlock}
            onViewportChange={onViewportChange}
            imageryAssets={imageryAssets}
            spatial3dAssets={spatial3dAssets}
            targetSpatialAssetId={targetSpatialAssetId}
            spatial3dDisplaySettings={spatial3dDisplaySettings}
            situationAssets={situationAssets}
            onSelectSituationAsset={onSelectSituationAsset}
            detailMode={detailMode}
          />
        </Suspense>
      )}
      <div className="map-engine-status" aria-live="polite">
        {mode === "3d" ? <Globe2 aria-hidden="true" /> : <MapIcon aria-hidden="true" />}
        <span>{mode === "3d" ? "三维地球" : "二维地图"}</span>
        <small>{config.available ? "天地图服务端缓存" : "OpenStreetMap 备用底图"}</small>
      </div>
      {layers.forestBlocks && (
        <div className="map-feature-status" aria-live="polite">
          {mode === "2d" ? (
            <><strong>MVT</strong><span>林班矢量瓦片</span><small>按视窗加载</small></>
          ) : (
            <><strong>{featureCollection.meta.returned}</strong><span>个林班边界</span>{featureCollection.meta.truncated && <small>当前层级仅显示前 {featureCollection.meta.maxFeatures} 个</small>}</>
          )}
        </div>
      )}
      <MapAnnotationLegend annotations={situationAssets} />
    </div>
  );
}
