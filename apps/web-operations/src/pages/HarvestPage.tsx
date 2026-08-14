import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, CheckCircle2, ClipboardCheck, Clock3, Download, Eye, FileCheck2,
  MapPinned, PackageCheck, Paperclip, Pencil, Play, Plus, RefreshCw, RotateCcw,
  Search, Send, ShieldCheck, Trash2, Trees, UserRound, X,
} from "lucide-react";
import { type FormEvent, type ReactNode, useDeferredValue, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  AttachmentRecord, ForestBlockOption, ForestRightOption, HarvestActionPayload, HarvestApplication,
  HarvestApplicationPayload, HarvestQuota, HarvestStatus, HarvestSubject,
} from "../api/types";
import { AttachmentSelector } from "../components/AttachmentSelector";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { ForestRightSelector, HarvestSubjectSelector } from "../components/HarvestSelectors";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 30;
const STATUS_ORDER: HarvestStatus[] = ["draft", "submitted", "quota_check", "approving", "approved", "operating", "verifying", "completed"];
const STATUS_LABELS: Record<HarvestStatus, string> = {
  draft: "草稿", submitted: "已提交", quota_check: "配额待处理", approving: "待审批",
  approved: "已批准", operating: "作业中", verifying: "待验收", completed: "已归档",
};
const HARVEST_LABELS = { timber: "竹材采伐", shoot: "竹笋采挖", tending: "抚育采收" } as const;
const SUBJECT_LABELS = { farmer: "竹农", cooperative: "合作社", enterprise: "竹企" } as const;

