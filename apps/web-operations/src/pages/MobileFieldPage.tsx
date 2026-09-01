import { Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  ArrowLeft,
  Camera,
  Check,
  ChevronRight,
  CloudDownload,
  CloudUpload,
  ClipboardList,
  LocateFixed,
  MapPin,
  Navigation,
  RefreshCw,
  Route,
  ShieldAlert,
  Signal,
  SignalZero,
  Smartphone,
  Square,
  UserRound,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type { MobileEvidenceUpload, MobileFieldTask, MobilePendingOperation, MobileTrackPayload, MobileUploadSession } from "../api/types";
import { SidePanel } from "../components/SidePanel";
import {
  createClientId,
  deleteEvidenceBlob,
  readEvidenceBlob,
  readMobileFieldState,
  saveEvidenceBlob,
  writeMobileFieldState,
  type MobileFieldState,
} from "../mobileFieldStore";
import { currentConnectivity, nativeBridge, subscribeConnectivity, subscribeNativeLocation } from "../nativeBridge";

type TaskFilter = "all" | "patrol" | "labor" | "safety";

export function MobileFieldPage() {
  const [state, setState] = useState<MobileFieldState>(() => readMobileFieldState());
  const [online, setOnline] = useState(currentConnectivity);
  const [filter, setFilter] = useState<TaskFilter>("all");
  const [selected, setSelected] = useState<MobileFieldTask | null>(null);
  const [busy, setBusy] = useState<"download" | "sync" | "track" | "evidence" | "">("");
  const [notice, setNotice] = useState("");
  const watchRef = useRef<number | null>(null);
  const nativeTrackingRef = useRef(false);

  useEffect(() => writeMobileFieldState(state), [state]);
  useEffect(() => subscribeConnectivity(setOnline), []);
  useEffect(() => subscribeNativeLocation((detail) => {
    if (detail.status === "update" && typeof detail.longitude === "number" && typeof detail.latitude === "number") {
      updateState((current) => current.activeTrack ? ({
        ...current,
        activeTrack: { ...current.activeTrack, points: [...current.activeTrack.points, {
          longitude: detail.longitude!, latitude: detail.latitude!,
          accuracyMeters: detail.accuracy ?? undefined, altitudeMeters: detail.altitude ?? undefined,
          capturedAt: new Date(detail.timestamp || Date.now()).toISOString(),
        }] },
      }) : current);
      return;
    }
    if (detail.status === "provider-disabled") setNotice("设备定位已关闭，请开启定位服务后重试。");
    if (detail.status === "unavailable") { setNotice("当前无法获取设备定位，请检查定位权限。"); setBusy(""); }
  }), []);
  useEffect(() => () => {
    if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current);
    if (nativeTrackingRef.current) nativeBridge()?.stopLocation();
  }, []);

  const tasks = state.offlinePackage?.tasks ?? [];
  const filteredTasks = useMemo(
    () => tasks.filter((task) => filter === "all" || task.taskType === filter),
    [filter, tasks],
  );
  const pendingCount = state.operations.length + state.tracks.length + state.evidence.length;
  const overdue = tasks.filter((task) => task.overdue).length;
  const principal = state.offlinePackage?.principal;

  const updateState = (next: (current: MobileFieldState) => MobileFieldState) => setState((current) => next(current));

  async function downloadPackage() {
    if (!online) { setNotice("当前处于离线状态，请联网后下载任务包。"); return; }
    setBusy("download"); setNotice("");
    try {
      const offlinePackage = await api.mobileOfflinePackage();
      updateState((current) => ({ ...current, offlinePackage }));
      setNotice(`已更新 ${offlinePackage.tasks.length} 条现场任务，可离线查看。`);
    } catch (error) { setNotice(error instanceof Error ? error.message : "任务包下载失败。"); }
    finally { setBusy(""); }
  }

  async function syncPending() {
    if (!online) { setNotice("当前无网络，现场记录已保存在本机。"); return; }
    if (!pendingCount) { await downloadPackage(); return; }
    setBusy("sync"); setNotice("");
    try {
      for (const track of state.tracks) await api.uploadMobileTrack(track);
      let message = `已同步 ${state.tracks.length} 条轨迹`;
      const completedEvidence = new Set<string>();
      for (const evidence of state.evidence) {
        await syncEvidence(evidence, (updated) => updateState((current) => ({
          ...current,
          evidence: current.evidence.map((item) => item.clientEvidenceId === updated.clientEvidenceId ? updated : item),
        })));
        completedEvidence.add(evidence.clientEvidenceId);
        await deleteEvidenceBlob(evidence.clientEvidenceId);
      }
      if (state.evidence.length) message += `、${state.evidence.length} 份现场凭证`;
      if (state.operations.length) {
        const result = await api.syncMobileOperations(state.operations);
        message += `、${result.completed} 条业务操作`;
        if (result.conflicts) message += `，${result.conflicts} 条冲突已转后台确认`;
        if (result.failed) message += `，${result.failed} 条未通过校验`;
      }
      const offlinePackage = await api.mobileOfflinePackage();
      updateState((current) => ({ ...current, offlinePackage, operations: [], tracks: [], evidence: current.evidence.filter((item) => !completedEvidence.has(item.clientEvidenceId)), lastSyncedAt: new Date().toISOString() }));
      setSelected(null);
      setNotice(`${message}。`);
    } catch (error) { setNotice(error instanceof Error ? error.message : "同步中断，记录仍保留在本机。"); }
    finally { setBusy(""); }
  }

  async function queueEvidence(task: MobileFieldTask, files: FileList) {
    const accepted = Array.from(files).filter((file) => file.type.startsWith("image/") || file.type.startsWith("video/"));
    if (!accepted.length) { setNotice("仅支持现场照片或视频。 "); return; }
    if (accepted.some((file) => file.size > 500 * 1024 * 1024)) { setNotice("单个现场文件不能超过 500 MB。"); return; }
    setBusy("evidence"); setNotice("正在安全保存现场文件…");
    try {
      const queued: MobileEvidenceUpload[] = [];
      for (const file of accepted) {
        const clientEvidenceId = createClientId("evidence");
        await saveEvidenceBlob(clientEvidenceId, file);
        queued.push({
          clientEvidenceId,
          taskType: task.taskType,
          taskId: task.id,
          fileName: file.name,
          contentType: file.type,
          totalBytes: file.size,
          totalChunks: Math.ceil(file.size / EVIDENCE_CHUNK_BYTES),
          sha256: file.size <= 100 * 1024 * 1024 ? await sha256(file) : "",
          sessionId: "",
          receivedChunks: [],
          status: "queued",
          createdAt: new Date().toISOString(),
        });
      }
      updateState((current) => ({ ...current, evidence: [...current.evidence, ...queued] }));
      setNotice(`已在本机保存 ${queued.length} 份现场凭证，联网后点击立即同步。`);
    } catch (error) { setNotice(error instanceof Error ? error.message : "现场文件保存失败。"); }
    finally { setBusy(""); }
  }

  function queueOperation(task: MobileFieldTask, action: string, payload: Record<string, unknown>) {
    const operation: MobilePendingOperation = {
      clientOperationId: createClientId("mobile"), entityType: task.taskType, entityId: task.id,
      action, baseVersion: task.version, occurredAt: new Date().toISOString(), payload,
    };
    const nextStatus = optimisticStatus(task.taskType, action, task.status);
    updateState((current) => ({
      ...current,
      operations: [...current.operations, operation],
      offlinePackage: current.offlinePackage ? {
        ...current.offlinePackage,
        tasks: current.offlinePackage.tasks.map((item) => item.id === task.id ? { ...item, status: nextStatus } : item),
      } : null,
    }));
    setSelected((current) => current ? { ...current, status: nextStatus } : current);
    setNotice(online ? "操作已加入同步队列，请点击立即同步。" : "操作已安全保存在本机，联网后可继续同步。");
  }

  function startTrack(task: MobileFieldTask) {
    const bridge = nativeBridge();
    if (!bridge && !navigator.geolocation) { setNotice("当前设备不支持定位。"); return; }
    if (watchRef.current !== null || nativeTrackingRef.current) return;
    setBusy("track");
    const initial: MobileTrackPayload = {
      clientTrackId: createClientId("track"), taskType: task.taskType === "labor" ? "labor" : "patrol",
      taskId: task.id, status: "recording", points: [],
    };
    updateState((current) => ({ ...current, activeTrack: initial }));
    if (bridge) {
      nativeTrackingRef.current = true;
      bridge.startLocation();
      return;
    }
    watchRef.current = navigator.geolocation.watchPosition(
      (position) => updateState((current) => current.activeTrack ? ({
        ...current,
        activeTrack: { ...current.activeTrack, points: [...current.activeTrack.points, {
          longitude: position.coords.longitude, latitude: position.coords.latitude,
          accuracyMeters: position.coords.accuracy, altitudeMeters: position.coords.altitude ?? undefined,
          capturedAt: new Date(position.timestamp).toISOString(),
        }] },
      }) : current),
      (error) => { setNotice(`定位失败：${error.message}`); setBusy(""); },
      { enableHighAccuracy: true, maximumAge: 10_000, timeout: 20_000 },
    );
  }

  function stopTrack() {
    if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current);
    if (nativeTrackingRef.current) nativeBridge()?.stopLocation();
    nativeTrackingRef.current = false;
    watchRef.current = null; setBusy("");
    updateState((current) => {
      const active = current.activeTrack;
      if (!active) return current;
      if (active.points.length < 2) { setNotice("定位点少于 2 个，本次轨迹未入队。"); return { ...current, activeTrack: null }; }
      setNotice(`轨迹已保存在本机，共 ${active.points.length} 个定位点。`);
      return { ...current, activeTrack: null, tracks: [...current.tracks, { ...active, status: "completed" }] };
    });
  }

  return <div className="field-mobile-page" id="field-mobile-top">
    <header className="field-mobile-header">
      <div><Link to="/workspace" aria-label="返回工作台"><ArrowLeft /></Link><span><small>智慧竹山 · 现场端</small><strong>今日现场</strong></span></div>
      <div className="field-mobile-identity"><span><UserRound /><strong>{principal?.user || "现场人员"}</strong><small>{principal?.areas?.[0] || "离线作业空间"}</small></span><b className={online ? "online" : "offline"}>{online ? <Signal /> : <SignalZero />}{online ? "在线" : "离线"}</b></div>
    </header>

    <section className="field-mobile-overview" aria-label="今日现场概览">
      <div className="field-mobile-overview-copy"><small>{online ? "现场任务已连接" : "弱网模式已启用"}</small><h1>{overdue ? `${overdue} 项任务需要优先处理` : tasks.length ? "今日任务已准备好" : "下载任务包后开始作业"}</h1><p>{pendingCount ? `${pendingCount} 条记录保存在本机，联网后可安全同步。` : state.offlinePackage ? `任务包更新于 ${formatTime(state.offlinePackage.generatedAt)}。` : "任务、地图和作业要求可保存到本机离线使用。"}</p></div>
      <div className="field-mobile-overview-number"><strong>{tasks.length}</strong><span>本机任务</span></div>
    </section>

    <section className="field-mobile-status">
      <div><small>待办任务</small><strong>{tasks.length}</strong><span>已下载到本机</span></div>
      <div className={pendingCount ? "warning" : ""}><small>待同步记录</small><strong>{pendingCount}</strong><span>{pendingCount ? "本机安全暂存" : "数据已同步"}</span></div>
      <div className={overdue ? "danger" : ""}><small>逾期任务</small><strong>{overdue}</strong><span>{overdue ? "建议优先处置" : "暂无逾期"}</span></div>
    </section>

    <section className="field-mobile-actions" aria-label="现场快捷操作">
      <button type="button" onClick={downloadPackage} disabled={Boolean(busy)}><CloudDownload />{busy === "download" ? "正在更新" : "更新离线包"}</button>
      <button className="primary" type="button" onClick={syncPending} disabled={Boolean(busy)}><CloudUpload />{busy === "sync" ? "正在同步" : pendingCount ? `同步 ${pendingCount} 条记录` : "检查更新"}</button>
    </section>

    {notice && <div className="field-mobile-notice" role="status"><AlertTriangle />{notice}</div>}
    {state.activeTrack && <div className="field-track-bar"><Navigation /><span><strong>正在记录轨迹</strong><small>{state.activeTrack.points.length} 个定位点已保存在本机</small></span><button type="button" onClick={stopTrack}><Square />结束</button></div>}

    <nav className="field-task-tabs" aria-label="任务类型">
      {([['all', '全部'], ['patrol', '巡护'], ['labor', '劳务'], ['safety', '安全']] as const).map(([value, label]) => <button key={value} className={filter === value ? "active" : ""} type="button" onClick={() => setFilter(value)}>{label}<span>{value === "all" ? tasks.length : tasks.filter((task) => task.taskType === value).length}</span></button>)}
    </nav>

    <section className="field-task-list">
      {filteredTasks.map((task) => <button key={task.id} type="button" className={task.overdue ? "overdue" : ""} onClick={() => setSelected(task)}>
        <TaskIcon type={task.taskType} /><span><small>{typeLabel(task.taskType)} · {task.taskNo}</small><strong>{task.title}</strong><em><MapPin />{task.linkedBlockCodes.join("、") || "未关联林班"}</em></span><span className="field-task-meta"><b>{statusLabel(task.status)}</b><time>{task.dueAt ? formatDate(task.dueAt) : "未设时限"}</time></span><ChevronRight />
      </button>)}
      {!filteredTasks.length && <div className="field-task-empty"><Smartphone /><strong>{state.offlinePackage ? "当前筛选下没有任务" : "先下载离线任务包"}</strong><p>{state.offlinePackage ? "切换任务类型查看其他现场任务。" : "下载后即使进入林区无网络，也能查看任务和记录现场结果。"}</p></div>}
    </section>

    <footer className="field-mobile-footer"><span><LocateFixed />定位仅在执行任务时采集</span><span>{state.lastSyncedAt ? `上次同步 ${formatTime(state.lastSyncedAt)}` : "尚未同步"}</span></footer>
    <nav className="field-mobile-dock" aria-label="现场端快捷导航">
      <button type="button" onClick={() => { setFilter("all"); document.getElementById("field-mobile-top")?.scrollIntoView({ behavior: "smooth" }); }}><ClipboardList /><span>任务</span></button>
      <button className={pendingCount ? "primary" : ""} type="button" onClick={syncPending} disabled={Boolean(busy)}><CloudUpload /><span>{pendingCount ? `同步 ${pendingCount}` : "同步"}</span></button>
      <Link to="/operations/mobile-sync"><RefreshCw /><span>同步记录</span></Link>
    </nav>
    <SidePanel open={Boolean(selected)} eyebrow="现场任务" title={selected?.title || "任务详情"} onClose={() => setSelected(null)}>{selected && <TaskDetail task={selected} tracking={Boolean(state.activeTrack)} evidenceCount={state.evidence.filter((item) => item.taskId === selected.id).length} onQueue={queueOperation} onTrack={startTrack} onEvidence={queueEvidence} />}</SidePanel>
  </div>;
}

