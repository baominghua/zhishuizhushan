import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, KeyRound, MapPinned, RefreshCw, Save, Server, Smartphone } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";

import { api } from "../api/client";
import type { BasemapSettingsPayload, BasemapSettingsResponse } from "../api/types";
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
        client.invalidateQueries({ queryKey: ["map-config"] }),
      ]);
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage("");
    const data = new FormData(event.currentTarget);
    const payload: BasemapSettingsPayload = {
      serverKey: String(data.get("serverKey") || "").trim(),
      webKey: String(data.get("webKey") || "").trim(),
      androidKey: String(data.get("androidKey") || "").trim(),
      iosKey: String(data.get("iosKey") || "").trim(),
      webDirectEnabled: data.get("webDirectEnabled") === "on",
      proxyBaseUrl: String(data.get("proxyBaseUrl") || "").trim(),
      referer: String(data.get("referer") || "").trim(),
    };
    update.mutate(payload);
  };

  return <div className="standard-page basemap-settings-page">
    <section className="page-heading ledger-heading">
      <div><span className="eyebrow">系统管理 / 地图服务</span><h1>底图服务配置</h1><p>按使用端隔离天地图凭证，服务端、Web、Android 与 iOS Key 互不混用。</p></div>
      <div className="heading-actions">
        <button className="button secondary" type="button" onClick={() => settings.refetch()}><RefreshCw aria-hidden="true" />刷新状态</button>
        <a className="button secondary" href="https://console.tianditu.gov.cn/" target="_blank" rel="noreferrer"><ExternalLink aria-hidden="true" />天地图控制台</a>
      </div>
    </section>
    <QueryState loading={settings.isLoading} error={settings.error}>{settings.data && <BasemapSettingsForm settings={settings.data} canManage={canManage} isPending={update.isPending} message={message} error={update.error?.message} onSubmit={submit} />}</QueryState>
  </div>;
}

function BasemapSettingsForm({ settings, canManage, isPending, message, error, onSubmit }: { settings: BasemapSettingsResponse; canManage: boolean; isPending: boolean; message: string; error?: string; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const mobileCount = Number(settings.hasAndroidKey) + Number(settings.hasIosKey);
  return <>
    <section className="domain-summary-strip">
      <Summary icon={<MapPinned />} label="服务状态" value={settings.available ? "已连接" : "未连接"} detail="GIS 一张图底图服务" tone={settings.available ? "active" : ""} />
      <Summary icon={<KeyRound />} label="Web 访问" value={settings.hasWebKey ? settings.webKeyMasked : "未配置"} detail={settings.webDirectEnabled ? "浏览器直连 CDN" : "服务端代理模式"} />
      <Summary icon={<Smartphone />} label="移动端 Key" value={`${mobileCount} / 2`} detail="Android / iOS 独立配置" />
    </section>
    <section className="ledger-shell basemap-config-shell">
      <form className="entity-form" onSubmit={onSubmit}>
        <fieldset className="form-section">
          <legend>天地图多端凭证</legend>
          <div className="form-grid">
            <CredentialField name="serverKey" label="服务端 Key" configured={settings.hasServerKey} masked={settings.serverKeyMasked} hint="用于后台代理、缓存预热和服务端任务" />
            <CredentialField name="webKey" label="Web Key" configured={settings.hasWebKey} masked={settings.webKeyMasked} hint="用于浏览器直连；请在天地图控制台限制访问域名" />
            <CredentialField name="androidKey" label="Android APP Key" configured={settings.hasAndroidKey} masked={settings.androidKeyMasked} hint="只供 Android 客户端配置，不下发到网页" />
            <CredentialField name="iosKey" label="iOS APP Key" configured={settings.hasIosKey} masked={settings.iosKeyMasked} hint="只供 iOS 客户端配置，不下发到网页" />
          </div>
        </fieldset>
        <fieldset className="form-section">
          <legend>访问策略</legend>
          <div className="form-grid">
            <label className="field-span"><span>上游代理地址</span><input name="proxyBaseUrl" type="url" defaultValue={settings.proxyBaseUrl} placeholder="可选，例如内部统一地图代理地址" /></label>
            <label className="field-span"><span>固定 Referer</span><input name="referer" type="url" defaultValue={settings.referer} placeholder="仅在天地图服务端应用策略要求时填写" /></label>
            <label className="field-span checkbox-field"><input name="webDirectEnabled" type="checkbox" defaultChecked={settings.webDirectEnabled} /><span><strong>启用 Web 直连加速</strong><small>浏览器直接访问天地图 CDN；Web Key 会出现在瓦片请求中，这是浏览器 Key 的正常工作方式。</small></span></label>
          </div>
        </fieldset>
        <div className="basemap-security-note"><CheckCircle2 aria-hidden="true" /><div><strong>密钥安全边界</strong><p>后台查询只返回掩码，完整值不会返回浏览器。服务端、Android 和 iOS Key 不会下发给网页；只有主动启用 Web 直连时，地图配置才向当前网页提供 Web Key。</p></div></div>
        {message && <p className="form-success">{message}</p>}
        {error && <p className="form-error">{error}</p>}
        <div className="form-actions"><button className="button primary" type="submit" disabled={!canManage || isPending}><Save aria-hidden="true" />{isPending ? "正在保存" : "保存配置"}</button></div>
      </form>
    </section>
  </>;
}

function CredentialField({ name, label, configured, masked, hint }: { name: string; label: string; configured: boolean; masked: string; hint: string }) {
  return <label className="field-span"><span>{label}</span><input name={name} type="password" autoComplete="new-password" placeholder={configured ? `已配置 ${masked}；留空保持不变` : `输入 32 位${label}`} /><small>{hint}</small></label>;
}

function Summary({ icon, label, value, detail, tone = "" }: { icon: ReactNode; label: string; value: string; detail: string; tone?: string }) {
  return <div className={tone}><span className="summary-icon">{icon}</span><small>{label}</small><strong>{value}</strong><em>{detail}</em></div>;
}
