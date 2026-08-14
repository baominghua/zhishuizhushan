import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck, BriefcaseBusiness, CalendarDays, CheckCircle2, ChevronRight, ClipboardCheck,
  Clock3, Coins, Download, Eye, FileSignature, MapPinned, Pencil, Play, Plus, RefreshCw, RotateCcw,
  Search, Send, ShieldCheck, Trash2, UserRound, UsersRound, WalletCards, X,
} from "lucide-react";
import { type FormEvent, type ReactNode, useDeferredValue, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  ForestBlockOption, LaborActionPayload, LaborJob, LaborJobPayload, LaborJobStatus,
  LaborTeam, LaborTeamPayload, LaborWorker, LaborWorkerPayload,
} from "../api/types";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 30;
const JOB_STATUS_ORDER: LaborJobStatus[] = ["draft", "published", "matched", "contracted", "working", "submitted", "settled", "closed"];
const JOB_STATUS_LABELS: Record<LaborJobStatus, string> = {
  draft: "草稿", published: "待匹配", matched: "待签约", contracted: "待进场",
  working: "作业中", submitted: "待结算", settled: "待归档", closed: "已归档",
};
const WORK_TYPE_LABELS: Record<LaborJob["workType"], string> = {
  tending: "抚育管护", harvest: "竹材采伐", transport: "装运运输", fertilization: "施肥作业",
  "pest-control": "植保防治", survey: "调查测绘", other: "其他作业",
};
const EMPLOYER_LABELS: Record<LaborJob["employerType"], string> = {
  farmer: "竹农", cooperative: "合作社", enterprise: "竹企", government: "政府单位", other: "其他主体",
};
const PRICE_UNIT_LABELS: Record<LaborJob["priceUnit"], string> = { mu: "元/亩", day: "元/工日", ton: "元/吨", job: "元/项" };
const WORKER_STATUS_LABELS: Record<LaborWorker["employmentStatus"], string> = { available: "可接单", working: "作业中", inactive: "已停用" };
const TRAINING_STATUS_LABELS: Record<LaborWorker["trainingStatus"], string> = { valid: "培训有效", expiring: "即将到期", missing: "待培训" };
const TEAM_STATUS_LABELS: Record<LaborTeam["status"], string> = { active: "可接单", busy: "作业中", inactive: "已停用" };

type LedgerView = "jobs" | "workers" | "teams";
type CreateView = "job" | "worker" | "team" | null;

