import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Download,
  Eye,
  MapPin,
  Paperclip,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import { type FormEvent, type ReactNode, useDeferredValue, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  AttachmentRecord,
  ForestBlockOption,
  PatrolActionPayload,
  PatrolStatus,
  PatrolTask,
  PatrolTaskPayload,
} from "../api/types";
import { AttachmentSelector } from "../components/AttachmentSelector";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 50;
const STATUS_ORDER: PatrolStatus[] = ["planned", "assigned", "accepted", "patrolling", "reported", "resolved", "verified", "closed"];
const STATUS_LABELS: Record<PatrolStatus, string> = {
  planned: "待派发", assigned: "待接单", accepted: "待出发", patrolling: "巡护中",
  reported: "待处置/复核", resolved: "待复核", verified: "待归档", closed: "已完成",
};
const PRIORITY_LABELS = { low: "低", normal: "普通", high: "高", urgent: "紧急" } as const;

export function PatrolPage() {
  const queryClient = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<PatrolTask | null>(null);
  const [selected, setSelected] = useState<PatrolTask | null>(null);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const deferredQ = useDeferredValue(q);
  const tasks = useQuery({
    queryKey: ["v2-patrol-tasks", deferredQ, status, includeDeleted, offset],
    queryFn: () => api.patrolTasks({ q: deferredQ, status, includeDeleted, limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const permissions = capabilities.data?.permissions;
  const roles = capabilities.data?.principal.roles;
  const canCreate = hasPermission(permissions, roles, "business.maintenanceTasks.create");
  const canUpdate = hasPermission(permissions, roles, "business.maintenanceTasks.update");
  const canDelete = hasPermission(permissions, roles, "business.maintenanceTasks.delete");
  const canRestore = hasPermission(permissions, roles, "business.maintenanceTasks.restore");
  const canExport = hasPermission(permissions, roles, "business.maintenanceTasks.export");

  const create = useMutation({
    mutationFn: api.createPatrolTask,
    onSuccess: async (task) => {
      setCreating(false);
      setSelected(task);
      await queryClient.invalidateQueries({ queryKey: ["v2-patrol-tasks"] });
    },
  });
  const action = useMutation({
    mutationFn: ({ task, action: actionName, payload }: { task: PatrolTask; action: string; payload?: PatrolActionPayload }) =>
      api.applyPatrolAction(task.id, actionName, payload),
    onSuccess: async (task) => {
      setSelected(task);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["v2-patrol-tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["workspace-summary"] }),
      ]);
    },
  });
  const update = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: PatrolTaskPayload }) => api.updatePatrolTask(id, payload),
    onSuccess: async (task) => { setEditing(null); setSelected(task); await queryClient.invalidateQueries({ queryKey: ["v2-patrol-tasks"] }); },
  });
  const remove = useMutation({
    mutationFn: api.deletePatrolTask,
    onSuccess: async () => { setSelected(null); await queryClient.invalidateQueries({ queryKey: ["v2-patrol-tasks"] }); },
  });
  const restore = useMutation({
    mutationFn: api.restorePatrolTask,
    onSuccess: async (task) => { setSelected(task); await queryClient.invalidateQueries({ queryKey: ["v2-patrol-tasks"] }); },
  });

  const visibleItems = tasks.data?.items ?? [];
  const summary = useMemo(() => ({
    active: visibleItems.filter((item) => ["assigned", "accepted", "patrolling"].includes(item.status)).length,
    review: visibleItems.filter((item) => ["reported", "resolved"].includes(item.status)).length,
    urgent: visibleItems.filter((item) => item.priority === "urgent").length,
  }), [visibleItems]);

  return (
    <div className="standard-page ledger-page patrol-page">
      <section className="page-heading ledger-heading">
        <div><span className="eyebrow">生产运营 / 巡护管护</span><h1>巡护办理</h1><p>围绕正式林班建立任务，按派发、接单、现场巡护、上报、复核和归档形成可追溯闭环。</p></div>
        <div className="heading-actions">
          <button className="button secondary" type="button" onClick={() => tasks.refetch()}><RefreshCw aria-hidden="true" />刷新</button>
          <a className={`button secondary ${canExport ? "" : "disabled"}`} href={canExport ? `/api/v2/patrol/tasks-export.csv?${new URLSearchParams({ q, status }).toString()}` : undefined}><Download aria-hidden="true" />导出台账</a>
          <button className="button primary" type="button" disabled={!canCreate} onClick={() => setCreating(true)} title={canCreate ? "新建巡护任务" : "当前角色无创建权限"}><Plus aria-hidden="true" />新建任务</button>
        </div>
      </section>

      <section className="patrol-summary-strip" aria-label="当前页巡护摘要">
        <SummaryMetric label="任务总数" value={tasks.data?.total ?? 0} detail="当前筛选结果" />
        <SummaryMetric label="执行中" value={summary.active} detail="待接单、待出发、巡护中" />
        <SummaryMetric label="待处置/复核" value={summary.review} detail="已提交现场结果" />
        <SummaryMetric label="紧急任务" value={summary.urgent} detail="当前页需优先处理" tone="warning" />
      </section>

      <section className="ledger-shell">
        <div className="ledger-toolbar">
          <label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索任务编号、名称、责任人或林班" /></label>
          <label className="compact-filter"><span>办理状态</span><select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}><option value="">全部状态</option>{STATUS_ORDER.map((value) => <option value={value} key={value}>{STATUS_LABELS[value]}</option>)}</select></label>
          {canRestore && <label className="compact-check"><input type="checkbox" checked={includeDeleted} onChange={(event) => { setIncludeDeleted(event.target.checked); setOffset(0); }} />显示已删除</label>}
          {(q || status || includeDeleted) && <button className="text-button" type="button" onClick={() => { setQ(""); setStatus(""); setIncludeDeleted(false); setOffset(0); }}>清除条件</button>}
        </div>
        <QueryState loading={tasks.isLoading} error={tasks.error}>
          <div className="table-scroll">
            <table className="ledger-table patrol-ledger-table">
              <thead><tr><th>巡护任务</th><th>关联林班</th><th>责任人</th><th>计划时间</th><th>状态</th><th className="action-column">操作</th></tr></thead>
              <tbody>
                {visibleItems.map((task) => (
                  <tr className={task.deletedAt ? "deleted-row" : ""} key={task.id} onClick={() => setSelected(task)}>
                    <td><strong>{task.name}</strong><small>{task.patrolNo} · {PRIORITY_LABELS[task.priority]}优先级</small></td>
                    <td><strong>{task.linkedBlockCodes[0] || "未关联"}</strong><small>{task.linkedBlockCodes.length > 1 ? `另有 ${task.linkedBlockCodes.length - 1} 个林班` : "空间范围"}</small></td>
                    <td><strong>{task.assigneeName || "待派发"}</strong><small>任务责任人</small></td>
                    <td><strong>{formatDateTime(task.plannedStartAt)}</strong><small>至 {formatDateTime(task.plannedEndAt)}</small></td>
                    <td><PatrolStatusBadge status={task.status} /></td>
                    <td className="action-column"><div className="row-actions"><RowAction label="查看" icon={Eye} onClick={() => setSelected(task)} />{task.deletedAt ? <RowAction label="恢复" icon={RotateCcw} disabled={!canRestore} onClick={() => restore.mutate(task.id)} /> : <><RowAction label="编辑" icon={Pencil} disabled={!canUpdate || !["planned", "assigned"].includes(task.status)} onClick={() => setEditing(task)} /><RowAction label="删除" icon={Trash2} danger disabled={!canDelete || !["planned", "assigned"].includes(task.status)} onClick={() => { if (window.confirm(`确认将“${task.name}”移入回收站？`)) remove.mutate(task.id); }} /></>}</div></td>
                  </tr>
                ))}
                {!tasks.isLoading && !visibleItems.length && <tr><td colSpan={6}><div className="table-empty"><ClipboardCheck aria-hidden="true" /><strong>当前没有巡护任务</strong><p>{q || status ? "请清除筛选条件后重试。" : "新建任务时从正式林班台账选择巡护范围。"}</p></div></td></tr>}
              </tbody>
            </table>
          </div>
          <LedgerPagination total={tasks.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
        </QueryState>
      </section>

      <SidePanel wide open={creating} eyebrow="建立巡护计划" title="新建巡护任务" onClose={() => !create.isPending && setCreating(false)}>
        <PatrolTaskForm pending={create.isPending} error={create.error} onCancel={() => setCreating(false)} onSubmit={(payload) => create.mutate(payload)} />
      </SidePanel>
      <SidePanel wide open={Boolean(editing)} eyebrow="维护巡护计划" title={editing?.name || "编辑巡护任务"} onClose={() => !update.isPending && setEditing(null)}>
        {editing && <PatrolTaskForm record={editing} pending={update.isPending} error={update.error} onCancel={() => setEditing(null)} onSubmit={(payload) => update.mutate({ id: editing.id, payload })} />}
      </SidePanel>
      <SidePanel wide open={Boolean(selected)} eyebrow="巡护任务办理" title={selected?.name || "巡护任务"} onClose={() => !action.isPending && setSelected(null)}>
        {selected && <PatrolTaskDetail task={selected} canUpdate={canUpdate} canRestore={canRestore} pending={action.isPending || restore.isPending} error={action.error || restore.error} onRestore={() => restore.mutate(selected.id)} onAction={(actionName, payload) => action.mutate({ task: selected, action: actionName, payload })} />}
      </SidePanel>
    </div>
  );
}

