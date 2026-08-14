import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, CircleDollarSign, Eye, Filter, Leaf, Pencil, Plus, RefreshCw, Search, Trash2, Trees, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { type FormEvent, type ReactNode, useDeferredValue, useEffect, useState } from "react";

import { api } from "../api/client";
import type { CarbonEstimatePayload, CarbonEstimateRecord, ForestBlockOption } from "../api/types";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 50;
type PanelState = { mode: "closed"; record: null } | { mode: "create"; record: null } | { mode: "view" | "edit"; record: CarbonEstimateRecord };
const CLOSED: PanelState = { mode: "closed", record: null };

export function CarbonEstimatesPage() {
  const queryClient = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [linkedBlock, setLinkedBlock] = useState<ForestBlockOption | null>(null);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [panel, setPanel] = useState<PanelState>(CLOSED);
  const deferredQ = useDeferredValue(q);
  const ledger = useQuery({
    queryKey: ["v2-carbon-estimates", deferredQ, status, linkedBlock?.code || "", offset],
    queryFn: () => api.carbonEstimates({ q: deferredQ, verificationStatus: status, linkedBlockCode: linkedBlock?.code, limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const permissions = capabilities.data?.permissions;
  const roles = capabilities.data?.principal.roles;
  const canCreate = hasPermission(permissions, roles, "business.carbonEstimates.create");
  const canUpdate = hasPermission(permissions, roles, "business.carbonEstimates.update");
  const canDelete = hasPermission(permissions, roles, "business.carbonEstimates.delete");
  const save = useMutation({
    mutationFn: ({ record, payload }: { record: CarbonEstimateRecord | null; payload: CarbonEstimatePayload }) =>
      record ? api.updateCarbonEstimate(record.id, payload) : api.createCarbonEstimate(payload),
    onSuccess: async () => { setPanel(CLOSED); await queryClient.invalidateQueries({ queryKey: ["v2-carbon-estimates"] }); },
  });
  const remove = useMutation({
    mutationFn: api.deleteCarbonEstimate,
    onSuccess: async () => { setPanel(CLOSED); await queryClient.invalidateQueries({ queryKey: ["v2-carbon-estimates"] }); },
  });
  const summary = ledger.data?.summary;

  return <div className="standard-page ledger-page carbon-page">
    <section className="page-heading ledger-heading">
      <div><span className="eyebrow">经营决策 / 碳汇运营</span><h1>碳汇项目与测算</h1><p>以正式林班为核算边界，管理碳储量、碳汇增量、项目核证和预计收益。</p></div>
      <div className="heading-actions"><button className="button secondary" type="button" onClick={() => ledger.refetch()}><RefreshCw aria-hidden="true" />刷新</button><button className="button primary" type="button" disabled={!canCreate} onClick={() => setPanel({ mode: "create", record: null })}><Plus aria-hidden="true" />新建项目</button></div>
    </section>

    <section className="metric-strip carbon-metrics" aria-label="碳汇测算汇总">
      <Metric icon={Trees} label="核算面积" value={formatNumber(summary?.accountingAreaMu)} unit="亩" />
      <Metric icon={Leaf} label="年碳汇量" value={formatNumber(summary?.annualSequestration)} unit="tCO2e" />
      <Metric icon={BadgeCheck} label="核证减排量" value={formatNumber(summary?.verifiedAmount)} unit="tCO2e" />
      <Metric icon={CircleDollarSign} label="预计收益" value={formatCurrency(summary?.estimatedRevenue)} unit="元" />
    </section>

    <section className="ledger-shell">
      <div className="ledger-toolbar">
        <label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索项目编号、名称或边界说明" /></label>
        <label className="compact-filter"><span>核证状态</span><select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}><option value="">全部状态</option><option value="calculating">测算中</option><option value="review">待复核</option><option value="verified">已核证</option><option value="rejected">未通过</option></select></label>
        <button className={`button secondary filter-button ${linkedBlock ? "active" : ""}`} type="button" onClick={() => setSelectorOpen(true)}><Filter aria-hidden="true" />{linkedBlock?.code || "按林班筛选"}</button>
        {(q || status || linkedBlock) && <button className="text-button" type="button" onClick={() => { setQ(""); setStatus(""); setLinkedBlock(null); setOffset(0); }}>清除条件</button>}
      </div>
      <QueryState loading={ledger.isLoading} error={ledger.error}>
        <div className="table-scroll"><table className="ledger-table carbon-table"><thead><tr><th>项目</th><th>核算类型 / 周期</th><th>核算林班</th><th>关键测算</th><th>核证状态</th><th>更新时间</th><th className="action-column">操作</th></tr></thead><tbody>
          {ledger.data?.items.map((record) => <tr key={record.id} onClick={() => setPanel({ mode: "view", record })}>
            <td><strong>{record.name}</strong><small>{record.projectCode}</small></td>
            <td><strong>{accountingLabel(record.accountingType)}</strong><small>{periodLabel(record)}</small></td>
            <td><strong>{record.linkedBlockCodes.length} 个林班</strong><small>{record.linkedBlockCodes.slice(0, 2).join("、")}</small></td>
            <td><strong>{formatNumber(record.annualSequestration)} tCO2e/年</strong><small>预计收益 {formatCurrency(record.estimatedRevenue)} 元</small></td>
            <td><StatusBadge status={record.verificationStatus} /></td><td>{formatDateTime(record.updatedAt)}</td>
            <td className="action-column"><div className="row-actions"><ActionButton label="查看" icon={Eye} onClick={() => setPanel({ mode: "view", record })} /><ActionButton label="编辑" icon={Pencil} disabled={!canUpdate} onClick={() => setPanel({ mode: "edit", record })} /><ActionButton label="删除" icon={Trash2} danger disabled={!canDelete || remove.isPending} onClick={() => confirmDelete(record, remove.mutate)} /></div></td>
          </tr>)}
          {!ledger.isLoading && !ledger.data?.items.length && <tr><td colSpan={7}><div className="table-empty"><Leaf aria-hidden="true" /><strong>暂无碳汇项目</strong><p>新建项目后，从正式林班台账选择核算边界并录入测算结果。</p></div></td></tr>}
        </tbody></table></div>
        <LedgerPagination total={ledger.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
      </QueryState>
    </section>

    <ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => { setLinkedBlock(block); setOffset(0); }} />
    <SidePanel open={panel.mode === "view"} eyebrow="碳汇项目详情" title={panel.record?.name || "项目详情"} onClose={() => setPanel(CLOSED)} footer={panel.record && canUpdate ? <button className="button primary" type="button" onClick={() => setPanel({ mode: "edit", record: panel.record! })}><Pencil aria-hidden="true" />编辑项目</button> : undefined}>{panel.record && <CarbonDetail record={panel.record} />}</SidePanel>
    <SidePanel wide open={panel.mode === "create" || panel.mode === "edit"} eyebrow="碳汇核算" title={panel.mode === "create" ? "新建碳汇项目" : `编辑 ${panel.record?.name || "项目"}`} onClose={() => !save.isPending && setPanel(CLOSED)}><CarbonForm record={panel.record} pending={save.isPending} error={save.error} onCancel={() => setPanel(CLOSED)} onSubmit={(payload) => save.mutate({ record: panel.record, payload })} /></SidePanel>
  </div>;
}

function CarbonForm({ record, pending, error, onCancel, onSubmit }: { record: CarbonEstimateRecord | null; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: CarbonEstimatePayload) => void }) {
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [links, setLinks] = useState<Array<{ code: string; name: string }>>([]);
  useEffect(() => setLinks((record?.linkedBlockCodes || []).map((code) => ({ code, name: code }))), [record]);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSubmit({
      projectCode: field(data, "projectCode"), name: field(data, "name"), accountingType: field(data, "accountingType") as CarbonEstimatePayload["accountingType"], verificationStatus: field(data, "verificationStatus") as CarbonEstimatePayload["verificationStatus"],
      projectBoundary: field(data, "projectBoundary"), methodology: field(data, "methodology"), accountingStartDate: field(data, "accountingStartDate"), accountingEndDate: field(data, "accountingEndDate"),
      accountingAreaMu: numberField(data, "accountingAreaMu"), carbonStock: numberField(data, "carbonStock"), annualSequestration: numberField(data, "annualSequestration"), verifiedAmount: numberField(data, "verifiedAmount"), carbonPrice: numberField(data, "carbonPrice"), estimatedRevenue: numberField(data, "estimatedRevenue"),
      verificationAgency: field(data, "verificationAgency"), verificationDate: field(data, "verificationDate"), beneficiary: field(data, "beneficiary"), notes: field(data, "notes"), linkedBlockCodes: links.map((item) => item.code),
    });
  };
  const addLink = (block: ForestBlockOption) => setLinks((current) => current.some((item) => item.code === block.code) ? current : [...current, { code: block.code, name: block.name }]);
  return <><form className="entity-form" onSubmit={submit}>
    <FormSection title="项目基础" description="项目编号用于跨年度追踪，核算边界应与关联林班范围一致。"><Field label="项目编号" required><input name="projectCode" required defaultValue={record?.projectCode || ""} placeholder="例如：CCER-ZS-2026-001" /></Field><Field label="项目名称" required><input name="name" required defaultValue={record?.name || ""} /></Field><Field label="核算类型" required><select name="accountingType" defaultValue={record?.accountingType || "project"}><option value="stock">碳储量</option><option value="increment">碳汇增量</option><option value="project">项目减排量</option></select></Field><Field label="核证状态" required><select name="verificationStatus" defaultValue={record?.verificationStatus || "calculating"}><option value="calculating">测算中</option><option value="review">待复核</option><option value="verified">已核证</option><option value="rejected">未通过</option></select></Field><Field label="项目边界说明" required span><input name="projectBoundary" required defaultValue={record?.projectBoundary || ""} placeholder="说明边界口径、林班范围或项目分区" /></Field><Field label="核算方法学" span><input name="methodology" defaultValue={record?.methodology || ""} placeholder="例如：竹林经营碳汇项目方法学" /></Field></FormSection>
    <FormSection title="核算周期与结果" description="数量统一使用 tCO2e；预计收益可按核证量和碳价填写。"><Field label="核算开始"><input type="date" name="accountingStartDate" defaultValue={record?.accountingStartDate || ""} /></Field><Field label="核算结束"><input type="date" name="accountingEndDate" defaultValue={record?.accountingEndDate || ""} /></Field><Field label="核算面积（亩）"><input type="number" min="0" step="0.01" name="accountingAreaMu" defaultValue={record?.accountingAreaMu ?? ""} /></Field><Field label="碳储量 / 减排量（tCO2e）"><input type="number" min="0" step="0.01" name="carbonStock" defaultValue={record?.carbonStock ?? ""} /></Field><Field label="年碳汇量（tCO2e）"><input type="number" min="0" step="0.01" name="annualSequestration" defaultValue={record?.annualSequestration ?? ""} /></Field><Field label="核证减排量（tCO2e）"><input type="number" min="0" step="0.01" name="verifiedAmount" defaultValue={record?.verifiedAmount ?? ""} /></Field><Field label="碳价（元/tCO2e）"><input type="number" min="0" step="0.01" name="carbonPrice" defaultValue={record?.carbonPrice ?? ""} /></Field><Field label="预计收益（元）"><input type="number" min="0" step="0.01" name="estimatedRevenue" defaultValue={record?.estimatedRevenue ?? ""} /></Field></FormSection>
    <FormSection title="核证与收益" description="核证机构、核证日期和收益主体用于形成项目管理闭环。"><Field label="核证机构"><input name="verificationAgency" defaultValue={record?.verificationAgency || ""} /></Field><Field label="核证日期"><input type="date" name="verificationDate" defaultValue={record?.verificationDate || ""} /></Field><Field label="收益主体"><input name="beneficiary" defaultValue={record?.beneficiary || ""} /></Field><Field label="测算说明" span><textarea name="notes" rows={4} defaultValue={record?.notes || ""} /></Field></FormSection>
    <FormSection title="关联林班" description="只能从正式林班台账选择，提交时后端会校验编号和当前账号数据范围。"><div className="relation-toolbar field-span"><button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}><Plus aria-hidden="true" />选择林班</button><span>{links.length ? `已选择 ${links.length} 个` : "至少选择 1 个林班"}</span></div><div className="relation-list field-span">{links.map((item) => <span className="relation-chip" key={item.code}><span><strong>{item.name}</strong><small>{item.code}</small></span><button type="button" aria-label={`移除 ${item.code}`} onClick={() => setLinks((current) => current.filter((link) => link.code !== item.code))}><X aria-hidden="true" /></button></span>)}{!links.length && <p className="relation-empty">尚未关联核算林班</p>}</div></FormSection>
    {error && <p className="form-error">{error.message}</p>}<div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={pending || !links.length}>{pending ? "保存中" : "保存项目"}</button></div>
  </form><ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={addLink} /></>;
}

