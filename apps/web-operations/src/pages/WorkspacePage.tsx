import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  ArrowRight,
  BellRing,
  ClipboardCheck,
  Clock3,
  Database,
  FileWarning,
  FolderKey,
  MapPinned,
  RefreshCw,
  ShieldCheck,
  Sprout,
  Trees,
  Upload,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { ForestBlockOption, OperationsAuditEvent, OperationsTodo } from "../api/types";
import { ForestBlockSelector } from "../components/ForestBlockSelector";
import { QueryState } from "../components/QueryState";

const quickActions: Array<{ to: string; label: string; hint: string; icon: LucideIcon }> = [
  { to: "/map", label: "GIS 一张图", hint: "查看林班空间态势", icon: MapPinned },
  { to: "/resources/imports", label: "成果接入", hint: "导入 KMZ 与调查成果", icon: Upload },
  { to: "/operations/patrol", label: "巡护办理", hint: "处理巡护任务与记录", icon: ShieldCheck },
  { to: "/carbon/estimates", label: "碳汇项目", hint: "核算碳储量与收益", icon: Sprout },
];

export function WorkspacePage() {
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [selectedBlock, setSelectedBlock] = useState<ForestBlockOption | null>(null);
  const summary = useQuery({
    queryKey: ["workspace-summary"],
    queryFn: api.workspaceSummary,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
  const availableModules = useMemo(
    () => Object.values(summary.data?.moduleAvailability || {}).filter((status) => status === "available").length,
    [summary.data?.moduleAvailability],
  );
  const totalModules = Object.keys(summary.data?.moduleAvailability || {}).length;
  const principal = summary.data?.principal.user || "林业管理员";

  return (
    <div className="workspace-page workspace-dashboard">
      <header className="workspace-hero">
        <div>
          <span className="workspace-eyebrow"><i />今日工作总览</span>
          <h1>{greeting()}，{principal}</h1>
          <p>聚焦当前账号权限范围内的待办、风险和正式业务台账。</p>
        </div>
        <div className="workspace-sync">
          <span><i />数据已同步</span>
          <time>{new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" })}</time>
          <button className="icon-button" type="button" title="刷新工作台" aria-label="刷新工作台" onClick={() => summary.refetch()}>
            <RefreshCw aria-hidden="true" className={summary.isFetching ? "spinning" : ""} />
          </button>
        </div>
      </header>

      <QueryState loading={summary.isLoading} error={summary.error}>
        <section className="workspace-status-strip" aria-label="工作台关键指标">
          <WorkspaceMetric icon={Trees} label="林班空间台账" value={summary.data?.metrics.forestBlocks ?? 0} hint="正式林班" />
          <WorkspaceMetric icon={FolderKey} label="林权档案台账" value={summary.data?.metrics.forestRights ?? 0} hint="法律凭证" />
          <WorkspaceMetric icon={ClipboardCheck} label="当前待办" value={summary.data?.todos.length ?? 0} hint="按风险排序" />
          <WorkspaceMetric icon={FileWarning} label="质量问题" value={summary.data?.metrics.openQualityIssues ?? 0} hint="待处理项" warning />
        </section>

        <section className="workspace-command-bar" aria-label="常用功能">
          <div><strong>快捷操作</strong><small>常用业务入口</small></div>
          {quickActions.map(({ to, label, hint, icon: Icon }) => (
            <Link key={to} to={to}>
              <Icon aria-hidden="true" />
              <span><strong>{label}</strong><small>{hint}</small></span>
              <ArrowRight aria-hidden="true" />
            </Link>
          ))}
        </section>

        <div className="workspace-layout">
          <section className="workspace-primary-panel">
            <header className="workspace-section-heading">
              <div><span>任务队列</span><h2>我的优先待办</h2><p>按照时限、优先级和业务风险汇总。</p></div>
              <Link to="/operations/todos">全部待办<ArrowRight aria-hidden="true" /></Link>
            </header>
            {summary.data?.todos.length ? (
              <div className="workspace-task-list">
                {summary.data.todos.slice(0, 6).map((item, index) => <TodoRow key={item.id} item={item} index={index} />)}
              </div>
            ) : (
              <div className="workspace-clear-state"><ShieldCheck aria-hidden="true" /><strong>{summary.data?.emptyState}</strong><p>当前账号权限范围内没有未完成业务事项。</p></div>
            )}
          </section>

          <aside className="workspace-side-column">
            <section className="workspace-signal-panel">
              <header><div><span>运行信号</span><h2>提醒与数据状态</h2></div><BellRing aria-hidden="true" /></header>
              <div className="workspace-availability">
                <span><Database aria-hidden="true" /><b>{availableModules}/{totalModules || 0}</b><small>模块数据源可用</small></span>
                <span className={(summary.data?.alerts.length || 0) > 0 ? "has-alert" : ""}><AlertTriangle aria-hidden="true" /><b>{summary.data?.alerts.length || 0}</b><small>近期业务提醒</small></span>
              </div>
              <AlertList items={summary.data?.alerts.slice(0, 3) || []} />
              <Link className="workspace-panel-link" to="/system/notifications">进入消息中心<ArrowRight aria-hidden="true" /></Link>
            </section>

            <section className="workspace-locator-panel">
              <header><div><span>空间联动</span><h2>林班快速定位</h2></div><MapPinned aria-hidden="true" /></header>
              {selectedBlock ? (
                <div className="workspace-selected-block">
                  <strong>{selectedBlock.name}</strong>
                  <span>{selectedBlock.code}</span>
                  <small>{selectedBlock.location} · {selectedBlock.areaMu ?? "--"} 亩</small>
                </div>
              ) : <p>从正式林班台账中选择一个对象，快速进入 GIS 查看空间详情。</p>}
              {selectedBlock ? <div className="workspace-locator-actions">
                <button className="button secondary" type="button" onClick={() => setSelectorOpen(true)}>重新选择</button>
                <a className="button primary" href={`/v2/map?blockId=${encodeURIComponent(selectedBlock.id)}`}><MapPinned aria-hidden="true" />进入 GIS 定位</a>
              </div> : <button className="button primary full" type="button" onClick={() => setSelectorOpen(true)}><MapPinned aria-hidden="true" />选择林班</button>}
            </section>
          </aside>
        </div>
      </QueryState>
      <ForestBlockSelector open={selectorOpen} onClose={() => setSelectorOpen(false)} onSelect={(block) => { setSelectedBlock(block); setSelectorOpen(false); }} />
    </div>
  );
}

function WorkspaceMetric({ icon: Icon, label, value, hint, warning = false }: { icon: LucideIcon; label: string; value: number; hint: string; warning?: boolean }) {
  return <article className={warning && value > 0 ? "warning" : ""}><Icon aria-hidden="true" /><span><small>{label}</small><strong>{value.toLocaleString("zh-CN")}</strong><em>{hint}</em></span></article>;
}

function TodoRow({ item, index }: { item: OperationsTodo; index: number }) {
  const overdue = Boolean(item.dueAt && new Date(item.dueAt).getTime() < Date.now());
  return <a className="workspace-task-row" href={`/v2${item.targetPath}`} style={{ animationDelay: `${index * 55}ms` }}>
    <span className={`workspace-priority ${priorityClass(item.priority)}`}>{priorityLabel(item.priority)}</span>
    <span className="workspace-task-copy"><strong>{item.title}</strong><small>{item.moduleLabel} · {item.recordNo || item.statusLabel}</small></span>
    <span className="workspace-task-owner">{item.assigneeName || "待分配"}</span>
    <time className={overdue ? "overdue" : ""}><Clock3 aria-hidden="true" />{item.dueAt ? new Date(item.dueAt).toLocaleDateString("zh-CN") : "未设时限"}</time>
    <ArrowRight aria-hidden="true" />
  </a>;
}

function AlertList({ items }: { items: OperationsAuditEvent[] }) {
  if (!items.length) return <div className="workspace-no-alert"><ShieldCheck aria-hidden="true" /><span><strong>运行平稳</strong><small>暂无新的业务提醒</small></span></div>;
  return <div className="workspace-alert-list">{items.map((item) => <a key={item.id} href={`/v2${item.targetPath}`}><i /><span><strong>{item.recordName || item.message}</strong><small>{item.moduleLabel} · {item.action}</small></span><time>{new Date(item.createdAt).toLocaleDateString("zh-CN")}</time></a>)}</div>;
}

function greeting() { const hour = new Date().getHours(); return hour < 6 ? "夜深了" : hour < 11 ? "上午好" : hour < 14 ? "中午好" : hour < 18 ? "下午好" : "晚上好"; }
function priorityClass(value: string) { const normalized = value.toLowerCase(); return normalized.includes("high") || normalized.includes("urgent") || normalized.includes("高") ? "high" : normalized.includes("medium") || normalized.includes("中") ? "medium" : "normal"; }
function priorityLabel(value: string) { const type = priorityClass(value); return type === "high" ? "紧急" : type === "medium" ? "关注" : "常规"; }
