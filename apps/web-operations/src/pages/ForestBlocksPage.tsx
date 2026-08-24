import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  Eye,
  Download,
  FileUp,
  Filter,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { type FormEvent, type ReactNode, useDeferredValue, useMemo, useState } from "react";

import { api, downloadFile } from "../api/client";
import type { ForestBlockPayload, ForestBlockRecord } from "../api/types";
import { BoundaryEditor } from "../components/SubcompartmentBoundaryEditor";
import { AdministrativeDivisionSelector } from "../components/AdministrativeDivisionSelector";
import { LedgerPagination } from "../components/LedgerPagination";
import { LedgerSummaryStrip } from "../components/LedgerSummaryStrip";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { SpatialVersionHistory } from "../components/SpatialVersionHistory";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 50;

type PanelState =
  | { mode: "closed"; record: null }
  | { mode: "view" | "edit"; record: ForestBlockRecord }
  | { mode: "create"; record: null };

const EMPTY_PANEL: PanelState = { mode: "closed", record: null };

export function ForestBlocksPage() {
  const queryClient = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const [baseType, setBaseType] = useState("");
  const [operationType, setOperationType] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [panel, setPanel] = useState<PanelState>(EMPTY_PANEL);
  const [exporting, setExporting] = useState(false);
  const deferredQ = useDeferredValue(q);
  const query = useQuery({
    queryKey: ["v2-forest-block-ledger", deferredQ, riskLevel, baseType, operationType, offset],
    queryFn: () => api.forestBlockLedger({
      q: deferredQ,
      riskLevel,
      baseType,
      operationType,
      limit: PAGE_SIZE,
      offset,
    }),
    placeholderData: (previous) => previous,
  });
  const permissions = capabilities.data?.permissions;
  const roles = capabilities.data?.principal.roles;
  const canCreate = hasPermission(permissions, roles, "forest.blocks.create");
  const canUpdate = hasPermission(permissions, roles, "forest.blocks.update");
  const canDelete = hasPermission(permissions, roles, "forest.blocks.delete");
  const canRollback = hasPermission(permissions, roles, "forest.blocks.rollback");
  const canExport = hasPermission(permissions, roles, "forest.blocks.export");
  const exportHref = `/api/v2/resources/forest-blocks-export.csv?${new URLSearchParams({
    q: deferredQ,
    riskLevel,
    baseType,
    operationType,
  }).toString()}`;
  const summary = useMemo(() => {
    const items = query.data?.items ?? [];
    return [
      { label: "林班总数", value: query.data?.total ?? 0, detail: "当前权限范围" },
      { label: "本页面积", value: `${items.reduce((sum, item) => sum + Number(item.areaMu || 0), 0).toFixed(1)} 亩`, detail: "当前筛选页合计" },
      { label: "已入图", value: items.filter((item) => item.geometry).length, detail: "本页具备空间边界", tone: "active" as const },
      { label: "高风险", value: items.filter((item) => ["high", "高"].includes(String(item.riskLevel))).length, detail: "本页重点关注", tone: "warning" as const },
    ];
  }, [query.data]);

  const save = useMutation({
    mutationFn: ({ record, payload }: { record: ForestBlockRecord | null; payload: ForestBlockPayload }) =>
      record
        ? api.updateForestBlock(record.id, withoutImmutableBlockFields(payload))
        : api.createForestBlock(payload),
    onSuccess: async () => {
      setPanel(EMPTY_PANEL);
      await queryClient.invalidateQueries({ queryKey: ["v2-forest-block-ledger"] });
      await queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    },
  });
  const remove = useMutation({
    mutationFn: api.deleteForestBlock,
    onSuccess: async () => {
      setPanel(EMPTY_PANEL);
      await queryClient.invalidateQueries({ queryKey: ["v2-forest-block-ledger"] });
      await queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    },
  });

  const resetFilters = () => {
    setQ("");
    setRiskLevel("");
    setBaseType("");
    setOperationType("");
    setOffset(0);
  };

  return (
    <div className="standard-page ledger-page">
      <section className="page-heading ledger-heading">
        <div><span className="eyebrow">资源数据 / 空间资源</span><h1>林班台账</h1><p>管理林地位置、区划、面积、竹林资源与空间边界，不保存林权法律字段。</p></div>
        <div className="heading-actions">
          <button className="button secondary" type="button" onClick={() => query.refetch()}><RefreshCw aria-hidden="true" />刷新</button>
          <button className="button secondary" type="button" disabled={!canExport || exporting} title={canExport ? "导出当前筛选结果" : "当前角色无导出权限"} onClick={async () => { setExporting(true); try { await downloadFile(exportHref, "林班台账.csv"); } finally { setExporting(false); } }}><Download aria-hidden="true" />{exporting ? "正在导出" : "导出台账"}</button>
          <Link className="button secondary" to="/resources/imports"><FileUp aria-hidden="true" />批量导入</Link>
          <button className="button primary" type="button" disabled={!canCreate} onClick={() => setPanel({ mode: "create", record: null })} title={canCreate ? "新增林班" : "当前角色无新增权限"}><Plus aria-hidden="true" />新增林班</button>
        </div>
      </section>

      <LedgerSummaryStrip metrics={summary} />

      <section className="ledger-shell">
        <div className="ledger-toolbar">
          <label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索林班编号、名称、县乡村或竹种" /></label>
          <label className="compact-filter"><span>风险等级</span><select value={riskLevel} onChange={(event) => { setRiskLevel(event.target.value); setOffset(0); }}><option value="">全部风险</option><option value="low">低风险</option><option value="medium">中风险</option><option value="high">高风险</option><option value="低">低</option><option value="中">中</option><option value="高">高</option></select></label>
          <button className={`button secondary filter-button ${advancedOpen ? "active" : ""}`} type="button" onClick={() => setAdvancedOpen((value) => !value)}><Filter aria-hidden="true" />更多筛选</button>
          {(q || riskLevel || baseType || operationType) && <button className="text-button" type="button" onClick={resetFilters}>清除条件</button>}
        </div>
        {advancedOpen && (
          <div className="advanced-filters">
            <label><span>基地类型</span><input value={baseType} onChange={(event) => { setBaseType(event.target.value); setOffset(0); }} placeholder="例如：示范基地" /></label>
            <label><span>经营类型</span><input value={operationType} onChange={(event) => { setOperationType(event.target.value); setOffset(0); }} placeholder="例如：合作经营" /></label>
            <p>高级筛选只影响当前账号可见数据，不会改变台账内容。</p>
          </div>
        )}

        <QueryState loading={query.isLoading} error={query.error}>
          <div className="table-scroll">
            <table className="ledger-table">
              <thead><tr><th>林班</th><th>区划与面积</th><th>资源经营</th><th>图形状态</th><th>更新时间</th><th className="action-column">操作</th></tr></thead>
              <tbody>
                {query.data?.items.map((record) => (
                  <tr key={record.id} onClick={() => setPanel({ mode: "view", record })}>
                    <td><strong>{record.blockCode}</strong><small>{record.name}</small></td>
                    <td><strong>{locationLabel(record) || "区划待补充"}</strong><small>{formatArea(record.areaMu)}</small></td>
                    <td><strong>{record.forestType || record.operationType || "资源属性待补充"}</strong><small>{record.baseType || record.qualityGrade || "未分级"}</small></td>
                    <td><StatusBadge tone={record.geometry ? "success" : "warning"}>{record.geometry ? "有边界" : "待补图"}</StatusBadge></td>
                    <td>{formatDateTime(record.updatedAt)}</td>
                    <td className="action-column">
                      <div className="row-actions">
                        <ActionButton label="查看" icon={Eye} onClick={() => setPanel({ mode: "view", record })} />
                        <ActionButton label="编辑" icon={Pencil} disabled={!canUpdate} onClick={() => setPanel({ mode: "edit", record })} />
                        <ActionButton label="移入回收站" icon={Trash2} danger disabled={!canDelete || remove.isPending} onClick={() => confirmDelete(record, remove.mutate)} />
                      </div>
                    </td>
                  </tr>
                ))}
                {!query.isLoading && !query.data?.items.length && (
                  <tr><td colSpan={6}><div className="table-empty"><MapPin aria-hidden="true" /><strong>当前条件下没有林班</strong><p>{q || riskLevel || baseType || operationType ? "请清除筛选条件后重试。" : "尚无正式林班，请先批量导入测绘成果或新增属性记录。"}</p></div></td></tr>
                )}
              </tbody>
            </table>
          </div>
          <LedgerPagination total={query.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
        </QueryState>
      </section>

      <SidePanel open={panel.mode === "view"} eyebrow="空间资源详情" title={panel.record?.name || "林班详情"} onClose={() => setPanel(EMPTY_PANEL)} footer={panel.record && canUpdate ? <button className="button primary" type="button" onClick={() => setPanel({ mode: "edit", record: panel.record! })}><Pencil aria-hidden="true" />编辑林班</button> : undefined}>
        {panel.record && <ForestBlockDetail record={panel.record} canRollback={canRollback} onRestored={async () => {
          setPanel(EMPTY_PANEL);
          await queryClient.invalidateQueries({ queryKey: ["v2-forest-block-ledger"] });
          await queryClient.invalidateQueries({ queryKey: ["forest-block-map"] });
        }} />}
      </SidePanel>
      <SidePanel wide open={panel.mode === "create" || panel.mode === "edit"} eyebrow={panel.mode === "create" ? "建立空间资源记录" : "维护空间资源属性"} title={panel.mode === "create" ? "新增林班" : `编辑 ${panel.record?.blockCode || "林班"}`} onClose={() => !save.isPending && setPanel(EMPTY_PANEL)}>
        <ForestBlockForm key={panel.record?.id || "new-forest-block"} record={panel.record} pending={save.isPending} error={save.error} onCancel={() => setPanel(EMPTY_PANEL)} onSubmit={(payload) => save.mutate({ record: panel.record, payload })} />
      </SidePanel>
    </div>
  );
}

function ForestBlockForm({ record, pending, error, onCancel, onSubmit }: { record: ForestBlockRecord | null; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: ForestBlockPayload) => void }) {
  const [geometry, setGeometry] = useState<Record<string, unknown> | null>(record?.geometry || null);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSubmit({
      blockCode: field(data, "blockCode"),
      name: field(data, "name"),
      countyCode: nullableField(data, "countyCode"), countyName: nullableField(data, "countyName"),
      townCode: nullableField(data, "townCode"), townName: nullableField(data, "townName"),
      villageCode: nullableField(data, "villageCode"), villageName: nullableField(data, "villageName"),
      areaMu: numberField(data, "areaMu"), slopeDegree: numberField(data, "slopeDegree"),
      forestType: nullableField(data, "forestType"), baseType: nullableField(data, "baseType"),
      operationType: nullableField(data, "operationType"), qualityGrade: nullableField(data, "qualityGrade"),
      healthStatus: nullableField(data, "healthStatus"), riskLevel: nullableField(data, "riskLevel"),
      bambooAge: nullableField(data, "bambooAge"), avgDbhCm: numberField(data, "avgDbhCm"),
      avgHeightM: numberField(data, "avgHeightM"), standingDensity: numberField(data, "standingDensity"),
      carbonEstimateTco2e: numberField(data, "carbonEstimateTco2e"),
      tags: field(data, "tags").split(/[,，]/).map((item) => item.trim()).filter(Boolean),
      geometry,
    });
  };
  return (
    <form className="entity-form" onSubmit={submit}>
      <FormSection title="基础信息" description="林班编号创建后不可修改，避免破坏业务关联。">
        <Field label="林班编号" required><input name="blockCode" required readOnly={Boolean(record)} defaultValue={record?.blockCode || ""} placeholder="例如：350783-003" /></Field>
        <Field label="林班名称" required><input name="name" required defaultValue={record?.name || ""} placeholder="例如：上屯村 003 林班" /></Field>
        <Field label="面积（亩）"><input name="areaMu" type="number" min="0" step="0.01" defaultValue={record?.areaMu ?? ""} /></Field>
        <Field label="坡度（度）"><input name="slopeDegree" type="number" min="0" max="90" step="0.1" defaultValue={record?.slopeDegree ?? ""} /></Field>
      </FormSection>
      <FormSection title="行政区划" description="按省、市、区县、乡镇逐级选择，区划代码和名称将自动成对保存。">
        <AdministrativeDivisionSelector value={record || {}} />
      </FormSection>
      <fieldset className="form-section boundary-section">
        <legend>空间边界</legend>
        <p>可直接绘制、拖动节点调整，或导入 Polygon / MultiPolygon GeoJSON。已有小班边界时，保存会检查所有小班仍完整位于林班范围内。</p>
        <BoundaryEditor value={geometry} onChange={setGeometry} entityLabel="林班" />
      </fieldset>
      <FormSection title="资源与经营" description="仅维护资源属性；权利人、证号等法律信息请到林权档案维护。">
        <Field label="竹种 / 林种"><input name="forestType" defaultValue={record?.forestType || ""} placeholder="例如：毛竹林" /></Field>
        <Field label="基地类型"><input name="baseType" defaultValue={record?.baseType || ""} /></Field>
        <Field label="经营类型"><input name="operationType" defaultValue={record?.operationType || ""} /></Field>
        <Field label="质量等级"><input name="qualityGrade" defaultValue={record?.qualityGrade || ""} /></Field>
        <Field label="健康状态"><input name="healthStatus" defaultValue={record?.healthStatus || ""} /></Field>
        <Field label="风险等级"><input name="riskLevel" defaultValue={record?.riskLevel || ""} /></Field>
        <Field label="竹龄"><input name="bambooAge" defaultValue={record?.bambooAge || ""} /></Field>
        <Field label="平均胸径（cm）"><input name="avgDbhCm" type="number" min="0" step="0.1" defaultValue={record?.avgDbhCm ?? ""} /></Field>
        <Field label="平均高度（m）"><input name="avgHeightM" type="number" min="0" step="0.1" defaultValue={record?.avgHeightM ?? ""} /></Field>
        <Field label="密度（株/亩）"><input name="standingDensity" type="number" min="0" step="0.1" defaultValue={record?.standingDensity ?? ""} /></Field>
        <Field label="碳储量估算（tCO₂e）"><input name="carbonEstimateTco2e" type="number" min="0" step="0.01" defaultValue={record?.carbonEstimateTco2e ?? ""} /></Field>
        <Field label="资源标签" span><input name="tags" defaultValue={record?.tags.join("，") || ""} placeholder="多个标签使用逗号分隔" /></Field>
      </FormSection>
      {error && <p className="form-error">{error.message}</p>}
      <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={pending}>{pending ? "保存中" : record ? "保存修改" : "创建林班"}</button></div>
    </form>
  );
}

