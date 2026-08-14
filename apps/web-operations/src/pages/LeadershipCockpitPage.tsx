import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Activity, Building2, CircleDollarSign, Leaf, MonitorUp, Plane, RefreshCw, ShieldAlert, Trees, UsersRound, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { CockpitMetric, CockpitRankingItem } from "../api/types";
import { QueryState } from "../components/QueryState";

const overviewMetrics: Array<[string, string, LucideIcon]> = [
  ["forestAreaMu", "竹林资源面积", Trees], ["annualYieldTons", "年度预测产量", Activity],
  ["annualOutputValue", "年度预计产值", CircleDollarSign], ["enterpriseCount", "竹企数量", Building2],
  ["practitionerCount", "竹农主体", UsersRound], ["annualSequestration", "年度碳汇量", Leaf],
];
const carbonMetrics: Array<[string, string, LucideIcon]> = [
  ["totalCarbonStock", "碳储量", Trees], ["annualSequestration", "年度碳汇量", Leaf],
  ["projectCount", "碳汇项目", Activity], ["ccerRegisteredAmount", "CCER 核证量", ShieldAlert],
  ["tradeVolume", "交易量", Activity], ["tradeAmount", "交易金额", CircleDollarSign],
];

export function LeadershipCockpitPage() {
  const [tab, setTab] = useState<"overview" | "carbon">("overview");
  const query = useQuery({ queryKey: ["leadership-cockpit"], queryFn: api.leadershipCockpit, refetchInterval: 60_000 });
  const data = query.data;
  const metrics = tab === "overview" ? overviewMetrics : carbonMetrics;
  const focusMetric = (tab === "overview" ? data?.overview.forestBlockCount : data?.carbon.projectCount) as CockpitMetric | undefined;
  return <div className="cockpit-page">
    <header className="cockpit-hero">
      <div><span className="cockpit-kicker"><i />南平市智慧竹山 · 实时决策中枢</span><h1>领导驾驶舱</h1><p>资源、经营、安全与碳汇数据统一态势感知</p></div>
      <div className="cockpit-hero-actions"><Link className="cockpit-display-link" to="/display"><MonitorUp aria-hidden="true" />大屏模式</Link><span className="cockpit-live"><i />数据在线</span><time>{data ? new Date(data.asOf).toLocaleString("zh-CN", { hour12: false }) : "同步中"}</time><button type="button" title="刷新数据" aria-label="刷新数据" onClick={() => query.refetch()}><RefreshCw aria-hidden="true" /></button></div>
    </header>
    <nav className="cockpit-tabs" aria-label="驾驶舱专题"><button className={tab === "overview" ? "active" : ""} type="button" onClick={() => setTab("overview")}>综合态势</button><button className={tab === "carbon" ? "active" : ""} type="button" onClick={() => setTab("carbon")}>碳汇专题</button><span className={tab} /></nav>
    <QueryState loading={query.isLoading} error={query.error}>{data && <div key={tab} className="cockpit-scene">
      <section className="cockpit-kpis">{metrics.map(([key, label, icon], index) => <Metric key={key} label={label} metric={(tab === "overview" ? data.overview[key] : data.carbon[key]) as CockpitMetric} icon={icon} index={index} />)}</section>
      <section className="cockpit-main-grid">
        <div className="cockpit-focus"><div className="focus-rings"><span /><span /><span /><Trees aria-hidden="true" /></div><small>{tab === "overview" ? "林班空间底座" : "碳汇核算底座"}</small><AnimatedNumber value={Number(focusMetric?.value || 0)} /><em>{tab === "overview" ? "个正式林班" : "个碳汇项目"}</em><p>{tab === "overview" ? "空间边界、资源属性与经营主体持续汇聚" : "核算边界、方法学、核证结果与收益统一管理"}</p></div>
        {tab === "overview" ? <Operations data={data.operations} availability={data.availability} /> : <CarbonRanking items={data.carbon.districtRanking as CockpitRankingItem[]} />}
      </section>
      <footer className="cockpit-footer"><span>当前数据范围：{data.scope.areas.includes("*") ? "全市" : data.scope.areas.join("、") || "未配置"}</span><span>数据源：正式业务台账</span><Link to="/carbon/estimates">进入碳汇项目台账</Link></footer>
    </div>}</QueryState>
  </div>;
}

function AnimatedNumber({ value }: { value: number }) { const [shown, setShown] = useState(0); useEffect(() => { const start = performance.now(); const frame = (now: number) => { const p = Math.min((now - start) / 900, 1); setShown(value * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(frame); }; const id = requestAnimationFrame(frame); return () => cancelAnimationFrame(id); }, [value]); return <strong>{Math.round(shown).toLocaleString("zh-CN")}</strong>; }
function Metric({ label, metric, icon: Icon, index }: { label: string; metric?: CockpitMetric; icon: LucideIcon; index: number }) { return <article className="cockpit-metric" style={{ animationDelay: `${index * 70}ms` }}><div><Icon aria-hidden="true" /><span>{label}</span></div>{metric?.available ? <><AnimatedNumber value={Number(metric.value || 0)} /><small>{metric.unit} · {metric.source}</small></> : <><strong className="unavailable">未接入</strong><small>等待正式数据源</small></>}</article>; }
function Operations({ data, availability }: { data: Record<string, CockpitMetric>; availability: Record<string, boolean> }) { return <div className="cockpit-side"><h2>运行态势</h2><div className="operation-cards"><Status icon={ShieldAlert} label="安全事件" metric={data.openSafetyEvents} tone="amber" /><Status icon={Plane} label="无人机任务" metric={data.activeDroneMissions} tone="cyan" /></div><h3>数据源健康度</h3><div className="source-grid">{Object.entries(availability).map(([key, ready]) => <span className={ready ? "ready" : "pending"} key={key}><i />{sourceLabel(key)}</span>)}</div></div>; }
function Status({ icon: Icon, label, metric, tone }: { icon: LucideIcon; label: string; metric: CockpitMetric; tone: string }) { return <div className={`operation-card ${tone}`}><Icon /><span>{label}</span><strong>{metric.available ? `${metric.value || 0}${metric.unit}` : "未接入"}</strong><small>{metric.source}</small></div>; }
function CarbonRanking({ items = [] }: { items: CockpitRankingItem[] }) { const max = Math.max(...items.map(item => item.annualSequestration), 1); return <div className="cockpit-side"><h2>区划碳汇排名</h2>{items.length ? <div className="ranking-list">{items.slice(0, 6).map((item, index) => <div key={item.name}><b>{String(index + 1).padStart(2, "0")}</b><span><strong>{item.name}</strong><i style={{ width: `${Math.max(item.annualSequestration / max * 100, 4)}%` }} /></span><em>{item.annualSequestration.toLocaleString("zh-CN")} tCO2e</em></div>)}</div> : <div className="cockpit-empty"><Leaf /><strong>暂无区划汇总</strong><p>碳汇项目关联正式林班后自动形成排名。</p></div>}</div>; }
function sourceLabel(key: string) { return ({ carbon: "碳汇", enterprises: "竹企", farmers: "竹农", yieldForecasts: "产量", harvestPlans: "采挖", incomeEstimates: "收益", carbonTrades: "交易", safetyEvents: "安全", droneMissions: "无人机" } as Record<string, string>)[key] || key; }
