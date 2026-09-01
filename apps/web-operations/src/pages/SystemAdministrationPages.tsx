import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  Building2, Check, ChevronRight, Eye, KeyRound, Network,
  Pencil, Plus, RefreshCw, Search, ShieldCheck, Trash2, UserRoundCog, UsersRound,
} from "lucide-react";
import { type FormEvent, type ReactNode, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  AdminOrganization, AdminOrganizationPayload, AdminRole, AdminRolePayload,
  AdminUser, AdminUserPayload, PermissionCatalogItem, PermissionCatalogResponse,
} from "../api/types";
import { QueryState } from "../components/QueryState";
import { SidePanel } from "../components/SidePanel";
import { hasPermission, useCapabilities } from "../hooks/useCapabilities";

type PanelState<T> = { mode: "create" | "edit" | "view"; record: T | null } | null;

const ORG_TYPE_LABELS: Record<string, string> = {
  platform: "平台运营单位", government: "政府单位", department: "职能部门", town: "乡镇",
  village: "村级组织", enterprise: "企业", cooperative: "合作社", project: "项目组织", team: "作业班组",
};

const STATUS_LABELS: Record<string, string> = { active: "启用", disabled: "停用", locked: "锁定" };

function dateText(value: string) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "-";
}

function field(data: FormData, name: string) {
  return String(data.get(name) || "").trim();
}

function lines(value: FormDataEntryValue | null) {
  return String(value || "").split(/[\n,，]/).map((item) => item.trim()).filter(Boolean);
}

function scopeText(scopes: Record<string, unknown> | undefined, key: string) {
  const value = scopes?.[key];
  return Array.isArray(value) ? value.map(String).join("\n") : "";
}

function Status({ value }: { value: string }) {
  return <span className={`admin-status ${value}`}>{STATUS_LABELS[value] || value}</span>;
}