export function HarvestPage() {
  const queryClient = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<HarvestApplication | null>(null);
  const [selected, setSelected] = useState<HarvestApplication | null>(null);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const deferredQ = useDeferredValue(q);
  const applications = useQuery({
    queryKey: ["v2-harvest-applications", deferredQ, status, includeDeleted, offset],
    queryFn: () => api.harvestApplications({ q: deferredQ, status, includeDeleted, limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const permissions = capabilities.data?.permissions;
  const roles = capabilities.data?.principal.roles;
  const canCreate = hasPermission(permissions, roles, "operations.harvest.create");
  const canApprove = hasPermission(permissions, roles, "operations.harvest.approve");
  const canOperate = hasPermission(permissions, roles, "operations.harvest.operate");
  const canVerify = hasPermission(permissions, roles, "operations.harvest.verify");
  const canManage = hasPermission(permissions, roles, "operations.harvest.manage");
  const create = useMutation({
    mutationFn: api.createHarvestApplication,
    onSuccess: async (record) => {
      setCreating(false);
      setSelected(record);
      await queryClient.invalidateQueries({ queryKey: ["v2-harvest-applications"] });
    },
  });
  const action = useMutation({
    mutationFn: ({ record, actionName, payload }: { record: HarvestApplication; actionName: string; payload?: HarvestActionPayload }) =>
      api.applyHarvestAction(record.id, actionName, payload),
    onSuccess: async (record) => {
      setSelected(record);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["v2-harvest-applications"] }),
        queryClient.invalidateQueries({ queryKey: ["harvest-quotas"] }),
        queryClient.invalidateQueries({ queryKey: ["workspace-summary"] }),
      ]);
    },
  });
  const update = useMutation({
    mutationFn: ({ record, payload }: { record: HarvestApplication; payload: HarvestApplicationPayload }) =>
      api.updateHarvestApplication(record.id, payload),
    onSuccess: async (record) => {
      setEditing(null);
      setSelected(record);
      await queryClient.invalidateQueries({ queryKey: ["v2-harvest-applications"] });
    },
  });
  const remove = useMutation({
    mutationFn: api.deleteHarvestApplication,
    onSuccess: async (record) => {
      if (selected?.id === record.id) setSelected(null);
      await queryClient.invalidateQueries({ queryKey: ["v2-harvest-applications"] });
    },
  });
  const restore = useMutation({
    mutationFn: api.restoreHarvestApplication,
    onSuccess: async (record) => {
      setSelected(record);
      await queryClient.invalidateQueries({ queryKey: ["v2-harvest-applications"] });
    },
  });
  const items = applications.data?.items ?? [];
  const summary = useMemo(() => ({
    review: items.filter((item) => item.status === "approving").length,
    operation: items.filter((item) => item.status === "operating").length,
    verification: items.filter((item) => item.status === "verifying").length,
  }), [items]);

  return <div className="standard-page ledger-page harvest-page">
    <section className="page-heading ledger-heading"><div><span className="eyebrow">生产运营 / 采伐监管</span><h1>采伐办理</h1><p>把主体、权属、林班、配额、审批、作业围栏和验收归档收进同一条可追溯业务链。</p></div><div className="heading-actions"><button className="button secondary" type="button" onClick={() => applications.refetch()}><RefreshCw aria-hidden="true" />刷新</button><a className="button secondary" href={`/api/v2/harvest/applications-export.csv?${new URLSearchParams({ q, status }).toString()}`}><Download aria-hidden="true" />导出台账</a><button className="button primary" type="button" disabled={!canCreate} onClick={() => setCreating(true)} title={canCreate ? "新建采伐申请" : "当前角色无申请权限"}><Plus aria-hidden="true" />新建申请</button></div></section>

    <section className="harvest-summary-strip" aria-label="当前页采伐摘要">
      <SummaryMetric label="申请总数" value={applications.data?.total ?? 0} detail="当前筛选结果" />
      <SummaryMetric label="待审批" value={summary.review} detail="权属与配额已校验" />
      <SummaryMetric label="作业中" value={summary.operation} detail="围栏与时间窗已启用" tone="active" />
      <SummaryMetric label="待验收" value={summary.verification} detail="等待现场核验归档" tone="warning" />
    </section>

    <section className="ledger-shell">
      <div className="ledger-toolbar"><label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索申请编号、名称或经营主体" /></label><label className="compact-filter"><span>办理状态</span><select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}><option value="">全部状态</option>{STATUS_ORDER.map((value) => <option value={value} key={value}>{STATUS_LABELS[value]}</option>)}</select></label>{canManage && <label className="compact-check"><input type="checkbox" checked={includeDeleted} onChange={(event) => { setIncludeDeleted(event.target.checked); setOffset(0); }} />显示已删除</label>}{(q || status || includeDeleted) && <button className="text-button" type="button" onClick={() => { setQ(""); setStatus(""); setIncludeDeleted(false); setOffset(0); }}>清除条件</button>}</div>
      <QueryState loading={applications.isLoading} error={applications.error}><div className="table-scroll"><table className="ledger-table harvest-ledger-table"><thead><tr><th>采伐申请</th><th>申请主体</th><th>空间与面积</th><th>计划作业期</th><th>办理状态</th><th className="action-column">操作</th></tr></thead><tbody>
        {items.map((record) => <tr className={record.deletedAt ? "is-deleted" : ""} key={record.id} onClick={() => setSelected(record)}><td><strong>{record.name}</strong><small>{record.applicationNo} · {HARVEST_LABELS[record.harvestType]}</small></td><td><strong>{record.applicantName}</strong><small>{SUBJECT_LABELS[record.applicantType]}</small></td><td><strong>{record.requestedAreaMu} 亩</strong><small>{record.blocks[0]?.code || "未关联林班"}{record.blocks.length > 1 ? ` 等 ${record.blocks.length} 个` : ""}</small></td><td><strong>{formatDate(record.workStartAt)}</strong><small>至 {formatDate(record.workEndAt)}</small></td><td>{record.deletedAt ? <span className="harvest-status neutral">已删除</span> : <HarvestStatusBadge status={record.status} />}</td><td className="action-column"><div className="row-actions"><RowAction label="查看" icon={Eye} onClick={() => setSelected(record)} />{record.deletedAt ? <RowAction label="恢复" icon={RotateCcw} disabled={!canManage} onClick={() => restore.mutate(record.id)} /> : <><RowAction label="编辑" icon={Pencil} disabled={!canCreate || record.status !== "draft"} onClick={() => setEditing(record)} /><RowAction label="删除" icon={Trash2} danger disabled={!canManage || record.status !== "draft"} onClick={() => { if (window.confirm(`确认将“${record.name}”移入回收站？`)) remove.mutate(record.id); }} /></>}</div></td></tr>)}
        {!applications.isLoading && !items.length && <tr><td colSpan={6}><div className="table-empty"><Trees aria-hidden="true" /><strong>当前没有采伐申请</strong><p>{q || status ? "请清除筛选条件后重试。" : "新建申请时从正式主体、林权和林班台账建立关联。"}</p></div></td></tr>}
      </tbody></table></div><LedgerPagination total={applications.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} /></QueryState>
    </section>

    <SidePanel wide open={creating} eyebrow="采伐业务申请" title="新建采伐申请" onClose={() => !create.isPending && setCreating(false)}><HarvestApplicationForm pending={create.isPending} error={create.error} onCancel={() => setCreating(false)} onSubmit={(payload) => create.mutate(payload)} /></SidePanel>
    <SidePanel wide open={Boolean(editing)} eyebrow="采伐申请维护" title={editing?.name || "编辑采伐申请"} onClose={() => !update.isPending && setEditing(null)}>{editing && <HarvestApplicationForm record={editing} pending={update.isPending} error={update.error} onCancel={() => setEditing(null)} onSubmit={(payload) => update.mutate({ record: editing, payload })} />}</SidePanel>
    <SidePanel wide open={Boolean(selected)} eyebrow="采伐全过程办理" title={selected?.name || "采伐申请"} onClose={() => !action.isPending && setSelected(null)}>{selected && <HarvestDetail record={selected} permissions={{ create: canCreate, approve: canApprove, operate: canOperate, verify: canVerify }} pending={action.isPending} error={action.error} onAction={(actionName, payload) => action.mutate({ record: selected, actionName, payload })} />}</SidePanel>
  </div>;
}

