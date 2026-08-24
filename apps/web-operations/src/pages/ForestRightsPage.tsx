import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArchiveX,
  Eye,
  Filter,
  FolderKey,
  Link2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { type FormEvent, type ReactNode, useDeferredValue, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { ForestBlockOption, ForestRightPayload, ForestRightRecord } from "../api/types";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { LedgerPagination } from "../components/LedgerPagination";
import { LedgerSummaryStrip } from "../components/LedgerSummaryStrip";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 50;
type PanelState =
  | { mode: "closed"; record: null }
  | { mode: "view" | "edit"; record: ForestRightRecord }
  | { mode: "create"; record: null };
const EMPTY_PANEL: PanelState = { mode: "closed", record: null };

export function ForestRightsPage() {
  const queryClient = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState("");
  const [archiveStatus, setArchiveStatus] = useState("");
  const [linkedBlock, setLinkedBlock] = useState<ForestBlockOption | null>(null);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [panel, setPanel] = useState<PanelState>(EMPTY_PANEL);
  const deferredQ = useDeferredValue(q);
  const query = useQuery({
    queryKey: ["v2-forest-right-ledger", deferredQ, archiveStatus, linkedBlock?.code || "", offset],
    queryFn: () => api.forestRightLedger({
      q: deferredQ,
      archiveStatus,
      linkedBlockCode: linkedBlock?.code,
      limit: PAGE_SIZE,
      offset,
    }),
    placeholderData: (previous) => previous,
  });
  const permissions = capabilities.data?.permissions;
  const roles = capabilities.data?.principal.roles;
  const canCreate = hasPermission(permissions, roles, "forest.rights.create");
  const canUpdate = hasPermission(permissions, roles, "forest.rights.update");
  const canDelete = hasPermission(permissions, roles, "forest.rights.delete");
  const save = useMutation({
    mutationFn: ({ record, payload }: { record: ForestRightRecord | null; payload: ForestRightPayload }) =>
      record ? api.updateForestRight(record.id, payload) : api.createForestRight(payload),
    onSuccess: async () => {
      setPanel(EMPTY_PANEL);
      await queryClient.invalidateQueries({ queryKey: ["v2-forest-right-ledger"] });
      await queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    },
  });
  const remove = useMutation({
    mutationFn: api.deleteForestRight,
    onSuccess: async () => {
      setPanel(EMPTY_PANEL);
      await queryClient.invalidateQueries({ queryKey: ["v2-forest-right-ledger"] });
      await queryClient.invalidateQueries({ queryKey: ["workspace-summary"] });
    },
  });
  const summary = useMemo(() => {
    const items = query.data?.items ?? [];
    return [
      { label: "档案总数", value: query.data?.total ?? 0, detail: "当前权限范围" },
      { label: "有效档案", value: items.filter((item) => ["complete", "active"].includes(item.archiveStatus ?? "")).length, detail: "本页完整或有效", tone: "active" as const },
      { label: "已挂接林班", value: items.filter((item) => item.linkedBlockCodes.length > 0).length, detail: "本页图档关联" },
      { label: "待补正/争议", value: items.filter((item) => ["partial", "disputed"].includes(item.archiveStatus ?? "")).length, detail: "本页待处理", tone: "warning" as const },
    ];
  }, [query.data]);

  return (
    <div className="standard-page ledger-page">
      <section className="page-heading ledger-heading">
        <div><span className="eyebrow">资源数据 / 权属档案</span><h1>林权档案</h1><p>管理证照、权利人、期限、合同、流转和争议，并与正式林班建立可核验关系。</p></div>
        <div className="heading-actions">
          <button className="button secondary" type="button" onClick={() => query.refetch()}><RefreshCw aria-hidden="true" />刷新</button>
          <button className="button primary" type="button" disabled={!canCreate} onClick={() => setPanel({ mode: "create", record: null })} title={canCreate ? "新建林权档案" : "当前角色无新增权限"}><Plus aria-hidden="true" />新建档案</button>
        </div>
      </section>

      <LedgerSummaryStrip metrics={summary} />
      <section className="domain-boundary-note"><FolderKey aria-hidden="true" /><div><strong>档案与林班独立管理</strong><p>林班边界或资源调查变化不会自动改写林权档案；档案通过关联林班建立图档关系。</p></div></section>

      <section className="ledger-shell">
        <div className="ledger-toolbar">
          <label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索档案号、证号、权利人或合同号" /></label>
          <label className="compact-filter"><span>档案状态</span><select value={archiveStatus} onChange={(event) => { setArchiveStatus(event.target.value); setOffset(0); }}><option value="">全部状态</option><option value="complete">完整</option><option value="partial">待补正</option><option value="active">有效</option><option value="expired">到期</option><option value="disputed">争议</option></select></label>
          <button className={`button secondary filter-button ${linkedBlock ? "active" : ""}`} type="button" onClick={() => setSelectorOpen(true)}><Filter aria-hidden="true" />{linkedBlock ? linkedBlock.code : "按林班筛选"}</button>
          {(q || archiveStatus || linkedBlock) && <button className="text-button" type="button" onClick={() => { setQ(""); setArchiveStatus(""); setLinkedBlock(null); setOffset(0); }}>清除条件</button>}
        </div>

        <QueryState loading={query.isLoading} error={query.error}>
          <div className="table-scroll">
            <table className="ledger-table rights-table">
              <thead><tr><th>档案</th><th>权利人 / 权利类型</th><th>坐落与面积</th><th>关联林班</th><th>档案状态</th><th>更新时间</th><th className="action-column">操作</th></tr></thead>
              <tbody>
                {query.data?.items.map((record) => (
                  <tr key={record.id} onClick={() => setPanel({ mode: "view", record })}>
                    <td><strong>{record.archiveCode}</strong><small>{record.certificateNo || record.contractNo || "证号待补充"}</small></td>
                    <td><strong>{record.holder}</strong><small>{[record.rightType, record.ownershipType].filter(Boolean).join(" / ") || "权利类型待补充"}</small></td>
                    <td><strong>{locationLabel(record) || "坐落待补充"}</strong><small>{formatArea(record.areaMu)}</small></td>
                    <td><strong>{record.linkedBlockCodes.length ? `${record.linkedBlockCodes.length} 个林班` : "未挂接"}</strong><small>{record.linkedBlockCodes.slice(0, 2).join("、") || "请选择正式林班"}</small></td>
                    <td><ArchiveStatus status={record.archiveStatus} /></td>
                    <td>{formatDateTime(record.updatedAt)}</td>
                    <td className="action-column"><div className="row-actions">
                      <ActionButton label="查看" icon={Eye} onClick={() => setPanel({ mode: "view", record })} />
                      <ActionButton label="编辑" icon={Pencil} disabled={!canUpdate} onClick={() => setPanel({ mode: "edit", record })} />
                      <ActionButton label="作废档案" icon={Trash2} danger disabled={!canDelete || remove.isPending} onClick={() => confirmDelete(record, remove.mutate)} />
                    </div></td>
                  </tr>
                ))}
                {!query.isLoading && !query.data?.items.length && <tr><td colSpan={7}><div className="table-empty"><ArchiveX aria-hidden="true" /><strong>当前条件下没有林权档案</strong><p>{q || archiveStatus || linkedBlock ? "请清除筛选条件后重试。" : "可新建纸质档案电子索引，并从正式林班台账选择空间挂接对象。"}</p></div></td></tr>}
              </tbody>
            </table>
          </div>
          <LedgerPagination total={query.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
        </QueryState>
      </section>

      <ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => { setLinkedBlock(block); setOffset(0); }} />
      <SidePanel open={panel.mode === "view"} eyebrow="法律档案详情" title={panel.record?.archiveCode || "林权档案"} onClose={() => setPanel(EMPTY_PANEL)} footer={panel.record && canUpdate ? <button className="button primary" type="button" onClick={() => setPanel({ mode: "edit", record: panel.record! })}><Pencil aria-hidden="true" />编辑档案</button> : undefined}>
        {panel.record && <ForestRightDetail record={panel.record} />}
      </SidePanel>
      <SidePanel wide open={panel.mode === "create" || panel.mode === "edit"} eyebrow={panel.mode === "create" ? "建立法律档案" : "维护法律凭证"} title={panel.mode === "create" ? "新建林权档案" : `编辑 ${panel.record?.archiveCode || "档案"}`} onClose={() => !save.isPending && setPanel(EMPTY_PANEL)}>
        <ForestRightForm record={panel.record} pending={save.isPending} error={save.error} onCancel={() => setPanel(EMPTY_PANEL)} onSubmit={(payload) => save.mutate({ record: panel.record, payload })} />
      </SidePanel>
    </div>
  );
}

function ForestRightForm({ record, pending, error, onCancel, onSubmit }: { record: ForestRightRecord | null; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: ForestRightPayload) => void }) {
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [links, setLinks] = useState<Array<{ id: string; code: string; name: string }>>([]);
  useEffect(() => {
    setLinks((record?.linkedBlockCodes || []).map((code, index) => ({ id: record?.linkedBlockIds[index] || "", code, name: code })));
  }, [record]);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSubmit({
      archiveCode: nullableField(data, "archiveCode"), certificateNo: nullableField(data, "certificateNo"), holder: field(data, "holder"),
      certificateType: nullableField(data, "certificateType"), rightType: nullableField(data, "rightType"), ownershipType: nullableField(data, "ownershipType"),
      rightStart: nullableField(data, "rightStart"), rightEnd: nullableField(data, "rightEnd"), contractNo: nullableField(data, "contractNo"),
      circulationStatus: nullableField(data, "circulationStatus"), archiveStatus: nullableField(data, "archiveStatus"), registrar: nullableField(data, "registrar"),
      missingItems: nullableField(data, "missingItems"), areaMu: numberField(data, "areaMu"),
      countyCode: nullableField(data, "countyCode"), countyName: nullableField(data, "countyName"), townCode: nullableField(data, "townCode"), townName: nullableField(data, "townName"), villageCode: nullableField(data, "villageCode"), villageName: nullableField(data, "villageName"),
      linkedBlockIds: links.map((item) => item.id).filter(Boolean), linkedBlockCodes: links.map((item) => item.code),
    });
  };
  const addLink = (block: ForestBlockOption) => setLinks((current) => current.some((item) => item.code === block.code) ? current : [...current, { id: block.id, code: block.code, name: block.name }]);
  return <>
    <form className="entity-form" onSubmit={submit}>
      <FormSection title="档案凭证" description="档案编号、证号、合同号至少应有一项；建议使用现有档案编号作为主索引。">
        <Field label="档案编号" required><input name="archiveCode" required defaultValue={record?.archiveCode || ""} placeholder="例如：闽(2025)建瓯市不动产权第0012629号" /></Field>
        <Field label="不动产权证号"><input name="certificateNo" defaultValue={record?.certificateNo || ""} /></Field>
        <Field label="权利人" required><input name="holder" required defaultValue={record?.holder || ""} /></Field>
        <Field label="共有情况"><input name="ownershipType" defaultValue={record?.ownershipType || ""} placeholder="例如：单独所有" /></Field>
        <Field label="权利类型"><input name="rightType" defaultValue={record?.rightType || ""} placeholder="例如：林地经营权 / 林木所有权" /></Field>
        <Field label="证件类型"><input name="certificateType" defaultValue={record?.certificateType || ""} /></Field>
        <Field label="承包 / 流转合同号"><input name="contractNo" defaultValue={record?.contractNo || ""} /></Field>
        <Field label="登记人"><input name="registrar" defaultValue={record?.registrar || ""} /></Field>
      </FormSection>
      <FormSection title="期限与状态" description="历史流转、争议和补正材料保留在档案中，不覆盖既有法律事实。">
        <Field label="权利开始"><input name="rightStart" type="date" defaultValue={record?.rightStart?.slice(0, 10) || ""} /></Field>
        <Field label="权利截止"><input name="rightEnd" type="date" defaultValue={record?.rightEnd?.slice(0, 10) || ""} /></Field>
        <Field label="档案状态"><select name="archiveStatus" defaultValue={record?.archiveStatus || "complete"}><option value="complete">完整</option><option value="partial">待补正</option><option value="active">有效</option><option value="expired">到期</option><option value="disputed">争议</option></select></Field>
        <Field label="流转状态"><input name="circulationStatus" defaultValue={record?.circulationStatus || ""} /></Field>
        <Field label="缺失材料" span><textarea name="missingItems" rows={3} defaultValue={record?.missingItems || ""} placeholder="完整档案可不填写" /></Field>
      </FormSection>
      <FormSection title="坐落与面积" description="这里记录证载坐落和证载面积，空间范围以关联林班边界为锚点。">
        <Field label="区县代码"><input name="countyCode" defaultValue={record?.countyCode || ""} /></Field><Field label="区县名称"><input name="countyName" defaultValue={record?.countyName || ""} /></Field>
        <Field label="乡镇代码"><input name="townCode" defaultValue={record?.townCode || ""} /></Field><Field label="乡镇名称"><input name="townName" defaultValue={record?.townName || ""} /></Field>
        <Field label="村代码"><input name="villageCode" defaultValue={record?.villageCode || ""} /></Field><Field label="村名称"><input name="villageName" defaultValue={record?.villageName || ""} /></Field>
        <Field label="证载面积（亩）"><input name="areaMu" type="number" min="0" step="0.01" defaultValue={record?.areaMu ?? ""} /></Field>
      </FormSection>
      <fieldset className="form-section relation-section"><legend>关联林班</legend><p>只能从正式林班台账选择，不能自由填写林班编号。</p>
        <div className="relation-toolbar"><button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}><Link2 aria-hidden="true" />选择林班</button><span>已关联 {links.length} 个空间单元</span></div>
        <div className="relation-list">{links.map((link) => <span className="relation-chip" key={link.code}><span><strong>{link.name}</strong><small>{link.code}</small></span><button type="button" onClick={() => setLinks((current) => current.filter((item) => item.code !== link.code))} aria-label={`移除 ${link.code}`} title="移除关联"><X aria-hidden="true" /></button></span>)}{!links.length && <p className="relation-empty">尚未关联林班。档案可以先保存，正式确权前应完成空间挂接。</p>}</div>
      </fieldset>
      {error && <p className="form-error">{error.message}</p>}
      <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" type="submit" disabled={pending}>{pending ? "保存中" : record ? "保存修改" : "创建档案"}</button></div>
    </form>
    <ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={addLink} />
  </>;
}

