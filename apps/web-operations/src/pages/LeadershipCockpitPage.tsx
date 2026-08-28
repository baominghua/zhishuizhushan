import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Activity, Building2, CircleDollarSign, Images, Leaf, MonitorUp, Plane, RefreshCw, ShieldAlert, Trees, UsersRound, WalletCards, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { CockpitMetric, CockpitRankingItem, CockpitTopic, ImageryInventoryResponse } from "../api/types";
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
  const [tab, setTab] = useState<"overview" | "emergency" | "harvest" | "drone" | "cost" | "imagery" | "carbon">("overview");
  const query = useQuery({ queryKey: ["leadership-cockpit"], queryFn: api.leadershipCockpit, refetchInterval: 60_000 });
  const topicsQuery = useQuery({ queryKey: ["leadership-cockpit-topics"], queryFn: api.cockpitTopics, refetchInterval: 60_000 });
  const imageryQuery = useQuery({ queryKey: ["leadership-cockpit-imagery"], queryFn: api.imageryInventory, enabled: tab === "imagery", staleTime: 60_000 });
  const data = query.data;
  const metrics = tab === "overview" ? overviewMetrics : carbonMetrics;
  const selectedTopic = topicsQuery.data?.topics.find((topic) => topic.key === tab);
  const focusMetric = (tab === "overview" ? data?.overview.forestBlockCount : data?.carbon.projectCount) as CockpitMetric | undefined;
  return <div className="cockpit-page">
    <header className="cockpit-hero">
      <div><span className="cockpit-kicker"><i />南平市智慧竹山 · 实时决策中枢</span><h1>领导驾驶舱</h1><p>资源、经营、安全与碳汇数据统一态势感知</p></div>
      <div className="cockpit-hero-actions"><Link className="cockpit-display-link" to="/display"><MonitorUp aria-hidden="true" />大屏模式</Link><span className="cockpit-live"><i />数据在线</span><time>{data ? new Date(data.asOf).toLocaleString("zh-CN", { hour12: false }) : "同步中"}</time><button type="button" title="刷新数据" aria-label="刷新数据" onClick={() => { query.refetch(); topicsQuery.refetch(); }}><RefreshCw aria-hidden="true" /></button></div>
    </header>
    <nav className="cockpit-tabs cockpit-topic-tabs" aria-label="驾驶舱专题"><button className={tab === "overview" ? "active" : ""} type="button" onClick={() => setTab("overview")}>综合态势</button><button className={tab === "emergency" ? "active" : ""} type="button" onClick={() => setTab("emergency")}>灾害应急</button><button className={tab === "harvest" ? "active" : ""} type="button" onClick={() => setTab("harvest")}>采伐监管</button><button className={tab === "drone" ? "active" : ""} type="button" onClick={() => setTab("drone")}>无人机运营</button><button className={tab === "cost" ? "active" : ""} type="button" onClick={() => setTab("cost")}>成本效益</button><button className={tab === "imagery" ? "active" : ""} type="button" onClick={() => setTab("imagery")}>影像资源</button><button className={tab === "carbon" ? "active" : ""} type="button" onClick={() => setTab("carbon")}>碳汇专题</button></nav>
    {tab === "imagery" ? <QueryState loading={imageryQuery.isLoading} error={imageryQuery.error}>{imageryQuery.data && <ImageryInventoryScene inventory={imageryQuery.data} />}</QueryState> : tab !== "overview" && tab !== "carbon" ? <QueryState loading={topicsQuery.isLoading} error={topicsQuery.error}>{selectedTopic && <TopicScene topic={selectedTopic} policy={topicsQuery.data?.metricPolicy || ""} />}</QueryState> : <QueryState loading={query.isLoading} error={query.error}>{data && <div key={tab} className="cockpit-scene">
      <section className="cockpit-kpis">{metrics.map(([key, label, icon], index) => <Metric key={key} label={label} metric={(tab === "overview" ? data.overview[key] : data.carbon[key]) as CockpitMetric} icon={icon} index={index} />)}</section>
      <section className="cockpit-main-grid">
        <div className="cockpit-focus"><div className="focus-rings"><span /><span /><span /><Trees aria-hidden="true" /></div><small>{tab === "overview" ? "林班空间底座" : "碳汇核算底座"}</small><AnimatedNumber value={Number(focusMetric?.value || 0)} /><em>{tab === "overview" ? "个正式林班" : "个碳汇项目"}</em><p>{tab === "overview" ? "空间边界、资源属性与经营主体持续汇聚" : "核算边界、方法学、核证结果与收益统一管理"}</p></div>
        {tab === "overview" ? <Operations data={data.operations} availability={data.availability} /> : <CarbonRanking items={data.carbon.districtRanking as CockpitRankingItem[]} />}
      </section>
      <footer className="cockpit-footer"><span>当前数据范围：{data.scope.areas.includes("*") ? "全市" : data.scope.areas.join("、") || "未配置"}</span><span>数据源：正式业务台账</span><Link to="/carbon/estimates">进入碳汇项目台账</Link></footer>
    </div>}</QueryState>}
  </div>;
}