function HarvestApplicationForm({ record, pending, error, onCancel, onSubmit }: { record?: HarvestApplication; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: HarvestApplicationPayload) => void }) {
  const defaults = useMemo(() => record ? { start: toLocalInput(record.workStartAt), end: toLocalInput(record.workEndAt) } : defaultSchedule(), [record]);
  const quotas = useQuery({ queryKey: ["harvest-quotas"], queryFn: () => api.harvestQuotas(), staleTime: 30_000 });
  const [subject, setSubject] = useState<HarvestSubject | null>(() => record ? { id: record.applicantId, type: record.applicantType, code: "", name: record.applicantName, status: "active", linkedBlockCodes: record.blocks.map((item) => item.code) } : null);
  const [blocks, setBlocks] = useState<ForestBlockOption[]>(() => record?.blocks.map((item) => ({ id: item.id, code: item.code, name: item.code, location: "", areaMu: item.declaredAreaMu, hasGeometry: true, riskLevel: null })) ?? []);
  const [rights, setRights] = useState<ForestRightOption[]>(() => record?.rights.map((item) => ({ id: item.id, code: item.archiveCode, certificateNo: "", holder: item.archiveCode, status: "active", linkedBlockCodes: record.blocks.map((block) => block.code) })) ?? []);
  const [subjectOpen, setSubjectOpen] = useState(false);
  const [blockOpen, setBlockOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!subject) return;
    const data = new FormData(event.currentTarget);
    onSubmit({
      name: field(data, "name"), applicantType: subject.type, applicantId: subject.id,
      harvestType: field(data, "harvestType") as HarvestApplication["harvestType"],
      requestedAreaMu: numberField(data, "requestedAreaMu"), requestedQuantityTon: numberField(data, "requestedQuantityTon"),
      quotaId: field(data, "quotaId"), workStartAt: field(data, "workStartAt"), workEndAt: field(data, "workEndAt"),
      purpose: field(data, "purpose"), linkedBlockCodes: blocks.map((item) => item.code), linkedRightIds: rights.map((item) => item.id),
    });
  };
  const canSubmit = Boolean(subject && blocks.length && rights.length && quotas.data?.items.length);
  return <>
    <form className="entity-form harvest-create-form" onSubmit={submit}>
      <fieldset className="form-section"><legend>申请主体</legend><p>申请人必须来自正式经营主体台账。</p><RelationPicker icon={<UserRound aria-hidden="true" />} label="经营主体" selected={subject ? `${subject.name} · ${SUBJECT_LABELS[subject.type]}` : "尚未选择申请主体"} onOpen={() => setSubjectOpen(true)} onClear={subject ? () => setSubject(null) : undefined} /></fieldset>
      <fieldset className="form-section"><legend>采伐事项</legend><p>填写申请用途、面积、数量和计划作业期。</p><div className="form-grid"><label className="field-span"><span>申请名称<em>*</em></span><input name="name" required defaultValue={record?.name} placeholder="例如：上屯村毛竹择伐申请" /></label><label><span>采伐类型<em>*</em></span><select name="harvestType" defaultValue={record?.harvestType ?? "timber"}><option value="timber">竹材采伐</option><option value="shoot">竹笋采挖</option><option value="tending">抚育采收</option></select></label><label><span>申请面积(亩)<em>*</em></span><input name="requestedAreaMu" type="number" min="0.01" step="0.01" required defaultValue={record?.requestedAreaMu} /></label><label><span>申请数量(吨)</span><input name="requestedQuantityTon" type="number" min="0" step="0.01" defaultValue={record?.requestedQuantityTon ?? 0} /></label><label><span>配额依据<em>*</em></span><select name="quotaId" required defaultValue={record?.quotaId ?? ""}><option value="" disabled>请选择有效配额</option>{(quotas.data?.items ?? []).map((quota) => <option value={quota.id} key={quota.id}>{quota.quotaYear}年 · {quota.authorityName} · 剩余 {remainingArea(quota)} 亩</option>)}</select></label><label><span>计划开始<em>*</em></span><input name="workStartAt" type="datetime-local" required defaultValue={defaults.start} /></label><label><span>计划结束<em>*</em></span><input name="workEndAt" type="datetime-local" required defaultValue={defaults.end} /></label><label className="field-span"><span>采伐用途</span><textarea name="purpose" rows={3} defaultValue={record?.purpose} placeholder="说明择伐、更新、加工供材等用途。" /></label></div></fieldset>
      <fieldset className="form-section"><legend>空间与权属</legend><p>林班和林权档案必须从正式台账选择；系统提交时自动核验覆盖关系。</p><div className="harvest-relation-grid"><RelationPicker icon={<MapPinned aria-hidden="true" />} label="采伐林班" selected={blocks.length ? `已选择 ${blocks.length} 个林班，共 ${sumArea(blocks)} 亩` : "尚未选择林班"} onOpen={() => setBlockOpen(true)} /><RelationPicker icon={<FileCheck2 aria-hidden="true" />} label="林权依据" selected={rights.length ? `已选择 ${rights.length} 份林权档案` : "尚未选择林权档案"} onOpen={() => setRightOpen(true)} /></div><div className="relation-chips">{blocks.map((block) => <span key={block.id}><strong>{block.name}</strong><small>{block.code} · {block.areaMu ?? "面积待补"} 亩</small><button type="button" aria-label={`移除 ${block.name}`} onClick={() => setBlocks((current) => current.filter((item) => item.id !== block.id))}><X aria-hidden="true" /></button></span>)}{rights.map((right) => <span className="right-chip" key={right.id}><strong>{right.holder}</strong><small>{right.code}</small><button type="button" aria-label={`移除 ${right.code}`} onClick={() => setRights((current) => current.filter((item) => item.id !== right.id))}><X aria-hidden="true" /></button></span>)}</div></fieldset>
      {error && <p className="form-error">{error.message}</p>}
      <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={pending || !canSubmit}>{pending ? "保存中" : record ? "保存修改" : "保存申请草稿"}</button></div>
    </form>
    <HarvestSubjectSelector open={subjectOpen} onClose={() => setSubjectOpen(false)} onSelect={setSubject} />
    <ForestBlockSelector open={blockOpen} onClose={() => setBlockOpen(false)} onSelect={(block) => setBlocks((current) => current.some((item) => item.id === block.id) ? current : [...current, block])} />
    <ForestRightSelector open={rightOpen} linkedBlockCode={blocks[0]?.code} onClose={() => setRightOpen(false)} onSelect={(right) => setRights((current) => current.some((item) => item.id === right.id) ? current : [...current, right])} />
  </>;
}