export function LaborPage() {
  const queryClient = useQueryClient();
  const capabilities = useCapabilities();
  const [view, setView] = useState<LedgerView>("jobs");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState<CreateView>(null);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [selectedJob, setSelectedJob] = useState<LaborJob | null>(null);
  const [selectedWorker, setSelectedWorker] = useState<LaborWorker | null>(null);
  const [selectedTeam, setSelectedTeam] = useState<LaborTeam | null>(null);
  const [editingJob, setEditingJob] = useState<LaborJob | null>(null);
  const [editingWorker, setEditingWorker] = useState<LaborWorker | null>(null);
  const [editingTeam, setEditingTeam] = useState<LaborTeam | null>(null);
  const deferredQ = useDeferredValue(q);

  const jobs = useQuery({
    queryKey: ["v2-labor-jobs", deferredQ, status, includeDeleted, offset],
    queryFn: () => api.laborJobs({ q: deferredQ, status, includeDeleted, limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const workers = useQuery({
    queryKey: ["v2-labor-workers", deferredQ, status, includeDeleted, offset],
    queryFn: () => api.laborWorkers({ q: deferredQ, status, includeDeleted, limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const teams = useQuery({
    queryKey: ["v2-labor-teams", deferredQ, status, includeDeleted, offset],
    queryFn: () => api.laborTeams({ q: deferredQ, status, includeDeleted, limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const availableWorkers = useQuery({
    queryKey: ["v2-labor-worker-options"],
    queryFn: () => api.laborWorkers({ limit: 200, offset: 0 }),
    staleTime: 15_000,
  });
  const availableTeams = useQuery({
    queryKey: ["v2-labor-team-options"],
    queryFn: () => api.laborTeams({ limit: 200, offset: 0 }),
    staleTime: 15_000,
  });

  const permissions = capabilities.data?.permissions;
  const roles = capabilities.data?.principal.roles;
  const canCreateJob = hasPermission(permissions, roles, "labor.jobs.create");
  const canManageWorkers = hasPermission(permissions, roles, "labor.workers.manage");
  const canManageTeams = hasPermission(permissions, roles, "labor.teams.manage");
  const canDispatch = hasPermission(permissions, roles, "labor.jobs.dispatch");
  const canOperate = hasPermission(permissions, roles, "labor.jobs.operate");
  const canSettle = hasPermission(permissions, roles, "labor.jobs.settle");

  const createWorker = useMutation({
    mutationFn: api.createLaborWorker,
    onSuccess: async (record) => { setCreating(null); setSelectedWorker(record); await invalidateLabor(queryClient); },
  });
  const createTeam = useMutation({
    mutationFn: api.createLaborTeam,
    onSuccess: async (record) => { setCreating(null); setSelectedTeam(record); await invalidateLabor(queryClient); },
  });
  const createJob = useMutation({
    mutationFn: api.createLaborJob,
    onSuccess: async (record) => { setCreating(null); setSelectedJob(record); await invalidateLabor(queryClient); },
  });
  const updateWorker = useMutation({
    mutationFn: ({ record, payload }: { record: LaborWorker; payload: LaborWorkerPayload }) => api.updateLaborWorker(record.id, payload),
    onSuccess: async (record) => { setEditingWorker(null); setSelectedWorker(record); await invalidateLabor(queryClient); },
  });
  const updateTeam = useMutation({
    mutationFn: ({ record, payload }: { record: LaborTeam; payload: LaborTeamPayload }) => api.updateLaborTeam(record.id, payload),
    onSuccess: async (record) => { setEditingTeam(null); setSelectedTeam(record); await invalidateLabor(queryClient); },
  });
  const updateJob = useMutation({
    mutationFn: ({ record, payload }: { record: LaborJob; payload: LaborJobPayload }) => api.updateLaborJob(record.id, payload),
    onSuccess: async (record) => { setEditingJob(null); setSelectedJob(record); await invalidateLabor(queryClient); },
  });
  const removeWorker = useMutation({ mutationFn: api.deleteLaborWorker, onSuccess: async () => invalidateLabor(queryClient) });
  const restoreWorker = useMutation({ mutationFn: api.restoreLaborWorker, onSuccess: async () => invalidateLabor(queryClient) });
  const removeTeam = useMutation({ mutationFn: api.deleteLaborTeam, onSuccess: async () => invalidateLabor(queryClient) });
  const restoreTeam = useMutation({ mutationFn: api.restoreLaborTeam, onSuccess: async () => invalidateLabor(queryClient) });
  const removeJob = useMutation({ mutationFn: api.deleteLaborJob, onSuccess: async () => invalidateLabor(queryClient) });
  const restoreJob = useMutation({ mutationFn: api.restoreLaborJob, onSuccess: async () => invalidateLabor(queryClient) });
  const applyAction = useMutation({
    mutationFn: ({ record, action, payload }: { record: LaborJob; action: string; payload?: LaborActionPayload }) => api.applyLaborAction(record.id, action, payload),
    onSuccess: async (record) => { setSelectedJob(record); await invalidateLabor(queryClient); },
  });

  const jobItems = jobs.data?.items ?? [];
  const workerItems = workers.data?.items ?? [];
  const teamItems = teams.data?.items ?? [];
  const metrics = useMemo(() => ({
    demand: jobItems.filter((item) => ["published", "matched", "contracted"].includes(item.status)).length,
    working: jobItems.filter((item) => item.status === "working").length,
    people: availableWorkers.data?.total ?? workerItems.length,
    unsettled: jobItems.filter((item) => item.status === "submitted").length,
  }), [availableWorkers.data?.total, jobItems, workerItems.length]);
  const activeQuery = view === "jobs" ? jobs : view === "workers" ? workers : teams;
  const activeTotal = activeQuery.data?.total ?? 0;
  const canCreate = view === "jobs" ? canCreateJob : view === "workers" ? canManageWorkers : canManageTeams;
  const createLabel = view === "jobs" ? "新建用工任务" : view === "workers" ? "新增人员" : "新增班组";
  const exportHref = `/api/v2/labor/${view}-export.csv?${new URLSearchParams({ q: deferredQ, status }).toString()}`;

  const switchView = (next: LedgerView) => {
    setView(next); setQ(""); setStatus(""); setIncludeDeleted(false); setOffset(0);
  };

  return <div className="standard-page ledger-page labor-page">
    <section className="page-heading ledger-heading">
      <div><span className="eyebrow">运营管护 / 人员与班组</span><h1>劳务用工</h1><p>从人员建档、班组组织到任务发包、合同、考勤、完工和工资结算，形成可追溯的用工闭环。</p></div>
      <div className="heading-actions"><a className="button secondary" href={exportHref}><Download aria-hidden="true" />导出台账</a><button className="button secondary" type="button" onClick={() => activeQuery.refetch()}><RefreshCw aria-hidden="true" />刷新</button><button className="button primary" type="button" disabled={!canCreate} onClick={() => setCreating(view === "jobs" ? "job" : view === "workers" ? "worker" : "team")} title={canCreate ? createLabel : "当前角色无新增权限"}><Plus aria-hidden="true" />{createLabel}</button></div>
    </section>

    <section className="labor-summary-strip" aria-label="劳务管理摘要">
      <SummaryMetric label="待匹配需求" value={metrics.demand} detail="待班组承接或签约" icon={<BriefcaseBusiness aria-hidden="true" />} />
      <SummaryMetric label="作业中任务" value={metrics.working} detail="正在执行的用工任务" tone="active" icon={<Clock3 aria-hidden="true" />} />
      <SummaryMetric label="人员档案" value={metrics.people} detail="正式人员台账总数" icon={<UsersRound aria-hidden="true" />} />
      <SummaryMetric label="待结算任务" value={metrics.unsettled} detail="已完工待核算工资" tone="warning" icon={<WalletCards aria-hidden="true" />} />
    </section>

    <section className="ledger-shell labor-ledger-shell">
      <div className="ledger-tabs" role="tablist" aria-label="劳务管理台账">
        <button type="button" className={view === "jobs" ? "active" : ""} onClick={() => switchView("jobs")} role="tab" aria-selected={view === "jobs"}>用工任务</button>
        <button type="button" className={view === "workers" ? "active" : ""} onClick={() => switchView("workers")} role="tab" aria-selected={view === "workers"}>人员档案</button>
        <button type="button" className={view === "teams" ? "active" : ""} onClick={() => switchView("teams")} role="tab" aria-selected={view === "teams"}>班组档案</button>
      </div>
      <div className="ledger-toolbar labor-toolbar">
        <label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder={view === "jobs" ? "搜索任务编号、名称、发包方或班组" : view === "workers" ? "搜索人员编号、姓名、手机或技能" : "搜索班组编号、名称、负责人或服务区域"} /></label>
        <label className="compact-filter"><span>状态</span><select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}><option value="">全部状态</option>{view === "jobs" ? Object.entries(JOB_STATUS_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>) : view === "workers" ? Object.entries(WORKER_STATUS_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>) : Object.entries(TEAM_STATUS_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
        {canCreate && <label className="deleted-toggle"><input type="checkbox" checked={includeDeleted} onChange={(event) => { setIncludeDeleted(event.target.checked); setOffset(0); }} /><span>显示已删除</span></label>}
        {(q || status || includeDeleted) && <button className="text-button" type="button" onClick={() => { setQ(""); setStatus(""); setIncludeDeleted(false); setOffset(0); }}>清除条件</button>}
      </div>
      {view === "jobs" && <JobLedger loading={jobs.isLoading} error={jobs.error} items={jobItems} canManage={canCreateJob} onView={setSelectedJob} onEdit={setEditingJob} onDelete={(record) => removeJob.mutate(record.id)} onRestore={(record) => restoreJob.mutate(record.id)} />}
      {view === "workers" && <WorkerLedger loading={workers.isLoading} error={workers.error} items={workerItems} canManage={canManageWorkers} onView={setSelectedWorker} onEdit={setEditingWorker} onDelete={(record) => removeWorker.mutate(record.id)} onRestore={(record) => restoreWorker.mutate(record.id)} />}
      {view === "teams" && <TeamLedger loading={teams.isLoading} error={teams.error} items={teamItems} canManage={canManageTeams} onView={setSelectedTeam} onEdit={setEditingTeam} onDelete={(record) => removeTeam.mutate(record.id)} onRestore={(record) => restoreTeam.mutate(record.id)} />}
      <LedgerPagination total={activeTotal} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
    </section>

    <SidePanel wide open={creating === "job"} eyebrow="用工需求建档" title="新建用工任务" onClose={() => !createJob.isPending && setCreating(null)}>
      <JobCreateForm pending={createJob.isPending} error={createJob.error} onCancel={() => setCreating(null)} onSubmit={(payload) => createJob.mutate(payload)} />
    </SidePanel>
    <SidePanel wide open={creating === "worker"} eyebrow="人员正式档案" title="新增劳务人员" onClose={() => !createWorker.isPending && setCreating(null)}>
      <WorkerCreateForm pending={createWorker.isPending} error={createWorker.error} onCancel={() => setCreating(null)} onSubmit={(payload) => createWorker.mutate(payload)} />
    </SidePanel>
    <SidePanel wide open={creating === "team"} eyebrow="班组正式档案" title="新增劳务班组" onClose={() => !createTeam.isPending && setCreating(null)}>
      <TeamCreateForm workers={availableWorkers.data?.items ?? []} pending={createTeam.isPending} error={createTeam.error} onCancel={() => setCreating(null)} onSubmit={(payload) => createTeam.mutate(payload)} />
    </SidePanel>
    <SidePanel wide open={Boolean(editingJob)} eyebrow="用工任务维护" title="编辑任务草稿" onClose={() => !updateJob.isPending && setEditingJob(null)}>
      {editingJob && <JobCreateForm record={editingJob} pending={updateJob.isPending} error={updateJob.error} onCancel={() => setEditingJob(null)} onSubmit={(payload) => updateJob.mutate({ record: editingJob, payload })} />}
    </SidePanel>
    <SidePanel wide open={Boolean(editingWorker)} eyebrow="人员档案维护" title="编辑劳务人员" onClose={() => !updateWorker.isPending && setEditingWorker(null)}>
      {editingWorker && <WorkerCreateForm record={editingWorker} pending={updateWorker.isPending} error={updateWorker.error} onCancel={() => setEditingWorker(null)} onSubmit={(payload) => updateWorker.mutate({ record: editingWorker, payload })} />}
    </SidePanel>
    <SidePanel wide open={Boolean(editingTeam)} eyebrow="班组档案维护" title="编辑劳务班组" onClose={() => !updateTeam.isPending && setEditingTeam(null)}>
      {editingTeam && <TeamCreateForm record={editingTeam} workers={availableWorkers.data?.items ?? []} pending={updateTeam.isPending} error={updateTeam.error} onCancel={() => setEditingTeam(null)} onSubmit={(payload) => updateTeam.mutate({ record: editingTeam, payload })} />}
    </SidePanel>
    <SidePanel wide open={Boolean(selectedJob)} eyebrow="用工任务闭环" title={selectedJob?.title || "任务详情"} onClose={() => !applyAction.isPending && setSelectedJob(null)}>
      {selectedJob && <JobDetail record={selectedJob} teams={(availableTeams.data?.items ?? []).filter((item) => item.status !== "inactive")} permissions={{ dispatch: canDispatch, operate: canOperate, settle: canSettle }} pending={applyAction.isPending} error={applyAction.error} onAction={(action, payload) => applyAction.mutate({ record: selectedJob, action, payload })} />}
    </SidePanel>
    <SidePanel open={Boolean(selectedWorker)} eyebrow="人员档案详情" title={selectedWorker?.name || "人员详情"} onClose={() => setSelectedWorker(null)}>{selectedWorker && <WorkerDetail record={selectedWorker} />}</SidePanel>
    <SidePanel open={Boolean(selectedTeam)} eyebrow="班组档案详情" title={selectedTeam?.name || "班组详情"} onClose={() => setSelectedTeam(null)}>{selectedTeam && <TeamDetail record={selectedTeam} />}</SidePanel>
  </div>;
}

type LedgerActions<T> = { canManage: boolean; onView: (record: T) => void; onEdit: (record: T) => void; onDelete: (record: T) => void; onRestore: (record: T) => void };

function RowActions<T extends { deletedAt?: string | null }>({ record, canManage, canEdit = true, onView, onEdit, onDelete, onRestore }: LedgerActions<T> & { record: T; canEdit?: boolean }) {
  return <div className="row-actions">
    <button className="icon-button" type="button" aria-label="查看" title="查看" onClick={(event) => { event.stopPropagation(); onView(record); }}><Eye aria-hidden="true" /></button>
    {record.deletedAt ? <button className="icon-button" type="button" aria-label="恢复" title="恢复" disabled={!canManage} onClick={(event) => { event.stopPropagation(); onRestore(record); }}><RotateCcw aria-hidden="true" /></button> : <>
      <button className="icon-button" type="button" aria-label="编辑" title={canEdit ? "编辑" : "当前状态不可编辑"} disabled={!canManage || !canEdit} onClick={(event) => { event.stopPropagation(); onEdit(record); }}><Pencil aria-hidden="true" /></button>
      <button className="icon-button danger" type="button" aria-label="删除" title={canEdit ? "删除" : "当前状态不可删除"} disabled={!canManage || !canEdit} onClick={(event) => { event.stopPropagation(); onDelete(record); }}><Trash2 aria-hidden="true" /></button>
    </>}
  </div>;
}

function JobLedger({ loading, error, items, ...actions }: { loading: boolean; error: Error | null; items: LaborJob[] } & LedgerActions<LaborJob>) {
  return <QueryState loading={loading} error={error}><div className="table-scroll"><table className="ledger-table labor-job-table"><thead><tr><th>用工任务</th><th>发包与作业</th><th>计划安排</th><th>承接班组</th><th>办理状态</th><th className="action-column">操作</th></tr></thead><tbody>
    {items.map((record) => <tr className={record.deletedAt ? "is-deleted" : ""} key={record.id} onClick={() => actions.onView(record)}><td><strong>{record.title}</strong><small>{record.jobNo} · 关联 {record.blocks.length} 个林班</small></td><td><strong>{record.employerName}</strong><small>{EMPLOYER_LABELS[record.employerType]} · {WORK_TYPE_LABELS[record.workType]}</small></td><td><strong>{formatDate(record.plannedStartAt)} 至 {formatDate(record.plannedEndAt)}</strong><small>{record.requiredHeadcount} 人 · {formatMoney(record.unitPrice)} {PRICE_UNIT_LABELS[record.priceUnit]}</small></td><td><strong>{record.teamName || "待匹配班组"}</strong><small>{record.contractNo || "合同待签订"}</small></td><td>{record.deletedAt ? <span className="status-badge muted">已删除</span> : <JobStatusBadge status={record.status} />}</td><td className="action-column"><RowActions record={record} canEdit={record.status === "draft"} {...actions} /></td></tr>)}
    {!loading && !items.length && <tr className="empty-row"><td colSpan={6}><div className="table-empty"><BriefcaseBusiness aria-hidden="true" /><strong>当前没有用工任务</strong><p>新建需求后，按匹配班组、签订合同、考勤和工资结算逐步办理。</p></div></td></tr>}
  </tbody></table></div></QueryState>;
}

function WorkerLedger({ loading, error, items, ...actions }: { loading: boolean; error: Error | null; items: LaborWorker[] } & LedgerActions<LaborWorker>) {
  return <QueryState loading={loading} error={error}><div className="table-scroll"><table className="ledger-table labor-worker-table"><thead><tr><th>人员档案</th><th>联系方式</th><th>技能与资格</th><th>培训状态</th><th>从业状态</th><th className="action-column">操作</th></tr></thead><tbody>
    {items.map((record) => <tr className={record.deletedAt ? "is-deleted" : ""} key={record.id} onClick={() => actions.onView(record)}><td><strong>{record.name}</strong><small>{record.workerNo} · {record.gender || "性别未填"}</small></td><td><strong>{record.mobile || "手机未填"}</strong><small>{record.emergencyContact || "紧急联系人未填"}</small></td><td><strong>{record.skillCodes.join("、") || "技能待补"}</strong><small>{record.qualifications.join("、") || "资格证待补"}</small></td><td><TrainingBadge status={record.trainingStatus} /></td><td>{record.deletedAt ? <span className="status-badge muted">已删除</span> : <WorkerStatusBadge status={record.employmentStatus} />}</td><td className="action-column"><RowActions record={record} {...actions} /></td></tr>)}
    {!loading && !items.length && <tr className="empty-row"><td colSpan={6}><div className="table-empty"><UserRound aria-hidden="true" /><strong>当前没有人员档案</strong><p>先建立人员、技能、证照和培训档案，再组建可承接任务的班组。</p></div></td></tr>}
  </tbody></table></div></QueryState>;
}

function TeamLedger({ loading, error, items, ...actions }: { loading: boolean; error: Error | null; items: LaborTeam[] } & LedgerActions<LaborTeam>) {
  return <QueryState loading={loading} error={error}><div className="table-scroll"><table className="ledger-table labor-team-table"><thead><tr><th>班组档案</th><th>负责人</th><th>成员配置</th><th>服务范围</th><th>班组状态</th><th className="action-column">操作</th></tr></thead><tbody>
    {items.map((record) => <tr className={record.deletedAt ? "is-deleted" : ""} key={record.id} onClick={() => actions.onView(record)}><td><strong>{record.name}</strong><small>{record.teamNo}</small></td><td><strong>{record.leaderName}</strong><small>{record.contactPhone || "联系电话未填"}</small></td><td><strong>{record.members.length} 人</strong><small>{record.skillCodes.join("、") || "技能待补"}</small></td><td><strong>{record.serviceArea || "服务范围待补"}</strong><small>{record.notes || "暂无备注"}</small></td><td>{record.deletedAt ? <span className="status-badge muted">已删除</span> : <TeamStatusBadge status={record.status} />}</td><td className="action-column"><RowActions record={record} {...actions} /></td></tr>)}
    {!loading && !items.length && <tr className="empty-row"><td colSpan={6}><div className="table-empty"><UsersRound aria-hidden="true" /><strong>当前没有班组档案</strong><p>班组成员必须从正式人员台账选择，负责人也必须是班组成员。</p></div></td></tr>}
  </tbody></table></div></QueryState>;
}

function WorkerCreateForm({ record, pending, error, onCancel, onSubmit }: { record?: LaborWorker; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: LaborWorkerPayload) => void }) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    onSubmit({ name: field(data, "name"), mobile: field(data, "mobile"), idCardMask: field(data, "idCardMask"), gender: field(data, "gender"), employmentStatus: field(data, "employmentStatus") as LaborWorker["employmentStatus"], skillCodes: listField(data, "skillCodes"), qualifications: listField(data, "qualifications"), trainingStatus: field(data, "trainingStatus") as LaborWorker["trainingStatus"], creditScore: numberField(data, "creditScore"), homeAddress: field(data, "homeAddress"), emergencyContact: field(data, "emergencyContact"), notes: field(data, "notes") });
  };
  return <form className="entity-form" onSubmit={submit}><fieldset className="form-section"><legend>身份与联系信息</legend><p>身份证仅录入脱敏信息，正式证照文件后续进入附件档案。</p><div className="form-grid"><label><span>姓名<em>*</em></span><input name="name" required defaultValue={record?.name} /></label><label><span>手机号</span><input name="mobile" type="tel" defaultValue={record?.mobile} /></label><label><span>身份证脱敏号</span><input name="idCardMask" placeholder="3507********1234" defaultValue={record?.idCardMask} /></label><label><span>性别</span><select name="gender" defaultValue={record?.gender || ""}><option value="">未填写</option><option value="男">男</option><option value="女">女</option></select></label><label><span>紧急联系人</span><input name="emergencyContact" placeholder="姓名 / 手机号" defaultValue={record?.emergencyContact} /></label><label><span>常住地址</span><input name="homeAddress" defaultValue={record?.homeAddress} /></label></div></fieldset><fieldset className="form-section"><legend>从业能力</legend><div className="form-grid"><label className="field-span"><span>作业技能</span><input name="skillCodes" placeholder="抚育、采伐、运输，多个用逗号分隔" defaultValue={record?.skillCodes.join("、")} /></label><label className="field-span"><span>资格证书</span><input name="qualifications" placeholder="安全培训证、采伐作业证，多个用逗号分隔" defaultValue={record?.qualifications.join("、")} /></label><label><span>培训状态</span><select name="trainingStatus" defaultValue={record?.trainingStatus || "missing"}><option value="valid">培训有效</option><option value="expiring">即将到期</option><option value="missing">待培训</option></select></label><label><span>从业状态</span><select name="employmentStatus" defaultValue={record?.employmentStatus || "available"}><option value="available">可接单</option><option value="working">作业中</option><option value="inactive">已停用</option></select></label><label><span>信用分</span><input name="creditScore" type="number" min="0" max="100" defaultValue={record?.creditScore ?? 100} /></label><label className="field-span"><span>备注</span><textarea name="notes" rows={3} defaultValue={record?.notes} /></label></div></fieldset>{error && <p className="form-error">{error.message}</p>}<div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={pending}>{pending ? "正在保存" : record ? "保存修改" : "保存人员档案"}</button></div></form>;
}

function TeamCreateForm({ record, workers, pending, error, onCancel, onSubmit }: { record?: LaborTeam; workers: LaborWorker[]; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: LaborTeamPayload) => void }) {
  const [leaderId, setLeaderId] = useState(record?.leaderWorkerId || "");
  const [members, setMembers] = useState<string[]>(record?.members.map((item) => item.id) || []);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    onSubmit({ name: field(data, "name"), status: field(data, "status") as LaborTeam["status"], leaderWorkerId: leaderId, memberIds: members, contactPhone: field(data, "contactPhone"), serviceArea: field(data, "serviceArea"), skillCodes: listField(data, "skillCodes"), notes: field(data, "notes") });
  };
  const selectLeader = (value: string) => { setLeaderId(value); setMembers((items) => items.includes(value) ? items : [...items, value]); };
  return <form className="entity-form" onSubmit={submit}><fieldset className="form-section"><legend>班组基本信息</legend><p>负责人和成员必须来自正式人员档案，后续考勤只能登记本班组成员。</p><div className="form-grid"><label><span>班组名称<em>*</em></span><input name="name" required defaultValue={record?.name} /></label><label><span>班组状态</span><select name="status" defaultValue={record?.status || "active"}><option value="active">可接单</option><option value="busy">作业中</option><option value="inactive">已停用</option></select></label><label><span>班组负责人<em>*</em></span><select required value={leaderId} onChange={(event) => selectLeader(event.target.value)}><option value="">请选择正式人员</option>{workers.filter((item) => item.employmentStatus !== "inactive" || item.id === record?.leaderWorkerId).map((worker) => <option value={worker.id} key={worker.id}>{worker.name} · {worker.workerNo}</option>)}</select></label><label><span>联系电话</span><input name="contactPhone" type="tel" defaultValue={record?.contactPhone} /></label><label className="field-span"><span>服务范围<em>*</em></span><input name="serviceArea" required placeholder="例如：建阳区麻沙镇及周边乡镇" defaultValue={record?.serviceArea} /></label><label className="field-span"><span>班组技能</span><input name="skillCodes" placeholder="抚育、采伐、运输，多个用逗号分隔" defaultValue={record?.skillCodes.join("、")} /></label></div></fieldset><fieldset className="form-section"><legend>成员配置</legend><div className="labor-member-grid">{workers.filter((item) => item.employmentStatus !== "inactive" || members.includes(item.id)).map((worker) => <label key={worker.id} className={members.includes(worker.id) ? "selected" : ""}><input type="checkbox" checked={members.includes(worker.id)} onChange={(event) => setMembers((items) => event.target.checked ? [...new Set([...items, worker.id])] : worker.id === leaderId ? items : items.filter((id) => id !== worker.id))} /><span><strong>{worker.name}</strong><small>{worker.workerNo} · {worker.skillCodes.join("、") || "技能待补"}</small></span>{worker.id === leaderId && <em>负责人</em>}</label>)}</div>{!workers.length && <div className="empty-state compact"><strong>还没有可用人员</strong><p>请先在人员档案中新增劳务人员，再建立班组。</p></div>}<label className="field-span"><span>备注</span><textarea name="notes" rows={3} defaultValue={record?.notes} /></label></fieldset>{error && <p className="form-error">{error.message}</p>}<div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={pending || !leaderId || !members.length}>{pending ? "正在保存" : record ? "保存修改" : "保存班组档案"}</button></div></form>;
}

function JobCreateForm({ record, pending, error, onCancel, onSubmit }: { record?: LaborJob; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: LaborJobPayload) => void }) {
  const schedule = defaultSchedule();
  const [blocks, setBlocks] = useState<ForestBlockOption[]>(record?.blocks.map((block) => ({ id: block.id, code: block.code, name: block.code, location: "", areaMu: null, hasGeometry: true, riskLevel: null })) || []);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    onSubmit({ title: field(data, "title"), employerType: field(data, "employerType") as LaborJob["employerType"], employerId: field(data, "employerId"), employerName: field(data, "employerName"), workType: field(data, "workType") as LaborJob["workType"], requiredHeadcount: numberField(data, "requiredHeadcount"), unitPrice: numberField(data, "unitPrice"), priceUnit: field(data, "priceUnit") as LaborJob["priceUnit"], plannedStartAt: field(data, "plannedStartAt"), plannedEndAt: field(data, "plannedEndAt"), linkedBlockCodes: blocks.map((item) => item.code), instructions: field(data, "instructions") });
  };
  return <><form className="entity-form" onSubmit={submit}><fieldset className="form-section"><legend>用工需求</legend><p>这里建立的是任务草稿，发布后再从正式班组档案中匹配承接班组。</p><div className="form-grid"><label className="field-span"><span>任务名称<em>*</em></span><input name="title" required placeholder="例如：上屯村毛竹林冬季抚育" defaultValue={record?.title} /></label><label><span>发包方类型<em>*</em></span><select name="employerType" defaultValue={record?.employerType || "cooperative"}>{Object.entries(EMPLOYER_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>发包方名称<em>*</em></span><input name="employerName" required defaultValue={record?.employerName} /></label><label><span>发包方编号</span><input name="employerId" placeholder="可关联主体编号" defaultValue={record?.employerId} /></label><label><span>作业类型<em>*</em></span><select name="workType" defaultValue={record?.workType || "tending"}>{Object.entries(WORK_TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>需求人数<em>*</em></span><input name="requiredHeadcount" type="number" min="1" defaultValue={record?.requiredHeadcount ?? 5} required /></label><label><span>计价单价<em>*</em></span><input name="unitPrice" type="number" min="0" step="0.01" defaultValue={record?.unitPrice} required /></label><label><span>计价单位<em>*</em></span><select name="priceUnit" defaultValue={record?.priceUnit || "mu"}>{Object.entries(PRICE_UNIT_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>计划开始<em>*</em></span><input name="plannedStartAt" type="datetime-local" defaultValue={record ? localInput(new Date(record.plannedStartAt)) : schedule.start} required /></label><label><span>计划结束<em>*</em></span><input name="plannedEndAt" type="datetime-local" defaultValue={record ? localInput(new Date(record.plannedEndAt)) : schedule.end} required /></label><label className="field-span"><span>作业要求</span><textarea name="instructions" rows={4} placeholder="说明质量标准、安全要求、工器具和验收口径。" defaultValue={record?.instructions} /></label></div></fieldset><fieldset className="form-section"><legend>作业林班</legend><p>必须从正式林班空间台账选择，任务、考勤、结算和地图统计共同使用这组空间关系。</p><button className="relation-picker labor-block-picker" type="button" onClick={() => setSelectorOpen(true)}><span><MapPinned aria-hidden="true" /></span><div><small>关联林班</small><strong>{blocks.length ? `已选择 ${blocks.length} 个林班` : "尚未选择林班"}</strong></div><ChevronRight aria-hidden="true" /></button><div className="relation-chips">{blocks.map((block) => <span key={block.id}><strong>{block.name}</strong><small>{block.code}{block.areaMu == null ? "" : ` · ${block.areaMu} 亩`}</small><button type="button" aria-label={`移除 ${block.name}`} onClick={() => setBlocks((items) => items.filter((item) => item.id !== block.id))}><X aria-hidden="true" /></button></span>)}</div></fieldset>{error && <p className="form-error">{error.message}</p>}<div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={pending || !blocks.length}>{pending ? "正在保存" : record ? "保存修改" : "保存任务草稿"}</button></div></form><ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => setBlocks((items) => items.some((item) => item.id === block.id) ? items : [...items, block])} /></>;
}

function JobDetail({ record, teams, permissions, pending, error, onAction }: { record: LaborJob; teams: LaborTeam[]; permissions: { dispatch: boolean; operate: boolean; settle: boolean }; pending: boolean; error: Error | null; onAction: (action: string, payload?: LaborActionPayload) => void }) {
  const current = JOB_STATUS_ORDER.indexOf(record.status);
  return <div className="labor-detail"><div className="labor-detail-header"><div><JobStatusBadge status={record.status} /><span>{WORK_TYPE_LABELS[record.workType]}</span></div><strong>{record.jobNo}</strong></div><ol className="labor-progress">{JOB_STATUS_ORDER.map((value, index) => <li className={index < current ? "done" : index === current ? "current" : ""} key={value}><span>{index < current ? <CheckCircle2 aria-hidden="true" /> : index + 1}</span><small>{JOB_STATUS_LABELS[value]}</small></li>)}</ol><section className="labor-facts"><Detail label="发包方" value={`${record.employerName} · ${EMPLOYER_LABELS[record.employerType]}`} /><Detail label="计划周期" value={`${formatDateTime(record.plannedStartAt)} 至 ${formatDateTime(record.plannedEndAt)}`} /><Detail label="用工规模" value={`${record.requiredHeadcount} 人 · ${formatMoney(record.unitPrice)} ${PRICE_UNIT_LABELS[record.priceUnit]}`} /><Detail label="承接班组" value={record.teamName || "待匹配"} /><Detail label="合同编号" value={record.contractNo || "待签订"} /><Detail label="结算金额" value={record.settlementAmount == null ? "待结算" : formatMoney(record.settlementAmount)} /></section><section className="labor-blocks-section"><div className="section-heading"><span><MapPinned aria-hidden="true" /></span><div><h3>作业林班</h3><p>任务空间范围来自正式林班台账。</p></div></div><div className="relation-chips read-only">{record.blocks.map((block) => <span key={block.id}><strong>{block.code}</strong><small>正式关联林班</small></span>)}</div></section>{record.instructions && <section className="labor-description"><span>作业要求</span><p>{record.instructions}</p></section>}<LaborAttendanceTable record={record} /><LaborCurrentAction record={record} teams={teams} permissions={permissions} pending={pending} onAction={onAction} />{error && <p className="form-error">{error.message}</p>}<section className="labor-timeline"><div className="section-heading"><span><Clock3 aria-hidden="true" /></span><div><h3>办理时间轴</h3><p>任务状态、考勤和结算操作全部留痕。</p></div></div><ol>{[...record.timeline].reverse().map((item) => <li key={item.id}><span className="timeline-dot" /><div><strong>{laborActionLabel(item.action)}</strong><small>{item.actor} · {formatDateTime(item.createdAt)}</small><p>{item.note || "未填写办理说明"}</p></div></li>)}</ol></section></div>;
}

function LaborAttendanceTable({ record }: { record: LaborJob }) {
  return <section className="labor-attendance"><div className="section-heading"><span><ClipboardCheck aria-hidden="true" /></span><div><h3>考勤与工作量</h3><p>仅能登记当前承接班组的正式成员。</p></div></div>{record.attendance.length ? <div className="table-scroll"><table className="compact-ledger-table"><thead><tr><th>人员</th><th>日期</th><th>工时</th><th>工作量</th><th>核验人</th></tr></thead><tbody>{record.attendance.map((item) => <tr key={item.id}><td><strong>{item.workerName}</strong><small>{item.workerNo}</small></td><td>{item.workDate}</td><td>{item.workHours} 小时</td><td>{item.workQuantity ?? "-"}</td><td>{item.verifierName}</td></tr>)}</tbody></table></div> : <div className="empty-state compact"><strong>尚未登记考勤</strong><p>任务进入作业中后，按人员和日期记录工时与工作量。</p></div>}</section>;
}

function LaborCurrentAction({ record, teams, permissions, pending, onAction }: { record: LaborJob; teams: LaborTeam[]; permissions: { dispatch: boolean; operate: boolean; settle: boolean }; pending: boolean; onAction: (action: string, payload?: LaborActionPayload) => void }) {
  if (record.status === "draft" && permissions.dispatch) return <ActionCard title="发布用工需求" detail="发布后进入待匹配状态，由调度人员选择正式班组。"><button className="button primary" type="button" disabled={pending} onClick={() => onAction("publish")}><Send aria-hidden="true" />发布需求</button></ActionCard>;
  if (record.status === "published" && permissions.dispatch) return <ActionForm title="匹配承接班组" detail="班组必须来自正式班组台账，停用班组不可选择。" pending={pending} submitLabel="确认匹配" icon={UsersRound} fields={<><label className="field-span"><span>承接班组<em>*</em></span><select name="teamId" required defaultValue=""><option value="">请选择可用班组</option>{teams.map((team) => <option value={team.id} key={team.id}>{team.name} · {team.members.length} 人 · {TEAM_STATUS_LABELS[team.status]}</option>)}</select></label><label className="field-span"><span>匹配说明</span><textarea name="note" rows={3} /></label></>} onSubmit={(data) => onAction("match", { teamId: field(data, "teamId"), note: field(data, "note") })} />;
  if (record.status === "matched" && permissions.dispatch) return <ActionForm title="签订劳务合同" detail="合同生效后才能安排班组进场作业。" pending={pending} submitLabel="确认签约" icon={FileSignature} fields={<><label><span>合同编号<em>*</em></span><input name="contractNo" required /></label><label><span>合同开始<em>*</em></span><input name="contractStartAt" type="datetime-local" required defaultValue={localInput(new Date(record.plannedStartAt))} /></label><label><span>合同结束<em>*</em></span><input name="contractEndAt" type="datetime-local" required defaultValue={localInput(new Date(record.plannedEndAt))} /></label><label className="field-span"><span>付款约定</span><textarea name="paymentTerms" rows={3} placeholder="例如：验收后 10 个工作日内结算" /></label><label className="field-span"><span>签约说明</span><textarea name="note" rows={2} /></label></>} onSubmit={(data) => onAction("contract", { contractNo: field(data, "contractNo"), contractStartAt: field(data, "contractStartAt"), contractEndAt: field(data, "contractEndAt"), paymentTerms: field(data, "paymentTerms"), note: field(data, "note") })} />;
  if (record.status === "contracted" && permissions.operate) return <ActionCard title="班组进场作业" detail="确认进场后即可按人员登记每日考勤和工作量。"><button className="button primary" type="button" disabled={pending} onClick={() => onAction("start")}><Play aria-hidden="true" />确认进场</button></ActionCard>;
  if (record.status === "working" && permissions.operate) return <div className="labor-working-actions"><ActionForm title="登记人员考勤" detail="同一人员同一日期再次登记将更新原记录。" pending={pending} submitLabel="保存考勤" icon={CalendarDays} fields={<><label><span>班组成员<em>*</em></span><select name="workerId" required defaultValue=""><option value="">请选择人员</option>{(record.teamId ? recordAttendanceMembers(record, teams) : []).map((member) => <option value={member.id} key={member.id}>{member.name} · {member.workerNo}</option>)}</select></label><label><span>作业日期<em>*</em></span><input name="workDate" type="date" required defaultValue={new Date().toISOString().slice(0, 10)} /></label><label><span>有效工时<em>*</em></span><input name="workHours" type="number" min="0" max="24" step="0.5" required defaultValue="8" /></label><label><span>完成工作量</span><input name="workQuantity" type="number" min="0" step="0.01" /></label><label><span>签到时间</span><input name="checkInAt" type="datetime-local" /></label><label><span>签退时间</span><input name="checkOutAt" type="datetime-local" /></label><label className="field-span"><span>核验说明</span><textarea name="note" rows={2} /></label></>} onSubmit={(data) => onAction("attendance", { workerId: field(data, "workerId"), workDate: field(data, "workDate"), workHours: numberField(data, "workHours"), workQuantity: optionalNumberField(data, "workQuantity"), checkInAt: field(data, "checkInAt"), checkOutAt: field(data, "checkOutAt"), attendanceStatus: "present", note: field(data, "note") })} /><ActionForm title="提交完工记录" detail="至少登记一条考勤后才能提交结算。" pending={pending} submitLabel="提交结算" icon={ClipboardCheck} fields={<><label><span>实际完成量<em>*</em></span><input name="actualQuantity" type="number" min="0" step="0.01" required /></label><label className="field-span"><span>完工说明</span><textarea name="note" rows={3} /></label></>} onSubmit={(data) => onAction("submit", { actualQuantity: numberField(data, "actualQuantity"), note: field(data, "note") })} /></div>;
  if (record.status === "submitted" && permissions.settle) return <ActionForm title="核算工资并结算" detail="核对合同、考勤和实际工作量；可退回作业中补正。" pending={pending} submitLabel="确认结算" secondaryLabel="退回补正" icon={Coins} fields={<><label><span>结算金额(元)<em>*</em></span><input name="settlementAmount" type="number" min="0" step="0.01" required /></label><label className="field-span"><span>结算说明</span><textarea name="note" rows={3} placeholder="退回时必须填写原因" /></label></>} onSubmit={(data) => onAction("settle", { settlementAmount: numberField(data, "settlementAmount"), note: field(data, "note") })} onSecondary={(data) => onAction("return", { note: field(data, "note") })} />;
  if (record.status === "settled" && permissions.settle) return <ActionCard title="归档用工任务" detail="归档后保留合同、考勤、工资和林班关系，任务不再继续办理。"><button className="button primary" type="button" disabled={pending} onClick={() => onAction("close")}><ShieldCheck aria-hidden="true" />确认归档</button></ActionCard>;
  if (record.status === "closed") return <div className="labor-complete"><BadgeCheck aria-hidden="true" /><div><strong>用工任务已归档</strong><p>合同、考勤、完工与结算信息已形成完整留痕。</p></div></div>;
  return <div className="permission-note"><ShieldCheck aria-hidden="true" /><span><strong>当前环节无可执行操作</strong><small>办理按钮会根据任务状态和角色操作权限显示。</small></span></div>;
}

function WorkerDetail({ record }: { record: LaborWorker }) { return <div className="master-detail"><div className="master-detail-hero"><span><UserRound aria-hidden="true" /></span><div><h3>{record.name}</h3><p>{record.workerNo}</p></div><WorkerStatusBadge status={record.employmentStatus} /></div><dl className="master-detail-grid"><Detail label="手机号" value={record.mobile} /><Detail label="身份证脱敏号" value={record.idCardMask} /><Detail label="性别" value={record.gender} /><Detail label="培训状态" value={TRAINING_STATUS_LABELS[record.trainingStatus]} /><Detail label="信用分" value={record.creditScore} /><Detail label="紧急联系人" value={record.emergencyContact} /><Detail label="常住地址" value={record.homeAddress} /><Detail label="作业技能" value={record.skillCodes.join("、")} /><Detail label="资格证书" value={record.qualifications.join("、")} /><Detail label="备注" value={record.notes} /></dl></div>; }
function TeamDetail({ record }: { record: LaborTeam }) { return <div className="master-detail"><div className="master-detail-hero"><span><UsersRound aria-hidden="true" /></span><div><h3>{record.name}</h3><p>{record.teamNo}</p></div><TeamStatusBadge status={record.status} /></div><dl className="master-detail-grid"><Detail label="负责人" value={record.leaderName} /><Detail label="联系电话" value={record.contactPhone} /><Detail label="服务范围" value={record.serviceArea} /><Detail label="班组技能" value={record.skillCodes.join("、")} /><Detail label="成员数量" value={`${record.members.length} 人`} /><Detail label="备注" value={record.notes} /></dl><section className="team-member-list"><h3>班组成员</h3>{record.members.map((member) => <div key={member.id}><span className="avatar small">{member.name.slice(0, 1)}</span><span><strong>{member.name}</strong><small>{member.workerNo}</small></span><em>{member.role === "leader" ? "负责人" : "成员"}</em></div>)}</section></div>; }

function SummaryMetric({ label, value, detail, icon, tone = "neutral" }: { label: string; value: number; detail: string; icon: ReactNode; tone?: "neutral" | "active" | "warning" }) { return <div className={tone}><span>{icon}</span><div><small>{label}</small><strong>{value}</strong><em>{detail}</em></div></div>; }
function JobStatusBadge({ status }: { status: LaborJobStatus }) { const tone = status === "closed" ? "success" : status === "working" ? "active" : status === "submitted" || status === "settled" ? "warning" : "neutral"; return <span className={`labor-status ${tone}`}>{JOB_STATUS_LABELS[status]}</span>; }
function WorkerStatusBadge({ status }: { status: LaborWorker["employmentStatus"] }) { return <span className={`labor-status ${status === "available" ? "success" : status === "working" ? "active" : "neutral"}`}>{WORKER_STATUS_LABELS[status]}</span>; }
function TeamStatusBadge({ status }: { status: LaborTeam["status"] }) { return <span className={`labor-status ${status === "active" ? "success" : status === "busy" ? "active" : "neutral"}`}>{TEAM_STATUS_LABELS[status]}</span>; }
function TrainingBadge({ status }: { status: LaborWorker["trainingStatus"] }) { return <span className={`labor-status ${status === "valid" ? "success" : status === "expiring" ? "warning" : "danger"}`}>{TRAINING_STATUS_LABELS[status]}</span>; }
function Detail({ label, value }: { label: string; value: unknown }) { const text = String(value ?? "").trim() || "未填写"; return <div><dt>{label}</dt><dd>{text}</dd></div>; }
function ActionCard({ title, detail, children }: { title: string; detail: string; children: ReactNode }) { return <section className="labor-action-card"><div><span className="eyebrow">当前可办</span><h3>{title}</h3><p>{detail}</p></div><div className="form-actions">{children}</div></section>; }
function ActionForm({ title, detail, fields, pending, submitLabel, secondaryLabel, icon: Icon, onSubmit, onSecondary }: { title: string; detail: string; fields: ReactNode; pending: boolean; submitLabel: string; secondaryLabel?: string; icon: typeof Send; onSubmit: (data: FormData) => void; onSecondary?: (data: FormData) => void }) { const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); onSubmit(new FormData(event.currentTarget)); }; return <form className="labor-action-card" onSubmit={submit}><div><span className="eyebrow">当前可办</span><h3>{title}</h3><p>{detail}</p></div><div className="form-grid">{fields}</div><div className="form-actions">{secondaryLabel && <button className="button secondary" type="button" disabled={pending} onClick={(event) => onSecondary?.(new FormData(event.currentTarget.form!))}><RotateCcw aria-hidden="true" />{secondaryLabel}</button>}<button className="button primary" type="submit" disabled={pending}><Icon aria-hidden="true" />{pending ? "处理中" : submitLabel}</button></div></form>; }

function recordAttendanceMembers(record: LaborJob, teams: LaborTeam[]) { return teams.find((team) => team.id === record.teamId)?.members ?? []; }
async function invalidateLabor(client: ReturnType<typeof useQueryClient>) { await Promise.all([client.invalidateQueries({ queryKey: ["v2-labor-jobs"] }), client.invalidateQueries({ queryKey: ["v2-labor-workers"] }), client.invalidateQueries({ queryKey: ["v2-labor-teams"] }), client.invalidateQueries({ queryKey: ["v2-labor-worker-options"] }), client.invalidateQueries({ queryKey: ["v2-labor-team-options"] })]); }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function numberField(data: FormData, name: string) { const value = Number(data.get(name) || 0); return Number.isFinite(value) ? value : 0; }
function optionalNumberField(data: FormData, name: string) { const raw = field(data, name); if (!raw) return undefined; const value = Number(raw); return Number.isFinite(value) ? value : undefined; }
function listField(data: FormData, name: string) { return field(data, name).split(/[，,、]/).map((item) => item.trim()).filter(Boolean); }
function formatMoney(value: number) { return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 2 }).format(value); }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }); }
function localInput(date: Date) { if (Number.isNaN(date.valueOf())) return ""; const offset = date.getTimezoneOffset() * 60_000; return new Date(date.getTime() - offset).toISOString().slice(0, 16); }
function defaultSchedule() { const start = new Date(); start.setDate(start.getDate() + 3); start.setHours(8, 0, 0, 0); const end = new Date(start); end.setDate(end.getDate() + 7); end.setHours(18, 0, 0, 0); return { start: localInput(start), end: localInput(end) }; }
function laborActionLabel(action: string) { return ({ create: "建立任务", publish: "发布需求", match: "匹配班组", contract: "签订合同", start: "班组进场", attendance: "登记考勤", submit: "提交完工", return: "退回补正", settle: "工资结算", close: "任务归档" } as Record<string, string>)[action] || action; }
