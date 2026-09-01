import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  AlertTriangle,
  BadgeCheck,
  Clock3,
  DatabaseZap,
  Download,
  Eye,
  FileUp,
  MapPinned,
  Pencil,
  Plane,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Route,
  Search,
  Trash2,
  UserRoundCheck,
  X,
} from "lucide-react";
import { type FormEvent, useDeferredValue, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  AttachmentRecord,
  DroneMission,
  DroneMissionActionPayload,
  DroneMissionPayload,
  DroneMissionStatus,
  DroneMissionType,
  ForestBlockOption,
} from "../api/types";
import { AttachmentSelector } from "../components/AttachmentSelector";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 30;
const TYPE_LABELS: Record<DroneMissionType, string> = {
  survey: "资源调查",
  patrol: "巡护巡查",
  mapping: "航测建模",
  pest: "病虫害巡检",
  fire: "森林防火",
  delivery: "物资运输",
  other: "其他任务",
};
const STATUS_LABELS: Record<DroneMissionStatus, string> = {
  planned: "待安排",
  assigned: "已派发",
  flying: "飞行中",
  processing: "成果处理中",
  reviewed: "待归档",
  completed: "已完成",
  cancelled: "已取消",
};

export function DroneMissionsPage() {
  const client = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<DroneMission | null>(null);
  const [editing, setEditing] = useState<DroneMission | null>(null);
  const deferredQ = useDeferredValue(q);
  const ledger = useQuery({
    queryKey: ["v2-drone-missions", deferredQ, status, includeDeleted, offset],
    queryFn: () => api.droneMissions({ q: deferredQ, status, includeDeleted, limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const permissions = capabilities.data?.permissions;
  const roles = capabilities.data?.principal.roles;
  const canManage = hasPermission(permissions, roles, "drone.missions.manage");
  const actionPermission = {
    assign: hasPermission(permissions, roles, "drone.missions.dispatch"),
    start: hasPermission(permissions, roles, "drone.missions.operate"),
    upload: hasPermission(permissions, roles, "drone.missions.operate"),
    review: hasPermission(permissions, roles, "drone.missions.review"),
  };
  const createMission = useMutation({ mutationFn: api.createDroneMission, onSuccess: async (record) => { setCreating(false); setSelected(record); await invalidate(client); } });
  const updateMission = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: DroneMissionPayload }) => api.updateDroneMission(id, payload), onSuccess: async (record) => { setEditing(null); setSelected(record); await invalidate(client); } });
  const deleteMission = useMutation({ mutationFn: api.deleteDroneMission, onSuccess: async () => { setSelected(null); setEditing(null); await invalidate(client); } });
  const restoreMission = useMutation({ mutationFn: api.restoreDroneMission, onSuccess: async (record) => { setSelected(record); await invalidate(client); } });
  const transition = useMutation({ mutationFn: ({ id, action, payload }: { id: string; action: string; payload: DroneMissionActionPayload }) => api.applyDroneMissionAction(id, action, payload), onSuccess: async (record) => { setSelected(record); await invalidate(client); } });
  const syncTrajectories = useMutation({ mutationFn: api.syncTrajectoryMissions, onSuccess: async (result) => { await invalidate(client); window.alert(`轨迹台账同步完成：新增 ${result.created} 项，补充 ${result.updated} 项，已存在 ${result.existing} 项${result.failed ? `，失败 ${result.failed} 项` : ""}。`); } });
  const items = ledger.data?.items ?? [];
  const metrics = useMemo(() => ({
    total: ledger.data?.total ?? 0,
    pending: items.filter((item) => item.status === "planned" || item.status === "assigned").length,
    active: items.filter((item) => item.status === "flying" || item.status === "processing").length,
    completed: items.filter((item) => item.status === "completed").length,
  }), [items, ledger.data?.total]);

  return <div className="standard-page ledger-page drone-page">
    <section className="page-heading ledger-heading">
      <div><span className="eyebrow">低空作业 / 任务全过程</span><h1>无人机任务</h1><p>以正式无人机和林班为依据，管理计划、派发、飞行、成果、复核与归档。</p></div>
      <div className="heading-actions"><a className="button secondary" href={`/api/v2/drone/missions-export.csv?q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}`}><Download aria-hidden="true" />导出</a><button className="button secondary" type="button" disabled={!canManage || syncTrajectories.isPending} onClick={() => { if (window.confirm("扫描已确认覆盖的空间成果，并按 DJI Terra 轨迹目录补建历史飞行任务台账？同一航次不会重复创建。")) syncTrajectories.mutate(); }}><DatabaseZap aria-hidden="true" />{syncTrajectories.isPending ? "正在同步" : "同步轨迹台账"}</button><button className="button secondary" type="button" onClick={() => ledger.refetch()}><RefreshCw aria-hidden="true" />刷新</button><button className="button primary" type="button" disabled={!canManage} onClick={() => setCreating(true)}><Plus aria-hidden="true" />新建任务</button></div>
    </section>
    <section className="domain-summary-strip"><Summary label="任务总数" value={metrics.total} detail="正式飞行任务" /><Summary label="待执行" value={metrics.pending} detail="待安排或已派发" tone="warning" /><Summary label="执行中" value={metrics.active} detail="飞行或成果处理" tone="active" /><Summary label="已归档" value={metrics.completed} detail="本页已完成任务" /></section>
    <section className="ledger-shell">
      <div className="ledger-toolbar domain-ledger-toolbar"><label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索任务编号、标题、无人机或飞手" /></label><label className="compact-filter"><span>任务状态</span><select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}><option value="">全部状态</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label className="deleted-toggle"><input type="checkbox" checked={includeDeleted} onChange={(event) => { setIncludeDeleted(event.target.checked); setOffset(0); }} /><span>显示已删除</span></label>{(q || status) && <button className="text-button" type="button" onClick={() => { setQ(""); setStatus(""); setOffset(0); }}>清除条件</button>}</div>
      <QueryState loading={ledger.isLoading} error={ledger.error}><div className="table-scroll"><table className="ledger-table drone-ledger-table"><thead><tr><th>任务档案</th><th>设备与飞手</th><th>目标林班</th><th>计划窗口</th><th>任务状态</th><th className="action-column">操作</th></tr></thead><tbody>{items.map((record) => <tr className={record.deletedAt ? "is-deleted" : ""} key={record.id} onClick={() => setSelected(record)}><td><strong>{record.title}</strong><small>{record.missionNo} · {TYPE_LABELS[record.missionType]}{record.flightSummary?.recordOrigin === "trajectory-auto-import" ? " · 轨迹自动导入" : ""}</small></td><td><strong>{record.deviceName || "无人机待补"}</strong><small>{record.pilotName || (record.flightSummary?.recordOrigin === "trajectory-auto-import" ? "飞手待补" : "飞手待派发")}{record.routeName ? ` · ${record.routeName}` : ""}</small></td><td><strong>{record.blocks.map((item) => item.code).join("、") || "未关联林班"}</strong><small>{record.blocks.length} 个空间作业单元</small></td><td><strong>{record.plannedStartAt ? formatDateTime(record.plannedStartAt) : "历史航次待补"}</strong><small>{record.plannedEndAt ? `至 ${formatDateTime(record.plannedEndAt)}` : "未虚构计划时间"}</small></td><td>{record.deletedAt ? <span className="status-badge deleted"><i />已删除</span> : <StatusBadge status={record.status} />}</td><td className="action-column"><div className="row-actions"><button className="icon-button" type="button" title="查看" aria-label="查看任务" onClick={(event) => { event.stopPropagation(); setSelected(record); }}><Eye aria-hidden="true" /></button>{record.deletedAt ? <button className="icon-button" type="button" title="恢复" aria-label="恢复任务" disabled={!canManage || restoreMission.isPending} onClick={(event) => { event.stopPropagation(); restoreMission.mutate(record.id); }}><RotateCcw aria-hidden="true" /></button> : <><button className="icon-button" type="button" title="编辑" aria-label="编辑任务" disabled={!canManage || record.status !== "planned"} onClick={(event) => { event.stopPropagation(); setEditing(record); }}><Pencil aria-hidden="true" /></button><button className="icon-button danger-copy" type="button" title="删除" aria-label="删除任务" disabled={!canManage || !["planned", "cancelled"].includes(record.status) || deleteMission.isPending} onClick={(event) => { event.stopPropagation(); if (window.confirm(`确认将任务“${record.title}”移入回收站吗？`)) deleteMission.mutate(record.id); }}><Trash2 aria-hidden="true" /></button></>}</div></td></tr>)}{!ledger.isLoading && !items.length && <tr className="empty-row"><td colSpan={6}><div className="table-empty"><Plane aria-hidden="true" /><strong>当前没有无人机任务</strong><p>先在设备台账登记无人机，再建立与正式林班关联的飞行任务。</p></div></td></tr>}</tbody></table></div></QueryState>
      <LedgerPagination total={ledger.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
    </section>
    <SidePanel wide open={creating} eyebrow="无人机任务" title="新建任务" onClose={() => !createMission.isPending && setCreating(false)}><MissionForm pending={createMission.isPending} error={createMission.error} onCancel={() => setCreating(false)} onSubmit={(payload) => createMission.mutate(payload)} /></SidePanel>
    <SidePanel wide open={Boolean(editing)} eyebrow="无人机任务" title={`编辑 ${editing?.missionNo || "任务"}`} onClose={() => !updateMission.isPending && setEditing(null)}>{editing && <MissionForm initial={editing} pending={updateMission.isPending} error={updateMission.error} onCancel={() => setEditing(null)} onSubmit={(payload) => updateMission.mutate({ id: editing.id, payload })} />}</SidePanel>
    <SidePanel wide open={Boolean(selected)} eyebrow="任务全过程" title={selected?.title || "任务详情"} onClose={() => !transition.isPending && setSelected(null)}>{selected && <MissionDetail record={selected} permissions={actionPermission} pending={transition.isPending} error={transition.error} onAction={(action, payload) => transition.mutate({ id: selected.id, action, payload })} />}</SidePanel>
  </div>;
}

function MissionForm({ initial, pending, error, onCancel, onSubmit }: { initial?: DroneMission; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: DroneMissionPayload) => void }) {
  const devices = useQuery({ queryKey: ["v2-iot-device-options", "drone"], queryFn: () => api.iotDeviceOptions("drone") });
  const [blocks, setBlocks] = useState<ForestBlockOption[]>(initial?.blocks.map((item) => ({ id: item.id, code: item.code, name: item.code, location: "", areaMu: null, hasGeometry: false, riskLevel: null })) ?? []);
  const [selectorOpen, setSelectorOpen] = useState(false);
  if (devices.isLoading) return <div className="panel-loading" role="status">正在加载无人机台账</div>;
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); onSubmit({ title: field(data, "title"), missionType: field(data, "missionType") as DroneMissionType, droneDeviceId: field(data, "droneDeviceId"), plannedStartAt: field(data, "plannedStartAt"), plannedEndAt: field(data, "plannedEndAt"), linkedBlockCodes: blocks.map((item) => item.code), objective: field(data, "objective") }); };
  return <><form className="entity-form" onSubmit={submit}><fieldset className="form-section"><legend>任务计划</legend><div className="form-grid"><label className="field-span"><span>任务名称<em>*</em></span><input name="title" required defaultValue={initial?.title} /></label><label><span>任务类型<em>*</em></span><select name="missionType" defaultValue={initial?.missionType || "survey"}>{Object.entries(TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>执行无人机<em>*</em></span><select name="droneDeviceId" required defaultValue={initial?.droneDeviceId || ""}><option value="">请选择设备台账中的无人机</option>{devices.data?.items.map((device) => <option value={device.id} key={device.id}>{device.name} · {device.deviceCode}{device.connectivityStatus === "offline" ? "（离线）" : ""}</option>)}</select></label><label><span>计划开始<em>*</em></span><input type="datetime-local" name="plannedStartAt" required defaultValue={localTime(initial?.plannedStartAt)} /></label><label><span>计划结束<em>*</em></span><input type="datetime-local" name="plannedEndAt" required defaultValue={localTime(initial?.plannedEndAt)} /></label><label className="field-span"><span>任务目标</span><textarea name="objective" rows={3} defaultValue={initial?.objective} /></label></div></fieldset><fieldset className="form-section"><legend>空间范围</legend><div className="relation-toolbar"><div><strong>目标林班<em>*</em></strong><small>至少选择一个正式林班，任务成果将沿此关系回写。</small></div><button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}><MapPinned aria-hidden="true" />从林班台账选择</button></div><div className="relation-chips">{blocks.map((block) => <span key={block.code}><strong>{block.name}</strong><small>{block.code}</small><button type="button" onClick={() => setBlocks((items) => items.filter((item) => item.code !== block.code))} aria-label={`移除 ${block.code}`}><X aria-hidden="true" /></button></span>)}</div>{!blocks.length && <p className="form-hint">尚未选择目标林班。</p>}</fieldset>{error && <p className="form-error">{error.message}</p>}<div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" disabled={pending || !blocks.length || devices.isLoading}>{pending ? "正在保存" : "保存任务"}</button></div></form><ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => setBlocks((items) => items.some((item) => item.code === block.code) ? items : [...items, block])} /></>;
}

