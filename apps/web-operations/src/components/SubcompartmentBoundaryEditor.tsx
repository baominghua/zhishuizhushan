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
import { Fill, Stroke, Style } from "ol/style";
import View from "ol/View";
import { useEffect, useRef, useState } from "react";
import { Crosshair, FileUp, MapPinned, Pencil, RotateCcw, Trash2 } from "lucide-react";
import "ol/ol.css";

import { api } from "../api/client";

type GeometryValue = Record<string, unknown> | null;

interface Props {
  parentGeometry?: GeometryValue;
  value: GeometryValue;
  onChange: (geometry: GeometryValue) => void;
  entityLabel?: string;
}

const format = new GeoJSON();
const parentStyle = new Style({
  fill: new Fill({ color: "rgba(21, 118, 91, 0.08)" }),
  stroke: new Stroke({ color: "rgba(17, 94, 71, 0.95)", width: 3, lineDash: [10, 7] }),
});
const childStyle = new Style({
  fill: new Fill({ color: "rgba(255, 207, 64, 0.34)" }),
  stroke: new Stroke({ color: "#e7a900", width: 4 }),
});

function readGeometry(geometry: GeometryValue) {
  if (!geometry) return null;
  return format.readFeature({ type: "Feature", properties: {}, geometry }, {
    dataProjection: "EPSG:4326",
    featureProjection: "EPSG:3857",
  }) as Feature;
}

function writeGeometry(feature: Feature): GeometryValue {
  const output = format.writeFeatureObject(feature, {
    dataProjection: "EPSG:4326",
    featureProjection: "EPSG:3857",
    decimals: 8,
  });
  return (output.geometry || null) as unknown as GeometryValue;
}

function extractGeometry(input: unknown): GeometryValue {
  if (!input || typeof input !== "object") throw new Error("文件中未找到有效 GeoJSON 图形");
  const value = input as Record<string, unknown>;
  if (value.type === "Feature") return extractGeometry(value.geometry);
  if (value.type === "FeatureCollection") {
    const first = Array.isArray(value.features) ? value.features[0] : null;
    return extractGeometry(first);
  }
  if (value.type !== "Polygon" && value.type !== "MultiPolygon") {
    throw new Error("仅支持 Polygon 或 MultiPolygon 面边界");
  }
  if (!Array.isArray(value.coordinates)) throw new Error("GeoJSON 坐标格式不正确");
  return value;
}