function PatrolTaskForm({ record, pending, error, onCancel, onSubmit }: { record?: PatrolTask; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: PatrolTaskPayload) => void }) {
  const defaults = useMemo(() => record ? { start: toLocalInput(record.plannedStartAt), end: toLocalInput(record.plannedEndAt) } : defaultSchedule(), [record]);
  const [blocks, setBlocks] = useState<ForestBlockOption[]>(() => (record?.linkedBlockCodes ?? []).map((code) => ({ id: code, code, name: code, location: "", areaMu: null, hasGeometry: false, riskLevel: null })));
  const [selectorOpen, setSelectorOpen] = useState(false);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSubmit({
      name: field(data, "name"),
      priority: field(data, "priority") as PatrolTaskPayload["priority"],
      plannedStartAt: field(data, "plannedStartAt"),
      plannedEndAt: field(data, "plannedEndAt"),
      assigneeName: field(data, "assigneeName"),
      linkedBlockCodes: blocks.map((block) => block.code),
      instructions: field(data, "instructions"),
    });
  };
  const addBlock = (block: ForestBlockOption) => setBlocks((current) => current.some((item) => item.id === block.id) ? current : [...current, block]);
  return <>
    <form className="entity-form patrol-create-form" onSubmit={submit}>
      <fieldset className="form-section"><legend>任务信息</legend><p>新建后按是否填写责任人进入“待派发”或“待接单”。</p><div className="form-grid">
        <label className="field-span"><span>任务名称<em>*</em></span><input name="name" required defaultValue={record?.name || ""} placeholder="例如：上屯村毛竹林日常巡护" /></label>
        <label><span>优先级<em>*</em></span><select name="priority" defaultValue={record?.priority || "normal"}><option value="low">低</option><option value="normal">普通</option><option value="high">高</option><option value="urgent">紧急</option></select></label>
        <label><span>责任人 / 班组</span><input name="assigneeName" defaultValue={record?.assigneeName || ""} placeholder="暂不填写则保存为待派发" /></label>
        <label><span>计划开始<em>*</em></span><input name="plannedStartAt" type="datetime-local" required defaultValue={defaults.start} /></label>
        <label><span>计划结束<em>*</em></span><input name="plannedEndAt" type="datetime-local" required defaultValue={defaults.end} /></label>
      </div></fieldset>
      <fieldset className="form-section"><legend>空间范围</legend><p>必须从正式林班台账选择，不允许自由输入编号。</p><div className="relation-toolbar"><button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}><MapPin aria-hidden="true" />选择林班</button><span>已选择 {blocks.length} 个</span></div><div className="relation-chips">{blocks.map((block) => <span key={block.id}><strong>{block.name}</strong><small>{block.code}</small><button type="button" aria-label={`移除 ${block.name}`} onClick={() => setBlocks((current) => current.filter((item) => item.id !== block.id))}><X aria-hidden="true" /></button></span>)}{!blocks.length && <p>尚未选择巡护林班</p>}</div></fieldset>
      <fieldset className="form-section"><legend>巡护要求</legend><p>说明本次需要重点检查的事项。</p><div className="form-grid"><label className="field-span"><span>任务说明</span><textarea name="instructions" rows={5} defaultValue={record?.instructions || ""} placeholder="例如：检查防火通道、盗伐迹象和病虫害风险点。" /></label></div></fieldset>
      {error && <p className="form-error">{error.message}</p>}
      <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={pending || !blocks.length}>{pending ? "保存中" : record ? "保存修改" : "创建任务"}</button></div>
    </form>
    <ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={addBlock} />
  </>;
}