function TaskDetail({ task, tracking, evidenceCount, onQueue, onTrack, onEvidence }: { task: MobileFieldTask; tracking: boolean; evidenceCount: number; onQueue: (task: MobileFieldTask, action: string, payload: Record<string, unknown>) => void; onTrack: (task: MobileFieldTask) => void; onEvidence: (task: MobileFieldTask, files: FileList) => void }) {
  const [summary, setSummary] = useState("");
  const [quantity, setQuantity] = useState("");
  const action = taskAction(task);
  return <div className="field-task-detail">
    <section><dl><div><dt>任务编号</dt><dd>{task.taskNo}</dd></div><div><dt>当前状态</dt><dd>{statusLabel(task.status)}</dd></div><div><dt>责任人</dt><dd>{task.assigneeName || "待认领"}</dd></div><div><dt>关联林班</dt><dd>{task.linkedBlockCodes.join("、") || "未关联"}</dd></div><div><dt>完成时限</dt><dd>{task.dueAt ? formatDateTime(task.dueAt) : "未设置"}</dd></div></dl></section>
    <section><h3>作业要求</h3><p>{task.instructions || "暂无补充说明，请按现场规范执行。"}</p></section>
    {(action === "report" || action === "submit") && <section className="field-report-form"><h3>{action === "report" ? "现场巡护结论" : "完工上报"}</h3><label><span>{action === "report" ? "巡护结论" : "实际完成量"}</span>{action === "report" ? <textarea rows={4} value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="填写现场情况、发现问题和处置建议" /> : <input type="number" min="0" value={quantity} onChange={(event) => setQuantity(event.target.value)} placeholder="填写实际完成工作量" />}</label></section>}
    <section className="field-evidence-picker"><h3>现场凭证</h3><p>支持拍照或选择视频。文件会先保存在本机，网络恢复后断点续传。</p><label><Camera /><span>{evidenceCount ? `继续添加 · 已暂存 ${evidenceCount} 份` : "拍照或选择文件"}</span><input type="file" accept="image/*,video/*" capture="environment" multiple onChange={(event) => { if (event.target.files?.length) onEvidence(task, event.target.files); event.target.value = ""; }} /></label></section>
    {task.taskType !== "safety" && (task.status === "accepted" || task.status === "patrolling" || task.status === "working") && <button className="button secondary field-track-button" type="button" disabled={tracking} onClick={() => onTrack(task)}><Route />{tracking ? "轨迹记录中" : "开始记录轨迹"}</button>}
    {action && <button className="button primary field-submit-button" type="button" disabled={(action === "report" && summary.trim().length < 2) || (action === "submit" && !Number(quantity))} onClick={() => onQueue(task, action, action === "report" ? { summary: summary.trim(), issueType: "none", locationText: task.linkedBlockCodes.join("、") } : action === "submit" ? { actualQuantity: Number(quantity), note: "移动现场端提交完工记录" } : {})}><Check />{actionText(action)}</button>}
    {!action && <div className="field-no-action"><Check /><span><strong>当前无需现场操作</strong><small>等待后台流转或任务已完成。</small></span></div>}
  </div>;
}

