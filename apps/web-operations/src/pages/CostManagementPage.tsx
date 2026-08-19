import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Calculator, CircleDollarSign, Download, PackageOpen, Plus, RefreshCw, Scale, TriangleAlert } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";

import { api } from "../api/client";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";

type Panel = "rate" | "material" | "budget" | "entry" | null;

export function CostManagementPage() {
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [panel, setPanel] = useState<Panel>(null);
  const report = useQuery({ queryKey: ["cost-report", period], queryFn: () => api.costMonthlyReport(period) });
  const rates = useQuery({ queryKey: ["cost-rates"], queryFn: api.costRates });
  const materials = useQuery({ queryKey: ["cost-materials"], queryFn: api.costMaterials });
  const entries = useQuery({ queryKey: ["cost-entries", period], queryFn: () => api.costEntries({ period }) });
  const periods = useQuery({ queryKey: ["cost-periods"], queryFn: api.costPeriods });
  const refresh = async () => queryClient.invalidateQueries({ queryKey: ["cost"] });
  const periodAction = useMutation({
    mutationFn: (action: "open" | "close" | "reopen" | "recalculate") => api.applyCostPeriodAction(period, action),
    onSuccess: refresh,
  });
  const currentPeriod = periods.data?.items.find((item) => item.period === period);
  const grandTotal = (report.data?.grandTotalCents ?? 0) / 100;
  const labor = report.data?.items.reduce((sum, item) => sum + item.laborCents, 0) ?? 0;
  const material = report.data?.items.reduce((sum, item) => sum + item.materialCents, 0) ?? 0;

  return <div className="standard-page ledger-page roadmap-page">
    <section className="page-heading ledger-heading">
      <div><span className="eyebrow">经营管理 / COST-01</span><h1>经营成本核算</h1><p>人工按有效工时与适用工价归集，物料按移动加权平均价归集；金额统一精确到分。</p></div>
      <div className="heading-actions"><button className="button secondary" type="button" onClick={() => refresh()}><RefreshCw />刷新</button><button className="button primary" type="button" onClick={() => setPanel("entry")}><Plus />成本调整</button></div>
    </section>

    <section className="metric-strip roadmap-metrics" aria-label="成本摘要">
      <Metric icon={CircleDollarSign} label="本期总成本" value={currency(grandTotal)} unit="元" />
      <Metric icon={Calculator} label="人工成本" value={currency(labor / 100)} unit="元" />
      <Metric icon={PackageOpen} label="物料成本" value={currency(material / 100)} unit="元" />
      <Metric icon={TriangleAlert} label="预算预警" value={String(report.data?.alerts.length ?? 0)} unit="条" warning={Boolean(report.data?.alerts.length)} />
    </section>

    <section className="roadmap-command-panel">
      <label><span>核算期间</span><input type="month" value={period} onChange={(event) => setPeriod(event.target.value)} /></label>
      <span className={`status-badge ${currentPeriod?.status === "closed" ? "neutral" : "success"}`}>{currentPeriod?.status === "closed" ? "已关账" : "开放核算"}</span>
      {!currentPeriod && <button className="button secondary" type="button" onClick={() => periodAction.mutate("open")}>打开期间</button>}
      {currentPeriod?.status === "open" && <><button className="button secondary" type="button" onClick={() => periodAction.mutate("recalculate")}>归集人工成本</button><button className="button secondary" type="button" onClick={() => periodAction.mutate("close")}>关账</button></>}
      {currentPeriod?.status === "closed" && <button className="button secondary" type="button" onClick={() => periodAction.mutate("reopen")}>重新打开</button>}
      <button className="button secondary" type="button" onClick={() => api.exportCostMonthlyReport(period)}><Download />导出月报</button>
      <button className="button secondary" type="button" onClick={() => setPanel("budget")}><Scale />设置预算</button>
    </section>

    <section className="roadmap-grid two-columns">
      <article className="roadmap-card span-two">
        <header><div><span>小班核算明细</span><h2>{period} 月报</h2></div><small>更新时间 {formatTime(report.data?.asOf)}</small></header>
        <QueryState loading={report.isLoading} error={report.error}><div className="table-scroll"><table className="ledger-table"><thead><tr><th>小班/林班</th><th>人工成本</th><th>物料成本</th><th>调整</th><th>总成本</th><th>分录数</th></tr></thead><tbody>
          {report.data?.items.map((item) => <tr key={item.blockCode}><td><strong>{item.blockCode}</strong></td><td>{currency(item.laborCents / 100)}</td><td>{currency(item.materialCents / 100)}</td><td>{currency(item.adjustmentCents / 100)}</td><td><strong>{currency(item.totalCents / 100)}</strong></td><td>{item.entryCount}</td></tr>)}
          {!report.data?.items.length && <tr><td colSpan={6}><div className="table-empty"><Calculator /><strong>本期暂无成本</strong><p>打开核算期间后可归集考勤成本、登记物料领用或录入调整分录。</p></div></td></tr>}
        </tbody></table></div></QueryState>
      </article>
      <article className="roadmap-card"><header><div><span>标准库</span><h2>工种工价</h2></div><button className="icon-button" type="button" aria-label="新增工价" onClick={() => setPanel("rate")}><Plus /></button></header><div className="roadmap-list">{rates.data?.items.slice(0, 6).map((rate) => <div key={rate.id}><span><strong>{rate.name}</strong><small>{rate.workType} · {rate.effectiveFrom}</small></span><b>{currency(rate.rateCents / 100)}/{rate.unit}</b></div>)}{!rates.data?.items.length && <Empty text="尚未配置工价标准" />}</div></article>
      <article className="roadmap-card"><header><div><span>物料核算</span><h2>库存与移动均价</h2></div><button className="icon-button" type="button" aria-label="新增物料" onClick={() => setPanel("material")}><Plus /></button></header><div className="roadmap-list">{materials.data?.items.slice(0, 6).map((item) => <div key={item.id}><span><strong>{item.name}</strong><small>{item.materialCode} · 库存 {item.stockQuantity} {item.unit}</small></span><b>{currency(item.movingAverageUnitCostCents / 100)}/{item.unit}</b></div>)}{!materials.data?.items.length && <Empty text="尚未建立物料标准" />}</div></article>
      <article className="roadmap-card span-two"><header><div><span>来源追溯</span><h2>最近成本分录</h2></div><small>{entries.data?.total ?? 0} 条</small></header><div className="table-scroll"><table className="ledger-table compact"><thead><tr><th>发生日期</th><th>小班/林班</th><th>类型</th><th>金额</th><th>来源</th></tr></thead><tbody>{entries.data?.items.slice(0, 10).map((entry) => <tr key={entry.id}><td>{entry.occurredOn}</td><td>{entry.blockCode}</td><td>{costType(entry.costType)}</td><td>{currency(entry.amountCents / 100)}</td><td><strong>{entry.sourceType}</strong><small>{entry.sourceId}</small></td></tr>)}</tbody></table></div></article>
    </section>
    <CostPanel panel={panel} period={period} close={() => setPanel(null)} saved={async () => { setPanel(null); await refresh(); }} />
  </div>;
}

