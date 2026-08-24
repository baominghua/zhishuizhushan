import type {
  ForestBlockFeatureCollection,
  ForestBlockGeometry,
  ImageryAsset,
  SituationAssetRecord,
} from "../api/types";

export type MapAnnotationKind =
  | "camera"
  | "helmet"
  | "dock"
  | "mission"
  | "orthophoto"
  | "pointcloud"
  | "mesh"
  | "demonstration";

export interface MapAnnotation {
  id: string;
  kind: MapAnnotationKind;
  label: string;
  mapLabel?: string;
  subtitle?: string;
  longitude: number;
  latitude: number;
  sourceType: "situation" | "imagery" | "forest-block";
  sourceId?: string;
  sourceIds?: string[];
  blockId?: string;
  blockCode?: string;
}

export const MAP_ANNOTATION_LABELS: Record<MapAnnotationKind, string> = {
  camera: "高位卡口",
  helmet: "安全帽",
  dock: "无人机机巢",
  mission: "无人机任务",
  orthophoto: "无人机正射",
  pointcloud: "彩色点云",
  mesh: "实景三维",
  demonstration: "高产示范点",
};

export const MAP_ANNOTATION_COLORS: Record<MapAnnotationKind, string> = {
  camera: "#ffb84a",
  helmet: "#61e4b1",
  dock: "#63c8ff",
  mission: "#d79bff",
  orthophoto: "#25b8e8",
  pointcloud: "#9b7bff",
  mesh: "#ff9f43",
  demonstration: "#ffe16d",
};

export const MAP_ANNOTATION_GLYPHS: Record<MapAnnotationKind, string> = {
  camera: "▣",
  helmet: "⌒",
  dock: "◆",
  mission: "✈",
  orthophoto: "▤",
  pointcloud: "⁙",
  mesh: "⬡",
  demonstration: "★",
};

export const MAP_ANNOTATION_GROUPS: Array<{ label: string; kinds: MapAnnotationKind[] }> = [
  { label: "设备与作业", kinds: ["camera", "helmet", "dock", "mission"] },
  { label: "影像与成果", kinds: ["orthophoto", "pointcloud", "mesh", "demonstration"] },
];

export const DEFAULT_MAP_ANNOTATION_VISIBILITY: Record<MapAnnotationKind, boolean> = {
  camera: true,
  helmet: true,
  dock: true,
  mission: true,
  orthophoto: true,
  pointcloud: true,
  mesh: true,
  demonstration: true,
};

export const MAP_ANNOTATION_KINDS = Object.keys(MAP_ANNOTATION_LABELS) as MapAnnotationKind[];

export function geometryAnchor(geometry: ForestBlockGeometry | null): [number, number] | null {
  if (!geometry) return null;
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  const rings = polygons
    .map((polygon) => (polygon as unknown[][])[0] as unknown[] | undefined)
    .filter((ring): ring is unknown[] => Array.isArray(ring) && ring.length >= 3);
  let bestArea = 0;
  let bestLongitude: number | null = null;
  let bestLatitude: number | null = null;
  rings.forEach((ring) => {
    const points = ring.filter((point): point is number[] => Array.isArray(point) && point.length >= 2);
    let crossSum = 0;
    let longitudeSum = 0;
    let latitudeSum = 0;
    for (let index = 0; index < points.length; index += 1) {
      const current = points[index];
      const next = points[(index + 1) % points.length];
      const cross = current[0] * next[1] - next[0] * current[1];
      crossSum += cross;
      longitudeSum += (current[0] + next[0]) * cross;
      latitudeSum += (current[1] + next[1]) * cross;
    }
    if (Math.abs(crossSum) < 1e-12) return;
    const area = Math.abs(crossSum / 2);
    if (area > bestArea) {
      bestArea = area;
      bestLongitude = longitudeSum / (3 * crossSum);
      bestLatitude = latitudeSum / (3 * crossSum);
    }
  });
  return bestLongitude !== null && bestLatitude !== null ? [bestLongitude, bestLatitude] : null;
}

function imageryKind(asset: ImageryAsset): MapAnnotationKind | null {
  if (asset.assetType === "orthophoto") return "orthophoto";
  if (asset.assetType === "pointcloud" || asset.tilesetContentType?.toLowerCase() === "pnts") return "pointcloud";
  if (asset.assetType === "oblique3d" || asset.tilesetContentType?.toLowerCase() === "b3dm") return "mesh";
  return null;
}

function linkedBlockCodes(asset: ImageryAsset) {
  return [...new Set([
    ...asset.linkedBlockCodes,
    ...(asset.coverageAnalysis?.confirmedBlockCodes ?? []),
  ].filter(Boolean))];
}

function boundsAnchor(bounds: ImageryAsset["bounds"]): [number, number] | null {
  if (!bounds?.every(Number.isFinite)) return null;
  const [west, south, east, north] = bounds;
  if (west >= east || south >= north) return null;
  return [(west + east) / 2, (south + north) / 2];
}

