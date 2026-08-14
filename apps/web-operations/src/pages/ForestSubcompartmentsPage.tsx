import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Eye,
  Download,
  Filter,
  Layers3,
  Link2,
  MapPinned,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { type FormEvent, type ReactNode, useDeferredValue, useState } from "react";

import { api, downloadFile } from "../api/client";
import type {
  ForestBlockOption,
  ForestSubcompartmentPayload,
  ForestSubcompartmentRecord,
} from "../api/types";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { SpatialVersionHistory } from "../components/SpatialVersionHistory";
import { SubcompartmentBoundaryEditor } from "../components/SubcompartmentBoundaryEditor";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 50;

type PanelState =
  | { mode: "closed"; record: null }
  | { mode: "view" | "edit"; record: ForestSubcompartmentRecord }
  | { mode: "create"; record: null };

const EMPTY_PANEL: PanelState = { mode: "closed", record: null };

export function ForestSubcompartmentsPage() {
  const queryClient = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const [managementStatus, setManagementStatus] = useState("");
  const [parentFilter, setParentFilter] = useState<ForestBlockOption | null>(null);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [panel, setPanel] = useState<PanelState>(EMPTY_PANEL);
  const [exporting, setExporting] = useState(false);
  const deferredQ = useDeferredValue(q);
  const query = useQuery({
    queryKey: ["v2-forest-subcompartment-ledger", deferredQ, riskLevel, managementStatus, parentFilter?.id, offset],
    queryFn: () => api.forestSubcompartmentLedger({
      q: deferredQ,
      riskLevel,
      managementStatus,
      forestBlockId: parentFilter?.id,
      limit: PAGE_SIZE,
      offset,
    }),
    placeholderData: (previous) => previous,
  });
  const permissions = capabilities.data?.permissions;
  const roles = capabilities.data?.principal.roles;
  const canCreate = hasPermission(permissions, roles, "forest.subcompartments.create");
  const canUpdate = hasPermission(permissions, roles, "forest.subcompartments.update");
  const canDelete = hasPermission(permissions, roles, "forest.subcompartments.delete");
  const canRollback = hasPermission(permissions, roles, "forest.subcompartments.rollback");
  const canExport = hasPermission(permissions, roles, "forest.subcompartments.export");
  const exportHref = `/api/v2/resources/forest-subcompartments-export.csv?${new URLSearchParams({
    q: deferredQ,
    riskLevel,
    managementStatus,
    forestBlockId: parentFilter?.id || "",
  }).toString()}`;

  const save = useMutation({
    mutationFn: ({ record, payload }: { record: ForestSubcompartmentRecord | null; payload: ForestSubcompartmentPayload }) => {
      if (!record) return api.createForestSubcompartment(payload);
      const { subcompartmentCode: _code, ...changes } = payload;
      return api.updateForestSubcompartment(record.id, {
        ...changes,
        expectedVersion: record.version,
      });
    },
    onSuccess: async () => {
      setPanel(EMPTY_PANEL);
      await queryClient.invalidateQueries({ queryKey: ["v2-forest-subcompartment-ledger"] });
    },
  });
  const remove = useMutation({
    mutationFn: api.deleteForestSubcompartment,
    onSuccess: async () => {
      setPanel(EMPTY_PANEL);
      await queryClient.invalidateQueries({ queryKey: ["v2-forest-subcompartment-ledger"] });
    },
  });

  const clearFilters = () => {
    setQ("");
    setRiskLevel("");
    setManagementStatus("");
    setParentFilter(null);
    setOffset(0);
  };
  const hasFilters = Boolean(q || riskLevel || managementStatus || parentFilter);

  return (
    <div className="standard-page ledger-page">
      <section className="page-heading ledger-heading">
        <div><span className="eyebrow">资源数据 / 作业单元</span><h1>小班台账</h1><p>小班是林班内部最小经营作业单元；位置与区划继承父林班，资源调查属性独立维护。</p></div>
        <div className="heading-actions">
          <button className="button secondary" type="button" onClick={() => query.refetch()}><RefreshCw aria-hidden="true" />刷新</button>
          <button className="button secondary" type="button" disabled={!canExport || exporting} title={canExport ? "导出当前筛选结果" : "当前角色无导出权限"} onClick={async () => { setExporting(true); try { await downloadFile(exportHref, "小班台账.csv"); } finally { setExporting(false); } }}><Download aria-hidden="true" />{exporting ? "正在导出" : "导出台账"}</button>
          <button className="button primary" type="button" disabled={!canCreate} onClick={() => setPanel({ mode: "create", record: null })} title={canCreate ? "新增小班" : "当前角色无新增权限"}><Plus aria-hidden="true" />新增小班</button>
        </div>
      </section>

      <section className="ledger-shell">
        <div className="ledger-toolbar">
          <label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索小班编号、名称、竹种或父林班" /></label>
          <label className="compact-filter"><span>风险等级</span><select value={riskLevel} onChange={(event) => { setRiskLevel(event.target.value); setOffset(0); }}><option value="">全部风险</option><option value="low">低风险</option><option value="medium">中风险</option><option value="high">高风险</option><option value="低">低</option><option value="中">中</option><option value="高">高</option></select></label>
          <button className={`button secondary filter-button ${advancedOpen ? "active" : ""}`} type="button" onClick={() => setAdvancedOpen((value) => !value)}><Filter aria-hidden="true" />更多筛选</button>
          {hasFilters && <button className="text-button" type="button" onClick={clearFilters}>清除条件</button>}
        </div>
        {advancedOpen && (
          <div className="advanced-filters">
            <label><span>经营状态</span><select value={managementStatus} onChange={(event) => { setManagementStatus(event.target.value); setOffset(0); }}><option value="">全部状态</option><option value="active">经营中</option><option value="resting">休养中</option><option value="planned">待作业</option><option value="closed">已停用</option></select></label>
            <div className="relation-picker field-span">
              <span><MapPinned aria-hidden="true" /></span>
              <div><small>父林班筛选</small><strong>{parentFilter ? `${parentFilter.name} · ${parentFilter.code}` : "全部林班"}</strong></div>
              {parentFilter && <button className="text-button" type="button" onClick={() => { setParentFilter(null); setOffset(0); }}>清除</button>}
              <button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}>选择林班</button>
            </div>
          </div>
        )}

        <QueryState loading={query.isLoading} error={query.error}>
          <div className="table-scroll">
            <table className="ledger-table">
              <thead><tr><th>小班</th><th>所属林班与区划</th><th>资源调查</th><th>经营状态</th><th>更新时间</th><th className="action-column">操作</th></tr></thead>
              <tbody>
                {query.data?.items.map((record) => (
                  <tr key={record.id} onClick={() => setPanel({ mode: "view", record })}>
                    <td><strong>{record.subcompartmentCode}</strong><small>{record.name}</small></td>
                    <td><strong>{record.forestBlockCode} · {record.forestBlockName}</strong><small>{locationLabel(record) || "行政区划继承中"} · {formatArea(record.areaMu)}</small></td>
                    <td><strong>{record.bambooSpecies || record.forestCategory || "资源属性待补"}</strong><small>{[record.origin, record.ageGroup, record.qualityGrade].filter(Boolean).join(" / ") || "调查指标待补充"}</small></td>
                    <td><StatusBadge status={record.managementStatus} risk={record.riskLevel} /></td>
                    <td>{formatDateTime(record.updatedAt)}</td>
                    <td className="action-column"><div className="row-actions">
                      <ActionButton label="查看" icon={Eye} onClick={() => setPanel({ mode: "view", record })} />
                      <ActionButton label="编辑" icon={Pencil} disabled={!canUpdate} onClick={() => setPanel({ mode: "edit", record })} />
                      <ActionButton label="删除" icon={Trash2} danger disabled={!canDelete || remove.isPending} onClick={() => confirmDelete(record, remove.mutate)} />
                    </div></td>
                  </tr>
                ))}
                {!query.isLoading && !query.data?.items.length && <tr><td colSpan={6}><div className="table-empty"><Layers3 aria-hidden="true" /><strong>当前条件下没有小班</strong><p>{hasFilters ? "请清除筛选条件后重试。" : "先建立林班，再新增该林班下的经营小班。"}</p></div></td></tr>}
              </tbody>
            </table>
          </div>
          <LedgerPagination total={query.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
        </QueryState>
      </section>

      <ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => { setParentFilter(block); setOffset(0); }} />
      <SidePanel open={panel.mode === "view"} eyebrow="经营作业单元" title={panel.record?.name || "小班详情"} onClose={() => setPanel(EMPTY_PANEL)} footer={panel.record && canUpdate ? <button className="button primary" type="button" onClick={() => setPanel({ mode: "edit", record: panel.record! })}><Pencil aria-hidden="true" />编辑小班</button> : undefined}>
        {panel.record && <ForestSubcompartmentDetail record={panel.record} canRollback={canRollback} onRestored={async () => {
          setPanel(EMPTY_PANEL);
          await queryClient.invalidateQueries({ queryKey: ["v2-forest-subcompartment-ledger"] });
          await queryClient.invalidateQueries({ queryKey: ["forest-block-map"] });
        }} />}
      </SidePanel>
      <SidePanel wide open={panel.mode === "create" || panel.mode === "edit"} eyebrow={panel.mode === "create" ? "建立经营作业单元" : "维护小班调查属性"} title={panel.mode === "create" ? "新增小班" : `编辑 ${panel.record?.subcompartmentCode || "小班"}`} onClose={() => !save.isPending && setPanel(EMPTY_PANEL)}>
        <ForestSubcompartmentForm record={panel.record} pending={save.isPending} error={save.error} onCancel={() => setPanel(EMPTY_PANEL)} onSubmit={(payload) => save.mutate({ record: panel.record, payload })} />
      </SidePanel>
    </div>
  );
}

