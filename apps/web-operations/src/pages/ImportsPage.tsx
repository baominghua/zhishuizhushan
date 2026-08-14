import { useRef, useState, type DragEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  FileCheck2,
  FileSearch,
  FileUp,
  Download,
  History,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";

import { api } from "../api/client";
import type { ImportJob, ImportJobIssue } from "../api/types";
import { QueryState } from "../components/QueryState";

const ACCEPTED_FORMATS = ".kmz,.kml,.ovkml,.ovkmz,.ovobj,.geojson,.json,.zip,.csv,.xlsx";

export function ImportsPage() {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const historyAnchor = useRef<HTMLElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [strategy, setStrategy] = useState<"upsert" | "skip">("upsert");
  const [job, setJob] = useState<ImportJob | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const jobs = useQuery({ queryKey: ["v2-import-jobs"], queryFn: api.importJobs });

  const refreshJobs = async () => queryClient.invalidateQueries({ queryKey: ["v2-import-jobs"] });
  const analyze = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("请先选择成果文件");
      return api.createImportJob(file, strategy);
    },
    onSuccess: async (next) => { setJob(next); setConfirmed(false); await refreshJobs(); },
  });
  const confirm = useMutation({
    mutationFn: (id: string) => api.confirmImportJob(id),
    onSuccess: async (next) => { setJob(next); await refreshJobs(); },
  });
  const commit = useMutation({
    mutationFn: (id: string) => api.commitImportJob(id),
    onSuccess: async (next) => {
      setJob(next);
      await Promise.all([
        refreshJobs(),
        queryClient.invalidateQueries({ queryKey: ["v2-forest-block-ledger"] }),
        queryClient.invalidateQueries({ queryKey: ["workspace-summary"] }),
      ]);
    },
  });

  const busy = analyze.isPending || confirm.isPending || commit.isPending;
  const error = analyze.error || confirm.error || commit.error;
  const step = job?.status === "completed" ? 3 : job?.status === "ready_to_commit" ? 3 : job ? 2 : 1;
  const reset = () => {
    setFile(null);
    setJob(null);
    setConfirmed(false);
    analyze.reset();
    confirm.reset();
    commit.reset();
    if (fileInput.current) fileInput.current.value = "";
  };
  const selectFile = (next?: File) => {
    if (!next) return;
    setFile(next);
    setJob(null);
    setConfirmed(false);
  };
  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files[0]);
  };

  return (
    <div className="standard-page import-page">
      <section className="page-heading ledger-heading">
        <div><span className="eyebrow">资源数据 / 批量接入</span><h1>数据接入</h1><p>上传后自动检查；无异常直接入库，有异常只确认一次，不再重复审核和验收。</p></div>
        <div className="heading-actions">
          <button className="button secondary" type="button" onClick={() => jobs.refetch()}><RefreshCw aria-hidden="true" />刷新</button>
          <button className="button secondary" type="button" onClick={() => historyAnchor.current?.scrollIntoView({ behavior: "smooth" })}><History aria-hidden="true" />最近接入</button>
        </div>
      </section>

      <ol className="import-steps" aria-label="成果接入流程">
        <ImportStep number={1} title="上传并检查" detail="解析字段、坐标和图形" state={step > 1 ? "done" : "current"} />
        <ImportStep number={2} title="处理异常" detail="只确认阻断记录" state={step > 2 ? "done" : step === 2 ? "current" : "pending"} />
        <ImportStep number={3} title="正式入库" detail="生成批次与审计" state={job?.status === "completed" ? "done" : step === 3 ? "current" : "pending"} />
      </ol>

      <div className="import-workbench-grid">
        <section className="import-workbench">
          {!job && (
            <>
              <div
                className={`upload-zone ${dragging ? "dragging" : ""}`}
                onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setDragging(false)}
                onDrop={drop}
              >
                <UploadCloud aria-hidden="true" />
                <h2>{file ? "文件已选择" : "上传林班测绘成果"}</h2>
                <p>{file ? file.name : "拖入文件，或从电脑中选择"}</p>
                {file && <small>{formatBytes(file.size)} · 等待系统检查</small>}
                <input ref={fileInput} type="file" accept={ACCEPTED_FORMATS} hidden onChange={(event) => selectFile(event.target.files?.[0])} />
                <div className="upload-zone-actions">
                  <button className="button secondary" type="button" onClick={() => fileInput.current?.click()}><FileUp aria-hidden="true" />{file ? "更换文件" : "选择文件"}</button>
                  {file && <button className="text-button" type="button" onClick={() => setFile(null)}>移除</button>}
                </div>
              </div>
              <div className="import-options">
                <div><strong>重复编号处理</strong><p>系统会先检查现有林班，不会静默生成重复编号。</p></div>
                <div className="segmented-control" aria-label="重复编号处理策略">
                  <button type="button" className={strategy === "upsert" ? "active" : ""} onClick={() => setStrategy("upsert")}><Check aria-hidden="true" />更新现有</button>
                  <button type="button" className={strategy === "skip" ? "active" : ""} onClick={() => setStrategy("skip")}><Check aria-hidden="true" />仅新增</button>
                </div>
              </div>
              <div className="import-primary-action">
                <span>支持 KMZ、OVKML、OVOBJ、GeoJSON、Shapefile ZIP、CSV、XLSX</span>
                <button className="button primary" type="button" disabled={!file || busy} onClick={() => analyze.mutate()}><FileSearch aria-hidden="true" />{analyze.isPending ? "正在检查…" : "开始检查"}</button>
              </div>
            </>
          )}

          {job && <ImportJobView job={job} confirmed={confirmed} busy={busy} onConfirmed={setConfirmed} onReset={reset} onConfirm={() => confirm.mutate(job.id)} onCommit={() => commit.mutate(job.id)} />}
          {error && <p className="form-error import-error">{error.message}</p>}
        </section>

        <aside className="import-automation-panel">
          <h2>系统自动完成</h2>
          <ul>
            <AutomationItem title="原文件留痕" detail="保存 SHA-256，后续可核验来源" />
            <AutomationItem title="空间与字段检查" detail="识别坐标、几何、编号和必填字段" />
            <AutomationItem title="重复记录识别" detail="按正式林班编号判断新增或更新" />
            <AutomationItem title="入库审计" detail="批次、操作者和结果自动进入审计" />
          </ul>
          <div className="help-block"><ShieldCheck aria-hidden="true" /><div><strong>业务人员只作一次决定</strong><p>技术日志、回执和操作队列不再占用业务流程。</p></div></div>
        </aside>
      </div>

      <section className="recent-imports" ref={historyAnchor}>
        <div className="section-heading"><div><span className="eyebrow">接入记录</span><h2>最近任务</h2></div><span>{jobs.data?.total ?? 0} 个任务</span></div>
        <QueryState loading={jobs.isLoading} error={jobs.error}>
          <div className="recent-import-list">
            {jobs.data?.items.map((item) => (
              <button type="button" key={item.id} onClick={() => { setJob(item); setFile(null); setConfirmed(item.status !== "needs_confirmation"); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                <FileCheck2 aria-hidden="true" /><span><strong>{item.fileName}</strong><small>{formatDateTime(item.createdAt)} · {item.validRows}/{item.totalRows} 条可入库</small></span><JobStatus job={item} /><ArrowRight aria-hidden="true" />
              </button>
            ))}
            {!jobs.data?.items.length && <div className="recent-import-empty"><History aria-hidden="true" /><p>还没有 V2 接入任务，上传第一份测绘成果后会显示在这里。</p></div>}
          </div>
        </QueryState>
      </section>
    </div>
  );
}

