import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CloudUpload,
  Database,
  Download,
  Eye,
  FileImage,
  Globe2,
  Layers,
  MapPinned,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { type FormEvent, useDeferredValue, useMemo, useRef, useState } from "react";

import { api, downloadFile } from "../api/client";
import type {
  ForestBlockOption,
  ImageryAsset,
  ImageryAssetType,
  ImageryUploadPayload,
  PointCloudUploadSession,
  SpatialAssetTask,
  SpatialCoverageMatch,
} from "../api/types";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { LedgerPagination } from "../components/LedgerPagination";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

const PAGE_SIZE = 30;
const POINT_CLOUD_RESUME_KEY = "smart-bamboo.point-cloud-upload-session.v1";
const TYPE_LABELS: Record<ImageryAssetType, string> = {
  orthophoto: "正射影像",
  dsm: "DSM 地表模型",
  dtm: "DTM 地形模型",
  oblique3d: "倾斜三维",
  pointcloud: "点云成果",
  "flight-photos": "航飞原片",
};
const TERMINAL_TASK_STATUSES = new Set(["completed", "failed", "canceled"]);

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
    queryFn: () => api.imageryAssets({ q: deferredQ, published: published ? true : undefined, includeDeleted, limit: PAGE_SIZE, offset }),
  });
  const permissions = capabilities.data?.permissions ?? [];
  const roles = capabilities.data?.principal.roles ?? [];
  const canCreate = hasPermission(permissions, roles, "imagery.scenes.create");
  const canUpdate = hasPermission(permissions, roles, "imagery.scenes.update");
  const canDelete = hasPermission(permissions, roles, "imagery.scenes.delete");
  const canRestore = hasPermission(permissions, roles, "imagery.scenes.restore");
  const canPublish = hasPermission(permissions, roles, "imagery.layers.publish") || hasPermission(permissions, roles, "map.layers.publish");
  const items = ledger.data?.scenes ?? [];
  const metrics = useMemo(() => ({
    total: ledger.data?.total ?? 0,
    orthophotos: items.filter((item) => assetType(item) === "orthophoto").length,
    pointClouds: items.filter((item) => ["pointcloud", "oblique3d"].includes(assetType(item))).length,
    pendingReview: items.filter((item) => item.processingStage === "coverage-review").length,
  }), [items, ledger.data?.total]);
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["imagery-assets"] }); };
  const remove = useMutation({ mutationFn: api.deleteImageryAsset, onSuccess: async () => { setSelected(null); await refresh(); } });
  const restore = useMutation({ mutationFn: api.restoreImageryAsset, onSuccess: async ({ scene }) => { setSelected(scene); await refresh(); } });
  const publish = useMutation({ mutationFn: api.publishImageryAsset, onSuccess: async ({ scene }) => { setSelected(scene); await refresh(); } });
  const downloadPublisher = useMutation({
    mutationFn: () => downloadFile("/api/v2/tools/map-publisher/download", "智慧竹山地图发布助手.zip"),
    onError: (error) => window.alert(error instanceof Error ? error.message : "发布助手下载失败"),
  });

  return <div className="standard-page ledger-page imagery-assets-page">
    <section className="page-heading ledger-heading">
      <div><span className="eyebrow">低空成果 / 空间资产</span><h1>影像与点云成果</h1><p>GeoTIFF 自动分析有效覆盖林班；LAS/LAZ 按航飞任务断点续传并生成 COPC、3D Tiles。</p></div>
      <div className="heading-actions"><button className="button secondary" type="button" disabled={!canCreate || downloadPublisher.isPending} onClick={() => downloadPublisher.mutate()}><Download aria-hidden="true" />{downloadPublisher.isPending ? "正在下载" : "地图发布助手"}</button><button className="button secondary" type="button" onClick={() => ledger.refetch()}><RefreshCw aria-hidden="true" />刷新</button><button className="button primary" type="button" disabled={!canCreate} onClick={() => setCreating(true)}><Plus aria-hidden="true" />上传成果</button></div>
    </section>
    <section className="domain-summary-strip">
      <Summary label="成果总数" value={metrics.total} detail="正式空间资产" />
      <Summary label="正射成果" value={metrics.orthophotos} detail="GeoTIFF / COG" />
      <Summary label="三维成果" value={metrics.pointClouds} detail="COPC / PNTS / B3DM" />
      <Summary label="待确认覆盖" value={metrics.pendingReview} detail="需人工确认林班" tone={metrics.pendingReview ? "warning" : "active"} />
    </section>
    <section className="ledger-shell">
      <div className="ledger-toolbar domain-ledger-toolbar"><label className="search-field"><FileImage aria-hidden="true" /><input value={q} onChange={(event) => { setQ(event.target.value); setOffset(0); }} placeholder="搜索成果名称、文件名、任务或林班" /></label><label className="compact-filter"><span>发布状态</span><select value={published} onChange={(event) => { setPublished(event.target.value); setOffset(0); }}><option value="">全部成果</option><option value="published">已发布上图</option></select></label><label className="deleted-toggle"><input type="checkbox" checked={includeDeleted} onChange={(event) => { setIncludeDeleted(event.target.checked); setOffset(0); }} /><span>显示回收站</span></label></div>
      <QueryState loading={ledger.isLoading} error={ledger.error}><div className="table-scroll"><table className="ledger-table imagery-ledger-table"><thead><tr><th>成果档案</th><th>类型与采集</th><th>关联林班</th><th>空间信息</th><th>处理状态</th><th className="action-column">操作</th></tr></thead><tbody>
        {items.map((record) => <tr className={record.deletedAt ? "is-deleted" : ""} key={record.id} onClick={() => setSelected(record)}>
          <td><strong>{record.name}</strong><small>{record.fileName || record.id}</small></td>
          <td><strong>{TYPE_LABELS[assetType(record)]}</strong><small>{formatDate(record.capturedAt)}{record.missionId ? ` · ${record.missionId}` : ""}</small></td>
          <td><strong>{record.linkedBlockCodes?.join("、") || (record.spatialRelation?.type === "independent-point" ? record.spatialRelation.pointName || "独立空间点位" : "待确认")}</strong><small>{record.spatialRelation?.type === "independent-point" ? record.spatialRelation.pointCategory || "林外设施" : `${record.linkedBlockCodes?.length || 0} 个正式林班`}</small></td>
          <td><strong>{record.tilesetUrl ? record.pointCount ? `${formatNumber(record.pointCount)} 点` : `${formatNumber(record.tileCount || 0)} 瓦片` : record.resolution || "分辨率自动识别"}</strong><small>{record.crs || "坐标系待识别"}</small></td>
          <td>{record.deletedAt ? <Badge label="已删除" tone="deleted" /> : record.processingStage === "coverage-review" ? <Badge label="覆盖待确认" tone="warning" /> : isPublished(record) ? <Badge label="已发布" tone="ready" /> : <Badge label="已入库" tone="active" />}</td>
          <td className="action-column"><div className="row-actions"><Action label="查看" icon={Eye} onClick={() => setSelected(record)} />{record.originalDownloadUrl || record.copcUrl ? <a className="icon-button" href={record.originalDownloadUrl || record.copcUrl} title="下载影像资源" aria-label={`下载 ${record.name}`} onClick={(event) => event.stopPropagation()}><Download aria-hidden="true" /></a> : null}{record.deletedAt ? <Action label="恢复" icon={RotateCcw} disabled={!canRestore} onClick={() => restore.mutate(record.id)} /> : <><Action label="编辑" icon={Pencil} disabled={!canUpdate} onClick={() => setEditing(record)} />{!isPublished(record) && !record.tilesetUrl ? <Action label="发布到一张图" icon={Send} disabled={!canPublish || record.processingStage === "coverage-review"} onClick={() => publish.mutate(record)} /> : null}<Action label="删除" icon={Trash2} danger disabled={!canDelete} onClick={() => { if (window.confirm(`确认将“${record.name}”移入回收站吗？`)) remove.mutate(record.id); }} /></>}</div></td>
        </tr>)}
        {!ledger.isLoading && !items.length ? <tr><td colSpan={6}><div className="table-empty"><FileImage aria-hidden="true" /><strong>暂无空间成果</strong><p>可上传 GeoTIFF，或按一次航飞任务批量接收 LAS/LAZ。</p></div></td></tr> : null}
      </tbody></table></div></QueryState>
      <LedgerPagination total={ledger.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onPage={setOffset} />
    </section>
    <SidePanel wide open={creating} eyebrow="林班空间成果" title="上传并自动匹配" onClose={() => setCreating(false)}><SpatialAssetUploadForm onCancel={() => setCreating(false)} onSaved={async (record) => { setCreating(false); setSelected(record); await refresh(); }} /></SidePanel>
    <SidePanel wide open={Boolean(editing)} eyebrow="成果元数据" title={`编辑 ${editing?.name || "成果"}`} onClose={() => setEditing(null)}>{editing ? <ImageryEditForm initial={editing} onCancel={() => setEditing(null)} onSaved={async (record) => { setEditing(null); setSelected(record); await refresh(); }} /> : null}</SidePanel>
    <SidePanel wide open={Boolean(selected)} eyebrow="空间成果详情" title={selected?.name || "成果"} onClose={() => setSelected(null)}>{selected ? <ImageryDetail record={selected} canPublish={canPublish} publishing={publish.isPending} onPublish={() => publish.mutate(selected)} /> : null}</SidePanel>
  </div>;
}

function SpatialAssetUploadForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: (record: ImageryAsset) => void }) {
  const rasterFileRef = useRef<HTMLInputElement>(null);
  const pointCloudFilesRef = useRef<HTMLInputElement>(null);
  const [assetKind, setAssetKind] = useState<"raster" | "pointcloud" | "tileset">("raster");
  const [rasterType, setRasterType] = useState<"orthophoto" | "dsm" | "dtm">("orthophoto");
  const [sourceMode, setSourceMode] = useState<"upload" | "register">("upload");
  const [taskId, setTaskId] = useState("");
  const [uploadSessionId, setUploadSessionId] = useState("");
  const [transfer, setTransfer] = useState({ uploaded: 0, total: 0, label: "" });
  const task = useQuery({
    queryKey: ["spatial-asset-task", taskId],
    queryFn: () => api.spatialAssetTask(taskId),
    enabled: Boolean(taskId),
    refetchInterval: (query) => TERMINAL_TASK_STATUSES.has(String(query.state.data?.status || "")) ? false : 2_000,
  });
  const completedSceneId = task.data?.status === "completed" ? task.data.sceneId : "";
  const completedAsset = useQuery({
    queryKey: ["imagery-asset", completedSceneId],
    queryFn: () => api.imageryAsset(completedSceneId),
    enabled: Boolean(completedSceneId),
    retry: 2,
  });

  const submitMutation = useMutation({
    mutationFn: async (form: HTMLFormElement) => {
      const data = new FormData(form);
      const payload: ImageryUploadPayload = {
        name: field(data, "name"),
        assetType: assetKind === "raster" ? rasterType : assetKind === "pointcloud" ? "pointcloud" : "oblique3d",
        missionId: field(data, "missionId"),
        capturedAt: field(data, "capturedAt"),
        resolution: field(data, "resolution"),
        linkedBlockCodes: [],
      };
      const path = field(data, "serverPath");
      let result: { accepted: true; task: SpatialAssetTask };
      if (assetKind === "raster") {
        if (sourceMode === "register") {
          result = await api.registerImageryAsset(path, payload);
        } else {
          const file = rasterFileRef.current?.files?.[0];
          if (!file) throw new Error("请选择 GeoTIFF 文件");
          setTransfer({ uploaded: 0, total: file.size, label: "正在上传 GeoTIFF" });
          result = await api.uploadImageryAsset(file, payload);
          setTransfer({ uploaded: file.size, total: file.size, label: "文件上传完成，等待后台处理" });
        }
      } else if (assetKind === "tileset") {
        result = await api.registerTileset({ path, name: payload.name, missionId: payload.missionId || "", capturedAt: payload.capturedAt || "" });
      } else if (sourceMode === "register") {
        result = await api.registerPointCloud({ path, name: payload.name, missionId: payload.missionId || "", capturedAt: payload.capturedAt || "", recursive: true, outputs: ["copc", "3dtiles"] });
      } else {
        const files = Array.from(pointCloudFilesRef.current?.files ?? []);
        if (!files.length) throw new Error("请选择一个航飞任务的 LAS/LAZ 文件");
        const fingerprint = pointCloudUploadFingerprint(files);
        let session: PointCloudUploadSession;
        const storedResume = readPointCloudResume();
        const resumableSessionId = uploadSessionId || (storedResume?.fingerprint === fingerprint ? storedResume.sessionId : "");
        if (resumableSessionId) {
          try {
            session = await api.pointCloudUploadSession(resumableSessionId);
          } catch {
            session = await api.createPointCloudUploadSession({ name: payload.name, missionId: payload.missionId || "", capturedAt: payload.capturedAt || "", files, outputs: ["copc", "3dtiles"] });
          }
        } else {
          session = await api.createPointCloudUploadSession({ name: payload.name, missionId: payload.missionId || "", capturedAt: payload.capturedAt || "", files, outputs: ["copc", "3dtiles"] });
        }
        setUploadSessionId(session.id);
        writePointCloudResume({ sessionId: session.id, fingerprint });
        setTransfer({ uploaded: session.uploadedBytes, total: session.totalBytes, label: `正在续传 ${files.length} 个点云分片` });
        for (const remoteFile of session.files) {
          const localFile = files[remoteFile.index];
          if (!localFile || localFile.name !== remoteFile.name || localFile.size !== remoteFile.size) throw new Error(`本地文件与续传会话不一致：${remoteFile.name}`);
          const received = new Set(remoteFile.receivedChunks);
          for (let chunkIndex = 0; chunkIndex < remoteFile.totalChunks; chunkIndex += 1) {
            if (received.has(chunkIndex)) continue;
            const start = chunkIndex * remoteFile.chunkSize;
            const end = Math.min(localFile.size, start + remoteFile.chunkSize);
            const response = await api.uploadPointCloudChunk(session.id, remoteFile.index, chunkIndex, localFile.slice(start, end), localFile.size, start);
            session = response.session;
            setTransfer({ uploaded: session.uploadedBytes, total: session.totalBytes, label: `正在续传 ${remoteFile.name}` });
          }
        }
        result = await api.completePointCloudUploadSession(session.id);
        clearPointCloudResume(session.id);
        setTransfer({ uploaded: session.totalBytes, total: session.totalBytes, label: "点云上传完成，等待后台转换" });
      }
      setTaskId(result.task.id);
      return result.task;
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); submitMutation.mutate(event.currentTarget); };

  if (completedAsset.data) return <CoverageConfirmation asset={completedAsset.data} onCancel={onCancel} onSaved={onSaved} />;
  if (taskId) return <TaskProgress task={task.data} loading={task.isLoading || completedAsset.isLoading} error={task.error || completedAsset.error} onCancel={onCancel} />;

  return <form className="entity-form spatial-upload-form" onSubmit={submit}>
    <fieldset className="form-section"><legend>成果类型</legend><div className="asset-kind-switch"><button type="button" className={assetKind === "raster" ? "active" : ""} onClick={() => { setAssetKind("raster"); setUploadSessionId(""); }}><FileImage aria-hidden="true" /><span><strong>GeoTIFF 影像</strong><small>正射、DSM、DTM 自动转 COG</small></span></button><button type="button" className={assetKind === "pointcloud" ? "active" : ""} onClick={() => setAssetKind("pointcloud")}><CloudUpload aria-hidden="true" /><span><strong>LAS/LAZ 点云</strong><small>批量续传，生成 COPC 与 3D Tiles</small></span></button><button type="button" className={assetKind === "tileset" ? "active" : ""} onClick={() => { setAssetKind("tileset"); setSourceMode("register"); setUploadSessionId(""); }}><Layers aria-hidden="true" /><span><strong>DJI 3D Tiles</strong><small>直接登记 PNTS / B3DM，不重复转换</small></span></button></div></fieldset>
    <fieldset className="form-section"><legend>文件来源</legend><div className="source-mode-tabs"><button type="button" className={sourceMode === "upload" ? "active" : ""} disabled={assetKind === "tileset"} onClick={() => setSourceMode("upload")}>本机断点续传</button><button type="button" className={sourceMode === "register" ? "active" : ""} onClick={() => setSourceMode("register")}>服务器 / NAS 目录</button></div>{assetKind === "tileset" ? <p className="form-hint tileset-register-note">DJI Terra 已生成的目录直接留在服务器或 NAS；平台只校验引用、提取范围并建立目录索引。</p> : null}<div className="form-grid">
      {sourceMode === "upload" && assetKind === "raster" ? <label className="field-span"><span>GeoTIFF 文件<em>*</em></span><input ref={rasterFileRef} type="file" accept=".tif,.tiff,.geotiff,image/tiff" required /><small>上传完成后由后台转为 COG，并根据透明通道或 NoData 提取有效覆盖范围。</small></label> : null}
      {sourceMode === "upload" && assetKind === "pointcloud" ? <label className="field-span"><span>同一航飞任务的 LAS/LAZ<em>*</em></span><input ref={pointCloudFilesRef} type="file" accept=".las,.laz" multiple required onChange={() => setUploadSessionId("")} /><small>可一次选择多个文件；系统按 16–128MB 分片续传，失败或刷新页面后重新选择同一批文件即可续传。不要选择 .temp 中间目录。</small></label> : null}
      {sourceMode === "register" ? <label className="field-span"><span>服务器允许目录中的路径<em>*</em></span><input name="serverPath" required placeholder={assetKind === "tileset" ? "/app/data/remote-sensing/inbox/邵武S1地块/terra_pnts" : assetKind === "pointcloud" ? "/app/data/remote-sensing/inbox/邵武S1地块/terra_las_1_4" : "/app/data/remote-sensing/inbox/result.tif"} /><small>{assetKind === "tileset" ? "填写包含根 tileset.json 的目录，或直接填写该文件。系统递归校验 PNTS/B3DM 与子 tileset，原目录不会被复制、改写或删除。" : "路径必须位于 REMOTE_SENSING_IMPORT_DIRS；点云目录会递归扫描并自动排除 .temp 等隐藏目录。"}</small></label> : null}
      <label><span>成果名称<em>*</em></span><input name="name" required /></label>
      {assetKind === "raster" ? <label><span>成果类型<em>*</em></span><select value={rasterType} onChange={(event) => setRasterType(event.target.value as typeof rasterType)}><option value="orthophoto">正射影像</option><option value="dsm">DSM 地表模型</option><option value="dtm">DTM 地形模型</option></select></label> : <label><span>{assetKind === "tileset" ? "登记方式" : "转换产物"}</span><input readOnly value={assetKind === "tileset" ? "直接登记 PNTS / B3DM（不转换）" : "COPC + 3D Tiles"} /></label>}
      <label><span>无人机任务</span><input name="missionId" placeholder="例如 DJI-S1-20260813" /></label>
      <label><span>采集时间</span><input name="capturedAt" type="datetime-local" /></label>
      {assetKind === "raster" ? <label><span>标称分辨率</span><input name="resolution" placeholder="留空则从 GeoTIFF 自动识别" /></label> : null}
    </div></fieldset>
    {transfer.total ? <TransferProgress uploaded={transfer.uploaded} total={transfer.total} label={transfer.label} /> : null}
    {submitMutation.error ? <p className="form-error">{submitMutation.error.message}</p> : null}
    <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" disabled={submitMutation.isPending}>{submitMutation.isPending ? uploadSessionId ? "继续上传中" : "正在提交" : uploadSessionId ? "继续断点上传" : assetKind === "tileset" ? "登记并自动分析" : "上传并自动分析"}</button></div>
  </form>;
}

function TaskProgress({ task, loading, error, onCancel }: { task?: SpatialAssetTask; loading: boolean; error: Error | null; onCancel: () => void }) {
  const progress = Math.max(0, Math.min(100, Number(task?.progress || 0)));
  return <div className="spatial-task-progress"><div className="task-progress-icon">{task?.status === "failed" ? <AlertTriangle aria-hidden="true" /> : task?.status === "completed" ? <CheckCircle2 aria-hidden="true" /> : <Database aria-hidden="true" />}</div><span className="eyebrow">后台空间处理</span><h3>{task?.message || (loading ? "正在读取任务状态" : "任务已提交")}</h3><div className="progress-track"><i style={{ width: `${progress}%` }} /></div><div className="progress-meta"><strong>{progress}%</strong><small>{task?.status || "queued"}</small></div>{error ? <p className="form-error">{error.message}</p> : null}{task?.status === "failed" ? <p className="form-hint">源文件和已上传分片均已保留，可由具备任务重试权限的管理员重试。</p> : <p className="form-hint">可以关闭面板，后台任务不会中断；完成后将在成果台账显示“覆盖待确认”。</p>}<div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>关闭</button></div></div>;
}

function CoverageConfirmation({ asset, onCancel, onSaved }: { asset: ImageryAsset; onCancel: () => void; onSaved: (record: ImageryAsset) => void }) {
  const analysis = asset.coverageAnalysis;
  const [blocks, setBlocks] = useState<ForestBlockOption[]>(() => (analysis?.matches ?? []).filter((item) => item.suggested).map(matchToBlock));
  const [relationType, setRelationType] = useState<"forest-block" | "independent-point">(() => asset.spatialRelation?.type || "forest-block");
  const [pointName, setPointName] = useState(asset.spatialRelation?.pointName || asset.name);
  const [pointCategory, setPointCategory] = useState(asset.spatialRelation?.pointCategory || "竹材加工厂");
  const [selectorOpen, setSelectorOpen] = useState(false);
  const selectedCodes = useMemo(() => new Set(blocks.map((block) => block.code)), [blocks]);
  const confirm = useMutation({ mutationFn: () => api.confirmImageryCoverage(asset.id, relationType === "forest-block" ? { blockCodes: blocks.map((block) => block.code), relationType } : { blockCodes: [], relationType, pointName, pointCategory, longitude: asset.spatialRelation?.longitude, latitude: asset.spatialRelation?.latitude }), onSuccess: onSaved });
  const toggleMatch = (match: SpatialCoverageMatch) => setBlocks((current) => selectedCodes.has(match.blockCode) ? current.filter((item) => item.code !== match.blockCode) : [...current, matchToBlock(match)]);
  return <div className="coverage-review">
    <section className="coverage-review-heading"><span className="eyebrow">空间分析完成</span><h3>确认成果空间关系</h3><p>林地成果关联一个或多个林班；加工厂、机巢、堆场等林外设施可登记为独立空间点位。</p></section>
    <div className="spatial-relation-options" role="radiogroup" aria-label="空间关系类型">
      <label className={relationType === "forest-block" ? "active" : ""}><input type="radio" name="relationType" checked={relationType === "forest-block"} onChange={() => setRelationType("forest-block")} /><span><strong>关联林班</strong><small>适合林地正射、点云和实景模型</small></span></label>
      <label className={relationType === "independent-point" ? "active" : ""}><input type="radio" name="relationType" checked={relationType === "independent-point"} onChange={() => setRelationType("independent-point")} /><span><strong>独立空间点位</strong><small>适合加工厂、机巢、堆场等林外设施</small></span></label>
    </div>
    <div className="coverage-summary"><Summary label="有效覆盖面积" value={`${analysis?.effectiveAreaHa ?? "—"} ha`} detail="按有效轮廓估算" /><Summary label="相交林班" value={analysis?.matches.length ?? 0} detail="包含边缘相交" /><Summary label="已选林班" value={blocks.length} detail="确认后正式关联" /></div>
    {analysis?.error ? <p className="form-error">自动分析未完成：{analysis.error}</p> : null}
    <div className="coverage-table-wrap"><table className="coverage-table"><thead><tr><th>选择</th><th>林班</th><th>交叠面积</th><th>占林班</th><th>占成果</th></tr></thead><tbody>{(analysis?.matches ?? []).map((match) => <tr key={match.blockCode} className={selectedCodes.has(match.blockCode) ? "selected" : ""} onClick={() => toggleMatch(match)}><td><input type="checkbox" checked={selectedCodes.has(match.blockCode)} onChange={() => toggleMatch(match)} onClick={(event) => event.stopPropagation()} /></td><td><strong>{match.blockName}</strong><small>{match.blockCode}{match.location ? ` · ${match.location}` : ""}</small></td><td>{match.intersectionAreaHa} ha</td><td>{match.blockCoveragePercent}%</td><td>{match.imageryCoveragePercent}%</td></tr>)}{!analysis?.matches.length ? <tr><td colSpan={5}><div className="table-empty compact"><AlertTriangle aria-hidden="true" /><strong>没有自动匹配到正式林班</strong><p>请检查林班是否有几何边界，或使用下方按钮人工选择。</p></div></td></tr> : null}</tbody></table></div>
    {relationType === "forest-block" ? <><div className="relation-toolbar"><div><strong>最终关联林班<em>*</em></strong><small>跨林班成果只建一份档案，可确认多个林班。</small></div><button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}><MapPinned aria-hidden="true" />补充林班</button></div><BlockChips blocks={blocks} onRemove={(code) => setBlocks((items) => items.filter((item) => item.code !== code))} /></> : <div className="independent-point-form"><label><span>点位名称<em>*</em></span><input value={pointName} onChange={(event) => setPointName(event.target.value)} placeholder="例如 大横厂房" /></label><label><span>点位类型</span><select value={pointCategory} onChange={(event) => setPointCategory(event.target.value)}><option>竹材加工厂</option><option>无人机机巢</option><option>临时堆场</option><option>仓储物流点</option><option>其他设施</option></select></label><p>位置默认取影像有效范围中心；确认后作为独立点位进入 GIS 图层、搜索和成果详情。</p></div>}
    {confirm.error ? <p className="form-error">{confirm.error.message}</p> : null}
    <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>稍后确认</button><button className="button primary" disabled={confirm.isPending || (relationType === "forest-block" ? !blocks.length : !pointName.trim())} onClick={() => confirm.mutate()}>{confirm.isPending ? "正在写入关系" : relationType === "forest-block" ? `确认关联 ${blocks.length} 个林班` : "确认为独立点位"}</button></div>
    <ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => setBlocks((items) => items.some((item) => item.code === block.code) ? items : [...items, block])} />
  </div>;
}

