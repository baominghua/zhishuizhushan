import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, ClipboardCheck, Download, FileClock, MailOpen, RotateCcw, Search } from "lucide-react";
import { useState } from "react";

import { api } from "../api/client";
import type { LedgerResponse, OperationsAuditEvent, OperationsTodo } from "../api/types";
import { QueryState } from "../components/QueryState";

type Mode = "todos" | "notifications" | "audit";
const MODULES = [
  ["", "全部模块"], ["patrol", "巡护办理"], ["harvest", "采伐办理"], ["labor", "劳务用工"],
  ["safety", "事件中心"], ["drone", "无人机任务"], ["ai", "AI 识别复核"],
] as const;

export function OperationsCenterPage({ mode }: { mode: Mode }) {
  const [q, setQ] = useState("");
  const [module, setModule] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const queryClient = useQueryClient();
  const query = useQuery<LedgerResponse<OperationsTodo | OperationsAuditEvent>>({
    queryKey: ["operations-center", mode, q, module, unreadOnly],
    queryFn: () => mode === "todos"
      ? api.operationsTodos({ q, module, limit: 100 })
      : mode === "notifications"
        ? api.operationsNotifications({ q, module, unreadOnly, limit: 100 })
        : api.operationsAudit({ q, module, limit: 100 }),
    staleTime: 15_000,
  });
  const readMutation = useMutation({
    mutationFn: ({ id, read }: { id: string; read: boolean }) => read ? api.markNotificationRead(id) : api.markNotificationUnread(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["operations-center"] }),
  });
  const readAllMutation = useMutation({ mutationFn: api.markAllNotificationsRead, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["operations-center"] }) });
  const config = mode === "todos"
    ? { title: "我的待办", copy: "聚合当前账号权限与数据范围内的未完成事项。", icon: ClipboardCheck }
    : mode === "notifications"
      ? { title: "消息中心", copy: "业务状态变化集中送达，已读状态按当前账号保存。", icon: Bell }
      : { title: "审计中心", copy: "跨业务查看不可篡改的操作流水，并按条件导出。", icon: FileClock };
  const Icon = config.icon;
  const items = query.data?.items ?? [];

  return <div className="operations-center-page">
    <section className="page-heading">
      <div><h1>{config.title}</h1><p>{config.copy}</p></div>
      <div className="heading-actions">
        <a className="button secondary" href={`/api/v2/operations-center/${mode === "audit" ? "audit" : mode}.csv?q=${encodeURIComponent(q)}&module=${encodeURIComponent(module)}${mode === "notifications" && unreadOnly ? "&unreadOnly=true" : ""}`}><Download aria-hidden="true" />导出</a>
        {mode === "notifications" && <button className="button secondary" type="button" disabled={readAllMutation.isPending} onClick={() => readAllMutation.mutate()}><CheckCheck aria-hidden="true" />全部已读</button>}
        <button className="button secondary" type="button" onClick={() => query.refetch()}><RotateCcw aria-hidden="true" />刷新</button>
      </div>
    </section>
    <section className="ledger-panel operations-ledger">
      <header className="section-heading operations-heading"><span><Icon aria-hidden="true" /></span><div><h2>{config.title}台账</h2><p>共 {query.data?.total ?? 0} 条</p></div></header>
      <div className="ledger-toolbar operations-toolbar">
        <label className="search-control"><Search aria-hidden="true" /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="搜索单号、名称、操作人或说明" /></label>
        <select value={module} onChange={(event) => setModule(event.target.value)} aria-label="业务模块">{MODULES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        {mode === "notifications" && <label className="inline-check"><input type="checkbox" checked={unreadOnly} onChange={(event) => setUnreadOnly(event.target.checked)} />只看未读</label>}
      </div>
      <QueryState loading={query.isLoading} error={query.error}>
        {items.length ? <div className="ledger-shell"><table className="ledger-table operations-table"><thead><tr>
          <th>业务事项</th><th>模块 / 状态</th><th>{mode === "todos" ? "责任与时限" : "操作信息"}</th><th>关联信息</th><th>时间</th><th className="action-column">操作</th>
        </tr></thead><tbody>{items.map((item) => mode === "todos"
          ? <TodoRow key={item.id} item={item as OperationsTodo} />
          : <AuditRow key={item.id} item={item as OperationsAuditEvent} notification={mode === "notifications"} toggle={(read) => readMutation.mutate({ id: item.id, read })} />
        )}</tbody></table></div>
        : <div className="empty-state"><strong>暂无符合条件的记录</strong><p>调整关键词或模块筛选后再试。</p></div>}
      </QueryState>
    </section>
  </div>;
}

function TodoRow({ item }: { item: OperationsTodo }) {
  return <tr><td><strong>{item.title}</strong><small>{item.recordNo || item.recordId}</small></td><td><strong>{item.moduleLabel}</strong><small><span className={`status-badge ${item.priority === "critical" || item.priority === "urgent" ? "danger" : "warning"}`}>{item.statusLabel}</span></small></td><td><strong>{item.assigneeName || "待明确"}</strong><small>{formatTime(item.dueAt) || "未设置时限"}</small></td><td><strong>{item.linkedBlockCodes.slice(0, 2).join("、") || "未关联"}</strong><small>{item.linkedBlockCodes.length > 2 ? `另 ${item.linkedBlockCodes.length - 2} 个` : ""}</small></td><td><strong>{formatTime(item.updatedAt)}</strong><small>最近更新</small></td><td className="action-column"><a className="table-action" href={`/v2${item.targetPath}`}>去办理</a></td></tr>;
}

function AuditRow({ item, notification, toggle }: { item: OperationsAuditEvent; notification: boolean; toggle: (read: boolean) => void }) {
  return <tr className={notification && !item.read ? "unread-row" : ""}><td><strong>{item.recordName || item.recordNo}</strong><small>{item.recordNo || item.recordId}</small></td><td><strong>{item.moduleLabel}</strong><small>{item.fromStatus || "-"} → {item.toStatus || "-"}</small></td><td><strong>{item.actor || "系统"}</strong><small>{item.message || item.action}</small></td><td><strong>业务流水</strong><small>源记录留痕</small></td><td><strong>{formatTime(item.createdAt)}</strong><small>{item.action}</small></td><td className="action-column"><a className="table-action" href={`/v2${item.targetPath}`}>查看</a>{notification && <button className="icon-button compact" type="button" title={item.read ? "标为未读" : "标为已读"} aria-label={item.read ? "标为未读" : "标为已读"} onClick={() => toggle(!item.read)}>{item.read ? <MailOpen aria-hidden="true" /> : <CheckCheck aria-hidden="true" />}</button>}</td></tr>;
}

function formatTime(value: string) {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN", { hour12: false });
}