function ImportJobView({ job, confirmed, busy, onConfirmed, onReset, onConfirm, onCommit }: { job: ImportJob; confirmed: boolean; busy: boolean; onConfirmed: (value: boolean) => void; onReset: () => void; onConfirm: () => void; onCommit: () => void }) {
  const blocking = job.invalidRows > 0;
  const completed = job.status === "completed";
  return <div className="import-job-view">
    <header className="import-result-heading">
      <div><FileCheck2 aria-hidden="true" /><span><small>{job.fileType.toUpperCase()} · {formatBytes(job.sizeBytes)}</small><h2>{job.fileName}</h2><p>文件校验码 {job.sha256.slice(0, 12)}…</p></span></div>
      <JobStatus job={job} />
    </header>
    <div className="import-metrics">
      <Metric label="识别记录" value={job.totalRows} />
      <Metric label="可入库" value={job.validRows} tone="success" />
      <Metric label="阻断记录" value={job.invalidRows} tone={blocking ? "warning" : "success"} />
      <Metric label="现有编号" value={job.existingRows} />
    </div>
    {job.issues.length > 0 && !completed && <section className="import-issues"><div className="section-heading"><div><span className="eyebrow">质量规则检查</span><h3>{job.blockingIssues ?? job.invalidRows} 个阻断问题 · {job.warningIssues ?? 0} 个提醒</h3></div><button className="button secondary" type="button" onClick={() => api.exportImportIssues(job.id)}><Download aria-hidden="true" />导出问题清单</button></div><div className="issue-list">{job.issues.slice(0, 30).map((issue) => <IssueRow key={issue.id} issue={issue} />)}</div>{blocking && <label className="issue-confirmation"><input type="checkbox" checked={confirmed} onChange={(event) => onConfirmed(event.target.checked)} /><span><strong>跳过阻断记录，继续导入通过项</strong><small>本次只写入 {job.validRows} 条通过规则检查的记录；问题行保留并可导出修复。</small></span></label>}</section>}
    {!blocking && !completed && <div className="import-ready-note"><CheckCircle2 aria-hidden="true" /><div><strong>{(job.warningIssues ?? 0) > 0 ? "检查通过，存在非阻断提醒" : "检查通过，可以直接入库"}</strong><p>{job.validRows} 条记录均可入库{(job.warningIssues ?? 0) > 0 ? `，${job.warningIssues} 个提醒可在台账中后续补充。` : "，不需要额外审核。"}</p></div></div>}
    {completed && <div className="import-complete-note"><CheckCircle2 aria-hidden="true" /><div><strong>成果已正式入库</strong><p>已写入 {job.commitSummary?.importedBlocks ?? job.validRows} 条林班结果，系统已生成批次和审计记录。</p></div><Link className="button secondary" to="/resources/forest-blocks">查看林班台账<ArrowRight aria-hidden="true" /></Link></div>}
    <section className="import-preview"><div className="section-heading"><div><span className="eyebrow">解析预览</span><h3>前 {job.preview.length} 条记录</h3></div></div><div className="table-scroll"><table><thead><tr><th>行</th><th>林班编号</th><th>名称</th><th>村</th><th>面积</th><th>检查</th></tr></thead><tbody>{job.preview.map((record) => <tr key={record.row}><td>{record.row}</td><td>{record.blockCode || "-"}</td><td>{record.name || "-"}</td><td>{record.villageName || "-"}</td><td>{record.areaMu == null ? "-" : `${record.areaMu} 亩`}</td><td><span className={`record-check ${record.valid ? "success" : "warning"}`}>{record.valid ? "通过" : "阻断"}</span></td></tr>)}</tbody></table></div></section>
    <div className="import-job-actions"><button className="button secondary" type="button" onClick={onReset} disabled={busy}><RotateCcw aria-hidden="true" />导入下一份</button>{job.status === "needs_confirmation" && <button className="button primary" type="button" disabled={!confirmed || busy} onClick={onConfirm}><ShieldCheck aria-hidden="true" />{busy ? "正在确认…" : "确认处理方式"}</button>}{job.status === "ready_to_commit" && <button className="button primary" type="button" disabled={busy} onClick={onCommit}><FileUp aria-hidden="true" />{busy ? "正在入库…" : `正式入库 ${job.validRows} 条`}</button>}</div>
  </div>;
}