function ForestBlockDetail({ record, canRollback, onRestored }: { record: ForestBlockRecord; canRollback: boolean; onRestored: () => Promise<void> }) {
  return <div className="detail-stack">
    <DetailGroup title="空间身份"><Detail label="林班编号" value={record.blockCode} /><Detail label="名称" value={record.name} /><Detail label="行政区划" value={locationLabel(record)} /><Detail label="面积" value={formatArea(record.areaMu)} /><Detail label="边界" value={record.geometry ? "已入库" : "待补图"} /></DetailGroup>
    <DetailGroup title="资源属性"><Detail label="竹种 / 林种" value={record.forestType} /><Detail label="基地类型" value={record.baseType} /><Detail label="经营类型" value={record.operationType} /><Detail label="质量等级" value={record.qualityGrade} /><Detail label="健康状态" value={record.healthStatus} /><Detail label="风险等级" value={record.riskLevel} /></DetailGroup>
    <DetailGroup title="调查指标"><Detail label="竹龄" value={record.bambooAge} /><Detail label="平均胸径" value={record.avgDbhCm == null ? "" : `${record.avgDbhCm} cm`} /><Detail label="平均高度" value={record.avgHeightM == null ? "" : `${record.avgHeightM} m`} /><Detail label="密度" value={record.standingDensity == null ? "" : `${record.standingDensity} 株/亩`} /><Detail label="碳储量估算" value={record.carbonEstimateTco2e == null ? "" : `${record.carbonEstimateTco2e} tCO₂e`} /></DetailGroup>
    <DetailGroup title="数据追溯"><Detail label="来源批次" value={record.sourceBatchId} /><Detail label="创建时间" value={formatDateTime(record.createdAt)} /><Detail label="更新时间" value={formatDateTime(record.updatedAt)} /></DetailGroup>
    <SpatialVersionHistory entityId={record.id} queryKey="forest-block-versions" canRollback={canRollback} load={() => api.forestBlockVersions(record.id)} rollback={(versionId) => api.rollbackForestBlock(record.id, versionId)} onRestored={onRestored} />
  </div>;
}

