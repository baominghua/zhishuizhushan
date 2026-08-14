import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, KeyRound, MapPinned, RefreshCw, Save, Server } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";

import { api } from "../api/client";
import type { BasemapSettingsPayload } from "../api/types";
import { QueryState } from "../components/QueryState";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

export function BasemapSettingsPage() {
  const client = useQueryClient();
  const capabilities = useCapabilities();
  const settings = useQuery({ queryKey: ["v2-basemap-settings"], queryFn: api.basemapSettings });
  const [message, setMessage] = useState("");
  const canManage = hasPermission(capabilities.data?.permissions, capabilities.data?.principal.roles, "system.basemap.manage");
  const update = useMutation({
    mutationFn: api.updateBasemapSettings,
    onSuccess: async () => {
      setMessage("配置已保存并立即生效。");
      await Promise.all([
        client.invalidateQueries({ queryKey: ["v2-basemap-settings"] }),
        client.invalidateQueries({ queryKey: ["v2-map-config"] }),
      ]);
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage("");
    const data = new FormData(event.currentTarget);
    const payload: BasemapSettingsPayload = {
      serverKey: String(data.get("serverKey") || "").trim(),
      proxyBaseUrl: String(data.get("proxyBaseUrl") || "").trim(),
      referer: String(data.get("referer") || "").trim(),
    };
    update.mutate(payload);
  };

  return <div className="standard-page basemap-settings-page">
    <section className="page-heading ledger-heading"><div><span className="eyebrow">系统管理 / 地图服务</span><h1>底图服务配置</h1><p>服务端统一代理天地图并缓存瓦片，前端只读取连接状态，不接触服务密钥。</p></div><div className="heading-actions"><button className="button secondary" type="button" onClick={() => settings.refetch()}><RefreshCw aria-hidden="true" />刷新状态</button><a className="button secondary" href="https://console.tianditu.gov.cn/" target="_blank" rel="noreferrer"><ExternalLink aria-hidden="true" />天地图控制台</a></div></section>
    <QueryState loading={settings.isLoading} error={settings.error}>{settings.data && <>
      <section className="domain-summary-strip"><Summary icon={<MapPinned />} label="服务状态" value={settings.data.available ? "已连接" : "未连接"} detail="GIS 一张图底图代理" tone={settings.data.available ? "active" : ""} /><Summary icon={<KeyRound />} label="服务端 Key" value={settings.data.hasServerKey ? settings.data.serverKeyMasked : "未配置"} detail="完整值不会返回浏览器" /><Summary icon={<Server />} label="上游方式" value={settings.data.proxyBaseUrl ? "代理转发" : "服务端直连"} detail={settings.data.source === "stored" ? "后台持久配置" : "环境配置"} /></section>
      <section className="ledger-shell basemap-config-shell"><form className="entity-form" onSubmit={submit}><fieldset className="form-section"><legend>天地图服务</legend><div className="form-grid"><label className="field-span"><span>服务端 Key</span><input name="serverKey" type="password" autoComplete="new-password" placeholder={settings.data.hasServerKey ? `已配置 ${settings.data.serverKeyMasked}；留空保持不变` : "输入 32 位服务端 Key"} /></label><label className="field-span"><span>上游代理地址</span><input name="proxyBaseUrl" type="url" defaultValue={settings.data.proxyBaseUrl} placeholder="可选，例如内部统一地图代理地址" /></label><label className="field-span"><span>固定 Referer</span><input name="referer" type="url" defaultValue={settings.data.referer} placeholder="仅在天地图应用策略要求时填写" /></label></div></fieldset><div className="basemap-security-note"><CheckCircle2 aria-hidden="true" /><div><strong>密钥安全边界</strong><p>保存后密钥只在服务端读取；地图瓦片继续通过本站 `/api/basemaps/tianditu/...` 访问，浏览器请求中不携带 Key。</p></div></div>{message && <p className="form-success">{message}</p>}{update.error && <p className="form-error">{update.error.message}</p>}<div className="form-actions"><button className="button primary" type="submit" disabled={!canManage || update.isPending}><Save aria-hidden="true" />{update.isPending ? "正在保存" : "保存配置"}</button></div></form></section>
    </>}</QueryState>
  </div>;
}

function Summary({ icon, label, value, detail, tone = "" }: { icon: ReactNode; label: string; value: string; detail: string; tone?: string }) {
  return <div className={tone}><span className="summary-icon">{icon}</span><small>{label}</small><strong>{value}</strong><em>{detail}</em></div>;
}
