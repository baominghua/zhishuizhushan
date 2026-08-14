import type {
  ForestBlockFeatureCollection,
  ForestBlockMapFeature,
  ForestBlockOption,
  ForestBlockRecord,
} from "../api/types";

export const EMPTY_FOREST_BLOCK_COLLECTION: ForestBlockFeatureCollection = {
  type: "FeatureCollection",
  meta: {
    total: 0,
    returned: 0,
    maxFeatures: 0,
    truncated: false,
    zoom: 8,
    geometryMode: "simplified",
    simplificationTolerance: 0,
  },
  features: [],
};

export function forestBlockColor(riskLevel: string | null | undefined) {
  const risk = (riskLevel ?? "").toLowerCase();
  if (risk.includes("高") || risk.includes("high")) return "#e05d44";
  if (risk.includes("中") || risk.includes("medium")) return "#d5a62e";
  if (risk.includes("低") || risk.includes("low")) return "#36a96b";
  return "#31a77c";
}

export function recordToOption(record: ForestBlockRecord): ForestBlockOption {
  return {
    id: record.id,
    code: record.blockCode,
    name: record.name,
    location: [record.countyName, record.townName, record.villageName].filter(Boolean).join(" / "),
    areaMu: record.areaMu,
    hasGeometry: Boolean(record.geometry),
    riskLevel: record.riskLevel,
  };
}

export function featureToOption(feature: ForestBlockMapFeature): ForestBlockOption {
  return {
    id: feature.properties.id,
    code: feature.properties.blockCode,
    name: feature.properties.name,
    location: [
      feature.properties.countyName,
      feature.properties.townName,
      feature.properties.villageName,
    ].filter(Boolean).join(" / "),
    areaMu: feature.properties.areaMu,
    hasGeometry: Boolean(feature.geometry),
    riskLevel: feature.properties.riskLevel,
  };
}

export function mergeSelectedForestBlock(
  collection: ForestBlockFeatureCollection | undefined,
  selected: ForestBlockRecord | undefined,
): ForestBlockFeatureCollection {
  const base = collection ?? EMPTY_FOREST_BLOCK_COLLECTION;
  if (!selected?.geometry || base.features.some((feature) => feature.id === selected.id)) return base;
  const { geometry, ...properties } = selected;

  return {
    ...base,
    features: [
      ...base.features,
      {
        type: "Feature",
        id: selected.id,
        geometry: geometry as ForestBlockMapFeature["geometry"],
        properties,
      },
    ],
  };
}
