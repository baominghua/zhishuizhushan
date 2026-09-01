import Feature from "ol/Feature";
import GeoJSON from "ol/format/GeoJSON";
import Point from "ol/geom/Point";
import Map from "ol/Map";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import { defaults as defaultInteractions } from "ol/interaction/defaults";
import MouseWheelZoom from "ol/interaction/MouseWheelZoom";
import { fromLonLat, transformExtent } from "ol/proj";
import VectorSource from "ol/source/Vector";
import XYZ from "ol/source/XYZ";
import { Circle as CircleStyle, Fill, RegularShape, Stroke, Style } from "ol/style";
import View from "ol/View";
import { useEffect, useRef } from "react";
import "ol/ol.css";

import type { ImageryAsset } from "../api/types";

interface CandidateLocation { longitude: number; latitude: number; score: number }

export function MosoInventoryEvidenceMap({ asset, geometry, candidates, blockName }: {
  asset: ImageryAsset;
  geometry: Record<string, unknown> | null;
  candidates: CandidateLocation[];
  blockName: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!containerRef.current) return;
    const imagery = new TileLayer({
      source: new XYZ({ url: asset.tileUrl, maxZoom: asset.maximumZoom || 24, crossOrigin: "anonymous", transition: 120 }),
    });
    const boundarySource = new VectorSource();
    if (geometry) {
      const [boundary] = new GeoJSON().readFeatures({ type: "FeatureCollection", features: [{ type: "Feature", properties: { name: blockName }, geometry }] }, { dataProjection: "EPSG:4326", featureProjection: "EPSG:3857" });
      if (boundary) { boundary.setId("selected-forest-block"); boundarySource.addFeature(boundary); }
    }
    const boundaryCasing = new VectorLayer({ source: boundarySource, style: new Style({ fill: new Fill({ color: "rgba(11, 49, 39, 0.015)" }), stroke: new Stroke({ color: "rgba(1, 18, 24, 0.96)", width: 6.4 }) }), zIndex: 10 });
    const boundaryLine = new VectorLayer({ source: boundarySource, style: new Style({ stroke: new Stroke({ color: "#35d6ff", width: 2.6 }) }), zIndex: 11 });
    const pointSource = new VectorSource({ features: candidates.map((candidate, index) => new Feature({ geometry: new Point(fromLonLat([candidate.longitude, candidate.latitude])), score: candidate.score, index })) });
    const pointLayer = new VectorLayer({ source: pointSource, declutter: false, zIndex: 12, style: (feature) => {
      const score = Number(feature.get("score") || 0.5);
      return [
        new Style({ image: new CircleStyle({ radius: 7.6, fill: new Fill({ color: "rgba(2, 13, 20, .88)" }), stroke: new Stroke({ color: "rgba(255, 255, 255, .96)", width: 1.35 }) }) }),
        new Style({ image: new RegularShape({ points: 4, radius: 3.4 + Math.max(0, Math.min(1, score)) * 1.4, angle: Math.PI / 4, fill: new Fill({ color: "#ffb000" }), stroke: new Stroke({ color: "#3b2100", width: 1.15 }) }) }),
      ];
    } });
    const view = new View({ center: fromLonLat([(asset.bounds[0] + asset.bounds[2]) / 2, (asset.bounds[1] + asset.bounds[3]) / 2]), zoom: 17, minZoom: 12, maxZoom: asset.maximumZoom || 24, constrainResolution: true, smoothResolutionConstraint: true });
    const map = new Map({ target: containerRef.current, layers: [imagery, boundaryCasing, boundaryLine, pointLayer], view, interactions: defaultInteractions({ mouseWheelZoom: false }).extend([new MouseWheelZoom({ duration: 260, timeout: 90, maxDelta: 1 })]) });
    const boundaryExtent = boundarySource.getExtent();
    if (geometry && boundaryExtent && boundaryExtent.every(Number.isFinite)) view.fit(boundaryExtent, { padding: [48, 48, 80, 48], duration: 0, maxZoom: Math.min(asset.maximumZoom || 22, 21) });
    else view.fit(transformExtent(asset.bounds, "EPSG:4326", "EPSG:3857"), { padding: [40, 40, 80, 40], duration: 0, maxZoom: 20 });
    return () => map.setTarget(undefined);
  }, [asset, blockName, candidates, geometry]);
  return <div className="moso-evidence-map" ref={containerRef} aria-label={`${blockName} 正射影像与竹冠候选点沙盘`} />;
}