function PatrolTaskDetail({ task, canUpdate, canRestore, pending, error, onRestore, onAction }: { task: PatrolTask; canUpdate: boolean; canRestore: boolean; pending: boolean; error: Error | null; onRestore: () => void; onAction: (action: string, payload?: PatrolActionPayload) => void }) {
  const report = task.report ?? { summary: "", issueType: "", issueLevel: "", locationText: "", reportedBy: "", reportedAt: "" };
  const disposition = task.disposition ?? { summary: "", result: "", attachmentIds: [], resolvedBy: "", resolvedAt: "" };
  const attachments = task.attachments ?? [];
  const timeline = task.timeline ?? [];
  return <div className="patrol-detail">
    <div className="patrol-detail-header"><div><small>{task.patrolNo}</small><PatrolStatusBadge status={task.status} /></div><strong>{PRIORITY_LABELS[task.priority]}优先级</strong></div>
    <ol className="patrol-progress" aria-label="巡护办理进度">{STATUS_ORDER.map((status, index) => { const current = STATUS_ORDER.indexOf(task.status); return <li className={index < current ? "done" : index === current ? "current" : "pending"} key={status}><span>{index < current ? <CheckCircle2 aria-hidden="true" /> : index + 1}</span><small>{STATUS_LABELS[status]}</small></li>; })}</ol>
    <section className="detail-group"><h3>任务安排</h3><dl><Detail label="责任人" value={task.assigneeName} /><Detail label="计划开始" value={formatDateTime(task.plannedStartAt)} /><Detail label="计划结束" value={formatDateTime(task.plannedEndAt)} /><Detail label="巡护要求" value={task.instructions} /></dl></section>
    <section className="detail-group"><h3>关联林班</h3><div className="detail-relations">{task.linkedBlockCodes.map((code) => <span key={code}><MapPin aria-hidden="true" />{code}</span>)}</div></section>
    {report.summary && <section className="patrol-report-card"><span className="eyebrow">现场报告</span><h3>{report.summary}</h3><dl><Detail label="问题类型" value={report.issueType} /><Detail label="问题等级" value={report.issueLevel} /><Detail label="问题位置" value={report.locationText} /><Detail label="上报人" value={report.reportedBy} /></dl></section>}
    {disposition.summary && <section className="patrol-report-card"><span className="eyebrow">问题处置</span><h3>{disposition.summary}</h3><dl><Detail label="处置结果" value={disposition.result} /><Detail label="处置人" value={disposition.resolvedBy} /><Detail label="处置时间" value={formatDateTime(disposition.resolvedAt || "")} /></dl></section>}
    <section className="detail-group"><h3>现场证据</h3><div className="attachment-link-list">{attachments.map((attachment) => <a key={attachment.id} href={attachment.downloadUrl || undefined}><Paperclip aria-hidden="true" /><span><strong>{attachment.originalName}</strong><small>{attachment.category} · {attachment.sha256.slice(0, 12)}</small></span><Download aria-hidden="true" /></a>)}{!attachments.length && <p className="muted-copy">尚未关联照片或文档证据。</p>}</div></section>
    {task.deletedAt ? <div className="permission-note"><Trash2 aria-hidden="true" /><span><strong>任务已移入回收站</strong><small>恢复后可继续维护。</small></span>{canRestore && <button className="button secondary" type="button" disabled={pending} onClick={onRestore}><RotateCcw aria-hidden="true" />恢复任务</button>}</div> : canUpdate && task.status !== "closed" && <PatrolNextAction task={task} pending={pending} onAction={onAction} />}
    {!canUpdate && task.status !== "closed" && <div className="permission-note"><ShieldCheck aria-hidden="true" /><span><strong>当前账号仅可查看</strong><small>办理按钮会根据角色操作权限显示。</small></span></div>}
    {error && <p className="form-error">{error.message}</p>}
    <section className="patrol-timeline"><div className="section-heading"><div><span className="eyebrow">全程留痕</span><h3>任务时间轴</h3></div></div>{[...timeline].reverse().map((item) => <div className="timeline-entry" key={item.id}><span><Clock3 aria-hidden="true" /></span><div><strong>{item.label}</strong><small>{item.actor} · {formatDateTime(item.at)}</small>{item.note && <p>{item.note}</p>}</div></div>)}</section>
  </div>;
}

