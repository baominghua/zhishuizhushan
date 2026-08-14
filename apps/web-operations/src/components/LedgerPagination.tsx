import { ChevronLeft, ChevronRight } from "lucide-react";

export function LedgerPagination({
  total,
  limit,
  offset,
  onPage,
}: {
  total: number;
  limit: number;
  offset: number;
  onPage: (offset: number) => void;
}) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  const start = total ? offset + 1 : 0;
  const end = Math.min(total, offset + limit);
  return (
    <footer className="ledger-footer">
      <span>共 {total.toLocaleString("zh-CN")} 条，当前显示 {start}-{end}</span>
      <div className="pagination-actions">
        <button className="icon-button" type="button" disabled={page <= 1} onClick={() => onPage(Math.max(0, offset - limit))} aria-label="上一页" title="上一页">
          <ChevronLeft aria-hidden="true" />
        </button>
        <strong>{page} / {pages}</strong>
        <button className="icon-button" type="button" disabled={page >= pages} onClick={() => onPage(offset + limit)} aria-label="下一页" title="下一页">
          <ChevronRight aria-hidden="true" />
        </button>
      </div>
    </footer>
  );
}