function ForestRightDetail({ record }: { record: ForestRightRecord }) {
  return <div className="detail-stack">
    <DetailGroup title="法律凭证"><Detail label="档案编号" value={record.archiveCode} /><Detail label="不动产权证号" value={record.certificateNo} /><Detail label="权利人" value={record.holder} /><Detail label="共有情况" value={record.ownershipType} /><Detail label="权利类型" value={record.rightType} /><Detail label="合同号" value={record.contractNo} /></DetailGroup>
    <DetailGroup title="期限与状态"><Detail label="权利开始" value={record.rightStart} /><Detail label="权利截止" value={record.rightEnd} /><Detail label="档案状态" value={statusLabel(record.archiveStatus)} /><Detail label="流转状态" value={record.circulationStatus} /><Detail label="缺失材料" value={record.missingItems} /></DetailGroup>
    <DetailGroup title="证载信息"><Detail label="坐落" value={locationLabel(record)} /><Detail label="证载面积" value={formatArea(record.areaMu)} /><Detail label="登记人" value={record.registrar} /></DetailGroup>
    <section className="detail-group"><h3>空间挂接</h3><div className="detail-relations">{record.linkedBlockCodes.map((code) => <span key={code}><Link2 aria-hidden="true" />{code}</span>)}{!record.linkedBlockCodes.length && <p>尚未关联林班，当前档案没有空间锚点。</p>}</div></section>
    <DetailGroup title="档案留痕"><Detail label="附件数量" value={`${record.documents.length} 份`} /><Detail label="创建时间" value={formatDateTime(record.createdAt)} /><Detail label="更新时间" value={formatDateTime(record.updatedAt)} /></DetailGroup>
  </div>;
}

