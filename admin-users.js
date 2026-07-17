(() => {
  const {
    $,
    api,
    applyActionPermissions,
    createLedgerPager,
    escapeHtml,
    formatDateTime,
    initShell,
    parseJson,
    query,
    refreshRoleMenu,
    rowActionButtons,
    setStatus,
    splitValues,
    stringifyPretty,
  } = AdminCommon;

  const PAGE_PERMISSION = "system.users.view";
  const USER_CREATE_PERMISSION = "system.users.create";
  const USER_UPDATE_PERMISSION = "system.users.update";
  const USER_DELETE_PERMISSION = "system.users.delete";
  const USER_RESTORE_PERMISSION = "system.users.restore";
  const USER_EVENT_EXPORT_PERMISSION = "system.users.export";
  const state = {
    users: [],
    userEvents: [],
    roles: [],
    operationQueue: null,
    userEffectivePermissions: null,
    userDraftEffectivePermissions: null,
    activeId: "",
  };
  let pager;
  let userFilterTimer;
  const initialUserParams = new URLSearchParams(window.location.search);
  const initialUserRole = initialUserParams.get("role") || "";
  const initialUsername = initialUserParams.get("username") || "";
  let initialUserId = initialUserParams.get("userId") || "";
  let userDraftPreviewTimer = 0;
  const VIEW_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>';
  const RESTORE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.4-6.4"></path><path d="M18 3v5h-5"></path><path d="M21 12a9 9 0 0 1-15.4 6.4"></path><path d="M6 21v-5h5"></path></svg>';

  function activeUser() {
    return state.users.find((user) => String(user.id) === String(state.activeId)) || null;
  }

  function isDeletedUser(user) {
    return Boolean(user?.deletedAt);
  }

  function userQuery() {
    return query({
      q: $("#userKeyword").value.trim(),
      status: $("#userStatusFilter").value.trim(),
      role: $("#userRoleFilter").value.trim(),
      includeDeleted: $("#includeDeletedUsers")?.checked ? "true" : "",
      limit: pager.limit,
      offset: pager.offset,
    });
  }

  function applyInitialUserQuery() {
    if (initialUserRole) $("#userRoleFilter").value = initialUserRole;
    if (initialUsername) $("#userKeyword").value = initialUsername;
  }

  function consumeInitialUserSelection() {
    if (!initialUserId) return;
    const linkedUser = state.users.find((user) => String(user.id) === String(initialUserId));
    if (!linkedUser) return;
    state.activeId = linkedUser.id;
    initialUserId = "";
  }

  function renderRoleOptions() {
    const list = $("#roleOptions");
    if (!list) return;
    list.innerHTML = state.roles
      .map((role) => `<option value="${escapeHtml(role.roleCode || "")}" label="${escapeHtml(role.name || role.roleCode || "")}"></option>`)
      .join("");
    renderUserRoleChecklist();
  }

  function selectedRoleCodesFromField() {
    return new Set(splitValues($("#assignedRoles")?.value || ""));
  }

  function syncUserRoleSelectionsFromField() {
    const selected = selectedRoleCodesFromField();
    document.querySelectorAll('[data-user-role-option]').forEach((input) => {
      input.checked = selected.has(input.value);
    });
    scheduleUserDraftEffectivePermissions();
  }

  function syncAssignedRolesFromChecklist() {
    const knownRoleCodes = new Set(
      Array.from(document.querySelectorAll('[data-user-role-option]'))
        .map((input) => input.value)
        .filter(Boolean),
    );
    const unknownRoleCodes = splitValues($("#assignedRoles")?.value || "").filter((roleCode) => !knownRoleCodes.has(roleCode));
    const checkedRoleCodes = Array.from(document.querySelectorAll('[data-user-role-option]:checked'))
      .map((input) => input.value)
      .filter(Boolean);
    if ($("#assignedRoles")) $("#assignedRoles").value = [...unknownRoleCodes, ...checkedRoleCodes].join(", ");
    scheduleUserDraftEffectivePermissions();
  }

  function renderUserRoleChecklist() {
    const target = $("#userRoleChecklist");
    if (!target) return;
    if (!state.roles.length) {
      target.innerHTML = '<p class="trace-empty">暂无可选角色，请先在角色权限管理中创建角色。</p>';
      return;
    }
    target.innerHTML = state.roles
      .map((role) => {
        const roleCode = role.roleCode || "";
        const menuCount = Array.isArray(role.menuModules) ? role.menuModules.length : 0;
        const permissionCount = Array.isArray(role.permissions) ? role.permissions.length : 0;
        const status = role.status || "active";
        return `
          <label class="check-item compact">
            <input type="checkbox" data-user-role-option value="${escapeHtml(roleCode)}" />
            <span>${escapeHtml(role.name || roleCode || "-")}</span>
            <small>${escapeHtml(roleCode || "-")} · ${escapeHtml(status)} · 菜单 ${escapeHtml(menuCount)} 个 · 权限 ${escapeHtml(permissionCount)} 项</small>
          </label>
        `;
      })
      .join("");
    syncUserRoleSelectionsFromField();
  }

  async function loadRoleOptions() {
    try {
      const payload = await api("/api/admin/roles?limit=1000");
      state.roles = Array.isArray(payload.items) ? payload.items : [];
      renderRoleOptions();
    } catch (error) {
      state.roles = [];
      renderRoleOptions();
    }
  }

  function userOperationQueueItem(item = {}, lane = {}) {
    const requiredPermission = item.requiredPermission || lane.requiredPermission || PAGE_PERMISSION;
    const meta = [
      `风险 ${item.riskLevel || "-"}`,
      `角色 ${item.roleCount ?? 0}`,
      `未知 ${item.unknownRoleCount ?? 0}`,
      `失效 ${item.invalidRoleCount ?? 0}`,
      `范围 ${item.dataScopeValueCount ?? 0}`,
    ];
    return `
      <div class="operation-queue-row" data-user-operation-row="${escapeHtml(item.username || "")}">
        <p><strong>${escapeHtml(item.username || "-")}</strong> ${escapeHtml(item.displayName || "")}</p>
        <small>${escapeHtml(item.summary || "等待补充账号授权诊断")}</small>
        <div class="operation-queue-meta">
          ${meta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}
          <span>权限 ${escapeHtml(requiredPermission)}</span>
        </div>
        <button
          type="button"
          class="button-ghost compact-button"
          data-user-operation-action="open"
          data-username="${escapeHtml(item.username || "")}"
          data-user-lane="${escapeHtml(lane.key || "")}"
          data-permission="${escapeHtml(requiredPermission)}"
        >打开账号</button>
      </div>
    `;
  }

  function renderUserOperationQueue() {
    const target = $("#userOperationQueueRows");
    if (!target) return;
    const lanes = Array.isArray(state.operationQueue?.items) ? state.operationQueue.items : [];
    if (!lanes.length) {
      target.innerHTML = `
        <article class="operation-queue-item">
          <div class="operation-queue-head">
            <div><span>暂无队列</span><strong>0</strong><small>当前没有可展示的账号授权闭环状态</small></div>
          </div>
        </article>
      `;
      return;
    }
    target.innerHTML = lanes
      .map((lane) => {
        const items = Array.isArray(lane.items) ? lane.items : [];
        const rows = items.length
          ? items.map((item) => userOperationQueueItem(item, lane)).join("")
          : '<div class="operation-queue-row"><p>暂无待处理账号</p><small>该队列当前为空</small></div>';
        return `
          <article class="operation-queue-item tone-${escapeHtml(lane.tone || "ready")}">
            <div class="operation-queue-head">
              <div>
                <span>${escapeHtml(lane.label || lane.key || "账号队列")}</span>
                <strong>${escapeHtml(lane.count ?? items.length)}</strong>
                <small>${escapeHtml(lane.description || "")}</small>
              </div>
            </div>
            <div class="operation-queue-list">${rows}</div>
          </article>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  async function loadUserOperationQueue() {
    const target = $("#userOperationQueueRows");
    if (target) {
      target.innerHTML = `
        <article class="operation-queue-item">
          <div class="operation-queue-head">
            <div><span>正在加载</span><strong>...</strong><small>正在读取账号授权操作队列</small></div>
          </div>
        </article>
      `;
    }
    try {
      const payload = await api("/api/admin/users/operation-queue?limit=4");
      state.operationQueue = payload;
      renderUserOperationQueue();
    } catch (error) {
      if (target) {
        target.innerHTML = `
          <article class="operation-queue-item tone-danger">
            <div class="operation-queue-head">
              <div><span>加载失败</span><strong>!</strong><small>${escapeHtml(error.message)}</small></div>
            </div>
          </article>
        `;
      }
    }
  }

  async function openUserOperationQueueItem(laneKey, username) {
    const keyword = $("#userKeyword");
    if (keyword) keyword.value = username || "";
    await loadUsers();
    const user = state.users.find((item) => String(item.username || "") === String(username || ""));
    if (!user) {
      setStatus("offline", `未找到队列账号：${username || laneKey || "-"}`);
      return;
    }
    state.activeId = user.id;
    renderRows();
    renderDetail(user);
    $("#userRows")?.closest(".table-wrap")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleUserOperationQueueAction(event) {
    const button = event.target.closest("[data-user-operation-action]");
    if (!button) return false;
    event.preventDefault();
    event.stopPropagation();
    if (button.disabled) return true;
    openUserOperationQueueItem(button.dataset.userLane || "", button.dataset.username || "");
    return true;
  }

  function userActionButtons(user) {
    if (isDeletedUser(user)) {
      return `
        <div class="row-actions" aria-label="账号操作">
          <button type="button" class="icon-button" data-row-action="view" aria-label="查看账号" title="查看账号">${VIEW_ICON}</button>
          <button type="button" class="icon-button" data-user-action="restore" data-permission="${USER_RESTORE_PERMISSION}" aria-label="恢复账号" title="恢复账号">${RESTORE_ICON}</button>
        </div>
      `;
    }
    return rowActionButtons({ edit: USER_UPDATE_PERMISSION, delete: USER_DELETE_PERMISSION });
  }

  function renderRows() {
    const body = $("#userRows");
    if (!state.users.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无用户账号</td></tr>';
      return;
    }
    body.innerHTML = state.users
      .map((user) => {
        const active = String(user.id) === String(state.activeId) ? "active" : "";
        const scopes = user.dataScopes || {};
        const scopeText = [
          Array.isArray(scopes.areas) && scopes.areas.length ? `区县 ${scopes.areas.join(", ")}` : "",
          Array.isArray(scopes.projects) && scopes.projects.length ? `项目 ${scopes.projects.join(", ")}` : "",
        ]
          .filter(Boolean)
          .join(" / ");
        return `
          <tr data-id="${escapeHtml(user.id)}" class="${active}">
            <td><div class="cell-stack"><strong>${escapeHtml(user.username || "-")}</strong><small>${escapeHtml(user.displayName || "-")}</small></div></td>
            <td>${escapeHtml((user.roles || []).join(", ") || "-")}</td>
            <td>${escapeHtml(scopeText || "-")}</td>
            <td><span class="status-pill">${escapeHtml(user.status || "active")}</span></td>
            <td>${escapeHtml(formatDateTime(user.updatedAt))}</td>
            <td>${userActionButtons(user)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  function detailItem(label, value) {
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "未填")}</dd></div>`;
  }

  function renderUserAuditEvents(user) {
    const target = $("#userAuditEventList");
    if (!target) return;
    const auditEvents = Array.isArray(user?.properties?.auditEvents) ? user.properties.auditEvents : [];
    if (!auditEvents.length) {
      target.innerHTML = '<p class="trace-empty">暂无账号变更审计</p>';
      return;
    }
    target.innerHTML = auditEvents
      .slice()
      .reverse()
      .map((event) => {
        const changedFields = Array.isArray(event.changedFields) ? event.changedFields.join(", ") : "-";
        return `
          <article class="trace-item">
            <strong>${escapeHtml(event.action || "-")} · ${escapeHtml(changedFields || "-")}</strong>
            <span>${escapeHtml(formatDateTime(event.at))} · ${escapeHtml(event.actor || "-")} · ${escapeHtml(event.username || user.username || "-")}</span>
          </article>
        `;
      })
      .join("");
  }

  function previewGroup(title, items, className, label, meta) {
    if (!items.length) return "";
    return `
      <section class="preview-group ${className}">
        <strong>${escapeHtml(title)}</strong>
        ${items
          .map((item) => {
            const itemLabel = label ? label(item) : item.label || item.key || item.code || item;
            const suffix = meta ? `<small>${escapeHtml(meta(item))}</small>` : "";
            return `<span>${escapeHtml(itemLabel)}${suffix}</span>`;
          })
          .join("")}
      </section>
    `;
  }

  function userPermissionModuleKey(module) {
    return typeof module === "string" ? module : module?.key || module?.moduleKey || "";
  }

  function userPermissionModuleLabel(module) {
    if (typeof module === "string") return module;
    return module?.label || module?.name || module?.key || module?.moduleKey || "-";
  }

  function userPermissionModuleHref(module) {
    return typeof module === "string" ? "" : module?.href || "";
  }

  function userPermissionModuleEntryPermission(module) {
    if (!module || typeof module === "string") return "";
    return module.entryPermission || module.permission || module.requiredPermission || "";
  }

  function userPermissionCoverageStateClass(state) {
    if (state === "blocked") return "permission-coverage-state-blocked";
    if (state === "pending") return "permission-coverage-state-pending";
    return "permission-coverage-state-visible";
  }

  function userPermissionCoverageItems(payload = {}) {
    const visibleMenuModules = Array.isArray(payload.visibleMenuModules) ? payload.visibleMenuModules : [];
    const blockedMenuModules = Array.isArray(payload.blockedMenuModules) ? payload.blockedMenuModules : [];
    const configuredMenuModules = Array.isArray(payload.configuredMenuModules) ? payload.configuredMenuModules : [];
    const permissions = new Set(Array.isArray(payload.permissions) ? payload.permissions : []);
    const visibleKeys = new Set(visibleMenuModules.map((module) => userPermissionModuleKey(module)).filter(Boolean));
    const blockedKeys = new Set(blockedMenuModules.map((module) => userPermissionModuleKey(module)).filter(Boolean));
    const visibleItems = visibleMenuModules.map((module) => {
      const entryPermission = userPermissionModuleEntryPermission(module);
      return {
        key: userPermissionModuleKey(module),
        label: userPermissionModuleLabel(module),
        href: userPermissionModuleHref(module),
        entryPermission,
        state: "visible",
        stateLabel: "可进入",
        reason: entryPermission && permissions.has(entryPermission) ? "入口权限已生效" : "已纳入有效菜单",
      };
    });
    const blockedItems = blockedMenuModules.map((module) => {
      const missingEntryPermission = module?.missingEntryPermission || userPermissionModuleEntryPermission(module) || "缺少入口权限";
      return {
        key: userPermissionModuleKey(module),
        label: userPermissionModuleLabel(module),
        href: userPermissionModuleHref(module),
        entryPermission: userPermissionModuleEntryPermission(module),
        state: "blocked",
        stateLabel: "被拦截",
        reason: missingEntryPermission,
      };
    });
    const pendingItems = configuredMenuModules
      .map((module) => {
        const key = userPermissionModuleKey(module);
        return {
          key,
          label: userPermissionModuleLabel(module),
          href: userPermissionModuleHref(module),
          entryPermission: userPermissionModuleEntryPermission(module),
          state: "pending",
          stateLabel: "待校验",
          reason: "角色已配置，等待入口权限匹配",
        };
      })
      .filter((item) => item.key && !visibleKeys.has(item.key) && !blockedKeys.has(item.key));
    return [...visibleItems, ...blockedItems, ...pendingItems];
  }

  function renderUserPermissionCoverage(
    payload,
    targetSelector = "#userEffectivePermissionCoverage",
    emptyText = "选择账号后生成模块权限覆盖矩阵。",
  ) {
    const target = $(targetSelector);
    if (!target) return;
    target.classList.add("permission-coverage-list");
    if (!payload) {
      target.innerHTML = `<p class="trace-empty">${escapeHtml(emptyText)}</p>`;
      return;
    }
    const items = userPermissionCoverageItems(payload);
    const visibleMenuModules = Array.isArray(payload.visibleMenuModules) ? payload.visibleMenuModules : [];
    const blockedMenuModules = Array.isArray(payload.blockedMenuModules) ? payload.blockedMenuModules : [];
    const configuredMenuModules = Array.isArray(payload.configuredMenuModules) ? payload.configuredMenuModules : [];
    const permissions = Array.isArray(payload.permissions) ? payload.permissions : [];
    if (!items.length) {
      target.innerHTML = '<p class="trace-empty">暂无可展示的菜单模块覆盖，请先为账号绑定角色。</p>';
      return;
    }
    target.innerHTML = `
      <section class="permission-coverage-summary">
        <span><b>配置模块</b>${escapeHtml(configuredMenuModules.length)}</span>
        <span><b>可进入</b>${escapeHtml(visibleMenuModules.length)}</span>
        <span><b>被拦截</b>${escapeHtml(blockedMenuModules.length)}</span>
        <span><b>有效权限</b>${escapeHtml(permissions.length)}</span>
      </section>
      ${items
        .map(
          (item) => `
            <article class="permission-coverage-item ${userPermissionCoverageStateClass(item.state)}">
              <header>
                <strong>${escapeHtml(item.label)}</strong>
                <span>${escapeHtml(item.stateLabel)}</span>
              </header>
              <p><b>模块标识</b><code>${escapeHtml(item.key || "-")}</code></p>
              <p><b>入口权限</b><code>${escapeHtml(item.entryPermission || "-")}</code></p>
              <p><b>判断依据</b><code>${escapeHtml(item.reason || "-")}</code></p>
              ${item.href ? `<p><b>页面地址</b><code>${escapeHtml(item.href)}</code></p>` : ""}
            </article>
          `,
        )
        .join("")}
    `;
  }

  const DATA_SCOPE_LABELS = {
    areas: "区县",
    projects: "项目",
    towns: "乡镇",
    villages: "村",
    blockCodes: "林班",
  };

  function permissionReceiptScopeChips(dataScopes = {}) {
    const chips = Object.entries(DATA_SCOPE_LABELS)
      .map(([key, label]) => {
        const values = Array.isArray(dataScopes[key]) ? dataScopes[key] : [];
        if (!values.length) return "";
        return `<span><b>${escapeHtml(label)}</b>${escapeHtml(values.join(", "))}</span>`;
      })
      .filter(Boolean);
    if (!chips.length) return '<span><b>数据范围</b>未限定</span>';
    return chips.join("");
  }

  function permissionReceiptIssueText(blockedMenuModules, unknownRoles, invalidRoles) {
    const issueLabels = [];
    if (blockedMenuModules.length) {
      issueLabels.push(`阻断菜单 ${blockedMenuModules.map((item) => item.label || item.key || "-").join(", ")}`);
    }
    if (unknownRoles.length) {
      issueLabels.push(`未知角色 ${unknownRoles.map((item) => item.roleCode || item.label || "-").join(", ")}`);
    }
    if (invalidRoles.length) {
      issueLabels.push(`无效角色 ${invalidRoles.map((item) => item.roleCode || item.label || "-").join(", ")}`);
    }
    return issueLabels.join("；");
  }

  function renderUserPermissionReceipt(
    payload,
    targetSelector = "#userPermissionReceipt",
    emptyText = "选择账号后生成有效权限回执。",
  ) {
    const target = $(targetSelector);
    if (!target) return;
    if (!payload) {
      target.innerHTML = `<p class="trace-empty">${escapeHtml(emptyText)}</p>`;
      return;
    }
    const visibleMenuModules = Array.isArray(payload.visibleMenuModules) ? payload.visibleMenuModules : [];
    const blockedMenuModules = Array.isArray(payload.blockedMenuModules) ? payload.blockedMenuModules : [];
    const permissions = Array.isArray(payload.permissions) ? payload.permissions : [];
    const configuredMenuModules = Array.isArray(payload.configuredMenuModules) ? payload.configuredMenuModules : [];
    const unknownRoles = Array.isArray(payload.unknownRoles) ? payload.unknownRoles : [];
    const invalidRoles = Array.isArray(payload.invalidRoles) ? payload.invalidRoles : [];
    const dataScopes = payload.dataScopes || {};
    const issueText = permissionReceiptIssueText(blockedMenuModules, unknownRoles, invalidRoles);
    const statusText = issueText ? "需修正" : "可生效";
    target.innerHTML = `
      <article class="permission-receipt ${issueText ? "permission-receipt-warning" : ""}">
        <div class="permission-receipt-header">
          <div>
            <strong>${escapeHtml(payload.user || $("#username")?.value.trim() || "账号")}</strong>
            <span>${escapeHtml((payload.roles || []).join(", ") || "未绑定角色")}</span>
          </div>
          <em>${escapeHtml(statusText)}</em>
        </div>
        <div class="permission-receipt-grid">
          <span><b>可见菜单</b>${escapeHtml(visibleMenuModules.length)} / ${escapeHtml(configuredMenuModules.length)}</span>
          <span><b>被拦截</b>${escapeHtml(blockedMenuModules.length)}</span>
          <span><b>有效权限</b>${escapeHtml(permissions.length)}</span>
          <span><b>异常角色</b>${escapeHtml(unknownRoles.length + invalidRoles.length)}</span>
        </div>
        <div class="permission-receipt-scopes">${permissionReceiptScopeChips(dataScopes)}</div>
        ${issueText ? `<p class="permission-receipt-notice">${escapeHtml(issueText)}</p>` : ""}
      </article>
    `;
  }

  function dataScopeValueCount(dataScopes = {}) {
    if (!dataScopes || typeof dataScopes !== "object") return 0;
    return Object.values(dataScopes).reduce((count, value) => {
      if (Array.isArray(value)) return count + value.filter(Boolean).length;
      return count + (value ? 1 : 0);
    }, 0);
  }

  function userAccessReceiptSummaryItems(user = activeUser(), payload = state.userEffectivePermissions) {
    const visibleMenuModules = Array.isArray(payload?.visibleMenuModules) ? payload.visibleMenuModules : [];
    const blockedMenuModules = Array.isArray(payload?.blockedMenuModules) ? payload.blockedMenuModules : [];
    const configuredMenuModules = Array.isArray(payload?.configuredMenuModules) ? payload.configuredMenuModules : [];
    const permissions = Array.isArray(payload?.permissions) ? payload.permissions : [];
    const unknownRoles = Array.isArray(payload?.unknownRoles) ? payload.unknownRoles : [];
    const invalidRoles = Array.isArray(payload?.invalidRoles) ? payload.invalidRoles : [];
    const dataScopes = payload?.dataScopes || user?.dataScopes || {};
    const effectivePermissionCount = permissions.length;
    const visibleMenuCount = visibleMenuModules.length;
    const blockedMenuCount = blockedMenuModules.length;
    const configuredMenuCount = configuredMenuModules.length;
    const roleIssueCount = unknownRoles.length + invalidRoles.length;
    const scopeValueCount = dataScopeValueCount(dataScopes);
    const auditEventCount = Array.isArray(user?.properties?.auditEvents) ? user.properties.auditEvents.length : 0;
    return [
      {
        label: "\u83dc\u5355\u53ef\u89c1",
        value: `${visibleMenuCount}/${configuredMenuCount}`,
        meta: blockedMenuCount ? `\u963b\u65ad\u83dc\u5355 ${blockedMenuCount} \u4e2a` : "\u5df2\u6309\u89d2\u8272\u6743\u9650\u751f\u6548",
        tone: blockedMenuCount ? "warning" : "ready",
      },
      {
        label: "\u6709\u6548\u6743\u9650",
        value: effectivePermissionCount,
        meta: roleIssueCount ? `\u5f02\u5e38\u89d2\u8272 ${roleIssueCount} \u4e2a` : "\u89d2\u8272\u7ee7\u627f\u6743\u9650\u5df2\u5c55\u5f00",
        tone: roleIssueCount ? "warning" : "ready",
      },
      {
        label: "\u6570\u636e\u8303\u56f4",
        value: scopeValueCount,
        meta: scopeValueCount ? "\u5df2\u9650\u5b9a\u533a\u57df\u3001\u9879\u76ee\u6216\u6797\u73ed" : "\u672a\u9650\u5b9a\u6570\u636e\u8303\u56f4",
        tone: scopeValueCount ? "ready" : "warning",
      },
      {
        label: "\u8bbf\u95ee\u56de\u6267",
        value: user?.username || payload?.user || "-",
        meta: `\u5ba1\u8ba1\u4e8b\u4ef6 ${auditEventCount} \u6761`,
        tone: "ready",
        action: "user-access",
        permission: USER_EVENT_EXPORT_PERMISSION,
      },
    ];
  }

  function receiptSummaryCard(item) {
    const tone = item.tone ? ` tone-${item.tone}` : "";
    const actionAttribute =
      item.action === "user-access"
        ? 'data-receipt-action="user-access"'
        : `data-receipt-action="${escapeHtml(item.action || "")}"`;
    const command = item.action
      ? `<button type="button" class="button-ghost receipt-summary-command" ${actionAttribute} data-permission="${USER_EVENT_EXPORT_PERMISSION}">\u5bfc\u51fa\u56de\u6267</button>`
      : "";
    return `
      <article class="receipt-summary-card${tone}">
        <span>${escapeHtml(item.label || "-")}</span>
        <strong>${escapeHtml(item.value ?? "-")}</strong>
        <small>${escapeHtml(item.meta || "-")}</small>
        ${command}
      </article>
    `;
  }

  function renderUserAccessReceiptSummary(user = activeUser(), payload = state.userEffectivePermissions) {
    const target = $("#userAccessReceiptSummary");
    if (!target) return;
    if (!user?.id) {
      target.innerHTML = '<p class="trace-empty">\u8bf7\u9009\u62e9\u8d26\u53f7\u751f\u6210\u8bbf\u95ee\u6743\u9650\u56de\u6267\u6458\u8981\u3002</p>';
      return;
    }
    target.innerHTML = userAccessReceiptSummaryItems(user, payload).map(receiptSummaryCard).join("");
    applyActionPermissions();
  }

  function renderUserEffectivePermissionPreview(
    payload = state.userEffectivePermissions,
    targetSelector = "#userEffectivePermissionPreview",
    emptyText = "选择账号后加载有效权限。",
  ) {
    const target = $(targetSelector);
    if (!target) return;
    if (!payload) {
      target.innerHTML = `<p class="trace-empty">${escapeHtml(emptyText)}</p>`;
      return;
    }
    const visibleMenuModules = Array.isArray(payload.visibleMenuModules) ? payload.visibleMenuModules : [];
    const blockedMenuModules = Array.isArray(payload.blockedMenuModules) ? payload.blockedMenuModules : [];
    const permissions = Array.isArray(payload.permissions) ? payload.permissions : [];
    const configuredMenuModules = Array.isArray(payload.configuredMenuModules) ? payload.configuredMenuModules : [];
    const unknownRoles = Array.isArray(payload.unknownRoles) ? payload.unknownRoles : [];
    const invalidRoles = Array.isArray(payload.invalidRoles) ? payload.invalidRoles : [];
    const dataScopes = payload.dataScopes || {};
    target.innerHTML =
      previewGroup("无效角色", invalidRoles, "preview-blocked", (item) => item.label || item.roleCode, (item) => {
        const reason = item.reason === "deleted" ? "角色已删除" : "角色已停用";
        return `${item.roleCode || ""} · ${reason}`;
      }) +
      previewGroup("可见菜单", visibleMenuModules, "preview-effective", (item) => item.label || item.key, (item) => item.href || item.key) +
      previewGroup("被拦截菜单", blockedMenuModules, "preview-blocked", (item) => item.label || item.key, (item) => item.missingEntryPermission || "缺少入口权限") +
      previewGroup("已配置菜单", configuredMenuModules, "preview-action", (item) => item, () => "角色配置") +
      previewGroup("未知角色", unknownRoles, "preview-unknown", (item) => item.label || item.roleCode, (item) => item.roleCode || "未在角色台账中找到") +
      previewGroup("有效权限", permissions, "preview-action", (item) => item, () => "可执行权限") +
      `<section class="preview-group preview-effective"><strong>数据范围</strong><span>${escapeHtml(stringifyPretty(dataScopes, {}))}</span></section>`;
  }

  async function loadUserEffectivePermissions(user = activeUser()) {
    if (!user?.id) {
      state.userEffectivePermissions = null;
      renderUserEffectivePermissionPreview(null);
      renderUserPermissionReceipt(null);
      renderUserPermissionCoverage(null, "#userEffectivePermissionCoverage");
      renderUserAccessReceiptSummary(null, null);
      return;
    }
    const target = $("#userEffectivePermissionPreview");
    if (target) target.innerHTML = '<p class="trace-empty">正在加载账号有效权限...</p>';
    renderUserPermissionReceipt(null, "#userPermissionReceipt", "正在生成有效权限回执...");
    renderUserPermissionCoverage(null, "#userEffectivePermissionCoverage", "正在生成模块权限覆盖矩阵...");
    try {
      const payload = await api(`/api/admin/users/${encodeURIComponent(user.id)}/effective-permissions`);
      state.userEffectivePermissions = payload;
      renderUserPermissionReceipt(payload);
      renderUserPermissionCoverage(payload, "#userEffectivePermissionCoverage");
      renderUserEffectivePermissionPreview(payload);
      renderUserAccessReceiptSummary(user, payload);
    } catch (error) {
      state.userEffectivePermissions = null;
      renderUserPermissionReceipt(null, "#userPermissionReceipt", `有效权限回执生成失败：${error.message}`);
      renderUserPermissionCoverage(null, "#userEffectivePermissionCoverage", `模块权限覆盖生成失败：${error.message}`);
      if (target) target.innerHTML = `<p class="trace-empty">有效权限加载失败：${escapeHtml(error.message)}</p>`;
    }
  }

  function renderUserDraftEffectivePermissions(payload = state.userDraftEffectivePermissions) {
    renderUserEffectivePermissionPreview(payload, "#userDraftPermissionPreview", "填写角色和数据范围后预览草稿权限。");
    renderUserPermissionReceipt(payload, "#userDraftPermissionReceipt", "填写角色和数据范围后生成草稿权限回执。");
    renderUserPermissionCoverage(payload, "#userDraftPermissionCoverage");
  }

  function userDraftPreviewPayload() {
    syncDataScopesToJson();
    return {
      username: $("#username")?.value.trim() || "",
      status: $("#userStatus")?.value.trim() || "active",
      roles: splitValues($("#assignedRoles")?.value || ""),
      dataScopes: parseJson("数据范围 JSON", $("#userDataScopes")?.value || "{}", {}),
    };
  }

  async function loadUserDraftEffectivePermissions() {
    const target = $("#userDraftPermissionPreview");
    if (!target) return;
    target.innerHTML = '<p class="trace-empty">正在预览草稿权限...</p>';
    renderUserPermissionCoverage(null, "#userDraftPermissionCoverage", "正在生成草稿模块权限覆盖矩阵...");
    try {
      const payload = await api("/api/admin/users/effective-permissions/preview", {
        method: "POST",
        body: JSON.stringify(userDraftPreviewPayload()),
      });
      state.userDraftEffectivePermissions = payload;
      renderUserDraftEffectivePermissions(payload);
    } catch (error) {
      state.userDraftEffectivePermissions = null;
      renderUserPermissionReceipt(null, "#userDraftPermissionReceipt", `草稿权限回执生成失败：${error.message}`);
      renderUserPermissionCoverage(null, "#userDraftPermissionCoverage", `草稿模块权限覆盖生成失败：${error.message}`);
      target.innerHTML = `<p class="trace-empty">草稿权限预览失败：${escapeHtml(error.message)}</p>`;
    }
  }

  function scheduleUserDraftEffectivePermissions() {
    window.clearTimeout(userDraftPreviewTimer);
    userDraftPreviewTimer = window.setTimeout(loadUserDraftEffectivePermissions, 220);
  }

  function renderDetail(user = activeUser()) {
    const panel = $("#userDetailPanel");
    if (!user) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      renderUserEffectivePermissionPreview(null);
      renderUserPermissionReceipt(null);
      renderUserAccessReceiptSummary(null, null);
      return;
    }
    $("#userDetailTitle").textContent = `${user.displayName || user.username || "账号"}详情`;
    $("#userDetailEmpty").hidden = true;
    $("#userDetailGrid").innerHTML = [
      detailItem("用户名", user.username || "-"),
      detailItem("显示名称", user.displayName || "-"),
      detailItem("状态", user.status || "active"),
      detailItem("绑定角色", (user.roles || []).join(", ") || "-"),
      detailItem("数据范围", stringifyPretty(user.dataScopes, { areas: [] })),
      detailItem("更新时间", formatDateTime(user.updatedAt)),
      detailItem("扩展字段", stringifyPretty(user.properties, {})),
    ].join("");
    renderUserAccessReceiptSummary(user, null);
    renderUserAuditEvents(user);
    loadUserEffectivePermissions(user);
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    renderRows();
  }

  function parseDataScopesFromTextarea() {
    try {
      return JSON.parse($("#userDataScopes")?.value || "{}") || {};
    } catch (error) {
      return {};
    }
  }

  function syncDataScopesFromJson() {
    const scopes = parseDataScopesFromTextarea();
    $("#userDataScopeAreas").value = Array.isArray(scopes.areas) ? scopes.areas.join(", ") : "";
    $("#userDataScopeProjects").value = Array.isArray(scopes.projects) ? scopes.projects.join(", ") : "";
    $("#userDataScopeTowns").value = Array.isArray(scopes.towns) ? scopes.towns.join(", ") : "";
    $("#userDataScopeVillages").value = Array.isArray(scopes.villages) ? scopes.villages.join(", ") : "";
    $("#userDataScopeBlockCodes").value = Array.isArray(scopes.blockCodes) ? scopes.blockCodes.join(", ") : "";
  }

  function syncDataScopesToJson() {
    const scopes = parseDataScopesFromTextarea();
    scopes.areas = splitValues($("#userDataScopeAreas").value);
    scopes.projects = splitValues($("#userDataScopeProjects").value);
    scopes.towns = splitValues($("#userDataScopeTowns").value);
    scopes.villages = splitValues($("#userDataScopeVillages").value);
    scopes.blockCodes = splitValues($("#userDataScopeBlockCodes").value);
    $("#userDataScopes").value = stringifyPretty(scopes, { areas: [], projects: [], towns: [], villages: [], blockCodes: [] });
  }

  function fillForm(user = {}) {
    state.activeId = user.id || "";
    $("#userFormTitle").textContent = user.id ? "编辑账号" : "新建账号";
    $("#userId").value = user.id || "";
    $("#username").value = user.username || "";
    $("#username").readOnly = Boolean(user.id);
    $("#displayName").value = user.displayName || "";
    $("#userStatus").value = user.status || "active";
    $("#assignedRoles").value = Array.isArray(user.roles) ? user.roles.join(", ") : "";
    syncUserRoleSelectionsFromField();
    $("#userDataScopes").value = stringifyPretty(user.dataScopes, { areas: [] });
    $("#userProperties").value = stringifyPretty(user.properties, {});
    $("#saveUser").setAttribute("data-permission", user.id ? USER_UPDATE_PERMISSION : USER_CREATE_PERMISSION);
    $("#deleteUser").setAttribute("data-permission", USER_DELETE_PERMISSION);
    $("#deleteUser").hidden = !user.id;
    syncDataScopesFromJson();
    state.userDraftEffectivePermissions = null;
    renderUserDraftEffectivePermissions(null);
    renderRows();
    applyActionPermissions();
  }

  function openUserEditor(mode, user = {}) {
    closeUserDetail();
    fillForm(mode === "edit" ? user : {});
    $("#userForm").classList.remove("hidden");
    $("#userForm").setAttribute("aria-hidden", "false");
    $("#username").focus();
    loadUserDraftEffectivePermissions();
  }

  function closeUserEditor() {
    $("#userForm").classList.add("hidden");
    $("#userForm").setAttribute("aria-hidden", "true");
  }

  function closeUserDetail() {
    $("#userDetailPanel").classList.add("hidden");
    $("#userDetailPanel").setAttribute("aria-hidden", "true");
  }

  function payloadFromForm() {
    syncDataScopesToJson();
    return {
      username: $("#username").value.trim(),
      displayName: $("#displayName").value.trim(),
      status: $("#userStatus").value.trim() || "active",
      roles: splitValues($("#assignedRoles").value),
      dataScopes: parseJson("数据范围 JSON", $("#userDataScopes").value, { areas: [] }),
      properties: parseJson("扩展 JSON", $("#userProperties").value, {}),
    };
  }

  async function loadUsers() {
    setStatus("busy", "正在加载用户账号...");
    pager.setBusy(true);
    try {
      const payload = await api(`/api/admin/users?${userQuery()}`);
      if (pager.setTotal(payload.total ?? 0)) return loadUsers();
      state.users = Array.isArray(payload.items) ? payload.items : [];
      consumeInitialUserSelection();
      if (state.activeId && !activeUser()) state.activeId = "";
      renderRows();
      renderDetail(activeUser());
      setStatus("online", `已加载 ${payload.total ?? state.users.length} 个账号。`);
    } catch (error) {
      setStatus("offline", `账号加载失败：${error.message}`);
    } finally {
      pager.setBusy(false);
    }
  }

  function reloadUsersFromFirstPage() {
    pager.reset();
    return loadUsers();
  }

  function userEventQuery() {
    return query({
      q: $("#userEventKeyword")?.value.trim() || "",
      action: $("#userEventActionFilter")?.value.trim() || "",
      username: $("#userEventUserFilter")?.value.trim() || "",
      limit: 100,
    });
  }

  function renderUserEventRows() {
    const body = $("#userEventRows");
    if (!body) return;
    if (!state.userEvents.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无账号权限变更记录</td></tr>';
      return;
    }
    body.innerHTML = state.userEvents
      .map((event) => {
        const changedFields = Array.isArray(event.changedFields) ? event.changedFields.join(", ") : "-";
        const eventLabel = `${event.action || "-"} 事件`;
        return `
          <tr>
            <td><div class="cell-stack"><strong>${escapeHtml(eventLabel)}</strong><small>${escapeHtml(event.eventId || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(event.username || "-")}</strong><small>${escapeHtml(event.displayName || event.userId || "-")}</small></div></td>
            <td><span class="status-pill">${escapeHtml(event.action || "-")}</span></td>
            <td>${escapeHtml(changedFields || "-")}</td>
            <td>${escapeHtml(event.actor || "-")}</td>
            <td>${escapeHtml(formatDateTime(event.at))}</td>
          </tr>
        `;
      })
      .join("");
  }

  async function loadUserEvents() {
    const body = $("#userEventRows");
    try {
      const payload = await api(`/api/admin/users/events?${userEventQuery()}`);
      state.userEvents = Array.isArray(payload.items) ? payload.items : [];
      renderUserEventRows();
    } catch (error) {
      if (body) body.innerHTML = `<tr class="placeholder-row"><td colspan="6">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  async function downloadFile(path, filename, messages) {
    setStatus("busy", messages.busy);
    try {
      const response = await fetch(`${AdminCommon.apiBase()}${path}`, {
        headers: AdminCommon.buildHeaders(),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus("online", messages.done);
    } catch (error) {
      setStatus("offline", `${messages.fail}：${error.message}`);
    }
  }

  async function exportUserEvents() {
    await downloadFile(
      `/api/admin/users/events.csv?${userEventQuery()}`,
      "user-events.csv",
      {
        busy: "正在导出用户账号审计 CSV...",
        done: "用户账号审计 CSV 已开始下载。",
        fail: "用户账号审计导出失败",
      },
    );
  }

  function userAccessReceiptFilename(user) {
    const stem = String(user?.username || user?.id || "user")
      .trim()
      .replace(/[^A-Za-z0-9_.-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "user";
    return `user-access-receipt-${stem}.json`;
  }

  async function exportUserAccessReceipt(user = activeUser()) {
    if (!user?.id) {
      setStatus("offline", "请先从账号台账选择一个账号。");
      return;
    }
    await downloadFile(
      `/api/admin/users/${encodeURIComponent(user.id)}/access-receipt.json`,
      userAccessReceiptFilename(user),
      {
        busy: "正在导出账号有效权限回执...",
        done: "账号有效权限回执已开始下载。",
        fail: "账号有效权限回执导出失败",
      },
    );
  }

  async function saveUser(event) {
    event.preventDefault();
    let body;
    try {
      body = JSON.stringify(payloadFromForm());
    } catch (error) {
      setStatus("offline", error.message);
      return;
    }
    const id = $("#userId").value.trim();
    const path = id ? `/api/admin/users/${encodeURIComponent(id)}` : "/api/admin/users";
    const method = id ? "PATCH" : "POST";
    setStatus("busy", "正在保存用户账号...");
    try {
      const saved = await api(path, { method, body });
      state.activeId = saved.id;
      closeUserEditor();
      await loadUsers();
      await loadUserEvents();
      await loadUserOperationQueue();
      await refreshRoleMenu();
      renderDetail(state.users.find((user) => String(user.id) === String(saved.id)) || saved);
      setStatus("online", "用户账号已保存。");
    } catch (error) {
      setStatus("offline", `账号保存失败：${error.message}`);
    }
  }

  async function deleteUser(user = activeUser()) {
    if (!user) return;
    setStatus("busy", "正在删除用户账号...");
    try {
      await api(`/api/admin/users/${encodeURIComponent(user.id)}`, { method: "DELETE" });
      state.activeId = "";
      closeUserEditor();
      closeUserDetail();
      await loadUsers();
      await loadUserEvents();
      await loadUserOperationQueue();
      await refreshRoleMenu();
      setStatus("online", "用户账号已软删除。");
    } catch (error) {
      setStatus("offline", `账号删除失败：${error.message}`);
    }
  }

  async function restoreUser(user = activeUser()) {
    if (!user) return;
    setStatus("busy", "正在恢复用户账号...");
    try {
      const payload = await api(`/api/admin/users/${encodeURIComponent(user.id)}/restore`, { method: "POST" });
      state.activeId = payload.user?.id || user.id;
      await loadUsers();
      await loadUserEvents();
      await loadUserOperationQueue();
      await refreshRoleMenu();
      renderDetail(state.users.find((item) => String(item.id) === String(state.activeId)) || payload.user);
      setStatus("online", "用户账号已恢复。");
    } catch (error) {
      setStatus("offline", `账号恢复失败：${error.message}`);
    }
  }

  function handleRowAction(event) {
    const userButton = event.target.closest("[data-user-action]");
    if (userButton) {
      event.stopPropagation();
      if (userButton.disabled) return true;
      const row = userButton.closest("tr[data-id]");
      const user = state.users.find((item) => String(item.id) === String(row?.dataset.id)) || null;
      if (!user) return true;
      state.activeId = user.id;
      if (userButton.dataset.userAction === "restore") {
        restoreUser(user);
      }
      return true;
    }
    const button = event.target.closest("[data-row-action]");
    if (!button) return false;
    event.stopPropagation();
    if (button.disabled) return true;
    const row = button.closest("tr[data-id]");
    const user = state.users.find((item) => String(item.id) === String(row?.dataset.id)) || null;
    if (!user) return true;
    state.activeId = user.id;
    const action = button.dataset.rowAction;
    if (action === "view") {
      renderDetail(user);
    } else if (action === "edit") {
      openUserEditor("edit", user);
      renderRows();
    } else if (action === "delete") {
      deleteUser(user);
    }
    return true;
  }

  function handleUserAccessReceiptSummaryAction(event) {
    const button = event.target.closest("[data-receipt-action]");
    if (!button) return false;
    event.preventDefault();
    event.stopPropagation();
    if (button.disabled) return true;
    const action = button.dataset.receiptAction;
    const user = activeUser();
    if (action === "user-access") {
      exportUserAccessReceipt(user);
    }
    return true;
  }

  function initialize() {
    initShell();
    loadRoleOptions();
    applyInitialUserQuery();
    pager = createLedgerPager({ anchor: $("#userRows").closest(".table-wrap"), onPageChange: loadUsers });
    $("#refreshUserOperationQueue")?.addEventListener("click", loadUserOperationQueue);
    $("#userOperationQueueRows")?.addEventListener("click", handleUserOperationQueueAction);
    $("#reloadUsers").addEventListener("click", loadUsers);
    $("#newUser").addEventListener("click", () => openUserEditor("create"));
    $("#userForm").addEventListener("submit", saveUser);
    $("#cancelUserEdit").addEventListener("click", closeUserEditor);
    $("#closeUserDetail").addEventListener("click", closeUserDetail);
    $("#deleteUser").addEventListener("click", () => deleteUser(activeUser()));
    $("#exportUserAccessReceipt")?.addEventListener("click", () => exportUserAccessReceipt(activeUser()));
    $("#userAccessReceiptSummary")?.addEventListener("click", handleUserAccessReceiptSummaryAction);
    $("#exportUserEvents")?.setAttribute("data-permission", USER_EVENT_EXPORT_PERMISSION);
    $("#refreshUserEvents")?.addEventListener("click", loadUserEvents);
    $("#exportUserEvents")?.addEventListener("click", exportUserEvents);
    $("#userEventActionFilter")?.addEventListener("input", () => window.setTimeout(loadUserEvents, 180));
    $("#userEventUserFilter")?.addEventListener("input", () => window.setTimeout(loadUserEvents, 180));
    $("#userEventKeyword")?.addEventListener("input", () => window.setTimeout(loadUserEvents, 180));
    $("#refreshUserDraftPermissionPreview")?.addEventListener("click", loadUserDraftEffectivePermissions);
    $("#userRoleChecklist")?.addEventListener("change", syncAssignedRolesFromChecklist);
    $("#assignedRoles")?.addEventListener("input", syncUserRoleSelectionsFromField);
    ["#username", "#userStatus", "#assignedRoles"].forEach((selector) => {
      $(selector)?.addEventListener("input", scheduleUserDraftEffectivePermissions);
    });
    ["#userDataScopeAreas", "#userDataScopeProjects", "#userDataScopeTowns", "#userDataScopeVillages", "#userDataScopeBlockCodes"].forEach((selector) => {
      $(selector).addEventListener("input", () => {
        syncDataScopesToJson();
        scheduleUserDraftEffectivePermissions();
      });
    });
    $("#userDataScopes").addEventListener("change", () => {
      syncDataScopesFromJson();
      scheduleUserDraftEffectivePermissions();
    });
    ["#userStatusFilter", "#userRoleFilter"].forEach((selector) => {
      $(selector).addEventListener("change", reloadUsersFromFirstPage);
    });
    ["#userKeyword", "#userRoleFilter"].forEach((selector) => {
      $(selector).addEventListener("input", () => {
        window.clearTimeout(userFilterTimer);
        userFilterTimer = window.setTimeout(reloadUsersFromFirstPage, 180);
      });
    });
    $("#includeDeletedUsers").addEventListener("change", reloadUsersFromFirstPage);
    $("#userRows").addEventListener("click", (event) => {
      if (handleRowAction(event)) return;
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      state.activeId = row.dataset.id;
      renderDetail(activeUser());
    });
    loadUsers();
    loadUserEvents();
    loadUserOperationQueue();
  }

  initialize();
})();