function ImageryEditForm({ initial, onCancel, onSaved }: { initial: ImageryAsset; onCancel: () => void; onSaved: (record: ImageryAsset) => void }) {
  const [blocks, setBlocks] = useState<ForestBlockOption[]>(() => initial.linkedBlockCodes.map((code) => ({ id: "", code, name: code, location: "", areaMu: null, hasGeometry: true, riskLevel: null })));
  const [relationType, setRelationType] = useState<"forest-block" | "independent-point">(() => initial.spatialRelation?.type || "forest-block");
  const [pointName, setPointName] = useState(initial.spatialRelation?.pointName || initial.name);
  const [pointCategory, setPointCategory] = useState(initial.spatialRelation?.pointCategory || "竹材加工厂");
  const [selectorOpen, setSelectorOpen] = useState(false);
  const mutation = useMutation({
    mutationFn: async (form: HTMLFormElement) => {
      const data = new FormData(form);
      const blockCodes = relationType === "forest-block" ? blocks.map((block) => block.code) : [];
      await api.updateImageryAsset(initial.id, { name: field(data, "name"), missionId: field(data, "missionId"), capturedAt: field(data, "capturedAt"), resolution: field(data, "resolution"), linkedBlockCodes: blockCodes });
      return api.confirmImageryCoverage(initial.id, relationType === "forest-block" ? { blockCodes, relationType } : { blockCodes, relationType, pointName, pointCategory, longitude: initial.spatialRelation?.longitude, latitude: initial.spatialRelation?.latitude });
    },
    onSuccess: onSaved,
  });
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); mutation.mutate(event.currentTarget); };
  return <><form className="entity-form" onSubmit={submit}>
    <fieldset className="form-section"><legend>成果元数据</legend><div className="form-grid"><label><span>成果名称<em>*</em></span><input name="name" required defaultValue={initial.name} /></label><label><span>成果类型</span><input readOnly value={TYPE_LABELS[assetType(initial)]} /></label><label><span>无人机任务</span><input name="missionId" defaultValue={initial.missionId} /></label><label><span>采集时间</span><input name="capturedAt" type="datetime-local" defaultValue={localTime(initial.capturedAt)} /></label>{assetType(initial) !== "pointcloud" ? <label><span>标称分辨率</span><input name="resolution" defaultValue={initial.resolution} /></label> : null}</div></fieldset>
    <fieldset className="form-section"><legend>空间关系</legend>
      <div className="spatial-relation-options" role="radiogroup" aria-label="空间关系类型"><label className={relationType === "forest-block" ? "active" : ""}><input type="radio" checked={relationType === "forest-block"} onChange={() => setRelationType("forest-block")} /><span><strong>关联林班</strong><small>林地范围内成果</small></span></label><label className={relationType === "independent-point" ? "active" : ""}><input type="radio" checked={relationType === "independent-point"} onChange={() => setRelationType("independent-point")} /><span><strong>独立空间点位</strong><small>加工厂、机巢、堆场等林外设施</small></span></label></div>
      {relationType === "forest-block" ? <><div className="relation-toolbar"><div><strong>覆盖林班<em>*</em></strong><small>保存后同步替换成果与林班的正式关联关系。</small></div><button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}><MapPinned aria-hidden="true" />选择林班</button></div><BlockChips blocks={blocks} onRemove={(code) => setBlocks((items) => items.filter((item) => item.code !== code))} /></> : <div className="independent-point-form"><label><span>点位名称<em>*</em></span><input value={pointName} onChange={(event) => setPointName(event.target.value)} /></label><label><span>点位类型</span><select value={pointCategory} onChange={(event) => setPointCategory(event.target.value)}><option>竹材加工厂</option><option>无人机机巢</option><option>临时堆场</option><option>仓储物流点</option><option>其他设施</option></select></label><p>点位默认取成果有效范围中心，保存后可在 GIS 中查看和筛选。</p></div>}
    </fieldset>
    {mutation.error ? <p className="form-error">{mutation.error.message}</p> : null}<div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" disabled={mutation.isPending || (relationType === "forest-block" ? !blocks.length : !pointName.trim())}>{mutation.isPending ? "正在保存" : "保存元数据与空间关系"}</button></div>
  </form><ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => setBlocks((items) => items.some((item) => item.code === block.code) ? items : [...items, block])} /></>;
}