function PatrolNextAction({ task, pending, onAction }: { task: PatrolTask; pending: boolean; onAction: (action: string, payload?: PatrolActionPayload) => void }) {
  if (task.status === "assigned") return <ActionCard title="接收任务" detail="确认后任务进入待出发状态。"><button className="button primary" type="button" disabled={pending} onClick={() => onAction("accept")}><ClipboardCheck aria-hidden="true" />确认接单</button></ActionCard>;
  if (task.status === "accepted") return <ActionCard title="开始巡护" detail="到达现场后开始记录本次巡护过程。"><button className="button primary" type="button" disabled={pending} onClick={() => onAction("start")}><Play aria-hidden="true" />开始巡护</button></ActionCard>;
  if (task.status === "verified") return <ActionCard title="归档任务" detail="复核已经通过，归档后任务进入已完成。"><button className="button primary" type="button" disabled={pending} onClick={() => onAction("close")}><CheckCircle2 aria-hidden="true" />完成归档</button></ActionCard>;
  if (task.status === "planned") return <ActionForm title="派发任务" detail="指定责任人后进入待接单。" pending={pending} submitLabel="派发任务" icon={Send} fields={<label><span>责任人 / 班组<em>*</em></span><input name="assigneeName" required /></label>} onSubmit={(data) => onAction("assign", { assigneeName: field(data, "assigneeName"), note: field(data, "note") })} />;
  if (task.status === "patrolling") return <PatrolReportAction task={task} pending={pending} onAction={onAction} />;
  if (task.status === "reported" && !["", "none"].includes(task.report?.issueType || "none")) return <PatrolResolveAction task={task} pending={pending} onAction={onAction} />;
  if (["reported", "resolved"].includes(task.status)) return <ActionForm title="复核现场结果" detail="通过后进入待归档；不通过退回巡护中。" pending={pending} submitLabel="复核通过" icon={ShieldCheck} secondaryLabel="退回补充" fields={<label className="field-span"><span>复核意见</span><textarea name="note" rows={3} placeholder="退回时必须填写原因" /></label>} onSubmit={(data) => onAction("verify", { note: field(data, "note") })} onSecondary={(data) => onAction("return", { note: field(data, "note") })} />;
  return null;
}