function HarvestDetail({ record, permissions, pending, error, onAction }: { record: HarvestApplication; permissions: { create: boolean; approve: boolean; operate: boolean; verify: boolean }; pending: boolean; error: Error | null; onAction: (action: string, payload?: HarvestActionPayload) => void }) {
  return <div className="harvest-detail">
    <div className="harvest-detail-header"><div><small>{record.applicationNo}</small><HarvestStatusBadge status={record.status} /></div><strong>{HARVEST_LABELS[record.harvestType]}</strong></div>
    <ol className="harvest-progress" aria-label="采伐办理进度">{STATUS_ORDER.map((status, index) => { const current = STATUS_ORDER.indexOf(record.status); return <li className={index < current ? "done" : index === current ? "current" : "pending"} key={status}><span>{index < current ? <CheckCircle2 aria-hidden="true" /> : index + 1}</span><small>{STATUS_LABELS[status]}</small></li>; })}</ol>
    <section className="detail-group"><h3>申请信息</h3><dl><Detail label="申请主体" value={`${record.applicantName} · ${SUBJECT_LABELS[record.applicantType]}`} /><Detail label="申请面积" value={`${record.requestedAreaMu} 亩`} /><Detail label="申请数量" value={`${record.requestedQuantityTon} 吨`} /><Detail label="计划作业期" value={`${formatDateTime(record.workStartAt)} 至 ${formatDateTime(record.workEndAt)}`} /><Detail label="采伐用途" value={record.purpose} /></dl></section>
    <section className="detail-group"><h3>空间与权属依据</h3><div className="harvest-reference-columns"><div><span>采伐林班</span>{record.blocks.map((item) => <strong key={item.id}><MapPinned aria-hidden="true" />{item.code}<small>{item.declaredAreaMu || "面积待补"} 亩</small></strong>)}</div><div><span>林权档案</span>{record.rights.map((item) => <strong key={item.id}><FileCheck2 aria-hidden="true" />{item.archiveCode}</strong>)}</div></div></section>
    {record.quotaCheck.checkedAt && <section className={`quota-result ${record.quotaCheck.passed ? "passed" : "failed"}`}><span>{record.quotaCheck.passed ? <ShieldCheck aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}</span><div><small>自动配额校验</small><h3>{record.quotaCheck.passed ? "配额校验通过" : "配额校验未通过"}</h3><p>{record.quotaCheck.passed ? `校验时剩余 ${record.quotaCheck.remainingAreaMu} 亩，可进入审批。` : record.quotaCheck.reasons?.join("；")}</p></div></section>}
    {record.operation.workWindow && <section className="operation-boundary-card"><div><span className="eyebrow">作业许可</span><h3>林班边界围栏已启用</h3><p>{record.operation.geofence?.blockCodes.join("、")}</p></div><dl><Detail label="许可开始" value={formatDateTime(record.operation.workWindow.startAt)} /><Detail label="许可结束" value={formatDateTime(record.operation.workWindow.endAt)} /></dl></section>}
    {(record.operation.alerts?.length ?? 0) > 0 && <section className="harvest-alert-list"><div className="section-heading"><div><span className="eyebrow">安全监管</span><h3>作业告警</h3></div><strong>{record.operation.alerts?.length} 条</strong></div>{record.operation.alerts?.map((alert) => <article key={alert.id}><AlertTriangle aria-hidden="true" /><div><strong>{alert.message}</strong><small>{alert.type} · {alert.locationText || "位置未填"} · {formatDateTime(alert.reportedAt)}</small></div></article>)}</section>}
    {record.attachments.length > 0 && <section className="detail-group"><h3>作业凭证</h3><div className="attachment-chip-list">{record.attachments.map((item) => <span key={item.id}><Paperclip aria-hidden="true" /><strong>{item.originalName}</strong><small>{item.category}</small></span>)}</div></section>}
    {record.batch && <section className="harvest-batch-card"><PackageCheck aria-hidden="true" /><div><span className="eyebrow">验收归档完成</span><h3>{record.batch.batchNo}</h3><p>追溯码 {record.batch.traceCode}</p><small>实采 {record.batch.actualAreaMu} 亩 / {record.batch.actualQuantityTon} 吨 · 已生成 {record.batch.resourceVersionIds.length} 个资源版本</small></div></section>}
    {record.deletedAt ? <div className="permission-note"><Trash2 aria-hidden="true" /><span><strong>该申请已进入回收站</strong><small>恢复后才能继续编辑或办理。</small></span></div> : <HarvestNextAction record={record} permissions={permissions} pending={pending} onAction={onAction} />}
    {error && <p className="form-error">{error.message}</p>}
    <section className="harvest-timeline"><div className="section-heading"><div><span className="eyebrow">全程留痕</span><h3>办理时间轴</h3></div></div>{[...record.timeline].reverse().map((item) => <div className="timeline-entry" key={item.id}><span><Clock3 aria-hidden="true" /></span><div><strong>{actionLabel(item.action)}</strong><small>{item.actor} · {formatDateTime(item.createdAt)}</small>{item.note && <p>{item.note}</p>}</div></div>)}</section>
  </div>;
}