function ImageryInventoryScene({ inventory }: { inventory: ImageryInventoryResponse }) {
  const labels: Record<string, string> = { orthophoto: "正射影像", dsm: "DSM 地表", dtm: "DTM 地形", pointcloud: "彩色点云", oblique3d: "实景三维", "flight-photos": "航飞原片" };
  const resources = inventory.bambooResources;
  return <div className="cockpit-scene cockpit-topic-scene">
    <section className="cockpit-topic-heading"><span><Images /><small>空间资产盘点</small><h2>影像资源</h2></span><Link to="/drone/imagery-assets">进入影像台账</Link></section>
    <section className="cockpit-kpis"><article className="cockpit-metric"><div><Images /><span>成果总数</span></div><strong>{inventory.total.toLocaleString("zh-CN")}</strong><small>正式影像与点云资产</small></article><article className="cockpit-metric"><div><Activity /><span>资料类型</span></div><strong>{inventory.typeCount}</strong><small>已入库成果分类</small></article><article className="cockpit-metric"><div><Trees /><span>覆盖面积</span></div><strong>{Math.round(inventory.totalAreaMu).toLocaleString("zh-CN")}</strong><small>亩 · 已完成范围分析</small></article><article className="cockpit-metric"><div><WalletCards /><span>数据容量</span></div><strong>{formatStorage(inventory.totalSizeBytes)}</strong><small>当前资产原始容量</small></article></section>
    <section className="cockpit-imagery-inventory">{inventory.items.map((item) => <article key={item.assetType}><span><strong>{labels[item.assetType] || item.assetType}</strong><small>{item.count} 个成果</small></span><b>{Math.round(item.areaMu).toLocaleString("zh-CN")} 亩</b><em>{formatStorage(item.sizeBytes)}</em></article>)}</section>
    <section className="cockpit-bamboo-dashboard">
      <header><span><Trees /><small>林班资源盘点</small><h2>竹材资源统计</h2></span><Link to="/resources/intelligence">进入资源专题分析</Link></header>
      <div className="cockpit-bamboo-metrics">
        <BambooMetric label="正式调查资源株数" value={resources.formal.stock} unit={resources.formal.unit} detail={resources.formal.available ? `${resources.formal.blockCount} 个林班 · ${resources.formal.source}` : "暂无正式调查数据"} tone="formal" />
        <BambooMetric label="AI 估算毛竹株数" value={resources.estimated.stock} unit={resources.estimated.unit} detail={resources.estimated.available ? `${resources.estimated.blockCount} 个已试算林班` : "暂无 AI 试算数据"} tone="estimated" />
        <BambooMetric label="AI 估算地上生物量" value={resources.estimated.biomassTons} unit="t" detail={resources.estimated.available ? resources.estimated.source : "暂无 AI 试算数据"} tone="estimated" digits={1} />
        <BambooMetric label="AI 已试算林班" value={resources.estimated.available ? resources.estimated.blockCount : null} unit="个" detail={resources.estimated.estimatedAt ? `最近试算 ${new Date(resources.estimated.estimatedAt).toLocaleString("zh-CN", { hour12: false })}` : "尚未形成估算结果"} tone="estimated" />
      </div>
      <p>{resources.policy}</p>
    </section>
    <footer className="cockpit-footer"><span>面积单位：{inventory.areaUnit || "亩"} · {inventory.areaMethod || "按有效覆盖范围汇总"}</span><span>数据源：影像与点云成果台账 · {new Date(inventory.asOf).toLocaleString("zh-CN", { hour12: false })}</span></footer>
  </div>;
}

function BambooMetric({ label, value, unit, detail, tone, digits = 0 }: { label: string; value: number | null; unit: string; detail: string; tone: "formal" | "estimated"; digits?: number }) {
  return <article className={tone}><span>{label}</span>{value === null ? <strong className="unavailable">暂无</strong> : <strong>{value.toLocaleString("zh-CN", { maximumFractionDigits: digits })}<small>{unit}</small></strong>}<p>{detail}</p></article>;
}