function CostPanel({ panel, period, close, saved }: { panel: Panel; period: string; close: () => void; saved: () => Promise<void> }) {
  const mutation = useMutation({ mutationFn: async (form: HTMLFormElement) => {
    const data = new FormData(form); const value = (name: string) => String(data.get(name) || "").trim(); const number = (name: string) => Number(value(name) || 0);
    if (panel === "rate") return api.createCostRate({ workType: value("workType"), name: value("name"), unit: value("unit"), rate: number("rate"), effectiveFrom: value("effectiveFrom") });
    if (panel === "material") return api.createCostMaterial({ materialCode: value("materialCode"), name: value("name"), unit: value("unit"), openingQuantity: number("openingQuantity"), openingUnitCost: number("openingUnitCost") });
    if (panel === "budget") return api.createCostBudget({ period, blockCode: value("blockCode"), amount: number("amount"), yellowThresholdPct: 15, redThresholdPct: 30 });
    return api.createCostEntry({ costType: "adjustment", blockCode: value("blockCode"), amount: number("amount"), occurredOn: value("occurredOn"), sourceType: "manual-adjustment", sourceId: value("sourceId"), sourceVersion: 1, note: value("note") }, crypto.randomUUID());
  }, onSuccess: saved });
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); mutation.mutate(event.currentTarget); };
  return <SidePanel open={Boolean(panel)} title={{ rate: "新增工种工价", material: "新增物料标准", budget: "设置小班预算", entry: "录入成本调整" }[panel || "rate"]} eyebrow="经营成本" onClose={close}><form className="entity-form" onSubmit={submit}><div className="form-grid">
    {panel === "rate" && <><Field label="工种编码"><input name="workType" required /></Field><Field label="工种名称"><input name="name" required /></Field><Field label="计价单位"><select name="unit"><option value="hour">小时</option><option value="day">天</option><option value="mu">亩</option><option value="ton">吨</option><option value="job">项</option></select></Field><Field label="工价（元）"><input name="rate" type="number" min="0" step="0.01" required /></Field><Field label="生效日期"><input name="effectiveFrom" type="date" required /></Field></>}
    {panel === "material" && <><Field label="物料编码"><input name="materialCode" required /></Field><Field label="物料名称"><input name="name" required /></Field><Field label="单位"><input name="unit" required /></Field><Field label="期初数量"><input name="openingQuantity" type="number" min="0" step="0.0001" defaultValue="0" /></Field><Field label="期初单价（元）"><input name="openingUnitCost" type="number" min="0" step="0.01" defaultValue="0" /></Field></>}
    {panel === "budget" && <><Field label="核算期间"><input value={period} readOnly /></Field><Field label="小班/林班编码"><input name="blockCode" required /></Field><Field label="预算金额（元）"><input name="amount" type="number" min="0" step="0.01" required /></Field><p className="field-span form-hint">默认超过预算 15% 触发黄色预警，超过 30% 触发红色预警。</p></>}
    {panel === "entry" && <><Field label="小班/林班编码"><input name="blockCode" required /></Field><Field label="金额（元）"><input name="amount" type="number" step="0.01" required /></Field><Field label="发生日期"><input name="occurredOn" type="date" required /></Field><Field label="来源单号"><input name="sourceId" required /></Field><Field label="说明"><textarea name="note" rows={4} /></Field></>}
  </div>{mutation.error && <p className="form-error">{mutation.error.message}</p>}<div className="form-actions"><button className="button secondary" type="button" onClick={close}>取消</button><button className="button primary" type="submit" disabled={mutation.isPending}>{mutation.isPending ? "保存中" : "保存"}</button></div></form></SidePanel>;
}

function Field({ label, children }: { label: string; children: ReactNode }) { return <label><span>{label}</span>{children}</label>; }
function Metric({ icon: Icon, label, value, unit, warning = false }: { icon: typeof Calculator; label: string; value: string; unit: string; warning?: boolean }) { return <div className={`metric ${warning ? "warning" : ""}`}><Icon /><span><small>{label}</small><strong>{value}</strong><em>{unit}</em></span></div>; }
function Empty({ text }: { text: string }) { return <p className="roadmap-empty">{text}</p>; }
function currency(value: number) { return Number(value || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function formatTime(value?: string) { return value ? new Date(value).toLocaleString("zh-CN") : "—"; }
function costType(value: string) { return ({ labor: "人工", material: "物料", adjustment: "调整" } as Record<string, string>)[value] || value; }
