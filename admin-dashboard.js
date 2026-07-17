(() => {
  const { $, api, apiBase, buildHeaders, escapeHtml, formatDateTime, initShell, setStatus } = AdminCommon;
  const state = {
    workflowSummary: {
      imports: null,
      imagery: null,
    },
    operationQueue: null,
    imageryOperationQueue: null,
    mapLayerDashboard: null,
    roleOperationQueue: null,
    userOperationQueue: null,
  };

  async function fetchDeploymentHealth() {
    const response = await fetch(`${apiBase()}/api/health`, {
      headers: buildHeaders(),
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { ok: false, error: await response.text() };
    payload.httpStatus = response.status;
    return payload;
  }

  async function loadMetricTotal(path) {
    try {
      const payload = await api(path);
      return Number(payload.total ?? 0);
    } catch (error) {
      return 0;
    }
  }

  async function loadQueueSource(path, mapItems) {
    try {
      const payload = await api(path);
      return mapItems(payload);
    } catch (error) {
      return [];
    }
  }

  async function loadQueuePayload(path) {
    try {
      return await api(path);
    } catch (error) {
      return null;
    }
  }

  function queueLink(href, label) {
    return `<a class="trace-link" href="${escapeHtml(href)}">${escapeHtml(label)}</a>`;
  }

  function payloadItems(payload) {
    return Array.isArray(payload?.items) ? payload.items : [];
  }

  function activeLedgerItems(payload) {
    return payloadItems(payload).filter((item) => !item.deletedAt && item.status !== "deleted");
  }

  function builtInRoleCodes() {
    return new Set(["admin", "operator", "gis-admin"]);
  }

  function roleCoverageQueueItems(rolesPayload, catalogPayload) {
    const roles = activeLedgerItems(rolesPayload);
    const menuModules = Array.isArray(catalogPayload?.menuModules) ? catalogPayload.menuModules : [];
    const configuredModules = new Set();
    roles.forEach((role) => {
      (role.menuModules || []).forEach((moduleKey) => {
        if (moduleKey) configuredModules.add(String(moduleKey));
      });
    });

    if (!roles.length) {
      return [
        {
          kind: "权限配置",
          kindClass: "missing",
          title: "尚未创建正式角色",
          meta: "需要先配置菜单权限和接口权限，再分配给用户",
          status: "待配置",
          subStatus: "0 个角色",
          updatedAt: "",
          href: "admin-roles.html",
          linkLabel: "配置角色",
        },
      ];
    }

    const uncoveredModules = menuModules.filter((module) => {
      const key = String(module.key || "");
      return key && key !== "overview" && !configuredModules.has(key);
    });
    const emptyRoles = roles.filter(
      (role) => !(role.permissions || []).length && !(role.menuModules || []).length,
    );
    const rows = [];
    if (uncoveredModules.length) {
      rows.push({
        kind: "权限配置",
        kindClass: "review",
        title: `${uncoveredModules.length} 个菜单未纳入任何角色`,
        meta: uncoveredModules
          .slice(0, 4)
          .map((module) => module.label || module.key)
          .join("、"),
        status: "待覆盖",
        subStatus: `${roles.length} 个角色`,
        updatedAt: roles[0]?.updatedAt || "",
        href: "admin-roles.html",
        linkLabel: "查看角色",
      });
    }
    if (emptyRoles.length) {
      rows.push({
        kind: "权限配置",
        kindClass: "missing",
        title: `${emptyRoles.length} 个角色没有菜单或权限`,
        meta: emptyRoles
          .slice(0, 4)
          .map((role) => role.roleCode || role.name)
          .join("、"),
        status: "待完善",
        subStatus: "空角色",
        updatedAt: emptyRoles[0]?.updatedAt || "",
        href: "admin-roles.html",
        linkLabel: "完善角色",
      });
    }
    return rows;
  }

  function roleCoversPermissionClosure(role, closure) {
    const roleMenus = new Set((role.menuModules || []).map((moduleKey) => String(moduleKey)));
    const rolePermissions = new Set((role.permissions || []).map((permission) => String(permission)));
    const closureMenus = Array.isArray(closure.menuModules) ? closure.menuModules : [];
    const closurePermissions = Array.isArray(closure.permissions) ? closure.permissions : [];
    return (
      closureMenus.every((moduleKey) => roleMenus.has(String(moduleKey))) &&
      closurePermissions.every((permission) => rolePermissions.has(String(permission)))
    );
  }

  function permissionClosureQueueItems(rolesPayload, catalogPayload) {
    const roles = activeLedgerItems(rolesPayload);
    const closures = Array.isArray(catalogPayload?.permissionClosures) ? catalogPayload.permissionClosures : [];
    return closures
      .filter((closure) => !roles.some((role) => roleCoversPermissionClosure(role, closure)))
      .map((closure) => {
        const menuCount = Array.isArray(closure.menuModules) ? closure.menuModules.length : 0;
        const permissionCount = Array.isArray(closure.permissions) ? closure.permissions.length : 0;
        return {
          kind: "闭环权限包",
          kindClass: "review",
          title: closure.label || closure.key || "待配置闭环权限包",
          meta: `${menuCount} 个菜单 / ${permissionCount} 个权限`,
          status: "待配置",
          subStatus: closure.preview?.riskLevel || closure.key || "",
          updatedAt: "",
          href: "admin-roles.html#roleClosureGuides",
          linkLabel: "配置权限包",
        };
      });
  }

  function userRoleQueueItems(usersPayload, rolesPayload) {
    const users = activeLedgerItems(usersPayload);
    const roleCodes = new Set(activeLedgerItems(rolesPayload).map((role) => String(role.roleCode || "")));
    builtInRoleCodes().forEach((roleCode) => roleCodes.add(roleCode));
    const usersWithoutRoles = users.filter((user) => !(user.roles || []).length);
    const usersWithUnknownRoles = users.filter((user) =>
      (user.roles || []).some((roleCode) => !roleCodes.has(String(roleCode || ""))),
    );
    const rows = [];
    if (!users.length) {
      rows.push({
        kind: "账号配置",
        kindClass: "review",
        title: "尚未创建后台用户账号",
        meta: "需要将岗位人员绑定到角色和数据范围",
        status: "待开通",
        subStatus: "0 个账号",
        updatedAt: "",
        href: "admin-users.html",
        linkLabel: "配置账号",
      });
    }
    if (usersWithoutRoles.length) {
      rows.push({
        kind: "账号配置",
        kindClass: "missing",
        title: `${usersWithoutRoles.length} 个账号未绑定角色`,
        meta: usersWithoutRoles
          .slice(0, 4)
          .map((user) => user.displayName || user.username)
          .join("、"),
        status: "待授权",
        subStatus: "缺少角色",
        updatedAt: usersWithoutRoles[0]?.updatedAt || "",
        href: "admin-users.html",
        linkLabel: "分配角色",
      });
    }
    if (usersWithUnknownRoles.length) {
      rows.push({
        kind: "账号配置",
        kindClass: "review",
        title: `${usersWithUnknownRoles.length} 个账号引用了未知角色`,
        meta: usersWithUnknownRoles
          .slice(0, 4)
          .map((user) => user.displayName || user.username)
          .join("、"),
        status: "待核验",
        subStatus: "角色不存在",
        updatedAt: usersWithUnknownRoles[0]?.updatedAt || "",
        href: "admin-users.html",
        linkLabel: "核验账号",
      });
    }
    return rows;
  }

  function renderWorkflowSummaryCards(cards) {
    if (!cards.length) {
      return '<article class="workflow-summary-card"><span>暂无待办</span><strong>0</strong><small>成果入库与影像管理暂无后台待办</small></article>';
    }
    return cards
      .map((card) => {
        const tone = card.tone ? ` tone-${card.tone}` : "";
        const href = card.href || "#";
        return `
          <a class="workflow-summary-card${tone}" href="${escapeHtml(href)}">
            <span>${escapeHtml(card.label || card.key || "-")}</span>
            <strong>${escapeHtml(card.value ?? 0)}</strong>
            <small>${escapeHtml(card.source || card.key || "")}</small>
          </a>
        `;
      })
      .join("");
  }

  function workflowSummaryCards(source, sourceLabel, href) {
    const cards = Array.isArray(source?.cards) ? source.cards : [];
    return cards.map((card) => ({
      ...card,
      href: card.href || href,
      source: card.source || sourceLabel,
    }));
  }

  function renderAdminWorkflowSummary() {
    const target = $("#adminWorkflowSummary");
    if (!target) return;
    const cards = [
      ...workflowSummaryCards(state.workflowSummary.imports, "成果入库", "admin-imports.html"),
      ...workflowSummaryCards(state.workflowSummary.imagery, "影像管理", "admin-imagery.html"),
    ];
    target.innerHTML = renderWorkflowSummaryCards(cards);
  }

  async function loadWorkflowSummarySource(path, sourceLabel, href) {
    try {
      return await api(path);
    } catch (error) {
      return {
        cards: [
          {
            key: `${sourceLabel} summary error`,
            label: `${sourceLabel}摘要加载失败`,
            value: "!",
            tone: "danger",
            source: error.message,
            href,
          },
        ],
      };
    }
  }

  async function loadAdminWorkflowSummary() {
    const imports = await loadWorkflowSummarySource(
      "/api/imports/forest-blocks/workflow-summary",
      "成果入库",
      "admin-imports.html",
    );
    const imagery = await loadWorkflowSummarySource(
      "/api/scenes/workflow-summary",
      "影像管理",
      "admin-imagery.html",
    );
    state.workflowSummary = { imports, imagery };
    renderAdminWorkflowSummary();
  }

  function workQueueStatusLabel(item) {
    return [item.status, item.subStatus].filter(Boolean).join(" / ") || "-";
  }

  function renderWorkQueueRows(rows) {
    const body = $("#workQueueRows");
    if (!body) return;
    if (!rows.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="5">暂无待处理的数据、影像或权限事项</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map(
        (item) => `
          <tr>
            <td><span class="status-pill ${escapeHtml(item.kindClass || "")}">${escapeHtml(item.kind)}</span></td>
            <td><div class="cell-stack"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.meta || "-")}</small></div></td>
            <td>${escapeHtml(workQueueStatusLabel(item))}</td>
            <td>${escapeHtml(formatDateTime(item.updatedAt))}</td>
            <td>${queueLink(item.href, item.linkLabel || "查看")}</td>
          </tr>
        `,
      )
      .join("");
  }

  function deliveryPackageRows(payload, kindClass, linkLabel) {
    return payloadItems(payload).map((deliveryPackage) => ({
      kind: "交付包",
      kindClass,
      title: deliveryPackage.fileName || deliveryPackage.batchId || "待处理交付包",
      meta: [
        deliveryPackage.batchId,
        `${deliveryPackage.linkedBlockCount || 0} 个林班`,
        `${deliveryPackage.pendingSceneCount || 0} 个待交付影像`,
      ]
        .filter(Boolean)
        .join(" / "),
      status: deliveryPackage.packageStatus || "pending",
      subStatus: deliveryPackage.deliveryStatus || "",
      updatedAt: deliveryPackage.updatedAt,
      href:
        deliveryPackage.adminHref ||
        `admin-imports.html?deliveryPackageStatus=${encodeURIComponent(deliveryPackage.packageStatus || "")}&batchId=${encodeURIComponent(deliveryPackage.batchId || "")}`,
      linkLabel,
    }));
  }

  function operationQueueKindClass(lane) {
    const key = String(lane?.key || "");
    const tone = String(lane?.tone || "");
    if (key === "blocked" || tone === "danger") return "missing";
    if (key === "ready" || tone === "ready") return "complete";
    if (tone === "review") return "review";
    return "partial";
  }

  function operationQueueRows(payload) {
    const lanes = payloadItems(payload);
    return lanes.flatMap((lane) => {
      const laneItems = Array.isArray(lane.items) ? lane.items : [];
      return laneItems.map((item) => {
        const batchId = item.batchId || "";
        return {
          kind: "成果闭环",
          kindClass: operationQueueKindClass(lane),
          title: item.fileName || batchId || lane.label || "待处理闭环事项",
          meta: [
            lane.label || item.packageStatus,
            batchId,
            `${item.linkedBlockCount || 0} 个林班`,
            `${item.linkedSceneCount || 0} 景影像`,
            `${item.publishedLayerCount || 0} 个图层`,
          ]
            .filter(Boolean)
            .join(" / "),
          status: lane.label || item.packageStatus || "",
          subStatus: [item.deliveryStatus, item.qualityStatus].filter(Boolean).join(" / "),
          updatedAt: item.updatedAt,
          href:
            item.adminHref ||
            lane.href ||
            `admin-imports.html?deliveryPackageStatus=${encodeURIComponent(lane.key || "")}&batchId=${encodeURIComponent(batchId)}`,
          linkLabel: lane.primaryActionLabel || "处理闭环",
        };
      });
    });
  }

  function operationQueueSummaryTotal(payload) {
    return Number(payload?.summary?.operationQueueTotal ?? 0);
  }

  function imageryOperationQueueSummaryTotal(payload) {
    return Number(payload?.summary?.operationQueueTotal ?? 0);
  }

  function roleOperationQueueSummaryTotal(payload) {
    return Number(payload?.summary?.operationQueueTotal ?? 0);
  }

  function userOperationQueueSummaryTotal(payload) {
    return Number(payload?.summary?.operationQueueTotal ?? 0);
  }

  function roleOperationQueueKindClass(lane) {
    const key = String(lane?.key || "");
    const tone = String(lane?.tone || "");
    if (key === "blocked_roles" || tone === "danger") return "missing";
    if (key === "ready_roles" || tone === "ready") return "complete";
    if (key === "review_roles" || tone === "warning" || tone === "review") return "review";
    return "partial";
  }

  function roleOperationQueueRows(payload) {
    const lanes = payloadItems(payload);
    return lanes.flatMap((lane) => {
      const laneItems = Array.isArray(lane.items) ? lane.items : [];
      return laneItems.map((item) => ({
        kind: "权限角色",
        kindClass: roleOperationQueueKindClass(lane),
        title: item.name || item.roleCode || lane.label || "待处理角色权限事项",
        meta: [lane.label || lane.key, item.roleCode, item.summary].filter(Boolean).join(" / "),
        status: lane.label || item.riskLevel || "",
        subStatus: [
          item.requiredPermission,
          item.blockedMenuModuleCount ? `${item.blockedMenuModuleCount} 个入口阻断` : "",
          item.permissionDependencyIssueCount ? `${item.permissionDependencyIssueCount} 个依赖缺口` : "",
        ]
          .filter(Boolean)
          .join(" / "),
        updatedAt: item.updatedAt,
        href: item.adminHref || `admin-roles.html?roleCode=${encodeURIComponent(item.roleCode || "")}`,
        linkLabel: lane.primaryActionLabel || "处理角色",
      }));
    });
  }

  function userOperationQueueKindClass(lane) {
    const key = String(lane?.key || "");
    const tone = String(lane?.tone || "");
    if (key === "blocked_users" || tone === "danger") return "missing";
    if (key === "ready_users" || tone === "ready") return "complete";
    if (key === "review_users" || tone === "warning" || tone === "review") return "review";
    return "partial";
  }

  function userOperationQueueRows(payload) {
    const lanes = payloadItems(payload);
    return lanes.flatMap((lane) => {
      const laneItems = Array.isArray(lane.items) ? lane.items : [];
      return laneItems.map((item) => ({
        kind: "账号配置",
        kindClass: userOperationQueueKindClass(lane),
        title: item.displayName || item.username || lane.label || "待处理账号授权事项",
        meta: [lane.label || lane.key, item.username, item.summary].filter(Boolean).join(" / "),
        status: lane.label || item.riskLevel || "",
        subStatus: [
          item.requiredPermission,
          item.unknownRoleCount ? `${item.unknownRoleCount} 个未知角色` : "",
          item.invalidRoleCount ? `${item.invalidRoleCount} 个失效角色` : "",
          item.dataScopeValueCount === 0 ? "未配置数据范围" : "",
        ]
          .filter(Boolean)
          .join(" / "),
        updatedAt: item.updatedAt,
        href: item.adminHref || `admin-users.html?username=${encodeURIComponent(item.username || "")}`,
        linkLabel: lane.primaryActionLabel || "处理账号",
      }));
    });
  }

  function imageryOperationQueueKindClass(lane) {
    const key = String(lane?.key || "");
    const tone = String(lane?.tone || "");
    if (key === "failed_tasks" || key === "quality_issues" || tone === "danger") return "missing";
    if (key === "ready" || tone === "ready") return "complete";
    if (key === "awaiting_delivery" || tone === "review") return "review";
    return "partial";
  }

  function imageryOperationQueueRows(payload) {
    const lanes = payloadItems(payload);
    return lanes.flatMap((lane) => {
      const laneItems = Array.isArray(lane.items) ? lane.items : [];
      return laneItems.map((item) => {
        const sceneId = item.sceneId || "";
        const taskId = item.taskId || "";
        const issueId = item.issueId || "";
        const href =
          item.adminHref ||
          (issueId
            ? `admin-imagery.html?sceneId=${encodeURIComponent(sceneId)}&imageryIssueId=${encodeURIComponent(issueId)}`
            : taskId
              ? `admin-imagery.html?taskId=${encodeURIComponent(taskId)}`
              : `admin-imagery.html?sceneId=${encodeURIComponent(sceneId)}`);
        return {
          kind: "影像闭环",
          kindClass: imageryOperationQueueKindClass(lane),
          title: item.name || item.sceneName || item.taskName || item.fileName || issueId || taskId || sceneId || lane.label || "待处理影像事项",
          meta: [lane.label || lane.key, sceneId, taskId, issueId].filter(Boolean).join(" / "),
          status: lane.label || item.status || "",
          subStatus: [item.deliveryStatus, item.severity, item.message].filter(Boolean).join(" / "),
          updatedAt: item.updatedAt,
          href,
          linkLabel: lane.primaryActionLabel || "处理影像",
        };
      });
    });
  }

  function mapLayerPublicationQueueTotal(payload) {
    return Number(payload?.publicationSummary?.publicationQueueTotal ?? 0);
  }

  function mapLayerPublicationKindClass(lane) {
    const key = String(lane?.key || "");
    const tone = String(lane?.tone || "");
    if (key === "blocked" || tone === "danger") return "missing";
    if (key === "receipt_ready" || tone === "ready") return "complete";
    if (key === "needs_review" || tone === "review") return "review";
    return "partial";
  }

  function mapLayerPublicationRows(payload) {
    const lanes = Array.isArray(payload?.publicationQueue) ? payload.publicationQueue : [];
    return lanes.flatMap((lane) => {
      const laneItems = Array.isArray(lane.items) ? lane.items : [];
      return laneItems.map((item) => ({
        kind: "图层发布",
        kindClass: mapLayerPublicationKindClass(lane),
        title: item.name || item.recordCode || lane.label || "待处理图层发布事项",
        meta: [
          lane.label || lane.key,
          item.recordCode,
          item.sourceType,
          `${Array.isArray(item.linkedBlockCodes) ? item.linkedBlockCodes.length : 0} 个林班`,
        ]
          .filter(Boolean)
          .join(" / "),
        status: lane.label || item.status || "",
        subStatus: item.publishRiskStatus || "",
        updatedAt: item.updatedAt,
        href: item.adminHref || `admin-map-layers.html?layerCode=${encodeURIComponent(item.recordCode || item.id || "")}`,
        linkLabel: lane.primaryActionLabel || "处理图层",
      }));
    });
  }

  async function loadPermissionQueue() {
    const catalogPayload = await loadQueuePayload("/api/admin/permission-catalog");
    const rolesPayload = await loadQueuePayload("/api/admin/roles?limit=1000");
    if (!catalogPayload && !rolesPayload) {
      return [];
    }
    return [
      ...roleCoverageQueueItems(rolesPayload || { items: [] }, catalogPayload || { menuModules: [] }),
      ...permissionClosureQueueItems(rolesPayload || { items: [] }, catalogPayload || { permissionClosures: [] }),
    ];
  }

  async function loadWorkQueue() {
    state.operationQueue = await loadQueuePayload("/api/imports/forest-blocks/operation-queue?limit=3");
    state.imageryOperationQueue = await loadQueuePayload("/api/scenes/operation-queue?limit=3");
    state.mapLayerDashboard = await loadQueuePayload("/api/map-layers/dashboard");
    state.roleOperationQueue = await loadQueuePayload("/api/admin/roles/operation-queue?limit=3");
    state.userOperationQueue = await loadQueuePayload("/api/admin/users/operation-queue?limit=3");
    const operationQueueTotal =
      operationQueueSummaryTotal(state.operationQueue) +
      imageryOperationQueueSummaryTotal(state.imageryOperationQueue) +
      mapLayerPublicationQueueTotal(state.mapLayerDashboard) +
      roleOperationQueueSummaryTotal(state.roleOperationQueue) +
      userOperationQueueSummaryTotal(state.userOperationQueue);
    $("#metricOperationQueue").textContent = String(operationQueueTotal);
    const pendingImports = await loadQueueSource("/api/imports/forest-blocks/batches?reviewStatus=pending&limit=5", (payload) =>
      (payload.items || []).map((batch) => ({
        kind: "入库审核",
        kindClass: "review",
        title: batch.fileName || batch.id || "待审核批次",
        meta: batch.id || "",
        status: batch.reviewStatus || "pending",
        subStatus: batch.qualityStatus || "",
        updatedAt: batch.completedAt || batch.updatedAt || batch.createdAt,
        href: `admin-imports.html?batchId=${encodeURIComponent(batch.id || "")}`,
        linkLabel: "查看批次",
      })),
    );
    const importIssues = await loadQueueSource("/api/imports/forest-blocks/quality-issues?status=open&limit=5", (payload) =>
      (payload.items || []).map((issue) => ({
        kind: "入库质检",
        kindClass: "missing",
        title: issue.message || issue.issueType || "待处理质检问题",
        meta: [issue.batchId, issue.issueKey].filter(Boolean).join(" / "),
        status: issue.status || "open",
        subStatus: issue.severity || "",
        updatedAt: issue.updatedAt || issue.createdAt || issue.handledAt,
        href: issue.issueId
          ? `admin-imports.html?batchId=${encodeURIComponent(issue.batchId || "")}&qualityIssueId=${encodeURIComponent(issue.issueId)}`
          : `admin-imports.html?batchId=${encodeURIComponent(issue.batchId || "")}`,
        linkLabel: "处理问题",
      })),
    );
    const permissionItems = await loadPermissionQueue();
    const rows = [
      ...operationQueueRows(state.operationQueue || { items: [] }),
      ...imageryOperationQueueRows(state.imageryOperationQueue || { items: [] }),
      ...mapLayerPublicationRows(state.mapLayerDashboard || { publicationQueue: [] }),
      ...roleOperationQueueRows(state.roleOperationQueue || { items: [] }),
      ...userOperationQueueRows(state.userOperationQueue || { items: [] }),
      ...pendingImports,
      ...importIssues,
      ...permissionItems,
    ]
      .sort((left, right) => String(right.updatedAt || "").localeCompare(String(left.updatedAt || "")))
      .slice(0, 20);
    renderWorkQueueRows(rows);
  }

  function statusLabel(healthy) {
    return healthy ? "就绪" : "待处理";
  }

  function statusClass(healthy) {
    return healthy ? "complete" : "missing";
  }

  function renderDeploymentRow(item) {
    return `
      <tr>
        <td><strong>${escapeHtml(item.name)}</strong></td>
        <td><span class="status-pill ${statusClass(item.healthy)}">${escapeHtml(statusLabel(item.healthy))}</span></td>
        <td>${escapeHtml(item.config || "-")}</td>
        <td>${escapeHtml(item.detail || "-")}</td>
      </tr>
    `;
  }

  function renderDeploymentHealth(payload) {
    const deployment = payload?.deployment || {};
    const platform = deployment.database.platform || {};
    const remoteSensingCatalog = deployment.database.remoteSensingCatalog || {};
    deployment.smartBamboo = deployment.smartBamboo || {};
    const smartBamboo = deployment.smartBamboo;
    const storageBackend = deployment.smartBamboo.storageBackend || "-";
    const smartBambooData = smartBamboo.jsonData || {};
    const dataDir = smartBambooData.dataDir || {};
    const imagery = deployment.imagery || {};
    const imageryCatalog = deployment.imagery.catalog || {};
    const imageryImportDirs = Array.isArray(imagery.importDirs) ? imagery.importDirs : [];
    const importsReady = imageryImportDirs.length ? imageryImportDirs.every((item) => item.exists && item.writable) : false;
    const rows = [
      {
        name: "平台数据库",
        healthy: Boolean(platform.reachable && platform.schemaReady),
        config: `${platform.backend || "json"} / ${storageBackend}`,
        detail: platform.error || `缺失表：${(platform.missingTables || []).join(", ") || "无"}`,
      },
      {
        name: "影像目录库",
        healthy: Boolean(remoteSensingCatalog.reachable && remoteSensingCatalog.schemaReady),
        config: remoteSensingCatalog.backend || "-",
        detail: remoteSensingCatalog.error || `缺失表：${(remoteSensingCatalog.missingTables || []).join(", ") || "无"}`,
      },
      {
        name: "数据目录",
        healthy: Boolean(dataDir.exists && dataDir.writable),
        config: dataDir.path || "-",
        detail: dataDir.exists ? "目录存在，可写状态已检查" : "目录不存在",
      },
      {
        name: "影像入库目录",
        healthy: importsReady,
        config: `${imageryImportDirs.length} 个目录`,
        detail: importsReady ? "入库目录可用" : "存在未创建或不可写目录",
      },
    ];

    $("#metricHealth").textContent = statusLabel(Boolean(payload?.ok));
    $("#metricStorage").textContent = storageBackend;
    $("#metricCatalog").textContent = remoteSensingCatalog.backend || imageryCatalog.key || "-";
    const body = $("#deploymentHealthRows");
    if (body) {
      body.innerHTML = rows.map(renderDeploymentRow).join("");
    }
  }

  async function loadDashboard() {
    setStatus("busy", "正在读取后台模块概览...");
    try {
      const blocks = await loadMetricTotal("/api/forest-blocks?limit=1");
      const rights = await loadMetricTotal("/api/forest-rights?limit=1");
      const layers = await loadMetricTotal("/api/map-layers?limit=1");
      const imports = await loadMetricTotal("/api/imports/forest-blocks/batches?limit=1");
      const scenes = await loadMetricTotal("/api/scenes?limit=1");
      const roles = await loadMetricTotal("/api/admin/roles?limit=1");
      const users = await loadMetricTotal("/api/admin/users?limit=1");
      const health = await fetchDeploymentHealth();
      $("#metricBlocks").textContent = String(blocks);
      $("#metricRights").textContent = String(rights);
      $("#metricLayers").textContent = String(layers);
      $("#metricImports").textContent = String(imports);
      $("#metricScenes").textContent = String(scenes);
      $("#metricRoles").textContent = String(roles);
      $("#metricUsers").textContent = String(users);
      renderDeploymentHealth(health);
      await loadAdminWorkflowSummary();
      await loadWorkQueue();
      setStatus("online", "后台模块概览已更新。");
    } catch (error) {
      setStatus("offline", `后台概览读取失败：${error.message}`);
    }
  }

  function initialize() {
    initShell();
    $("#connectApi")?.addEventListener("click", loadDashboard);
    $("#refreshDeploymentHealth")?.addEventListener("click", loadDashboard);
    $("#refreshAdminWorkflowSummary")?.addEventListener("click", loadAdminWorkflowSummary);
    $("#refreshWorkQueue")?.addEventListener("click", loadWorkQueue);
    loadDashboard();
  }

  initialize();
})();
