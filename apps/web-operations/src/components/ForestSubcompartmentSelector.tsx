import { useQuery } from "@tanstack/react-query";
import { Check, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { ForestSubcompartmentOption } from "../api/types";
import { QueryState } from "./QueryState";

export function ForestSubcompartmentSelector({ open, onClose, onSelect }: {
  open: boolean;
  onClose: () => void;
  onSelect: (item: ForestSubcompartmentOption) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const options = useQuery({
    queryKey: ["forest-subcompartment-options", query],
    queryFn: () => api.forestSubcompartments(query),
    enabled: open,
    staleTime: 30_000,
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return <dialog className="entity-dialog" ref={dialogRef} onClose={onClose} aria-labelledby="forest-subcompartment-selector-title">
    <header><div><h2 id="forest-subcompartment-selector-title">选择调查小班</h2><p>从正式小班台账选择，调查记录会稳定关联到空间作业单元。</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="关闭"><X aria-hidden="true" /></button></header>
    <label className="dialog-search"><Search aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索小班编号、名称或所属林班" autoFocus /></label>
    <QueryState loading={options.isLoading} error={options.error}>
      <div className="selector-results">
        {(options.data?.items ?? []).map((item) => <button type="button" key={item.id} onClick={() => { onSelect(item); onClose(); }}>
          <span><strong>{item.name}</strong><small>{item.code} · {item.forestBlockCode} {item.forestBlockName}</small></span>
          <span className="selector-meta">{item.areaMu == null ? "面积待补" : `${item.areaMu} 亩`}<Check aria-hidden="true" /></span>
        </button>)}
        {options.data?.items.length === 0 && <div className="empty-state compact"><strong>没有匹配的小班</strong><p>请调整关键词，或先在小班台账建立经营作业单元。</p></div>}
      </div>
    </QueryState>
  </dialog>;
}