function PatrolReportAction({ task, pending, onAction }: { task: PatrolTask; pending: boolean; onAction: (action: string, payload?: PatrolActionPayload) => void }) {
  const [attachments, setAttachments] = useState<AttachmentRecord[]>(task.attachments ?? []);
  const [selectorOpen, setSelectorOpen] = useState(false);
  useEffect(() => setAttachments(task.attachments ?? []), [task.id, task.attachments]);
  return <><ActionForm title="上报现场结果" detail="填写巡护结论，并从附件中心关联现场照片或文档。" pending={pending} submitLabel="提交结果" icon={Send} fields={<><label className="field-span"><span>巡护结论<em>*</em></span><textarea name="summary" rows={3} required /></label><label><span>问题类型</span><select name="issueType" defaultValue="none"><option value="none">未发现问题</option><option value="fire-risk">火险</option><option value="theft">盗伐</option><option value="pest">病虫害</option><option value="road">道路设施</option><option value="other">其他</option></select></label><label><span>问题等级</span><select name="issueLevel" defaultValue="low"><option value="low">低</option><option value="medium">中</option><option value="high">高</option></select></label><label className="field-span"><span>问题位置</span><input name="locationText" placeholder="例如：林班东侧作业道附近" /></label><EvidenceField attachments={attachments} onOpen={() => setSelectorOpen(true)} onRemove={(id) => setAttachments((items) => items.filter((item) => item.id !== id))} /></>} onSubmit={(data) => onAction("report", { summary: field(data, "summary"), issueType: field(data, "issueType"), issueLevel: field(data, "issueLevel"), locationText: field(data, "locationText"), attachmentIds: attachments.map((item) => item.id) })} /><AttachmentSelector open={selectorOpen} selectedIds={attachments.map((item) => item.id)} category="patrol_evidence" title="选择巡护现场证据" onClose={() => setSelectorOpen(false)} onChange={setAttachments} /></>;
}

