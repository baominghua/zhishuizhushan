import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  BrainCircuit,
  Check,
  CloudSun,
  Crosshair,
  Database,
  ExternalLink,
  Layers3,
  ScanSearch,
  Sprout,
} from "lucide-react";
import { useMemo } from "react";

import { api } from "../api/client";
import type { ForestBlockRecord, MosoInventoryEstimate } from "../api/types";
import { QueryState } from "../components/QueryState";

type Coordinate = [number, number];
type PolygonRings = { outer: Coordinate[]; holes: Coordinate[][] };
type ProjectedPoint = { x: number; y: number; strength: number };

const VIEW_WIDTH = 980;
const VIEW_HEIGHT = 720;
const VIEW_PADDING = 64;

function numberValue(record: Record<string, unknown>, key: string) {
  const value = Number(record[key]);
  return Number.isFinite(value) ? value : 0;
}

function textValue(record: Record<string, unknown>, key: string) {
  return String(record[key] ?? "").trim();
}

function formatNumber(value: number, digits = 0) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function formatDateTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function toCoordinate(value: unknown): Coordinate | null {
  if (!Array.isArray(value) || value.length < 2) return null;
  const x = Number(value[0]);
  const y = Number(value[1]);
  return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null;
}

function polygonRings(geometry: Record<string, unknown> | null): PolygonRings[] {
  if (!geometry || !Array.isArray(geometry.coordinates)) return [];
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.type === "MultiPolygon" ? geometry.coordinates : [];
  return polygons.flatMap((polygon) => {
    if (!Array.isArray(polygon) || !polygon.length) return [];
    const rings = polygon.map((ring) => Array.isArray(ring) ? ring.map(toCoordinate).filter((item): item is Coordinate => Boolean(item)) : []);
    return rings[0]?.length >= 3 ? [{ outer: rings[0], holes: rings.slice(1).filter((ring) => ring.length >= 3) }] : [];
  });
}

