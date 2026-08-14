import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertOctagon, BellRing, CheckCircle2, ChevronRight, CircleDot, Clock3, Download, Eye,
  FileCheck2, MapPinned, Pencil, Plus, RefreshCw, RotateCcw, Search, ShieldAlert,
  Siren, Trash2, UserRound, X,
} from "lucide-react";
import { type FormEvent, useDeferredValue, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  ForestBlockOption, SafetyActionPayload, SafetyAlert, SafetyEvent, SafetyEventPayload,
  SafetyEventStatus, SafetyEventType, SafetySeverity,
} from "../api/types";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 30;
const STATUS_ORDER: SafetyEventStatus[] = ["new", "triaged", "assigned", "handling", "resolved", "verified", "closed"];
const STATUS_LABELS: Record<SafetyEventStatus, string> = {
  new: "待分级", triaged: "待派单", assigned: "待接单", handling: "处置中",
  resolved: "待复核", verified: "待关闭", closed: "已关闭",
};
const TYPE_LABELS: Record<SafetyEventType, string> = {
  fire: "森林火情", pest: "病虫害", theft: "盗伐盗采", geofence: "越界告警",
  sos: "人员求救", equipment: "设备异常", weather: "灾害天气", other: "其他事件",
};
const SEVERITY_LABELS: Record<SafetySeverity, string> = { low: "低", medium: "中", high: "高", critical: "紧急" };
const SOURCE_LABELS: Record<SafetyEvent["sourceType"] | SafetyAlert["sourceType"], string> = {
  manual: "人工上报", device: "设备告警", patrol: "巡护发现", harvest: "采伐监管",
  ai: "AI 识别", system: "系统规则", alert: "告警转事件",
};