function HarvestNextAction({ record, permissions, pending, onAction }: { record: HarvestApplication; permissions: { create: boolean; approve: boolean; operate: boolean; verify: boolean }; pending: boolean; onAction: (action: string, payload?: HarvestActionPayload) => void }) {
  if (record.status === "draft" && permissions.create) return <ActionCard title="提交申请" detail="提交后系统自动校验林权覆盖关系和年度配额。"><button className="button primary" type="button" disabled={pending} onClick={() => onAction("submit")}><Send aria-hidden="true" />提交并校验</button></ActionCard>;
  if (record.status === "quota_check" && permissions.create) return <ActionCard title="重新校验配额" detail="配额补充或调整后，可重新执行自动校验。"><button className="button primary" type="button" disabled={pending} onClick={() => onAction("recheck")}><RefreshCw aria-hidden="true" />重新校验</button></ActionCard>;
  if (record.status === "approving" && permissions.approve) return <ActionForm title="审批采伐申请" detail="审批通过将锁定对应年度配额。" pending={pending} submitLabel="审批通过" secondaryLabel="退回修改" icon={ShieldCheck} fields={<label className="field-span"><span>审批意见</span><textarea name="note" rows={3} placeholder="退回时必须填写原因" /></label>} onSubmit={(data) => onAction("approve", { note: field(data, "note") })} onSecondary={(data) => onAction("return", { note: field(data, "note") })} />;
  if (record.status === "approved" && permissions.operate) return <ActionCard title="启动采伐作业" detail="系统会按批准林班生成电子围栏，并启用许可时间窗。"><button className="button primary" type="button" disabled={pending} onClick={() => onAction("start")}><Play aria-hidden="true" />开始作业</button></ActionCard>;
  if (record.status === "operating" && permissions.operate) return <div className="harvest-operating-actions"><ActionForm title="记录作业告警" detail="越界、超时或设备异常需要单独留痕。" pending={pending} submitLabel="记录告警" icon={AlertTriangle} fields={<><label><span>告警类型<em>*</em></span><select name="alertType" required defaultValue="outside-geofence"><option value="outside-geofence">越出电子围栏</option><option value="outside-window">超出许可时间</option><option value="unlicensed-device">未备案设备</option><option value="safety">现场安全风险</option></select></label><label><span>告警等级</span><select name="alertLevel" defaultValue="warning"><option value="warning">一般</option><option value="high">严重</option></select></label><label className="field-span"><span>告警说明<em>*</em></span><textarea name="alertMessage" rows={2} required /></label><label><span>位置</span><input name="locationText" /></label><label><span>设备编号</span><input name="deviceCode" /></label></>} onSubmit={(data) => onAction("record-alert", { alertType: field(data, "alertType"), alertLevel: field(data, "alertLevel"), alertMessage: field(data, "alertMessage"), locationText: field(data, "locationText"), deviceCode: field(data, "deviceCode") })} /><HarvestCompletionAction record={record} pending={pending} onAction={onAction} /></div>;
  if (record.status === "verifying" && permissions.verify) return <ActionForm title="验收采伐成果" detail="通过后生成采伐批次、追溯码和新的资源调查版本，原始资源版本不会被覆盖。" pending={pending} submitLabel="验收通过并归档" secondaryLabel="退回作业" icon={PackageCheck} fields={<label className="field-span"><span>验收意见</span><textarea name="note" rows={3} placeholder="退回时必须填写原因" /></label>} onSubmit={(data) => onAction("verify", { note: field(data, "note") })} onSecondary={(data) => onAction("return-operation", { note: field(data, "note") })} />;
  if (record.status !== "completed") return <div className="permission-note"><ShieldCheck aria-hidden="true" /><span><strong>当前环节无可执行操作</strong><small>办理按钮会根据申请状态和角色操作权限显示。</small></span></div>;
  return null;
}

