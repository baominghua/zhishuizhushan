import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BrainCircuit, Check, CloudSun, Crosshair, Database, ExternalLink, Layers3, ScanSearch, Sprout } from "lucide-react";
import { useMemo } from "react";

import { api } from "../api/client";
import type { ForestBlockRecord, MosoInventoryEstimate } from "../api/types";
import { MosoInventoryEvidenceMap } from "../components/MosoInventoryEvidenceMap";
import { QueryState } from "../components/QueryState";

function numberValue(record: Record<string, unknown>, key: string) { const value = Number(record[key]); return Number.isFinite(value) ? value : 0; }
function textValue(record: Record<string, unknown>, key: string) { return String(record[key] ?? "").trim(); }
function formatNumber(value: number, digits = 0) { return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits }); }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false }); }
function estimateFrom(record?: ForestBlockRecord) { return record?.yieldEstimate?.mosoInventory as MosoInventoryEstimate | undefined; }

export function MosoInventorySandboxPage() {
  const blockId = useMemo(() => new URLSearchParams(window.location.search).get("blockId") || "", []);
  const blockQuery = useQuery({ queryKey: ["moso-inventory-sandbox", blockId], queryFn: () => api.forestBlockDetail(blockId), enabled: Boolean(blockId), staleTime: 30_000 });
  const record = blockQuery.data;
  const estimate = estimateFrom(record);
  const imagerySceneId = estimate ? textValue(estimate.imageryEvidence, "sceneId") : "";
  const imageryQuery = useQuery({ queryKey: ["moso-inventory-evidence", imagerySceneId], queryFn: () => api.imageryAsset(imagerySceneId), enabled: Boolean(imagerySceneId), staleTime: 60_000 });
  const candidates = estimate?.crownCandidateLocations ?? [];
  const pointCloudSceneId = estimate ? textValue(estimate.pointCloudEvidence, "sceneId") : "";

  if (!blockId) return <div className="moso-sandbox-page"><div className="moso-sandbox-empty"><BrainCircuit /><h1>缺少林班参数</h1><p>请从 GIS 林班卡片或林班台账进入 AI 估算沙盘。</p><a className="button primary" href="/v2/map">返回 GIS 一张图</a></div></div>;
  return <div className="moso-sandbox-page">
    <header className="moso-sandbox-header"><a className="moso-sandbox-back" href={`/v2/map?blockId=${encodeURIComponent(blockId)}`}><ArrowLeft /><span>返回林班</span></a><div><small>毛竹资源 AI 试算</small><h1>{record?.name || "林班估算沙盘"}</h1></div><div className="moso-sandbox-model"><span>模型</span><strong>{estimate?.modelVersion || "等待结果"}</strong></div></header>
    <QueryState loading={blockQuery.isLoading} error={blockQuery.error}>{!record || !estimate ? <div className="moso-sandbox-empty"><ScanSearch /><h2>该林班暂无试算结果</h2><p>请先在林班台账执行“生成试算”，完成后即可查看真实影像沙盘。</p><a className="button primary" href="/v2/resources/forest-blocks">进入林班台账</a></div> : <>
      <div className="moso-sandbox-layout">
        <aside className="moso-process-panel"><div className="moso-panel-heading"><span>模型流水线</span><strong>计算过程</strong></div><ProcessStep icon={Database} title="证据装载" detail={textValue(estimate.imageryEvidence, "name") || "已关联正射影像"} /><ProcessStep icon={Crosshair} title="林班边界裁切" detail={`${formatNumber(numberValue(estimate.imageryEvidence, "validPixelCount"))} 个有效像素`} /><ProcessStep icon={CloudSun} title="RGB 冠层分割" detail={`阈值 ${numberValue(estimate.imageryEvidence, "canopyThreshold").toFixed(4)} · 覆盖 ${estimate.canopyClosure.value}%`} /><ProcessStep icon={ScanSearch} title="竹冠候选提取" detail={`${formatNumber(estimate.crownEquivalentCount.value)} 个等价峰值`} /><ProcessStep icon={Sprout} title="密度与株数外推" detail={`${formatNumber(estimate.stemDensity.value, 1)} 株/亩`} /><ProcessStep icon={BrainCircuit} title="置信度评估" detail={`${estimate.confidence.level} · ${Math.round(estimate.confidence.score * 100)}%`} /><div className={`moso-evidence-status ${estimate.pointCloudEvidence.available ? "available" : ""}`}><Layers3 /><div><strong>{estimate.pointCloudEvidence.available ? "点云证据已关联" : "当前使用 RGB 证据"}</strong><small>{estimate.pointCloudEvidence.available ? textValue(estimate.pointCloudEvidence, "name") || "可进入三维窗口核验林分结构" : "补充分类点云可提升结构参数"}</small></div></div></aside>
        <main className="moso-sandbox-stage"><div className="moso-stage-heading"><div><span>真实影像沙盘</span><strong>{record.blockCode}</strong></div><div><i />竹冠候选点 {formatNumber(candidates.length)} 个</div></div><div className="moso-stage-canvas real-imagery">
          {imageryQuery.data ? <MosoInventoryEvidenceMap asset={imageryQuery.data} geometry={record.geometry ?? null} candidates={candidates} blockName={record.name} /> : <div className="moso-map-empty"><ScanSearch /><strong>{imageryQuery.isLoading ? "正在装载正射证据" : "未找到可展示的正射证据"}</strong><small>{imageryQuery.error instanceof Error ? imageryQuery.error.message : "请检查试算所关联的影像成果"}</small></div>}
          <div className="moso-stage-legend"><span><i className="boundary" />林班边界</span><span><i className="candidate" />竹冠候选点</span><small>描边始终置顶，不遮盖影像</small></div><div className="moso-stage-caption"><Crosshair /><span>{candidates.length ? "候选点来自当前正射影像的冠层峰值检测，用于解释密度与覆盖关系；不是逐株外业坐标。" : "该历史试算只保存汇总结果，重新试算后即可在真实影像上显示竹冠候选点。"}</span></div>
        </div><div className="moso-stage-actions">{imagerySceneId ? <a href={`/v2/asset-viewer?sceneId=${encodeURIComponent(imagerySceneId)}&mode=2d&blockId=${encodeURIComponent(record.id)}`} target="_blank" rel="noreferrer"><ExternalLink />独立查看正射证据</a> : null}{pointCloudSceneId ? <a href={`/v2/asset-viewer?sceneId=${encodeURIComponent(pointCloudSceneId)}&mode=3d&engine=copc&blockId=${encodeURIComponent(record.id)}`} target="_blank" rel="noreferrer"><Layers3 />独立查看点云证据</a> : null}</div></main>
        <aside className="moso-summary-panel"><div className="moso-panel-heading"><span>试算结果</span><strong>资源汇总</strong></div><Metric label="资源株数" value={formatNumber(estimate.resourceStock.value)} unit="株" detail={`${formatNumber(estimate.resourceStock.lower)}–${formatNumber(estimate.resourceStock.upper)} 株`} /><div className="moso-summary-grid"><Metric label="林班面积" value={formatNumber(estimate.blockArea.value, 2)} unit={estimate.blockArea.unit} /><Metric label="密度" value={formatNumber(estimate.stemDensity.value, 1)} unit={estimate.stemDensity.unit} /></div><div className="moso-summary-grid"><Metric label="冠层覆盖" value={formatNumber(estimate.canopyClosure.value, 1)} unit="%" /><Metric label="地上生物量" value={formatNumber(estimate.abovegroundBiomass.value, 1)} unit="t" /></div><section className="moso-confidence"><div><span>结果置信度</span><strong>{estimate.confidence.level}</strong></div><div className="moso-confidence-track"><i style={{ width: `${Math.round(estimate.confidence.score * 100)}%` }} /></div><small>{Math.round(estimate.confidence.score * 100)}% · 科研试算</small></section><dl className="moso-evidence-list"><div><dt>影像分辨率</dt><dd>{numberValue(estimate.imageryEvidence, "nativeResolutionM") || "—"} m</dd></div><div><dt>影像覆盖率</dt><dd>{numberValue(estimate.imageryEvidence, "imageCoveragePct") || "—"}%</dd></div><div><dt>候选点留样</dt><dd>{formatNumber(candidates.length)} 个</dd></div><div><dt>估算时间</dt><dd>{formatDateTime(estimate.estimatedAt)}</dd></div></dl></aside>
      </div><footer className="moso-sandbox-footer"><span>{estimate.method?.name || "RGB 多尺度冠层分割与资源量试算"}</span><p>{estimate.disclaimer}</p></footer>
    </>}</QueryState>
  </div>;
}

function ProcessStep({ icon: Icon, title, detail }: { icon: typeof Database; title: string; detail: string }) { return <div className="moso-process-step"><div><Icon /><Check className="moso-step-check" /></div><span><strong>{title}</strong><small>{detail}</small></span></div>; }
function Metric({ label, value, unit, detail = "" }: { label: string; value: string; unit: string; detail?: string }) { return <section className="moso-summary-metric"><span>{label}</span><div><strong>{value}</strong><small>{unit}</small></div>{detail && <p>{detail}</p>}</section>; }
