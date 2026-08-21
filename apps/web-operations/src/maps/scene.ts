import type { ForestBlockOption } from "../api/types";

export type MapViewMode = "2d" | "3d";

export interface MapZoomRequest {
  sequence: number;
  direction: "in" | "out";
}

export interface MapAreaFocusRequest {
  sequence: number;
  bbox: [number, number, number, number];
}

export interface MapLayerState {
  imagery: boolean;
  labels: boolean;
  forestBlocks: boolean;
  droneImagery: boolean;
  spatial3d: boolean;
}

export interface MapViewport {
  bbox: [number, number, number, number];
  zoom: number;
}

export interface MapViewMetrics {
  zoom: number;
  latitude: number;
  metresPerPixel: number;
  cameraHeight?: number;
}

export interface MapSceneModel {
  home: {
    longitude: number;
    latitude: number;
    zoom2d: number;
    height3d: number;
  };
  selectedBlock: ForestBlockOption | null;
}

export const DEFAULT_MAP_LAYERS: MapLayerState = {
  imagery: true,
  labels: true,
  forestBlocks: true,
  droneImagery: false,
  spatial3d: false,
};

export const DEFAULT_MAP_VIEWPORT: MapViewport = {
  bbox: [117.65, 27.47, 117.78, 27.62],
  zoom: 12,
};

export function createMapScene(selectedBlock: ForestBlockOption | null): MapSceneModel {
  return {
    home: {
      longitude: 117.7135,
      latitude: 27.5448,
      zoom2d: 12,
      height3d: 25_000,
    },
    selectedBlock,
  };
}