function ArchiveStatus({ status }: { status: string | null }) { const tone = status === "complete" || status === "active" ? "success" : status === "disputed" || status === "expired" ? "danger" : "warning"; return <span className={`status-badge ${tone}`}>{statusLabel(status)}</span>; }
function ActionButton({ label, icon: Icon, onClick, disabled = false, danger = false }: { label: string; icon: typeof Eye; onClick: () => void; disabled?: boolean; danger?: boolean }) { return <button className={`icon-button ${danger ? "danger" : ""}`} type="button" disabled={disabled} aria-label={label} title={label} onClick={(event) => { event.stopPropagation(); onClick(); }}><Icon aria-hidden="true" /></button>; }
function FormSection({ title, description, children }: { title: string; description: string; children: ReactNode }) { return <fieldset className="form-section"><legend>{title}</legend><p>{description}</p><div className="form-grid">{children}</div></fieldset>; }
function Field({ label, children, required = false, span = false }: { label: string; children: ReactNode; required?: boolean; span?: boolean }) { return <label className={span ? "field-span" : ""}><span>{label}{required && <em>*</em>}</span>{children}</label>; }
function DetailGroup({ title, children }: { title: string; children: ReactNode }) { return <section className="detail-group"><h3>{title}</h3><dl>{children}</dl></section>; }
function Detail({ label, value }: { label: string; value: unknown }) { const text = String(value ?? "").trim() || "未填写"; return <div><dt>{label}</dt><dd>{text}</dd></div>; }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function nullableField(data: FormData, name: string) { return field(data, name) || null; }
function numberField(data: FormData, name: string) { const value = field(data, name); return value ? Number(value) : null; }
function locationLabel(record: ForestRightRecord) { return [record.countyName, record.townName, record.villageName].filter(Boolean).join(" / "); }
function formatArea(value: number | null) { return value == null ? "面积待核定" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })} 亩`; }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false }); }
function statusLabel(status: string | null) { return ({ complete: "完整", partial: "待补正", active: "有效", expired: "到期", disputed: "争议" } as Record<string, string>)[status || ""] || status || "未标记"; }
function confirmDelete(record: ForestRightRecord, remove: (id: string) => void) { if (window.confirm(`确认作废林权档案“${record.archiveCode}”？\n该操作只进入回收站，不会物理删除法律记录。`)) remove(record.id); }
