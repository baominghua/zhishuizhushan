import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import {
  Bell,
  ClipboardCheck,
  Database,
  FolderKey,
  FileClock,
  Images,
  History,
  Paperclip,
  FileUp,
  Home,
  Layers3,
  Map,
  Menu,
  MonitorUp,
  MonitorCog,
  Settings2,
  Smartphone,
  Plane,
  Route,
  Search,
  ShieldAlert,
  ScanSearch,
  BrainCircuit,
  PlaySquare,
  Trees,
  UsersRound,
  Leaf,
  LayoutDashboard,
  Building2,
  UserRoundCog,
  ShieldCheck,
  KeyRound,
  X,
  ChartNoAxesCombined,
  WalletCards,
  Cable,
  GraduationCap,
  ShieldEllipsis,
} from "lucide-react";
import { useMemo, useState } from "react";

import { ApiError, api } from "../api/client";
import type { V2Module } from "../api/types";

const MODULE_ICONS = {
  workspace: Home,
  "operations-todos": ClipboardCheck,
  "operations-notifications": Bell,
  "operations-audit": History,
  map: Map,
  "forest-blocks": Trees,
  "forest-subcompartments": Layers3,
  resourceSurveys: FileClock,
  attachments: Paperclip,
  "forest-rights": FolderKey,
  imports: FileUp,
  patrol: Route,
  harvest: Trees,
  labor: UsersRound,
  equipment: MonitorCog,
  "drone-missions": Plane,
  "imagery-assets": Images,
  "ai-findings": ScanSearch,
  "ai-models": BrainCircuit,
  "ai-inference": PlaySquare,
  "safety-events": ShieldAlert,
  "mobile-operations": Smartphone,
  "carbon-estimates": Leaf,
  "leadership-cockpit": LayoutDashboard,
  "basemap-settings": Settings2,
  "system-overview": Settings2,
  organizations: Building2,
  users: UserRoundCog,
  roles: ShieldCheck,
  permissions: KeyRound,
  "resource-intelligence": ChartNoAxesCombined,
  "cost-management": WalletCards,
  "integration-hub": Cable,
  "workforce-development": GraduationCap,
  "system-governance": ShieldEllipsis,
};

function pageTitle(pathname: string) {
  if (pathname.includes("/system/governance")) return "系统治理";
  if (pathname.includes("/resources/intelligence")) return "资源专题分析";
  if (pathname.includes("/operations/costs")) return "经营成本";
  if (pathname.includes("/integrations")) return "集成与联调";
  if (pathname.includes("/workforce")) return "劳务培训与资质";
  if (pathname.includes("/system/overview")) return "系统管理";
  if (pathname.includes("/system/organizations")) return "组织架构";
  if (pathname.includes("/system/users")) return "用户账号";
  if (pathname.includes("/system/roles")) return "角色管理";
  if (pathname.includes("/system/permissions")) return "权限目录";
  if (pathname.includes("/cockpit/leadership")) return "领导驾驶舱";
  if (pathname.includes("/operations/todos")) return "我的待办";
  if (pathname.includes("/system/notifications")) return "消息中心";
  if (pathname.includes("/system/audit")) return "审计中心";
  if (pathname.includes("/system/basemap-settings")) return "底图服务配置";
  if (pathname.includes("/map")) return "GIS 一张图";
  if (pathname.includes("/resources/forest-blocks")) return "林班台账";
  if (pathname.includes("/resources/forest-subcompartments")) return "小班台账";
  if (pathname.includes("/resources/resource-surveys")) return "资源调查";
  if (pathname.includes("/system/attachments")) return "附件中心";
  if (pathname.includes("/resources/forest-rights")) return "林权档案";
  if (pathname.includes("/resources/imports")) return "数据接入";
  if (pathname.includes("/operations/patrol")) return "巡护办理";
  if (pathname.includes("/operations/harvest")) return "采伐办理";
  if (pathname.includes("/operations/labor")) return "劳务用工";
  if (pathname.includes("/iot/devices")) return "设备台账";
  if (pathname.includes("/drone/missions")) return "无人机任务";
  if (pathname.includes("/drone/imagery-assets")) return "影像成果";
  if (pathname.includes("/ai/reviews")) return "AI 识别复核";
  if (pathname.includes("/ai/models")) return "AI 模型管理";
  if (pathname.includes("/ai/inference-runs")) return "AI 推理任务";
  if (pathname.includes("/safety/events")) return "事件中心";
  if (pathname.includes("/operations/mobile-sync")) return "现场同步";
  if (pathname.includes("/field/mobile")) return "移动现场作业";
  if (pathname.includes("/carbon/estimates")) return "碳汇项目";
  return "我的工作台";
}