function PageHeading({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <section className="page-heading ledger-heading"><div><span className="eyebrow">系统管理 / 身份与访问</span><h1>{title}</h1><p>{description}</p></div>{action && <div className="heading-actions">{action}</div>}</section>;
}

function SystemTabs() {
  return <nav className="system-tabs" aria-label="系统管理导航">
    <Link to="/system/overview" activeProps={{ className: "active" }}>管理总览</Link>
    <Link to="/system/organizations" activeProps={{ className: "active" }}>组织架构</Link>
    <Link to="/system/users" activeProps={{ className: "active" }}>用户账号</Link>
    <Link to="/system/roles" activeProps={{ className: "active" }}>角色管理</Link>
    <Link to="/system/dictionaries" activeProps={{ className: "active" }}>字典管理</Link>
    <Link to="/system/permissions" activeProps={{ className: "active" }}>权限目录</Link>
  </nav>;
}

export function SystemOverviewPage() {
  const organizations = useQuery({ queryKey: ["admin-organizations"], queryFn: () => api.adminOrganizations({ limit: 1000 }) });
  const users = useQuery({ queryKey: ["admin-users"], queryFn: () => api.adminUsers({ limit: 1000 }) });
  const roles = useQuery({ queryKey: ["admin-roles"], queryFn: () => api.adminRoles({ limit: 1000 }) });
  const catalog = useQuery({ queryKey: ["permission-catalog"], queryFn: api.permissionCatalog });
  const loading = organizations.isLoading || users.isLoading || roles.isLoading || catalog.isLoading;
  const error = organizations.error || users.error || roles.error || catalog.error;
  const usersWithoutOrg = users.data?.items.filter((user) => !String(user.properties.organizationId || "")).length ?? 0;
  const usersWithoutRole = users.data?.items.filter((user) => !user.roles.length).length ?? 0;
  return <div className="standard-page system-admin-page"><PageHeading title="系统管理" description="统一维护组织、账号、角色、权限和数据范围，变更直接作用于同一套后台身份体系。" /><SystemTabs />
    <QueryState loading={loading} error={error}><section className="domain-summary-strip system-summary">
      <Summary icon={<Network />} label="组织节点" value={String(organizations.data?.total ?? 0)} detail={`${organizations.data?.items.filter((item) => item.status === "active").length ?? 0} 个启用`} />
      <Summary icon={<UsersRound />} label="用户账号" value={String(users.data?.total ?? 0)} detail={`${usersWithoutOrg} 人待分配组织`} />
      <Summary icon={<ShieldCheck />} label="角色模板" value={String(roles.data?.total ?? 0)} detail={`${usersWithoutRole} 人尚未分配角色`} />
      <Summary icon={<KeyRound />} label="权限项" value={String(catalog.data?.permissions.length ?? 0)} detail={`${(catalog.data?.menuModules.length ?? 0) + (catalog.data?.v2MenuModules?.length ?? 0)} 个功能模块`} />
    </section>
    <section className="ledger-shell system-health-grid"><article><header><div><h2>身份治理检查</h2><p>需要优先处理的账号配置问题</p></div></header><ul className="governance-checks"><CheckItem ok={!usersWithoutOrg} text={usersWithoutOrg ? `${usersWithoutOrg} 个账号未绑定主组织` : "全部账号已绑定主组织"} href="/system/users" /><CheckItem ok={!usersWithoutRole} text={usersWithoutRole ? `${usersWithoutRole} 个账号未分配角色` : "全部账号已分配角色"} href="/system/users" /><CheckItem ok={Boolean(roles.data?.items.length)} text="角色权限目录可用" href="/system/permissions" /></ul></article><article><header><div><h2>管理入口</h2><p>按职责进入对应台账</p></div></header><div className="management-shortcuts"><Shortcut icon={<Building2 />} title="组织架构" detail="部门、乡镇、村、企业和项目组织" to="/system/organizations" /><Shortcut icon={<UserRoundCog />} title="用户账号" detail="组织归属、角色和数据范围" to="/system/users" /><Shortcut icon={<ShieldCheck />} title="角色权限" detail="角色模板和功能权限矩阵" to="/system/roles" /></div></article></section></QueryState>
  </div>;
}

export function OrganizationsPage() {
  const client = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState("");
  const [panel, setPanel] = useState<PanelState<AdminOrganization>>(null);
  const query = useQuery({ queryKey: ["admin-organizations", q], queryFn: () => api.adminOrganizations({ q, limit: 1000 }) });
  const create = useMutation({ mutationFn: api.createAdminOrganization, onSuccess: () => done() });
  const update = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Partial<AdminOrganizationPayload> }) => api.updateAdminOrganization(id, payload), onSuccess: () => done() });
  const remove = useMutation({ mutationFn: api.deleteAdminOrganization, onSuccess: () => done() });
  const done = async () => { setPanel(null); await client.invalidateQueries({ queryKey: ["admin-organizations"] }); };
  const tree = useMemo(() => organizationTree(query.data?.items ?? []), [query.data]);
  const canCreate = hasPermission(capabilities.data?.permissions, capabilities.data?.principal.roles, "system.organizations.create");
  const canUpdate = hasPermission(capabilities.data?.permissions, capabilities.data?.principal.roles, "system.organizations.update");
  const canDelete = hasPermission(capabilities.data?.permissions, capabilities.data?.principal.roles, "system.organizations.delete");
  return <div className="standard-page system-admin-page"><PageHeading title="组织架构" description="维护平台运营单位、部门、乡镇、村级组织和经营主体的统一层级关系。" action={<><button className="button secondary" onClick={() => query.refetch()}><RefreshCw />刷新</button><button className="button primary" disabled={!canCreate} onClick={() => setPanel({ mode: "create", record: null })}><Plus />新增组织</button></>} /><SystemTabs />
    <section className="ledger-shell"><div className="ledger-toolbar"><label className="search-field"><Search /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="搜索组织编码、名称或负责人" /></label></div><QueryState loading={query.isLoading} error={query.error}><div className="table-scroll"><table className="ledger-table"><thead><tr><th>组织</th><th>类型</th><th>负责人</th><th>成员 / 下级</th><th>状态</th><th>更新时间</th><th className="action-column">操作</th></tr></thead><tbody>{tree.map(({ record, depth }) => <tr key={record.id}><td><div className="organization-cell" style={{ paddingLeft: `${depth * 24}px` }}>{depth > 0 && <ChevronRight />}<strong>{record.name}</strong><small>{record.organizationCode}{record.shortName ? ` · ${record.shortName}` : ""}</small></div></td><td>{ORG_TYPE_LABELS[record.organizationType] || record.organizationType}</td><td><strong>{record.leader || "待指定"}</strong><small>{record.phone || "未留联系方式"}</small></td><td>{record.userCount} 人 / {record.childCount} 个</td><td><Status value={record.status} /></td><td>{dateText(record.updatedAt)}</td><td className="action-column"><div className="row-actions"><button title="查看" onClick={() => setPanel({ mode: "view", record })}><Eye /></button><button title="编辑" disabled={!canUpdate} onClick={() => setPanel({ mode: "edit", record })}><Pencil /></button><button className="danger" title="删除" disabled={!canDelete || Boolean(record.userCount || record.childCount)} onClick={() => { if (confirm(`确认删除组织“${record.name}”？`)) remove.mutate(record.id); }}><Trash2 /></button></div></td></tr>)}{!tree.length && <tr><td colSpan={7}><div className="table-empty"><Network /><strong>尚未建立组织架构</strong><p>新增根组织后，再逐级维护部门、乡镇和项目团队。</p></div></td></tr>}</tbody></table></div></QueryState></section>
    <SidePanel open={Boolean(panel)} title={panel?.mode === "create" ? "新增组织" : panel?.mode === "edit" ? "编辑组织" : "组织详情"} eyebrow="组织架构" onClose={() => setPanel(null)}><OrganizationForm record={panel?.record ?? null} organizations={query.data?.items ?? []} readOnly={panel?.mode === "view"} pending={create.isPending || update.isPending} error={create.error || update.error} onCancel={() => setPanel(null)} onSubmit={(payload) => panel?.record ? update.mutate({ id: panel.record.id, payload }) : create.mutate(payload as AdminOrganizationPayload)} /></SidePanel>
  </div>;
}

