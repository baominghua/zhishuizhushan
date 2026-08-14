import { X } from "lucide-react";
import { type ReactNode, useEffect } from "react";

export function SidePanel({
  open,
  title,
  eyebrow,
  children,
  footer,
  onClose,
  wide = false,
}: {
  open: boolean;
  title: string;
  eyebrow: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);

  if (!open) return null;
  return (
    <div className="panel-layer" role="presentation">
      <button className="panel-scrim" type="button" onClick={onClose} aria-label="关闭面板" />
      <aside className={`side-panel ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="side-panel-header">
          <div><small>{eyebrow}</small><h2>{title}</h2></div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭" title="关闭">
            <X aria-hidden="true" />
          </button>
        </header>
        <div className="side-panel-body">{children}</div>
        {footer && <footer className="side-panel-footer">{footer}</footer>}
      </aside>
    </div>
  );
}