function PatrolResolveAction({ task, pending, onAction }: { task: PatrolTask; pending: boolean; onAction: (action: string, payload?: PatrolActionPayload) => void }) {
  const [attachments, setAttachments] = useState<AttachmentRecord[]>(task.attachments ?? []);
  const [selectorOpen, setSelectorOpen] = useState(false);
  return <><ActionForm title="完成问题处置" detail="记录处置措施和结果，完成后提交复核。" pending={pending} submitLabel="完成处置" icon={CheckCircle2} secondaryLabel="退回补充" fields={<><label className="field-span"><span>处置说明<em>*</em></span><textarea name="dispositionSummary" rows={3} required placeholder="说明采取了哪些措施" /></label><label className="field-span"><span>处置结果<em>*</em></span><textarea name="dispositionResult" rows={3} required placeholder="说明现场问题是否消除、后续是否需要跟踪" /></label><EvidenceField attachments={attachments} onOpen={() => setSelectorOpen(true)} onRemove={(id) => setAttachments((items) => items.filter((item) => item.id !== id))} /></>} onSubmit={(data) => onAction("resolve", { dispositionSummary: field(data, "dispositionSummary"), dispositionResult: field(data, "dispositionResult"), attachmentIds: attachments.map((item) => item.id) })} onSecondary={(data) => onAction("return", { note: field(data, "dispositionSummary") || "退回补充巡护信息" })} /><AttachmentSelector open={selectorOpen} selectedIds={attachments.map((item) => item.id)} category="patrol_disposition" title="选择问题处置证据" onClose={() => setSelectorOpen(false)} onChange={setAttachments} /></>;
}

