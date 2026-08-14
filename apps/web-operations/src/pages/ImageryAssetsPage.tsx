import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, FileImage, Layers, MapPinned, Pencil, Plus, RefreshCw, RotateCcw, Send, Trash2, X } from "lucide-react";
import { type FormEvent, useDeferredValue, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type { ForestBlockOption, ImageryAsset, ImageryAssetType, ImageryUploadPayload } from "../api/types";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 30;
const TYPE_LABELS: Record<ImageryAssetType, string> = {
  orthophoto: "正射影像",
  dsm: "DSM 地表模型",
  dtm: "DTM 地形模型",
  oblique3d: "倾斜三维",
  pointcloud: "点云成果",
  "flight-photos": "航飞原片",
};

export function ImageryAssetsPage() {
  const client = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState("");
  const [published, setPublished] = useState("");
  const [offset, setOffset] = useState(0);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<ImageryAsset | null>(null);
  const [editing, setEditing] = useState<ImageryAsset | null>(null);
  const deferredQ = useDeferredValue(q);
  const ledger = useQuery({
    queryKey: ["imagery-assets", deferredQ, published, includeDeleted, offset],
    queryFn: () => api.imageryAssets({
      q: deferredQ,
      published: published === "published" ? true : undefined,
      includeDeleted,
      status: includeDeleted ? "deleted" : undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    placeholderData: (previous) => previous,
  });
  const permissions = capabilities.data?.permissions;
  const roles = capabilities.data?.principal.roles;
  const canCreate = hasPermission(permissions, roles, "imagery.scenes.create");
  const canUpdate = hasPermission(permissions, roles, "imagery.scenes.update");
  const canDelete = hasPermission(permissions, roles, "imagery.scenes.delete");
  const canRestore = hasPermission(permissions, roles, "imagery.scenes.restore");
  const canPublish = hasPermission(permissions, roles, "imagery.layers.publish") || hasPermission(permissions, roles, "map.layers.publish");
  const items = ledger.data?.scenes ?? [];
  const metrics = useMemo(() => ({
    total: ledger.data?.total ?? 0,
    orthophotos: items.filter((item) => assetType(item) === "orthophoto").length,
    published: items.filter(isPublished).length,
    storage: items.reduce((total, item) => total + Number(item.size || 0), 0),
  }), [items, ledger.data?.total]);
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["imagery-assets"] }); };
  const remove = useMutation({ mutationFn: api.deleteImageryAsset, onSuccess: async () => { setSelected(null); await refresh(); } });
  const restore = useMutation({ mutationFn: api.restoreImageryAsset, onSuccess: async ({ scene }) => { setSelected(scene); await refresh(); } });
  const publish = useMutation({ mutationFn: api.publishImageryAsset, onSuccess: async ({ scene }) => { setSelected(scene); await refresh(); } });

  return <div className="standard-page ledger-page imagery-assets-page">
    <section className="page-heading ledger-heading">
      <div><span className="eyebrow">低空成果 / 林班影像资产</span><h1>影像成果</h1><p>以林班为索引管理正射、地形、倾斜三维和点云成果；当前节点直接处理 GeoTIFF。</p></div>
      <div className="heading-actions"><button className="button secondary" type="button" onClick={() => ledger.refetch()}><RefreshCw aria-hidden="true" />刷新</button><button className="button primary" type="button" disabled={!canCreate} onClick={() => setCreating(true)}><Plus aria-hidden="true" />上传成果</button></div>
    </section>
    <section className="domain-summary-strip"><Summary label="成果总数" value={metrics.total} detail="正式影像资产" /><Summary label="正射成果" value={metrics.orthophotos} detail="当前页 GeoTIFF" /><Summary label="已发布" value={metrics.published} detail="可在 GIS 一张图显示" tone="active" /><Summary label="当前页容量" value={formatBytes(metrics.storage)} detail="COG 存储占用" /></section>
    <section className="ledger-shell">
      <div className="ledger-toolbar domain-ledger-toolbar"><label className="search-field"><FileImage aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索成果名称、文件名、任务或林班" /></label><label className="compact-filter"><span>发布状态</span><select value={published} onChange={(event) => { setPublished(event.target.value); setOffset(0); }}><option value="">全部成果</option><option value="published">已发布上图</option></select></label><label className="deleted-toggle"><input type="checkbox" checked={includeDeleted} onChange={(event) => { setIncludeDeleted(event.target.checked); setOffset(0); }} /><span>显示回收站</span></label></div>
      <QueryState loading={ledger.isLoading} error={ledger.error}><div className="table-scroll"><table className="ledger-table imagery-ledger-table"><thead><tr><th>成果档案</th><th>类型与采集</th><th>关联林班</th><th>空间信息</th><th>发布状态</th><th className="action-column">操作</th></tr></thead><tbody>{items.map((record) => <tr className={record.deletedAt ? "is-deleted" : ""} key={record.id} onClick={() => setSelected(record)}><td><strong>{record.name}</strong><small>{record.fileName || record.id}</small></td><td><strong>{TYPE_LABELS[assetType(record)]}</strong><small>{formatDate(record.capturedAt)}{record.missionId ? ` · ${record.missionId}` : ""}</small></td><td><strong>{record.linkedBlockCodes?.join("、") || "未关联林班"}</strong><small>{record.linkedBlockCodes?.length || 0} 个空间单元</small></td><td><strong>{record.resolution || "分辨率自动识别"}</strong><small>{record.crs || "坐标系待识别"} · {record.width || 0} × {record.height || 0}</small></td><td>{record.deletedAt ? <Badge label="已删除" tone="deleted" /> : isPublished(record) ? <Badge label="已发布" tone="ready" /> : <Badge label="待发布" tone="warning" />}</td><td className="action-column"><div className="row-actions"><Action label="查看" icon={Eye} onClick={() => setSelected(record)} />{record.deletedAt ? <Action label="恢复" icon={RotateCcw} disabled={!canRestore} onClick={() => restore.mutate(record.id)} /> : <><Action label="编辑" icon={Pencil} disabled={!canUpdate} onClick={() => setEditing(record)} />{!isPublished(record) && <Action label="发布到一张图" icon={Send} disabled={!canPublish || !["orthophoto", "dsm", "dtm"].includes(assetType(record))} onClick={() => publish.mutate(record)} />}<Action label="删除" icon={Trash2} danger disabled={!canDelete} onClick={() => { if (window.confirm(`确认将“${record.name}”移入回收站吗？`)) remove.mutate(record.id); }} /></>}</div></td></tr>)}{!ledger.isLoading && !items.length && <tr><td colSpan={6}><div className="table-empty"><FileImage aria-hidden="true" /><strong>暂无影像成果</strong><p>上传林班正射 GeoTIFF 后，系统会生成 COG 并提供地图瓦片。</p></div></td></tr>}</tbody></table></div></QueryState>
      <LedgerPagination total={ledger.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
    </section>
    <SidePanel wide open={creating} eyebrow="林班影像成果" title="上传成果" onClose={() => setCreating(false)}><ImageryForm onCancel={() => setCreating(false)} onSaved={async (record) => { setCreating(false); setSelected(record); await refresh(); }} /></SidePanel>
    <SidePanel wide open={Boolean(editing)} eyebrow="成果元数据" title={`编辑 ${editing?.name || "成果"}`} onClose={() => setEditing(null)}>{editing && <ImageryForm initial={editing} onCancel={() => setEditing(null)} onSaved={async (record) => { setEditing(null); setSelected(record); await refresh(); }} />}</SidePanel>
    <SidePanel wide open={Boolean(selected)} eyebrow="影像成果详情" title={selected?.name || "成果"} onClose={() => setSelected(null)}>{selected && <ImageryDetail record={selected} canPublish={canPublish} publishing={publish.isPending} onPublish={() => publish.mutate(selected)} />}</SidePanel>
  </div>;
}

function ImageryForm({ initial, onCancel, onSaved }: { initial?: ImageryAsset; onCancel: () => void; onSaved: (record: ImageryAsset) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [blocks, setBlocks] = useState<ForestBlockOption[]>(initial?.linkedBlockCodes?.map((code) => ({ id: "", code, name: code, location: "", areaMu: null, hasGeometry: true, riskLevel: null })) ?? []);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const mutation = useMutation({
    mutationFn: async (payload: ImageryUploadPayload) => {
      if (initial) return api.updateImageryAsset(initial.id, payload);
      const file = fileRef.current?.files?.[0];
      if (!file) throw new Error("请选择 GeoTIFF 文件");
      const asset = await api.uploadImageryAsset(file, payload);
      await Promise.allSettled(blocks.filter((block) => block.id).map((block) => api.linkImageryAssetToBlock(block.id, asset)));
      return asset;
    },
    onSuccess: onSaved,
  });
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); mutation.mutate({ name: field(data, "name"), assetType: field(data, "assetType") as ImageryAssetType, missionId: field(data, "missionId"), capturedAt: field(data, "capturedAt"), resolution: field(data, "resolution"), linkedBlockCodes: blocks.map((block) => block.code) }); };
  return <><form className="entity-form" onSubmit={submit}><fieldset className="form-section"><legend>成果文件</legend><div className="form-grid">{!initial && <label className="field-span"><span>GeoTIFF 文件<em>*</em></span><input ref={fileRef} type="file" accept=".tif,.tiff,image/tiff" required /><small>当前轻量节点支持正射、DSM、DTM 的 GeoTIFF；系统自动转换为 COG。</small></label>}<label><span>成果名称<em>*</em></span><input name="name" required defaultValue={initial?.name} /></label><label><span>成果类型<em>*</em></span><select name="assetType" defaultValue={assetType(initial)}><option value="orthophoto">正射影像</option><option value="dsm">DSM 地表模型</option><option value="dtm">DTM 地形模型</option><option value="oblique3d" disabled>倾斜三维（待接转换器）</option><option value="pointcloud" disabled>点云成果（待接转换器）</option><option value="flight-photos" disabled>航飞原片（待接对象存储）</option></select></label><label><span>无人机任务</span><input name="missionId" defaultValue={initial?.missionId} placeholder="可填写任务编号" /></label><label><span>采集时间</span><input name="capturedAt" type="datetime-local" defaultValue={localTime(initial?.capturedAt)} /></label><label><span>标称分辨率</span><input name="resolution" defaultValue={initial?.resolution} placeholder="例如 0.08 m" /></label></div></fieldset><fieldset className="form-section"><legend>林班关联</legend><div className="relation-toolbar"><div><strong>覆盖林班<em>*</em></strong><small>必须从正式林班台账选择，可关联一个或多个林班。</small></div><button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}><MapPinned aria-hidden="true" />选择林班</button></div><div className="relation-chips">{blocks.map((block) => <span key={block.code}><strong>{block.name}</strong><small>{block.code}</small><button type="button" onClick={() => setBlocks((items) => items.filter((item) => item.code !== block.code))} aria-label={`移除 ${block.code}`}><X aria-hidden="true" /></button></span>)}</div>{!blocks.length && <p className="form-hint">尚未选择覆盖林班。</p>}</fieldset>{mutation.error && <p className="form-error">{mutation.error.message}</p>}<div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" disabled={mutation.isPending || !blocks.length}>{mutation.isPending ? "正在处理影像" : initial ? "保存元数据" : "上传并建档"}</button></div></form><ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => setBlocks((items) => items.some((item) => item.code === block.code) ? items : [...items, block])} /></>;
}

