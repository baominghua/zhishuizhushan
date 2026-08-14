import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, FileDown, Paperclip, Pencil, Plus, RefreshCw, RotateCcw, Search, Trash2 } from "lucide-react";
import { type FormEvent, useDeferredValue, useRef, useState } from "react";

import { api } from "../api/client";
import type { AttachmentRecord } from "../api/types";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 50;
type Panel = { mode: "closed"; record: null } | { mode: "view" | "edit"; record: AttachmentRecord } | { mode: "upload"; record: null };

export function AttachmentsPage() {
  const client = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState(""); const [category, setCategory] = useState(""); const [includeDeleted, setIncludeDeleted] = useState(false); const [offset, setOffset] = useState(0);
  const [panel, setPanel] = useState<Panel>({ mode: "closed", record: null });
  const deferredQ = useDeferredValue(q);
  const query = useQuery({ queryKey: ["v2-attachments", deferredQ, category, includeDeleted, offset], queryFn: () => api.attachments({ q: deferredQ, category, includeDeleted, limit: PAGE_SIZE, offset }), placeholderData: (previous) => previous });
  const permissions = capabilities.data?.permissions; const roles = capabilities.data?.principal.roles;
  const canUpload = hasPermission(permissions, roles, "files.attachments.upload"); const canUpdate = hasPermission(permissions, roles, "files.attachments.update"); const canDelete = hasPermission(permissions, roles, "files.attachments.delete"); const canRestore = hasPermission(permissions, roles, "files.attachments.restore"); const canExport = hasPermission(permissions, roles, "files.attachments.export");
  const refresh = async () => { setPanel({ mode: "closed", record: null }); await client.invalidateQueries({ queryKey: ["v2-attachments"] }); };
  const remove = useMutation({ mutationFn: api.deleteAttachment, onSuccess: refresh });
  const restore = useMutation({ mutationFn: api.restoreAttachment, onSuccess: refresh });
  return <div className="standard-page ledger-page">
    <section className="page-heading ledger-heading"><div><span className="eyebrow">数据治理 / 受控文件</span><h1>附件中心</h1><p>统一保存调查照片、成果文档和业务证据；文件哈希、关联来源和操作记录全程可追溯。</p></div><div className="heading-actions"><button className="button secondary" type="button" onClick={() => query.refetch()}><RefreshCw aria-hidden="true" />刷新</button><a className={`button secondary ${canExport ? "" : "disabled"}`} href={canExport ? "/api/v2/attachments/export.csv" : undefined}><FileDown aria-hidden="true" />导出台账</a><button className="button primary" type="button" disabled={!canUpload} onClick={() => setPanel({ mode: "upload", record: null })}><Plus aria-hidden="true" />上传附件</button></div></section>
    <section className="ledger-shell"><div className="ledger-toolbar"><label className="search-field"><Search aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索文件名、摘要、上传人或 SHA-256" /></label><label className="compact-filter"><span>文件分类</span><select value={category} onChange={(event) => { setCategory(event.target.value); setOffset(0); }}><option value="">全部分类</option><option value="survey_evidence">调查证据</option><option value="document">业务文档</option><option value="image">现场照片</option><option value="result">成果文件</option></select></label>{canRestore && <label className="inline-check"><input type="checkbox" checked={includeDeleted} onChange={(event) => setIncludeDeleted(event.target.checked)} />显示回收站</label>}</div>
      <QueryState loading={query.isLoading} error={query.error}><div className="table-scroll"><table className="ledger-table attachment-table"><thead><tr><th>文件</th><th>分类与类型</th><th>完整性</th><th>业务关联</th><th>上传信息</th><th className="action-column">操作</th></tr></thead><tbody>{query.data?.items.map((record) => <tr key={record.id} onClick={() => setPanel({ mode: "view", record })}><td><strong>{record.originalName}</strong><small>{formatBytes(record.sizeBytes)}</small></td><td><strong>{categoryLabel(record.category)}</strong><small>{record.contentType || "未知类型"}</small></td><td><strong>{record.sha256.slice(0, 16)}</strong><small>SHA-256 已校验</small></td><td><strong>{record.linkCount} 项</strong><small>{record.links[0] ? `${record.links[0].entityType} · ${record.links[0].relationType}` : "暂未关联业务"}</small></td><td><strong>{record.uploadedBy || "系统"}</strong><small>{formatDateTime(record.createdAt)}</small></td><td className="action-column"><div className="row-actions"><Action label="查看" icon={Eye} onClick={() => setPanel({ mode: "view", record })} />{record.downloadUrl && <a className="icon-button" href={record.downloadUrl} title="下载" aria-label="下载" onClick={(event) => event.stopPropagation()}><Download aria-hidden="true" /></a>}{record.deletedAt ? <Action label="恢复" icon={RotateCcw} disabled={!canRestore} onClick={() => restore.mutate(record.id)} /> : <><Action label="编辑" icon={Pencil} disabled={!canUpdate} onClick={() => setPanel({ mode: "edit", record })} /><Action label="删除" icon={Trash2} danger disabled={!canDelete || record.linkCount > 0} onClick={() => { if (window.confirm(`确认将“${record.originalName}”移入回收站？`)) remove.mutate(record.id); }} /></>}</div></td></tr>)}{!query.isLoading && !query.data?.items.length && <tr><td colSpan={6}><div className="table-empty"><Paperclip aria-hidden="true" /><strong>附件中心暂无文件</strong><p>上传调查照片、文档或成果文件后，可在各业务模块中直接选择关联。</p></div></td></tr>}</tbody></table></div></QueryState>
      <LedgerPagination total={query.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
    </section>
    <SidePanel wide open={panel.mode === "upload" || panel.mode === "edit"} eyebrow="受控文件" title={panel.mode === "upload" ? "上传附件" : "编辑附件元数据"} onClose={() => setPanel({ mode: "closed", record: null })}><AttachmentForm record={panel.record} onDone={refresh} /></SidePanel>
    <SidePanel open={panel.mode === "view"} eyebrow="附件详情" title={panel.record?.originalName || "附件"} onClose={() => setPanel({ mode: "closed", record: null })}>{panel.record && <AttachmentDetail record={panel.record} />}</SidePanel>
  </div>;
}

function AttachmentForm({ record, onDone }: { record: AttachmentRecord | null; onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const mutation = useMutation({
    mutationFn: async ({ file, category, description }: { file: File | null; category: string; description: string }) => {
      if (record) return api.updateAttachment(record.id, { expectedVersion: record.version, category, description });
      if (!file) throw new Error("请选择要上传的文件");
      return api.uploadAttachment(file, category, description);
    },
    onSuccess: onDone,
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    mutation.mutate({
      file: fileRef.current?.files?.[0] ?? null,
      category: String(data.get("category") || "document"),
      description: String(data.get("description") || "").trim(),
    });
  };
  return <form className="entity-form" onSubmit={submit}><fieldset className="form-section"><legend>{record ? "元数据" : "选择文件"}</legend><p>文件内容上传后不可被元数据编辑替换；需要新版本时请重新上传并更新业务关联。</p><div className="form-grid">{!record && <label className="field-span"><span>本地文件<em>*</em></span><input ref={fileRef} type="file" required /></label>}<label><span>文件分类</span><select name="category" defaultValue={record?.category || "document"}><option value="survey_evidence">调查证据</option><option value="document">业务文档</option><option value="image">现场照片</option><option value="result">成果文件</option></select></label><label className="field-span"><span>文件说明</span><textarea name="description" rows={4} defaultValue={record?.description || ""} placeholder="说明文件来源、采集时间和用途" /></label></div></fieldset>{mutation.error && <p className="form-error">{mutation.error.message}</p>}<div className="form-actions"><button className="button primary" disabled={mutation.isPending}>{mutation.isPending ? "保存中" : record ? "保存元数据" : "上传附件"}</button></div></form>;
}
function AttachmentDetail({ record }: { record: AttachmentRecord }) { return <div className="detail-stack"><section className="detail-group"><h3>文件信息</h3><dl><Detail label="文件名" value={record.originalName} /><Detail label="分类" value={categoryLabel(record.category)} /><Detail label="类型" value={record.contentType} /><Detail label="大小" value={formatBytes(record.sizeBytes)} /><Detail label="上传人" value={record.uploadedBy} /><Detail label="上传时间" value={formatDateTime(record.createdAt)} /></dl></section><section className="detail-group"><h3>完整性与说明</h3><dl><Detail label="SHA-256" value={record.sha256} /><Detail label="版本" value={`v${record.version}`} /><Detail label="状态" value={record.deletedAt ? "已删除" : "正常"} /><Detail label="说明" value={record.description} /></dl></section><section className="detail-group"><h3>业务关联</h3><div className="attachment-link-list">{record.links.map((link) => <div key={link.id}><Paperclip aria-hidden="true" /><span><strong>{link.entityType}</strong><small>{link.entityId} · {link.relationType}</small></span></div>)}{!record.links.length && <p className="muted-copy">尚未关联业务记录。</p>}</div></section>{record.downloadUrl && <a className="button primary" href={record.downloadUrl}><Download aria-hidden="true" />下载原文件</a>}</div>; }
function Action({ label, icon: Icon, onClick, disabled = false, danger = false }: { label: string; icon: typeof Eye; onClick: () => void; disabled?: boolean; danger?: boolean }) { return <button className={`icon-button ${danger ? "danger" : ""}`} type="button" disabled={disabled} aria-label={label} title={label} onClick={(event) => { event.stopPropagation(); onClick(); }}><Icon aria-hidden="true" /></button>; }
function Detail({ label, value }: { label: string; value: unknown }) { return <div><dt>{label}</dt><dd>{String(value ?? "").trim() || "未填写"}</dd></div>; }
function categoryLabel(value: string) { return ({ survey_evidence: "调查证据", document: "业务文档", image: "现场照片", result: "成果文件" } as Record<string, string>)[value] || value; }
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB`; }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false }); }