function MissionDetail({ record, permissions, pending, error, onAction }: { record: DroneMission; permissions: { assign: boolean; start: boolean; upload: boolean; review: boolean }; pending: boolean; error: Error | null; onAction: (action: string, payload: DroneMissionActionPayload) => void }) {
  const controlledAssets = record.resultAttachments ?? [];
  const legacyAssets = record.resultAssetUrls ?? [];
  const imported = record.flightSummary?.recordOrigin === "trajectory-auto-import";
  const missingFields = Array.isArray(record.flightSummary?.missingFields) ? record.flightSummary.missingFields.map(String) : [];
  return <div className="domain-detail">{imported && <section className="domain-action-card"><AlertTriangle aria-hidden="true" /><div><strong>由 DJI Terra 轨迹自动建立的历史台账</strong><small>已保留真实轨迹及林班关系，没有虚构设备、飞手或飞行时间。待补：{missingFields.map(missingFieldLabel).join("、") || "完整飞行日志"}。</small></div></section>}<section className="detail-group"><div className="detail-title-row"><h3>任务信息</h3><StatusBadge status={record.status} /></div><dl><Fact label="任务编号" value={record.missionNo} /><Fact label="任务类型" value={TYPE_LABELS[record.missionType]} /><Fact label="执行无人机" value={[record.deviceName, record.deviceCode].filter(Boolean).join(" · ")} /><Fact label="飞手" value={record.pilotName} /><Fact label="航线" value={record.routeName} /><Fact label="计划窗口" value={record.plannedStartAt ? `${formatDateTime(record.plannedStartAt)} 至 ${formatDateTime(record.plannedEndAt)}` : "历史导入，待补"} /><Fact label="实际飞行" value={record.actualStartAt ? `${formatDateTime(record.actualStartAt)} 至 ${record.actualEndAt ? formatDateTime(record.actualEndAt) : "进行中"}` : imported ? "待从原始飞行日志提取" : "尚未起飞"} /><Fact label="任务目标" value={record.objective} /></dl><div className="relation-chips read-only">{record.blocks.map((item) => <span key={item.code}><strong>{item.code}</strong><small>正式目标林班</small></span>)}</div></section><MissionActionCard record={record} permissions={permissions} pending={pending} onAction={onAction} />{error && <p className="form-error">{error.message}</p>}<section className="detail-group"><h3>成果资产</h3>{controlledAssets.length ? <div className="asset-list">{controlledAssets.map((asset) => <a href={asset.downloadUrl || undefined} target="_blank" rel="noreferrer" key={asset.id}><FileUp aria-hidden="true" /><span><strong>{asset.originalName}</strong><small>{formatBytes(asset.sizeBytes)} · SHA-256 {asset.sha256.slice(0, 12)}</small></span></a>)}</div> : legacyAssets.length ? <div className="asset-list">{legacyAssets.map((url) => <a href={url} target="_blank" rel="noreferrer" key={url}><FileUp aria-hidden="true" /><span><strong>历史外部成果</strong><small>{url}</small></span></a>)}</div> : <div className="action-unavailable"><FileUp aria-hidden="true" /><span><strong>{imported ? "轨迹已关联，成果从影像台账追溯" : "暂无成果资产"}</strong><small>{imported ? `${Number(record.flightSummary?.trajectoryFileCount || 0)} 个轨迹文件 · ${Array.isArray(record.flightSummary?.trajectoryFormats) ? record.flightSummary.trajectoryFormats.join(" / ") : "POS/SBET"}` : "完成飞行后从统一附件中心提交正射影像、视频或模型成果。"}</small></span></div>}</section><section className="detail-group"><h3>任务时间线</h3><div className="domain-timeline">{record.timeline.map((item) => <article key={item.id}><i /><div><strong>{actionLabel(item.action)}</strong><small>{item.actor} · {formatDateTime(item.createdAt)}</small><p>{item.note || `${STATUS_LABELS[item.fromStatus as DroneMissionStatus] || "创建"} → ${STATUS_LABELS[item.toStatus as DroneMissionStatus] || item.toStatus}`}</p></div></article>)}</div></section></div>;
}