function ForestSubcompartmentForm({ record, pending, error, onCancel, onSubmit }: { record: ForestSubcompartmentRecord | null; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: ForestSubcompartmentPayload) => void }) {
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [relationError, setRelationError] = useState("");
  const [parent, setParent] = useState<ForestBlockOption | null>(() => record ? ({ id: record.forestBlockId, code: record.forestBlockCode, name: record.forestBlockName, location: locationLabel(record), areaMu: null, hasGeometry: false, riskLevel: null }) : null);
  const [geometry, setGeometry] = useState<Record<string, unknown> | null>(() => record?.geometry || null);
  const parentDetail = useQuery({
    queryKey: ["forest-block-detail", parent?.id],
    queryFn: () => api.forestBlockDetail(parent!.id),
    enabled: Boolean(parent?.id),
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!parent) { setRelationError("请选择一个正式林班作为父级。"); return; }
    setRelationError("");
    const data = new FormData(event.currentTarget);
    onSubmit({
      subcompartmentCode: field(data, "subcompartmentCode"),
      name: field(data, "name"),
      forestBlockId: parent.id,
      areaMu: numberField(data, "areaMu"),
      landCategory: nullableField(data, "landCategory"),
      forestCategory: nullableField(data, "forestCategory"),
      origin: nullableField(data, "origin"),
      ageGroup: nullableField(data, "ageGroup"),
      bambooSpecies: nullableField(data, "bambooSpecies"),
      slopeDegree: numberField(data, "slopeDegree"),
      aspect: nullableField(data, "aspect"),
      elevationM: numberField(data, "elevationM"),
      qualityGrade: nullableField(data, "qualityGrade"),
      healthStatus: nullableField(data, "healthStatus"),
      riskLevel: nullableField(data, "riskLevel"),
      managementStatus: nullableField(data, "managementStatus"),
      tags: field(data, "tags").split(/[,，]/).map((item) => item.trim()).filter(Boolean),
      geometry,
    });
  };
  return <>
    <form className="entity-form" onSubmit={submit}>
      <fieldset className="form-section relation-section">
        <legend>所属林班</legend><p>必须从现有林班台账选择。小班自动继承林班的县、乡镇和村级区划。</p>
        <div className="relation-picker">
          <span><Link2 aria-hidden="true" /></span>
          <div><small>父级空间单元</small><strong>{parent ? `${parent.name} · ${parent.code}` : "尚未选择林班"}</strong></div>
          {parent && <button className="icon-button" type="button" onClick={() => setParent(null)} aria-label="清除父林班" title="清除父林班"><Trash2 aria-hidden="true" /></button>}
          <button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}>{parent ? "更换林班" : "选择林班"}</button>
        </div>
        {relationError && <p className="form-error">{relationError}</p>}
      </fieldset>
      <fieldset className="form-section boundary-section">
        <legend>空间边界</legend>
        <p>以父林班边界为约束，可直接描绘、修改节点，或导入 GIS GeoJSON 面数据。边界未补齐时也可先保存属性。</p>
        {parentDetail.isLoading && <div className="boundary-warning">正在读取父林班空间边界...</div>}
        {parent && !parentDetail.isLoading && <SubcompartmentBoundaryEditor parentGeometry={parentDetail.data?.geometry || null} value={geometry} onChange={setGeometry} />}
        {!parent && <div className="boundary-empty"><MapPinned aria-hidden="true" /><strong>请先选择父林班</strong><span>选择后才能加载参照边界并进行小班划界。</span></div>}
      </fieldset>
      <FormSection title="基础信息" description="小班编号创建后不可修改，确保作业、巡护和调查数据稳定关联。">
        <Field label="小班编号" required><input name="subcompartmentCode" required readOnly={Boolean(record)} defaultValue={record?.subcompartmentCode || ""} placeholder="例如：003-7-1" /></Field>
        <Field label="小班名称" required><input name="name" required defaultValue={record?.name || ""} placeholder="例如：上屯村毛竹经营小班" /></Field>
        <Field label="面积（亩）"><input name="areaMu" type="number" min="0" step="0.01" defaultValue={record?.areaMu ?? ""} /></Field>
        <Field label="经营状态"><select name="managementStatus" defaultValue={record?.managementStatus || "active"}><option value="active">经营中</option><option value="planned">待作业</option><option value="resting">休养中</option><option value="closed">已停用</option></select></Field>
      </FormSection>
      <FormSection title="资源调查" description="记录小班自身的林分、起源、龄组和质量情况，不在这里维护权属凭证。">
        <Field label="地类"><input name="landCategory" defaultValue={record?.landCategory || ""} placeholder="例如：竹林地" /></Field>
        <Field label="森林类别"><input name="forestCategory" defaultValue={record?.forestCategory || ""} placeholder="例如：商品林" /></Field>
        <Field label="竹种"><input name="bambooSpecies" defaultValue={record?.bambooSpecies || ""} placeholder="例如：毛竹" /></Field>
        <Field label="起源"><input name="origin" defaultValue={record?.origin || ""} placeholder="天然 / 人工" /></Field>
        <Field label="龄组"><input name="ageGroup" defaultValue={record?.ageGroup || ""} /></Field>
        <Field label="质量等级"><input name="qualityGrade" defaultValue={record?.qualityGrade || ""} /></Field>
        <Field label="健康状态"><input name="healthStatus" defaultValue={record?.healthStatus || ""} /></Field>
        <Field label="风险等级"><select name="riskLevel" defaultValue={record?.riskLevel || "low"}><option value="low">低风险</option><option value="medium">中风险</option><option value="high">高风险</option></select></Field>
      </FormSection>
      <FormSection title="立地条件" description="用于经营方案、采伐设计和产量分析。">
        <Field label="坡度（度）"><input name="slopeDegree" type="number" min="0" max="90" step="0.1" defaultValue={record?.slopeDegree ?? ""} /></Field>
        <Field label="坡向"><input name="aspect" defaultValue={record?.aspect || ""} /></Field>
        <Field label="海拔（米）"><input name="elevationM" type="number" step="0.1" defaultValue={record?.elevationM ?? ""} /></Field>
        <Field label="资源标签"><input name="tags" defaultValue={record?.tags.join("，") || ""} placeholder="多个标签使用逗号分隔" /></Field>
      </FormSection>
      {error && <p className="form-error">{error.message}</p>}
      <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={pending}>{pending ? "保存中" : record ? "保存修改" : "创建小班"}</button></div>
    </form>
    <ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => {
      if (parent?.id !== block.id) setGeometry(null);
      setParent(block);
      setRelationError("");
    }} />
  </>;
}