function EvidenceField({ attachments, onOpen, onRemove }: { attachments: AttachmentRecord[]; onOpen: () => void; onRemove: (id: string) => void }) {
  return <div className="field-span relation-section"><div className="relation-toolbar"><span>已关联 {attachments.length} 项证据</span><button className="button secondary" type="button" onClick={onOpen}><Paperclip aria-hidden="true" />选择附件</button></div><div className="relation-list">{attachments.map((attachment) => <div className="relation-chip" key={attachment.id}><span><strong>{attachment.originalName}</strong><small>{attachment.category} · {attachment.sha256.slice(0, 12)}</small></span><button type="button" aria-label={`移除 ${attachment.originalName}`} onClick={() => onRemove(attachment.id)}><X aria-hidden="true" /></button></div>)}{!attachments.length && <p className="relation-empty">暂无现场证据，可直接从附件中心选择或上传。</p>}</div></div>;
}

function ActionForm({ title, detail, fields, pending, submitLabel, secondaryLabel, icon: Icon, onSubmit, onSecondary }: { title: string; detail: string; fields: ReactNode; pending: boolean; submitLabel: string; secondaryLabel?: string; icon: typeof Send; onSubmit: (data: FormData) => void; onSecondary?: (data: FormData) => void }) {
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); onSubmit(new FormData(event.currentTarget)); };
  return <form className="patrol-action-card" onSubmit={submit}><div><span className="eyebrow">当前可办</span><h3>{title}</h3><p>{detail}</p></div><div className="form-grid">{fields}</div><div className="form-actions">{secondaryLabel && <button className="button secondary" type="button" disabled={pending} onClick={(event) => onSecondary?.(new FormData(event.currentTarget.form!))}><RotateCcw aria-hidden="true" />{secondaryLabel}</button>}<button className="button primary" type="submit" disabled={pending}><Icon aria-hidden="true" />{pending ? "处理中" : submitLabel}</button></div></form>;
}
function ActionCard({ title, detail, children }: { title: string; detail: string; children: ReactNode }) { return <section className="patrol-action-card"><div><span className="eyebrow">当前可办</span><h3>{title}</h3><p>{detail}</p></div><div className="form-actions">{children}</div></section>; }
function RowAction({ label, icon: Icon, disabled = false, danger = false, onClick }: { label: string; icon: typeof Eye; disabled?: boolean; danger?: boolean; onClick: () => void }) { return <button className={`icon-button ${danger ? "danger" : ""}`} type="button" disabled={disabled} aria-label={label} title={label} onClick={(event) => { event.stopPropagation(); onClick(); }}><Icon aria-hidden="true" /></button>; }
function PatrolStatusBadge({ status }: { status: PatrolStatus }) { const tone = status === "closed" ? "success" : ["reported", "resolved"].includes(status) ? "warning" : status === "patrolling" ? "active" : "neutral"; return <span className={`patrol-status ${tone}`}>{STATUS_LABELS[status]}</span>; }
function SummaryMetric({ label, value, detail, tone = "neutral" }: { label: string; value: number; detail: string; tone?: "neutral" | "warning" }) { return <div className={tone}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function Detail({ label, value }: { label: string; value: unknown }) { const text = String(value ?? "").trim() || "未填写"; return <div><dt>{label}</dt><dd>{text}</dd></div>; }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
function toLocalInput(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value.slice(0, 16) : localInput(date); }
function localInput(date: Date) { const offset = date.getTimezoneOffset() * 60_000; return new Date(date.getTime() - offset).toISOString().slice(0, 16); }
function defaultSchedule() { const start = new Date(); start.setMinutes(Math.ceil(start.getMinutes() / 30) * 30, 0, 0); const end = new Date(start.getTime() + 4 * 60 * 60 * 1000); return { start: localInput(start), end: localInput(end) }; }