export function UsersPage() {
  const client = useQueryClient();
  const capabilities = useCapabilities();
  const [q, setQ] = useState(""); const [panel, setPanel] = useState<PanelState<AdminUser>>(null);
  const users = useQuery({ queryKey: ["admin-users", q], queryFn: () => api.adminUsers({ q, limit: 500 }) });
  const roles = useQuery({ queryKey: ["admin-roles"], queryFn: () => api.adminRoles({ limit: 500 }) });
  const organizations = useQuery({ queryKey: ["admin-organizations"], queryFn: () => api.adminOrganizations({ limit: 1000 }) });
  const done = async () => { setPanel(null); await client.invalidateQueries({ queryKey: ["admin-users"] }); };
  const create = useMutation({ mutationFn: api.createAdminUser, onSuccess: done });
  const update = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Partial<Omit<AdminUserPayload, "username">> }) => api.updateAdminUser(id, payload), onSuccess: done });
  const remove = useMutation({ mutationFn: api.deleteAdminUser, onSuccess: done });
  const resetPassword = useMutation({ mutationFn: ({ id, password }: { id: string; password: string }) => api.setAdminUserPassword(id, password) });
  const revoke = useMutation({ mutationFn: api.revokeAdminUserSessions });
  const orgById = new Map((organizations.data?.items ?? []).map((item) => [item.id, item.name]));
  const allowed = (permission: string) => hasPermission(capabilities.data?.permissions, capabilities.data?.principal.roles, permission);
  return <div className="standard-page system-admin-page"><PageHeading title="用户账号" description="账号、所属组织、岗位角色和数据范围在一个表单内维护。" action={<button className="button primary" disabled={!allowed("system.users.create")} onClick={() => setPanel({ mode: "create", record: null })}><Plus />新增用户</button>} /><SystemTabs />
    <section className="ledger-shell"><div className="ledger-toolbar"><label className="search-field"><Search /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="搜索用户名、姓名、角色或组织" /></label></div><QueryState loading={users.isLoading || roles.isLoading || organizations.isLoading} error={users.error || roles.error || organizations.error}><div className="table-scroll"><table className="ledger-table"><thead><tr><th>账号</th><th>所属组织</th><th>角色</th><th>数据范围</th><th>状态</th><th>更新时间</th><th className="action-column">操作</th></tr></thead><tbody>{users.data?.items.map((user) => { const organizationId = String(user.properties.organizationId || ""); return <tr key={user.id}><td><strong>{user.displayName}</strong><small>{user.username}</small></td><td><strong>{orgById.get(organizationId) || "未分配"}</strong><small>{String(user.properties.jobTitle || "岗位待补充")}</small></td><td><div className="inline-tags">{user.roles.map((role) => <span key={role}>{role}</span>)}{!user.roles.length && <em>未分配</em>}</div></td><td>{Object.values(user.dataScopes).flat().length} 项</td><td><Status value={user.status} /></td><td>{dateText(user.updatedAt)}</td><td className="action-column"><div className="row-actions"><button title="查看" onClick={() => setPanel({ mode: "view", record: user })}><Eye /></button><button title="编辑" disabled={!allowed("system.users.update")} onClick={() => setPanel({ mode: "edit", record: user })}><Pencil /></button><button title="重置密码" disabled={!allowed("system.users.setPassword")} onClick={() => { const password = prompt(`为 ${user.displayName} 设置临时密码`); if (password) resetPassword.mutate({ id: user.id, password }); }}><KeyRound /></button><button title="撤销会话" disabled={!allowed("system.users.revokeSessions")} onClick={() => { if (confirm(`确认强制 ${user.displayName} 重新登录？`)) revoke.mutate(user.id); }}><RefreshCw /></button><button className="danger" title="删除" disabled={!allowed("system.users.delete")} onClick={() => { if (confirm(`确认删除账号“${user.username}”？`)) remove.mutate(user.id); }}><Trash2 /></button></div></td></tr>})}</tbody></table></div></QueryState>{resetPassword.isSuccess && <p className="form-success">临时密码已更新，用户下次登录必须修改密码。</p>}{resetPassword.error && <p className="form-error">{resetPassword.error.message}</p>}</section>
    <SidePanel open={Boolean(panel)} title={panel?.mode === "create" ? "新增用户" : panel?.mode === "edit" ? "编辑用户" : "用户详情"} eyebrow="用户账号" onClose={() => setPanel(null)} wide><UserForm record={panel?.record ?? null} roles={roles.data?.items ?? []} organizations={organizations.data?.items ?? []} readOnly={panel?.mode === "view"} pending={create.isPending || update.isPending} error={create.error || update.error} onCancel={() => setPanel(null)} onSubmit={(payload) => panel?.record ? update.mutate({ id: panel.record.id, payload }) : create.mutate(payload as AdminUserPayload)} /></SidePanel>
  </div>;
}