function ImportStep({ number, title, detail, state }: { number: number; title: string; detail: string; state: "pending" | "current" | "done" }) { return <li className={state}><span>{state === "done" ? <Check aria-hidden="true" /> : number}</span><div><strong>{title}</strong><small>{detail}</small></div></li>; }
function AutomationItem({ title, detail }: { title: string; detail: string }) { return <li><Check aria-hidden="true" /><span><strong>{title}</strong><small>{detail}</small></span></li>; }
function Metric({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "success" | "warning" }) { return <div className={tone}><span>{label}</span><strong>{value}</strong></div>; }
function IssueRow({ issue }: { issue: ImportJobIssue }) { return <div className={`issue-row ${issue.severity}`}><AlertTriangle aria-hidden="true" /><span><strong>第 {issue.row} 行 · {issue.blockCode || "编号缺失"} · {issue.code}</strong><small>{translateIssue(issue.message)}{issue.name ? ` · ${issue.name}` : ""}</small><small>建议：{issue.suggestion}</small></span></div>; }
function JobStatus({ job }: { job: ImportJob }) { const values = { needs_confirmation: ["待确认", "warning"], ready_to_commit: ["待入库", "ready"], completed: ["已完成", "success"], failed: ["失败", "danger"] } as const; const [label, tone] = values[job.status] || [job.status, "ready"]; return <span className={`job-status ${tone}`}>{label}</span>; }
function translateIssue(message: string) { if (message.includes("blockCode is required")) return "缺少林班编号"; if (message.includes("name is required")) return "缺少林班名称"; return message; }
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB`; }
function formatDateTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false }); }