function ImageryDetail({ record, canPublish, publishing, onPublish }: { record: ImageryAsset; canPublish: boolean; publishing: boolean; onPublish: () => void }) {
  const pointCloud = assetType(record) === "pointcloud";
  const is3d = Boolean(record.tilesetUrl);
  const formatSummary = Object.entries(record.tileFormats ?? {}).map(([format, count]) => `${format.toUpperCase()} ${count}`).join(" · ");
  return <div className="detail-stack imagery-detail">
    {is3d ? <section className="point-cloud-preview"><Layers aria-hidden="true" /><div><strong>{pointCloud && record.pointCount ? `${formatNumber(record.pointCount)} 个点` : `${formatNumber(record.tileCount || 0)} 个三维瓦片`}</strong><small>{formatSummary || record.tilesetContentType?.toUpperCase() || "3D Tiles"} · {record.crs}</small></div></section> : <section className="imagery-preview"><img src={record.thumbnailUrl} alt={`${record.name} 预览`} /></section>}
    <section className="detail-group"><div className="detail-title-row"><h3>成果信息</h3>{record.processingStage === "coverage-review" ? <Badge label="覆盖待确认" tone="warning" /> : isPublished(record) ? <Badge label="已发布" tone="ready" /> : <Badge label="已入库" tone="active" />}</div><dl><Detail label="成果类型" value={TYPE_LABELS[assetType(record)]} /><Detail label="文件名" value={record.fileName} /><Detail label="采集时间" value={formatDate(record.capturedAt)} /><Detail label="任务编号" value={record.missionId} /><Detail label="坐标系" value={record.crs} />{is3d ? <><Detail label="瓦片格式" value={formatSummary} /><Detail label="内容瓦片" value={`${record.tileCount || 0} 个`} /><Detail label="子 tileset" value={`${record.tilesetCount || 0} 个`} />{record.pointCount ? <Detail label="点数量" value={formatNumber(record.pointCount)} /> : null}<Detail label="Tiles 版本" value={record.tilesetAssetVersions?.join("、")} /></> : <><Detail label="分辨率" value={record.resolution} /><Detail label="像素尺寸" value={`${record.width} × ${record.height} · ${record.bands} 波段`} /></>}<Detail label="文件容量" value={formatBytes(record.size)} /></dl>{is3d ? <div className="point-cloud-downloads">{record.copcUrl ? <a className="button secondary" href={record.copcUrl}><Download aria-hidden="true" />下载 COPC</a> : null}{record.processingStage !== "coverage-review" ? <a className="button primary" href={`/v2/asset-viewer?sceneId=${encodeURIComponent(record.id)}&mode=3d`} target="_blank" rel="noreferrer"><Globe2 aria-hidden="true" />在独立三维窗口打开</a> : null}<a className="button secondary" href={record.tilesetUrl} target="_blank" rel="noreferrer"><Layers aria-hidden="true" />检查 tileset.json</a></div> : null}</section>
    <section className="detail-group"><h3>空间关系</h3><div className="relation-chips read-only">{record.linkedBlockCodes?.map((code) => <span key={code}><strong>{code}</strong><small>正式林班</small></span>)}{record.spatialRelation?.type === "independent-point" ? <span><strong>{record.spatialRelation.pointName || record.name}</strong><small>{record.spatialRelation.pointCategory || "独立空间点位"}</small></span> : null}{!record.linkedBlockCodes?.length && record.spatialRelation?.type !== "independent-point" ? <p className="muted-copy">尚未确认空间关系，请点击编辑完成确认。</p> : null}</div></section>
    {!is3d && isPublished(record) ? <div className="point-cloud-downloads"><a className="button primary" href={`/v2/asset-viewer?sceneId=${encodeURIComponent(record.id)}&mode=2d`} target="_blank" rel="noreferrer"><Globe2 aria-hidden="true" />在独立二维窗口打开</a>{record.originalDownloadUrl ? <a className="button secondary" href={record.originalDownloadUrl}><Download aria-hidden="true" />下载原始 GeoTIFF</a> : null}</div> : null}
    {!is3d && !isPublished(record) ? <button className="button primary" type="button" disabled={!canPublish || publishing || record.processingStage === "coverage-review"} onClick={onPublish}><Layers aria-hidden="true" />{publishing ? "正在发布" : "发布到 GIS 一张图"}</button> : null}
  </div>;
}