export function RolesPage() {
  const client = useQueryClient(); const [q, setQ] = useState(""); const [panel, setPanel] = useState<PanelState<AdminRole>>(null);
  const capabilities = useCapabilities();
  const roles = useQuery({ queryKey: ["admin-roles", q], queryFn: () => api.adminRoles({ q, limit: 500 }) });
  const catalog = useQuery({ queryKey: ["permission-catalog"], queryFn: api.permissionCatalog });
  const done = async () => { setPanel(null); await client.invalidateQueries({ queryKey: ["admin-roles"] }); };
  const create = useMutation({ mutationFn: api.createAdminRole, onSuccess: done });
  const update = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Partial<Omit<AdminRolePayload, "roleCode">> }) => api.updateAdminRole(id, payload), onSuccess: done });
  const remove = useMutation({ mutationFn: api.deleteAdminRole, onSuccess: done });
  const allowed = (permission: string) => hasPermission(capabilities.data?.permissions, capabilities.data?.principal.roles, permission);
  return <div className="standard-page system-admin-page"><PageHeading title="角色管理" description="使用功能模块和权限矩阵配置岗位角色，数据范围与功能权限分开治理。" action={<button className="button primary" disabled={!allowed("system.roles.create")} onClick={() => setPanel({ mode: "create", record: null })}><Plus />新增角色</button>} /><SystemTabs />
    <section className="ledger-shell"><div className="ledger-toolbar"><label className="search-field"><Search /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="搜索角色代码、名称或权限" /></label></div><QueryState loading={roles.isLoading || catalog.isLoading} error={roles.error || catalog.error}><div className="table-scroll"><table className="ledger-table"><thead><tr><th>角色</th><th>菜单模块</th><th>权限项</th><th>数据范围</th><th>状态</th><th>更新时间</th><th className="action-column">操作</th></tr></thead><tbody>{roles.data?.items.map((role) => <tr key={role.id}><td><strong>{role.name}</strong><small>{role.roleCode}</small></td><td>{role.menuModules.length}</td><td>{role.permissions.length}</td><td>{Object.values(role.dataScopes).flat().length} 项</td><td><Status value={role.status} /></td><td>{dateText(role.updatedAt)}</td><td className="action-column"><div className="row-actions"><button title="查看" onClick={() => setPanel({ mode: "view", record: role })}><Eye /></button><button title="编辑" disabled={!allowed("system.roles.update")} onClick={() => setPanel({ mode: "edit", record: role })}><Pencil /></button><button className="danger" title="删除" disabled={!allowed("system.roles.delete") || role.roleCode === "admin"} onClick={() => { if (confirm(`确认删除角色“${role.name}”？`)) remove.mutate(role.id); }}><Trash2 /></button></div></td></tr>)}</tbody></table></div></QueryState></section>
    <SidePanel open={Boolean(panel)} title={panel?.mode === "create" ? "新增角色" : panel?.mode === "edit" ? "编辑角色" : "角色详情"} eyebrow="角色与权限" onClose={() => setPanel(null)} wide><RoleForm record={panel?.record ?? null} catalog={catalog.data} readOnly={panel?.mode === "view"} pending={create.isPending || update.isPending} error={create.error || update.error} onCancel={() => setPanel(null)} onSubmit={(payload) => panel?.record ? update.mutate({ id: panel.record.id, payload }) : create.mutate(payload as AdminRolePayload)} /></SidePanel>
  </div>;
}