function ImageryDetail({ record, canPublish, publishing, onPublish }: { record: ImageryAsset; canPublish: boolean; publishing: boolean; onPublish: () => void }) {
  return <div className="detail-stack imagery-detail"><section className="imagery-preview"><img src={record.thumbnailUrl} alt={`${record.name} 预览`} /></section><section className="detail-group"><div className="detail-title-row"><h3>成果信息</h3>{isPublished(record) ? <Badge label="已发布" tone="ready" /> : <Badge label="待发布" tone="warning" />}</div><dl><Detail label="成果类型" value={TYPE_LABELS[assetType(record)]} /><Detail label="文件名" value={record.fileName} /><Detail label="采集时间" value={formatDate(record.capturedAt)} /><Detail label="任务编号" value={record.missionId} /><Detail label="坐标系" value={record.crs} /><Detail label="分辨率" value={record.resolution} /><Detail label="像素尺寸" value={`${record.width} × ${record.height} · ${record.bands} 波段`} /><Detail label="文件容量" value={formatBytes(record.size)} /></dl></section><section className="detail-group"><h3>覆盖林班</h3><div className="relation-chips read-only">{record.linkedBlockCodes?.map((code) => <span key={code}><strong>{code}</strong><small>正式林班</small></span>)}{!record.linkedBlockCodes?.length && <p className="muted-copy">尚未关联林班。</p>}</div></section>{!isPublished(record) && <button className="button primary" type="button" disabled={!canPublish || publishing || !["orthophoto", "dsm", "dtm"].includes(assetType(record))} onClick={onPublish}><Layers aria-hidden="true" />{publishing ? "正在发布" : "发布到 GIS 一张图"}</button>}</div>;
}

