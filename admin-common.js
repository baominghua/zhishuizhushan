const AdminCommon = (() => {
  const DEFAULT_API_BASE = /^https?:$/.test(window.location.protocol)
    ? window.location.origin
    : "http://127.0.0.1:8010";
  const CSRF_TOKEN_KEY = "smartBambooCsrfToken";
  const AUTH_PROFILE_KEY = "smartBambooAuthProfile";
  let currentAllowedPermissions = null;
  let currentProfile = null;
  let sessionReadyPromise = null;
  let resolveSessionGate = null;
  let sessionGateBlocked = false;
  let sessionGeneration = 0;
  const LEGACY_TOKEN_KEYS = ["smartBambooAdminToken", "smartBambooAdminTokenPersistent"];

  const LABELS = {
    baseType: {
      self_operated: "自营",
      franchise: "加盟",
      cooperative: "合作经营",
    },
    operationType: {
      timber: "竹材用林",
      dual_regular: "常规笋竹两用林",
      dual_high_yield: "高产笋竹两用林",
      understory: "林下经济",
    },
    riskLevel: {
      low: "低",
      medium: "中",
      high: "高",
      critical: "严重",
    },
    archiveStatus: {
      complete: "完整",
      partial: "待补充",
      missing: "缺档",
      review: "复核中",
    },
  };

  const BUSINESS_MANAGE_PERMISSION_PREFIXES = [
    "business.farmers",
    "business.cooperatives",
    "business.enterprises",
    "business.plantProtection",
    "business.materials",
    "business.policies",
    "business.stewardshipAgreements",
    "business.franchiseBases",
    "business.maintenanceTasks",
    "business.workLogs",
    "business.droneTasks",
    "business.equipment",
    "business.pestWarnings",
    "business.materialServices",
    "business.yieldForecasts",
    "business.harvestPlans",
    "business.incomeEstimates",
    "business.performanceDashboards",
    "business.carbonEstimates",
    "business.tradeMatches",
    "business.logisticsTraces",
    "business.productQrcodes",
    "business.supplyChainFinance",
    "business.priceIndexes",
    "business.mobileServiceChannels",
  ];

  function businessManagePermissionImplications() {
    return Object.fromEntries(
      BUSINESS_MANAGE_PERMISSION_PREFIXES.map((prefix) => [
        `${prefix}.manage`,
        [
          `${prefix}.view`,
          `${prefix}.create`,
          `${prefix}.update`,
          `${prefix}.delete`,
          `${prefix}.restore`,
          `${prefix}.export`,
        ],
      ]),
    );
  }

  const MANAGE_PERMISSION_IMPLICATIONS = {
    "forest.blocks.manage": [
      "forest.blocks.view",
      "forest.blocks.create",
      "forest.blocks.update",
      "forest.blocks.delete",
      "forest.blocks.restore",
      "forest.blocks.rollback",
    ],
    "forest.rights.manage": [
      "forest.rights.view",
      "forest.rights.create",
      "forest.rights.update",
      "forest.rights.delete",
      "forest.rights.restore",
      "forest.rights.rollback",
    ],
    "imports.forestBlocks.manage": [
      "imports.forestBlocks.view",
      "imports.forestBlocks.create",
      "imports.forestBlocks.review",
      "imports.forestBlocks.quality",
      "imports.forestBlocks.acceptance",
      "imports.forestBlocks.rollback",
      "imports.forestBlocks.delete",
      "imports.forestBlocks.restore",
      "imports.forestBlocks.export",
      "imports.sceneLayers.link",
    ],
    "imagery.scenes.manage": [
      "imagery.scenes.view",
      "imagery.scenes.create",
      "imagery.scenes.update",
      "imagery.scenes.delete",
      "imagery.scenes.restore",
      "imagery.scenes.archive",
      "imagery.scenes.quality",
      "imagery.scenes.delivery",
      "imagery.scenes.export",
      "imagery.tasks.retry",
      "imagery.tasks.cancel",
      "imagery.tasks.archive",
      "imagery.layers.publish",
    ],
    "map.layers.manage": [
      "map.layers.view",
      "map.layers.create",
      "map.layers.update",
      "map.layers.delete",
      "map.layers.restore",
      "map.layers.export",
      "map.layers.publish",
    ],
    ...businessManagePermissionImplications(),
    "system.roles.manage": [
      "system.roles.view",
      "system.roles.create",
      "system.roles.update",
      "system.roles.delete",
      "system.roles.restore",
      "system.roles.export",
    ],
    "system.roles.create": ["system.roles.view"],
    "system.roles.update": ["system.roles.view"],
    "system.roles.delete": ["system.roles.view"],
    "system.roles.restore": ["system.roles.view"],
    "system.roles.export": ["system.roles.view"],
    "system.users.manage": [
      "system.users.view",
      "system.users.create",
      "system.users.update",
      "system.users.delete",
      "system.users.restore",
      "system.users.export",
      "system.roles.view",
    ],
    "system.users.create": ["system.users.view", "system.roles.view"],
    "system.users.update": ["system.users.view", "system.roles.view"],
    "system.users.delete": ["system.users.view"],
    "system.users.restore": ["system.users.view"],
    "system.users.export": ["system.users.view"],
  };
  let managePermissionImplications = { ...MANAGE_PERMISSION_IMPLICATIONS };

  const $ = (selector, root = document) => root.querySelector(selector);

  function normalizeApiBase(value) {
    const raw = String(value || "").trim();
    return raw ? raw.replace(/\/+$/, "") : DEFAULT_API_BASE;
  }

  function apiBase() {
    return normalizeApiBase($("#apiBase")?.value || DEFAULT_API_BASE);
  }

  function splitValues(value) {
    return String(value || "")
      .split(/[,\s;]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function normalizePermissionImplications(value) {
    if (!value || typeof value !== "object") return {};
    return Object.fromEntries(
      Object.entries(value)
        .map(([permission, impliedPermissions]) => [
          String(permission || "").trim(),
          Array.isArray(impliedPermissions) ? impliedPermissions.map((item) => String(item || "").trim()).filter(Boolean) : [],
        ])
        .filter(([permission, impliedPermissions]) => permission && impliedPermissions.length),
    );
  }

  function syncPermissionImplications(value) {
    const normalized = normalizePermissionImplications(value);
    if (Object.keys(normalized).length) {
      managePermissionImplications = normalized;
    }
  }

  function buildHeaders(extraHeaders, method = "GET") {
    const headers = new Headers(extraHeaders || {});
    if (currentProfile?.authType !== "session") {
      const roles = splitValues($("#authRoles")?.value || "").join(",");
      const areas = splitValues($("#authAreas")?.value || "").join(",");
      const user = String($("#authUser")?.value || "").trim();
      if (roles) headers.set("X-RS-Roles", roles);
      if (areas) headers.set("X-RS-Areas", areas);
      if (user) headers.set("X-RS-User", user);
    }
    if (["POST", "PUT", "PATCH", "DELETE"].includes(String(method).toUpperCase()) && csrfToken() && currentProfile?.authType !== "service-token") {
      headers.set("X-CSRF-Token", csrfToken());
    }
    return headers;
  }

  function csrfToken() {
    return sessionStorage.getItem(CSRF_TOKEN_KEY) || "";
  }

  function clearSessionState() {
    sessionStorage.removeItem(CSRF_TOKEN_KEY);
    sessionStorage.removeItem(AUTH_PROFILE_KEY);
    LEGACY_TOKEN_KEYS.forEach((key) => {
      sessionStorage.removeItem(key);
      localStorage.removeItem(key);
    });
    currentProfile = null;
  }

  function clearLegacyTokenState() {
    LEGACY_TOKEN_KEYS.forEach((key) => {
      sessionStorage.removeItem(key);
      localStorage.removeItem(key);
    });
  }

  function blockBusinessRequests() {
    if (sessionGateBlocked) return;
    sessionGateBlocked = true;
    sessionReadyPromise = new Promise((resolve) => {
      resolveSessionGate = resolve;
    });
  }

  function releaseBusinessRequests() {
    if (!sessionGateBlocked) return;
    sessionGateBlocked = false;
    const resolve = resolveSessionGate;
    resolveSessionGate = null;
    resolve?.();
  }

  function redirectToLogin() {
    if (window.location.pathname.endsWith("/admin-login.html")) return;
    const current = new URL(window.location.href, window.location.origin);
    if (current.origin !== window.location.origin) return;
    const fileName = current.pathname.split("/").pop() || "admin.html";
    const returnTo = /^admin(?:-[a-z0-9-]+)?\.html$/i.test(fileName) ? `${fileName}${current.search}${current.hash}` : "admin.html";
    window.location.replace(`admin-login.html?returnTo=${encodeURIComponent(returnTo)}`);
  }

  function isPasswordChangeRequired(status, payload) {
    return status === 403 && payload && typeof payload === "object" && payload.detail === "Password change required";
  }

  function isAuthBypassPath(path) {
    return ["/api/auth/session", "/api/auth/me", "/api/auth/change-password", "/api/auth/logout"].includes(path);
  }

  async function parseResponse(response, requestGeneration = null) {
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      if (response.status === 401) redirectToLogin();
      if (isPasswordChangeRequired(response.status, payload)) handleForcedPasswordChange(requestGeneration);
      const detail =
        payload && typeof payload === "object"
          ? payload.detail || JSON.stringify(payload)
          : String(payload || response.statusText);
      throw new Error(`${response.status} ${detail}`);
    }
    return payload;
  }

  async function api(path, options = {}) {
    const requestOptions = { credentials: "include", ...options };
    const skipSessionReady = requestOptions.skipSessionReady;
    delete requestOptions.skipSessionReady;
    const authBypass = skipSessionReady || isAuthBypassPath(path);
    if (!authBypass && sessionReadyPromise) await sessionReadyPromise;
    const method = String(requestOptions.method || "GET").toUpperCase();
    const headers = buildHeaders(requestOptions.headers, method);
    if (requestOptions.body && !(requestOptions.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    requestOptions.headers = headers;
    const requestGeneration = authBypass ? null : sessionGeneration;
    return parseResponse(await fetch(`${apiBase()}${path}`, requestOptions), requestGeneration);
  }

  function authApi(path, options = {}) {
    return api(path, { ...options, skipSessionReady: true });
  }

  async function fetchWithSession(path, options = {}) {
    const requestOptions = { credentials: "include", ...options };
    const skipSessionReady = requestOptions.skipSessionReady;
    delete requestOptions.skipSessionReady;
    const authBypass = skipSessionReady || isAuthBypassPath(path);
    if (!authBypass && sessionReadyPromise) await sessionReadyPromise;
    const method = String(requestOptions.method || "GET").toUpperCase();
    requestOptions.headers = buildHeaders(requestOptions.headers, method);
    const requestGeneration = authBypass ? null : sessionGeneration;
    const response = await fetch(`${apiBase()}${path}`, requestOptions);
    if (response.status === 401) redirectToLogin();
    if (response.status === 403 && response.clone) {
      const payload = await response.clone().json().catch(() => null);
      if (isPasswordChangeRequired(response.status, payload)) handleForcedPasswordChange(requestGeneration);
    }
    return response;
  }

  function setStatus(kind, message) {
    const badge = $("#statusBadge");
    const text = $("#statusText");
    const labels = { idle: "未连接", online: "已连接", busy: "处理中", warning: "需处理", offline: "不可用" };
    if (badge) {
      badge.className = `status-badge ${kind}`;
      badge.textContent = labels[kind] || labels.idle;
    }
    if (text) text.textContent = message;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function labelFor(group, value) {
    if (value === null || value === undefined || value === "") return "未填";
    return LABELS[group]?.[value] || String(value);
  }

  function stringifyPretty(value, fallback = {}) {
    try {
      return JSON.stringify(value ?? fallback, null, 2);
    } catch (error) {
      return JSON.stringify(fallback, null, 2);
    }
  }

  function parseJson(label, value, fallback = {}) {
    const text = String(value || "").trim();
    if (!text) return fallback;
    try {
      return JSON.parse(text);
    } catch (error) {
      throw new Error(`${label} 不是合法 JSON`);
    }
  }

  function formatArea(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "未填";
    return `${numeric.toFixed(numeric % 1 === 0 ? 0 : 1)} 亩`;
  }

  function formatDateTime(value) {
    if (!value) return "未填";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("zh-CN", { hour12: false });
  }

  function query(params) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== "" && value !== null && value !== undefined) search.set(key, value);
    });
    return search.toString();
  }

  function setActiveNav() {
    const current = document.body.dataset.adminModule || "overview";
    document.querySelectorAll(".sidebar-nav a[data-module]").forEach((link) => {
      link.classList.toggle("active", link.dataset.module === current);
    });
    const permission = document.body.dataset.permission || "";
    const permissionNode = $("#permissionCode");
    if (permissionNode) permissionNode.textContent = permission;
  }

  function ensureEffectivePermissionSummary() {
    const statusPanel = $(".sidebar-status");
    if (!statusPanel) return null;
    let summary = $("#effectivePermissionSummary", statusPanel);
    if (!summary) {
      summary = document.createElement("dl");
      summary.id = "effectivePermissionSummary";
      summary.className = "status-meta permission-scope-summary";
      statusPanel.appendChild(summary);
    }
    return summary;
  }

  function renderEffectivePermissionStatus(payload) {
    const summary = ensureEffectivePermissionSummary();
    if (!summary) return;
    const roles = Array.isArray(payload.roles) && payload.roles.length ? payload.roles.join(", ") : "未配置";
    const menuCount = Array.isArray(payload.visibleMenuModules) ? payload.visibleMenuModules.length : 0;
    const permissions = Array.isArray(payload.permissions) ? payload.permissions : [];
    const scopes = payload.dataScopes || {};
    const areas = Array.isArray(scopes.areas) && scopes.areas.length ? scopes.areas.join(", ") : "全域";
    const projects = Array.isArray(scopes.projects) && scopes.projects.length ? scopes.projects.join(", ") : "全部";
    summary.innerHTML = `
      <div><dt>有效角色</dt><dd>${escapeHtml(roles)}</dd></div>
      <div><dt>可见菜单</dt><dd>${menuCount} 个</dd></div>
      <div><dt>功能权限</dt><dd>${permissions.length} 项</dd></div>
      <div><dt>区县范围</dt><dd>${escapeHtml(areas)}</dd></div>
      <div><dt>项目范围</dt><dd>${escapeHtml(projects)}</dd></div>
    `;
  }

  function visibleMenuKeys(payload) {
    const visibleModules = Array.isArray(payload.visibleMenuModules) ? payload.visibleMenuModules : [];
    const visibleKeys = visibleModules.map((module) => module?.key).filter(Boolean);
    if (visibleKeys.length) return visibleKeys;
    return Array.isArray(payload.menuModules) ? payload.menuModules : [];
  }

  function permissionSatisfies(permissions, requiredPermission) {
    const required = String(requiredPermission || "").trim();
    if (!required) return true;
    const permissionSet = new Set(Array.isArray(permissions) ? permissions : []);
    if (permissionSet.has(required)) return true;
    return Object.entries(managePermissionImplications).some(
      ([managePermission, impliedPermissions]) => permissionSet.has(managePermission) && impliedPermissions.includes(required),
    );
  }

  function permissionRequirementState(element, permissions, hasConfiguredPermissions) {
    const requiredPermission = element.dataset.permission || "";
    const allPermissions = splitValues(element.dataset.permissionAll || "");
    const anyPermissions = splitValues(element.dataset.permissionAny || "");
    if (!hasConfiguredPermissions) return { allowed: true, missing: [] };
    const requiredPermissions = [requiredPermission, ...allPermissions].filter(Boolean);
    const missingRequired = requiredPermissions.filter((permission) => !permissionSatisfies(permissions, permission));
    const anySatisfied = !anyPermissions.length || anyPermissions.some((permission) => permissionSatisfies(permissions, permission));
    const missing = [...missingRequired];
    if (!anySatisfied) {
      missing.push(`任选其一：${anyPermissions.join(" / ")}`);
    }
    return {
      allowed: missing.length === 0,
      missing,
    };
  }

  const OVERVIEW_MODULE = {
    key: "overview",
    label: "后台首页",
    href: "admin.html",
    group: "系统",
  };
  const STATIC_MENU_GROUPS = {
    系统: ["overview", "deployment", "roles", "users"],
    空间与权属: ["blocks", "rights", "linkages"],
    经营主体: ["farmers", "cooperatives", "enterprises"],
    生产服务: ["plantProtection", "materials"],
    政策项目: ["policies"],
    运营管护: [
      "stewardshipAgreements",
      "franchiseBases",
      "maintenanceTasks",
      "workLogs",
      "droneTasks",
      "equipment",
      "pestWarnings",
      "materialServices",
    ],
    经营决策: ["yieldForecasts", "harvestPlans", "incomeEstimates", "performanceDashboards", "carbonEstimates"],
    产业平台: ["tradeMatches", "logisticsTraces", "productQrcodes", "supplyChainFinance", "priceIndexes", "mobileServiceChannels"],
    地图发布: ["mapLayers"],
    数据治理: ["imports", "imagery"],
  };

  function staticModuleGroup(moduleKey) {
    return (
      Object.entries(STATIC_MENU_GROUPS).find(([, moduleKeys]) => moduleKeys.includes(String(moduleKey || "")))?.[0] ||
      "其他"
    );
  }

  function groupStaticNavigation() {
    const nav = $(".sidebar-nav");
    if (!nav || nav.dataset.grouped === "true") return;
    const links = Array.from(nav.querySelectorAll(":scope > a[data-module]"));
    if (!links.length) return;
    const groups = new Map();
    links.forEach((link) => {
      const module = {
        key: link.dataset.module || "",
        href: link.getAttribute("href") || "#",
        label: link.textContent?.trim() || link.dataset.module || "",
        group: staticModuleGroup(link.dataset.module),
      };
      if (!groups.has(module.group)) groups.set(module.group, []);
      groups.get(module.group).push(module);
    });
    nav.innerHTML = Array.from(groups.entries())
      .map(([group, groupModules]) => {
        const groupLinks = groupModules
          .map(
            (module) =>
              `<a href="${escapeHtml(module.href)}" data-module="${escapeHtml(module.key)}">${escapeHtml(module.label)}</a>`,
          )
          .join("");
        return `<section class="sidebar-nav-group"><p>${escapeHtml(group)}</p>${groupLinks}</section>`;
      })
      .join("");
    nav.dataset.grouped = "true";
  }

  function visibleBackendModules(payload, hasConfiguredMenu) {
    const visibleModules = Array.isArray(payload.visibleMenuModules) ? payload.visibleMenuModules : [];
    if (!visibleModules.length && !hasConfiguredMenu) return [];
    const modules = visibleModules
      .filter((module) => module && module.key && module.href && module.label)
      .map((module) => ({
        key: String(module.key),
        label: String(module.label),
        href: String(module.href),
        group: String(module.group || "其他"),
      }));
    return [OVERVIEW_MODULE, ...modules.filter((module) => module.key !== OVERVIEW_MODULE.key)];
  }

  function renderBackendNavigation(payload, hasConfiguredMenu) {
    const nav = $(".sidebar-nav");
    if (!nav) return;
    const modules = visibleBackendModules(payload, hasConfiguredMenu);
    if (!modules.length) {
      setActiveNav();
      return;
    }
    const current = document.body.dataset.adminModule || "overview";
    const groups = new Map();
    modules.forEach((module) => {
      if (!groups.has(module.group)) groups.set(module.group, []);
      groups.get(module.group).push(module);
    });
    nav.innerHTML = Array.from(groups.entries())
      .map(([group, groupModules]) => {
        const links = groupModules
          .map((module) => {
            const active = module.key === current ? " active" : "";
            return `<a href="${escapeHtml(module.href)}" data-module="${escapeHtml(module.key)}" class="${active.trim()}">${escapeHtml(module.label)}</a>`;
          })
          .join("");
        return `<section class="sidebar-nav-group"><p>${escapeHtml(group)}</p>${links}</section>`;
      })
      .join("");
    nav.dataset.grouped = "true";
  }

  function ensurePageAccessGuard() {
    const main = $(".admin-main");
    if (!main) return null;
    let guard = $("#pageAccessGuard", main);
    if (!guard) {
      guard = document.createElement("section");
      guard.id = "pageAccessGuard";
      guard.className = "page-access-guard";
      guard.hidden = true;
      const topbar = $(".topbar", main);
      if (topbar?.nextSibling) {
        main.insertBefore(guard, topbar.nextSibling);
      } else {
        main.prepend(guard);
      }
    }
    return guard;
  }

  function renderPageAccessGuard(payload, allowedModules, allowedPermissions, hasConfiguredMenu) {
    const guard = ensurePageAccessGuard();
    const moduleKey = document.body.dataset.adminModule || "overview";
    const requiredPermission = document.body.dataset.permission || "";
    const hasConfiguredPermissions = Array.isArray(payload.permissions);
    const moduleDenied = hasConfiguredMenu && moduleKey !== "overview" && !allowedModules.includes(moduleKey);
    const permissionDenied = hasConfiguredPermissions && requiredPermission && !permissionSatisfies(allowedPermissions, requiredPermission);
    const denied = Boolean(moduleDenied || permissionDenied);
    document.body.classList.toggle("permission-page-denied", denied);
    if (!guard) return;
    guard.hidden = !denied;
    if (!denied) {
      guard.innerHTML = "";
      return;
    }
    guard.innerHTML = `
      <strong>当前角色无权访问本页面</strong>
      <span>需要菜单模块 ${escapeHtml(moduleKey)} 与入口权限 ${escapeHtml(requiredPermission || "-")}。请切换角色或在角色权限管理中配置。</span>
    `;
  }

  function applyMenuAndPermissions(payload) {
    syncPermissionImplications(payload.permissionImplications);
    const allowedModules = visibleMenuKeys(payload);
    const allowedPermissions = Array.isArray(payload.permissions) ? payload.permissions : [];
    const hasConfiguredMenu = Array.isArray(payload.menuModules) || Array.isArray(payload.visibleMenuModules);
    currentAllowedPermissions = allowedPermissions;
    renderBackendNavigation(payload, hasConfiguredMenu);
    document.querySelectorAll(".sidebar-nav a[data-module]").forEach((link) => {
      link.hidden = hasConfiguredMenu && link.dataset.module !== "overview" && !allowedModules.includes(link.dataset.module);
    });
    setActiveNav();
    applyActionPermissions(allowedPermissions);
    renderPageAccessGuard(payload, allowedModules, allowedPermissions, hasConfiguredMenu);
  }

  function cacheProfile(profile) {
    currentProfile = profile && typeof profile === "object" ? profile : null;
    if (currentProfile) sessionStorage.setItem(AUTH_PROFILE_KEY, JSON.stringify(currentProfile));
  }

  async function recoverCsrfToken() {
    if (csrfToken()) return;
    const session = await authApi("/api/auth/session");
    if (session?.csrfToken) sessionStorage.setItem(CSRF_TOKEN_KEY, session.csrfToken);
  }

  async function refreshSession({ afterPasswordChange = false } = {}) {
    try {
      await recoverCsrfToken();
      const payload = await authApi("/api/auth/me");
      cacheProfile(payload);
      applyMenuAndPermissions(payload);
      renderEffectivePermissionStatus(payload);
      ensureSessionControl();
      if (payload.mustChangePassword) {
        handleForcedPasswordChange();
      } else {
        hideForcedPasswordChange();
        if (afterPasswordChange) sessionGeneration += 1;
        releaseBusinessRequests();
      }
      return payload;
    } catch (error) {
      throw error;
    } finally {
      document.body.classList.remove("admin-session-pending");
    }
  }

  function ensureForcedPasswordChangeDialog() {
    let dialog = $("#forcedPasswordChangeDialog");
    if (dialog) return dialog;
    dialog = document.createElement("section");
    dialog.id = "forcedPasswordChangeDialog";
    dialog.className = "forced-password-change";
    dialog.hidden = true;
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-labelledby", "forcedPasswordChangeTitle");
    dialog.innerHTML = `
      <form id="forcedPasswordChangeForm" class="forced-password-change-panel">
        <p class="eyebrow">账户安全</p>
        <h2 id="forcedPasswordChangeTitle">请先修改密码</h2>
        <label for="currentPassword"><span>旧密码</span><input id="currentPassword" type="password" autocomplete="current-password" required /></label>
        <label for="newPassword"><span>新密码</span><input id="newPassword" type="password" autocomplete="new-password" required /></label>
        <label for="confirmPassword"><span>确认新密码</span><input id="confirmPassword" type="password" autocomplete="new-password" required /></label>
        <p id="forcedPasswordChangeStatus" class="form-status" aria-live="polite"></p>
        <div class="panel-actions"><button id="submitForcedPasswordChange" type="submit">更新密码</button></div>
      </form>
    `;
    document.body.appendChild(dialog);
    $("#forcedPasswordChangeForm").addEventListener("submit", submitForcedPasswordChange);
    return dialog;
  }

  function showForcedPasswordChange() {
    const dialog = ensureForcedPasswordChangeDialog();
    document.body.classList.add("password-change-required");
    dialog.hidden = false;
    dialog.setAttribute("aria-hidden", "false");
    window.setTimeout(() => $("#currentPassword")?.focus(), 0);
  }

  function handleForcedPasswordChange(requestGeneration = null) {
    if (requestGeneration !== null && requestGeneration < sessionGeneration) return false;
    blockBusinessRequests();
    showForcedPasswordChange();
    return true;
  }

  function hideForcedPasswordChange() {
    document.body.classList.remove("password-change-required");
    const dialog = $("#forcedPasswordChangeDialog");
    if (!dialog) return;
    dialog.hidden = true;
    dialog.setAttribute("aria-hidden", "true");
  }

  async function submitForcedPasswordChange(event) {
    event.preventDefault();
    const current = $("#currentPassword");
    const next = $("#newPassword");
    const confirm = $("#confirmPassword");
    const status = $("#forcedPasswordChangeStatus");
    const submit = $("#submitForcedPasswordChange");
    try {
      if (!current.value || !next.value || !confirm.value) throw new Error("请填写旧密码、新密码和确认密码。");
      if (next.value !== confirm.value) throw new Error("两次输入的新密码不一致。");
      if (submit) submit.disabled = true;
      if (status) status.textContent = "正在更新密码...";
      await authApi("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ currentPassword: current.value, newPassword: next.value }),
      });
      await refreshSession({ afterPasswordChange: true });
    } catch (error) {
      if (status) status.textContent = error.message || "密码更新失败。";
    } finally {
      current.value = "";
      next.value = "";
      confirm.value = "";
      if (submit) submit.disabled = false;
    }
  }

  function applyActionPermissions(allowedPermissions) {
    const permissions = allowedPermissions ?? currentAllowedPermissions;
    const hasConfiguredPermissions = Array.isArray(permissions);
    document.querySelectorAll("[data-permission], [data-permission-all], [data-permission-any]").forEach((element) => {
      if (element === document.body) return;
      const requirement = permissionRequirementState(element, permissions || [], hasConfiguredPermissions);
      const allowed = requirement.allowed;
      if ("disabled" in element) {
        element.disabled = true;
        element.disabled = !allowed;
      }
      element.classList.toggle("permission-disabled", !allowed);
      element.setAttribute("aria-disabled", allowed ? "false" : "true");
      if (!allowed) {
        element.title = `缺少权限：${requirement.missing.join("，")}`;
      } else if (element.title?.startsWith("缺少权限：")) {
        element.removeAttribute("title");
      }
    });
  }

  const ACTION_ICONS = {
    view: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>',
    edit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 20 4.6-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z"></path><path d="m13.5 6.5 4 4"></path></svg>',
    delete: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M6 7l1 13h10l1-13"></path><path d="M9 7V4h6v3"></path></svg>',
  };

  function rowActionButtons(permission, labels = {}) {
    const editPermissionValue = typeof permission === "object" ? permission.edit : permission;
    const deletePermissionValue = typeof permission === "object" ? permission.delete : permission;
    const editPermission = editPermissionValue ? ` data-permission="${escapeHtml(editPermissionValue)}"` : "";
    const deletePermission = deletePermissionValue ? ` data-permission="${escapeHtml(deletePermissionValue)}"` : "";
    const viewLabel = labels.view || "查看";
    const editLabel = labels.edit || "编辑";
    const deleteLabel = labels.delete || "删除";
    return `
      <div class="row-actions" aria-label="行操作">
        <button type="button" class="icon-button" data-row-action="view" aria-label="${escapeHtml(viewLabel)}" title="${escapeHtml(viewLabel)}">${ACTION_ICONS.view}</button>
        <button type="button" class="icon-button" data-row-action="edit"${editPermission} aria-label="${escapeHtml(editLabel)}" title="${escapeHtml(editLabel)}">${ACTION_ICONS.edit}</button>
        <button type="button" class="icon-button danger" data-row-action="delete"${deletePermission} aria-label="${escapeHtml(deleteLabel)}" title="${escapeHtml(deleteLabel)}">${ACTION_ICONS.delete}</button>
      </div>
    `;
  }

  function createLedgerPager({ anchor, pageSize = 50, pageSizes = [25, 50, 100], onPageChange } = {}) {
    const anchorElement = typeof anchor === "string" ? $(anchor) : anchor;
    if (!anchorElement) throw new Error("Ledger pager anchor is required");

    const host = document.createElement("nav");
    host.className = "ledger-pagination";
    host.setAttribute("aria-label", "台账分页");
    host.innerHTML = `
      <p class="ledger-pagination-summary" aria-live="polite">暂无记录</p>
      <div class="ledger-pagination-controls">
        <label class="ledger-page-size"><span>每页</span><select aria-label="每页记录数"></select></label>
        <button type="button" class="icon-button ledger-page-button" data-page-action="previous" aria-label="上一页" title="上一页">‹</button>
        <strong class="ledger-page-indicator">1 / 1</strong>
        <button type="button" class="icon-button ledger-page-button" data-page-action="next" aria-label="下一页" title="下一页">›</button>
      </div>
    `;
    anchorElement.insertAdjacentElement("afterend", host);

    const normalizedSizes = [...new Set([...pageSizes, pageSize].map(Number).filter((value) => value > 0))].sort(
      (left, right) => left - right,
    );
    const sizeSelect = $("select", host);
    sizeSelect.innerHTML = normalizedSizes
      .map((value) => `<option value="${value}"${value === Number(pageSize) ? " selected" : ""}>${value} 条</option>`)
      .join("");

    let currentPage = 1;
    let currentPageSize = Number(pageSize);
    let total = 0;
    let busy = false;

    function totalPages() {
      return Math.max(1, Math.ceil(total / currentPageSize));
    }

    function render() {
      const pages = totalPages();
      const start = total ? (currentPage - 1) * currentPageSize + 1 : 0;
      const end = total ? Math.min(total, currentPage * currentPageSize) : 0;
      $(".ledger-pagination-summary", host).textContent = total ? `显示 ${start}-${end} 条，共 ${total} 条` : "暂无记录";
      $(".ledger-page-indicator", host).textContent = `${currentPage} / ${pages}`;
      const previous = $('[data-page-action="previous"]', host);
      const next = $('[data-page-action="next"]', host);
      previous.disabled = busy || currentPage <= 1;
      next.disabled = busy || currentPage >= pages;
      sizeSelect.disabled = busy;
      host.setAttribute("aria-busy", busy ? "true" : "false");
    }

    async function notifyPageChange() {
      if (typeof onPageChange === "function") await onPageChange(pager);
    }

    const pager = {
      get page() {
        return currentPage;
      },
      get limit() {
        return currentPageSize;
      },
      get offset() {
        return (currentPage - 1) * currentPageSize;
      },
      get total() {
        return total;
      },
      reset() {
        currentPage = 1;
        render();
      },
      setBusy(value) {
        busy = Boolean(value);
        render();
      },
      setTotal(value) {
        total = Math.max(0, Number(value) || 0);
        const previousPage = currentPage;
        currentPage = Math.min(currentPage, totalPages());
        render();
        return previousPage !== currentPage;
      },
    };

    host.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-page-action]");
      if (!button || button.disabled || busy) return;
      const nextPage = button.dataset.pageAction === "previous" ? currentPage - 1 : currentPage + 1;
      currentPage = Math.max(1, Math.min(totalPages(), nextPage));
      render();
      await notifyPageChange();
    });
    sizeSelect.addEventListener("change", async () => {
      currentPageSize = Number(sizeSelect.value) || Number(pageSize);
      currentPage = 1;
      render();
      await notifyPageChange();
    });
    render();
    return pager;
  }

  function promotePrimaryLedger() {
    const main = $(".admin-main");
    if (!main) return;
    const config = $(".config-panel", main);
    const ledger = $('[data-admin-primary-ledger="true"]', main);
    if (!config || !ledger || config.nextElementSibling === ledger) return;
    main.insertBefore(ledger, config.nextElementSibling);
  }

  function groupConnectionContextFields() {
    const panel = $(".config-panel");
    if (!panel) return;
    const grid = $(".field-grid", panel);
    if (!grid || $(".connection-context-disclosure", panel)) return;
    const labels = ["apiBase", "authRoles", "authAreas", "authUser"]
      .map((id) => document.getElementById(id)?.closest("label"))
      .filter((label) => label && grid.contains(label));
    if (!labels.length) return;

    const details = document.createElement("details");
    details.className = "connection-context-disclosure";
    const summary = document.createElement("summary");
    summary.textContent = "连接与权限上下文";
    const contextGrid = document.createElement("div");
    contextGrid.className = "connection-context-grid";
    labels.forEach((label) => contextGrid.appendChild(label));
    details.append(summary, contextGrid);
    grid.appendChild(details);
  }

  function initShell() {
    clearLegacyTokenState();
    groupConnectionContextFields();
    $("#apiBase")?.setAttribute("value", localStorage.getItem("smartBambooApiBase") || DEFAULT_API_BASE);
    $("#apiBase")?.addEventListener("change", (event) => {
      localStorage.setItem("smartBambooApiBase", normalizeApiBase(event.target.value));
    });
    $("#authRoles")?.addEventListener("change", refreshSession);
    promotePrimaryLedger();
    groupStaticNavigation();
    setActiveNav();
    document.body.classList.add("admin-session-pending");
    blockBusinessRequests();
    refreshSession().catch(() => {});
    return sessionReadyPromise;
  }

  function ensureSessionControl() {
    if (!currentProfile?.authenticated || currentProfile.authType !== "session") return;
    const statusPanel = $(".sidebar-status");
    if (!statusPanel || $("#adminLogout", statusPanel)) return;
    const control = document.createElement("div");
    control.className = "sidebar-session-control";
    control.innerHTML = `<span>${escapeHtml(currentProfile.user || "已认证用户")}</span><button id="adminLogout" type="button" class="button-ghost">退出登录</button>`;
    statusPanel.appendChild(control);
    $("#adminLogout", control).addEventListener("click", logout);
  }

  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
      clearSessionState();
      redirectToLogin();
      return true;
    } catch (error) {
      if (/^401\b/.test(String(error.message || ""))) {
        clearSessionState();
        redirectToLogin();
        return true;
      }
      setStatus("offline", `退出登录失败：${error.message || "请检查网络后重试。"}`);
      return false;
    }
  }

  return {
    $,
    api,
    apiBase,
    applyActionPermissions,
    buildHeaders,
    clearSessionState,
    createLedgerPager,
    escapeHtml,
    fetchWithSession,
    formatArea,
    formatDateTime,
    initShell,
    labelFor,
    parseJson,
    query,
    logout,
    refreshRoleMenu: refreshSession,
    refreshSession,
    rowActionButtons,
    setStatus,
    splitValues,
    stringifyPretty,
  };
})();