export function PermissionsPage() {
  const [q, setQ] = useState(""); const catalog = useQuery({ queryKey: ["permission-catalog"], queryFn: api.permissionCatalog });
  const permissions = (catalog.data?.permissions ?? []).filter((item) => !q || `${item.code} ${item.label}`.toLowerCase().includes(q.toLowerCase()));
  const modules = new Map([...(catalog.data?.menuModules ?? []), ...(catalog.data?.v2MenuModules ?? [])].map((module) => [module.key, module]));
  const grouped = permissions.reduce<Record<string, PermissionCatalogItem[]>>((result, item) => { const moduleKey = String((item as PermissionCatalogItem & { module?: string }).module || "other"); (result[moduleKey] ||= []).push(item); return result; }, {});
  return <div className="standard-page system-admin-page"><PageHeading title="权限目录" description="只读展示功能权限、接口覆盖和依赖关系；权限分配请在角色管理中完成。" /><SystemTabs /><section className="ledger-shell"><div className="ledger-toolbar"><label className="search-field"><Search /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="搜索权限名称或代码" /></label><div className="toolbar-note">{permissions.length} 项权限</div></div><QueryState loading={catalog.isLoading} error={catalog.error}><div className="permission-catalog-list">{Object.entries(grouped).map(([moduleKey, items]) => <section key={moduleKey}><header><div><h2>{modules.get(moduleKey)?.label || moduleKey}</h2><p>{modules.get(moduleKey)?.group || "平台能力"}</p></div><span>{items.length} 项</span></header><div>{items.map((item) => <article key={item.code}><ShieldCheck /><div><strong>{item.label}</strong><code>{item.code}</code></div><small>{item.apiScopes?.length || 0} 个接口</small></article>)}</div></section>)}</div></QueryState></section></div>;
}

