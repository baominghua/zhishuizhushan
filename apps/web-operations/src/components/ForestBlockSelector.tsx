import { useQuery } from "@tanstack/react-query";
import { Check, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { ForestBlockOption } from "../api/types";
import { QueryState } from "./QueryState";

interface ForestBlockSelectorProps {
  open: boolean;
  onClose: () => void;
  onSelect: (block: ForestBlockOption) => void;
}

export function ForestBlockSelector({ open, onClose, onSelect }: ForestBlockSelectorProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const blocks = useQuery({
    queryKey: ["forest-block-options", query],
    queryFn: () => api.forestBlocks(query),
    enabled: open,
    staleTime: 30_000,
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog className="entity-dialog" ref={dialogRef} onClose={onClose}>
      <header>
        <div>
          <h2>选择林班</h2>
          <p>从正式林班空间台账检索，不允许自由输入编号。</p>
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="关闭">
          <X aria-hidden="true" />
        </button>
      </header>
      <label className="dialog-search">
        <Search aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索林班编号、名称、区县或乡镇"
          autoFocus
        />
      </label>
      <QueryState loading={blocks.isLoading} error={blocks.error}>
        <div className="selector-results">
          {(blocks.data?.items ?? []).map((block) => (
            <button
              type="button"
              key={block.id}
              onClick={() => {
                onSelect(block);
                onClose();
              }}
            >
              <span>
                <strong>{block.name}</strong>
                <small>{block.code} · {block.location || "未填写行政区划"}</small>
              </span>
              <span className="selector-meta">
                {block.areaMu == null ? "面积待补" : `${block.areaMu} 亩`}
                <Check aria-hidden="true" />
              </span>
            </button>
          ))}
          {blocks.data?.items.length === 0 && (
            <div className="empty-state compact">
              <strong>没有匹配的林班</strong>
              <p>请调整关键词，或先在数据接入模块导入测绘成果。</p>
            </div>
          )}
        </div>
      </QueryState>
    </dialog>
  );
}