function MissionActionCard({ record, permissions, pending, onAction }: { record: DroneMission; permissions: { assign: boolean; start: boolean; upload: boolean; review: boolean }; pending: boolean; onAction: (action: string, payload: DroneMissionActionPayload) => void }) {
  const [resultAttachments, setResultAttachments] = useState<AttachmentRecord[]>(record.resultAttachments ?? []);
  const [attachmentSelectorOpen, setAttachmentSelectorOpen] = useState(false);
  const submit = (action: string) => (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); onAction(action, { note: field(data, "note"), pilotName: field(data, "pilotName"), routeName: field(data, "routeName"), resultAttachmentIds: action === "upload-result" ? resultAttachments.map((item) => item.id) : undefined, flightDurationMinutes: numberField(data, "flightDurationMinutes"), flightDistanceKm: numberField(data, "flightDistanceKm"), coverageAreaMu: numberField(data, "coverageAreaMu"), reviewNote: field(data, "reviewNote") }); };
  if (record.status === "completed" || record.status === "cancelled") return <section className="domain-action-card complete"><BadgeCheck aria-hidden="true" /><div><strong>{record.status === "completed" ? "任务已归档" : "任务已取消"}</strong><small>全过程记录已锁定，可继续查看成果与时间线。</small></div></section>;
  if (record.status === "planned") return <section className="domain-action-card"><form onSubmit={submit("assign")}><header><UserRoundCheck aria-hidden="true" /><div><span>下一步</span><h3>派发任务</h3></div></header><div className="form-grid"><label><span>飞手<em>*</em></span><input name="pilotName" required /></label><label><span>航线名称<em>*</em></span><input name="routeName" required /></label><label className="field-span"><span>派发说明</span><textarea name="note" rows={2} /></label></div><div className="form-actions split"><CancelButton pending={pending} allowed={permissions.assign} onAction={onAction} /><button className="button primary" disabled={pending || !permissions.assign}>确认派发</button></div></form></section>;
  if (record.status === "assigned") return <section className="domain-action-card"><form onSubmit={submit("start")}><header><Play aria-hidden="true" /><div><span>下一步</span><h3>开始飞行</h3></div></header><label><span>起飞备注</span><textarea name="note" rows={2} /></label><div className="form-actions split"><CancelButton pending={pending} allowed={permissions.start} onAction={onAction} /><button className="button primary" disabled={pending || !permissions.start}><Play aria-hidden="true" />确认起飞</button></div></form></section>;
  if (record.status === "flying") return <><section className="domain-action-card"><form onSubmit={submit("upload-result")}><header><FileUp aria-hidden="true" /><div><span>下一步</span><h3>提交飞行成果</h3></div></header><div className="relation-toolbar"><div><strong>受控成果附件<em>*</em></strong><small>从统一附件中心选择，成果会同步关联任务及其目标林班。</small></div><button className="button secondary" type="button" onClick={() => setAttachmentSelectorOpen(true)}><FileUp aria-hidden="true" />选择或上传成果</button></div><div className="relation-chips">{resultAttachments.map((asset) => <span key={asset.id}><strong>{asset.originalName}</strong><small>{formatBytes(asset.sizeBytes)} · {asset.sha256.slice(0, 12)}</small><button type="button" onClick={() => setResultAttachments((items) => items.filter((item) => item.id !== asset.id))} aria-label={`移除 ${asset.originalName}`}><X aria-hidden="true" /></button></span>)}</div>{!resultAttachments.length && <p className="form-hint">尚未选择成果附件。</p>}<div className="form-grid"><label><span>飞行时长（分钟）</span><input name="flightDurationMinutes" type="number" min="0" step="0.1" /></label><label><span>飞行距离（公里）</span><input name="flightDistanceKm" type="number" min="0" step="0.01" /></label><label><span>覆盖面积（亩）</span><input name="coverageAreaMu" type="number" min="0" step="0.01" /></label><label><span>成果说明</span><input name="note" /></label></div><div className="form-actions"><button className="button primary" disabled={pending || !permissions.upload || !resultAttachments.length}>提交成果处理</button></div></form></section><AttachmentSelector open={attachmentSelectorOpen} selectedIds={resultAttachments.map((item) => item.id)} onClose={() => setAttachmentSelectorOpen(false)} onChange={setResultAttachments} category="drone_result" title="选择飞行成果" /></>;
  if (record.status === "processing") return <section className="domain-action-card"><form onSubmit={submit("review")}><header><BadgeCheck aria-hidden="true" /><div><span>下一步</span><h3>复核飞行成果</h3></div></header><label><span>复核意见</span><textarea name="reviewNote" rows={3} /></label><div className="form-actions"><button className="button primary" disabled={pending || !permissions.review}>成果复核通过</button></div></form></section>;
  return <section className="domain-action-card"><header><Archive aria-hidden="true" /><div><span>最后一步</span><h3>归档任务</h3></div></header><div className="dual-action-forms"><form onSubmit={submit("return")}><label><span>退回原因<em>*</em></span><textarea name="note" required rows={2} /></label><button className="button secondary" disabled={pending || !permissions.review}><RotateCcw aria-hidden="true" />退回处理</button></form><form onSubmit={submit("complete")}><label><span>归档说明</span><textarea name="note" rows={2} /></label><button className="button primary" disabled={pending || !permissions.review}><Archive aria-hidden="true" />完成并归档</button></form></div></section>;
}