const EVIDENCE_CHUNK_BYTES = 8 * 1024 * 1024;

async function sha256(blob: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function syncEvidence(evidence: MobileEvidenceUpload, onProgress: (updated: MobileEvidenceUpload) => void): Promise<MobileUploadSession> {
  const blob = await readEvidenceBlob(evidence.clientEvidenceId);
  if (!blob) throw new Error(`现场文件 ${evidence.fileName} 已丢失，请重新选择。`);
  let session = evidence.sessionId ? await api.mobileUploadStatus(evidence.sessionId) : await api.createMobileUpload({
    fileName: evidence.fileName,
    contentType: evidence.contentType,
    totalBytes: evidence.totalBytes,
    totalChunks: evidence.totalChunks,
    sha256: evidence.sha256,
    taskType: evidence.taskType,
    taskId: evidence.taskId,
  });
  if (session.status === "completed") return session;
  if (session.status !== "uploading") throw new Error(`现场文件 ${evidence.fileName} 的上传会话已失效，请重新选择。`);
  let current = { ...evidence, sessionId: session.id, receivedChunks: session.receivedChunks, status: "uploading" as const };
  onProgress(current);
  const received = new Set(session.receivedChunks);
  for (let index = 0; index < evidence.totalChunks; index += 1) {
    if (received.has(index)) continue;
    const start = index * EVIDENCE_CHUNK_BYTES;
    session = await api.uploadMobileChunk(session.id, index, blob.slice(start, Math.min(start + EVIDENCE_CHUNK_BYTES, blob.size), evidence.contentType), evidence.fileName);
    current = { ...current, receivedChunks: session.receivedChunks };
    onProgress(current);
  }
  return api.completeMobileUpload(session.id);
}

function TaskIcon({ type }: { type: MobileFieldTask["taskType"] }) { return type === "patrol" ? <Route /> : type === "labor" ? <Navigation /> : <ShieldAlert />; }
function taskAction(task: MobileFieldTask) { if (task.taskType === "patrol") return ({ assigned: "accept", accepted: "start", patrolling: "report" } as Record<string, string>)[task.status] || ""; if (task.taskType === "labor") return ({ contracted: "start", working: "submit" } as Record<string, string>)[task.status] || ""; return ""; }
function optimisticStatus(type: string, action: string, fallback: string) { const key = `${type}:${action}`; return ({ "patrol:accept": "accepted", "patrol:start": "patrolling", "patrol:report": "reported", "labor:start": "working", "labor:submit": "submitted" } as Record<string, string>)[key] || fallback; }
function actionText(action: string) { return ({ accept: "接收任务", start: "确认开始作业", report: "保存巡护结论", submit: "提交完工记录" } as Record<string, string>)[action] || action; }
function typeLabel(type: string) { return ({ patrol: "巡护任务", labor: "劳务作业", safety: "安全处置" } as Record<string, string>)[type] || type; }
function statusLabel(status: string) { return ({ planned: "待派发", assigned: "待接单", accepted: "待出发", patrolling: "巡护中", reported: "待复核", resolved: "已处置", verified: "已复核", closed: "已归档", contracted: "待进场", working: "作业中", submitted: "待验收", new: "待响应", dispatched: "已派单", handling: "处置中" } as Record<string, string>)[status] || status; }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(date); }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date); }
function formatTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(date); }