function HarvestCompletionAction({ record, pending, onAction }: { record: HarvestApplication; pending: boolean; onAction: (action: string, payload?: HarvestActionPayload) => void }) {
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [attachments, setAttachments] = useState<AttachmentRecord[]>(record.attachments ?? []);
  return <>
    <form className="harvest-action-card" onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); onAction("report-complete", { actualAreaMu: numberField(data, "actualAreaMu"), actualQuantityTon: numberField(data, "actualQuantityTon"), note: field(data, "note"), attachmentIds: attachments.map((item) => item.id) }); }}>
      <div><span className="eyebrow">当前可办</span><h3>提交作业结果</h3><p>填写实采数据并关联照片、测量表或现场记录后进入验收。</p></div>
      <div className="form-grid"><label><span>实际面积(亩)<em>*</em></span><input name="actualAreaMu" type="number" min="0.01" max={record.requestedAreaMu} step="0.01" required defaultValue={record.requestedAreaMu} /></label><label><span>实际数量(吨)</span><input name="actualQuantityTon" type="number" min="0" step="0.01" defaultValue={record.requestedQuantityTon} /></label><label className="field-span"><span>作业总结</span><textarea name="note" rows={3} /></label></div>
      <div className="selected-evidence"><button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}><Paperclip aria-hidden="true" />选择作业凭证</button><span>{attachments.length ? `已关联 ${attachments.length} 份凭证` : "尚未关联凭证"}</span></div>
      <div className="form-actions"><button className="button primary" type="submit" disabled={pending}><ClipboardCheck aria-hidden="true" />{pending ? "处理中" : "提交验收"}</button></div>
    </form>
    <AttachmentSelector open={selectorOpen} selectedIds={attachments.map((item) => item.id)} onClose={() => setSelectorOpen(false)} onChange={setAttachments} category="harvest_evidence" title="选择采伐作业凭证" />
  </>;
}

