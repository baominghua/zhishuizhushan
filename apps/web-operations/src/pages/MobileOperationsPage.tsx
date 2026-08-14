import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, Eye, FileImage, MapPin, RefreshCw, Search, Smartphone, WifiOff } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useDeferredValue, useMemo, useState } from "react";

import { api } from "../api/client";
import type { MobileEvidenceRecord, MobileSyncOperationRecord, MobileTrackRecord } from "../api/types";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";

const PAGE_SIZE = 30;
type Tab = "sync" | "tracks" | "evidence";

export function MobileOperationsPage() {
  const [tab, setTab] = useState<Tab>("sync");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<MobileSyncOperationRecord | MobileTrackRecord | MobileEvidenceRecord | null>(null);
  const queryClient = useQueryClient();
  const deferredQ = useDeferredValue(q);
  const sync = useQuery({ queryKey: ["v2-mobile-sync", deferredQ, status, offset], queryFn: () => api.mobileSyncOperations({ q: deferredQ, status, limit: PAGE_SIZE, offset }), enabled: tab === "sync", placeholderData: (previous) => previous });
  const tracks = useQuery({ queryKey: ["v2-mobile-tracks", deferredQ, status, offset], queryFn: () => api.mobileTracks({ q: deferredQ, status, limit: PAGE_SIZE, offset }), enabled: tab === "tracks", placeholderData: (previous) => previous });
  const evidence = useQuery({ queryKey: ["v2-mobile-evidence", deferredQ, offset], queryFn: () => api.mobileEvidence({ q: deferredQ, limit: PAGE_SIZE, offset }), enabled: tab === "evidence", placeholderData: (previous) => previous });
  const active = tab === "sync" ? sync : tab === "tracks" ? tracks : evidence;
  const syncItems = sync.data?.items ?? [];
  const metrics = useMemo(() => ({ total: sync.data?.total ?? 0, completed: syncItems.filter((item) => item.status === "completed").length, conflicts: syncItems.filter((item) => item.status === "conflict").length, failed: syncItems.filter((item) => item.status === "failed").length }), [sync.data?.total, syncItems]);
  const switchTab = (next: Tab) => { setTab(next); setQ(""); setStatus(""); setOffset(0); setSelected(null); };
  const resolveConflict = useMutation({
    mutationFn: ({ id, strategy, note }: { id: string; strategy: "retry" | "discard"; note: string }) => api.resolveMobileSyncConflict(id, strategy, note),
    onSuccess: () => { setSelected(null); queryClient.invalidateQueries({ queryKey: ["v2-mobile-sync"] }); },
  });

  return <div className="standard-page ledger-page mobile-operations-page">
    <section className="page-heading ledger-heading"><div><span className="eyebrow">现场作业 / 弱网协同</span><h1>现场同步台账</h1><p>集中查看离线操作、定位轨迹和音视频证据；客户端操作号保证弱网重试不会重复入账。</p></div><div className="heading-actions"><Link className="button primary" to="/field/mobile"><Smartphone aria-hidden="true" />进入现场端</Link><a className="button secondary" href={`/api/v2/mobile/operations-export.csv?${new URLSearchParams({ q: deferredQ, status }).toString()}`}><Download aria-hidden="true" />导出同步记录</a><button className="button secondary" type="button" onClick={() => active.refetch()}><RefreshCw aria-hidden="true" />刷新</button></div></section>
    <section className="domain-summary-strip mobile-summary-strip"><Summary label="同步操作" value={metrics.total} detail="服务端留痕总数" /><Summary label="本页已完成" value={metrics.completed} detail="幂等写入成功" tone="active" /><Summary label="版本冲突" value={metrics.conflicts} detail="需人工确认后重提" tone="warning" /><Summary label="同步失败" value={metrics.failed} detail="保留错误码可追溯" tone="danger" /></section>
    <section className="ledger-shell"><div className="domain-tabs" role="tablist" aria-label="现场同步数据类型"><button className={tab === "sync" ? "active" : ""} type="button" onClick={() => switchTab("sync")}><Smartphone aria-hidden="true" />同步记录</button><button className={tab === "tracks" ? "active" : ""} type="button" onClick={() => switchTab("tracks")}><MapPin aria-hidden="true" />轨迹记录</button><button className={tab === "evidence" ? "active" : ""} type="button" onClick={() => switchTab("evidence")}><FileImage aria-hidden="true" />现场证据</button></div>
      <div className="ledger-toolbar domain-ledger-toolbar"><label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder={tab === "sync" ? "搜索客户端操作号、业务记录或动作" : tab === "tracks" ? "搜索轨迹号或任务 ID" : "搜索证据编号、文件名或任务 ID"} /></label>{tab !== "evidence" && <label className="compact-filter"><span>状态</span><select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}><option value="">全部状态</option>{tab === "sync" ? <><option value="completed">已完成</option><option value="conflict">版本冲突</option><option value="resolved">已重试处理</option><option value="discarded">已放弃</option><option value="failed">同步失败</option><option value="processing">处理中</option></> : <><option value="recording">记录中</option><option value="completed">已完成</option></>}</select></label>}</div>
      <QueryState loading={active.isLoading} error={active.error}>{tab === "sync" ? <SyncTable items={syncItems} onSelect={setSelected} /> : tab === "tracks" ? <TrackTable items={tracks.data?.items ?? []} onSelect={setSelected} /> : <EvidenceTable items={evidence.data?.items ?? []} onSelect={setSelected} />}</QueryState>
      <LedgerPagination total={active.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
    </section>
    <SidePanel wide open={Boolean(selected)} eyebrow="现场数据详情" title={detailTitle(selected)} onClose={() => setSelected(null)}>{selected && <RecordDetail record={selected} resolving={resolveConflict.isPending} onResolve={(strategy, note) => resolveConflict.mutate({ id: selected.id, strategy, note })} />}</SidePanel>
  </div>;
}