function ForestSubcompartmentDetail({ record, canRollback, onRestored }: { record: ForestSubcompartmentRecord; canRollback: boolean; onRestored: () => Promise<void> }) {
  return <div className="detail-stack">
    <DetailGroup title="空间关系"><Detail label="小班编号" value={record.subcompartmentCode} /><Detail label="小班名称" value={record.name} /><Detail label="父林班" value={`${record.forestBlockCode} · ${record.forestBlockName}`} /><Detail label="行政区划" value={locationLabel(record)} /><Detail label="面积" value={formatArea(record.areaMu)} /><Detail label="边界" value={record.geometry ? "已入库" : "待补图"} /></DetailGroup>
    <DetailGroup title="资源调查"><Detail label="地类" value={record.landCategory} /><Detail label="森林类别" value={record.forestCategory} /><Detail label="竹种" value={record.bambooSpecies} /><Detail label="起源" value={record.origin} /><Detail label="龄组" value={record.ageGroup} /><Detail label="质量等级" value={record.qualityGrade} /><Detail label="健康状态" value={record.healthStatus} /><Detail label="风险等级" value={riskLabel(record.riskLevel)} /></DetailGroup>
    <DetailGroup title="立地条件"><Detail label="坡度" value={record.slopeDegree == null ? "" : `${record.slopeDegree}°`} /><Detail label="坡向" value={record.aspect} /><Detail label="海拔" value={record.elevationM == null ? "" : `${record.elevationM} 米`} /><Detail label="经营状态" value={managementLabel(record.managementStatus)} /></DetailGroup>
    <DetailGroup title="数据留痕"><Detail label="版本" value={`v${record.version}`} /><Detail label="创建人" value={record.createdBy} /><Detail label="来源批次" value={record.sourceBatchId} /><Detail label="创建时间" value={formatDateTime(record.createdAt)} /><Detail label="更新时间" value={formatDateTime(record.updatedAt)} /></DetailGroup>
    <SpatialVersionHistory entityId={record.id} queryKey="forest-subcompartment-versions" currentVersion={record.version} canRollback={canRollback} load={() => api.forestSubcompartmentVersions(record.id)} rollback={(versionId) => api.rollbackForestSubcompartment(record.id, versionId, record.version)} onRestored={onRestored} />
  </div>;
}