function assetType(record?: Partial<ImageryAsset>): ImageryAssetType { return (record?.assetType || "orthophoto") as ImageryAssetType; }
function isPublished(record: ImageryAsset) { return Boolean(record.publishedLayerId || record.publishedLayerRecordCode || record.status === "published"); }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function localTime(value?: string) { if (!value) return ""; const date = new Date(value); if (Number.isNaN(date.valueOf())) return value.slice(0, 16); const offset = date.getTimezoneOffset() * 60_000; return new Date(date.valueOf() - offset).toISOString().slice(0, 16); }
function formatDate(value?: string) { if (!value) return "采集时间待补"; const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false }); }
function formatBytes(value: number) { if (!value) return "0 B"; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`; return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`; }
function Summary({ label, value, detail, tone = "" }: { label: string; value: string | number; detail: string; tone?: string }) { return <article className={tone}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>; }
function Badge({ label, tone }: { label: string; tone: string }) { return <span className={`status-badge ${tone}`}><i />{label}</span>; }
function Detail({ label, value }: { label: string; value: unknown }) { return <div><dt>{label}</dt><dd>{String(value ?? "").trim() || "未填写"}</dd></div>; }
function Action({ label, icon: Icon, onClick, disabled = false, danger = false }: { label: string; icon: typeof Eye; onClick: () => void; disabled?: boolean; danger?: boolean }) { return <button className={`icon-button ${danger ? "danger" : ""}`} type="button" disabled={disabled} aria-label={label} title={label} onClick={(event) => { event.stopPropagation(); onClick(); }}><Icon aria-hidden="true" /></button>; }