function SyncTable({ items, onSelect }: { items: MobileSyncOperationRecord[]; onSelect: (item: MobileSyncOperationRecord) => void }) { return <div className="table-scroll"><table className="ledger-table mobile-ledger-table"><thead><tr><th>现场操作</th><th>人员与业务</th><th>现场时间</th><th>接收结果</th><th>错误信息</th><th className="action-column">操作</th></tr></thead><tbody>{items.map((item) => <tr key={item.id} onClick={() => onSelect(item)}><td><strong>{actionLabel(item.action)}</strong><small>{item.clientOperationId}</small></td><td><strong>{item.userId}</strong><small>{item.entityType} · {item.entityId || "新建记录"}</small></td><td><strong>{formatDateTime(item.occurredAt)}</strong><small>接收 {formatDateTime(item.receivedAt)}</small></td><td><SyncBadge status={item.status} /></td><td><strong>{item.errorCode || "无错误"}</strong><small>{resultMessage(item.result)}</small></td><Action onClick={() => onSelect(item)} label="查看同步详情" /></tr>)}{!items.length && <Empty colSpan={6} icon={<WifiOff />} title="暂无同步记录" text="现场端提交离线操作后会显示在这里。" />}</tbody></table></div>; }
function TrackTable({ items, onSelect }: { items: MobileTrackRecord[]; onSelect: (item: MobileTrackRecord) => void }) { return <div className="table-scroll"><table className="ledger-table mobile-ledger-table"><thead><tr><th>轨迹记录</th><th>关联任务</th><th>采样统计</th><th>作业时段</th><th>同步人员</th><th className="action-column">操作</th></tr></thead><tbody>{items.map((item) => <tr key={item.id} onClick={() => onSelect(item)}><td><strong>{item.clientTrackId}</strong><small>{item.status === "completed" ? "已完成" : "记录中"}</small></td><td><strong>{item.taskId}</strong><small>{item.taskType}</small></td><td><strong>{item.pointCount} 个定位点</strong><small>{formatDistance(item.distanceMeters)}</small></td><td><strong>{formatDateTime(item.startedAt)}</strong><small>至 {formatDateTime(item.endedAt)}</small></td><td><strong>{item.userId}</strong><small>{formatDateTime(item.createdAt)}</small></td><Action onClick={() => onSelect(item)} label="查看轨迹详情" /></tr>)}{!items.length && <Empty colSpan={6} icon={<MapPin />} title="暂无轨迹记录" text="移动端回传定位轨迹后会显示在这里。" />}</tbody></table></div>; }
function EvidenceTable({ items, onSelect }: { items: MobileEvidenceRecord[]; onSelect: (item: MobileEvidenceRecord) => void }) { return <div className="table-scroll"><table className="ledger-table mobile-ledger-table"><thead><tr><th>证据文件</th><th>关联任务</th><th>采集位置</th><th>文件校验</th><th>上传人员</th><th className="action-column">操作</th></tr></thead><tbody>{items.map((item) => <tr key={item.id} onClick={() => onSelect(item)}><td><strong>{item.fileName}</strong><small>{item.evidenceNo}</small></td><td><strong>{item.taskId || "未关联任务"}</strong><small>{item.taskType || "通用证据"}</small></td><td><strong>{item.longitude !== null ? `${item.longitude.toFixed(6)}, ${item.latitude?.toFixed(6)}` : "未记录坐标"}</strong><small>{formatDateTime(item.capturedAt || item.createdAt)}</small></td><td><strong>{formatBytes(item.byteSize)}</strong><small>{item.sha256.slice(0, 16)}...</small></td><td><strong>{item.userId}</strong><small>{item.contentType}</small></td><Action onClick={() => onSelect(item)} label="查看证据详情" /></tr>)}{!items.length && <Empty colSpan={6} icon={<FileImage />} title="暂无现场证据" text="照片、视频或分片上传完成后会显示在这里。" />}</tbody></table></div>; }
function Action({ onClick, label }: { onClick: () => void; label: string }) { return <td className="action-column"><div className="row-actions"><button className="icon-button" type="button" aria-label={label} title="查看" onClick={(event) => { event.stopPropagation(); onClick(); }}><Eye aria-hidden="true" /></button></div></td>; }
function Empty({ colSpan, icon, title, text }: { colSpan: number; icon: React.ReactNode; title: string; text: string }) { return <tr className="empty-row"><td colSpan={colSpan}><div className="table-empty">{icon}<strong>{title}</strong><p>{text}</p></div></td></tr>; }
function RecordDetail({ record, resolving, onResolve }: { record: MobileSyncOperationRecord | MobileTrackRecord | MobileEvidenceRecord; resolving: boolean; onResolve: (strategy: "retry" | "discard", note: string) => void }) {
  const [note, setNote] = useState("");
  const conflict = "clientOperationId" in record && record.status === "conflict";
  return <div className="domain-detail">
    {conflict && <section className="detail-group conflict-resolution"><h3>冲突处理</h3><p>服务器记录已发生变化。确认现场数据仍有效后可按最新版本重试，或放弃本次离线操作；两种结果都会保留审计记录。</p><label><span>处理说明</span><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="填写核对结论，至少 2 个字" rows={3} /></label><div className="heading-actions"><button className="button primary" type="button" disabled={resolving || note.trim().length < 2} onClick={() => onResolve("retry", note.trim())}>按最新版本重试</button><button className="button danger" type="button" disabled={resolving || note.trim().length < 2} onClick={() => onResolve("discard", note.trim())}>放弃本次操作</button></div></section>}
    <section className="detail-group"><h3>完整数据</h3><pre className="json-detail">{JSON.stringify(record, null, 2)}</pre></section>{"url" in record && <a className="button primary" href={record.url} target="_blank" rel="noreferrer"><FileImage aria-hidden="true" />查看原始证据</a>}
  </div>;
}
function SyncBadge({ status }: { status: MobileSyncOperationRecord["status"] }) { const Icon = status === "completed" || status === "resolved" ? CheckCircle2 : AlertTriangle; return <span className={`status-badge mobile-sync-status ${status}`}><Icon aria-hidden="true" />{({ completed: "已完成", conflict: "版本冲突", failed: "同步失败", processing: "处理中", resolved: "已重试处理", discarded: "已放弃" })[status]}</span>; }
function Summary({ label, value, detail, tone = "" }: { label: string; value: number; detail: string; tone?: string }) { return <div className={tone}><small>{label}</small><strong>{value}</strong><em>{detail}</em></div>; }
function detailTitle(record: MobileSyncOperationRecord | MobileTrackRecord | MobileEvidenceRecord | null) { if (!record) return "详情"; if ("clientOperationId" in record) return record.clientOperationId; if ("clientTrackId" in record) return record.clientTrackId; return record.evidenceNo; }
function actionLabel(action: string) { return ({ accept: "接单", start: "开始作业", report: "巡护上报", attendance: "考勤上报", submit: "完工提交", sos: "紧急求助" } as Record<string, string>)[action] || action; }
function resultMessage(result: Record<string, unknown>) { return String(result.message || result.serverVersion || "服务端已留痕"); }
function formatDateTime(value?: string | null) { if (!value) return "未记录"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date); }
function formatDistance(value: number) { return value >= 1000 ? `${(value / 1000).toFixed(2)} km` : `${Math.round(value)} m`; }
function formatBytes(value: number) { return value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`; }