function RelationPicker({ icon, label, selected, onOpen, onClear }: { icon: ReactNode; label: string; selected: string; onOpen: () => void; onClear?: () => void }) { return <div className="relation-picker"><span>{icon}</span><div><small>{label}</small><strong>{selected}</strong></div>{onClear && <button className="icon-button" type="button" aria-label={`清除${label}`} onClick={onClear}><X aria-hidden="true" /></button>}<button className="button secondary" type="button" onClick={onOpen}>选择</button></div>; }
function ActionForm({ title, detail, fields, pending, submitLabel, secondaryLabel, icon: Icon, onSubmit, onSecondary }: { title: string; detail: string; fields: ReactNode; pending: boolean; submitLabel: string; secondaryLabel?: string; icon: typeof Send; onSubmit: (data: FormData) => void; onSecondary?: (data: FormData) => void }) { const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); onSubmit(new FormData(event.currentTarget)); }; return <form className="harvest-action-card" onSubmit={submit}><div><span className="eyebrow">当前可办</span><h3>{title}</h3><p>{detail}</p></div><div className="form-grid">{fields}</div><div className="form-actions">{secondaryLabel && <button className="button secondary" type="button" disabled={pending} onClick={(event) => onSecondary?.(new FormData(event.currentTarget.form!))}><RotateCcw aria-hidden="true" />{secondaryLabel}</button>}<button className="button primary" type="submit" disabled={pending}><Icon aria-hidden="true" />{pending ? "处理中" : submitLabel}</button></div></form>; }
function ActionCard({ title, detail, children }: { title: string; detail: string; children: ReactNode }) { return <section className="harvest-action-card"><div><span className="eyebrow">当前可办</span><h3>{title}</h3><p>{detail}</p></div><div className="form-actions">{children}</div></section>; }
function RowAction({ label, icon: Icon, disabled = false, danger = false, onClick }: { label: string; icon: typeof Eye; disabled?: boolean; danger?: boolean; onClick: () => void }) { return <button className={`icon-button ${danger ? "danger" : ""}`} type="button" disabled={disabled} aria-label={label} title={label} onClick={(event) => { event.stopPropagation(); onClick(); }}><Icon aria-hidden="true" /></button>; }
function HarvestStatusBadge({ status }: { status: HarvestStatus }) { const tone = status === "completed" ? "success" : status === "quota_check" || status === "verifying" ? "warning" : status === "operating" ? "active" : "neutral"; return <span className={`harvest-status ${tone}`}>{STATUS_LABELS[status]}</span>; }
function SummaryMetric({ label, value, detail, tone = "neutral" }: { label: string; value: number; detail: string; tone?: "neutral" | "active" | "warning" }) { return <div className={tone}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function Detail({ label, value }: { label: string; value: unknown }) { const text = String(value ?? "").trim() || "未填写"; return <div><dt>{label}</dt><dd>{text}</dd></div>; }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function numberField(data: FormData, name: string) { const value = Number(data.get(name) || 0); return Number.isFinite(value) ? value : 0; }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }); }
function localInput(date: Date) { const offset = date.getTimezoneOffset() * 60_000; return new Date(date.getTime() - offset).toISOString().slice(0, 16); }
function toLocalInput(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? "" : localInput(date); }
function defaultSchedule() { const start = new Date(); start.setDate(start.getDate() + 7); start.setHours(8, 0, 0, 0); const end = new Date(start); end.setDate(end.getDate() + 7); end.setHours(18, 0, 0, 0); return { start: localInput(start), end: localInput(end) }; }
function sumArea(blocks: ForestBlockOption[]) { return blocks.reduce((sum, item) => sum + (item.areaMu || 0), 0).toFixed(1); }
function remainingArea(quota: HarvestQuota) { return Math.max(0, quota.quotaAreaMu - quota.usedAreaMu).toFixed(1); }
function actionLabel(action: string) { return ({ create: "建立申请", edit: "修改草稿", delete: "移入回收站", restore: "恢复申请", submit: "提交申请", "quota-check": "配额校验", approve: "审批通过", return: "退回修改", start: "开始作业", "record-alert": "记录告警", "report-complete": "提交验收", verify: "验收归档", "return-operation": "退回作业" } as Record<string, string>)[action] || action; }
