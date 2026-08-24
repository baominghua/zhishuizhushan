export interface LedgerSummaryMetric {
  label: string;
  value: number | string;
  detail: string;
  tone?: "active" | "warning" | "";
}

export function LedgerSummaryStrip({ metrics, className = "" }: { metrics: LedgerSummaryMetric[]; className?: string }) {
  return <section className={`domain-summary-strip ${className}`.trim()} aria-label="台账汇总统计">
    {metrics.slice(0, 4).map((metric) => <div className={metric.tone || ""} key={metric.label}><small>{metric.label}</small><strong>{typeof metric.value === "number" ? metric.value.toLocaleString("zh-CN") : metric.value}</strong><em>{metric.detail}</em></div>)}
  </section>;
}