function formatStorage(bytes: number) { if (bytes >= 1024 ** 4) return `${(bytes / 1024 ** 4).toFixed(2)} TB`; if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`; return `${(bytes / 1024 ** 2).toFixed(1)} MB`; }

function TopicScene({ topic, policy }: { topic: CockpitTopic; policy: string }) { const icon = topic.key === "emergency" ? ShieldAlert : topic.key === "harvest" ? Trees : topic.key === "drone" ? Plane : WalletCards; const Icon = icon; return <div key={topic.key} className="cockpit-scene cockpit-topic-scene"><section className="cockpit-topic-heading"><span><Icon /><small>专题驾驶舱</small><h2>{topic.label}</h2></span><time>更新时间 {new Date(topic.asOf).toLocaleString("zh-CN", { hour12: false })}</time></section><section className="cockpit-kpis">{topic.metrics.map((metric, index) => <article className="cockpit-metric" key={metric.key} style={{ animationDelay: `${index * 70}ms` }}><div><Activity /><span>{metric.label}</span></div>{metric.available ? <><AnimatedNumber value={Number(metric.value || 0)} /><small>{metric.unit} · {metric.source}</small></> : <><strong className="unavailable">未接入</strong><small>{metric.source}</small></>}<p>{metric.definition}</p><a href={metric.drilldown}>查看明细</a></article>)}</section>{topic.featureGates && <section className="cockpit-feature-gate"><ShieldAlert /><span><strong>视频会商：{topic.featureGates.videoConference ? "已启用" : "待协议接通"}</strong><small>{String(topic.featureGates.reason || "")}</small></span></section>}<footer className="cockpit-footer"><span>{policy}</span><span>行政层级下钻与明细入口已启用</span></footer></div>; }

function AnimatedNumber({ value }: { value: number }) { const [shown, setShown] = useState(0); useEffect(() => { const start = performance.now(); const frame = (now: number) => { const p = Math.min((now - start) / 900, 1); setShown(value * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(frame); }; const id = requestAnimationFrame(frame); return () => cancelAnimationFrame(id); }, [value]); return <strong>{Math.round(shown).toLocaleString("zh-CN")}</strong>; }
function Metric({ label, metric, icon: Icon, index }: { label: string; metric?: CockpitMetric; icon: LucideIcon; index: number }) { return <article className="cockpit-metric" style={{ animationDelay: `${index * 70}ms` }}><div><Icon aria-hidden="true" /><span>{label}</span></div>{metric?.available ? <><AnimatedNumber value={Number(metric.value || 0)} /><small>{metric.unit} · {metric.source}</small></> : <><strong className="unavailable">未接入</strong><small>等待正式数据源</small></>}</article>; }
function Operations({ data, availability }: { data: Record<string, CockpitMetric>; availability: Record<string, boolean> }) { return <div className="cockpit-side"><h2>运行态势</h2><div className="operation-cards"><Status icon={ShieldAlert} label="安全事件" metric={data.openSafetyEvents} tone="amber" /><Status icon={Plane} label="无人机任务" metric={data.activeDroneMissions} tone="cyan" /></div><h3>数据源健康度</h3><div className="source-grid">{Object.entries(availability).map(([key, ready]) => <span className={ready ? "ready" : "pending"} key={key}><i />{sourceLabel(key)}</span>)}</div></div>; }
function Status({ icon: Icon, label, metric, tone }: { icon: LucideIcon; label: string; metric: CockpitMetric; tone: string }) { return <div className={`operation-card ${tone}`}><Icon /><span>{label}</span><strong>{metric.available ? `${metric.value || 0}${metric.unit}` : "未接入"}</strong><small>{metric.source}</small></div>; }
function CarbonRanking({ items = [] }: { items: CockpitRankingItem[] }) { const max = Math.max(...items.map(item => item.annualSequestration), 1); return <div className="cockpit-side"><h2>区划碳汇排名</h2>{items.length ? <div className="ranking-list">{items.slice(0, 6).map((item, index) => <div key={item.name}><b>{String(index + 1).padStart(2, "0")}</b><span><strong>{item.name}</strong><i style={{ width: `${Math.max(item.annualSequestration / max * 100, 4)}%` }} /></span><em>{item.annualSequestration.toLocaleString("zh-CN")} tCO2e</em></div>)}</div> : <div className="cockpit-empty"><Leaf /><strong>暂无区划汇总</strong><p>碳汇项目关联正式林班后自动形成排名。</p></div>}</div>; }
function sourceLabel(key: string) { return ({ carbon: "碳汇", enterprises: "竹企", farmers: "竹农", yieldForecasts: "产量", harvestPlans: "采挖", incomeEstimates: "收益", carbonTrades: "交易", safetyEvents: "安全", droneMissions: "无人机" } as Record<string, string>)[key] || key; }
