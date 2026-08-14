import { useQuery } from "@tanstack/react-query";
import { Check, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { ForestRightOption, HarvestSubject } from "../api/types";
import { QueryState } from "./QueryState";

type SelectorProps<T> = { open: boolean; onClose: () => void; onSelect: (item: T) => void };

export function HarvestSubjectSelector({ open, onClose, onSelect }: SelectorProps<HarvestSubject>) {
  const dialogRef = useDialog(open);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const subjects = useQuery({
    queryKey: ["harvest-subjects", query, type],
    queryFn: () => api.harvestSubjects(query, type),
    enabled: open,
    staleTime: 30_000,
  });
  return <dialog className="entity-dialog harvest-selector-dialog" ref={dialogRef} onClose={onClose}>
    <DialogHeader title="选择经营主体" description="从竹农、合作社和竹企正式台账选择申请人。" onClose={onClose} />
    <div className="selector-filter-row"><label className="dialog-search"><Search aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索主体名称或编号" autoFocus /></label><select aria-label="主体类型" value={type} onChange={(event) => setType(event.target.value)}><option value="">全部主体</option><option value="farmer">竹农</option><option value="cooperative">合作社</option><option value="enterprise">竹企</option></select></div>
    <QueryState loading={subjects.isLoading} error={subjects.error}><div className="selector-results">
      {(subjects.data?.items ?? []).map((subject) => <button type="button" key={subject.id} onClick={() => { onSelect(subject); onClose(); }}><span><strong>{subject.name}</strong><small>{SUBJECT_LABELS[subject.type]} · {subject.code}</small></span><span className="selector-meta">{subject.status || "状态未填"}<Check aria-hidden="true" /></span></button>)}
      {!subjects.isLoading && subjects.data?.items.length === 0 && <SelectorEmpty title="没有匹配的经营主体" detail="请先在经营主体台账建立竹农、合作社或竹企档案。" />}
    </div></QueryState>
  </dialog>;
}

export function ForestRightSelector({ open, onClose, onSelect, linkedBlockCode = "" }: SelectorProps<ForestRightOption> & { linkedBlockCode?: string }) {
  const dialogRef = useDialog(open);
  const [query, setQuery] = useState("");
  const rights = useQuery({
    queryKey: ["forest-right-options", query, linkedBlockCode],
    queryFn: () => api.forestRights(query, linkedBlockCode),
    enabled: open,
    staleTime: 30_000,
  });
  return <dialog className="entity-dialog harvest-selector-dialog" ref={dialogRef} onClose={onClose}>
    <DialogHeader title="选择林权档案" description={linkedBlockCode ? `优先显示覆盖林班 ${linkedBlockCode} 的有效权属档案。` : "从正式林权档案台账选择权属依据。"} onClose={onClose} />
    <label className="dialog-search"><Search aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索档案号、证号或权利人" autoFocus /></label>
    <QueryState loading={rights.isLoading} error={rights.error}><div className="selector-results">
      {(rights.data?.items ?? []).map((right) => <button type="button" key={right.id} onClick={() => { onSelect(right); onClose(); }}><span><strong>{right.holder}</strong><small>{right.code} · {right.certificateNo || "证号待补"}</small></span><span className="selector-meta">{right.status || "状态未填"}<Check aria-hidden="true" /></span></button>)}
      {!rights.isLoading && rights.data?.items.length === 0 && <SelectorEmpty title="没有匹配的林权档案" detail="请确认所选林班已经完成图档关联，并且档案处于有效状态。" />}
    </div></QueryState>
  </dialog>;
}

const SUBJECT_LABELS = { farmer: "竹农", cooperative: "合作社", enterprise: "竹企" };
function useDialog(open: boolean) { const ref = useRef<HTMLDialogElement>(null); useEffect(() => { const dialog = ref.current; if (!dialog) return; if (open && !dialog.open) dialog.showModal(); if (!open && dialog.open) dialog.close(); }, [open]); return ref; }
function DialogHeader({ title, description, onClose }: { title: string; description: string; onClose: () => void }) { return <header><div><h2>{title}</h2><p>{description}</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="关闭"><X aria-hidden="true" /></button></header>; }
function SelectorEmpty({ title, detail }: { title: string; detail: string }) { return <div className="empty-state compact"><strong>{title}</strong><p>{detail}</p></div>; }
