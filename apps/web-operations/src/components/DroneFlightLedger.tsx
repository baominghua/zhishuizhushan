import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, Eye, FileClock, Route, Search } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { api } from "../api/client";
import type { DroneFlightRecord } from "../api/types";
import { LedgerPagination } from "./LedgerPagination";
import { QueryState } from "./QueryState";
import { SidePanel } from "./SidePanel";

const PAGE_SIZE = 30;

export function DroneFlightLedger() {
  const [q, setQ] = useState("");
  const [origin, setOrigin] = useState("");
  const [completeness, setCompleteness] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<DroneFlightRecord | null>(null);
  const deferredQ = useDeferredValue(q);
  const ledger = useQuery({
    queryKey: ["v2-drone-flights", deferredQ, origin, completeness, offset],
    queryFn: () => api.droneFlights({ q: deferredQ, origin, completeness, limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const items = ledger.data?.items ?? [];
  return <>
    <section className="domain-summary-strip">
      <FlightSummary label="飞行记录" value={ledger.data?.total ?? 0} detail="真实起飞或轨迹导入" />
      <FlightSummary label="轨迹导入" value={items.filter((item) => item.origin === "trajectory").length} detail="DJI Terra POS / SBET" />
      <FlightSummary label="资料待补" value={items.filter((item) => item.completeness === "incomplete").length} detail="不虚构缺失字段" tone="warning" />
      <FlightSummary label="成果已关联" value={items.filter((item) => item.resultAttachmentCount > 0 || item.sourceSceneIds.length > 0).length} detail="附件或影像成果" tone="active" />
    </section>
    <section className="ledger-shell">
      <div className="ledger-toolbar domain-ledger-toolbar">
        <label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索航次、无人机、飞手、航线或林班" /></label>
        <label className="compact-filter"><span>记录来源</span><select value={origin} onChange={(event) => { setOrigin(event.target.value); setOffset(0); }}><option value="">全部来源</option><option value="mission">任务执行</option><option value="trajectory">轨迹导入</option></select></label>
        <label className="compact-filter"><span>资料完整性</span><select value={completeness} onChange={(event) => { setCompleteness(event.target.value); setOffset(0); }}><option value="">全部</option><option value="complete">资料完整</option><option value="incomplete">资料待补</option></select></label>
        <a className="button secondary" href="/api/v2/drone/flights-export.csv"><Download aria-hidden="true" />导出飞行台账</a>
      </div>
      <QueryState loading={ledger.isLoading} error={ledger.error}><div className="table-scroll"><table className="ledger-table drone-ledger-table"><thead><tr><th>飞行记录</th><th>无人机与飞手</th><th>实际飞行</th><th>轨迹与成果</th><th>资料完整性</th><th className="action-column">操作</th></tr></thead><tbody>
        {items.map((record) => <tr key={record.id} onClick={() => setSelected(record)}><td><strong>{record.title}</strong><small>{record.missionNo} · {record.origin === "trajectory" ? "轨迹自动导入" : "任务执行"}</small></td><td><strong>{record.deviceName || record.deviceCode || "无人机待补"}</strong><small>{record.pilotName || "飞手待补"}{record.routeName ? ` · ${record.routeName}` : ""}</small></td><td><strong>{record.actualStartAt ? formatDateTime(record.actualStartAt) : "起飞时间待补"}</strong><small>{metric(record.durationMinutes, "分钟")} · {metric(record.distanceKm, "km")} · {metric(record.coverageAreaMu, "亩")}</small></td><td><strong>{record.trajectoryFormats.join(" / ") || "任务记录"}</strong><small>{record.trajectoryFileCount} 个轨迹文件 · {record.resultAttachmentCount || record.sourceSceneIds.length} 项成果</small></td><td>{record.completeness === "complete" ? <span className="status-badge completed"><i />资料完整</span> : <span className="status-badge warning"><i />待补 {record.missingFields.length} 项</span>}</td><td className="action-column"><button className="icon-button" type="button" aria-label="查看飞行记录" title="查看" onClick={(event) => { event.stopPropagation(); setSelected(record); }}><Eye aria-hidden="true" /></button></td></tr>)}
        {!ledger.isLoading && !items.length && <tr className="empty-row"><td colSpan={6}><div className="table-empty"><FileClock aria-hidden="true" /><strong>当前没有飞行记录</strong><p>任务实际起飞或已确认成果含 DJI Terra 轨迹后，会自动进入本台账。</p></div></td></tr>}
      </tbody></table></div></QueryState>
      <LedgerPagination total={ledger.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
    </section>
    <SidePanel wide open={Boolean(selected)} eyebrow="无人机运营 / Flight" title={selected?.title || "飞行记录"} onClose={() => setSelected(null)}>{selected && <FlightDetail record={selected} />}</SidePanel>
  </>;
}

function FlightDetail({ record }: { record: DroneFlightRecord }) {
  return <div className="domain-detail">
    <section className={`domain-action-card ${record.completeness === "complete" ? "complete" : ""}`}>{record.completeness === "complete" ? <CheckCircle2 aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}<div><strong>{record.completeness === "complete" ? "飞行资料完整" : "飞行资料仍需补录"}</strong><small>{record.missingFields.length ? record.missingFields.map(missingFieldLabel).join("、") : "关键设备、人员、时间、航程与原始记录均已登记。"}</small></div></section>
    <section className="detail-group"><h3>航次信息</h3><dl><Fact label="任务编号" value={record.missionNo} /><Fact label="记录来源" value={record.origin === "trajectory" ? "DJI Terra 轨迹自动导入" : "平台任务执行"} /><Fact label="无人机" value={[record.deviceName, record.deviceCode].filter(Boolean).join(" · ")} /><Fact label="飞手" value={record.pilotName} /><Fact label="航线" value={record.routeName} /><Fact label="实际起飞" value={formatDateTime(record.actualStartAt)} /><Fact label="实际结束" value={formatDateTime(record.actualEndAt)} /><Fact label="飞行时长" value={metric(record.durationMinutes, "分钟")} /><Fact label="飞行航程" value={metric(record.distanceKm, "km")} /><Fact label="覆盖面积" value={metric(record.coverageAreaMu, "亩")} /></dl></section>
    <section className="detail-group"><h3>轨迹与成果</h3><dl><Fact label="轨迹格式" value={record.trajectoryFormats.join(" / ")} /><Fact label="轨迹文件" value={`${record.trajectoryFileCount} 个 · ${formatBytes(record.trajectorySizeBytes)}`} /><Fact label="关联成果" value={`${record.resultAttachmentCount || record.sourceSceneIds.length} 项`} /><Fact label="轨迹目录" value={record.trajectoryPath} /></dl><div className="relation-chips read-only">{record.blocks.map((item) => <span key={item.code}><Route aria-hidden="true" /><strong>{item.code}</strong><small>关联林班</small></span>)}</div></section>
  </div>;
}

function FlightSummary({ label, value, detail, tone = "" }: { label: string; value: number; detail: string; tone?: string }) { return <div className={tone}><small>{label}</small><strong>{value}</strong><em>{detail}</em></div>; }
function Fact({ label, value }: { label: string; value?: string | null }) { return <div><dt>{label}</dt><dd>{value || "暂无"}</dd></div>; }
function metric(value: number | null, unit: string) { return value === null || value === undefined ? `暂无${unit}` : `${value.toLocaleString("zh-CN")} ${unit}`; }
function formatDateTime(value?: string | null) { if (!value) return "暂无"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN"); }
function formatBytes(value: number) { if (!value) return "0 B"; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB`; }
function missingFieldLabel(fieldName: string) { return ({ droneDevice: "无人机型号与序列号", pilot: "飞手", plannedWindow: "计划时间", actualWindow: "起降时间", flightStatistics: "航程/时长/电池统计", originalFlightLog: "DJI 原始飞行记录" } as Record<string, string>)[fieldName] || fieldName; }