function ActionButton({ label, icon: Icon, onClick, disabled = false, danger = false }: { label: string; icon: typeof Eye; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return <button className={`icon-button ${danger ? "danger" : ""}`} type="button" disabled={disabled} aria-label={label} title={label} onClick={(event) => { event.stopPropagation(); onClick(); }}><Icon aria-hidden="true" /></button>;
}
function StatusBadge({ children, tone }: { children: string; tone: "success" | "warning" }) { return <span className={`status-badge ${tone}`}>{children}</span>; }
function FormSection({ title, description, children }: { title: string; description: string; children: ReactNode }) { return <fieldset className="form-section"><legend>{title}</legend><p>{description}</p><div className="form-grid">{children}</div></fieldset>; }
function Field({ label, children, required = false, span = false }: { label: string; children: ReactNode; required?: boolean; span?: boolean }) { return <label className={span ? "field-span" : ""}><span>{label}{required && <em>*</em>}</span>{children}</label>; }
function DetailGroup({ title, children }: { title: string; children: ReactNode }) { return <section className="detail-group"><h3>{title}</h3><dl>{children}</dl></section>; }
function Detail({ label, value }: { label: string; value: unknown }) { const text = String(value ?? "").trim() || "未填写"; return <div><dt>{label}</dt><dd>{text}</dd></div>; }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function nullableField(data: FormData, name: string) { return field(data, name) || null; }
function numberField(data: FormData, name: string) { const value = field(data, name); return value ? Number(value) : null; }
function locationLabel(record: ForestBlockRecord) { return [record.countyName, record.townName, record.villageName].filter(Boolean).join(" / "); }
function formatArea(value: number | null) { return value == null ? "面积待核定" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })} 亩`; }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false }); }
function withoutImmutableBlockFields(payload: ForestBlockPayload): Partial<ForestBlockPayload> { const { blockCode: _blockCode, ...changes } = payload; return changes; }
function confirmDelete(record: ForestBlockRecord, remove: (id: string) => void) { if (window.confirm(`确认将林班“${record.name}”移入回收站？\n已有林权关联不会被自动删除。`)) remove(record.id); }