function CancelButton({ pending, allowed, onAction }: { pending: boolean; allowed: boolean; onAction: (action: string, payload: DroneMissionActionPayload) => void }) { return <button className="text-button danger-copy" type="button" disabled={pending || !allowed} onClick={() => { const reason = window.prompt("请输入取消原因"); if (reason?.trim()) onAction("cancel", { note: reason.trim() }); }}><X aria-hidden="true" />取消任务</button>; }
function StatusBadge({ status }: { status: DroneMissionStatus }) { return <span className={`status-badge mission-status ${status}`}><i />{STATUS_LABELS[status]}</span>; }
function Summary({ label, value, detail, tone = "" }: { label: string; value: number; detail: string; tone?: string }) { return <div className={tone}><small>{label}</small><strong>{value}</strong><em>{detail}</em></div>; }
function Fact({ label, value }: { label: string; value?: string | null }) { return <div><dt>{label}</dt><dd>{value || "未填写"}</dd></div>; }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function numberField(data: FormData, name: string) { const value = field(data, name); return value ? Number(value) : undefined; }
function formatDateTime(value?: string | null) { if (!value) return "未填写"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date); }
function localTime(value?: string | null) { if (!value) return ""; const date = new Date(value); return Number.isNaN(date.getTime()) ? "" : new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16); }
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB`; }
function actionLabel(action: string) { return ({ create: "建立任务", edit: "修改计划", assign: "派发任务", start: "开始飞行", "upload-result": "提交成果", review: "成果复核", return: "退回处理", complete: "完成归档", cancel: "取消任务", "trajectory-import": "轨迹生成台账", "trajectory-link": "关联同航次成果" } as Record<string, string>)[action] || action; }
function missingFieldLabel(fieldName: string) { return ({ droneDevice: "无人机型号与序列号", pilot: "飞手", plannedWindow: "计划时间", actualWindow: "起降时间", flightStatistics: "航程/时长/电池统计", originalFlightLog: "DJI 原始飞行记录" } as Record<string, string>)[fieldName] || fieldName; }
async function invalidate(client: ReturnType<typeof useQueryClient>) { await client.invalidateQueries({ queryKey: ["v2-drone-missions"] }); }