export function SafetyEventsPage() {
  const queryClient = useQueryClient();
  const capabilities = useCapabilities();
  const [view, setView] = useState<"events" | "alerts">("events");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<SafetyEvent | null>(null);
  const [selectedAlert, setSelectedAlert] = useState<SafetyAlert | null>(null);
  const [editingEvent, setEditingEvent] = useState<SafetyEvent | null>(null);
  const deferredQ = useDeferredValue(q);

  const events = useQuery({
    queryKey: ["v2-safety-events", deferredQ, status, severity, overdueOnly, includeDeleted, offset],
    queryFn: () => api.safetyEvents({ q: deferredQ, status, severity, overdueOnly, includeDeleted, limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const alerts = useQuery({
    queryKey: ["v2-safety-alerts", deferredQ, status, severity, offset],
    queryFn: () => api.safetyAlerts({ q: deferredQ, status, severity, limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const mergeTargets = useQuery({
    queryKey: ["v2-safety-merge-targets"],
    queryFn: () => api.safetyEvents({ limit: 200, offset: 0 }),
    enabled: Boolean(selectedAlert),
    staleTime: 15_000,
  });

  const permissions = capabilities.data?.permissions;
  const roles = capabilities.data?.principal.roles;
  const canCreate = hasPermission(permissions, roles, "safety.events.create");
  const canTriage = hasPermission(permissions, roles, "safety.events.triage");
  const canAssign = hasPermission(permissions, roles, "safety.events.assign");
  const canHandle = hasPermission(permissions, roles, "safety.events.handle");
  const canVerify = hasPermission(permissions, roles, "safety.events.verify");
  const canCommand = hasPermission(permissions, roles, "safety.events.command");
  const canReviewAlerts = hasPermission(permissions, roles, "safety.alerts.review");

  const create = useMutation({
    mutationFn: api.createSafetyEvent,
    onSuccess: async (record) => {
      setCreating(false);
      setSelectedEvent(record);
      await invalidateSafety(queryClient);
    },
  });
  const update = useMutation({
    mutationFn: ({ record, payload }: { record: SafetyEvent; payload: SafetyEventPayload }) => api.updateSafetyEvent(record.id, payload),
    onSuccess: async (record) => { setEditingEvent(null); setSelectedEvent(record); await invalidateSafety(queryClient); },
  });
  const remove = useMutation({ mutationFn: api.deleteSafetyEvent, onSuccess: async () => invalidateSafety(queryClient) });
  const restore = useMutation({ mutationFn: api.restoreSafetyEvent, onSuccess: async () => invalidateSafety(queryClient) });
  const eventAction = useMutation({
    mutationFn: ({ record, action, payload }: { record: SafetyEvent; action: string; payload?: SafetyActionPayload }) =>
      api.applySafetyEventAction(record.id, action, payload),
    onSuccess: async (record) => {
      setSelectedEvent(record);
      await invalidateSafety(queryClient);
    },
  });
  const alertAction = useMutation({
    mutationFn: ({ record, action, payload }: { record: SafetyAlert; action: string; payload?: SafetyActionPayload }) =>
      api.applySafetyAlertAction(record.id, action, payload),
    onSuccess: async (result) => {
      if ("event" in result && result.event) {
        setSelectedAlert(null);
        setSelectedEvent(result.event);
        setView("events");
      } else {
        setSelectedAlert(null);
      }
      await invalidateSafety(queryClient);
    },
  });

  const eventItems = events.data?.items ?? [];
  const alertItems = alerts.data?.items ?? [];
  const metrics = useMemo(() => ({
    open: eventItems.filter((item) => item.status !== "closed").length,
    critical: eventItems.filter((item) => item.status !== "closed" && item.severity === "critical").length,
    overdue: eventItems.filter(isOverdue).length,
    alerts: alertItems.filter((item) => item.status === "new").length,
  }), [alertItems, eventItems]);
  const activeQuery = view === "events" ? events : alerts;
  const activeTotal = activeQuery.data?.total ?? 0;

  const switchView = (next: "events" | "alerts") => {
    setView(next);
    setQ(""); setStatus(""); setSeverity(""); setOverdueOnly(false); setIncludeDeleted(false); setOffset(0);
  };

  return <div className="standard-page ledger-page safety-page">
    <section className="page-heading ledger-heading">
      <div><span className="eyebrow">安全应急 / 统一业务主线</span><h1>事件中心</h1><p>告警先确认、事件再闭环；每条事件都有责任人、办理时限、空间位置、处置证据和完整时间轴。</p></div>
      <div className="heading-actions">{view === "events" && <a className="button secondary" href={`/api/v2/safety/events-export.csv?${new URLSearchParams({ q: deferredQ, status, severity }).toString()}`}><Download aria-hidden="true" />导出台账</a>}<button className="button secondary" type="button" onClick={() => activeQuery.refetch()}><RefreshCw aria-hidden="true" />刷新</button><button className="button primary" type="button" disabled={!canCreate} onClick={() => setCreating(true)} title={canCreate ? "上报安全事件" : "当前角色无事件上报权限"}><Plus aria-hidden="true" />上报事件</button></div>
    </section>

    <section className="safety-summary-strip" aria-label="安全事件摘要">
      <SummaryMetric label="未关闭事件" value={metrics.open} detail="当前页开放事件" icon={<ShieldAlert aria-hidden="true" />} />
      <SummaryMetric label="紧急事件" value={metrics.critical} detail="需要优先处置" tone="danger" icon={<Siren aria-hidden="true" />} />
      <SummaryMetric label="已经超时" value={metrics.overdue} detail="超过办理时限" tone="warning" icon={<Clock3 aria-hidden="true" />} />
      <SummaryMetric label="待确认告警" value={metrics.alerts} detail="尚未转为事件" tone="active" icon={<BellRing aria-hidden="true" />} />
    </section>

    <section className="ledger-shell safety-ledger-shell">
      <div className="ledger-tabs" role="tablist" aria-label="事件中心视图">
        <button type="button" className={view === "events" ? "active" : ""} onClick={() => switchView("events")} role="tab" aria-selected={view === "events"}>事件台账</button>
        <button type="button" className={view === "alerts" ? "active" : ""} onClick={() => switchView("alerts")} role="tab" aria-selected={view === "alerts"}>告警收件箱{metrics.alerts > 0 && <span>{metrics.alerts}</span>}</button>
      </div>
      <div className="ledger-toolbar safety-toolbar">
        <label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder={view === "events" ? "搜索事件编号、标题、地点或责任人" : "搜索告警编号、设备、标题或地点"} /></label>
        <label className="compact-filter"><span>{view === "events" ? "办理状态" : "告警状态"}</span><select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}><option value="">全部状态</option>{view === "events" ? STATUS_ORDER.map((value) => <option value={value} key={value}>{STATUS_LABELS[value]}</option>) : <><option value="new">待确认</option><option value="converted">已转事件</option><option value="merged">已合并</option><option value="ignored">已忽略</option></>}</select></label>
        <label className="compact-filter"><span>风险等级</span><select value={severity} onChange={(event) => { setSeverity(event.target.value); setOffset(0); }}><option value="">全部等级</option>{Object.entries(SEVERITY_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
        {view === "events" && <label className="toggle-filter"><input type="checkbox" checked={overdueOnly} onChange={(event) => { setOverdueOnly(event.target.checked); setOffset(0); }} /><span>只看超时</span></label>}
        {view === "events" && canCreate && <label className="toggle-filter"><input type="checkbox" checked={includeDeleted} onChange={(event) => { setIncludeDeleted(event.target.checked); setOffset(0); }} /><span>显示已删除</span></label>}
        {(q || status || severity || overdueOnly || includeDeleted) && <button className="text-button" type="button" onClick={() => { setQ(""); setStatus(""); setSeverity(""); setOverdueOnly(false); setIncludeDeleted(false); setOffset(0); }}>清除条件</button>}
      </div>
      {view === "events" ? <EventLedger query={events} items={eventItems} canManage={canCreate} onView={setSelectedEvent} onEdit={setEditingEvent} onDelete={(record) => remove.mutate(record.id)} onRestore={(record) => restore.mutate(record.id)} /> : <AlertLedger query={alerts} items={alertItems} onView={setSelectedAlert} />}
      <LedgerPagination total={activeTotal} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
    </section>

    <SidePanel wide open={creating} eyebrow="安全事件上报" title="新建安全事件" onClose={() => !create.isPending && setCreating(false)}>
      <SafetyCreateForm pending={create.isPending} error={create.error} onCancel={() => setCreating(false)} onSubmit={(payload) => create.mutate(payload)} />
    </SidePanel>
    <SidePanel wide open={Boolean(editingEvent)} eyebrow="安全事件维护" title="编辑未分级事件" onClose={() => !update.isPending && setEditingEvent(null)}>
      {editingEvent && <SafetyCreateForm record={editingEvent} pending={update.isPending} error={update.error} onCancel={() => setEditingEvent(null)} onSubmit={(payload) => update.mutate({ record: editingEvent, payload })} />}
    </SidePanel>
    <SidePanel wide open={Boolean(selectedEvent)} eyebrow="安全事件闭环" title={selectedEvent?.title || "事件详情"} onClose={() => !eventAction.isPending && setSelectedEvent(null)}>
      {selectedEvent && <SafetyEventDetail record={selectedEvent} permissions={{ triage: canTriage, assign: canAssign, handle: canHandle, verify: canVerify, command: canCommand }} pending={eventAction.isPending} error={eventAction.error} onAction={(action, payload) => eventAction.mutate({ record: selectedEvent, action, payload })} />}
    </SidePanel>
    <SidePanel wide open={Boolean(selectedAlert)} eyebrow="告警人工确认" title={selectedAlert?.title || "告警详情"} onClose={() => !alertAction.isPending && setSelectedAlert(null)}>
      {selectedAlert && <SafetyAlertDetail key={selectedAlert.id} alert={selectedAlert} openEvents={(mergeTargets.data?.items ?? []).filter((item) => item.status !== "closed")} canReview={canReviewAlerts} pending={alertAction.isPending} error={alertAction.error} onAction={(action, payload) => alertAction.mutate({ record: selectedAlert, action, payload })} />}
    </SidePanel>
  </div>;
}

function EventLedger({ query, items, canManage, onView, onEdit, onDelete, onRestore }: { query: ReturnType<typeof useQuery<any>>; items: SafetyEvent[]; canManage: boolean; onView: (record: SafetyEvent) => void; onEdit: (record: SafetyEvent) => void; onDelete: (record: SafetyEvent) => void; onRestore: (record: SafetyEvent) => void }) {
  return <QueryState loading={query.isLoading} error={query.error}><div className="table-scroll"><table className="ledger-table safety-event-table"><thead><tr><th>安全事件</th><th>空间位置</th><th>责任与时限</th><th>风险等级</th><th>办理状态</th><th className="action-column">操作</th></tr></thead><tbody>
    {items.map((record) => <tr className={record.deletedAt ? "is-deleted" : ""} key={record.id} onClick={() => onView(record)}><td><strong>{record.title}</strong><small>{record.incidentNo} · {TYPE_LABELS[record.eventType]}</small></td><td><strong>{record.locationText || record.blocks[0]?.code || "位置待确认"}</strong><small>{record.blocks.length ? `关联 ${record.blocks.length} 个林班` : "尚未关联林班"}</small></td><td><strong>{record.assigneeName || record.responsibilityUnit || "待分派"}</strong><small className={isOverdue(record) ? "overdue-copy" : ""}>{record.deadlineAt ? `${isOverdue(record) ? "已超时 · " : "截止 "}${formatDateTime(record.deadlineAt)}` : "办理时限待设置"}</small></td><td><SeverityBadge value={record.severity} /></td><td>{record.deletedAt ? <span className="status-badge muted">已删除</span> : <StatusBadge value={record.status} />}</td><td className="action-column"><div className="row-actions"><button className="icon-button" type="button" aria-label="查看" title="查看" onClick={(event) => { event.stopPropagation(); onView(record); }}><Eye aria-hidden="true" /></button>{record.deletedAt ? <button className="icon-button" type="button" aria-label="恢复" title="恢复" disabled={!canManage} onClick={(event) => { event.stopPropagation(); onRestore(record); }}><RotateCcw aria-hidden="true" /></button> : <><button className="icon-button" type="button" aria-label="编辑" title={record.status === "new" ? "编辑" : "仅未分级事件可编辑"} disabled={!canManage || record.status !== "new"} onClick={(event) => { event.stopPropagation(); onEdit(record); }}><Pencil aria-hidden="true" /></button><button className="icon-button danger" type="button" aria-label="删除" title={record.status === "new" ? "删除" : "仅未分级事件可删除"} disabled={!canManage || record.status !== "new"} onClick={(event) => { event.stopPropagation(); onDelete(record); }}><Trash2 aria-hidden="true" /></button></>}</div></td></tr>)}
    {!query.isLoading && !items.length && <tr><td colSpan={6}><div className="table-empty"><ShieldAlert aria-hidden="true" /><strong>当前没有安全事件</strong><p>可上报人工发现事件，也可先在告警收件箱确认设备或系统告警。</p></div></td></tr>}
  </tbody></table></div></QueryState>;
}

function AlertLedger({ query, items, onView }: { query: ReturnType<typeof useQuery<any>>; items: SafetyAlert[]; onView: (record: SafetyAlert) => void }) {
  return <QueryState loading={query.isLoading} error={query.error}><div className="table-scroll"><table className="ledger-table safety-alert-table"><thead><tr><th>告警信息</th><th>来源设备</th><th>空间位置</th><th>发生时间</th><th>处理状态</th><th className="action-column">操作</th></tr></thead><tbody>
    {items.map((record) => <tr key={record.id} onClick={() => onView(record)}><td><strong>{record.title}</strong><small>{record.alertNo} · {record.alertType}</small></td><td><strong>{record.deviceCode || SOURCE_LABELS[record.sourceType]}</strong><small>{SOURCE_LABELS[record.sourceType]}{record.sourceRef ? ` · ${record.sourceRef}` : ""}</small></td><td><strong>{record.locationText || record.linkedBlockCodes[0] || "位置待确认"}</strong><small>{record.linkedBlockCodes.length ? `关联 ${record.linkedBlockCodes.length} 个林班` : "需要人工定位"}</small></td><td><strong>{formatDateTime(record.occurredAt)}</strong><small><SeverityBadge value={record.severity} /></small></td><td><AlertStatusBadge value={record.status} /></td><td className="action-column"><div className="row-actions"><button className="icon-button" type="button" aria-label="查看" title="查看" onClick={(event) => { event.stopPropagation(); onView(record); }}><Eye aria-hidden="true" /></button></div></td></tr>)}
    {!query.isLoading && !items.length && <tr><td colSpan={6}><div className="table-empty"><BellRing aria-hidden="true" /><strong>当前没有告警</strong><p>设备、巡护、采伐监管和 AI 识别产生的告警会进入这里，确认后才转为业务事件。</p></div></td></tr>}
  </tbody></table></div></QueryState>;
}

function SafetyCreateForm({ record, pending, error, onCancel, onSubmit }: { record?: SafetyEvent; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: SafetyEventPayload) => void }) {
  const [blocks, setBlocks] = useState<ForestBlockOption[]>(record?.blocks.map((block) => ({ id: block.id, code: block.code, name: block.code, location: "", areaMu: null, hasGeometry: true, riskLevel: null })) || []);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSubmit({
      title: field(data, "title"), eventType: field(data, "eventType") as SafetyEventType,
      severity: field(data, "severity") as SafetySeverity, sourceType: "manual", sourceRef: "",
      locationText: field(data, "locationText"), description: field(data, "description"),
      linkedBlockCodes: blocks.map((item) => item.code),
    });
  };
  return <>
    <form className="entity-form safety-create-form" onSubmit={submit}>
      <fieldset className="form-section"><legend>事件基本信息</legend><p>先客观记录发现情况；责任单位和责任人将在分级、派单环节确定。</p><div className="form-grid"><label className="field-span"><span>事件标题<em>*</em></span><input name="title" required placeholder="例如：上屯村竹林疑似火情" defaultValue={record?.title} /></label><label><span>事件类型<em>*</em></span><select name="eventType" defaultValue={record?.eventType || "fire"}>{Object.entries(TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>初判等级<em>*</em></span><select name="severity" defaultValue={record?.severity || "medium"}>{Object.entries(SEVERITY_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label className="field-span"><span>位置描述</span><input name="locationText" placeholder="村、山场、小地名或道路附近" defaultValue={record?.locationText} /></label><label className="field-span"><span>发现情况<em>*</em></span><textarea name="description" rows={4} required placeholder="说明发现时间、现场情况和潜在影响。" defaultValue={record?.description} /></label></div></fieldset>
      <fieldset className="form-section"><legend>空间关联</legend><p>必须从正式林班台账选择，便于地图定位、数据范围控制和后续统计。</p><button className="relation-picker safety-block-picker" type="button" onClick={() => setSelectorOpen(true)}><span><MapPinned aria-hidden="true" /></span><div><small>关联林班</small><strong>{blocks.length ? `已选择 ${blocks.length} 个林班` : "尚未选择林班"}</strong></div><ChevronRight aria-hidden="true" /></button><div className="relation-chips">{blocks.map((block) => <span key={block.id}><strong>{block.name}</strong><small>{block.code} · {block.areaMu ?? "面积待补"} 亩</small><button type="button" aria-label={`移除 ${block.name}`} onClick={() => setBlocks((items) => items.filter((item) => item.id !== block.id))}><X aria-hidden="true" /></button></span>)}</div></fieldset>
      {error && <p className="form-error">{error.message}</p>}
      <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={pending || !blocks.length}>{pending ? "正在保存" : record ? "保存修改" : "上报事件"}</button></div>
    </form>
    <ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => setBlocks((items) => items.some((item) => item.id === block.id) ? items : [...items, block])} />
  </>;
}

function SafetyEventDetail({ record, permissions, pending, error, onAction }: { record: SafetyEvent; permissions: { triage: boolean; assign: boolean; handle: boolean; verify: boolean; command: boolean }; pending: boolean; error: Error | null; onAction: (action: string, payload?: SafetyActionPayload) => void }) {
  const current = STATUS_ORDER.indexOf(record.status);
  return <div className="safety-detail">
    <div className="safety-detail-header"><div><SeverityBadge value={record.severity} /><StatusBadge value={record.status} /></div><strong>{record.incidentNo}</strong></div>
    <ol className="safety-progress">{STATUS_ORDER.map((value, index) => <li className={index < current ? "done" : index === current ? "current" : ""} key={value}><span>{index < current ? <CheckCircle2 aria-hidden="true" /> : index + 1}</span><small>{STATUS_LABELS[value]}</small></li>)}</ol>
    <section className="event-facts"><div><span>事件类型</span><strong>{TYPE_LABELS[record.eventType]}</strong></div><div><span>事件来源</span><strong>{SOURCE_LABELS[record.sourceType]}</strong></div><div><span>责任单位</span><strong>{record.responsibilityUnit || "待分级确认"}</strong></div><div><span>当前责任人</span><strong>{record.assigneeName || "待派单"}</strong></div><div><span>办理时限</span><strong className={isOverdue(record) ? "overdue-copy" : ""}>{record.deadlineAt ? formatDateTime(record.deadlineAt) : "待设置"}</strong></div><div><span>空间位置</span><strong>{record.locationText || record.blocks.map((item) => item.code).join("、")}</strong></div></section>
    <section className="event-description"><span>事件描述</span><p>{record.description || "未填写事件描述。"}</p><div className="relation-chips">{record.blocks.map((block) => <span key={block.id}><strong>{block.code}</strong><small>正式林班关联</small></span>)}</div></section>
    {record.resolution.summary && <section className="event-resolution"><FileCheck2 aria-hidden="true" /><div><span>处置结果</span><h3>{record.resolution.summary}</h3><p>{record.resolution.evidenceUrls?.length ? `已提交 ${record.resolution.evidenceUrls.length} 项证据` : "暂未提交附件证据"} · {record.resolution.resolvedBy || "处置人员"}</p></div></section>}
    <EventActionPanel record={record} permissions={permissions} pending={pending} error={error} onAction={onAction} />
    <section className="event-timeline"><header className="section-heading"><div><h3>办理时间轴</h3><p>状态、责任和证据变更自动留痕</p></div></header><div className="timeline-list">{[...record.timeline].reverse().map((item) => <article key={item.id}><span><CircleDot aria-hidden="true" /></span><div><strong>{actionLabel(item.action)}</strong><small>{formatDateTime(item.createdAt)} · {item.actor}</small>{item.note && <p>{item.note}</p>}</div></article>)}</div></section>
  </div>;
}

function EventActionPanel({ record, permissions, pending, error, onAction }: { record: SafetyEvent; permissions: { triage: boolean; assign: boolean; handle: boolean; verify: boolean; command: boolean }; pending: boolean; error: Error | null; onAction: (action: string, payload?: SafetyActionPayload) => void }) {
  if (record.deletedAt) return <div className="action-unavailable"><RotateCcw aria-hidden="true" /><span><strong>事件已进入回收站</strong><small>恢复事件后才能继续分级和处置。</small></span></div>;
  const [escalating, setEscalating] = useState(false);
  const submit = (event: FormEvent<HTMLFormElement>, action: string) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const evidence = field(data, "evidenceUrls").split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    onAction(action, {
      note: field(data, "note"), eventType: optional(data, "eventType") as SafetyEventType | undefined,
      severity: optional(data, "severity") as SafetySeverity | undefined,
      responsibilityUnit: optional(data, "responsibilityUnit"), assigneeName: optional(data, "assigneeName"),
      deadlineAt: optional(data, "deadlineAt"), resolutionSummary: optional(data, "resolutionSummary"), evidenceUrls: evidence,
    });
  };
  const station = (() => {
    if (record.status === "new" && permissions.triage) return <form onSubmit={(event) => submit(event, "triage")}><header><div><span>下一步</span><h3>确认事件分级</h3><p>确认类型、等级和责任单位，再进入派单。</p></div></header><div className="form-grid"><label><span>事件类型</span><select name="eventType" defaultValue={record.eventType}>{Object.entries(TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>风险等级</span><select name="severity" defaultValue={record.severity}>{Object.entries(SEVERITY_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label className="field-span"><span>责任单位<em>*</em></span><input name="responsibilityUnit" required placeholder="例如：小桥镇林业站" /></label><label className="field-span"><span>分级说明</span><textarea name="note" rows={2} /></label></div><div className="form-actions"><button className="button primary" disabled={pending}>完成分级</button></div></form>;
    if (record.status === "triaged" && permissions.assign) return <form onSubmit={(event) => submit(event, "assign")}><header><div><span>下一步</span><h3>派发处置任务</h3><p>明确具体责任人和完成时限。</p></div></header><div className="form-grid"><label><span>责任人<em>*</em></span><input name="assigneeName" required placeholder="姓名或班组" /></label><label><span>办理时限<em>*</em></span><input name="deadlineAt" type="datetime-local" required defaultValue={defaultDeadline()} /></label><label className="field-span"><span>派单要求</span><textarea name="note" rows={2} /></label></div><div className="form-actions"><button className="button primary" disabled={pending}>确认派单</button></div></form>;
    if (record.status === "assigned" && permissions.handle) return <form onSubmit={(event) => submit(event, "accept")}><header><div><span>下一步</span><h3>接单并开始处置</h3><p>接单后事件进入处置中，首页待办同步更新。</p></div></header><label><span>接单备注</span><textarea name="note" rows={2} /></label><div className="form-actions"><button className="button primary" disabled={pending}>接单处置</button></div></form>;
    if (record.status === "handling" && permissions.handle) return <form onSubmit={(event) => submit(event, "resolve")}><header><div><span>当前办理</span><h3>记录进展或提交结果</h3><p>进展只留痕，提交结果后进入复核。</p></div></header><label><span>处置说明<em>*</em></span><textarea name="resolutionSummary" rows={3} required placeholder="填写现场处置情况和最终结果。" /></label><label><span>证据地址</span><textarea name="evidenceUrls" rows={2} placeholder="每行一个照片、视频或文档地址" /></label><label><span>补充备注</span><textarea name="note" rows={2} /></label><div className="form-actions"><button className="button secondary" type="button" disabled={pending} onClick={(event) => { const form = event.currentTarget.form; if (!form) return; const data = new FormData(form); onAction("progress", { note: field(data, "resolutionSummary") || field(data, "note") }); }}>记录进展</button><button className="button primary" disabled={pending}>提交处置结果</button></div></form>;
    if (record.status === "resolved" && permissions.verify) return <form onSubmit={(event) => submit(event, "verify")}><header><div><span>下一步</span><h3>复核处置结果</h3><p>复核不通过将退回处置中，不产生多余永久状态。</p></div></header><label><span>复核意见</span><textarea name="note" rows={3} /></label><div className="form-actions"><button className="button secondary" type="button" disabled={pending} onClick={(event) => { const form = event.currentTarget.form; if (!form) return; const note = field(new FormData(form), "note"); if (note) onAction("return", { note }); }}>退回处置</button><button className="button primary" disabled={pending}>复核通过</button></div></form>;
    if (record.status === "verified" && permissions.verify) return <form onSubmit={(event) => submit(event, "close")}><header><div><span>下一步</span><h3>关闭并归档事件</h3><p>关闭后事件进入只读归档，管理员仍可按原因重开。</p></div></header><label><span>关闭说明</span><textarea name="note" rows={2} /></label><div className="form-actions"><button className="button primary" disabled={pending}>关闭事件</button></div></form>;
    if (record.status === "closed" && permissions.command) return <form onSubmit={(event) => submit(event, "reopen")}><header><div><span>管理操作</span><h3>重新打开事件</h3><p>仅在发现复发、漏项或复核错误时使用。</p></div></header><label><span>重开原因<em>*</em></span><textarea name="note" rows={3} required /></label><div className="form-actions"><button className="button secondary" disabled={pending}><RotateCcw aria-hidden="true" />重新打开</button></div></form>;
    return <div className="action-unavailable"><CheckCircle2 aria-hidden="true" /><span><strong>{record.status === "closed" ? "事件已经归档" : "当前角色没有本环节办理权限"}</strong><small>可继续查看责任、时限、证据和办理时间轴。</small></span></div>;
  })();
  const canEscalate = permissions.command && ["triaged", "assigned", "handling"].includes(record.status) && record.severity !== "critical";
  return <section className="event-action-card">{station}{canEscalate && <div className="escalation-bar">{escalating ? <form onSubmit={(event) => submit(event, "escalate")}><label><span>升级等级</span><select name="severity" defaultValue={nextSeverity(record.severity)}>{Object.entries(SEVERITY_LABELS).filter(([value]) => severityRank(value as SafetySeverity) > severityRank(record.severity)).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>升级原因</span><input name="note" required /></label><button className="button danger" disabled={pending}>确认升级</button><button className="icon-button" type="button" onClick={() => setEscalating(false)} aria-label="取消升级"><X aria-hidden="true" /></button></form> : <button className="text-button danger-copy" type="button" onClick={() => setEscalating(true)}><AlertOctagon aria-hidden="true" />升级事件等级</button>}</div>}{error && <p className="form-error">{error.message}</p>}</section>;
}

function SafetyAlertDetail({ alert, openEvents, canReview, pending, error, onAction }: { alert: SafetyAlert; openEvents: SafetyEvent[]; canReview: boolean; pending: boolean; error: Error | null; onAction: (action: string, payload?: SafetyActionPayload) => void }) {
  const [selectedBlock, setSelectedBlock] = useState<ForestBlockOption | null>(null);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const submitConvert = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onAction("convert", { title: field(data, "title"), eventType: field(data, "eventType") as SafetyEventType, severity: field(data, "severity") as SafetySeverity, note: field(data, "note"), linkedBlockCodes: alert.linkedBlockCodes.length ? alert.linkedBlockCodes : selectedBlock ? [selectedBlock.code] : [] });
  };
  return <div className="safety-alert-detail">
    <div className="safety-detail-header"><div><SeverityBadge value={alert.severity} /><AlertStatusBadge value={alert.status} /></div><strong>{alert.alertNo}</strong></div>
    <section className="alert-source-card"><BellRing aria-hidden="true" /><div><span>{SOURCE_LABELS[alert.sourceType]}</span><h3>{alert.deviceCode || alert.sourceRef || "来源设备待补"}</h3><p>{formatDateTime(alert.occurredAt)} · {alert.locationText || "位置待确认"}</p></div></section>
    <section className="event-description"><span>告警内容</span><p>{alert.description || alert.title}</p><div className="relation-chips">{alert.linkedBlockCodes.map((code) => <span key={code}><strong>{code}</strong><small>告警关联林班</small></span>)}{selectedBlock && <span><strong>{selectedBlock.name}</strong><small>{selectedBlock.code}</small><button type="button" onClick={() => setSelectedBlock(null)} aria-label="移除补选林班"><X aria-hidden="true" /></button></span>}</div></section>
    {alert.status === "new" && canReview ? <section className="alert-review-card">
      <form onSubmit={submitConvert}><header><div><span>人工确认</span><h3>转为安全事件</h3><p>确认后进入事件分级，不直接把设备告警当成业务结论。</p></div></header><div className="form-grid"><label className="field-span"><span>事件标题</span><input name="title" defaultValue={alert.title} required /></label><label><span>事件类型</span><select name="eventType" defaultValue={alert.alertType in TYPE_LABELS ? alert.alertType : "other"}>{Object.entries(TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>风险等级</span><select name="severity" defaultValue={alert.severity}>{Object.entries(SEVERITY_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label className="field-span"><span>确认说明</span><textarea name="note" rows={2} /></label></div>{!alert.linkedBlockCodes.length && !selectedBlock && <button className="relation-picker safety-block-picker" type="button" onClick={() => setSelectorOpen(true)}><span><MapPinned aria-hidden="true" /></span><div><small>空间定位必填</small><strong>从正式林班台账补选位置</strong></div><ChevronRight aria-hidden="true" /></button>}<div className="form-actions"><button className="button secondary" type="button" disabled={pending} onClick={() => onAction("ignore", { note: "人工判断为无效告警" })}>忽略告警</button><button className="button primary" disabled={pending || (!alert.linkedBlockCodes.length && !selectedBlock)}>确认并转事件</button></div></form>
      <form className="merge-alert-form" onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); onAction("merge", { eventId: field(data, "eventId"), note: field(data, "note") }); }}><label><span>重复告警合并</span><select name="eventId" required defaultValue=""><option value="" disabled>选择当前开放事件</option>{openEvents.map((item) => <option value={item.id} key={item.id}>{item.incidentNo} · {item.title}</option>)}</select></label><label><span>合并说明</span><input name="note" placeholder="说明为何属于同一事件" /></label><button className="button secondary" disabled={pending || !openEvents.length}>合并到事件</button></form>
    </section> : <div className="action-unavailable"><CheckCircle2 aria-hidden="true" /><span><strong>该告警已经处理</strong><small>{alert.review?.note || (alert.eventId ? `关联事件 ${alert.eventId}` : "无需重复确认")}</small>{alert.review?.reviewedBy && <small>{alert.review.reviewedBy} · {alert.review.reviewedAt ? formatDateTime(alert.review.reviewedAt) : ""}</small>}</span></div>}
    {error && <p className="form-error">{error.message}</p>}
    <ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={setSelectedBlock} />
  </div>;
}

function SummaryMetric({ label, value, detail, icon, tone = "" }: { label: string; value: number; detail: string; icon: React.ReactNode; tone?: string }) { return <div className={tone}><span>{icon}</span><div><small>{label}</small><strong>{value}</strong><em>{detail}</em></div></div>; }
function SeverityBadge({ value }: { value: SafetySeverity }) { return <span className={`severity-badge ${value}`}><span />{SEVERITY_LABELS[value]}</span>; }
function StatusBadge({ value }: { value: SafetyEventStatus }) { return <span className={`event-status ${value}`}>{STATUS_LABELS[value]}</span>; }
function AlertStatusBadge({ value }: { value: SafetyAlert["status"] }) { const labels = { new: "待确认", converted: "已转事件", merged: "已合并", ignored: "已忽略" }; return <span className={`alert-status ${value}`}>{labels[value]}</span>; }
function isOverdue(record: SafetyEvent) { return Boolean(record.deadlineAt && record.status !== "closed" && record.status !== "verified" && new Date(record.deadlineAt).getTime() < Date.now()); }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date); }
function defaultDeadline() { const date = new Date(Date.now() + 24 * 60 * 60 * 1000); const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000); return local.toISOString().slice(0, 16); }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function optional(data: FormData, name: string) { const value = field(data, name); return value || undefined; }
function severityRank(value: SafetySeverity) { return { low: 0, medium: 1, high: 2, critical: 3 }[value]; }
function nextSeverity(value: SafetySeverity): SafetySeverity { return ({ low: "medium", medium: "high", high: "critical", critical: "critical" } as const)[value]; }
function actionLabel(action: string) { return ({ report: "事件上报", "convert-alert": "告警转事件", triage: "完成分级", assign: "任务派发", accept: "责任人接单", progress: "记录处置进展", resolve: "提交处置结果", return: "复核退回", verify: "复核通过", close: "关闭归档", reopen: "重新打开", escalate: "事件升级", "merge-alert": "合并告警" } as Record<string, string>)[action] || action; }
async function invalidateSafety(queryClient: ReturnType<typeof useQueryClient>) { await Promise.all([queryClient.invalidateQueries({ queryKey: ["v2-safety-events"] }), queryClient.invalidateQueries({ queryKey: ["v2-safety-alerts"] }), queryClient.invalidateQueries({ queryKey: ["v2-safety-merge-targets"] }), queryClient.invalidateQueries({ queryKey: ["workspace-summary"] })]); }