function ActionButton({ label, icon: Icon, onClick, disabled = false, danger = false }: { label: string; icon: typeof Eye; onClick: () => void; disabled?: boolean; danger?: boolean }) { return <button className={`icon-button ${danger ? "danger" : ""}`} type="button" disabled={disabled} aria-label={label} title={label} onClick={(event) => { event.stopPropagation(); onClick(); }}><Icon aria-hidden="true" /></button>; }
function StatusBadge({ status, risk }: { status: string | null; risk: string | null }) { const tone = risk === "high" || risk === "高" ? "danger" : status === "active" ? "success" : "warning"; return <span className={`status-badge ${tone}`}>{managementLabel(status)}</span>; }
function FormSection({ title, description, children }: { title: string; description: string; children: ReactNode }) { return <fieldset className="form-section"><legend>{title}</legend><p>{description}</p><div className="form-grid">{children}</div></fieldset>; }
function Field({ label, children, required = false }: { label: string; children: ReactNode; required?: boolean }) { return <label><span>{label}{required && <em>*</em>}</span>{children}</label>; }
function DetailGroup({ title, children }: { title: string; children: ReactNode }) { return <section className="detail-group"><h3>{title}</h3><dl>{children}</dl></section>; }
function Detail({ label, value }: { label: string; value: unknown }) { const text = String(value ?? "").trim() || "未填写"; return <div><dt>{label}</dt><dd>{text}</dd></div>; }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function nullableField(data: FormData, name: string) { return field(data, name) || null; }
function numberField(data: FormData, name: string) { const value = field(data, name); return value ? Number(value) : null; }
function locationLabel(record: Pick<ForestSubcompartmentRecord, "countyName" | "townName" | "villageName">) { return [record.countyName, record.townName, record.villageName].filter(Boolean).join(" / "); }
function formatArea(value: number | null) { return value == null ? "面积待核定" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })} 亩`; }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false }); }
function managementLabel(value: string | null) { return ({ active: "经营中", planned: "待作业", resting: "休养中", closed: "已停用" } as Record<string, string>)[value || ""] || value || "状态待补"; }
function riskLabel(value: string | null) { return ({ low: "低风险", medium: "中风险", high: "高风险" } as Record<string, string>)[value || ""] || value || "未评估"; }
function confirmDelete(record: ForestSubcompartmentRecord, remove: (id: string) => void) { if (window.confirm(`确认删除小班“${record.name}”？\n该操作为软删除，不会删除所属林班。`)) remove(record.id); }