export function buildMapAnnotations({
  blocks,
  situationRecords = [],
  imageryAssets = [],
}: {
  blocks?: ForestBlockFeatureCollection;
  situationRecords?: SituationAssetRecord[];
  imageryAssets?: ImageryAsset[];
}): MapAnnotation[] {
  const features = blocks?.features ?? [];
  const featureByCode = new Map(features.map((feature) => [feature.properties.blockCode, feature]));
  const annotations: MapAnnotation[] = [];

  situationRecords.forEach((record) => {
    const feature = featureByCode.get(record.blockCode);
    const anchor = record.longitude !== null && record.latitude !== null
      ? [record.longitude, record.latitude] as [number, number]
      : geometryAnchor(feature?.geometry ?? null);
    if (!anchor) return;
    annotations.push({
      id: `situation:${record.id}`,
      kind: record.kind,
      label: record.name,
      subtitle: record.subtitle,
      longitude: anchor[0],
      latitude: anchor[1],
      sourceType: "situation",
      sourceId: record.id,
      blockId: feature?.id,
      blockCode: record.blockCode || undefined,
    });
  });

  features.forEach((feature) => {
    const tags = feature.properties.tags ?? [];
    const isDemonstration = tags.includes("high-yield-demo")
      || tags.some((tag) => tag.includes("示范"))
      || feature.properties.name.includes("示范");
    const anchor = isDemonstration ? geometryAnchor(feature.geometry) : null;
    if (!anchor) return;
    annotations.push({
      id: `demonstration:${feature.id}`,
      kind: "demonstration",
      label: `${feature.properties.name} · 高产示范`,
      subtitle: [feature.properties.townName, feature.properties.villageName].filter(Boolean).join(" / ") || feature.properties.blockCode,
      longitude: anchor[0],
      latitude: anchor[1],
      sourceType: "forest-block",
      sourceId: feature.id,
      blockId: feature.id,
      blockCode: feature.properties.blockCode,
    });
  });

  const grouped = new Map<string, { kind: MapAnnotationKind; blockCode: string; assets: ImageryAsset[] }>();
  imageryAssets.forEach((asset) => {
    if (asset.visible === false) return;
    const kind = imageryKind(asset);
    if (!kind) return;
    const codes = linkedBlockCodes(asset);
    if (codes.length === 0) {
      const relation = asset.spatialRelation;
      const anchor = relation?.type === "independent-point"
        && Number.isFinite(relation.longitude) && Number.isFinite(relation.latitude)
        ? [Number(relation.longitude), Number(relation.latitude)] as [number, number]
        : boundsAnchor(asset.bounds);
      if (!anchor) return;
      const independent = relation?.type === "independent-point";
      annotations.push({
        id: `imagery:${kind}:unlinked:${asset.id}`,
        kind,
        label: independent ? relation.pointName || asset.name : `${asset.name} · 待关联`,
        subtitle: independent ? `独立空间点位 · ${relation.pointCategory || "其他设施"}` : "成果已入库，尚未关联林班",
        longitude: anchor[0],
        latitude: anchor[1],
        sourceType: "imagery",
        sourceId: asset.id,
        sourceIds: [asset.id],
      });
      return;
    }
    codes.forEach((blockCode) => {
      const key = `${kind}:${blockCode}`;
      const group = grouped.get(key) ?? { kind, blockCode, assets: [] };
      group.assets.push(asset);
      grouped.set(key, group);
    });
  });

  grouped.forEach(({ kind, blockCode, assets }) => {
    const feature = featureByCode.get(blockCode);
    const anchor = geometryAnchor(feature?.geometry ?? null) ?? boundsAnchor(assets[0].bounds);
    if (!anchor) return;
    annotations.push({
      id: `imagery:${kind}:${blockCode}`,
      kind,
      label: `${feature?.properties.name || blockCode} · ${MAP_ANNOTATION_LABELS[kind]}`,
      subtitle: `${assets.length} 项已入库成果`,
      longitude: anchor[0],
      latitude: anchor[1],
      sourceType: "imagery",
      sourceId: assets[0].id,
      sourceIds: assets.map((asset) => asset.id),
      blockId: feature?.id,
      blockCode,
    });
  });

  return annotations.map((annotation) => ({
    ...annotation,
    mapLabel: MAP_ANNOTATION_LABELS[annotation.kind],
  }));
}

export function filterMapAnnotations(
  annotations: MapAnnotation[],
  visibility: Record<MapAnnotationKind, boolean>,
  query = "",
) {
  const keyword = query.trim().toLowerCase();
  return annotations.filter((annotation) => visibility[annotation.kind] && (
    !keyword || `${annotation.label} ${annotation.subtitle ?? ""} ${annotation.blockCode ?? ""} ${MAP_ANNOTATION_LABELS[annotation.kind]}`.toLowerCase().includes(keyword)
  ));
}
