import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, FileUp, Paperclip, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { AttachmentRecord } from "../api/types";
import { QueryState } from "./QueryState";

export function AttachmentSelector({ open, selectedIds, onClose, onChange, category = "survey_evidence", title = "选择业务证据", maxSelections }: {
  open: boolean;
  selectedIds: string[];
  onClose: () => void;
  onChange: (items: AttachmentRecord[]) => void;
  category?: string;
  title?: string;
  maxSelections?: number;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const selectionInitializedRef = useRef(false);
  const client = useQueryClient();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<AttachmentRecord[]>([]);
  const options = useQuery({ queryKey: ["attachment-options", query], queryFn: () => api.attachments({ q: query, limit: 100 }), enabled: open });
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadAttachment(file, category),
    onSuccess: async (record) => { setSelected((items) => [...items.filter((item) => item.id !== record.id), record]); await client.invalidateQueries({ queryKey: ["attachment-options"] }); },
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!open) selectionInitializedRef.current = false;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  useEffect(() => {
    if (!open || !options.data || selectionInitializedRef.current) return;
    setSelected(options.data.items.filter((item) => selectedIds.includes(item.id)));
    selectionInitializedRef.current = true;
  }, [open, options.data, selectedIds]);

  const toggle = (record: AttachmentRecord) => setSelected((items) => {
    if (items.some((item) => item.id === record.id)) return items.filter((item) => item.id !== record.id);
    if (maxSelections === 1) return [record];
    if (maxSelections && items.length >= maxSelections) return items;
    return [...items, record];
  });
  return <dialog className="entity-dialog attachment-dialog" ref={dialogRef} onClose={onClose} aria-labelledby="attachment-selector-title">
    <header><div><h2 id="attachment-selector-title">{title}</h2><p>从受控附件中心选择，或上传新的照片、文档和成果文件。</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="关闭"><X aria-hidden="true" /></button></header>
    <div className="attachment-dialog-toolbar">
      <label className="dialog-search"><Search aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件名、摘要或哈希" /></label>
      <input ref={fileRef} type="file" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); event.target.value = ""; }} />
      <button className="button secondary" type="button" disabled={upload.isPending} onClick={() => fileRef.current?.click()}><FileUp aria-hidden="true" />{upload.isPending ? "上传中" : "上传附件"}</button>
    </div>
    {upload.error && <p className="form-error">{upload.error.message}</p>}
    <QueryState loading={options.isLoading} error={options.error}><div className="selector-results attachment-results">
      {(options.data?.items ?? []).map((item) => { const checked = selected.some((selectedItem) => selectedItem.id === item.id); return <button type="button" className={checked ? "selected" : ""} key={item.id} onClick={() => toggle(item)}><span className="attachment-result-icon"><Paperclip aria-hidden="true" /></span><span><strong>{item.originalName}</strong><small>{formatBytes(item.sizeBytes)} · {item.category} · {item.sha256.slice(0, 12)}</small></span><span className="selector-meta">{checked ? "已选择" : "选择"}<Check aria-hidden="true" /></span></button>; })}
      {!options.isLoading && !options.data?.items.length && <div className="empty-state compact"><strong>附件中心暂无文件</strong><p>点击“上传附件”建立第一份受控证据。</p></div>}
    </div></QueryState>
    <footer className="dialog-footer"><span>已选择 {selected.length} 项{maxSelections ? `，最多 ${maxSelections} 项` : ""}</span><div><button className="button secondary" type="button" onClick={onClose}>取消</button><button className="button primary" type="button" onClick={() => { onChange(selected); onClose(); }}>确认选择</button></div></footer>
  </dialog>;
}

function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB`; }