export function BoundaryEditor({ parentGeometry, value, onChange, entityLabel = "小班" }: Props) {
  const targetRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const childSourceRef = useRef(new VectorSource());
  const parentSourceRef = useRef(new VectorSource());
  const historyRef = useRef<GeometryValue[]>([]);
  const modifyStartRef = useRef<GeometryValue>(null);
  const onChangeRef = useRef(onChange);
  const [mode, setMode] = useState<"view" | "draw" | "modify">(value ? "modify" : "view");
  const [importOpen, setImportOpen] = useState(false);
  const [geojsonText, setGeojsonText] = useState("");
  const [message, setMessage] = useState("");
  const [historySize, setHistorySize] = useState(0);
  const constrainedByParent = parentGeometry !== undefined;
  const canDraw = !constrainedByParent || Boolean(parentGeometry);
  const config = useQuery({ queryKey: ["map-config", "subcompartment-editor"], queryFn: api.mapConfig });

  useEffect(() => { onChangeRef.current = onChange; }, [onChange]);

  const fitSource = (source: VectorSource) => {
    const extent = source.getExtent();
    if (!mapRef.current || !extent || extent.some((entry) => !Number.isFinite(entry))) return;
    mapRef.current.getView().fit(extent, { padding: [42, 42, 42, 42], maxZoom: 18, duration: 250 });
  };
  const pushHistory = (geometry: GeometryValue) => {
    historyRef.current.push(geometry ? structuredClone(geometry) : null);
    if (historyRef.current.length > 30) historyRef.current.shift();
    setHistorySize(historyRef.current.length);
  };
  const replaceChild = (geometry: GeometryValue, notify = true) => {
    const source = childSourceRef.current;
    source.clear();
    const feature = readGeometry(geometry);
    if (feature) source.addFeature(feature);
    if (notify) onChangeRef.current(geometry);
  };

  useEffect(() => {
    if (!targetRef.current || config.isPending) return;
    const layers = [];
    if (config.data?.available) {
      layers.push(new TileLayer({ source: new XYZ({ url: config.data.imageryUrl, maxZoom: config.data.maximumLevel }) }));
      layers.push(new TileLayer({ source: new XYZ({ url: config.data.labelsUrl, maxZoom: config.data.maximumLevel }) }));
    }
    layers.push(new VectorLayer({ source: parentSourceRef.current, style: parentStyle }));
    layers.push(new VectorLayer({ source: childSourceRef.current, style: childStyle }));
    const map = new Map({ target: targetRef.current, layers, view: new View({ center: [0, 0], zoom: 2 }) });
    mapRef.current = map;
    const modify = new Modify({ source: childSourceRef.current });
    modify.on("modifystart", () => {
      const feature = childSourceRef.current.getFeatures()[0];
      modifyStartRef.current = feature ? writeGeometry(feature) : null;
    });
    modify.on("modifyend", () => {
      const feature = childSourceRef.current.getFeatures()[0];
      if (!feature) return;
      pushHistory(modifyStartRef.current);
      onChangeRef.current(writeGeometry(feature));
      setMessage("边界节点已修改，保存表单后正式入库。 ");
    });
    modify.setActive(mode === "modify");
    map.addInteraction(modify);
    map.addInteraction(new Snap({ source: childSourceRef.current }));
    return () => { map.setTarget(undefined); mapRef.current = null; };
  // Map is intentionally created once for each resolved basemap configuration.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.data, config.isPending]);

  useEffect(() => {
    const source = parentSourceRef.current;
    source.clear();
    const feature = readGeometry(parentGeometry ?? null);
    if (feature) source.addFeature(feature);
    if (feature) window.setTimeout(() => fitSource(source), 0);
  }, [parentGeometry]);

  useEffect(() => { replaceChild(value, false); }, [value]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const modify = map.getInteractions().getArray().find((item) => item instanceof Modify) as Modify | undefined;
    modify?.setActive(mode === "modify");
    if (mode !== "draw") return;
    const draw = new Draw({ source: childSourceRef.current, type: "Polygon" });
    draw.on("drawstart", () => {
      const existing = childSourceRef.current.getFeatures()[0];
      pushHistory(existing ? writeGeometry(existing) : null);
      childSourceRef.current.clear();
    });
    draw.on("drawend", (event) => {
      onChangeRef.current(writeGeometry(event.feature));
      setMode("modify");
      setMessage("边界已绘制，可拖动节点继续调整。 ");
    });
    map.addInteraction(draw);
    return () => { map.removeInteraction(draw); };
  }, [mode]);

  const importGeometry = (geometry: GeometryValue) => {
    pushHistory(value);
    replaceChild(geometry);
    setMode("modify");
    setImportOpen(false);
    setMessage("GIS 边界已载入，可继续编辑节点。 ");
    window.setTimeout(() => fitSource(childSourceRef.current), 0);
  };
  const parseText = () => {
    try { importGeometry(extractGeometry(JSON.parse(geojsonText))); }
    catch (error) { setMessage(error instanceof Error ? error.message : "GeoJSON 解析失败"); }
  };
  const importFile = async (file: File | undefined) => {
    if (!file) return;
    try { importGeometry(extractGeometry(JSON.parse(await file.text()))); }
    catch (error) { setMessage(error instanceof Error ? error.message : "文件解析失败"); }
  };
  const undo = () => {
    const previous = historyRef.current.pop();
    if (previous === undefined) return;
    replaceChild(previous);
    setHistorySize(historyRef.current.length);
    setMessage("已撤销上一步边界修改。 ");
  };
  const clear = () => { pushHistory(value); replaceChild(null); setMode("view"); setMessage("边界已清空，保存后生效。 "); };

  return <div className="boundary-editor">
    <div className="boundary-toolbar" role="toolbar" aria-label={`${entityLabel}边界编辑工具`}>
      <button className={`button secondary ${mode === "draw" ? "active" : ""}`} type="button" disabled={!canDraw} onClick={() => setMode("draw")}><MapPinned aria-hidden="true" />绘制边界</button>
      <button className={`button secondary ${mode === "modify" ? "active" : ""}`} type="button" disabled={!value} onClick={() => setMode("modify")}><Pencil aria-hidden="true" />编辑节点</button>
      <button className="button secondary" type="button" disabled={constrainedByParent ? !parentGeometry : !value} onClick={() => fitSource(constrainedByParent ? parentSourceRef.current : childSourceRef.current)}><Crosshair aria-hidden="true" />{constrainedByParent ? "定位林班" : "定位边界"}</button>
      <button className="button secondary" type="button" disabled={!historySize} onClick={undo}><RotateCcw aria-hidden="true" />撤销</button>
      <label className="button secondary file-button"><FileUp aria-hidden="true" />导入文件<input type="file" accept=".geojson,.json,application/geo+json,application/json" onChange={(event) => void importFile(event.target.files?.[0])} /></label>
      <button className="text-button" type="button" onClick={() => setImportOpen((open) => !open)}>粘贴 GeoJSON</button>
      <button className="icon-button danger" type="button" disabled={!value} onClick={clear} aria-label="清空边界" title="清空边界"><Trash2 aria-hidden="true" /></button>
    </div>
    {constrainedByParent && !parentGeometry && <div className="boundary-warning">该父林班尚无空间边界。请先在林班台账补图，或更换已入库边界的林班。</div>}
    {config.isError && <div className="boundary-warning">底图暂不可用，仍可绘制或导入 GeoJSON 边界。</div>}
    <div className="boundary-map" ref={targetRef}><span className="map-loading">正在载入空间编辑器</span></div>
    {importOpen && <div className="geojson-import"><textarea value={geojsonText} onChange={(event) => setGeojsonText(event.target.value)} placeholder='粘贴 Polygon、MultiPolygon、Feature 或 FeatureCollection GeoJSON' /><div><button className="button secondary" type="button" onClick={() => setImportOpen(false)}>取消</button><button className="button primary" type="button" onClick={parseText}>载入边界</button></div></div>}
    <div className="boundary-status"><span>{value ? `${entityLabel}边界已就绪` : `尚未绘制${entityLabel}边界`}</span><small>{message || (constrainedByParent ? "保存时将校验小班边界必须完整位于父林班内。" : "保存时将校验边界有效性；已有小班时还会检查空间包含关系。")}</small></div>
  </div>;
}

export const SubcompartmentBoundaryEditor = BoundaryEditor;