function pointInRing(point: Coordinate, ring: Coordinate[]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersects = ((yi > point[1]) !== (yj > point[1]))
      && point[0] < ((xj - xi) * (point[1] - yi)) / ((yj - yi) || Number.EPSILON) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

function pointInPolygons(point: Coordinate, polygons: PolygonRings[]) {
  return polygons.some((polygon) => pointInRing(point, polygon.outer) && !polygon.holes.some((hole) => pointInRing(point, hole)));
}

function halton(index: number, base: number) {
  let result = 0;
  let fraction = 1 / base;
  let current = index;
  while (current > 0) {
    result += fraction * (current % base);
    current = Math.floor(current / base);
    fraction /= base;
  }
  return result;
}

function blockProjection(record: ForestBlockRecord, estimatedCulms: number) {
  const polygons = polygonRings(record.geometry);
  const coordinates = polygons.flatMap((polygon) => polygon.outer);
  if (!coordinates.length) return { paths: [] as string[], points: [] as ProjectedPoint[], representativeWeight: 0 };
  const minX = Math.min(...coordinates.map(([x]) => x));
  const maxX = Math.max(...coordinates.map(([x]) => x));
  const minY = Math.min(...coordinates.map(([, y]) => y));
  const maxY = Math.max(...coordinates.map(([, y]) => y));
  const spanX = Math.max(maxX - minX, 1e-8);
  const spanY = Math.max(maxY - minY, 1e-8);
  const scale = Math.min((VIEW_WIDTH - VIEW_PADDING * 2) / spanX, (VIEW_HEIGHT - VIEW_PADDING * 2) / spanY);
  const offsetX = (VIEW_WIDTH - spanX * scale) / 2;
  const offsetY = (VIEW_HEIGHT - spanY * scale) / 2;
  const project = ([x, y]: Coordinate): Coordinate => [offsetX + (x - minX) * scale, VIEW_HEIGHT - offsetY - (y - minY) * scale];
  const ringPath = (ring: Coordinate[]) => ring.map((coordinate, index) => `${index ? "L" : "M"}${project(coordinate).join(" ")}`).join(" ") + " Z";
  const paths = polygons.map((polygon) => [ringPath(polygon.outer), ...polygon.holes.map(ringPath)].join(" "));
  const targetCount = Math.min(320, Math.max(48, Math.round(Math.sqrt(Math.max(estimatedCulms, 1)) * 2.4)));
  const points: ProjectedPoint[] = [];
  let attempt = 1;
  const seed = [...record.blockCode].reduce((total, char) => total + char.charCodeAt(0), 0) % 97;
  while (points.length < targetCount && attempt < targetCount * 80) {
    const sampleIndex = attempt + seed;
    const coordinate: Coordinate = [minX + halton(sampleIndex, 2) * spanX, minY + halton(sampleIndex, 3) * spanY];
    if (pointInPolygons(coordinate, polygons)) {
      const [x, y] = project(coordinate);
      points.push({ x, y, strength: 0.58 + halton(sampleIndex, 5) * 0.42 });
    }
    attempt += 1;
  }
  return {
    paths,
    points,
    representativeWeight: points.length ? Math.max(1, Math.round(estimatedCulms / points.length)) : 0,
  };
}

function estimateFrom(record?: ForestBlockRecord) {
  return record?.yieldEstimate?.mosoInventory as MosoInventoryEstimate | undefined;
}

export function MosoInventorySandboxPage() {
  const blockId = useMemo(() => new URLSearchParams(window.location.search).get("blockId") || "", []);
  const blockQuery = useQuery({
    queryKey: ["moso-inventory-sandbox", blockId],
    queryFn: () => api.forestBlockDetail(blockId),
    enabled: Boolean(blockId),
    staleTime: 30_000,
  });
  const record = blockQuery.data;
  const estimate = estimateFrom(record);
  const projection = useMemo(
    () => record && estimate ? blockProjection(record, estimate.resourceStock.value) : { paths: [], points: [], representativeWeight: 0 },
    [estimate, record],
  );

  if (!blockId) return <div className="moso-sandbox-page"><div className="moso-sandbox-empty"><BrainCircuit /><h1>缺少林班参数</h1><p>请从 GIS 林班卡片或林班台账进入 AI 估算沙盘。</p><a className="button primary" href="/v2/map">返回 GIS 一张图</a></div></div>;

  return <div className="moso-sandbox-page">
    <header className="moso-sandbox-header">
      <a className="moso-sandbox-back" href={`/v2/map?blockId=${encodeURIComponent(blockId)}`}><ArrowLeft aria-hidden="true" /><span>返回林班</span></a>
      <div><small>毛竹资源 AI 试算</small><h1>{record?.name || "林班估算沙盘"}</h1></div>
      <div className="moso-sandbox-model"><span>模型</span><strong>{estimate?.modelVersion || "等待结果"}</strong></div>
    </header>
    <QueryState loading={blockQuery.isLoading} error={blockQuery.error}>
      {!record || !estimate ? <div className="moso-sandbox-empty"><ScanSearch /><h2>该林班暂无试算结果</h2><p>请先在林班台账执行“生成试算”，完成后即可查看空间沙盘。</p><a className="button primary" href="/v2/resources/forest-blocks">进入林班台账</a></div> : <>
        <div className="moso-sandbox-layout">
          <aside className="moso-process-panel">
            <div className="moso-panel-heading"><span>模型流水线</span><strong>计算过程</strong></div>
            <ProcessStep icon={Database} title="证据装载" detail={textValue(estimate.imageryEvidence, "name") || "已关联正射影像"} />
            <ProcessStep icon={Crosshair} title="林班边界裁切" detail={`${formatNumber(numberValue(estimate.imageryEvidence, "validPixelCount"))} 个有效像素`} />
            <ProcessStep icon={CloudSun} title="RGB 冠层分割" detail={`阈值 ${numberValue(estimate.imageryEvidence, "canopyThreshold").toFixed(4)} · 覆盖 ${estimate.canopyClosure.value}%`} />
            <ProcessStep icon={ScanSearch} title="竹冠等价峰值" detail={`${formatNumber(estimate.crownEquivalentCount.value)} 个候选峰值`} />
            <ProcessStep icon={Sprout} title="密度与株数外推" detail={`${formatNumber(estimate.stemDensity.value, 1)} 株/亩`} />
            <ProcessStep icon={BrainCircuit} title="置信度评估" detail={`${estimate.confidence.level} · ${Math.round(estimate.confidence.score * 100)}%`} />
            <div className={`moso-evidence-status ${estimate.pointCloudEvidence.available ? "available" : ""}`}><Layers3 /><div><strong>{estimate.pointCloudEvidence.available ? "点云证据已关联" : "仅使用 RGB 证据"}</strong><small>{estimate.pointCloudEvidence.available ? textValue(estimate.pointCloudEvidence, "name") || "可用于后续结构校准" : "补充分类点云可提升结构参数"}</small></div></div>
          </aside>

          <main className="moso-sandbox-stage">
            <div className="moso-stage-heading"><div><span>林班模拟沙盘</span><strong>{record.blockCode}</strong></div><div><i />代表性抽样点 · 每点约 {formatNumber(projection.representativeWeight)} 株</div></div>
            <div className="moso-stage-canvas">
              <svg viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} role="img" aria-label={`${record.name} 毛竹资源估算代表性点位分布`}>
                <defs>
                  <linearGradient id="moso-block-fill" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#0f6c52" /><stop offset="1" stopColor="#173e36" /></linearGradient>
                  <filter id="moso-point-glow"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
                  <pattern id="moso-grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M36 0H0V36" fill="none" stroke="rgba(150, 233, 198, .08)" /></pattern>
                </defs>
                <rect width={VIEW_WIDTH} height={VIEW_HEIGHT} fill="url(#moso-grid)" />
                {projection.paths.map((path, index) => <path className="moso-block-shape" d={path} fillRule="evenodd" key={index} />)}
                {projection.points.map((point, index) => <g key={index} className="moso-sample-point" style={{ animationDelay: `${(index % 24) * 45}ms` }}><circle cx={point.x} cy={point.y} r={2.1 + point.strength * 1.8} opacity={point.strength} /><circle className="pulse" cx={point.x} cy={point.y} r="8" /></g>)}
              </svg>
              <div className="moso-scan-line" />
              <div className="moso-stage-caption"><Crosshair /><span>点位为按林班边界和估算总量生成的<strong>代表性空间抽样</strong>，用于观察密度与覆盖关系，不等同于逐株坐标。</span></div>
            </div>
          </main>

          <aside className="moso-summary-panel">
            <div className="moso-panel-heading"><span>试算结果</span><strong>资源汇总</strong></div>
            <Metric label="资源株数" value={formatNumber(estimate.resourceStock.value)} unit="株" detail={`${formatNumber(estimate.resourceStock.lower)}–${formatNumber(estimate.resourceStock.upper)} 株`} />
            <div className="moso-summary-grid"><Metric label="林班面积" value={formatNumber(estimate.blockArea.value, 2)} unit={estimate.blockArea.unit} /><Metric label="密度" value={formatNumber(estimate.stemDensity.value, 1)} unit={estimate.stemDensity.unit} /></div>
            <div className="moso-summary-grid"><Metric label="冠层覆盖" value={formatNumber(estimate.canopyClosure.value, 1)} unit="%" /><Metric label="地上生物量" value={formatNumber(estimate.abovegroundBiomass.value, 1)} unit="t" /></div>
            <section className="moso-confidence"><div><span>结果置信度</span><strong>{estimate.confidence.level}</strong></div><div className="moso-confidence-track"><i style={{ width: `${Math.round(estimate.confidence.score * 100)}%` }} /></div><small>{Math.round(estimate.confidence.score * 100)}% · 科研试算</small></section>
            <dl className="moso-evidence-list"><div><dt>影像分辨率</dt><dd>{numberValue(estimate.imageryEvidence, "nativeResolutionM") || "—"} m</dd></div><div><dt>影像覆盖率</dt><dd>{numberValue(estimate.imageryEvidence, "imageCoveragePct") || "—"}%</dd></div><div><dt>分析分辨率</dt><dd>{numberValue(estimate.imageryEvidence, "analysisResolutionM") || "—"} m</dd></div><div><dt>估算时间</dt><dd>{formatDateTime(estimate.estimatedAt)}</dd></div></dl>
            {textValue(estimate.imageryEvidence, "sceneId") && <a className="button secondary moso-evidence-link" href={`/v2/asset-viewer?sceneId=${encodeURIComponent(textValue(estimate.imageryEvidence, "sceneId"))}&mode=2d&blockId=${encodeURIComponent(record.id)}`} target="_blank" rel="noreferrer"><ExternalLink />查看证据影像</a>}
          </aside>
        </div>
        <footer className="moso-sandbox-footer"><span>{estimate.method?.name || "RGB 多尺度冠层分割与资源量试算"}</span><p>{estimate.disclaimer}</p></footer>
      </>}
    </QueryState>
  </div>;
}

function ProcessStep({ icon: Icon, title, detail }: { icon: typeof Database; title: string; detail: string }) {
  return <div className="moso-process-step"><div><Icon /><Check className="moso-step-check" /></div><span><strong>{title}</strong><small>{detail}</small></span></div>;
}

function Metric({ label, value, unit, detail = "" }: { label: string; value: string; unit: string; detail?: string }) {
  return <section className="moso-summary-metric"><span>{label}</span><div><strong>{value}</strong><small>{unit}</small></div>{detail && <p>{detail}</p>}</section>;
}