function OrganizationForm({ record, organizations, readOnly, pending, error, onCancel, onSubmit }: { record: AdminOrganization | null; organizations: AdminOrganization[]; readOnly: boolean; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: AdminOrganizationPayload | Partial<AdminOrganizationPayload>) => void }) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSubmit({
      organizationCode: field(data, "organizationCode"), name: field(data, "name"),
      shortName: field(data, "shortName") || null, parentId: field(data, "parentId") || null,
      organizationType: field(data, "organizationType") as AdminOrganization["organizationType"],
      status: field(data, "status"), sortOrder: Number(field(data, "sortOrder") || 0),
      leader: field(data, "leader") || null, phone: field(data, "phone") || null,
      address: field(data, "address") || null,
      administrativeDivisionCode: field(data, "administrativeDivisionCode") || null,
      dataScopes: {
        areas: lines(data.get("areas")), towns: lines(data.get("towns")),
        villages: lines(data.get("villages")), blockCodes: lines(data.get("blockCodes")),
        projects: lines(data.get("projects")),
      },
      properties: record?.properties || {},
    });
  };
  return <form className="entity-form" onSubmit={submit}><fieldset disabled={readOnly}>
    <fieldset className="form-section"><legend>组织身份</legend><div className="form-grid">
      <label><span>组织编码<em>*</em></span><input name="organizationCode" required readOnly={Boolean(record)} defaultValue={record?.organizationCode} /></label>
      <label><span>组织名称<em>*</em></span><input name="name" required defaultValue={record?.name} /></label>
      <label><span>组织简称</span><input name="shortName" defaultValue={record?.shortName || ""} /></label>
      <label><span>组织类型</span><select name="organizationType" defaultValue={record?.organizationType || "department"}>{Object.entries(ORG_TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label><span>上级组织</span><select name="parentId" defaultValue={record?.parentId || ""}><option value="">无（根组织）</option>{organizations.filter((item) => item.id !== record?.id).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      <label><span>状态</span><select name="status" defaultValue={record?.status || "active"}><option value="active">启用</option><option value="disabled">停用</option></select></label>
      <label><span>排序</span><input name="sortOrder" type="number" defaultValue={record?.sortOrder || 0} /></label>
      <label><span>行政区划代码</span><input name="administrativeDivisionCode" defaultValue={record?.administrativeDivisionCode || ""} /></label>
    </div></fieldset>
    <fieldset className="form-section"><legend>联系信息</legend><div className="form-grid">
      <label><span>负责人</span><input name="leader" defaultValue={record?.leader || ""} /></label>
      <label><span>联系电话</span><input name="phone" type="tel" defaultValue={record?.phone || ""} /></label>
      <label className="field-span"><span>办公地址</span><input name="address" defaultValue={record?.address || ""} /></label>
    </div></fieldset>
    <fieldset className="form-section"><legend>组织数据范围</legend>
      <p className="form-section-note">成员自动继承本组织及上级组织的数据范围；留空表示不在本级额外授予。</p>
      <div className="form-grid">
        <label><span>行政区代码</span><textarea name="areas" defaultValue={scopeText(record?.dataScopes, "areas")} /></label>
        <label><span>乡镇</span><textarea name="towns" defaultValue={scopeText(record?.dataScopes, "towns")} /></label>
        <label><span>村</span><textarea name="villages" defaultValue={scopeText(record?.dataScopes, "villages")} /></label>
        <label><span>林班编号</span><textarea name="blockCodes" defaultValue={scopeText(record?.dataScopes, "blockCodes")} /></label>
        <label><span>项目代码</span><textarea name="projects" defaultValue={scopeText(record?.dataScopes, "projects")} /></label>
      </div>
    </fieldset>
  </fieldset>{error && <p className="form-error">{error.message}</p>}{!readOnly && <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" disabled={pending}>{pending ? "保存中" : "保存组织"}</button></div>}</form>;
}

function UserForm({ record, roles, organizations, readOnly, pending, error, onCancel, onSubmit }: { record: AdminUser | null; roles: AdminRole[]; organizations: AdminOrganization[]; readOnly: boolean; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: AdminUserPayload | Partial<Omit<AdminUserPayload, "username">>) => void }) {
  const selectedRoles = new Set(record?.roles ?? []); const properties = record?.properties ?? {};
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); const organizationId = field(data, "organizationId"); const organizationIds = data.getAll("organizationIds").map(String).filter((id) => id !== organizationId); onSubmit({ username: field(data, "username"), displayName: field(data, "displayName"), status: field(data, "status"), roles: data.getAll("roles").map(String), dataScopes: { areas: lines(data.get("areas")), towns: lines(data.get("towns")), villages: lines(data.get("villages")), blockCodes: lines(data.get("blockCodes")), projects: lines(data.get("projects")) }, properties: { ...properties, organizationId, organizationIds, jobTitle: field(data, "jobTitle"), phone: field(data, "phone"), email: field(data, "email") } }); };
  return <form className="entity-form" onSubmit={submit}><fieldset disabled={readOnly}><fieldset className="form-section"><legend>账号与组织</legend><div className="form-grid"><label><span>用户名<em>*</em></span><input name="username" required readOnly={Boolean(record)} defaultValue={record?.username} /></label><label><span>姓名<em>*</em></span><input name="displayName" required defaultValue={record?.displayName} /></label><label><span>主组织<em>*</em></span><select name="organizationId" required defaultValue={String(properties.organizationId || "")}><option value="">请选择</option>{organizations.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label><span>岗位</span><input name="jobTitle" defaultValue={String(properties.jobTitle || "")} /></label><label><span>手机</span><input name="phone" type="tel" defaultValue={String(properties.phone || "")} /></label><label><span>邮箱</span><input name="email" type="email" defaultValue={String(properties.email || "")} /></label><label><span>状态</span><select name="status" defaultValue={record?.status || "active"}><option value="active">启用</option><option value="disabled">停用</option><option value="locked">锁定</option></select></label></div></fieldset><fieldset className="form-section"><legend>角色分配</legend><div className="selection-grid">{roles.map((role) => <label className="selection-item" key={role.id}><input name="roles" type="checkbox" value={role.roleCode} defaultChecked={selectedRoles.has(role.roleCode)} /><span><strong>{role.name}</strong><small>{role.roleCode} · {role.permissions.length} 项权限</small></span></label>)}</div></fieldset><fieldset className="form-section"><legend>兼岗组织</legend><div className="selection-grid compact">{organizations.map((organization) => <label className="selection-item" key={organization.id}><input name="organizationIds" type="checkbox" value={organization.id} defaultChecked={Array.isArray(properties.organizationIds) && properties.organizationIds.includes(organization.id)} /><span><strong>{organization.name}</strong><small>{ORG_TYPE_LABELS[organization.organizationType]}</small></span></label>)}</div></fieldset><fieldset className="form-section"><legend>个人补充数据范围</legend><p className="form-section-note">通常由角色和组织继承；仅在确需扩大到指定林班或项目时补充。</p><div className="form-grid"><label><span>行政区代码</span><textarea name="areas" defaultValue={record?.dataScopes.areas?.join("\n")} /></label><label><span>乡镇</span><textarea name="towns" defaultValue={record?.dataScopes.towns?.join("\n")} /></label><label><span>村</span><textarea name="villages" defaultValue={record?.dataScopes.villages?.join("\n")} /></label><label><span>林班编号</span><textarea name="blockCodes" defaultValue={record?.dataScopes.blockCodes?.join("\n")} /></label></div></fieldset></fieldset>{error && <p className="form-error">{error.message}</p>}{!readOnly && <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" disabled={pending}>{pending ? "保存中" : "保存用户"}</button></div>}</form>;
}

function RoleForm({ record, catalog, readOnly, pending, error, onCancel, onSubmit }: { record: AdminRole | null; catalog?: PermissionCatalogResponse; readOnly: boolean; pending: boolean; error: Error | null; onCancel: () => void; onSubmit: (payload: AdminRolePayload | Partial<Omit<AdminRolePayload, "roleCode">>) => void }) {
  const selectedPermissions = new Set(record?.permissions ?? []); const selectedModules = new Set(record?.menuModules ?? []); const menuModules = [...(catalog?.menuModules ?? []), ...(catalog?.v2MenuModules ?? [])];
  const permissionsByModule = (catalog?.permissions ?? []).reduce<Record<string, PermissionCatalogItem[]>>((result, item) => { const key = String((item as PermissionCatalogItem & { module?: string }).module || "other"); (result[key] ||= []).push(item); return result; }, {});
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); const selectedMenuModules = data.getAll("menuModules").map(String); const entryPermissions = menuModules.filter((module) => selectedMenuModules.includes(module.key)).map((module) => module.permission).filter(Boolean); const permissions = Array.from(new Set([...data.getAll("permissions").map(String), ...entryPermissions])); onSubmit({ roleCode: field(data, "roleCode"), name: field(data, "name"), status: field(data, "status"), permissions, menuModules: selectedMenuModules, dataScopes: { areas: lines(data.get("areas")), towns: lines(data.get("towns")), villages: lines(data.get("villages")), blockCodes: lines(data.get("blockCodes")), projects: lines(data.get("projects")) }, properties: record?.properties || {} }); };
  return <form className="entity-form" onSubmit={submit}><fieldset disabled={readOnly}><fieldset className="form-section"><legend>角色身份</legend><div className="form-grid"><label><span>角色代码<em>*</em></span><input name="roleCode" required readOnly={Boolean(record)} defaultValue={record?.roleCode} /></label><label><span>角色名称<em>*</em></span><input name="name" required defaultValue={record?.name} /></label><label><span>状态</span><select name="status" defaultValue={record?.status || "active"}><option value="active">启用</option><option value="disabled">停用</option></select></label></div></fieldset><fieldset className="form-section"><legend>功能模块与权限</legend><div className="permission-matrix">{menuModules.map((module) => <section key={module.key}><label className="module-permission"><input name="menuModules" value={module.key} type="checkbox" defaultChecked={selectedModules.has(module.key)} /><span><strong>{module.label}</strong><small>{module.group}</small></span></label><div>{(permissionsByModule[module.key] || []).map((permission) => <label key={permission.code}><input name="permissions" value={permission.code} type="checkbox" defaultChecked={selectedPermissions.has(permission.code)} /><span>{permission.label}<code>{permission.code}</code></span></label>)}</div></section>)}</div></fieldset><fieldset className="form-section"><legend>角色数据范围</legend><div className="form-grid"><label><span>行政区代码</span><textarea name="areas" defaultValue={record?.dataScopes.areas?.join("\n")} /></label><label><span>乡镇</span><textarea name="towns" defaultValue={record?.dataScopes.towns?.join("\n")} /></label><label><span>村</span><textarea name="villages" defaultValue={record?.dataScopes.villages?.join("\n")} /></label><label><span>林班编号</span><textarea name="blockCodes" defaultValue={record?.dataScopes.blockCodes?.join("\n")} /></label><label><span>项目代码</span><textarea name="projects" defaultValue={record?.dataScopes.projects?.join("\n")} /></label></div></fieldset></fieldset>{error && <p className="form-error">{error.message}</p>}{!readOnly && <div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button primary" disabled={pending}>{pending ? "保存中" : "保存角色"}</button></div>}</form>;
}

function organizationTree(records: AdminOrganization[]) {
  const children = new Map<string, AdminOrganization[]>();
  records.forEach((record) => { const key = record.parentId || "root"; children.set(key, [...(children.get(key) || []), record]); });
  children.forEach((items) => items.sort((a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name, "zh-CN")));
  const result: Array<{ record: AdminOrganization; depth: number }> = []; const visited = new Set<string>();
  const visit = (record: AdminOrganization, depth: number) => { if (visited.has(record.id)) return; visited.add(record.id); result.push({ record, depth }); (children.get(record.id) || []).forEach((child) => visit(child, depth + 1)); };
  (children.get("root") || []).forEach((record) => visit(record, 0)); records.forEach((record) => visit(record, 0)); return result;
}

function Summary({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string; detail: string }) { return <div><span className="summary-icon">{icon}</span><small>{label}</small><strong>{value}</strong><em>{detail}</em></div>; }
function CheckItem({ ok, text, href }: { ok: boolean; text: string; href: string }) { return <li className={ok ? "ok" : "attention"}><span>{ok ? <Check /> : <KeyRound />}</span><strong>{text}</strong><Link to={href}>处理<ChevronRight /></Link></li>; }
function Shortcut({ icon, title, detail, to }: { icon: ReactNode; title: string; detail: string; to: string }) { return <Link to={to}>{icon}<span><strong>{title}</strong><small>{detail}</small></span><ChevronRight /></Link>; }
