import { useQuery } from "@tanstack/react-query";
import Feature from "ol/Feature";
import GeoJSON from "ol/format/GeoJSON";
import Draw from "ol/interaction/Draw";
import Modify from "ol/interaction/Modify";
import Snap from "ol/interaction/Snap";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import Map from "ol/Map";
import VectorSource from "ol/source/Vector";
import XYZ from "ol/source/XYZ";
import { Stroke, Style } from "ol/style";
import View from "ol/View";
import { Crosshair, FileUp, Pencil, Route, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import "ol/ol.css";

import { api } from "../api/client";
import type { ForestRoadRecord } from "../api/types";

type RoadGeometry = ForestRoadRecord["geometry"] | null;
const format = new GeoJSON();
const roadStyle = new Style({ stroke: new Stroke({ color: "#ffb000", width: 6 }) });

function readGeometry(geometry: RoadGeometry) {
  return geometry ? format.readFeature({ type: "Feature", properties: {}, geometry }, { dataProjection: "EPSG:4326", featureProjection: "EPSG:3857" }) as Feature : null;
}
function writeGeometry(feature: Feature): ForestRoadRecord["geometry"] {
  return format.writeFeatureObject(feature, { dataProjection: "EPSG:4326", featureProjection: "EPSG:3857", decimals: 8 }).geometry as ForestRoadRecord["geometry"];
}
function extractGeometry(input: unknown): ForestRoadRecord["geometry"] {
  if (!input || typeof input !== "object") throw new Error("文件中未找到有效 GeoJSON 道路线");
  const value = input as Record<string, unknown>;
  if (value.type === "Feature") return extractGeometry(value.geometry);
  if (value.type === "FeatureCollection") return extractGeometry(Array.isArray(value.features) ? value.features[0] : null);
  if (value.type !== "LineString" && value.type !== "MultiLineString") throw new Error("仅支持 LineString 或 MultiLineString 道路线");
  if (!Array.isArray(value.coordinates)) throw new Error("GeoJSON 坐标格式不正确");
  return value as unknown as ForestRoadRecord["geometry"];
}

export function RoadGeometryEditor({ value, onChange }: { value: RoadGeometry; onChange: (value: RoadGeometry) => void }) {
  const target = useRef<HTMLDivElement>(null);
  const map = useRef<Map | null>(null);
  const source = useRef(new VectorSource());
  const change = useRef(onChange);
  const [mode, setMode] = useState<"view" | "draw" | "modify">(value ? "modify" : "view");
  const [message, setMessage] = useState("");
  const config = useQuery({ queryKey: ["map-config", "road-editor"], queryFn: api.mapConfig });
  useEffect(() => { change.current = onChange; }, [onChange]);

  const fit = () => {
    const extent = source.current.getExtent();
    if (map.current && extent && extent.every(Number.isFinite)) map.current.getView().fit(extent, { padding: [48, 48, 48, 48], maxZoom: 18, duration: 250 });
  };
  useEffect(() => {
    source.current.clear(); const feature = readGeometry(value); if (feature) source.current.addFeature(feature);
  }, [value]);
  useEffect(() => {
    if (!target.current || config.isPending) return;
    const layers = [];
    if (config.data?.available) {
      layers.push(new TileLayer({ source: new XYZ({ url: config.data.imageryUrl, maxZoom: config.data.maximumLevel }) }));
      layers.push(new TileLayer({ source: new XYZ({ url: config.data.labelsUrl, maxZoom: config.data.maximumLevel }) }));
    }
    layers.push(new VectorLayer({ source: source.current, style: roadStyle }));
    const instance = new Map({ target: target.current, layers, view: new View({ center: [13110000, 3140000], zoom: 10 }) });
    map.current = instance;
    const modify = new Modify({ source: source.current });
    modify.on("modifyend", () => { const feature = source.current.getFeatures()[0]; if (feature) change.current(writeGeometry(feature)); setMessage("道路线节点已修改，保存后正式入库。"); });
    modify.setActive(mode === "modify"); instance.addInteraction(modify); instance.addInteraction(new Snap({ source: source.current }));
    return () => { instance.setTarget(undefined); map.current = null; };
  }, [config.data, config.isPending]);
  useEffect(() => {
    const instance = map.current; if (!instance) return;
    const modify = instance.getInteractions().getArray().find((item) => item instanceof Modify) as Modify | undefined;
    modify?.setActive(mode === "modify");
    if (mode !== "draw") return;
    const draw = new Draw({ source: source.current, type: "LineString" });
    draw.on("drawstart", () => source.current.clear());
    draw.on("drawend", (event) => { change.current(writeGeometry(event.feature)); setMode("modify"); setMessage("道路线已绘制，可拖动节点继续调整。"); });
    instance.addInteraction(draw); return () => { instance.removeInteraction(draw); };
  }, [mode]);

  const importFile = async (file?: File) => {
    if (!file) return;
    try { const geometry = extractGeometry(JSON.parse(await file.text())); onChange(geometry); setMode("modify"); setMessage("GeoJSON 道路线已载入。"); window.setTimeout(fit, 0); }
    catch (error) { setMessage(error instanceof Error ? error.message : "文件解析失败"); }
  };
  return <div className="boundary-editor road-geometry-editor">
    <div className="boundary-toolbar"><button className="button secondary" type="button" onClick={() => setMode("draw")}><Route />绘制道路线</button><button className="button secondary" type="button" disabled={!value} onClick={() => setMode("modify")}><Pencil />编辑节点</button><button className="button secondary" type="button" disabled={!value} onClick={fit}><Crosshair />定位路线</button><label className="button secondary file-button"><FileUp />导入 GeoJSON<input type="file" accept=".geojson,.json,application/geo+json" onChange={(event) => void importFile(event.target.files?.[0])} /></label><button className="icon-button danger" type="button" disabled={!value} onClick={() => onChange(null)} aria-label="清空道路线"><Trash2 /></button></div>
    <div className="boundary-map" ref={target}><span className="map-loading">正在载入道路空间编辑器</span></div>
    <div className="boundary-status"><span>{value ? "道路线已就绪" : "尚未绘制道路线"}</span><small>{message || "长度留空时，平台按 WGS84 道路线自动估算公里数。"}</small></div>
  </div>;
}
