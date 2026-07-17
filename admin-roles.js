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
  const PAGE_PERMISSION = "system.roles.view";
  const ROLE_CREATE_PERMISSION = "system.roles.create";
  const ROLE_UPDATE_PERMISSION = "system.roles.update";
  const ROLE_DELETE_PERMISSION = "system.roles.delete";
  const ROLE_RESTORE_PERMISSION = "system.roles.restore";
  const ROLE_EVENT_EXPORT_PERMISSION = "system.roles.export";
  const state = {
    roles: [],
    roleEvents: [],
    assignedUsers: [],
    activeId: "",
    rolePreview: null,
    operationQueue: null,
    catalog: { menuModules: [], permissions: [], matrix: [], coverage: null, permissionImplications: {}, rolePresets: [], permissionClosures: [] },
  };
  let pager;
  let roleFilterTimer;
  let rolePreviewTimer = 0;
  const PERMISSION_CLOSURE_PRIORITY = [
    "phase1-import-acceptance-loop",
    "phase1-imagery-delivery-loop",
    "phase1-layer-publishing-loop",
    "phase1-delivery-loop",
    "identity-access-loop",
  ];
  const VIEW_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>';
  const EDIT_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 20 9-9-4-4-9 9-2 6Z"></path><path d="m15 8 1-1a2.8 2.8 0 0 1 4 4l-1 1"></path></svg>';
  const DELETE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="m19 6-1 14H6L5 6"></path><path d="M10 11v5"></path><path d="M14 11v5"></path></svg>';
  const RECEIPT_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6Z"></path><path d="M14 3v5h5"></path><path d="M9 13h6"></path><path d="M9 17h5"></path></svg>';
  const RESTORE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.4-6.4"></path><path d="M18 3v5h-5"></path><path d="M21 12a9 9 0 0 1-15.4 6.4"></path><path d="M6 21v-5h5"></path></svg>';
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
    "map.layers.publish": [
      "map.layers.view",
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
  const ROLE_STATUS_LABELS = {
    active: "启用",
    paused: "停用",
    disabled: "停用",
    deleted: "已删除",
  };
  const ROLE_EVENT_ACTION_LABELS = {
    create: "新建",
    update: "更新",
    delete: "删除",
    restore: "恢复",
  };

  function activeRole() {
    return state.roles.find((role) => String(role.id) === String(state.activeId)) || null;
  }

  function roleStatusLabel(status) {
    const key = String(status || "active").trim();
    return ROLE_STATUS_LABELS[key] || key || "-";
  }

  function roleEventActionLabel(action) {
    const key = String(action || "").trim();
    return ROLE_EVENT_ACTION_LABELS[key] || key || "-";
  }

  function splitPermissionLines(value) {
    return String(value || "")
      .split(/[\n,;\s]+/)
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

  function optionHtml(value, label) {
    const safeValue = escapeHtml(value || "");
    const safeLabel = escapeHtml(label || value || "");
    return `<option value="${safeValue}" label="${safeLabel}"></option>`;
  }

  function renderCatalogOptions() {
    const menuList = $("#menuModuleOptions");
    const permissionList = $("#permissionOptions");
    if (menuList) {
      menuList.innerHTML = (state.catalog.menuModules || [])
        .map((item) => optionHtml(item.key, `${item.label || item.key} · ${item.group || ""}`))
        .join("");
    }
    if (permissionList) {
      permissionList.innerHTML = (state.catalog.permissions || [])
        .map((item) => optionHtml(item.code, `${item.label || item.code} · ${item.module || ""}`))
        .join("");
    }
  }

  function selectedRolePreset() {
    const key = $("#rolePresetSelect")?.value || "";
    if (!key) return null;
    return (state.catalog.rolePresets || []).find((preset) => preset.key === key) || null;
  }

  function renderRolePresetOptions() {
    const select = $("#rolePresetSelect");
    if (!select) return;
    const current = select.value;
    const options = (state.catalog.rolePresets || [])
      .map((preset) => {
        const label = [preset.label || preset.key, preset.group || ""].filter(Boolean).join(" · ");
        return `<option value="${escapeHtml(preset.key)}">${escapeHtml(label)}</option>`;
      })
      .join("");
    select.innerHTML = `<option value="">不使用模板</option>${options}`;
    if ((state.catalog.rolePresets || []).some((preset) => preset.key === current)) {
      select.value = current;
    }
    renderRolePresetSummary();
  }

  function renderRolePresetSummary() {
    const target = $("#rolePresetSummary");
    if (!target) return;
    const preset = selectedRolePreset();
    if (!preset) {
      target.dataset.risk = "empty";
      target.innerHTML = `
        <strong>未选择授权模板</strong>
        <span>选择阶段模板后可一键填充菜单模块与权限码，仍可继续手工微调。</span>
      `;
      return;
    }
    const summary = preset.summary || {};
    const preview = preset.preview || {};
    const risk = preview.riskLevel || "ready";
    target.dataset.risk = risk;
    target.innerHTML = `
      <strong>${escapeHtml(preset.label || preset.key)}</strong>
      <span>${escapeHtml(preset.description || "")}</span>
      <small>${escapeHtml(preset.group || "模板")} · 菜单 ${escapeHtml(summary.menuModuleCount || (preset.menuModules || []).length)} 个 · 权限 ${escapeHtml(summary.permissionCount || (preset.permissions || []).length)} 个 · 展开 ${escapeHtml(summary.expandedPermissionCount || (preset.expandedPermissions || []).length)} 个</small>
    `;
  }

  function permissionClosurePriority(closure) {
    const index = PERMISSION_CLOSURE_PRIORITY.indexOf(closure?.key || "");
    return index === -1 ? PERMISSION_CLOSURE_PRIORITY.length : index;
  }

  function closureExpandedPermissionChips(closure = {}) {
    const summary = closure.summary || {};
    const expandedPermissions = Array.isArray(closure.expandedPermissions) && closure.expandedPermissions.length
      ? closure.expandedPermissions
      : closure.permissions || [];
    return `
      <div class="closure-permission-chips">
        <span>展开权限 ${escapeHtml(summary.expandedPermissionCount ?? expandedPermissions.length)}</span>
        ${renderCompactList(expandedPermissions, { limit: 6 })}
      </div>
    `;
  }

  function closureOmittedPermissionChips(closure = {}) {
    const omittedPermissions = Array.isArray(closure.omittedPermissions)
      ? closure.omittedPermissions.filter(Boolean)
      : [];
    if (!omittedPermissions.length) return "";
    return `
      <div class="closure-permission-chips omitted-permission-chips">
        <span>未授予高危权限 ${escapeHtml(omittedPermissions.length)}</span>
        ${renderCompactList(omittedPermissions, { limit: 5 })}
      </div>
    `;
  }

  function roleClosureCard(closure = {}) {
    const summary = closure.summary || {};
    const preview = closure.preview || {};
    const risk = preview.riskLevel || "empty";
    const endpoints = Array.isArray(closure.workflowEndpoints) ? closure.workflowEndpoints : [];
    return `
      <article class="role-closure-card" data-permission-closure="${escapeHtml(closure.key || "")}" data-risk="${escapeHtml(risk)}">
        <div>
          <small>${escapeHtml(closure.group || "权限闭环")}</small>
          <strong>${escapeHtml(closure.label || closure.key || "权限配置包")}</strong>
          <span>${escapeHtml(closure.description || "")}</span>
        </div>
        <dl>
          <div><dt>菜单</dt><dd>${escapeHtml(summary.menuModuleCount ?? (closure.menuModules || []).length ?? 0)}</dd></div>
          <div><dt>权限</dt><dd>${escapeHtml(summary.permissionCount ?? (closure.permissions || []).length ?? 0)}</dd></div>
          <div><dt>接口</dt><dd>${escapeHtml(summary.workflowEndpointCount ?? endpoints.length ?? 0)}</dd></div>
        </dl>
        ${closureExpandedPermissionChips(closure)}
        ${closureOmittedPermissionChips(closure)}
        <p>${escapeHtml(endpoints.slice(0, 4).join(" / "))}</p>
        <div class="role-closure-actions">
          <button type="button" class="button-ghost compact-button" data-closure-action="apply" data-closure-key="${escapeHtml(closure.key || "")}" data-permission="${PAGE_PERMISSION}">追加到草稿</button>
          <button type="button" class="button-ghost compact-button" data-closure-action="export" data-permission="${ROLE_EVENT_EXPORT_PERMISSION}">导出方案</button>
        </div>
      </article>
    `;
  }

  function renderPermissionClosureGuides() {
    const target = $("#roleClosureGuides");
    if (!target) return;
    const closures = [...(state.catalog.permissionClosures || [])].sort((a, b) => permissionClosurePriority(a) - permissionClosurePriority(b));
    if (!closures.length) {
      target.innerHTML = '<article class="role-closure-card"><strong>暂无闭环配置包</strong><span>权限目录尚未返回第一阶段闭环配置，请检查后端 permissionClosures。</span></article>';
      return;
    }
    target.innerHTML = closures.map(roleClosureCard).join("");
    applyActionPermissions();
  }

  function roleOperationQueueItem(item = {}, lane = {}) {
    const requiredPermission = item.requiredPermission || lane.requiredPermission || PAGE_PERMISSION;
    const meta = [
      `风险 ${item.riskLevel || "-"}`,
      `菜单阻断 ${item.blockedMenuModuleCount ?? 0}`,
      `动作缺口 ${item.missingActionPermissionCount ?? 0}`,
      `依赖缺口 ${item.permissionDependencyIssueCount ?? 0}`,
    ];
    return `
      <div class="operation-queue-row" data-role-operation-row="${escapeHtml(item.roleCode || "")}">
        <p><strong>${escapeHtml(item.roleCode || "-")}</strong> ${escapeHtml(item.name || "")}</p>
        <small>${escapeHtml(item.summary || "等待补充权限诊断")}</small>
        <div class="operation-queue-meta">
          ${meta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}
          <span>权限 ${escapeHtml(requiredPermission)}</span>
        </div>
        <button
          type="button"
          class="button-ghost compact-button"
          data-role-operation-action="open"
          data-role-code="${escapeHtml(item.roleCode || "")}"
          data-role-lane="${escapeHtml(lane.key || "")}"
          data-permission="${escapeHtml(requiredPermission)}"
        >打开角色</button>
      </div>
    `;
  }

  function renderRoleOperationQueue() {
    const target = $("#roleOperationQueueRows");
    if (!target) return;
    const lanes = Array.isArray(state.operationQueue?.items) ? state.operationQueue.items : [];
    if (!lanes.length) {
      target.innerHTML = `
        <article class="operation-queue-item">
          <div class="operation-queue-head">
            <div><span>暂无队列</span><strong>0</strong><small>当前没有可展示的角色权限闭环状态</small></div>
          </div>
        </article>
      `;
      return;
    }
    target.innerHTML = lanes
      .map((lane) => {
        const items = Array.isArray(lane.items) ? lane.items : [];
        const rows = items.length
          ? items.map((item) => roleOperationQueueItem(item, lane)).join("")
          : '<div class="operation-queue-row"><p>暂无待处理角色</p><small>该队列当前为空</small></div>';
        return `
          <article class="operation-queue-item tone-${escapeHtml(lane.tone || "ready")}">
            <div class="operation-queue-head">
              <div>
                <span>${escapeHtml(lane.label || lane.key || "角色队列")}</span>
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

  async function loadRoleOperationQueue() {
    const target = $("#roleOperationQueueRows");
    if (target) {
      target.innerHTML = `
        <article class="operation-queue-item">
          <div class="operation-queue-head">
            <div><span>正在加载</span><strong>...</strong><small>正在读取角色权限操作队列</small></div>
          </div>
        </article>
      `;
    }
    try {
      const payload = await api("/api/admin/roles/operation-queue?limit=4");
      state.operationQueue = payload;
      renderRoleOperationQueue();
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

  async function openRoleOperationQueueItem(laneKey, roleCode) {
    const keyword = $("#roleKeyword");
    if (keyword) keyword.value = roleCode || "";
    await loadRoles();
    const role = state.roles.find((item) => String(item.roleCode || "") === String(roleCode || ""));
    if (!role) {
      setStatus("offline", `未找到队列角色：${roleCode || laneKey || "-"}`);
      return;
    }
    state.activeId = role.id;
    renderRows();
    renderDetail(role);
    $("#roleRows")?.closest(".table-wrap")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleRoleOperationQueueAction(event) {
    const button = event.target.closest("[data-role-operation-action]");
    if (!button) return false;
    event.preventDefault();
    event.stopPropagation();
    if (button.disabled) return true;
    openRoleOperationQueueItem(button.dataset.roleLane || "", button.dataset.roleCode || "");
    return true;
  }

  function applyPermissionClosure(key) {
    const closure = (state.catalog.permissionClosures || []).find((item) => item.key === key);
    if (!closure) {
      setStatus("offline", "未找到该权限闭环配置包。");
      return;
    }
    const menuValues = mergeDraftValues(splitValues($("#menuModules")?.value || ""), closure.menuModules || []);
    const permissionValues = mergeDraftValues(splitPermissionLines($("#permissions")?.value || ""), closure.permissions || []);
    if ($("#menuModules")) $("#menuModules").value = menuValues.join(", ");
    if ($("#permissions")) $("#permissions").value = permissionValues.join("\n");
    syncRoleSelectionsFromFields();
    setStatus("online", `${closure.label || closure.key} 已追加到角色草稿，请核对后保存。`);
  }

  function applyRolePreset() {
    const preset = selectedRolePreset();
    if (!preset) {
      setStatus("offline", "请先选择一个授权模板。");
      return;
    }
    if ($("#menuModules")) $("#menuModules").value = (preset.menuModules || []).join(", ");
    if ($("#permissions")) $("#permissions").value = (preset.permissions || []).join("\n");
    syncRoleSelectionsFromFields();
    renderRolePresetSummary();
    setStatus("online", `${preset.label || preset.key} 已套用，可继续调整后保存。`);
  }

  function catalogMatrix() {
    if (Array.isArray(state.catalog.matrix) && state.catalog.matrix.length) {
      return state.catalog.matrix;
    }
    const groups = new Map();
    (state.catalog.menuModules || []).forEach((module) => {
      const group = module.group || "system";
      if (!groups.has(group)) groups.set(group, []);
      const permissions = (state.catalog.permissions || [])
        .filter((permission) => permission.module === module.key)
        .map((permission) => permission.code);
      if (module.permission && !permissions.includes(module.permission)) {
        permissions.unshift(module.permission);
      }
      groups.get(group).push({ ...module, permissions });
    });
    return Array.from(groups.entries()).map(([group, modules]) => ({ group, modules }));
  }

  function compactPermissionList(values) {
    if (!Array.isArray(values)) return [];
    return values.map((item) => String(item || "").trim()).filter(Boolean);
  }

  function compactPermissionGroups(groups) {
    if (!Array.isArray(groups)) return [];
    return groups.map((group) => compactPermissionList(group)).filter((group) => group.length);
  }

  function permissionMetaByCode(code) {
    const permission = (state.catalog.permissions || []).find((item) => item.code === code) || {};
    return {
      code,
      label: permission.label || code,
      module: permission.module || "",
      apiScopes: compactPermissionList(permission.apiScopes),
      requiresAllPermissions: compactPermissionList(permission.requiresAllPermissions),
      requiresAnyPermissions: compactPermissionGroups(permission.requiresAnyPermissions),
      dependencyReason: permission.dependencyReason || "",
    };
  }

  function modulePermissionEntries(module) {
    if (Array.isArray(module.permissionEntries) && module.permissionEntries.length) {
      return module.permissionEntries.map((permission) => {
        const kind = permission.kind || (permission.code === module.permission ? "page" : "action");
        return {
          ...permission,
          kind,
          kindLabel: permission.kindLabel || (kind === "page" ? "入口权限" : "动作权限"),
        };
      });
    }
    const seen = new Set();
    const codes = [];
    if (module.permission) codes.push(module.permission);
    (module.permissions || []).forEach((permission) => codes.push(permission));
    return codes
      .filter((code) => {
        if (!code || seen.has(code)) return false;
        seen.add(code);
        return true;
      })
      .map((code) => {
        const meta = permissionMetaByCode(code);
        const kind = code === module.permission ? "page" : "action";
        return {
          ...meta,
          kind,
          kindLabel: kind === "page" ? "入口权限" : "动作权限",
        };
      });
  }

  function permissionKindClass(kind) {
    return kind === "page" ? "permission-kind-page" : "permission-kind-action";
  }

  function draftPermissionSatisfies(permissionValues, requiredPermission) {
    const required = String(requiredPermission || "").trim();
    if (!required) return true;
    const permissions = permissionValues instanceof Set ? permissionValues : new Set(permissionValues || []);
    if (permissions.has(required)) return true;
    return Object.entries(managePermissionImplications).some(
      ([managePermission, impliedPermissions]) => permissions.has(managePermission) && impliedPermissions.includes(required),
    );
  }

  function expandedDraftPermissionSet(permissionValues) {
    const permissions = new Set();
    (permissionValues || []).forEach((permission) => {
      const code = String(permission || "").trim();
      if (!code) return;
      permissions.add(code);
      (managePermissionImplications[code] || []).forEach((impliedPermission) => permissions.add(impliedPermission));
    });
    return permissions;
  }

  function permissionDependencyIssuesForSet(permissionValues) {
    const permissions = permissionValues instanceof Set ? permissionValues : expandedDraftPermissionSet(permissionValues);
    return Array.from(permissions)
      .sort()
      .map((code) => {
        const meta = permissionMetaByCode(code);
        const requiresAllPermissions = compactPermissionList(meta.requiresAllPermissions);
        const requiresAnyPermissions = compactPermissionGroups(meta.requiresAnyPermissions);
        if (!requiresAllPermissions.length && !requiresAnyPermissions.length) return null;
        const missingAllPermissions = requiresAllPermissions.filter((permission) => !draftPermissionSatisfies(permissions, permission));
        const missingAnyPermissionGroups = requiresAnyPermissions.filter(
          (group) => !group.some((permission) => draftPermissionSatisfies(permissions, permission)),
        );
        if (!missingAllPermissions.length && !missingAnyPermissionGroups.length) return null;
        const module = (state.catalog.menuModules || []).find((item) => item.key === meta.module) || {};
        return {
          ...meta,
          permissionCode: code,
          permissionLabel: meta.label || code,
          moduleLabel: module.label || meta.module || "",
          requiresAllPermissions,
          missingAllPermissions,
          requiresAnyPermissions,
          missingAnyPermissionGroups,
          dependencyReason: meta.dependencyReason || "",
        };
      })
      .filter(Boolean);
  }

  function filterText(selector) {
    return String($(selector)?.value || "").trim().toLowerCase();
  }

  function nodeMatchesFilterText(node, text) {
    if (!text) return true;
    const inputValues = Array.from(node.querySelectorAll("input"))
      .map((input) => input.value || "")
      .join(" ");
    return `${node.textContent || ""} ${inputValues}`.toLowerCase().includes(text);
  }

  function syncChecklistGroupVisibility(rootSelector) {
    document.querySelectorAll(`${rootSelector} .checklist-group`).forEach((group) => {
      const visibleItems = Array.from(group.children).filter((child) => child.tagName !== "LEGEND" && !child.hidden);
      group.hidden = visibleItems.length === 0;
    });
  }

  function applyCatalogChecklistFilters() {
    const menuFilter = filterText("#menuModuleFilter");
    const permissionFilter = filterText("#permissionFilter");
    document.querySelectorAll("#menuModuleChecklist .check-item").forEach((item) => {
      item.hidden = !nodeMatchesFilterText(item, menuFilter);
    });
    document.querySelectorAll("#permissionChecklist .permission-module").forEach((module) => {
      const moduleMatches = nodeMatchesFilterText(module, menuFilter);
      let visiblePermissions = 0;
      module.querySelectorAll(".check-item").forEach((item) => {
        const visible = moduleMatches && nodeMatchesFilterText(item, permissionFilter);
        item.hidden = !visible;
        if (visible) visiblePermissions += 1;
      });
      module.hidden = visiblePermissions === 0;
    });
    syncChecklistGroupVisibility("#menuModuleChecklist");
    syncChecklistGroupVisibility("#permissionChecklist");
  }

  function checklistGroup(title, content) {
    return `<fieldset class="checklist-group"><legend>${escapeHtml(title)}</legend>${content}</fieldset>`;
  }

  function moduleApiScopeText(module) {
    const scopes = Array.isArray(module.apiScopes) ? module.apiScopes.filter(Boolean) : [];
    const parts = [
      module.href || module.key || "",
      module.dataDomain ? `data-domain: ${module.dataDomain}` : "",
      scopes.length ? `API: ${scopes.join(", ")}` : "",
    ].filter(Boolean);
    return parts.join(" · ");
  }

  function permissionApiScopeText(permission) {
    const scopes = Array.isArray(permission.apiScopes) ? permission.apiScopes.filter(Boolean) : [];
    return scopes.length ? `API: ${scopes.join(", ")}` : "";
  }

  function permissionDependencyText(permission) {
    const requiresAllPermissions = compactPermissionList(permission.requiresAllPermissions);
    const requiresAnyPermissions = compactPermissionGroups(permission.requiresAnyPermissions);
    const parts = [];
    if (requiresAllPermissions.length) {
      parts.push(`必须同时具备 ${requiresAllPermissions.join(", ")}`);
    }
    requiresAnyPermissions.forEach((group) => {
      parts.push(`至少具备其一 ${group.join(" / ")}`);
    });
    return parts.length ? `依赖权限: ${parts.join("；")}` : "";
  }

  function renderPermissionMatrix() {
    const menuTarget = $("#menuModuleChecklist");
    const permissionTarget = $("#permissionChecklist");
    if (!menuTarget || !permissionTarget) return;
    const matrix = catalogMatrix();
    menuTarget.innerHTML = matrix
      .map((group) =>
        checklistGroup(
          group.group || "-",
          (group.modules || [])
            .map(
              (module) => `
                <label class="check-item">
                  <input type="checkbox" data-role-selection-item="menuModules" value="${escapeHtml(module.key)}" />
                  <span>${escapeHtml(module.label || module.key)}</span>
                  <small class="permission-module-scope">${escapeHtml(moduleApiScopeText(module))}</small>
                </label>
              `,
            )
            .join(""),
        ),
      )
      .join("");
    permissionTarget.innerHTML = matrix
      .map((group) =>
        checklistGroup(
          group.group || "-",
          (group.modules || [])
            .map((module) => {
              const modulePermissions = modulePermissionEntries(module);
              if (!modulePermissions.length) return "";
              return `
                <div class="permission-module">
                  <div class="permission-module-header">
                    <div>
                      <strong>${escapeHtml(module.label || module.key)}</strong>
                      <small class="permission-module-scope">${escapeHtml(moduleApiScopeText(module))}</small>
                    </div>
                    <div class="permission-module-actions">
                      <button type="button" class="button-ghost compact-button" data-module-permission-action="select-module" data-module-key="${escapeHtml(module.key)}">全选</button>
                      <button type="button" class="button-ghost compact-button" data-module-permission-action="clear-module" data-module-key="${escapeHtml(module.key)}">清空</button>
                    </div>
                  </div>
                  ${modulePermissions
                    .map(
                      (permission) => `
                        <label class="check-item compact ${permissionKindClass(permission.kind)}" data-permission-kind="${escapeHtml(permission.kind)}">
                          <input type="checkbox" data-role-selection-item="permissions" data-module-key="${escapeHtml(module.key)}" value="${escapeHtml(permission.code)}" />
                          <span class="permission-label">${escapeHtml(permission.label)}</span>
                          <small>${escapeHtml(permission.kindLabel)} · ${escapeHtml(permission.code)}</small>
                          <small class="permission-action-scope">${escapeHtml(permissionApiScopeText(permission))}</small>
                          <small class="permission-dependency-scope">${escapeHtml(permissionDependencyText(permission))}</small>
                        </label>
                      `,
                    )
                    .join("")}
                </div>
              `;
            })
            .join(""),
        ),
      )
      .join("");
    syncRoleSelectionsFromFields();
    applyCatalogChecklistFilters();
  }

  function collectCheckedValues(selectionName) {
    return Array.from(document.querySelectorAll(`[data-role-selection-item="${selectionName}"]:checked`))
      .map((input) => input.value.trim())
      .filter(Boolean);
  }

  function controlledSelectionValues(selectionName) {
    return new Set(
      Array.from(document.querySelectorAll(`[data-role-selection-item="${selectionName}"]`))
        .map((input) => input.value.trim())
        .filter(Boolean),
    );
  }

  function uncontrolledSelectionValues(selectionName, values) {
    const controlled = controlledSelectionValues(selectionName);
    return (values || [])
      .map((value) => String(value || "").trim())
      .filter((value) => value && !controlled.has(value));
  }

  function mergeDraftValues(...groups) {
    const values = [];
    const seen = new Set();
    groups.flat().forEach((value) => {
      const text = String(value || "").trim();
      if (!text || seen.has(text)) return;
      seen.add(text);
      values.push(text);
    });
    return values;
  }

  function hasSelectionControls(selectionName) {
    return Boolean(document.querySelector(`[data-role-selection-item="${selectionName}"]`));
  }

  function setCheckedValues(selectionName, values) {
    const selected = new Set(values || []);
    document.querySelectorAll(`[data-role-selection-item="${selectionName}"]`).forEach((input) => {
      input.checked = selected.has(input.value);
    });
  }

  function permissionInputsForModule(moduleKey) {
    const key = String(moduleKey || "").trim();
    return Array.from(document.querySelectorAll('[data-role-selection-item="permissions"]')).filter((input) => input.dataset.moduleKey === key);
  }

  function setModulePermissionSelection(moduleKey, checked) {
    permissionInputsForModule(moduleKey).forEach((input) => {
      input.checked = Boolean(checked);
    });
  }

  function handleModulePermissionBulkAction(event) {
    const button = event.target.closest("[data-module-permission-action]");
    if (!button) return false;
    event.preventDefault();
    const moduleKey = button.dataset.moduleKey || "";
    const action = button.dataset.modulePermissionAction || "";
    setModulePermissionSelection(moduleKey, action === "select-module");
    syncRoleSelectionsToFields();
    return true;
  }

  function findSelectionInput(selectionName, value) {
    return Array.from(document.querySelectorAll(`[data-role-selection-item="${selectionName}"]`)).find((input) => input.value === value) || null;
  }

  function syncModuleBasePermissionFromMenu(event) {
    const input = event.target.closest('[data-role-selection-item="menuModules"]');
    if (!input || !input.checked) return;
    const module = (state.catalog.menuModules || []).find((item) => item.key === input.value);
    if (!module?.permission) return;
    const permissionInput = findSelectionInput("permissions", module.permission);
    if (permissionInput) permissionInput.checked = true;
  }

  function syncRoleSelectionsFromFields() {
    setCheckedValues("menuModules", splitValues($("#menuModules")?.value || ""));
    setCheckedValues("permissions", splitPermissionLines($("#permissions")?.value || ""));
    scheduleRoleDraftPreview();
  }

  function syncRoleSelectionsToFields() {
    const menuValues = mergeDraftValues(
      uncontrolledSelectionValues("menuModules", splitValues($("#menuModules")?.value || "")),
      collectCheckedValues("menuModules"),
    );
    const permissionValues = mergeDraftValues(uncontrolledSelectionValues("permissions", splitPermissionLines($("#permissions")?.value || "")), collectCheckedValues("permissions"));
    if ($("#menuModules")) $("#menuModules").value = menuValues.join(", ");
    if ($("#permissions")) $("#permissions").value = permissionValues.join("\n");
    scheduleRoleDraftPreview();
  }

  function selectedRoleDraft() {
    const menuModules = hasSelectionControls("menuModules")
      ? mergeDraftValues(
          uncontrolledSelectionValues("menuModules", splitValues($("#menuModules")?.value || "")),
          collectCheckedValues("menuModules"),
        )
      : splitValues($("#menuModules")?.value || "");
    const permissions = hasSelectionControls("permissions")
      ? mergeDraftValues(
          uncontrolledSelectionValues("permissions", splitPermissionLines($("#permissions")?.value || "")),
          collectCheckedValues("permissions"),
        )
      : splitPermissionLines($("#permissions")?.value || "");
    return { menuModules, permissions };
  }

  function roleDraftDiagnostics(draft = selectedRoleDraft()) {
    const permissions = expandedDraftPermissionSet(draft.permissions || []);
    const modulesByKey = new Map((state.catalog.menuModules || []).map((module) => [module.key, module]));
    const knownPermissionCodes = new Set((state.catalog.permissions || []).map((permission) => permission.code));
    const effectiveMenuModules = [];
    const blockedMenuModules = [];
    const unknownMenuModules = [];
    (draft.menuModules || []).forEach((key) => {
      const module = modulesByKey.get(key);
      if (!module) {
        unknownMenuModules.push({ key, label: key });
        return;
      }
      const missingEntryPermission = module.permission && !draftPermissionSatisfies(permissions, module.permission) ? module.permission : "";
      const item = { ...module, missingEntryPermission };
      if (missingEntryPermission) {
        blockedMenuModules.push(item);
      } else {
        effectiveMenuModules.push(item);
      }
    });
    const effectiveModuleKeys = new Set(effectiveMenuModules.map((module) => module.key));
    const actionPermissionCoverage = effectiveMenuModules
      .map((module) => {
        const actionPermissions = modulePermissionEntries(module).filter((permission) => permission.kind === "action");
        if (!actionPermissions.length) return null;
        const grantedActionPermissions = actionPermissions.filter((permission) => draftPermissionSatisfies(permissions, permission.code));
        const missingActionPermissions = actionPermissions.filter((permission) => !draftPermissionSatisfies(permissions, permission.code));
        return {
          ...module,
          grantedActionPermissions,
          missingActionPermissions,
        };
      })
      .filter(Boolean);
    const orphanActionPermissions = (draft.permissions || [])
      .map((code) => {
        if (!knownPermissionCodes.has(code)) return null;
        const meta = permissionMetaByCode(code);
        const module = modulesByKey.get(meta.module);
        if (!module || code === module.permission || effectiveModuleKeys.has(meta.module)) return null;
        return {
          ...meta,
          moduleLabel: module.label || module.key,
        };
      })
      .filter(Boolean);
    const unknownPermissions = (draft.permissions || [])
      .filter((code) => !knownPermissionCodes.has(code))
      .map((code) => ({ code, label: code, module: "" }));
    const permissionDependencyIssues = permissionDependencyIssuesForSet(permissions);
    return {
      menuModules: draft.menuModules || [],
      permissions: draft.permissions || [],
      effectiveMenuModules,
      blockedMenuModules,
      actionPermissionCoverage,
      orphanActionPermissions,
      permissionDependencyIssues,
      unknownMenuModules,
      unknownPermissions,
    };
  }

  function roleDraftSummary(diagnostics = state.rolePreview || roleDraftDiagnostics()) {
    const summary = diagnostics.summary || {};
    const actionPermissionCoverage = diagnostics.actionPermissionCoverage || [];
    const missingActionPermissions = actionPermissionCoverage.reduce(
      (count, item) => count + ((item.missingActionPermissions || []).length || 0),
      0,
    );
    return {
      configuredMenuModules: Number(summary.configuredMenuModules ?? (diagnostics.menuModules || []).length ?? 0),
      configuredPermissions: Number(summary.configuredPermissions ?? (diagnostics.permissions || []).length ?? 0),
      effectiveMenuModules: Number(summary.effectiveMenuModules ?? (diagnostics.effectiveMenuModules || []).length ?? 0),
      blockedMenuModules: Number(summary.blockedMenuModules ?? (diagnostics.blockedMenuModules || []).length ?? 0),
      actionPermissionGroups: Number(summary.actionPermissionGroups ?? actionPermissionCoverage.length ?? 0),
      missingActionPermissions: Number(summary.missingActionPermissions ?? missingActionPermissions),
      orphanActionPermissions: Number(summary.orphanActionPermissions ?? (diagnostics.orphanActionPermissions || []).length ?? 0),
      permissionDependencyIssues: Number(summary.permissionDependencyIssues ?? (diagnostics.permissionDependencyIssues || []).length ?? 0),
      unknownMenuModules: Number(summary.unknownMenuModules ?? (diagnostics.unknownMenuModules || []).length ?? 0),
      unknownPermissions: Number(summary.unknownPermissions ?? (diagnostics.unknownPermissions || []).length ?? 0),
    };
  }

  function draftRiskLevel(summary) {
    if (summary.blockedMenuModules || summary.unknownMenuModules || summary.unknownPermissions) return "error";
    if (summary.orphanActionPermissions || summary.missingActionPermissions || summary.permissionDependencyIssues) return "warning";
    if (summary.configuredMenuModules || summary.configuredPermissions) return "ready";
    return "empty";
  }

  function roleDraftCanSave(diagnostics = state.rolePreview || roleDraftDiagnostics()) {
    const risk = diagnostics.riskLevel || draftRiskLevel(roleDraftSummary(diagnostics));
    return risk !== "error";
  }

  function syncRoleSaveState(diagnostics = state.rolePreview || roleDraftDiagnostics()) {
    const saveRole = $("#saveRole");
    if (!saveRole) return;
    const risk = diagnostics.riskLevel || draftRiskLevel(roleDraftSummary(diagnostics));
    const canSave = roleDraftCanSave(diagnostics);
    saveRole.dataset.draftRisk = risk;
    saveRole.dataset.roleSaveBlocked = canSave ? "false" : "true";
    saveRole.disabled = !canSave;
    if (saveRole.classList.contains("permission-disabled") || saveRole.getAttribute("aria-disabled") === "true") {
      saveRole.disabled = true;
    }
    saveRole.title =
      risk === "error"
        ? "菜单入口缺少对应权限或存在未知项，请补齐后保存"
        : risk === "warning"
          ? "角色配置可保存，但存在动作权限覆盖或跨模块依赖提示"
          : "";
  }

  function renderRoleDraftSummary(diagnostics = state.rolePreview || roleDraftDiagnostics()) {
    const target = $("#roleDraftSummary");
    if (!target) return;
    const summary = roleDraftSummary(diagnostics);
    const risk = diagnostics.riskLevel || draftRiskLevel(summary);
    syncRoleSaveState(diagnostics);
    target.dataset.risk = risk;
    const riskLabels = {
      empty: "未配置",
      ready: "可保存",
      warning: "有提示",
      error: "需核对",
    };
    target.innerHTML = `
      <div class="draft-risk-pill">${escapeHtml(riskLabels[risk] || risk)}</div>
      <dl>
        <div><dt>有效菜单</dt><dd>${escapeHtml(summary.effectiveMenuModules)}</dd></div>
        <div><dt>阻断菜单</dt><dd>${escapeHtml(summary.blockedMenuModules)}</dd></div>
        <div><dt>缺动作权限</dt><dd>${escapeHtml(summary.missingActionPermissions)}</dd></div>
        <div><dt>孤立权限</dt><dd>${escapeHtml(summary.orphanActionPermissions)}</dd></div>
        <div><dt>依赖缺口</dt><dd>${escapeHtml(summary.permissionDependencyIssues)}</dd></div>
        <div><dt>未知项</dt><dd>${escapeHtml(summary.unknownMenuModules + summary.unknownPermissions)}</dd></div>
      </dl>
    `;
  }

  function previewGroup(title, modules, className, meta) {
    if (!modules.length) return "";
    return `
      <section class="preview-group ${className}">
        <strong>${escapeHtml(title)}</strong>
        ${modules
          .map((item) => {
            const suffix = meta ? `<small>${escapeHtml(meta(item))}</small>` : "";
            return `<span>${escapeHtml(item.label || item.key)}${suffix}</span>`;
          })
          .join("")}
      </section>
    `;
  }

  function permissionPreviewGroup(title, permissions, className, meta) {
    if (!permissions.length) return "";
    return `
      <section class="preview-group ${className}">
        <strong>${escapeHtml(title)}</strong>
        ${permissions
          .map((item) => {
            const suffix = meta ? `<small>${escapeHtml(meta(item))}</small>` : "";
            return `<span>${escapeHtml(item.label || item.code || item.key)}${suffix}</span>`;
          })
          .join("")}
      </section>
    `;
  }

  function actionCoveragePreviewGroup(coverage) {
    if (!coverage.length) return "";
    return `
      <section class="preview-group preview-action permission-coverage-group">
        <strong>动作权限覆盖</strong>
        ${coverage
          .map((item) => {
            const missingCodes = item.missingActionPermissions.map((permission) => permission.code);
            const missingText = missingCodes.length ? missingCodes.join(", ") : "已覆盖全部动作权限";
            return `
              <article class="permission-coverage-item">
                <span>${escapeHtml(item.label || item.key)}<small>已开 ${item.grantedActionPermissions.length} / 缺 ${item.missingActionPermissions.length}</small></span>
                <p><b>缺少</b><code>${escapeHtml(missingText)}</code></p>
              </article>
            `;
          })
          .join("")}
      </section>
    `;
  }

  function dependencyIssueMeta(item) {
    const missingAll = compactPermissionList(item.missingAllPermissions);
    const missingAny = compactPermissionGroups(item.missingAnyPermissionGroups)
      .map((group) => `任选 ${group.join(" / ")}`);
    return [
      item.moduleLabel || item.module || "-",
      item.permissionCode || item.code || "",
      [...missingAll, ...missingAny].join(", "),
    ].filter(Boolean).join(" · ");
  }

  function roleMenuPreviewHtml(diagnostics, emptyText = "当前未选择菜单模块") {
    const effectiveMenuModules = diagnostics.effectiveMenuModules || [];
    const blockedMenuModules = diagnostics.blockedMenuModules || [];
    const actionPermissionCoverage = diagnostics.actionPermissionCoverage || [];
    const orphanActionPermissions = diagnostics.orphanActionPermissions || [];
    const permissionDependencyIssues = diagnostics.permissionDependencyIssues || [];
    const unknownMenuModules = diagnostics.unknownMenuModules || [];
    const unknownPermissions = diagnostics.unknownPermissions || [];
    if (!effectiveMenuModules.length && !blockedMenuModules.length && !actionPermissionCoverage.length && !orphanActionPermissions.length && !permissionDependencyIssues.length && !unknownMenuModules.length && !unknownPermissions.length) {
      return `<p class="trace-empty">${escapeHtml(emptyText)}</p>`;
    }
    return [
      previewGroup("最终可见菜单", effectiveMenuModules, "preview-effective", (item) => item.group || ""),
      previewGroup("缺少入口权限", blockedMenuModules, "preview-blocked", (item) => item.missingEntryPermission || ""),
      actionCoveragePreviewGroup(actionPermissionCoverage),
      permissionPreviewGroup("孤立动作权限", orphanActionPermissions, "preview-orphan", (item) => `${item.moduleLabel || item.module || "-"} · ${item.code}`),
      permissionPreviewGroup("跨模块依赖缺口", permissionDependencyIssues, "preview-dependency", dependencyIssueMeta),
      previewGroup("\u672a\u77e5\u83dc\u5355\u6a21\u5757", unknownMenuModules, "preview-unknown", (item) => item.key || ""),
      permissionPreviewGroup("\u672a\u77e5\u6743\u9650\u7801", unknownPermissions, "preview-unknown", (item) => item.code || ""),
    ].join("");
  }

  function renderRoleMenuPreview(diagnostics = state.rolePreview || roleDraftDiagnostics()) {
    const target = $("#roleMenuPreview");
    if (!target) return;
    renderRoleDraftSummary(diagnostics);
    target.innerHTML = roleMenuPreviewHtml(diagnostics);
  }

  function roleMenuDiagnosticsForRole(role) {
    return roleDraftDiagnostics({
      menuModules: Array.isArray(role?.menuModules) ? role.menuModules : [],
      permissions: Array.isArray(role?.permissions) ? role.permissions : [],
    });
  }

  function renderRoleDetailMenuDiagnostics(role = activeRole()) {
    const target = $("#roleDetailMenuDiagnostics");
    if (!target) return;
    if (!role) {
      target.innerHTML = '<p class="trace-empty">从台账选择一个角色查看菜单诊断。</p>';
      return;
    }
    if (!Array.isArray(state.catalog.menuModules) || !state.catalog.menuModules.length) {
      target.innerHTML = '<p class="trace-empty">等待权限目录加载后生成菜单诊断。</p>';
      return;
    }
    const diagnostics = roleMenuDiagnosticsForRole(role);
    const summary = roleDraftSummary(diagnostics);
    const risk = diagnostics.riskLevel || draftRiskLevel(summary);
    const riskLabels = {
      empty: "未配置",
      ready: "生效",
      warning: "有提示",
      error: "需核对",
    };
    target.innerHTML = `
      <div class="role-detail-diagnostics-summary" data-risk="${escapeHtml(risk)}">
        <strong>${escapeHtml(riskLabels[risk] || risk)}</strong>
        <span>最终可见 ${escapeHtml(summary.effectiveMenuModules)} 个菜单</span>
        <span>阻断 ${escapeHtml(summary.blockedMenuModules)} 个</span>
        <span>缺动作权限 ${escapeHtml(summary.missingActionPermissions)} 项</span>
        <span>孤立权限 ${escapeHtml(summary.orphanActionPermissions)} 项</span>
        <span>依赖缺口 ${escapeHtml(summary.permissionDependencyIssues)} 项</span>
      </div>
      ${roleMenuPreviewHtml(diagnostics, "当前角色未配置菜单模块")}
    `;
  }

  function rolePermissionCoverageModuleState(module, diagnostics) {
    const key = String(module?.key || "").trim();
    if (!key) return "blocked";
    const effectiveKeys = new Set((diagnostics.effectiveMenuModules || []).map((item) => item.key));
    const configuredKeys = new Set(diagnostics.menuModules || []);
    if (effectiveKeys.has(key)) return "visible";
    if (configuredKeys.has(key)) return "blocked";
    return "pending";
  }

  function roleEffectivePermissionCoverageItems(role = {}) {
    const diagnostics = roleMenuDiagnosticsForRole(role);
    const expandedPermissions = expandedDraftPermissionSet(role.permissions || []);
    const modulesByKey = new Map((state.catalog.menuModules || []).map((module) => [module.key, module]));
    const configuredKeys = Array.isArray(role.menuModules) ? role.menuModules : [];
    const moduleKeys = new Set(configuredKeys);
    (role.permissions || []).forEach((code) => {
      const moduleKey = permissionMetaByCode(code).module;
      if (moduleKey) moduleKeys.add(moduleKey);
    });
    return Array.from(moduleKeys)
      .map((moduleKey) => {
        const module = modulesByKey.get(moduleKey);
        if (!module) {
          return {
            key: moduleKey,
            label: moduleKey,
            group: "未知模块",
            state: "blocked",
            stateLabel: "未知模块",
            entryPermission: "",
            grantedPermissions: [],
            missingPermissions: [],
            reason: "角色配置了权限目录中不存在的菜单模块",
          };
        }
        const entries = modulePermissionEntries(module);
        const grantedPermissions = entries.filter((permission) => draftPermissionSatisfies(expandedPermissions, permission.code));
        const missingPermissions = entries.filter((permission) => !draftPermissionSatisfies(expandedPermissions, permission.code));
        const blockedModule = (diagnostics.blockedMenuModules || []).find((item) => item.key === module.key);
        const state = rolePermissionCoverageModuleState(module, diagnostics);
        const stateLabels = {
          visible: "可见",
          blocked: "入口阻断",
          pending: "未配置入口",
        };
        const reason =
          state === "visible"
            ? "菜单入口与权限匹配"
            : state === "blocked"
              ? `缺少入口权限 ${blockedModule?.missingEntryPermission || module.permission || "-"}`
              : "已配置动作权限但未加入菜单";
        return {
          key: module.key,
          label: module.label || module.key,
          group: module.group || "",
          state,
          stateLabel: stateLabels[state] || state,
          entryPermission: module.permission || "",
          grantedPermissions: grantedPermissions.map((permission) => permission.code),
          missingPermissions: missingPermissions.map((permission) => permission.code),
          apiScopes: Array.isArray(module.apiScopes) ? module.apiScopes : [],
          reason,
        };
      })
      .sort((a, b) => {
        const groupCompare = String(a.group || "").localeCompare(String(b.group || ""), "zh-Hans-CN");
        if (groupCompare) return groupCompare;
        return String(a.label || a.key || "").localeCompare(String(b.label || b.key || ""), "zh-Hans-CN");
      });
  }

  function rolePermissionCoverageSummary(items = []) {
    return items.reduce(
      (summary, item) => {
        summary.total += 1;
        if (item.state === "visible") summary.visible += 1;
        if (item.state === "blocked") summary.blocked += 1;
        if (item.state === "pending") summary.pending += 1;
        summary.grantedPermissions += (item.grantedPermissions || []).length;
        summary.missingPermissions += (item.missingPermissions || []).length;
        return summary;
      },
      { total: 0, visible: 0, blocked: 0, pending: 0, grantedPermissions: 0, missingPermissions: 0 },
    );
  }

  function permissionCoverageStateAttribute(state) {
    if (state === "visible") return 'data-coverage-state="visible"';
    if (state === "blocked") return 'data-coverage-state="blocked"';
    if (state === "pending") return 'data-coverage-state="pending"';
    return `data-coverage-state="${escapeHtml(state || "")}"`;
  }

  function roleEffectivePermissionCoverageCard(item) {
    return `
      <article class="permission-coverage-item permission-coverage-state-${escapeHtml(item.state || "pending")}" ${permissionCoverageStateAttribute(item.state)}>
        <header>
          <strong>${escapeHtml(item.label || item.key || "-")}</strong>
          <span>${escapeHtml(item.stateLabel || item.state || "-")}</span>
        </header>
        <p><b>入口权限</b><code>${escapeHtml(item.entryPermission || "-")}</code></p>
        <p><b>已授权动作</b>${renderCompactList(item.grantedPermissions || [], { limit: 5 })}</p>
        <p><b>缺少动作</b>${renderCompactList(item.missingPermissions || [], { limit: 5 })}</p>
        <p><b>依据</b><span>${escapeHtml(item.reason || "-")}</span></p>
      </article>
    `;
  }

  function renderRoleEffectivePermissionCoverage(role = activeRole()) {
    const target = $("#roleEffectivePermissionCoverage");
    if (!target) return;
    if (!role) {
      target.innerHTML = '<p class="trace-empty">从台账选择一个角色查看有效权限覆盖矩阵。</p>';
      return;
    }
    if (!Array.isArray(state.catalog.menuModules) || !state.catalog.menuModules.length) {
      target.innerHTML = '<p class="trace-empty">等待权限目录加载后生成权限覆盖矩阵。</p>';
      return;
    }
    const items = roleEffectivePermissionCoverageItems(role);
    if (!items.length) {
      target.innerHTML = '<p class="trace-empty">当前角色未配置菜单或功能权限。</p>';
      return;
    }
    const summary = rolePermissionCoverageSummary(items);
    target.innerHTML = `
      <div class="permission-coverage-summary">
        <span><b>菜单</b>${escapeHtml(summary.visible)}/${escapeHtml(summary.total)}</span>
        <span><b>阻断</b>${escapeHtml(summary.blocked)}</span>
        <span><b>未入菜单</b>${escapeHtml(summary.pending)}</span>
        <span><b>动作权限</b>${escapeHtml(summary.grantedPermissions)} 已授 / ${escapeHtml(summary.missingPermissions)} 缺少</span>
      </div>
      <div class="permission-coverage-list">${items.map(roleEffectivePermissionCoverageCard).join("")}</div>
    `;
  }

  async function loadRoleDraftPreview() {
    try {
      state.rolePreview = await api("/api/admin/roles/preview", {
        method: "POST",
        body: JSON.stringify(selectedRoleDraft()),
      });
      renderRoleMenuPreview(state.rolePreview);
    } catch (error) {
      state.rolePreview = null;
      renderRoleMenuPreview();
    }
  }

  function scheduleRoleDraftPreview() {
    state.rolePreview = null;
    renderRoleMenuPreview();
    window.clearTimeout(rolePreviewTimer);
    rolePreviewTimer = window.setTimeout(loadRoleDraftPreview, 180);
  }

  function parseDataScopesFromTextarea() {
    try {
      return JSON.parse($("#dataScopes")?.value || "{}") || {};
    } catch (error) {
      return {};
    }
  }

  function syncDataScopesFromJson() {
    const scopes = parseDataScopesFromTextarea();
    if ($("#dataScopeAreas")) {
      $("#dataScopeAreas").value = Array.isArray(scopes.areas) ? scopes.areas.join(", ") : "";
    }
    if ($("#dataScopeProjects")) {
      $("#dataScopeProjects").value = Array.isArray(scopes.projects) ? scopes.projects.join(", ") : "";
    }
    if ($("#dataScopeTowns")) {
      $("#dataScopeTowns").value = Array.isArray(scopes.towns) ? scopes.towns.join(", ") : "";
    }
    if ($("#dataScopeVillages")) {
      $("#dataScopeVillages").value = Array.isArray(scopes.villages) ? scopes.villages.join(", ") : "";
    }
    if ($("#dataScopeBlockCodes")) {
      $("#dataScopeBlockCodes").value = Array.isArray(scopes.blockCodes) ? scopes.blockCodes.join(", ") : "";
    }
  }

  function syncDataScopesToJson() {
    const scopes = parseDataScopesFromTextarea();
    scopes.areas = splitValues($("#dataScopeAreas")?.value || "");
    scopes.projects = splitValues($("#dataScopeProjects")?.value || "");
    scopes.towns = splitValues($("#dataScopeTowns")?.value || "");
    scopes.villages = splitValues($("#dataScopeVillages")?.value || "");
    scopes.blockCodes = splitValues($("#dataScopeBlockCodes")?.value || "");
    $("#dataScopes").value = stringifyPretty(scopes, { areas: [], projects: [], towns: [], villages: [], blockCodes: [] });
  }

  function catalogHealthTone(riskLevel) {
    if (riskLevel === "error") return "danger";
    if (riskLevel === "warning") return "warning";
    return "ready";
  }

  function catalogHealthCard(label, value, key, tone = "") {
    const toneClass = tone ? ` tone-${tone}` : "";
    return `
      <article class="workflow-summary-card${toneClass}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value ?? 0)}</strong>
        <small>${escapeHtml(key)}</small>
      </article>
    `;
  }

  function catalogIssueItems(issues = {}) {
    const issueGroups = [
      ["missingPagePermissions", "入口权限缺失", (item) => `${item.label || item.module || "-"} · ${item.permission || "-"}`],
      ["permissionsWithoutKnownModule", "未知模块权限", (item) => `${item.code || "-"} · ${item.module || "-"}`],
      ["missingManageImplications", "全权管理隐含权限缺失", (item) => `${item.managePermission || "-"} -> ${item.permission || "-"}`],
      ["missingPermissionDependencyTargets", "依赖权限目标缺失", (item) => `${item.permission || "-"} -> ${item.dependency || "-"}`],
    ];
    return issueGroups.flatMap(([key, label, formatter]) =>
      (issues[key] || []).map((item) => ({ label, text: formatter(item) })),
    );
  }

  function renderPermissionCatalogHealth() {
    const healthTarget = $("#permissionCatalogHealth");
    const issueTarget = $("#permissionCatalogIssues");
    const coverage = state.catalog.coverage;
    if (!coverage) {
      if (healthTarget) {
        healthTarget.innerHTML = catalogHealthCard("等待加载", 0, "权限目录体检尚未读取");
      }
      if (issueTarget) {
        issueTarget.innerHTML = '<p class="trace-empty">等待权限目录返回体检结果。</p>';
      }
      return;
    }
    const summary = coverage.summary || {};
    const issues = coverage.issues || {};
    const issueCount =
      Number(summary.missingPagePermissions || 0) +
      Number(summary.permissionsWithoutKnownModule || 0) +
      Number(summary.missingManageImplications || 0) +
      Number(summary.missingPermissionDependencyTargets || 0);
    if (healthTarget) {
      healthTarget.innerHTML = [
        catalogHealthCard("菜单模块", summary.menuModuleTotal, "可配置后台入口", "ready"),
        catalogHealthCard("权限码", summary.permissionTotal, "角色可勾选权限"),
        catalogHealthCard("动作权限", summary.actionPermissionTotal, "新增、编辑、删除、发布等按钮权限"),
        catalogHealthCard("目录风险", issueCount, coverage.riskLevel || "ready", catalogHealthTone(coverage.riskLevel)),
      ].join("");
    }
    const items = catalogIssueItems(issues);
    if (issueTarget) {
      if (!items.length) {
        issueTarget.innerHTML = '<p class="trace-empty">权限目录完整：入口权限、动作权限、跨模块依赖和全权管理隐含权限均已收录。</p>';
        return;
      }
      issueTarget.innerHTML = items
        .map(
          (item) => `
            <article class="catalog-issue-item">
              <strong>${escapeHtml(item.label)}</strong>
              <span>${escapeHtml(item.text)}</span>
            </article>
          `,
        )
        .join("");
    }
  }

  async function loadPermissionCatalog() {
    try {
      const payload = await api("/api/admin/permission-catalog");
      state.catalog = {
        menuModules: Array.isArray(payload.menuModules) ? payload.menuModules : [],
        permissions: Array.isArray(payload.permissions) ? payload.permissions : [],
        matrix: Array.isArray(payload.matrix) ? payload.matrix : [],
        coverage: payload.coverage || null,
        permissionImplications: payload.permissionImplications || {},
        rolePresets: Array.isArray(payload.rolePresets) ? payload.rolePresets : [],
        permissionClosures: Array.isArray(payload.permissionClosures) ? payload.permissionClosures : [],
      };
      state.catalog.permissionImplications = normalizePermissionImplications(state.catalog.permissionImplications);
      syncPermissionImplications(payload.permissionImplications);
      renderCatalogOptions();
      renderRolePresetOptions();
      renderPermissionClosureGuides();
      renderPermissionMatrix();
      renderPermissionCatalogHealth();
      renderRoleDetailMenuDiagnostics(activeRole());
      renderRoleEffectivePermissionCoverage(activeRole());
    } catch (error) {
      state.catalog.coverage = null;
      renderCatalogOptions();
      renderRolePresetOptions();
      renderPermissionClosureGuides();
      renderPermissionMatrix();
      renderPermissionCatalogHealth();
      renderRoleDetailMenuDiagnostics(activeRole());
      renderRoleEffectivePermissionCoverage(activeRole());
    }
  }

  function isDeletedRole(role) {
    return Boolean(role?.deletedAt);
  }

  function roleActionButtons(role) {
    if (isDeletedRole(role)) {
      return `
        <div class="row-actions" aria-label="角色操作">
          <button type="button" class="icon-button" data-row-action="view" aria-label="查看角色" title="查看角色">${VIEW_ICON}</button>
          <button type="button" class="icon-button" data-role-action="restore" data-permission="${ROLE_RESTORE_PERMISSION}" aria-label="恢复角色" title="恢复角色">${RESTORE_ICON}</button>
        </div>
      `;
    }
    return `
      <div class="row-actions row-actions-wide" aria-label="角色操作">
        <button type="button" class="icon-button" data-row-action="view" aria-label="查看角色" title="查看角色">${VIEW_ICON}</button>
        <button type="button" class="icon-button" data-row-action="edit" data-permission="${ROLE_UPDATE_PERMISSION}" aria-label="编辑角色" title="编辑角色">${EDIT_ICON}</button>
        <button type="button" class="icon-button danger" data-row-action="delete" data-permission="${ROLE_DELETE_PERMISSION}" aria-label="删除角色" title="删除角色">${DELETE_ICON}</button>
        <button type="button" class="icon-button" data-role-action="receipt" data-permission="${ROLE_EVENT_EXPORT_PERMISSION}" aria-label="导出权限回执" title="导出权限回执">${RECEIPT_ICON}</button>
      </div>
    `;
  }

  function renderCompactList(values, options = {}) {
    const items = Array.isArray(values) ? values.filter(Boolean) : [];
    if (!items.length) return '<span class="ledger-chip-empty">-</span>';
    const limit = options.limit || 4;
    const title = items.join(", ");
    const visibleItems = items.slice(0, limit);
    const hiddenCount = Math.max(0, items.length - visibleItems.length);
    return `
      <div class="ledger-chip-list" title="${escapeHtml(title)}">
        ${visibleItems.map((item) => `<span class="ledger-chip">${escapeHtml(item)}</span>`).join("")}
        ${hiddenCount ? `<span class="ledger-chip-more">+${hiddenCount}</span>` : ""}
      </div>
    `;
  }

  function renderRows() {
    const body = $("#roleRows");
    if (!state.roles.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="5">暂无角色配置</td></tr>';
      return;
    }
    body.innerHTML = state.roles
      .map((role) => {
        const active = String(role.id) === String(state.activeId) ? "active" : "";
        return `
          <tr data-id="${escapeHtml(role.id)}" class="${active}">
            <td><div class="cell-stack"><strong>${escapeHtml(role.roleCode || "-")}</strong><small>${escapeHtml(role.name || "-")}</small></div></td>
            <td>${renderCompactList(role.menuModules, { limit: 5 })}</td>
            <td>${renderCompactList(role.permissions, { limit: 4 })}</td>
            <td><span class="status-pill">${escapeHtml(roleStatusLabel(role.status))}</span></td>
            <td>${roleActionButtons(role)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  function detailItem(label, value) {
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "未填")}</dd></div>`;
  }

  function dataScopeValueCount(dataScopes = {}) {
    if (!dataScopes || typeof dataScopes !== "object") return 0;
    return Object.values(dataScopes).reduce((count, value) => {
      if (Array.isArray(value)) return count + value.filter(Boolean).length;
      return count + (value ? 1 : 0);
    }, 0);
  }

  function rolePermissionReceiptSummaryItems(role = {}) {
    const diagnostics = roleDraftDiagnostics({
      menuModules: Array.isArray(role.menuModules) ? role.menuModules : [],
      permissions: Array.isArray(role.permissions) ? role.permissions : [],
    });
    const summary = roleDraftSummary(diagnostics);
    const configuredPermissionCount = Array.isArray(role.permissions) ? role.permissions.length : 0;
    const expandedPermissionCount = expandedDraftPermissionSet(role.permissions || []).size;
    const dataScopeCount = dataScopeValueCount(role.dataScopes || {});
    const auditEventCount = Array.isArray(role?.properties?.auditEvents) ? role.properties.auditEvents.length : 0;
    const risk = diagnostics.riskLevel || draftRiskLevel(summary);
    return [
      {
        label: "\u83dc\u5355\u53ef\u89c1",
        value: `${summary.effectiveMenuModules}/${summary.configuredMenuModules}`,
        meta: summary.blockedMenuModules ? "\u5b58\u5728\u88ab\u6743\u9650\u963b\u65ad\u7684\u83dc\u5355" : "\u83dc\u5355\u5165\u53e3\u4e0e\u6743\u9650\u4e00\u81f4",
        tone: summary.blockedMenuModules ? "danger" : risk === "warning" ? "warning" : "ready",
      },
      {
        label: "\u6743\u9650\u8986\u76d6",
        value: `${configuredPermissionCount}/${expandedPermissionCount}`,
        meta: "\u76f4\u63a5\u914d\u7f6e / \u7ee7\u627f\u5c55\u5f00",
        tone: summary.missingActionPermissions || summary.orphanActionPermissions ? "warning" : "ready",
      },
      {
        label: "\u6570\u636e\u8303\u56f4",
        value: dataScopeCount,
        meta: dataScopeCount ? "\u5df2\u9650\u5b9a\u533a\u57df\u3001\u9879\u76ee\u6216\u6797\u73ed" : "\u672a\u9650\u5b9a\u6570\u636e\u8303\u56f4",
        tone: dataScopeCount ? "ready" : "warning",
      },
      {
        label: "\u914d\u7f6e\u56de\u6267",
        value: role.roleCode || role.id || "-",
        meta: `\u5ba1\u8ba1\u4e8b\u4ef6 ${auditEventCount} \u6761`,
        tone: "ready",
        action: "role-permission",
        permission: ROLE_EVENT_EXPORT_PERMISSION,
      },
    ];
  }

  function receiptSummaryCard(item) {
    const tone = item.tone ? ` tone-${item.tone}` : "";
    const actionAttribute =
      item.action === "role-permission"
        ? 'data-receipt-action="role-permission"'
        : `data-receipt-action="${escapeHtml(item.action || "")}"`;
    const command = item.action
      ? `<button type="button" class="button-ghost receipt-summary-command" ${actionAttribute} data-permission="${ROLE_EVENT_EXPORT_PERMISSION}">\u5bfc\u51fa\u56de\u6267</button>`
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

  function renderRolePermissionReceiptSummary(role) {
    const target = $("#rolePermissionReceiptSummary");
    if (!target) return;
    if (!role?.id) {
      target.innerHTML = '<p class="trace-empty">\u8bf7\u9009\u62e9\u89d2\u8272\u751f\u6210\u6743\u9650\u914d\u7f6e\u56de\u6267\u6458\u8981\u3002</p>';
      return;
    }
    target.innerHTML = rolePermissionReceiptSummaryItems(role).map(receiptSummaryCard).join("");
    applyActionPermissions();
  }

  function traceLink(href, label) {
    return `<a class="trace-link" href="${escapeHtml(href)}">${escapeHtml(label)}</a>`;
  }

  function roleAssignedUserScopeText(user) {
    const scopes = user?.dataScopes || {};
    const parts = [
      Array.isArray(scopes.areas) && scopes.areas.length ? `区县 ${scopes.areas.join(", ")}` : "",
      Array.isArray(scopes.projects) && scopes.projects.length ? `项目 ${scopes.projects.join(", ")}` : "",
      Array.isArray(scopes.towns) && scopes.towns.length ? `乡镇 ${scopes.towns.join(", ")}` : "",
      Array.isArray(scopes.villages) && scopes.villages.length ? `村 ${scopes.villages.join(", ")}` : "",
      Array.isArray(scopes.blockCodes) && scopes.blockCodes.length ? `林班 ${scopes.blockCodes.join(", ")}` : "",
    ].filter(Boolean);
    return parts.join(" / ") || "未限定";
  }

  function renderRoleAssignedUsers(role = activeRole()) {
    const target = $("#roleAssignedUsersList");
    if (!target) return;
    if (!role?.roleCode) {
      target.innerHTML = '<p class="trace-empty">保存角色后可查看绑定账号。</p>';
      return;
    }
    if (!state.assignedUsers.length) {
      target.innerHTML = `<p class="trace-empty">暂无账号绑定角色 ${escapeHtml(role.roleCode || "-")}。</p>`;
      return;
    }
    target.innerHTML = state.assignedUsers
      .map((user) => {
        const detailHref = `admin-users.html?userId=${encodeURIComponent(user.id || "")}`;
        const roleHref = `admin-users.html?role=${encodeURIComponent(role.roleCode || "")}`;
        return `
          <article class="trace-item">
            <strong>${traceLink(detailHref, user.displayName || user.username || user.id || "-")}</strong>
            <span>${escapeHtml(user.username || "-")} · ${escapeHtml(user.status || "active")} · ${escapeHtml(roleAssignedUserScopeText(user))}</span>
            <span>${traceLink(roleHref, `查看角色 ${role.roleCode || "-"} 绑定账号`)}</span>
          </article>
        `;
      })
      .join("");
  }

  async function loadRoleAssignedUsers(role = activeRole()) {
    const target = $("#roleAssignedUsersList");
    if (!role?.roleCode) {
      state.assignedUsers = [];
      renderRoleAssignedUsers(role);
      return;
    }
    const roleCode = role.roleCode || "";
    if (target) target.innerHTML = '<p class="trace-empty">正在加载关联账号...</p>';
    try {
      const payload = await api(`/api/admin/users?${query({ role: role.roleCode || "", limit: 100 })}`);
      if (activeRole()?.roleCode !== roleCode) return;
      state.assignedUsers = Array.isArray(payload.items) ? payload.items : [];
      renderRoleAssignedUsers(role);
    } catch (error) {
      state.assignedUsers = [];
      if (target) target.innerHTML = `<p class="trace-empty">关联账号加载失败：${escapeHtml(error.message)}</p>`;
    }
  }

  function renderRoleAuditEvents(role) {
    const target = $("#roleAuditEventList");
    if (!target) return;
    const auditEvents = Array.isArray(role?.properties?.auditEvents) ? role.properties.auditEvents : [];
    if (!auditEvents.length) {
      target.innerHTML = '<p class="trace-empty">暂无角色变更审计</p>';
      return;
    }
    target.innerHTML = auditEvents
      .slice()
      .reverse()
      .map((event) => {
        const changedFields = Array.isArray(event.changedFields) ? event.changedFields.join(", ") : "-";
        return `
          <article class="trace-item">
            <strong>${escapeHtml(roleEventActionLabel(event.action))} · ${escapeHtml(changedFields || "-")}</strong>
            <span>${escapeHtml(formatDateTime(event.at))} · ${escapeHtml(event.actor || "-")} · ${escapeHtml(event.roleCode || role.roleCode || "-")}</span>
          </article>
        `;
      })
      .join("");
  }

  function renderDetail(role = activeRole()) {
    const panel = $("#roleDetailPanel");
    if (!role) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      return;
    }
    $("#roleDetailTitle").textContent = `${role.name || role.roleCode || "角色"}详情`;
    $("#roleDetailEmpty").hidden = true;
    $("#roleDetailGrid").innerHTML = [
      detailItem("角色编码", role.roleCode || "-"),
      detailItem("角色名称", role.name || "-"),
      detailItem("状态", roleStatusLabel(role.status)),
      detailItem("菜单模块", (role.menuModules || []).join(", ") || "-"),
      detailItem("权限码", (role.permissions || []).join(", ") || "-"),
      detailItem("数据范围", stringifyPretty(role.dataScopes, { areas: [] })),
      detailItem("更新时间", formatDateTime(role.updatedAt)),
      detailItem("扩展字段", stringifyPretty(role.properties, {})),
    ].join("");
    renderRolePermissionReceiptSummary(role);
    renderRoleDetailMenuDiagnostics(role);
    renderRoleEffectivePermissionCoverage(role);
    loadRoleAssignedUsers(role);
    renderRoleAuditEvents(role);
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    renderRows();
  }

  function fillForm(role = {}) {
    state.activeId = role.id || "";
    $("#roleFormTitle").textContent = role.id ? "编辑角色" : "新建角色";
    $("#roleId").value = role.id || "";
    $("#roleCode").value = role.roleCode || "";
    $("#roleCode").readOnly = Boolean(role.id);
    $("#roleName").value = role.name || "";
    $("#roleStatus").value = role.status || "active";
    $("#menuModules").value = Array.isArray(role.menuModules) ? role.menuModules.join(", ") : "";
    $("#permissions").value = Array.isArray(role.permissions) ? role.permissions.join("\n") : "";
    $("#dataScopes").value = stringifyPretty(role.dataScopes, { areas: [] });
    $("#roleProperties").value = stringifyPretty(role.properties, {});
    $("#saveRole").setAttribute("data-permission", role.id ? ROLE_UPDATE_PERMISSION : ROLE_CREATE_PERMISSION);
    $("#deleteRole").setAttribute("data-permission", ROLE_DELETE_PERMISSION);
    $("#deleteRole").hidden = !role.id;
    if ($("#rolePresetSelect")) $("#rolePresetSelect").value = "";
    renderRolePresetSummary();
    syncRoleSelectionsFromFields();
    syncDataScopesFromJson();
    renderRows();
    applyActionPermissions();
  }

  function openRoleEditor(mode, role = {}) {
    closeRoleDetail();
    fillForm(mode === "edit" ? role : {});
    $("#roleForm").classList.remove("hidden");
    $("#roleForm").setAttribute("aria-hidden", "false");
    $("#roleCode").focus();
  }

  function closeRoleEditor() {
    $("#roleForm").classList.add("hidden");
    $("#roleForm").setAttribute("aria-hidden", "true");
  }

  function closeRoleDetail() {
    $("#roleDetailPanel").classList.add("hidden");
    $("#roleDetailPanel").setAttribute("aria-hidden", "true");
  }

  function payloadFromForm() {
    syncRoleSelectionsToFields();
    syncDataScopesToJson();
    const { menuModules, permissions } = selectedRoleDraft();
    return {
      roleCode: $("#roleCode").value.trim(),
      name: $("#roleName").value.trim(),
      status: $("#roleStatus").value.trim() || "active",
      menuModules,
      permissions,
      dataScopes: parseJson("数据范围 JSON", $("#dataScopes").value, { areas: [] }),
      properties: parseJson("扩展 JSON", $("#roleProperties").value, {}),
    };
  }

  function currentQuery() {
    return query({
      q: $("#roleKeyword").value.trim(),
      status: $("#roleStatusFilter").value.trim(),
      permission: $("#permissionFilter").value.trim(),
      menuModule: $("#menuModuleFilter").value.trim(),
      includeDeleted: $("#includeDeletedRoles")?.checked ? "true" : "",
      limit: pager.limit,
      offset: pager.offset,
    });
  }

  async function loadRoles() {
    setStatus("busy", "正在加载角色权限...");
    pager.setBusy(true);
    try {
      const payload = await api(`/api/admin/roles?${currentQuery()}`);
      if (pager.setTotal(payload.total ?? 0)) return loadRoles();
      state.roles = Array.isArray(payload.items) ? payload.items : [];
      if (state.activeId && !activeRole()) state.activeId = "";
      renderRows();
      renderDetail(activeRole());
      setStatus("online", `已加载 ${payload.total ?? state.roles.length} 个角色。`);
    } catch (error) {
      setStatus("offline", `角色加载失败：${error.message}`);
    } finally {
      pager.setBusy(false);
    }
  }

  function reloadRolesFromFirstPage() {
    pager.reset();
    return loadRoles();
  }

  function roleEventQuery() {
    return query({
      q: $("#roleEventKeyword")?.value.trim() || "",
      action: $("#roleEventActionFilter")?.value.trim() || "",
      roleCode: $("#roleEventRoleFilter")?.value.trim() || "",
      limit: 100,
    });
  }

  function renderRoleEventRows() {
    const body = $("#roleEventRows");
    if (!body) return;
    if (!state.roleEvents.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无角色权限变更记录</td></tr>';
      return;
    }
    body.innerHTML = state.roleEvents
      .map((event) => {
        const changedFields = Array.isArray(event.changedFields) ? event.changedFields.join(", ") : "-";
        const eventLabel = `${roleEventActionLabel(event.action)} 事件`;
        return `
          <tr>
            <td><div class="cell-stack"><strong>${escapeHtml(eventLabel)}</strong><small>${escapeHtml(event.eventId || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(event.roleCode || "-")}</strong><small>${escapeHtml(event.roleName || event.roleId || "-")}</small></div></td>
            <td><span class="status-pill">${escapeHtml(roleEventActionLabel(event.action))}</span></td>
            <td>${escapeHtml(changedFields || "-")}</td>
            <td>${escapeHtml(event.actor || "-")}</td>
            <td>${escapeHtml(formatDateTime(event.at))}</td>
          </tr>
        `;
      })
      .join("");
  }

  async function loadRoleEvents() {
    const body = $("#roleEventRows");
    try {
      const payload = await api(`/api/admin/roles/events?${roleEventQuery()}`);
      state.roleEvents = Array.isArray(payload.items) ? payload.items : [];
      renderRoleEventRows();
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

  async function exportRoleEvents() {
    await downloadFile(
      `/api/admin/roles/events.csv?${roleEventQuery()}`,
      "role-events.csv",
      {
        busy: "正在导出角色权限审计 CSV...",
        done: "角色权限审计 CSV 已开始下载。",
        fail: "角色权限审计导出失败",
      },
    );
  }

  async function exportPermissionCatalog() {
    await downloadFile(
      "/api/admin/permission-catalog.csv",
      "permission-catalog.csv",
      {
        busy: "正在导出权限目录 CSV...",
        done: "权限目录 CSV 已开始下载。",
        fail: "权限目录导出失败",
      },
    );
  }

  async function exportPermissionClosurePackage() {
    await downloadFile(
      "/api/admin/permission-closures.json",
      "permission-closure-package.json",
      {
        busy: "正在导出第一阶段权限闭环方案包...",
        done: "第一阶段权限闭环方案包已开始下载。",
        fail: "权限闭环方案包导出失败",
      },
    );
  }

  function roleReceiptFilename(role) {
    const stem = String(role?.roleCode || role?.id || "role")
      .trim()
      .replace(/[^A-Za-z0-9_.-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "role";
    return `role-permission-receipt-${stem}.json`;
  }

  async function exportRoleReceipt(role = activeRole()) {
    if (!role?.id) {
      setStatus("offline", "请先从角色台账选择一个角色。");
      return;
    }
    await downloadFile(
      `/api/admin/roles/${encodeURIComponent(role.id)}/permission-receipt.json`,
      roleReceiptFilename(role),
      {
        busy: "正在导出角色权限配置回执...",
        done: "角色权限配置回执已开始下载。",
        fail: "角色权限配置回执导出失败",
      },
    );
  }

  async function saveRole(event) {
    event.preventDefault();
    let body;
    try {
      const diagnostics = state.rolePreview || roleDraftDiagnostics();
      if (!roleDraftCanSave(diagnostics)) {
        state.rolePreview = diagnostics;
        renderRoleMenuPreview(diagnostics);
        console.warn("role save blocked by draft risk", diagnostics);
        setStatus("offline", "角色保存已阻止：菜单入口缺少对应权限或存在未知项。");
        return;
      }
      body = JSON.stringify(payloadFromForm());
    } catch (error) {
      setStatus("offline", error.message);
      return;
    }
    const id = $("#roleId").value.trim();
    const path = id ? `/api/admin/roles/${encodeURIComponent(id)}` : "/api/admin/roles";
    const method = id ? "PATCH" : "POST";
    setStatus("busy", "正在保存角色...");
    try {
      const saved = await api(path, { method, body });
      state.activeId = saved.id;
      closeRoleEditor();
      await loadRoles();
      await loadRoleEvents();
      await loadRoleOperationQueue();
      await refreshRoleMenu();
      renderDetail(state.roles.find((role) => String(role.id) === String(saved.id)) || saved);
      setStatus("online", "角色已保存。");
    } catch (error) {
      setStatus("offline", `角色保存失败：${error.message}`);
    }
  }

  async function deleteRole(role = activeRole()) {
    if (!role) return;
    setStatus("busy", "正在删除角色...");
    try {
      await api(`/api/admin/roles/${encodeURIComponent(role.id)}`, { method: "DELETE" });
      state.activeId = "";
      closeRoleEditor();
      closeRoleDetail();
      await loadRoles();
      await loadRoleEvents();
      await loadRoleOperationQueue();
      await refreshRoleMenu();
      setStatus("online", "角色已软删除。");
    } catch (error) {
      setStatus("offline", `角色删除失败：${error.message}`);
    }
  }

  async function restoreRole(role = activeRole()) {
    if (!role) return;
    setStatus("busy", "正在恢复角色...");
    try {
      const payload = await api(`/api/admin/roles/${encodeURIComponent(role.id)}/restore`, { method: "POST" });
      state.activeId = payload.role?.id || role.id;
      await loadRoles();
      await loadRoleEvents();
      await loadRoleOperationQueue();
      await refreshRoleMenu();
      renderDetail(state.roles.find((item) => String(item.id) === String(state.activeId)) || payload.role);
      setStatus("online", "角色已恢复。");
    } catch (error) {
      setStatus("offline", `角色恢复失败：${error.message}`);
    }
  }

  function handleRowAction(event) {
    const roleButton = event.target.closest("[data-role-action]");
    if (roleButton) {
      event.preventDefault();
      event.stopPropagation();
      if (roleButton.disabled) return true;
      const row = roleButton.closest("tr[data-id]");
      const role = state.roles.find((item) => String(item.id) === String(row?.dataset.id)) || null;
      if (!role) return true;
      state.activeId = role.id;
      if (roleButton.dataset.roleAction === "restore") {
        restoreRole(role);
      }
      if (roleButton.dataset.roleAction === "receipt") {
        exportRoleReceipt(role);
      }
      return true;
    }
    const button = event.target.closest("[data-row-action]");
    if (!button) return false;
    event.stopPropagation();
    if (button.disabled) return true;
    const row = button.closest("tr[data-id]");
    const role = state.roles.find((item) => String(item.id) === String(row?.dataset.id)) || null;
    if (!role) return true;
    state.activeId = role.id;
    const action = button.dataset.rowAction;
    if (action === "view") {
      renderDetail(role);
    } else if (action === "edit") {
      openRoleEditor("edit", role);
      renderRows();
    } else if (action === "delete") {
      deleteRole(role);
    }
    return true;
  }

  function handleRoleReceiptSummaryAction(event) {
    const button = event.target.closest("[data-receipt-action]");
    if (!button) return false;
    event.preventDefault();
    event.stopPropagation();
    if (button.disabled) return true;
    const action = button.dataset.receiptAction;
    const role = activeRole();
    if (action === "role-permission") {
      exportRoleReceipt(role);
    }
    return true;
  }

  function initialize() {
    initShell();
    const params = new URLSearchParams(window.location.search);
    if (params.get("roleCode") && $("#roleKeyword")) {
      $("#roleKeyword").value = params.get("roleCode");
    }
    pager = createLedgerPager({ anchor: $("#roleRows").closest(".table-wrap"), onPageChange: loadRoles });
    loadPermissionCatalog();
    $("#refreshRoleOperationQueue")?.addEventListener("click", loadRoleOperationQueue);
    $("#roleOperationQueueRows")?.addEventListener("click", handleRoleOperationQueueAction);
    $("#reloadRoles").addEventListener("click", loadRoles);
    $("#newRole").addEventListener("click", () => openRoleEditor("create"));
    $("#roleForm").addEventListener("submit", saveRole);
    $("#menuModuleChecklist").addEventListener("change", (event) => {
      syncModuleBasePermissionFromMenu(event);
      syncRoleSelectionsToFields();
    });
    $("#permissionChecklist").addEventListener("click", (event) => {
      if (handleModulePermissionBulkAction(event)) return;
    });
    $("#permissionChecklist").addEventListener("change", syncRoleSelectionsToFields);
    $("#menuModules").addEventListener("input", syncRoleSelectionsFromFields);
    $("#permissions").addEventListener("input", syncRoleSelectionsFromFields);
    $("#rolePresetSelect")?.addEventListener("change", renderRolePresetSummary);
    $("#applyRolePreset")?.addEventListener("click", applyRolePreset);
    $("#roleClosureGuides")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-closure-action]");
      if (!button) return;
      event.preventDefault();
      if (button.dataset.closureAction === "apply") {
        applyPermissionClosure(button.dataset.closureKey || "");
      } else if (button.dataset.closureAction === "export") {
        exportPermissionClosurePackage();
      }
    });
    $("#dataScopeAreas").addEventListener("input", syncDataScopesToJson);
    $("#dataScopeProjects").addEventListener("input", syncDataScopesToJson);
    $("#dataScopeTowns").addEventListener("input", syncDataScopesToJson);
    $("#dataScopeVillages").addEventListener("input", syncDataScopesToJson);
    $("#dataScopeBlockCodes").addEventListener("input", syncDataScopesToJson);
    $("#dataScopes").addEventListener("change", syncDataScopesFromJson);
    $("#cancelRoleEdit").addEventListener("click", closeRoleEditor);
    $("#closeRoleDetail").addEventListener("click", closeRoleDetail);
    $("#exportRoleReceipt")?.addEventListener("click", () => exportRoleReceipt(activeRole()));
    $("#rolePermissionReceiptSummary")?.addEventListener("click", handleRoleReceiptSummaryAction);
    $("#deleteRole").addEventListener("click", () => deleteRole(activeRole()));
    $("#refreshPermissionCatalogHealth")?.addEventListener("click", loadPermissionCatalog);
    $("#exportPermissionCatalog")?.setAttribute("data-permission", ROLE_EVENT_EXPORT_PERMISSION);
    $("#exportPermissionCatalog")?.addEventListener("click", exportPermissionCatalog);
    $("#exportRoleEvents")?.setAttribute("data-permission", ROLE_EVENT_EXPORT_PERMISSION);
    $("#refreshRoleEvents")?.addEventListener("click", loadRoleEvents);
    $("#exportRoleEvents")?.addEventListener("click", exportRoleEvents);
    $("#roleEventActionFilter")?.addEventListener("input", () => window.setTimeout(loadRoleEvents, 180));
    $("#roleEventRoleFilter")?.addEventListener("input", () => window.setTimeout(loadRoleEvents, 180));
    $("#roleEventKeyword")?.addEventListener("input", () => window.setTimeout(loadRoleEvents, 180));
    ["#roleStatusFilter", "#permissionFilter", "#menuModuleFilter"].forEach((selector) => {
      $(selector).addEventListener("change", reloadRolesFromFirstPage);
    });
    ["#permissionFilter", "#menuModuleFilter"].forEach((selector) => {
      $(selector).addEventListener("input", () => {
        applyCatalogChecklistFilters();
        window.clearTimeout(roleFilterTimer);
        roleFilterTimer = window.setTimeout(reloadRolesFromFirstPage, 180);
      });
    });
    $("#includeDeletedRoles").addEventListener("change", reloadRolesFromFirstPage);
    $("#roleKeyword").addEventListener("input", () => {
      window.clearTimeout(roleFilterTimer);
      roleFilterTimer = window.setTimeout(reloadRolesFromFirstPage, 180);
    });
    $("#roleRows").addEventListener("click", (event) => {
      if (handleRowAction(event)) return;
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      state.activeId = row.dataset.id;
      renderDetail(activeRole());
    });
    loadRoles();
    loadRoleEvents();
    loadRoleOperationQueue();
  }

  initialize();
})();