function TransferProgress({ uploaded, total, label }: { uploaded: number; total: number; label: string }) { const percent = total ? Math.min(100, uploaded / total * 100) : 0; return <section className="transfer-progress"><div><strong>{label}</strong><small>{formatBytes(uploaded)} / {formatBytes(total)}</small></div><div className="progress-track"><i style={{ width: `${percent}%` }} /></div></section>; }
function BlockChips({ blocks, onRemove }: { blocks: ForestBlockOption[]; onRemove: (code: string) => void }) { return <div className="relation-chips">{blocks.map((block) => <span key={block.code}><strong>{block.name}</strong><small>{block.code}</small><button type="button" onClick={() => onRemove(block.code)} aria-label={`移除 ${block.code}`}><X aria-hidden="true" /></button></span>)}{!blocks.length ? <p className="form-hint">尚未选择覆盖林班。</p> : null}</div>; }
function matchToBlock(match: SpatialCoverageMatch): ForestBlockOption { return { id: match.blockId, code: match.blockCode, name: match.blockName, location: match.location, areaMu: match.blockAreaMu, hasGeometry: true, riskLevel: null }; }
function assetType(record?: Partial<ImageryAsset>): ImageryAssetType { return (record?.assetType || "orthophoto") as ImageryAssetType; }
function isPublished(record: ImageryAsset) { return Boolean(record.publishedLayerId || record.publishedLayerRecordCode || record.status === "published"); }
function field(data: FormData, name: string) { return String(data.get(name) || "").trim(); }
function pointCloudUploadFingerprint(files: File[]) { return files.map((file) => `${file.name}:${file.size}:${file.lastModified}`).join("|"); }
function readPointCloudResume(): { sessionId: string; fingerprint: string } | null { try { const parsed = JSON.parse(window.localStorage.getItem(POINT_CLOUD_RESUME_KEY) || "null"); return parsed?.sessionId && parsed?.fingerprint ? parsed : null; } catch { return null; } }
function writePointCloudResume(value: { sessionId: string; fingerprint: string }) { try { window.localStorage.setItem(POINT_CLOUD_RESUME_KEY, JSON.stringify(value)); } catch { /* Private browsing or storage policy may disable persistence. */ } }
function clearPointCloudResume(sessionId: string) { const current = readPointCloudResume(); if (!current || current.sessionId !== sessionId) return; try { window.localStorage.removeItem(POINT_CLOUD_RESUME_KEY); } catch { /* Ignore unavailable storage. */ } }
function localTime(value?: string) { if (!value) return ""; const date = new Date(value); if (Number.isNaN(date.valueOf())) return value.slice(0, 16); const offset = date.getTimezoneOffset() * 60_000; return new Date(date.valueOf() - offset).toISOString().slice(0, 16); }
function formatDate(value?: string) { if (!value) return "采集时间待补"; const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false }); }
function formatBytes(value: number) { if (!value) return "0 B"; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`; return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`; }
function formatNumber(value: number) { return new Intl.NumberFormat("zh-CN").format(value); }
function Summary({ label, value, detail, tone = "" }: { label: string; value: string | number; detail: string; tone?: string }) { return <article className={tone}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>; }
function Badge({ label, tone }: { label: string; tone: string }) { return <span className={`status-badge ${tone}`}><i />{label}</span>; }
function Detail({ label, value }: { label: string; value: unknown }) { return <div><dt>{label}</dt><dd>{String(value ?? "").trim() || "未填写"}</dd></div>; }
function Action({ label, icon: Icon, onClick, disabled = false, danger = false }: { label: string; icon: typeof Eye; onClick: () => void; disabled?: boolean; danger?: boolean }) { return <button className={`icon-button ${danger ? "danger" : ""}`} type="button" disabled={disabled} aria-label={label} title={label} onClick={(event) => { event.stopPropagation(); onClick(); }}><Icon aria-hidden="true" /></button>; }