function loginUrl() {
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/admin-login.html?returnTo=${encodeURIComponent(returnTo)}`;
}

export function AppShell() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  if (pathname === "/display" || pathname === "/asset-viewer") return <Outlet />;
  return <AdministrativeShell pathname={pathname} />;
}

function AdministrativeShell({ pathname }: { pathname: string }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const capabilities = useQuery({
    queryKey: ["v2-capabilities"],
    queryFn: api.capabilities,
    staleTime: 60_000,
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
  });
  const modules = useMemo(
    () => (capabilities.data?.modules ?? []).filter((module) => module.visible),
    [capabilities.data],
  );
  const notificationsVisible = modules.some((module) => module.key === "operations-notifications");
  const unread = useQuery({
    queryKey: ["operations-center", "notification-count"],
    queryFn: () => api.operationsNotifications({ unreadOnly: true, limit: 1 }),
    enabled: notificationsVisible,
    staleTime: 30_000,
  });

  if (capabilities.error instanceof ApiError && capabilities.error.status === 401) {
    return (
      <main className="auth-required">
        <Database aria-hidden="true" />
        <h1>请先登录智慧竹山后台</h1>
        <p>V2 与现有后台账号、角色和数据范围使用同一套身份系统。</p>
        <a className="button primary" href={loginUrl()}>登录后台</a>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
        <div className="brand">
          <span className="brand-mark">竹</span>
          <span><strong>智慧竹山</strong><small>综合运营平台 V2</small></span>
          <button className="icon-button mobile-only" type="button" onClick={() => setMobileOpen(false)} aria-label="关闭菜单">
            <X aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="主导航">
          {modules.map((module) => <NavigationItem key={module.key} module={module} close={() => setMobileOpen(false)} />)}
          {capabilities.isLoading && <span className="nav-loading">正在加载权限菜单</span>}
        </nav>
        <div className="sidebar-footer">
          <span className="avatar">林</span>
          <span>
            <strong>{capabilities.data?.principal.user || "当前用户"}</strong>
            <small>{capabilities.data?.principal.roles.join("、") || "权限加载中"}</small>
          </span>
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-scrim" type="button" onClick={() => setMobileOpen(false)} aria-label="关闭菜单" />}
      <div className="app-column">
        <header className="topbar">
          <button className="icon-button mobile-only" type="button" onClick={() => setMobileOpen(true)} aria-label="打开菜单">
            <Menu aria-hidden="true" />
          </button>
          <div className="page-identity"><small>南平市 / 智慧竹山</small><strong>{pageTitle(pathname)}</strong></div>
          <div className="topbar-actions">
            <button className="command-search" type="button"><Search aria-hidden="true" />搜索林班、任务、人员</button>
            <Link className="topbar-display-link" to="/display"><MonitorUp aria-hidden="true" /><span>前端大屏</span></Link>
            {notificationsVisible && <Link className="icon-button notification-link" to="/system/notifications" aria-label={`通知，${unread.data?.total ?? 0} 条未读`}><Bell aria-hidden="true" />{Boolean(unread.data?.total) && <span>{Math.min(unread.data?.total ?? 0, 99)}</span>}</Link>}
          </div>
        </header>
        <main className="page-content"><Outlet /></main>
      </div>
    </div>
  );
}

function NavigationItem({ module, close }: { module: V2Module; close: () => void }) {
  const Icon = MODULE_ICONS[module.key];
  return (
    <Link to={module.path} activeProps={{ className: "active" }} onClick={close}>
      <Icon aria-hidden="true" />
      <span>{module.label}</span>
      {module.status === "planned" && <small>待建设</small>}
    </Link>
  );
}