function CarbonDetail({ record }: { record: CarbonEstimateRecord }) { return <div className="detail-stack"><DetailGroup title="项目概况"><Detail label="项目编号" value={record.projectCode} /><Detail label="核算类型" value={accountingLabel(record.accountingType)} /><Detail label="项目边界" value={record.projectBoundary} /><Detail label="核算方法学" value={record.methodology} /><Detail label="核算周期" value={periodLabel(record)} /><Detail label="核算面积" value={`${formatNumber(record.accountingAreaMu)} 亩`} /></DetailGroup><DetailGroup title="测算与核证"><Detail label="碳储量 / 减排量" value={`${formatNumber(record.carbonStock)} tCO2e`} /><Detail label="年碳汇量" value={`${formatNumber(record.annualSequestration)} tCO2e`} /><Detail label="核证减排量" value={`${formatNumber(record.verifiedAmount)} tCO2e`} /><Detail label="核证机构" value={record.verificationAgency} /><Detail label="碳价" value={`${formatNumber(record.carbonPrice)} 元/tCO2e`} /><Detail label="预计收益" value={`${formatCurrency(record.estimatedRevenue)} 元`} /></DetailGroup><section className="detail-group"><h3>关联林班</h3><div className="detail-relations">{record.linkedBlockCodes.map((code) => <span key={code}><Trees aria-hidden="true" />{code}</span>)}</div></section><DetailGroup title="项目留痕"><Detail label="收益主体" value={record.beneficiary} /><Detail label="测算说明" value={record.notes} /><Detail label="创建时间" value={formatDateTime(record.createdAt)} /><Detail label="更新时间" value={formatDateTime(record.updatedAt)} /></DetailGroup></div>; }
function Metric({ icon: Icon, label, value, unit }: { icon: LucideIcon; label: string; value: string; unit: string }) { return <div className="metric"><Icon aria-hidden="true" /><span><small>{label}</small><strong>{value}</strong><em>{unit}</em></span></div>; }
function StatusBadge({ status }: { status: CarbonEstimateRecord["verificationStatus"] }) { const tone = status === "verified" ? "success" : status === "rejected" ? "danger" : "warning"; return <span className={`status-badge ${tone}`}>{statusLabel(status)}</span>; }
function ActionButton({ label, icon: Icon, onClick, disabled = false, danger = false }: { label: string; icon: LucideIcon; onClick: () => void; disabled?: boolean; danger?: boolean }) { return <button className={`icon-button ${danger ? "danger" : ""}`} type="button" disabled={disabled} aria-label={label} title={label} onClick={(event) => { event.stopPropagation(); onClick(); }}><Icon aria-hidden="true" /></button>; }
function FormSection({ title, description, children }: { title: string; description: string; children: ReactNode }) { return <fieldset className="form-section"><legend>{title}</legend><p>{description}</p><div className="form-grid">{children}</div></fieldset>; }
function Field({ label, children, required = false, span = false }: { label: string; children: ReactNode; required?: boolean; span?: boolean }) { return <label className={span ? "field-span" : ""}><span>{label}{required && <em>*</em>}</span>{children}</label>; }
function DetailGroup({ title, children }: { title: string; children: ReactNode }) { return <section className="detail-group"><h3>{title}</h3><dl>{children}</dl></section>; }
function Detail({ label, value }: { label: string; value: unknown }) { const text = String(value ?? "").trim() || "未填写"; return <div><dt>{label}</dt><dd>{text}</dd></div>; }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function numberField(data: FormData, name: string) { const value = field(data, name); return value ? Number(value) : null; }
function formatNumber(value: number | null | undefined) { return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 2 }); }
function formatCurrency(value: number | null | undefined) { return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 2 }); }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false }); }
function periodLabel(record: CarbonEstimateRecord) { return record.accountingStartDate || record.accountingEndDate ? `${record.accountingStartDate || "未定"} 至 ${record.accountingEndDate || "未定"}` : "核算周期待补充"; }
function accountingLabel(value: CarbonEstimateRecord["accountingType"]) { return ({ stock: "碳储量", increment: "碳汇增量", project: "项目减排量" } as const)[value]; }
function statusLabel(value: CarbonEstimateRecord["verificationStatus"]) { return ({ calculating: "测算中", review: "待复核", verified: "已核证", rejected: "未通过" } as const)[value]; }
function confirmDelete(record: CarbonEstimateRecord, remove: (id: string) => void) { if (window.confirm(`确认删除碳汇项目“${record.name}”？\n记录将进入软删除状态。`)) remove(record.id); }
