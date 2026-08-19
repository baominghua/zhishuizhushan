import { useQuery } from "@tanstack/react-query";
import { ChartNoAxesCombined, Download, Layers3, ScanSearch, Sprout, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { api } from "../api/client";
import { QueryState } from "../components/QueryState";

const groups = [
  ["bambooSpecies", "竹种"], ["ageGroup", "龄级"], ["slope", "坡度"], ["town", "乡镇"],
] as const;

export function ResourceIntelligencePage() {
  const [groupBy, setGroupBy] = useState<(typeof groups)[number][0]>("bambooSpecies");
  const statistics = useQuery({ queryKey: ["resource-statistics", groupBy], queryFn: () => api.resourceStatistics({ groupBy }) });
  const changes = useQuery({ queryKey: ["resource-change-jobs"], queryFn: () => api.resourceChangeJobs() });
  const growth = useQuery({ queryKey: ["growth-anomalies"], queryFn: () => api.growthObservations("", true) });
  const maxArea = Math.max(...(statistics.data?.items.map((item) => item.areaMu) ?? [1]), 1);
  const pending = changes.data?.items.filter((item) => item.status === "pending-review").length ?? 0;

  return <div className="standard-page ledger-page roadmap-page">
    <section className="page-heading ledger-heading"><div><span className="eyebrow">资源一张图 / RES-01 · OPS-01</span><h1>资源专题与长势监测</h1><p>从正式小班台账聚合竹种、龄级和坡度统计；变化图斑只有人工核查通过后才能更新空间版本。</p></div><div className="heading-actions"><a className="button secondary" href={`/api/v2/intelligence/resources/statistics.xlsx?groupBy=${groupBy}`}><Download />Excel</a><a className="button secondary" href={`/api/v2/intelligence/resources/statistics.pdf?groupBy=${groupBy}`}><Download />PDF</a></div></section>
    <section className="metric-strip roadmap-metrics"><Metric icon={Layers3} label="统计小班" value={statistics.data?.total ?? 0} unit="个" /><Metric icon={ChartNoAxesCombined} label="统计面积" value={format(statistics.data?.totalAreaMu)} unit="亩" /><Metric icon={ScanSearch} label="待核查变化" value={pending} unit="项" warning={pending > 0} /><Metric icon={Sprout} label="长势异常" value={growth.data?.total ?? 0} unit="个" warning={Boolean(growth.data?.total)} /></section>
    <section className="roadmap-command-panel"><span className="command-label">组合分析维度</span>{groups.map(([key, label]) => <button className={`roadmap-tab ${groupBy === key ? "active" : ""}`} key={key} type="button" onClick={() => setGroupBy(key)}>{label}</button>)}<small>数据源：小班台账 · {statistics.data?.asOf ? new Date(statistics.data.asOf).toLocaleString("zh-CN") : "加载中"}</small></section>
    <section className="roadmap-grid two-columns">
      <article className="roadmap-card span-two"><header><div><span>专题统计</span><h2>{groups.find(([key]) => key === groupBy)?.[1]}分布</h2></div><small>{statistics.data?.items.length ?? 0} 个分组</small></header><QueryState loading={statistics.isLoading} error={statistics.error}><div className="resource-bars">{statistics.data?.items.map((item) => <div key={item.name}><span><strong>{item.name}</strong><small>{item.count} 个小班</small></span><i><b style={{ width: `${Math.max(2, item.areaMu / maxArea * 100)}%` }} /></i><em>{format(item.areaMu)} 亩</em></div>)}{!statistics.data?.items.length && <p className="roadmap-empty">当前筛选范围暂无小班统计数据</p>}</div></QueryState></article>
      <article className="roadmap-card"><header><div><span>季度影像变化</span><h2>人工核查队列</h2></div><ScanSearch /></header><div className="roadmap-list">{changes.data?.items.slice(0, 8).map((item) => <div key={item.id}><span><strong>{String(item.subcompartmentCode || item.id)}</strong><small>{String(item.changeType || "变化")} · 置信度 {format(Number(item.confidence || 0) * 100)}%</small></span><Status value={String(item.status || "")} /></div>)}{!changes.data?.items.length && <p className="roadmap-empty">尚无变化检测任务</p>}</div><footer className="roadmap-note"><TriangleAlert />系统不会直接覆盖小班边界；“待核查 → 已通过 → 应用版本”三步均留痕。</footer></article>
      <article className="roadmap-card"><header><div><span>月度 NDVI / LAI</span><h2>异常小班</h2></div><Sprout /></header><div className="roadmap-list">{growth.data?.items.slice(0, 8).map((item) => <div key={item.id}><span><strong>{String(item.subcompartmentCode || item.id)}</strong><small>{String(item.observedOn || "")} · {String(item.anomalyReason || "待核查")}</small></span><b>NDVI {item.ndvi == null ? "—" : format(Number(item.ndvi))}</b></div>)}{!growth.data?.items.length && <p className="roadmap-empty">当前没有长势异常记录</p>}</div></article>
    </section>
  </div>;
}

function Metric({ icon: Icon, label, value, unit, warning = false }: { icon: typeof Layers3; label: string; value: string | number; unit: string; warning?: boolean }) { return <div className={`metric ${warning ? "warning" : ""}`}><Icon /><span><small>{label}</small><strong>{value}</strong><em>{unit}</em></span></div>; }
function Status({ value }: { value: string }) { const config: Record<string, [string, string]> = { "pending-review": ["待核查", "warning"], accepted: ["已通过", "success"], rejected: ["已驳回", "danger"], applied: ["已更新版本", "success"] }; const current = config[value] || [value, "neutral"]; return <span className={`status-badge ${current[1]}`}>{current[0]}</span>; }
function format(value: number | undefined) { return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 2 }); }
