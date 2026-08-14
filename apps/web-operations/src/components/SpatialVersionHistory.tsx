import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, History, RotateCcw } from "lucide-react";

import type { LedgerResponse, SpatialVersionRecord } from "../api/types";
import { QueryState } from "./QueryState";

type SpatialVersionHistoryProps = {
  entityId: string;
  queryKey: string;
  currentVersion?: number;
  canRollback: boolean;
  load: () => Promise<LedgerResponse<SpatialVersionRecord>>;
  rollback: (versionId: string) => Promise<unknown>;
  onRestored: () => Promise<void> | void;
};

const CHANGE_LABELS: Record<string, string> = {
  create: "创建记录",
  update: "更新记录",
  delete: "移入回收站",
  rollback: "历史回退",
};

export function SpatialVersionHistory({
  entityId,
  queryKey,
  currentVersion,
  canRollback,
  load,
  rollback,
  onRestored,
}: SpatialVersionHistoryProps) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: [queryKey, entityId],
    queryFn: load,
  });
  const restore = useMutation({
    mutationFn: rollback,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: [queryKey, entityId] });
      await onRestored();
    },
  });
  const requestRestore = (item: SpatialVersionRecord) => {
    const label = item.version ? `v${item.version}` : formatDateTime(item.createdAt);
    if (window.confirm(`确认恢复到 ${label}？\n系统会先保留当前状态，并新增一条“历史回退”记录。`)) {
      restore.mutate(item.id);
    }
  };

  return (
    <section className="spatial-version-history">
      <header>
        <div><History aria-hidden="true" /><span><strong>版本历史</strong><small>每次属性或边界修改均自动留痕</small></span></div>
        <span>{query.data?.total ?? 0} 个版本</span>
      </header>
      <QueryState loading={query.isLoading} error={query.error}>
        <div className="spatial-version-list">
          {query.data?.items.map((item, index) => {
            const snapshot = item.snapshot || {};
            const isCurrent = index === 0 || (item.version != null && item.version === currentVersion);
            return (
              <article key={item.id}>
                <div className="spatial-version-marker">{isCurrent ? <Check aria-hidden="true" /> : null}</div>
                <div className="spatial-version-copy">
                  <div><strong>{item.version ? `v${item.version}` : CHANGE_LABELS[item.changeType] || "历史版本"}</strong><span>{CHANGE_LABELS[item.changeType] || item.changeType}</span></div>
                  <p>{String(snapshot.name || snapshot.blockCode || snapshot.subcompartmentCode || "未命名记录")}</p>
                  <small>{formatDateTime(item.createdAt)} · {item.createdBy || "系统"} · {snapshot.geometry ? "有空间边界" : "无空间边界"}</small>
                </div>
                <button className="icon-button" type="button" disabled={!canRollback || isCurrent || restore.isPending} onClick={() => requestRestore(item)} aria-label="恢复此版本" title={canRollback ? (isCurrent ? "当前版本" : "恢复此版本") : "当前角色无版本回退权限"}><RotateCcw aria-hidden="true" /></button>
              </article>
            );
          })}
          {!query.isLoading && !query.data?.items.length && <div className="version-empty">尚无历史版本</div>}
        </div>
        {restore.error && <p className="form-error">{restore.error.message}</p>}
      </QueryState>
    </section>
  );
}

function formatDateTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}
