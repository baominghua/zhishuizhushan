(() => {
  const {
    $,
    api,
    applyActionPermissions,
    buildHeaders,
    createLedgerPager,
    escapeHtml,
    formatDateTime,
    initShell,
    query,
    setStatus,
    splitValues,
    stringifyPretty,
  } = AdminCommon;
  const PAGE_PERMISSION = "imports.forestBlocks.view";
  const IMPORT_CREATE_PERMISSION = "imports.forestBlocks.create";
  const IMPORT_REVIEW_PERMISSION = "imports.forestBlocks.review";
  const IMPORT_QUALITY_PERMISSION = "imports.forestBlocks.quality";
  const IMPORT_ACCEPTANCE_PERMISSION = "imports.forestBlocks.acceptance";
  const IMPORT_ROLLBACK_PERMISSION = "imports.forestBlocks.rollback";
  const IMPORT_DELETE_PERMISSION = "imports.forestBlocks.delete";
  const IMPORT_RESTORE_PERMISSION = "imports.forestBlocks.restore";
  const IMPORT_EXPORT_PERMISSION = "imports.forestBlocks.export";
  const IMPORT_SCENE_LAYER_LINK_PERMISSION = "imports.sceneLayers.link";
  const IMPORT_MAP_LAYER_REQUIRED_PERMISSION = "map.layers.publish";
  const IMPORT_MAP_LAYER_UPSERT_PERMISSIONS = "map.layers.create map.layers.update";
  const state = {
    selectedPath: "",
    sources: [],
    batches: [],
    deliveryPackages: [],
    scenes: [],
    auditEvents: [],
    qualityIssues: [],
    workflowSummary: null,
    operationQueue: null,
    activeBatchId: "",
    activeDeliveryBatchId: "",
    activeQualityIssueId: "",
  };
  let pager;
  let batchFilterTimer;
  let initialBatchId = new URLSearchParams(window.location.search).get("batchId") || "";
  let initialDeliveryBatchId = initialBatchId;
  let initialQualityIssueId = new URLSearchParams(window.location.search).get("qualityIssueId") || "";
  let initialWorkflowQueue = new URLSearchParams(window.location.search).get("workflowQueue") || "";
  let initialQualityIssueStatus = new URLSearchParams(window.location.search).get("qualityIssueStatus") || "";
  let initialDeliveryPackageStatus = new URLSearchParams(window.location.search).get("deliveryPackageStatus") || "";
  const RESTORE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.4-6.4"></path><path d="M18 3v5h-5"></path><path d="M21 12a9 9 0 0 1-15.4 6.4"></path><path d="M6 21v-5h5"></path></svg>';
  const INVESTIGATING_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 0 1 14-5.3"></path><path d="M18 3v5h-5"></path><path d="M20 12a8 8 0 0 1-14 5.3"></path><path d="M6 21v-5h5"></path></svg>';
  const RESOLVED_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"></path></svg>';
  const IGNORED_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>';
  const RECEIPT_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6Z"></path><path d="M14 3v5h5"></path><path d="M9 13h6"></path><path d="M9 17h5"></path></svg>';
  const SCENE_RECEIPT_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="12" rx="2"></rect><path d="m7 15 3.2-3.2 2.3 2.3 2-2 2.5 2.9"></path><path d="M8 21h8"></path><path d="M12 17v4"></path></svg>';
  const REPORT_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h12v18H6Z"></path><path d="M9 8h6"></path><path d="M9 12h6"></path><path d="M9 16h4"></path></svg>';
  const ROLLBACK_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 14 4 9l5-5"></path><path d="M4 9h10a6 6 0 0 1 0 12H8"></path></svg>';

  function setCompoundPermission(selector, primaryPermission, allPermissions = "", anyPermissions = "") {
    const element = $(selector);
    if (!element) return;
    element.setAttribute("data-permission", primaryPermission);
    element.setAttribute("data-permission-all", allPermissions);
    element.setAttribute("data-permission-any", anyPermissions);
  }
  const QUALITY_STATUS_LABELS = {
    open: "\u5f85\u5904\u7406",
    investigating: "\u5904\u7406\u4e2d",
    resolved: "\u5df2\u89e3\u51b3",
    ignored: "\u5df2\u5ffd\u7565",
  };
  const BATCH_STATUS_LABELS = {
    completed: "\u5df2\u5b8c\u6210",
    deleted: "\u5df2\u5220\u9664",
    rolled_back: "\u5df2\u56de\u6eda",
    failed: "\u5931\u8d25",
    pending: "\u5904\u7406\u4e2d",
  };
  const IMPORT_AUDIT_ACTION_LABELS = {
    import: "成果入库",
    review: "批次审核",
    "link-scene-layer": "关联影像图层",
    "quality-issue-update": "质检处理",
    acceptance: "批次验收",
    "export-acceptance-receipt": "导出验收回执",
    rollback: "撤销入库",
    restore: "恢复批次",
    delete: "删除批次",
  };
  const REVIEW_STATUS_LABELS = {
    pending: "\u5f85\u5ba1\u6838",
    approved: "\u5df2\u901a\u8fc7",
    rejected: "\u5df2\u9a73\u56de",
    needs_correction: "\u9700\u4fee\u6b63",
  };
  const ACCEPTANCE_STATUS_LABELS = {
    pending: "待验收",
    accepted: "已验收",
    needs_correction: "需整改",
    rejected: "验收驳回",
  };
  const DELIVERY_PACKAGE_STATUS_LABELS = {
    ready: "可交付",
    awaiting_review: "待审核",
    awaiting_acceptance: "待验收",
    awaiting_scene_link: "待挂影像",
    awaiting_publish: "待发布",
    awaiting_delivery: "待交付",
    blocked: "阻断",
  };
  const WORKFLOW_SUMMARY_KEY_LABELS = {
    pendingReviewBatches: "审核队列",
    approvedUnlinkedBatches: "影像挂接队列",
    readyForLayerLinkBatches: "图层发布队列",
    readyDeliveryPackages: "交付队列",
    blockedQualityIssues: "质检阻断队列",
  };
  const DELIVERY_STATUS_LABELS = {
    pending: "待交付",
    partial: "部分交付",
    needs_correction: "需整改",
    rejected: "交付驳回",
    delivered: "已交付",
  };
  const DELIVERY_BLOCKING_REASON_LABELS = {
    review_not_approved: "批次未审核通过",
    acceptance_not_accepted: "批次未验收通过",
    no_linked_scene: "未挂接影像",
    quality_blocked: "质量阻断",
    publish_risk_blocked: "发布风险阻断",
    scene_missing: "影像不可见或不存在",
    scene_not_published: "影像/图层未发布",
    scene_not_delivered: "影像未交付",
  };
  const IMPORT_REVIEW_RECOMMENDATION_LABELS = {
    approved: "建议通过",
    can_publish: "可发布",
    needs_correction: "需修正",
    reject_publish: "暂缓发布",
    manual_review: "人工复核",
  };
  const BATCH_QUALITY_STATUS_LABELS = {
    pending: "\u5f85\u8bc4\u4f30",
    passed: "\u5df2\u901a\u8fc7",
    warning: "\u9700\u590d\u6838",
    blocked: "\u4e0d\u901a\u8fc7",
  };
  const PUBLISH_RISK_LABELS = {
    unknown: "\u5f85\u9884\u68c0",
    ready: "\u53ef\u53d1\u5e03",
    warning: "\u9700\u590d\u6838",
    blocked: "\u963b\u65ad",
  };
  const MAP_LAYER_SOURCE_TYPE_LABELS = {
    importBatch: "入库批次",
    imagery: "影像成果",
    manual: "手工维护",
  };
  const IMPORT_ISSUE_TYPE_LABELS = {
    import_error: "\u5bfc\u5165\u9519\u8bef",
    coverage_warning: "\u8986\u76d6\u9884\u8b66",
    missing_imported_block: "\u7f3a\u5931\u6797\u73ed",
  };
  const ISSUE_SEVERITY_LABELS = {
    blocked: "\u963b\u65ad",
    warning: "\u9884\u8b66",
    info: "\u63d0\u793a",
  };
  const AUDIT_SUMMARY_LABELS = {
    fileName: "\u6587\u4ef6",
    strategy: "\u7b56\u7565",
    totalRows: "\u603b\u884c",
    validRows: "\u6709\u6548\u884c",
    importedBlockCount: "\u5165\u5e93\u6797\u73ed",
    importedRightCount: "\u6797\u6743\u6863\u6848",
    reviewStatus: "\u5ba1\u6838",
    previousReviewStatus: "\u539f\u72b6\u6001",
    acceptanceStatus: "验收",
    previousAcceptanceStatus: "原验收状态",
    comment: "\u8bf4\u660e",
    sceneId: "\u5f71\u50cf",
    relationType: "\u5173\u7cfb",
    linkedBlockCount: "\u6302\u63a5\u6797\u73ed",
    layerRecordCode: "\u56fe\u5c42",
    qualityStatus: "\u8d28\u91cf",
    publishRiskStatus: "\u53d1\u5e03\u98ce\u9669",
    blocksSoftDeleted: "\u8f6f\u5220\u6797\u73ed",
    blocksSkipped: "\u8df3\u8fc7\u6797\u73ed",
    updatedRowsRequireManualReview: "\u9700\u590d\u6838",
    skippedRowsIgnored: "\u5ffd\u7565\u884c",
    issueId: "\u95ee\u9898",
    status: "\u72b6\u6001",
    permission: "权限",
    receiptType: "回执类型",
    restoredAt: "\u6062\u590d\u65f6\u95f4",
    deletedAt: "\u5220\u9664\u65f6\u95f4",
  };
  const AUDIT_SUMMARY_ORDER = [
    "fileName",
    "strategy",
    "totalRows",
    "validRows",
    "importedBlockCount",
    "importedRightCount",
    "reviewStatus",
    "previousReviewStatus",
    "sceneId",
    "relationType",
    "linkedBlockCount",
    "layerRecordCode",
    "qualityStatus",
    "publishRiskStatus",
    "blocksSoftDeleted",
    "blocksSkipped",
    "updatedRowsRequireManualReview",
    "skippedRowsIgnored",
    "issueId",
    "status",
    "permission",
    "receiptType",
    "comment",
    "restoredAt",
    "deletedAt",
  ];

  function formatBytes(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const index = Math.min(Math.floor(Math.log(numeric) / Math.log(1024)), units.length - 1);
    return `${(numeric / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
  }

  function activeBatch() {
    return state.batches.find((batch) => String(batch.id) === String(state.activeBatchId)) || null;
  }

  function activeDeliveryPackage() {
    return state.deliveryPackages.find((item) => String(item.batchId || "") === String(state.activeDeliveryBatchId || "")) || null;
  }

  function isDeletedBatch(batch) {
    return Boolean(batch?.deletedAt) || batch?.status === "deleted";
  }

  function batchActionButtons(batch) {
    if (isDeletedBatch(batch)) {
      return `
        <div class="row-actions" aria-label="批次操作">
          <button type="button" class="icon-button" data-row-action="view" aria-label="查看报告" title="查看报告">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>
          </button>
          <button type="button" class="icon-button" data-batch-action="restore" data-permission="${IMPORT_RESTORE_PERMISSION}" aria-label="恢复批次" title="恢复批次">${RESTORE_ICON}</button>
        </div>
      `;
    }
    return `
      <div class="row-actions row-actions-extra-wide" aria-label="批次操作">
        <button type="button" class="icon-button" data-row-action="view" aria-label="查看报告" title="查看报告">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>
        </button>
        <button type="button" class="icon-button" data-row-action="edit" data-permission-any="${IMPORT_REVIEW_PERMISSION} ${IMPORT_ACCEPTANCE_PERMISSION} ${IMPORT_SCENE_LAYER_LINK_PERMISSION}" aria-label="处理批次" title="处理批次">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 20 9-9-4-4-9 9-2 6Z"></path><path d="m15 8 1-1a2.8 2.8 0 0 1 4 4l-1 1"></path></svg>
        </button>
        <button type="button" class="icon-button" data-batch-action="report" data-permission="${IMPORT_EXPORT_PERMISSION}" aria-label="导出报告" title="导出报告">${REPORT_ICON}</button>
        <button type="button" class="icon-button" data-batch-action="receipt" data-permission="${IMPORT_EXPORT_PERMISSION}" aria-label="导出验收回执" title="导出验收回执">${RECEIPT_ICON}</button>
        <button type="button" class="icon-button" data-batch-action="rollback" data-permission="${IMPORT_ROLLBACK_PERMISSION}" aria-label="撤销入库" title="撤销入库">${ROLLBACK_ICON}</button>
        <button type="button" class="icon-button danger" data-row-action="delete" data-permission="${IMPORT_DELETE_PERMISSION}" aria-label="删除批次" title="删除批次">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="m19 6-1 14H6L5 6"></path><path d="M10 11v5"></path><path d="M14 11v5"></path></svg>
        </button>
      </div>
    `;
  }

  function batchQuery() {
    const batchStatus = $("#batchStatusFilter")?.value.trim() || "";
    return query({
      q: $("#batchKeyword")?.value.trim() || "",
      status: batchStatus,
      reviewStatus: $("#batchReviewStatusFilter")?.value.trim() || "",
      acceptanceStatus: $("#batchAcceptanceStatusFilter")?.value.trim() || "",
      sceneId: $("#batchSceneIdFilter")?.value.trim() || "",
      qualityStatus: $("#batchQualityStatusFilter")?.value.trim() || "",
      publishRiskStatus: $("#batchPublishRiskStatusFilter")?.value.trim() || "",
      workflowQueue: $("#batchWorkflowQueueFilter")?.value.trim() || "",
      includeDeleted: $("#includeDeletedImportBatches")?.checked || batchStatus === "deleted" ? "true" : "",
      limit: pager.limit,
      offset: pager.offset,
    });
  }

  function deliveryPackageQuery() {
    return query({
      q: $("#deliveryPackageKeyword")?.value.trim() || "",
      status: $("#deliveryPackageStatusFilter")?.value.trim() || "",
      acceptanceStatus: $("#deliveryPackageAcceptanceFilter")?.value.trim() || "",
      deliveryStatus: $("#deliveryPackageDeliveryFilter")?.value.trim() || "",
      linkedBlockCode: $("#deliveryPackageBlockFilter")?.value.trim() || "",
      limit: 200,
    });
  }

  function auditQuery() {
    return query({
      action: $("#importAuditActionFilter")?.value.trim() || "",
      batchId: $("#importAuditBatchFilter")?.value.trim() || "",
      includeDeleted: $("#includeDeletedImportAuditEvents")?.checked ? "true" : "",
      limit: 100,
    });
  }

  function qualityIssueQuery() {
    return query({
      q: $("#qualityIssueKeyword")?.value.trim() || "",
      issueType: $("#qualityIssueTypeFilter")?.value.trim() || "",
      severity: $("#qualityIssueSeverityFilter")?.value.trim() || "",
      status: $("#qualityIssueStatusFilter")?.value.trim() || "",
      batchId: $("#qualityIssueBatchFilter")?.value.trim() || "",
      includeDeleted: $("#includeDeletedQualityIssues")?.checked ? "true" : "",
      limit: 100,
    });
  }

  function qualityIssueStatusLabel(status) {
    return QUALITY_STATUS_LABELS[status] || status || QUALITY_STATUS_LABELS.open;
  }

  function displayLabel(map, value, fallback = "-") {
    const key = String(value ?? "").trim();
    if (!key) return fallback;
    return map[key] || key;
  }

  function workflowSummaryKeyLabel(key) {
    return displayLabel(WORKFLOW_SUMMARY_KEY_LABELS, key, "业务指标");
  }

  function operationQueueStatusLabel(status) {
    return displayLabel(DELIVERY_PACKAGE_STATUS_LABELS, status, "待处理");
  }

  function workflowSummaryCardHref(card = {}) {
    return card.href || "#";
  }

  function workflowSummaryCardActionLabel(card = {}) {
    return workflowSummaryCardHref(card) === "#" ? "暂无队列" : "查看队列";
  }

  function renderWorkflowSummaryCards(summary) {
    const cards = Array.isArray(summary?.cards) ? summary.cards : [];
    if (!cards.length) {
      return '<article class="workflow-summary-card"><span>暂无摘要</span><strong>0</strong><small>后台暂无工作流数据</small></article>';
    }
    return cards
      .map((card) => {
        const tone = card.tone ? ` tone-${card.tone}` : "";
        const href = workflowSummaryCardHref(card);
        const actionLabel = workflowSummaryCardActionLabel(card);
        const label = card.label || card.key || "-";
        return `
          <a class="workflow-summary-card${tone}" href="${escapeHtml(href)}" aria-label="${escapeHtml(`${label}：${actionLabel}`)}">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(card.value ?? 0)}</strong>
            <small>${escapeHtml(workflowSummaryKeyLabel(card.key))}</small>
            <em class="workflow-summary-link">${escapeHtml(actionLabel)}</em>
          </a>
        `;
      })
      .join("");
  }

  function renderImportWorkflowSummary() {
    const target = $("#importWorkflowSummary");
    if (!target) return;
    target.innerHTML = renderWorkflowSummaryCards(state.workflowSummary);
  }

  async function loadImportWorkflowSummary() {
    try {
      state.workflowSummary = await api("/api/imports/forest-blocks/workflow-summary");
      renderImportWorkflowSummary();
    } catch (error) {
      const target = $("#importWorkflowSummary");
      if (target) {
        target.innerHTML = `<article class="workflow-summary-card tone-danger"><span>摘要加载失败</span><strong>!</strong><small>${escapeHtml(error.message)}</small></article>`;
      }
    }
  }

  function operationQueueToneClass(tone) {
    if (tone === "danger") return "tone-danger";
    if (tone === "ready") return "tone-ready";
    if (tone === "review") return "tone-review";
    if (tone === "warning") return "tone-warning";
    return "";
  }

  function operationQueuePillClass(status) {
    if (status === "ready") return "complete";
    if (status === "blocked") return "missing";
    if (status === "awaiting_acceptance" || status === "awaiting_delivery") return "review";
    return "partial";
  }

  function operationQueueAnyPermissions(lane = {}) {
    const permissions = [];
    (lane.requiredAnyPermissions || []).forEach((group) => {
      if (Array.isArray(group)) {
        group.forEach((permission) => permissions.push(permission));
      } else if (group) {
        permissions.push(group);
      }
    });
    return permissions.join(" ");
  }

  function operationQueueActionAttributes(lane = {}) {
    const permission = lane.requiredPermission || "";
    const allPermissions = Array.isArray(lane.requiredAllPermissions) ? lane.requiredAllPermissions.join(" ") : "";
    const anyPermissions = operationQueueAnyPermissions(lane);
    return [
      permission ? `data-permission="${escapeHtml(permission)}"` : "",
      allPermissions ? `data-permission-all="${escapeHtml(allPermissions)}"` : "",
      anyPermissions ? `data-permission-any="${escapeHtml(anyPermissions)}"` : "",
    ]
      .filter(Boolean)
      .join(" ");
  }

  function operationQueueItem(item = {}, lane = {}) {
    const batchId = item.batchId || "";
    const actionAttrs = operationQueueActionAttributes(lane);
    const reasonText = deliveryBlockingText(item.blockingReasons);
    return `
      <article class="operation-queue-row" data-operation-queue-key="${escapeHtml(lane.key || "")}" data-batch-id="${escapeHtml(batchId)}">
        <div class="cell-stack">
          <strong>${traceLink(item.adminHref || `admin-imports.html?batchId=${encodeURIComponent(batchId)}`, item.fileName || batchId || "-")}</strong>
          <small>${escapeHtml(batchId || "-")}</small>
        </div>
        <div class="operation-queue-meta">
          <span>${escapeHtml(item.linkedBlockCount ?? 0)} 林班</span>
          <span>${escapeHtml(item.linkedSceneCount ?? 0)} 影像</span>
          <span>${escapeHtml(item.publishedLayerCount ?? 0)} 图层</span>
        </div>
        <p>${escapeHtml(reasonText || "等待下一步处理")}</p>
        <button type="button" class="button-ghost" data-operation-action="open" data-operation-queue-key="${escapeHtml(lane.key || "")}" data-batch-id="${escapeHtml(batchId)}" ${actionAttrs}>
          ${escapeHtml(lane.primaryActionLabel || "打开台账")}
        </button>
      </article>
    `;
  }

  function renderImportOperationQueue() {
    const target = $("#importOperationQueueRows");
    if (!target) return;
    const lanes = Array.isArray(state.operationQueue?.items) ? state.operationQueue.items : [];
    if (!lanes.length) {
      target.innerHTML = '<article class="operation-queue-item"><div><span>暂无队列</span><strong>0</strong><small>后台暂无成果运维待办</small></div></article>';
      return;
    }
    target.innerHTML = lanes
      .map((lane) => {
        const items = Array.isArray(lane.items) ? lane.items : [];
        const itemHtml = items.length
          ? items.map((item) => operationQueueItem(item, lane)).join("")
          : '<p class="trace-empty">当前队列暂无待办批次。</p>';
        return `
          <section class="operation-queue-item ${operationQueueToneClass(lane.tone)}" data-operation-queue-key="${escapeHtml(lane.key || "")}">
            <div class="operation-queue-head">
              <div>
                <span>${escapeHtml(lane.label || lane.key || "-")}</span>
                <strong>${escapeHtml(lane.count ?? 0)}</strong>
                <small>${escapeHtml(lane.description || "")}</small>
              </div>
              <span class="status-pill ${operationQueuePillClass(lane.key)}">${escapeHtml(operationQueueStatusLabel(lane.key))}</span>
            </div>
            <div class="operation-queue-list">${itemHtml}</div>
            <a class="workflow-summary-link" href="${escapeHtml(lane.href || "#")}">查看全部</a>
          </section>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  async function loadImportOperationQueue() {
    try {
      state.operationQueue = await api("/api/imports/forest-blocks/operation-queue?limit=3");
      renderImportOperationQueue();
    } catch (error) {
      const target = $("#importOperationQueueRows");
      if (target) {
        target.innerHTML = `<article class="operation-queue-item tone-danger"><div><span>队列加载失败</span><strong>!</strong><small>${escapeHtml(error.message)}</small></div></article>`;
      }
    }
  }

  async function openOperationQueueItem(laneKey, batchId) {
    if ($("#deliveryPackageStatusFilter")) $("#deliveryPackageStatusFilter").value = laneKey || "";
    if ($("#deliveryPackageKeyword")) $("#deliveryPackageKeyword").value = batchId || "";
    if ($("#batchKeyword")) $("#batchKeyword").value = batchId || "";
    state.activeBatchId = batchId || state.activeBatchId;
    state.activeDeliveryBatchId = batchId || state.activeDeliveryBatchId;
    await loadDeliveryPackages();
    await loadImportBatches();
    $("#deliveryPackageRows")?.scrollIntoView({ block: "start", behavior: "smooth" });
    setStatus("online", "已打开对应交付包台账筛选。");
  }

  function handleOperationQueueAction(event) {
    const button = event.target.closest("[data-operation-action]");
    if (!button) return false;
    event.preventDefault();
    if (button.disabled) return true;
    const action = button.dataset.operationAction;
    if (action === "open") {
      openOperationQueueItem(button.dataset.operationQueueKey || "", button.dataset.batchId || "");
    }
    return true;
  }

  function qualityIssueStatusClass(status) {
    if (status === "resolved") return "complete";
    if (status === "investigating") return "review";
    if (status === "open") return "partial";
    return "";
  }

  function qualityIssueActions(issue) {
    const issueId = escapeHtml(issue.issueId || "");
    return `
      <div class="row-actions" aria-label="\u8d28\u68c0\u95ee\u9898\u5904\u7406">
        <button type="button" class="icon-button" data-quality-action="investigating" data-issue-id="${issueId}" data-permission="${IMPORT_QUALITY_PERMISSION}" aria-label="\u6807\u8bb0\u5904\u7406\u4e2d" title="\u6807\u8bb0\u5904\u7406\u4e2d">${INVESTIGATING_ICON}</button>
        <button type="button" class="icon-button" data-quality-action="resolved" data-issue-id="${issueId}" data-permission="${IMPORT_QUALITY_PERMISSION}" aria-label="\u6807\u8bb0\u5df2\u89e3\u51b3" title="\u6807\u8bb0\u5df2\u89e3\u51b3">${RESOLVED_ICON}</button>
        <button type="button" class="icon-button danger" data-quality-action="ignored" data-issue-id="${issueId}" data-permission="${IMPORT_QUALITY_PERMISSION}" aria-label="\u6807\u8bb0\u5df2\u5ffd\u7565" title="\u6807\u8bb0\u5df2\u5ffd\u7565">${IGNORED_ICON}</button>
      </div>
    `;
  }

  function auditSummaryValue(value) {
    if (value === null || value === undefined || value === "") return "-";
    if (Array.isArray(value)) {
      if (!value.length) return "0";
      const preview = value.slice(0, 3).map((item) => (typeof item === "object" ? stringifyPretty(item, {}) : String(item)));
      return value.length > 3 ? `${preview.join(", ")} +${value.length - 3}` : preview.join(", ");
    }
    if (typeof value === "object") return stringifyPretty(value, {});
    return String(value);
  }

  function auditSummaryPairs(summary) {
    if (!summary || typeof summary !== "object" || Array.isArray(summary)) {
      return summary ? [["summary", auditSummaryValue(summary)]] : [];
    }
    const ordered = AUDIT_SUMMARY_ORDER.filter((key) => Object.prototype.hasOwnProperty.call(summary, key));
    const remaining = Object.keys(summary).filter((key) => !ordered.includes(key));
    return ordered.concat(remaining).map((key) => [key, auditSummaryValue(summary[key])]).filter(([, value]) => value !== "-");
  }

  function renderAuditSummary(summary, options = {}) {
    const limit = options.limit || 6;
    const pairs = auditSummaryPairs(summary);
    if (!pairs.length) return '<span class="audit-summary-empty">-</span>';
    const visiblePairs = pairs.slice(0, limit);
    const hiddenCount = pairs.length - visiblePairs.length;
    const chips = visiblePairs
      .map(([key, value]) => {
        const label = AUDIT_SUMMARY_LABELS[key] || key;
        return `<span class="audit-summary-chip"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></span>`;
      })
      .join("");
    const more = hiddenCount > 0 ? `<span class="audit-summary-more">+${hiddenCount}</span>` : "";
    return `<div class="audit-summary">${chips}${more}</div>`;
  }

  function sceneQuery() {
    return query({
      q: $("#batchSceneKeyword")?.value.trim() || "",
      limit: 200,
    });
  }

  function sceneLabel(scene) {
    return [scene.name || scene.id, scene.satellite, scene.sensor, scene.capturedAt].filter(Boolean).join(" · ");
  }

  function renderBatchSceneOptions() {
    const list = $("#batchSceneOptions");
    if (!list) return;
    list.innerHTML = state.scenes
      .map((scene) => {
        const label = `${sceneLabel(scene)} · ${scene.projectId || "未分项目"} / ${scene.areaCode || "未分区域"}`;
        return `<option value="${escapeHtml(scene.id)}" label="${escapeHtml(label)}"></option>`;
      })
      .join("");
  }

  function renderBatchScenePreview(sceneId = $("#batchSceneId")?.value.trim() || "") {
    const target = $("#batchScenePreview");
    if (!target) return;
    const scene = state.scenes.find((item) => String(item.id) === String(sceneId));
    if (!sceneId) {
      target.textContent = "选择一景影像后显示目录信息。";
      return;
    }
    if (!scene) {
      target.textContent = `未在当前影像目录列表中找到 ${sceneId}，可刷新影像目录或直接提交让后端校验。`;
      return;
    }
    target.innerHTML = `
      <strong>${escapeHtml(scene.name || scene.id)}</strong>
      <span>${escapeHtml(scene.id)} · ${escapeHtml(scene.satellite || "-")} / ${escapeHtml(scene.sensor || "-")} · ${escapeHtml(scene.capturedAt || "-")}</span>
      <span>${escapeHtml(scene.projectId || "未分项目")} / ${escapeHtml(scene.areaCode || "未分区域")} · ${escapeHtml(scene.storage || scene.source || "COG")}</span>
    `;
  }

  async function loadBatchScenes(options = {}) {
    const silent = Boolean(options.silent);
    if (!silent) setStatus("busy", "正在加载影像目录...");
    try {
      const payload = await api(`/api/scenes?${sceneQuery()}`);
      state.scenes = Array.isArray(payload.scenes) ? payload.scenes : Array.isArray(payload.items) ? payload.items : [];
      renderBatchSceneOptions();
      renderBatchScenePreview();
      if (!silent) setStatus("online", `已加载 ${payload.total ?? state.scenes.length} 景影像。`);
    } catch (error) {
      if (!silent) setStatus("offline", `影像目录加载失败：${error.message}`);
    }
  }

  function renderImportBatchRows() {
    const body = $("#importBatchRows");
    if (!state.batches.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无入库批次</td></tr>';
      return;
    }
    body.innerHTML = state.batches
      .map((batch) => {
        const active = String(batch.id) === String(state.activeBatchId) ? "active" : "";
        return `
          <tr data-id="${escapeHtml(batch.id)}" class="${active}">
            <td><div class="cell-stack"><strong>${escapeHtml(batch.fileName || batch.id)}</strong><small>${escapeHtml(batch.id || "-")}</small></div></td>
            <td>${escapeHtml(batch.fileType || "-")}</td>
            <td><div class="cell-stack"><strong>${escapeHtml(displayLabel(BATCH_STATUS_LABELS, batch.status))}</strong><small>${escapeHtml(displayLabel(REVIEW_STATUS_LABELS, batch.reviewStatus || "pending"))} · ${escapeHtml(displayLabel(ACCEPTANCE_STATUS_LABELS, batch.acceptanceStatus || "pending"))} · ${escapeHtml(displayLabel(BATCH_QUALITY_STATUS_LABELS, batch.qualityStatus || "pending"))} / ${escapeHtml(displayLabel(PUBLISH_RISK_LABELS, batch.publishRiskStatus || "unknown"))} · ${escapeHtml(batch.validRows ?? 0)} 有效 / ${escapeHtml(batch.invalidRows ?? 0)} 无效 / ${escapeHtml(batch.totalRows ?? 0)} 总行</small></div></td>
            <td>${escapeHtml(batch.createdBy || "-")}</td>
            <td>${escapeHtml(formatDateTime(batch.completedAt || batch.createdAt))}</td>
            <td>${batchActionButtons(batch)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  function deliveryPackageStatusClass(status) {
    if (status === "ready") return "complete";
    if (status === "blocked") return "danger";
    if (status === "awaiting_delivery" || status === "awaiting_publish") return "review";
    return "partial";
  }

  function deliveryBlockingText(reasons) {
    const items = Array.isArray(reasons) ? reasons : [];
    if (!items.length) return "无阻断";
    return items.map((reason) => DELIVERY_BLOCKING_REASON_LABELS[reason] || reason).join(" / ");
  }

  function primaryDeliverySceneId(item) {
    if (item.primarySceneId) return item.primarySceneId;
    const receipt = Array.isArray(item.sceneDeliveryReceiptUrls) ? item.sceneDeliveryReceiptUrls[0] : null;
    if (receipt?.sceneId) return receipt.sceneId;
    const scene = Array.isArray(item.scenes) ? item.scenes.find((candidate) => candidate?.sceneId && !candidate?.sceneMissing) : null;
    return scene?.sceneId || "";
  }

  function deliveryPackageActionButtons(item) {
    const batchId = item.batchId || "";
    const sceneId = primaryDeliverySceneId(item);
    const sceneDisabled = sceneId ? "" : " disabled";
    return `
      <div class="row-actions row-actions-wide" aria-label="交付包操作">
        <button type="button" class="icon-button" data-delivery-action="view" data-batch-id="${escapeHtml(batchId)}" aria-label="查看交付包" title="查看交付包">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>
        </button>
        <button type="button" class="icon-button" data-delivery-action="delivery-package-receipt" data-batch-id="${escapeHtml(batchId)}" data-permission="${IMPORT_EXPORT_PERMISSION}" aria-label="导出交付包总回执" title="导出交付包总回执">
          ${RECEIPT_ICON}
        </button>
        <button type="button" class="icon-button" data-delivery-action="acceptance-receipt" data-batch-id="${escapeHtml(batchId)}" data-permission="${IMPORT_EXPORT_PERMISSION}" aria-label="导出验收回执" title="导出验收回执">
          ${RECEIPT_ICON}
        </button>
        <button type="button" class="icon-button" data-delivery-action="scene-delivery-receipt" data-batch-id="${escapeHtml(batchId)}" data-scene-id="${escapeHtml(sceneId)}" data-permission="${IMPORT_EXPORT_PERMISSION}" aria-label="导出影像交付回执" title="导出影像交付回执"${sceneDisabled}>
          ${SCENE_RECEIPT_ICON}
        </button>
      </div>
    `;
  }

  function renderDeliveryPackageRows() {
    const body = $("#deliveryPackageRows");
    if (!body) return;
    if (!state.deliveryPackages.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无交付包数据</td></tr>';
      return;
    }
    body.innerHTML = state.deliveryPackages
      .map((item) => {
        const batchId = item.batchId || "";
        const linkedBlockPreview = (item.linkedBlockCodes || []).slice(0, 3).join(", ");
        const hiddenBlockCount = Math.max(0, Number(item.linkedBlockCount || 0) - 3);
        const blockSummary = `${linkedBlockPreview || "-"}${hiddenBlockCount ? ` +${hiddenBlockCount}` : ""}`;
        const sceneSummary = `${item.deliveredSceneCount || 0}/${item.linkedSceneCount || 0}`;
        const active = String(batchId) === String(state.activeDeliveryBatchId || "") ? "active" : "";
        return `
          <tr data-delivery-batch-id="${escapeHtml(batchId)}" class="${active}">
            <td><div class="cell-stack"><strong>${traceLink(`admin-imports.html?batchId=${encodeURIComponent(batchId)}`, item.fileName || batchId || "-")}</strong><small>${escapeHtml(batchId || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(displayLabel(ACCEPTANCE_STATUS_LABELS, item.acceptanceStatus || "pending"))}</strong><small>${escapeHtml(item.acceptedBy || "-")} / ${escapeHtml(formatDateTime(item.acceptedAt))}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(sceneSummary)} 已交付</strong><small>${escapeHtml(displayLabel(DELIVERY_STATUS_LABELS, item.deliveryStatus || "pending"))}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(item.publishedLayerCount ?? 0)} 个图层 / ${escapeHtml(item.linkedBlockCount ?? 0)} 个林班</strong><small>${escapeHtml(blockSummary)}</small></div></td>
            <td><div class="cell-stack"><span class="status-pill ${deliveryPackageStatusClass(item.packageStatus)}">${escapeHtml(displayLabel(DELIVERY_PACKAGE_STATUS_LABELS, item.packageStatus))}</span><small>${escapeHtml(deliveryBlockingText(item.blockingReasons))}</small></div></td>
            <td>${deliveryPackageActionButtons(item)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  function renderDeliveryPackageScenes(item) {
    const target = $("#deliveryPackageSceneList");
    if (!target) return;
    const scenes = Array.isArray(item?.scenes) ? item.scenes : [];
    if (!scenes.length) {
      target.innerHTML = '<p class="trace-empty">暂无关联影像，交付包仍需挂接影像成果。</p>';
      return;
    }
    target.innerHTML = scenes
      .map((scene) => {
        const sceneId = scene.sceneId || "";
        const layerCode = scene.publishedLayerRecordCode || scene.publishedLayerId || "";
        return `
          <article class="trace-item">
            <strong>${sceneId ? traceLink(`admin-imagery.html?sceneId=${encodeURIComponent(sceneId)}`, scene.sceneName || sceneId) : escapeHtml(scene.sceneName || "-")}</strong>
            <span>交付 ${escapeHtml(displayLabel(DELIVERY_STATUS_LABELS, scene.deliveryStatus || "pending"))} / 影像 ${escapeHtml(scene.status || "-")}</span>
            <span>${layerCode ? traceLink(`admin-map-layers.html?layerCode=${encodeURIComponent(layerCode)}`, `图层 ${layerCode}`) : "未发布图层"}</span>
            <span>交付人 ${escapeHtml(scene.deliveredBy || "-")} / ${escapeHtml(formatDateTime(scene.deliveredAt))}</span>
          </article>
        `;
      })
      .join("");
  }

  function renderDeliveryPackageBlockingReasons(item) {
    const target = $("#deliveryPackageBlockingList");
    if (!target) return;
    const reasons = Array.isArray(item?.blockingReasons) ? item.blockingReasons : [];
    if (!reasons.length) {
      target.innerHTML = '<p class="trace-empty">暂无阻断原因，交付包当前满足闭环条件。</p>';
      return;
    }
    target.innerHTML = reasons
      .map((reason) => `
        <article class="trace-item">
          <strong>${escapeHtml(DELIVERY_BLOCKING_REASON_LABELS[reason] || reason)}</strong>
          <span>${escapeHtml(reason)}</span>
        </article>
      `)
      .join("");
  }

  function deliveryPackageReceiptButton(action, batchId, label, sceneId = "", disabled = false) {
    return `
      <button type="button" class="button-ghost trace-command" data-delivery-action="${action}" data-batch-id="${escapeHtml(batchId)}" data-scene-id="${escapeHtml(sceneId)}" data-permission="${IMPORT_EXPORT_PERMISSION}"${disabled ? " disabled" : ""}>
        ${escapeHtml(label)}
      </button>
    `;
  }

  function renderDeliveryPackageReceipts(item) {
    const target = $("#deliveryPackageReceiptList");
    if (!target) return;
    const receipts = [];
    const batchId = item?.batchId || "";
    if (batchId) {
      receipts.push(traceLink(`admin-imports.html?batchId=${encodeURIComponent(batchId)}`, `批次 ${batchId}`));
      receipts.push(deliveryPackageReceiptButton("delivery-package-receipt", batchId, "导出交付包总回执"));
    }
    if (item?.acceptanceReceiptUrl) {
      receipts.push(deliveryPackageReceiptButton("acceptance-receipt", batchId, "导出验收回执"));
    }
    (item?.sceneDeliveryReceiptUrls || []).forEach((receipt) => {
      const sceneId = receipt?.sceneId || "";
      if (!sceneId) return;
      receipts.push(deliveryPackageReceiptButton("scene-delivery-receipt", batchId, `导出影像交付回执 ${sceneId}`, sceneId));
    });
    (item?.publishedLayerRecordCodes || []).forEach((layerCode) => {
      if (!layerCode) return;
      receipts.push(traceLink(`admin-map-layers.html?layerCode=${encodeURIComponent(layerCode)}`, `图层 ${layerCode}`));
    });
    target.innerHTML = receipts.length ? `<div class="operation-result-links">${receipts.join("")}</div>` : '<p class="trace-empty">暂无可导出的交付回执。</p>';
    applyActionPermissions();
  }

  function deliveryPackageNumericCount(value, fallback = 0) {
    const numeric = Number(value);
    return Number.isFinite(numeric) && numeric >= 0 ? numeric : fallback;
  }

  function deliveryPackageSceneProgress(item) {
    const scenes = Array.isArray(item?.scenes) ? item.scenes : [];
    const deliveredFromScenes = scenes.filter((scene) => scene?.deliveryStatus === "delivered").length;
    const delivered = deliveryPackageNumericCount(item?.deliveredSceneCount, deliveredFromScenes);
    const total = deliveryPackageNumericCount(item?.linkedSceneCount, Math.max(scenes.length, delivered));
    return { delivered, total: Math.max(total, delivered) };
  }

  function publishedLayerProgress(item) {
    const scenes = Array.isArray(item?.scenes) ? item.scenes : [];
    const linkedLayerCodes = Array.isArray(item?.publishedLayerRecordCodes) ? item.publishedLayerRecordCodes : [];
    const publishedFromScenes = scenes.filter((scene) => scene?.published || scene?.publishedLayerRecordCode || scene?.publishedLayerId).length;
    const published = deliveryPackageNumericCount(item?.publishedLayerCount, Math.max(linkedLayerCodes.length, publishedFromScenes));
    const total = deliveryPackageNumericCount(item?.linkedSceneCount, Math.max(scenes.length, published));
    return { published, total: Math.max(total, published) };
  }

  function deliveryPackageReceiptCount(item) {
    const packageReceiptCount = item?.batchId ? 1 : 0;
    const acceptanceReceiptCount = item?.acceptanceReceiptUrl ? 1 : 0;
    const sceneReceiptCount = Array.isArray(item?.sceneDeliveryReceiptUrls) ? item.sceneDeliveryReceiptUrls.length : 0;
    const layerReceiptCount = Array.isArray(item?.mapLayerPublicationReceiptUrls) ? item.mapLayerPublicationReceiptUrls.length : 0;
    return packageReceiptCount + acceptanceReceiptCount + sceneReceiptCount + layerReceiptCount;
  }

  function deliveryPackageClosureSummaryItems(item = {}) {
    const batchId = item.batchId || "";
    const sceneProgress = deliveryPackageSceneProgress(item);
    const layerProgress = publishedLayerProgress(item);
    const blockingReasonCount = Array.isArray(item.blockingReasons) ? item.blockingReasons.length : 0;
    const receiptCount = deliveryPackageReceiptCount(item);
    const primarySceneId = primaryDeliverySceneId(item);
    const layerCodes = Array.isArray(item.publishedLayerRecordCodes) ? item.publishedLayerRecordCodes : [];
    return [
      {
        label: "交付状态",
        value: displayLabel(DELIVERY_PACKAGE_STATUS_LABELS, item.packageStatus || "pending"),
        meta: deliveryBlockingText(item.blockingReasons),
        tone: item.packageStatus === "ready" ? "ready" : item.packageStatus === "blocked" ? "danger" : "warning",
      },
      {
        label: "影像交付",
        value: `${sceneProgress.delivered}/${sceneProgress.total}`,
        meta: primarySceneId ? `主影像 ${primarySceneId}` : "未挂接影像",
        tone: sceneProgress.total && sceneProgress.delivered >= sceneProgress.total ? "ready" : "warning",
        action: primarySceneId ? "scene-delivery-receipt" : "",
        batchId,
        sceneId: primarySceneId,
        permission: IMPORT_EXPORT_PERMISSION,
      },
      {
        label: "图层发布",
        value: `${layerProgress.published}/${layerProgress.total}`,
        meta: layerCodes.length ? layerCodes.join(", ") : "等待发布图层",
        tone: layerProgress.total && layerProgress.published >= layerProgress.total ? "ready" : "warning",
      },
      {
        label: "回执与阻断",
        value: `${receiptCount}/${blockingReasonCount}`,
        meta: "可导出回执 / 阻断原因",
        tone: blockingReasonCount ? "danger" : "ready",
        action: item.batchId ? "delivery-package-receipt" : "",
        batchId,
        permission: IMPORT_EXPORT_PERMISSION,
      },
    ];
  }

  function deliveryPackageClosureActionAttribute(action) {
    if (action === "delivery-package-receipt") return 'data-delivery-action="delivery-package-receipt"';
    if (action === "acceptance-receipt") return 'data-delivery-action="acceptance-receipt"';
    if (action === "scene-delivery-receipt") return 'data-delivery-action="scene-delivery-receipt"';
    return `data-delivery-action="${escapeHtml(action || "")}"`;
  }

  function deliveryPackageClosureSummaryCard(item) {
    const tone = item.tone ? ` tone-${item.tone}` : "";
    const command = item.action
      ? `<button type="button" class="button-ghost receipt-summary-command" ${deliveryPackageClosureActionAttribute(item.action)} data-batch-id="${escapeHtml(item.batchId || "")}" data-scene-id="${escapeHtml(item.sceneId || "")}" data-permission="${escapeHtml(item.permission || "")}">导出回执</button>`
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

  function renderDeliveryPackageClosureSummary(item) {
    const target = $("#deliveryPackageClosureSummary");
    if (!target) return;
    if (!item?.batchId) {
      target.innerHTML = '<p class="trace-empty">请选择交付包生成闭环摘要。</p>';
      return;
    }
    target.innerHTML = deliveryPackageClosureSummaryItems(item).map(deliveryPackageClosureSummaryCard).join("");
    applyActionPermissions();
  }

  function renderDeliveryPackageDetail(item = activeDeliveryPackage()) {
    const panel = $("#deliveryPackageDetailPanel");
    if (!panel) return;
    if (!item) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      return;
    }
    state.activeDeliveryBatchId = item.batchId || "";
    $("#deliveryPackageDetailTitle").textContent = `${item.fileName || item.batchId || "交付包"}详情`;
    $("#deliveryPackageDetailEmpty").hidden = true;
    $("#deliveryPackageDetailGrid").innerHTML = [
      detailItem("批次 ID", item.batchId || "-"),
      detailItem("文件名", item.fileName || "-"),
      detailItem("交付包状态", displayLabel(DELIVERY_PACKAGE_STATUS_LABELS, item.packageStatus || "-")),
      detailItem("验收状态", displayLabel(ACCEPTANCE_STATUS_LABELS, item.acceptanceStatus || "pending")),
      detailItem("验收人", item.acceptedBy || "-"),
      detailItem("验收时间", formatDateTime(item.acceptedAt)),
      detailItem("影像交付", displayLabel(DELIVERY_STATUS_LABELS, item.deliveryStatus || "pending")),
      detailItem("影像数量", `${item.deliveredSceneCount || 0}/${item.linkedSceneCount || 0}`),
      detailItem("已发布图层", item.publishedLayerCount ?? 0),
      detailItem("林班数量", item.linkedBlockCount ?? 0),
      detailItem("林权档案", item.rightArchiveCount ?? 0),
      detailItem("更新时间", formatDateTime(item.updatedAt)),
      detailItem("关联林班", (item.linkedBlockCodes || []).join(", ") || "-"),
      detailItem("图层编号", (item.publishedLayerRecordCodes || []).join(", ") || "-"),
    ].join("");
    renderDeliveryPackageClosureSummary(item);
    renderDeliveryPackageScenes(item);
    renderDeliveryPackageBlockingReasons(item);
    renderDeliveryPackageReceipts(item);
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    renderDeliveryPackageRows();
  }

  function renderImportAuditEvents() {
    const body = $("#importAuditRows");
    if (!body) return;
    if (!state.auditEvents.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无审计事件</td></tr>';
      return;
    }
    body.innerHTML = state.auditEvents
      .map((event) => `
        <tr>
          <td>${escapeHtml(formatDateTime(event.at))}</td>
          <td><span class="status-pill">${escapeHtml(displayLabel(IMPORT_AUDIT_ACTION_LABELS, event.action))}</span></td>
          <td><div class="cell-stack"><strong>${traceLink(`admin-imports.html?batchId=${encodeURIComponent(event.batchId || "")}`, event.batchId || "-")}</strong><small>${escapeHtml(event.fileName || "-")}</small></div></td>
          <td>${escapeHtml(event.actor || "-")}</td>
          <td><div class="cell-stack"><strong>${escapeHtml(displayLabel(BATCH_STATUS_LABELS, event.batchStatus))}</strong><small>${escapeHtml(displayLabel(REVIEW_STATUS_LABELS, event.reviewStatus))} / ${escapeHtml(displayLabel(PUBLISH_RISK_LABELS, event.publishRiskStatus))}</small></div></td>
          <td>${renderAuditSummary(event.summary)}</td>
        </tr>
      `)
      .join("");
  }

  function renderQualityIssueRows() {
    const body = $("#qualityIssueRows");
    if (!body) return;
    if (!state.qualityIssues.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="8">暂无质量问题</td></tr>';
      return;
    }
    body.innerHTML = state.qualityIssues
      .map((issue) => {
        const status = issue.status || "open";
        const active = String(issue.issueId || "") === String(state.activeQualityIssueId || "") ? "active" : "";
        return `
          <tr data-issue-id="${escapeHtml(issue.issueId || "")}" class="${active}">
            <td><span class="status-pill">${escapeHtml(displayLabel(ISSUE_SEVERITY_LABELS, issue.severity))}</span></td>
            <td><div class="cell-stack"><strong>${escapeHtml(displayLabel(IMPORT_ISSUE_TYPE_LABELS, issue.issueType))}</strong><small>${escapeHtml(issue.issueKey || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${traceLink(`admin-imports.html?batchId=${encodeURIComponent(issue.batchId || "")}`, issue.batchId || "-")}</strong><small>${escapeHtml(issue.fileName || "-")}</small></div></td>
            <td>${escapeHtml((issue.blockCodes || []).join(", ") || "-")}</td>
            <td>${escapeHtml(issue.sceneId || "-")}</td>
            <td><div class="cell-stack"><strong>${escapeHtml(issue.message || "-")}</strong><small>${escapeHtml(issue.actionRequired || "-")}</small></div></td>
            <td><div class="cell-stack"><span class="status-pill ${qualityIssueStatusClass(status)}">${escapeHtml(qualityIssueStatusLabel(status))}</span><small>${escapeHtml(issue.handledBy || "-")} / ${escapeHtml(formatDateTime(issue.handledAt))}</small><small>${escapeHtml(issue.handlingComment || "-")}</small></div></td>
            <td>${qualityIssueActions(issue)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  function detailItem(label, value) {
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "未填")}</dd></div>`;
  }

  function traceLink(href, label) {
    return `<a class="trace-link" href="${escapeHtml(href)}">${escapeHtml(label)}</a>`;
  }

  function renderImportTraceList(targetSelector, items, emptyText, renderer) {
    const target = $(targetSelector);
    if (!target) return;
    if (!Array.isArray(items) || !items.length) {
      target.innerHTML = `<p class="trace-empty">${escapeHtml(emptyText)}</p>`;
      return;
    }
    target.innerHTML = items.map(renderer).join("");
  }

  function appendImportTargetCount(targetSelector, payload) {
    const target = $(targetSelector);
    if (!target || !payload) return;
    const shown = Array.isArray(payload.items) ? payload.items.length : 0;
    const total = Number(payload.total || 0);
    if (total > shown) {
      target.insertAdjacentHTML(
        "beforeend",
        `<p class="trace-empty">当前显示 ${escapeHtml(shown)} 条，共 ${escapeHtml(total)} 条；可通过批次报告导出完整清单。</p>`,
      );
    }
  }

  async function loadImportBatchTargets(batchId) {
    const encodedBatchId = encodeURIComponent(batchId || "");
    if (!encodedBatchId) return;
    try {
      const [blocks, rights] = await Promise.all([
        api(`/api/imports/${encodedBatchId}/targets?kind=blocks&limit=100&offset=0`),
        api(`/api/imports/${encodedBatchId}/targets?kind=rights&limit=100&offset=0`),
      ]);
      if (String(state.activeBatchId || "") !== String(batchId || "")) return;
      renderImportTraceList("#importedBlocksList", blocks.items, "本批次未写入林班", (item) => `
        <article class="trace-item">
          <strong>${item.blockCode ? traceLink(`admin-blocks.html?blockCode=${encodeURIComponent(item.blockCode)}`, item.blockCode) : "-"}</strong>
          <span>${escapeHtml(item.name || "-")} · ${escapeHtml(item.action || "-")} · 第 ${escapeHtml(item.row || "-")} 行</span>
        </article>
      `);
      appendImportTargetCount("#importedBlocksList", blocks);
      renderImportTraceList("#importedRightsList", rights.items, "本批次未生成林权档案关联", (item) => `
        <article class="trace-item">
          <strong>${item.archiveCode ? traceLink(`admin-rights.html?archiveCode=${encodeURIComponent(item.archiveCode)}`, item.archiveCode) : "-"}</strong>
          <span>关联林班：${escapeHtml((item.linkedBlockCodes || []).join(", ") || "-")}</span>
        </article>
      `);
      appendImportTargetCount("#importedRightsList", rights);
    } catch (error) {
      if (String(state.activeBatchId || "") !== String(batchId || "")) return;
      renderImportTraceList("#importedBlocksList", [], `林班明细加载失败：${error.message}`, () => "");
      renderImportTraceList("#importedRightsList", [], `林权明细加载失败：${error.message}`, () => "");
    }
  }

  function renderImportBatchImageryLinksLegacy(batch) {
    renderImportTraceList("#importBatchImageryLinksList", batch?.imageryLinks, "\u672c\u6279\u6b21\u672a\u5173\u8054\u5f71\u50cf\u56fe\u5c42", (item) => `
      <article class="trace-item">
        <strong>${escapeHtml(item.sceneId || "-")}</strong>
        <span>${escapeHtml(item.layerRecordCode || item.layerId || "-")} · \u6797\u73ed ${escapeHtml((item.linkedBlockCodes || []).length)} \u4e2a · ${escapeHtml(formatDateTime(item.at))}</span>
      </article>
    `);
  }

  function renderImportBatchImageryLinks(batch) {
    renderImportTraceList("#importBatchImageryLinksList", batch?.imageryLinks, "本批次未关联影像图层", (item) => {
      const sceneId = item.sceneId || "";
      const layerCode = item.layerRecordCode || item.layerId || "";
      return `
        <article class="trace-item">
          <strong>${sceneId ? traceLink(`admin-imagery.html?sceneId=${encodeURIComponent(sceneId)}`, `影像 ${sceneId}`) : "-"}</strong>
          <span>${layerCode ? traceLink(`admin-map-layers.html?layerCode=${encodeURIComponent(layerCode)}`, `图层 ${layerCode}`) : "-"} · 林班 ${escapeHtml((item.linkedBlockCodes || []).length)} 个 · ${escapeHtml(formatDateTime(item.at))}</span>
        </article>
      `;
    });
  }

  function importBatchDeliveryPackage(batch) {
    const batchId = String(batch?.id || "").trim();
    if (!batchId) return null;
    return state.deliveryPackages.find((packageItem) => String(packageItem.batchId || "") === batchId) || null;
  }

  function renderWorkflowStepper(steps) {
    return steps
      .map(
        (step, index) => `
          <article class="workflow-step" data-state="${escapeHtml(step.state || "pending")}" data-workflow-step="${escapeHtml(step.key || "")}">
            <span class="workflow-step-index">${escapeHtml(index + 1)}</span>
            <div>
              <strong>${escapeHtml(step.label || step.key || "-")}</strong>
              <small>${escapeHtml(step.meta || "-")}</small>
            </div>
          </article>
        `,
      )
      .join("");
  }

  function workflowStepStatus(value, completeValues, warningValues = [], blockedValues = []) {
    const status = String(value || "").trim();
    if (completeValues.includes(status)) return "complete";
    if (blockedValues.includes(status)) return "blocked";
    if (warningValues.includes(status)) return "warning";
    return "pending";
  }

  function latestImportBatchImageryLink(batch) {
    const links = Array.isArray(batch?.imageryLinks) ? batch.imageryLinks : [];
    return links.length ? links[links.length - 1] : null;
  }

  function importBatchLayerPublished(batch) {
    const links = Array.isArray(batch?.imageryLinks) ? batch.imageryLinks : [];
    return links.some((link) => Boolean(link.layerRecordCode || link.layerId || link.publishedLayerId || link.layerStatus === "published"));
  }

  function importDeliveryPackageState(packageItem) {
    if (!packageItem) return "pending";
    if (Array.isArray(packageItem.blockingReasons) && packageItem.blockingReasons.length) return "warning";
    if (["ready", "delivered", "completed"].includes(String(packageItem.packageStatus || ""))) return "complete";
    if (["blocked", "rejected"].includes(String(packageItem.packageStatus || ""))) return "blocked";
    return "pending";
  }

  function importBatchWorkflowSteps(batch) {
    const packageItem = importBatchDeliveryPackage(batch);
    const latestLink = latestImportBatchImageryLink(batch);
    const reviewState = workflowStepStatus(batch?.reviewStatus, ["approved"], ["needs_correction"], ["rejected"]);
    const acceptanceState = workflowStepStatus(batch?.acceptanceStatus, ["accepted", "passed", "approved"], ["needs_correction"], ["rejected"]);
    const qualityState = Number(batch?.invalidRows || 0)
      ? "warning"
      : workflowStepStatus(batch?.qualityStatus, ["passed", "pass", "clear"], ["warning"], ["failed", "blocked"]);
    return [
      {
        key: "imported",
        label: "成果入库",
        state: workflowStepStatus(batch?.status, ["completed"], ["processing"], ["failed", "rolled_back", "deleted"]),
        meta: `有效 ${batch?.validRows ?? 0} / 总行 ${batch?.totalRows ?? 0}`,
      },
      {
        key: "quality",
        label: "质量校验",
        state: qualityState,
        meta: displayLabel(BATCH_QUALITY_STATUS_LABELS, batch?.qualityStatus || (Number(batch?.invalidRows || 0) ? "warning" : "pending")),
      },
      {
        key: "review",
        label: "业务审核",
        state: reviewState,
        meta: displayLabel(REVIEW_STATUS_LABELS, batch?.reviewStatus || "pending"),
      },
      {
        key: "acceptance",
        label: "验收确认",
        state: acceptanceState,
        meta: displayLabel(ACCEPTANCE_STATUS_LABELS, batch?.acceptanceStatus || "pending"),
      },
      {
        key: "imagery-link",
        label: "影像挂接",
        state: latestLink ? "complete" : "pending",
        meta: latestLink?.sceneId || "等待关联影像成果",
      },
      {
        key: "layer-publish",
        label: "图层发布",
        state: importBatchLayerPublished(batch) ? "complete" : latestLink ? "pending" : "blocked",
        meta: latestLink?.layerRecordCode || latestLink?.layerId || "等待图层发布",
      },
      {
        key: "delivery-package",
        label: "交付包",
        state: importDeliveryPackageState(packageItem),
        meta: packageItem ? displayLabel(DELIVERY_PACKAGE_STATUS_LABELS, packageItem.packageStatus || "pending") : "未生成交付包",
      },
    ];
  }

  function ensureImportBatchWorkflowStepper() {
    const detailGrid = $("#importBatchDetailGrid");
    if (!detailGrid) return null;
    if (!$("#importBatchWorkflowStepper")) {
      const wrapper = document.createElement("div");
      wrapper.className = "task-events workflow-stepper-panel";
      wrapper.innerHTML = '<h3>入库闭环进度</h3><div id="importBatchWorkflowStepper" class="workflow-stepper" aria-label="入库闭环进度"></div>';
      detailGrid.insertAdjacentElement("afterend", wrapper);
    }
    return $("#importBatchWorkflowStepper");
  }

  function renderImportBatchWorkflowSteps(batch) {
    const target = ensureImportBatchWorkflowStepper();
    if (!target) return;
    target.innerHTML = renderWorkflowStepper(importBatchWorkflowSteps(batch));
  }

  function importBatchPermissionBoundaryItems(batch) {
    const hasLinkedScene = Boolean(latestImportBatchImageryLink(batch));
    return [
      {
        key: "review",
        label: "批次审核",
        description: "审核导入成果是否可进入验收。",
        permission: IMPORT_REVIEW_PERMISSION,
      },
      {
        key: "acceptance",
        label: "验收确认",
        description: "记录验收状态、验收意见和回执依据。",
        permission: IMPORT_ACCEPTANCE_PERMISSION,
      },
      {
        key: "scene-layer-link",
        label: "影像挂接与图层发布",
        description: hasLinkedScene ? "已有关联影像，可继续执行图层发布闭环。" : "先选择影像，再完成地图图层发布依赖。",
        permission: IMPORT_SCENE_LAYER_LINK_PERMISSION,
        allPermissions: IMPORT_MAP_LAYER_REQUIRED_PERMISSION,
        anyPermissions: IMPORT_MAP_LAYER_UPSERT_PERMISSIONS,
      },
      {
        key: "rollback",
        label: "撤销入库",
        description: "软撤销本批次写入的林班和林权关联。",
        permission: IMPORT_ROLLBACK_PERMISSION,
      },
      {
        key: "export",
        label: "报告与回执导出",
        description: "导出入库报告、错误行、验收回执和审计事件。",
        permission: IMPORT_EXPORT_PERMISSION,
      },
    ];
  }

  function permissionBoundaryChipList(value) {
    const permissions = splitValues(value || "");
    if (!permissions.length) return '<span class="ledger-chip-empty">无额外权限</span>';
    return permissions.map((permission) => `<span class="ledger-chip">${escapeHtml(permission)}</span>`).join("");
  }

  function permissionBoundaryItem(item) {
    return `
      <article
        class="permission-boundary-item"
        data-permission-requirement="${escapeHtml(item.key)}"
        data-permission="${escapeHtml(item.permission || "")}"
        data-permission-all="${escapeHtml(item.allPermissions || "")}"
        data-permission-any="${escapeHtml(item.anyPermissions || "")}"
      >
        <div>
          <strong>${escapeHtml(item.label)}</strong>
          <span>${escapeHtml(item.description)}</span>
        </div>
        <div class="permission-boundary-permissions" aria-label="${escapeHtml(item.label)}所需权限">
          <span class="permission-boundary-label">必需</span>
          <div class="ledger-chip-list">${permissionBoundaryChipList(item.permission)}</div>
          ${
            item.allPermissions
              ? `<span class="permission-boundary-label">同时需要</span><div class="ledger-chip-list">${permissionBoundaryChipList(item.allPermissions)}</div>`
              : ""
          }
          ${
            item.anyPermissions
              ? `<span class="permission-boundary-label">任一满足</span><div class="ledger-chip-list">${permissionBoundaryChipList(item.anyPermissions)}</div>`
              : ""
          }
        </div>
      </article>
    `;
  }

  function ensureImportBatchPermissionBoundary() {
    const detailGrid = $("#importBatchDetailGrid");
    if (!detailGrid) return null;
    if (!$("#importBatchPermissionBoundary")) {
      const wrapper = document.createElement("div");
      wrapper.className = "task-events permission-boundary-panel";
      wrapper.innerHTML = '<h3>操作权限边界</h3><div id="importBatchPermissionBoundary" class="permission-boundary-list" aria-label="成果入库操作权限边界"></div>';
      const workflowPanel = $("#importBatchWorkflowStepper")?.closest(".task-events");
      (workflowPanel || detailGrid).insertAdjacentElement("afterend", wrapper);
    }
    return $("#importBatchPermissionBoundary");
  }

  function renderImportBatchPermissionBoundary(batch) {
    const target = ensureImportBatchPermissionBoundary();
    if (!target) return;
    target.innerHTML = importBatchPermissionBoundaryItems(batch).map(permissionBoundaryItem).join("");
  }

  function importBatchAcceptanceEvents(batch) {
    return Array.isArray(batch?.acceptanceEvents) ? batch.acceptanceEvents : [];
  }

  function importBatchReceiptSummaryItems(batch) {
    const acceptanceEvents = importBatchAcceptanceEvents(batch);
    const latestAcceptance = acceptanceEvents.length ? acceptanceEvents[acceptanceEvents.length - 1] : null;
    const qualityIssueCount = (Array.isArray(batch?.qualityIssues) ? batch.qualityIssues : state.qualityIssues.filter((issue) => String(issue.batchId || "") === String(batch?.id || ""))).length;
    const auditEventCount = Array.isArray(batch?.auditEvents) ? batch.auditEvents.length : 0;
    const acceptedAt = batch?.acceptedAt || latestAcceptance?.at || "";
    const acceptedBy = batch?.acceptedBy || latestAcceptance?.actor || "-";
    return [
      {
        label: "验收状态",
        value: displayLabel(ACCEPTANCE_STATUS_LABELS, batch?.acceptanceStatus || "pending"),
        meta: `${acceptedBy} / ${formatDateTime(acceptedAt)}`,
        tone: batch?.acceptanceStatus === "accepted" ? "ready" : batch?.acceptanceStatus === "rejected" ? "danger" : "warning",
      },
      {
        label: "回执事件",
        value: acceptanceEvents.length,
        meta: latestAcceptance?.comment || batch?.acceptanceComment || "暂无验收意见",
        tone: acceptanceEvents.length ? "ready" : "warning",
      },
      {
        label: "质检与审计",
        value: `${qualityIssueCount} / ${auditEventCount}`,
        meta: "质检问题 / 操作审计",
        tone: qualityIssueCount ? "warning" : "ready",
      },
      {
        label: "验收回执",
        value: batch?.id || "-",
        meta: "导出 JSON 回执并写入审计流",
        tone: "ready",
        action: "import-acceptance",
        permission: IMPORT_EXPORT_PERMISSION,
      },
    ];
  }

  function receiptSummaryCard(item) {
    const tone = item.tone ? ` tone-${item.tone}` : "";
    const actionAttribute =
      item.action === "import-acceptance"
        ? 'data-receipt-action="import-acceptance"'
        : `data-receipt-action="${escapeHtml(item.action || "")}"`;
    const command = item.action
      ? `<button type="button" class="button-ghost receipt-summary-command" ${actionAttribute} data-permission="${escapeHtml(item.permission || "")}">导出回执</button>`
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

  function renderImportBatchReceiptSummary(batch) {
    const target = $("#importBatchReceiptSummary");
    if (!target) return;
    if (!batch?.id) {
      target.innerHTML = '<p class="trace-empty">请选择入库批次生成回执摘要。</p>';
      return;
    }
    target.innerHTML = importBatchReceiptSummaryItems(batch).map(receiptSummaryCard).join("");
    applyActionPermissions();
  }

  function renderImportBatchDeliveryPackage(batch) {
    const target = $("#importBatchDeliveryPackageList");
    if (!target) return;
    const packageItem = importBatchDeliveryPackage(batch);
    if (!batch?.id) {
      target.innerHTML = '<p class="trace-empty">请先选择一条入库批次。</p>';
      return;
    }
    if (!packageItem) {
      target.innerHTML = '<p class="trace-empty">暂无交付包记录；批次完成审核、验收和影像挂接后会进入交付包台账。</p>';
      return;
    }
    const packageStatusClass = deliveryPackageStatusClass(packageItem.packageStatus);
    const packageStatus = displayLabel(DELIVERY_PACKAGE_STATUS_LABELS, packageItem.packageStatus);
    const batchId = packageItem.batchId || batch.id || "";
    const packageHref = `admin-imports.html?batchId=${encodeURIComponent(batchId)}&deliveryPackageStatus=${encodeURIComponent(packageItem.packageStatus || "")}`;
    const sceneSummary = `${packageItem.deliveredSceneCount || 0}/${packageItem.linkedSceneCount || 0}`;
    target.innerHTML = `
      <article class="trace-item">
        <strong>${traceLink(packageHref, packageItem.fileName || batchId || "交付包")}</strong>
        <span><span class="status-pill ${packageStatusClass}">${escapeHtml(packageStatus)}</span> · 验收 ${escapeHtml(displayLabel(ACCEPTANCE_STATUS_LABELS, packageItem.acceptanceStatus || "pending"))} · 影像交付 ${escapeHtml(displayLabel(DELIVERY_STATUS_LABELS, packageItem.deliveryStatus || "pending"))}</span>
        <span>影像 ${escapeHtml(sceneSummary)} · 图层 ${escapeHtml(packageItem.publishedLayerCount ?? 0)} 个 · 林班 ${escapeHtml(packageItem.linkedBlockCount ?? 0)} 个</span>
        <span>阻断：${escapeHtml(deliveryBlockingText(packageItem.blockingReasons))}</span>
      </article>
    `;
  }

  function renderImportBatchCoverageCheck(batch) {
    const target = $("#importBatchCoverageCheck");
    if (!target) return;
    const links = Array.isArray(batch?.imageryLinks) ? batch.imageryLinks : [];
    const latestLink = links.length ? links[links.length - 1] : null;
    const coverageCheck = latestLink?.coverageCheck || null;
    if (!coverageCheck) {
      target.innerHTML = '<p class="trace-empty">暂无覆盖预检；关联影像图层后显示。</p>';
      return;
    }
    const warnings = Array.isArray(coverageCheck.warnings) ? coverageCheck.warnings : [];
    const missingCodes = Array.isArray(coverageCheck.missingGeometryBlockCodes) ? coverageCheck.missingGeometryBlockCodes : [];
    const outsideCodes = Array.isArray(coverageCheck.outsideSceneBoundsBlockCodes) ? coverageCheck.outsideSceneBoundsBlockCodes : [];
    const statusText = coverageCheck.status === "pass" ? "通过" : "预警";
    const warningText = warnings.length ? warnings.join(", ") : "none";
    target.innerHTML = `
      <article class="trace-item">
        <strong>${escapeHtml(statusText)} · ${escapeHtml(latestLink.sceneId || "-")}</strong>
        <span>检查 ${escapeHtml(coverageCheck.checkedBlocks ?? 0)} / ${escapeHtml(coverageCheck.totalBlocks ?? 0)} 个林班；影像边界 ${coverageCheck.sceneHasBounds ? "已提供" : "缺失"}</span>
        <span>缺少空间边界 ${escapeHtml(coverageCheck.missingGeometryCount ?? 0)} 个；超出影像范围 ${escapeHtml(coverageCheck.outsideSceneBoundsCount ?? 0)} 个</span>
        <span>预警项：${escapeHtml(warningText)}</span>
        <span>缺图形：${escapeHtml(missingCodes.join(", ") || "-")}</span>
        <span>越界：${escapeHtml(outsideCodes.join(", ") || "-")}</span>
      </article>
    `;
  }

  function publishReadinessPayload() {
    const zIndexRaw = $("#batchSceneZIndex")?.value.trim() || "";
    const payload = {
      sceneId: $("#batchSceneId")?.value.trim() || "",
      relationType: $("#batchSceneRelationType")?.value.trim() || "coverage",
      publishLayer: true,
    };
    if (zIndexRaw) payload.zIndex = Number(zIndexRaw);
    return payload;
  }

  function renderImportBatchPublishReadiness(readiness) {
    const target = $("#importBatchPublishReadiness");
    if (!target) return;
    if (!readiness) {
      target.innerHTML = '<p class="trace-empty">选择影像后可执行发布预检。</p>';
      return;
    }
    const checks = Array.isArray(readiness.checks) ? readiness.checks : [];
    const blockingReasons = Array.isArray(readiness.blockingReasons) ? readiness.blockingReasons : [];
    const warnings = Array.isArray(readiness.warnings) ? readiness.warnings : [];
    target.innerHTML = `
      <article class="trace-item ${readiness.ready ? "preview-effective" : "preview-blocked"}">
        <strong>${readiness.ready ? "可发布" : "暂不可发布"} · 林班 ${escapeHtml(readiness.linkedBlockCount ?? 0)} 个</strong>
        <span>阻断：${escapeHtml(blockingReasons.join(", ") || "-")}</span>
        <span>预警：${escapeHtml(warnings.join(", ") || "-")}</span>
        <span>图层发布：${readiness.publishLayer ? "是" : "否"} · 质量 ${escapeHtml(displayLabel(BATCH_QUALITY_STATUS_LABELS, readiness.quality?.qualityStatus))} · 风险 ${escapeHtml(displayLabel(PUBLISH_RISK_LABELS, readiness.quality?.publishRiskStatus))}</span>
      </article>
      ${checks
        .map(
          (check) => `
            <article class="trace-item">
              <strong>${escapeHtml(check.key || "-")} · ${escapeHtml(check.status || "-")}</strong>
              <span>${escapeHtml(check.message || "-")}</span>
            </article>
          `,
        )
        .join("")}
    `;
  }

  function importBatchOperationResultLinks(layer = {}, payload = {}) {
    const links = [];
    const layerCode = layer.recordCode || layer.id || payload.layerRecordCode || payload.layerId || "";
    const sourceLinks = Array.isArray(layer.sourceLinks) ? layer.sourceLinks : [];
    if (layer.adminHref) {
      links.push(traceLink(layer.adminHref, "图层后台"));
    } else if (layerCode) {
      links.push(traceLink(`admin-map-layers.html?layerCode=${encodeURIComponent(layerCode)}`, "图层后台"));
    }
    if (layer.dashboardHref) {
      links.push(traceLink(layer.dashboardHref, "大屏图层"));
    }
    sourceLinks.forEach((source) => {
      if (!source?.href) return;
      const label = [source.label || "来源", source.value || ""].filter(Boolean).join(" ");
      links.push(traceLink(source.href, label));
    });
    if (!links.length) {
      return '<p class="trace-empty">本次操作暂无可跳转来源。</p>';
    }
    return `<div class="operation-result-links">${links.join("")}</div>`;
  }

  function renderImportBatchOperationResult(payload) {
    const target = $("#importBatchOperationResult");
    if (!target) return;
    if (!payload) {
      target.innerHTML = '<p class="trace-empty">暂无本次操作回执。</p>';
      return;
    }
    const layer = payload.layer || {};
    const event = payload.event || {};
    const quality = payload.quality || {};
    const coverageCheck = payload.coverageCheck || {};
    const sourceLinks = Array.isArray(layer.sourceLinks) ? layer.sourceLinks : [];
    const dashboardHref = layer.dashboardHref || "";
    const layerCode = layer.recordCode || layer.id || event.layerRecordCode || event.layerId || "-";
    const publishText = dashboardHref ? "已发布到大屏" : "仅后台管理";
    target.innerHTML = `
      <article class="operation-result">
        <div class="operation-result-header">
          <div>
            <strong class="operation-result-title">图层发布回执</strong>
            <span>${escapeHtml(formatDateTime(event.at || layer.updatedAt || layer.createdAt))}</span>
          </div>
          <span class="operation-result-status">${escapeHtml(publishText)}</span>
        </div>
        <div class="operation-result-meta">
          <span>图层 ${escapeHtml(layerCode)}</span>
          <span>来源 ${escapeHtml(displayLabel(MAP_LAYER_SOURCE_TYPE_LABELS, layer.sourceType || "importBatch"))}</span>
          <span>风险 ${escapeHtml(displayLabel(PUBLISH_RISK_LABELS, layer.publishRiskStatus || quality.publishRiskStatus || "unknown"))}</span>
          <span>覆盖 ${escapeHtml(coverageCheck.status || "-")}</span>
          <span>追溯 ${escapeHtml(sourceLinks.length)} 项</span>
        </div>
        ${importBatchOperationResultLinks(layer, event)}
      </article>
    `;
  }

  function renderImportBatchReviewEvents(batch) {
    renderImportTraceList("#importBatchReviewEventsList", batch?.reviewEvents, "暂无审核记录", (event) => `
      <article class="trace-item">
        <strong>${escapeHtml(displayLabel(REVIEW_STATUS_LABELS, event.decision || event.action))}</strong>
        <span>${escapeHtml(formatDateTime(event.at))} · ${escapeHtml(event.actor || "-")}</span>
        <span>${escapeHtml(event.comment || "-")}</span>
      </article>
    `);
  }

  function renderImportBatchAcceptanceEvents(batch) {
    renderImportTraceList("#importBatchAcceptanceEventsList", batch?.acceptanceEvents, "暂无验收记录", (event) => `
      <article class="trace-item">
        <strong>${escapeHtml(displayLabel(ACCEPTANCE_STATUS_LABELS, event.status || event.action))}</strong>
        <span>${escapeHtml(formatDateTime(event.at))} · ${escapeHtml(event.actor || "-")}</span>
        <span>${escapeHtml(event.comment || "-")}</span>
      </article>
    `);
  }

  function renderImportBatchAuditEvents(batch) {
    renderImportTraceList("#importBatchAuditEventsList", batch?.auditEvents, "暂无操作审计", (event) => `
      <article class="trace-item">
        <strong>${escapeHtml(displayLabel(IMPORT_AUDIT_ACTION_LABELS, event.action))}</strong>
        <span>${escapeHtml(formatDateTime(event.at))} · ${escapeHtml(event.actor || "-")}</span>
        ${renderAuditSummary(event.summary, { limit: 8 })}
      </article>
    `);
  }

  function renderImportBatchDetail(batch = activeBatch()) {
    const panel = $("#importBatchDetailPanel");
    if (!batch) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      return;
    }
    $("#importBatchDetailTitle").textContent = `${batch.fileName || batch.id} 报告`;
    $("#importBatchDetailEmpty").hidden = true;
    $("#importBatchDetailGrid").innerHTML = [
      detailItem("批次 ID", batch.id || "-"),
      detailItem("文件名", batch.fileName || "-"),
      detailItem("文件类型", batch.fileType || "-"),
      detailItem("状态", displayLabel(BATCH_STATUS_LABELS, batch.status)),
      detailItem("总行数", batch.totalRows ?? 0),
      detailItem("有效行", batch.validRows ?? 0),
      detailItem("无效行", batch.invalidRows ?? 0),
      detailItem("审核状态", displayLabel(REVIEW_STATUS_LABELS, batch.reviewStatus || "pending")),
      detailItem("审核人", batch.reviewedBy || "-"),
      detailItem("审核时间", formatDateTime(batch.reviewedAt)),
      detailItem("审核意见", batch.reviewComment || "-"),
      detailItem("验收状态", displayLabel(ACCEPTANCE_STATUS_LABELS, batch.acceptanceStatus || "pending")),
      detailItem("验收人", batch.acceptedBy || "-"),
      detailItem("验收时间", formatDateTime(batch.acceptedAt)),
      detailItem("验收意见", batch.acceptanceComment || "-"),
      detailItem("质量状态", displayLabel(BATCH_QUALITY_STATUS_LABELS, batch.qualityStatus || "pending")),
      detailItem("发布风险", displayLabel(PUBLISH_RISK_LABELS, batch.publishRiskStatus || "unknown")),
      detailItem("审核建议", displayLabel(IMPORT_REVIEW_RECOMMENDATION_LABELS, batch.reviewRecommendation)),
      detailItem("创建人", batch.createdBy || "-"),
      detailItem("完成时间", formatDateTime(batch.completedAt || batch.createdAt)),
    ].join("");
    renderImportBatchWorkflowSteps(batch);
    renderImportBatchPermissionBoundary(batch);
    renderImportBatchReceiptSummary(batch);
    renderImportTraceList("#importedBlocksList", [], "正在加载林班明细...", () => "");
    renderImportTraceList("#importedRightsList", [], "正在加载林权明细...", () => "");
    loadImportBatchTargets(batch.id);
    renderImportBatchImageryLinks(batch);
    renderImportBatchDeliveryPackage(batch);
    renderImportBatchCoverageCheck(batch);
    renderImportBatchPublishReadiness(null);
    renderImportBatchOperationResult(null);
    renderImportBatchReviewEvents(batch);
    renderImportBatchAcceptanceEvents(batch);
    renderImportBatchAuditEvents(batch);
    const latestImageryLink = Array.isArray(batch.imageryLinks) ? batch.imageryLinks[batch.imageryLinks.length - 1] : null;
    if ($("#importBatchReviewDecision")) $("#importBatchReviewDecision").value = batch.reviewStatus && batch.reviewStatus !== "pending" ? batch.reviewStatus : "approved";
    if ($("#importBatchReviewComment")) $("#importBatchReviewComment").value = batch.reviewComment || "";
    if ($("#importBatchAcceptanceStatus")) $("#importBatchAcceptanceStatus").value = batch.acceptanceStatus || "pending";
    if ($("#importBatchAcceptanceComment")) $("#importBatchAcceptanceComment").value = batch.acceptanceComment || "";
    if ($("#batchSceneId")) $("#batchSceneId").value = latestImageryLink?.sceneId || "";
    if ($("#batchSceneRelationType")) $("#batchSceneRelationType").value = latestImageryLink?.relationType || "coverage";
    if (state.scenes.length) {
      renderBatchScenePreview();
    } else {
      loadBatchScenes({ silent: true });
    }
    $("#importBatchDetailOutput").textContent = stringifyPretty(batch, {});
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    applyActionPermissions();
    renderImportBatchRows();
    const downloadButton = $("#downloadImportBatchErrors");
    if (downloadButton && !downloadButton.classList.contains("permission-disabled")) {
      downloadButton.disabled = !Number(batch.invalidRows || 0);
    }
    const rollbackButton = $("#rollbackImportBatch");
    if (rollbackButton && !rollbackButton.classList.contains("permission-disabled")) {
      rollbackButton.disabled = ["rolled_back", "deleted"].includes(String(batch.status || ""));
    }
    const linkButton = $("#linkImportBatchSceneLayer");
    if (linkButton && !linkButton.classList.contains("permission-disabled")) {
      const reviewBlocked = batch.reviewStatus !== "approved";
      linkButton.disabled = ["rolled_back", "deleted"].includes(String(batch.status || "")) || !Number(batch.validRows || 0) || reviewBlocked;
      linkButton.title = reviewBlocked ? "批次需审核通过后才能关联影像图层" : "";
    }
    const preflightButton = $("#checkImportBatchPublishReadiness");
    if (preflightButton && !preflightButton.classList.contains("permission-disabled")) {
      preflightButton.disabled = ["rolled_back", "deleted"].includes(String(batch.status || "")) || !Number(batch.validRows || 0);
    }
    const reviewButton = $("#reviewImportBatch");
    if (reviewButton && !reviewButton.classList.contains("permission-disabled")) {
      reviewButton.disabled = ["rolled_back", "deleted"].includes(String(batch.status || ""));
    }
    const acceptanceButton = $("#updateImportBatchAcceptance");
    if (acceptanceButton && !acceptanceButton.classList.contains("permission-disabled")) {
      const reviewBlocked = batch.reviewStatus !== "approved";
      acceptanceButton.disabled = ["rolled_back", "deleted"].includes(String(batch.status || "")) || reviewBlocked;
      acceptanceButton.title = reviewBlocked ? "批次需审核通过后才能记录验收" : "";
    }
  }

  function closeImportBatchDetail() {
    $("#importBatchDetailPanel").classList.add("hidden");
    $("#importBatchDetailPanel").setAttribute("aria-hidden", "true");
  }

  function closeDeliveryPackageDetail() {
    $("#deliveryPackageDetailPanel")?.classList.add("hidden");
    $("#deliveryPackageDetailPanel")?.setAttribute("aria-hidden", "true");
  }

  function consumeInitialBatchSelection() {
    const targetId = String(initialBatchId || "").trim();
    if (!targetId) return;
    const matched = state.batches.find((batch) => String(batch.id || "") === targetId);
    if (!matched) return;
    state.activeBatchId = matched.id;
    initialBatchId = "";
  }

  function consumeInitialDeliveryPackageSelection() {
    const targetId = String(initialDeliveryBatchId || "").trim();
    if (!targetId) return;
    const matched = state.deliveryPackages.find((item) => String(item.batchId || "") === targetId);
    if (!matched) return;
    state.activeDeliveryBatchId = matched.batchId || targetId;
    initialDeliveryBatchId = "";
  }

  function consumeInitialQualityIssueSelection() {
    const targetId = String(initialQualityIssueId || "").trim();
    if (!targetId) return;
    const matched = state.qualityIssues.find((issue) => String(issue.issueId || "") === targetId);
    if (!matched) return;
    state.activeQualityIssueId = matched.issueId || targetId;
    if (matched.batchId && !state.activeBatchId) state.activeBatchId = matched.batchId;
    initialQualityIssueId = "";
  }

  async function loadImportBatches() {
    setStatus("busy", "正在加载入库批次...");
    pager.setBusy(true);
    try {
      const payload = await api(`/api/imports/forest-blocks/batches?${batchQuery()}`);
      if (pager.setTotal(payload.total ?? 0)) return loadImportBatches();
      state.batches = Array.isArray(payload.items) ? payload.items : [];
      consumeInitialBatchSelection();
      if (state.activeBatchId && !activeBatch()) state.activeBatchId = "";
      renderImportBatchRows();
      renderImportBatchDetail(activeBatch());
      loadImportWorkflowSummary();
      loadImportOperationQueue();
      loadDeliveryPackages();
      setStatus("online", `已加载 ${payload.total ?? state.batches.length} 个入库批次。`);
    } catch (error) {
      setStatus("offline", `入库批次加载失败：${error.message}`);
    } finally {
      pager.setBusy(false);
    }
  }

  function reloadImportBatchesFromFirstPage() {
    pager.reset();
    return loadImportBatches();
  }

  async function loadDeliveryPackages() {
    try {
      const payload = await api(`/api/imports/forest-blocks/delivery-packages?${deliveryPackageQuery()}`);
      state.deliveryPackages = Array.isArray(payload.items) ? payload.items : [];
      consumeInitialDeliveryPackageSelection();
      if (state.activeDeliveryBatchId && !activeDeliveryPackage()) state.activeDeliveryBatchId = "";
      renderDeliveryPackageRows();
      renderDeliveryPackageDetail(activeDeliveryPackage());
      renderImportBatchDeliveryPackage(activeBatch());
    } catch (error) {
      const body = $("#deliveryPackageRows");
      if (body) body.innerHTML = `<tr class="placeholder-row"><td colspan="6">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  async function loadImportAuditEvents() {
    try {
      const payload = await api(`/api/imports/forest-blocks/audit-events?${auditQuery()}`);
      state.auditEvents = Array.isArray(payload.items) ? payload.items : [];
      renderImportAuditEvents();
    } catch (error) {
      const body = $("#importAuditRows");
      if (body) body.innerHTML = `<tr class="placeholder-row"><td colspan="6">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  async function loadQualityIssues() {
    try {
      const payload = await api(`/api/imports/forest-blocks/quality-issues?${qualityIssueQuery()}`);
      state.qualityIssues = Array.isArray(payload.items) ? payload.items : [];
      consumeInitialQualityIssueSelection();
      renderQualityIssueRows();
    } catch (error) {
      const body = $("#qualityIssueRows");
      if (body) body.innerHTML = `<tr class="placeholder-row"><td colspan="8">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  async function updateQualityIssueStatus(issue, status) {
    if (!issue?.issueId || !status) return;
    const label = qualityIssueStatusLabel(status);
    const comment =
      typeof window.prompt === "function"
        ? window.prompt(`${label}\u5904\u7406\u610f\u89c1`, issue.handlingComment || "")
        : "";
    if (comment === null) return;
    setStatus("busy", "\u6b63\u5728\u66f4\u65b0\u8d28\u68c0\u95ee\u9898\u5904\u7406\u72b6\u6001...");
    try {
      const payload = await api(`/api/imports/forest-blocks/quality-issues/${encodeURIComponent(issue.issueId)}`, {
        method: "PATCH",
        body: JSON.stringify({ status, comment: comment || "" }),
      });
      if (payload.issue?.batchId) state.activeBatchId = payload.issue.batchId;
      await loadQualityIssues();
      await loadImportAuditEvents();
      await loadImportBatches();
      renderImportBatchDetail(activeBatch());
      setStatus("online", "\u8d28\u68c0\u95ee\u9898\u5904\u7406\u72b6\u6001\u5df2\u66f4\u65b0\u3002");
    } catch (error) {
      setStatus("offline", `\u8d28\u68c0\u95ee\u9898\u5904\u7406\u5931\u8d25\uff1a${error.message}`);
    }
  }

  function handleQualityIssueAction(event) {
    const button = event.target.closest("[data-quality-action]");
    if (!button) return false;
    event.preventDefault();
    event.stopPropagation();
    if (button.disabled) return true;
    const issue = state.qualityIssues.find((item) => String(item.issueId) === String(button.dataset.issueId));
    if (!issue) return true;
    state.activeQualityIssueId = issue.issueId || "";
    updateQualityIssueStatus(issue, button.dataset.qualityAction);
    return true;
  }

  async function deleteImportBatch(batch = activeBatch()) {
    if (!batch) return;
    setStatus("busy", "正在删除入库批次...");
    try {
      await api(`/api/imports/${encodeURIComponent(batch.id)}`, { method: "DELETE" });
      state.activeBatchId = "";
      closeImportBatchDetail();
      await loadImportBatches();
      await loadImportAuditEvents();
      await loadQualityIssues();
      setStatus("online", "入库批次已软删除。");
    } catch (error) {
      setStatus("offline", `入库批次删除失败：${error.message}`);
    }
  }

  async function restoreImportBatch(batch = activeBatch()) {
    if (!batch) return;
    setStatus("busy", "正在恢复入库批次...");
    try {
      await api(`/api/imports/${encodeURIComponent(batch.id)}/restore`, { method: "POST" });
      state.activeBatchId = batch.id;
      await loadImportBatches();
      await loadImportAuditEvents();
      await loadQualityIssues();
      renderImportBatchDetail(activeBatch());
      setStatus("online", "入库批次已恢复。");
    } catch (error) {
      setStatus("offline", `入库批次恢复失败：${error.message}`);
    }
  }

  function handleDeliveryPackageAction(event) {
    const button = event.target.closest("[data-delivery-action]");
    if (!button) return false;
    event.preventDefault();
    event.stopPropagation();
    if (button.disabled) return true;
    const row = button.closest("tr[data-delivery-batch-id]");
    const commandHost = button.closest("[data-batch-id]");
    const candidateBatchId = row?.dataset.deliveryBatchId || commandHost?.dataset.batchId || "";
    const item =
      state.deliveryPackages.find((candidate) => String(candidate.batchId || "") === String(candidateBatchId)) ||
      null;
    if (!item) return true;
    state.activeDeliveryBatchId = item.batchId || "";
    const action = button.dataset.deliveryAction;
    if (action === "view") {
      renderDeliveryPackageDetail(item);
    } else if (action === "delivery-package-receipt") {
      exportDeliveryPackageReceipt(item);
    } else if (action === "acceptance-receipt") {
      exportDeliveryPackageAcceptanceReceipt(item);
    } else if (action === "scene-delivery-receipt") {
      exportDeliveryPackageSceneReceipt(item, button.dataset.sceneId || primaryDeliverySceneId(item));
    }
    return true;
  }

  async function rollbackImportBatch(batch = activeBatch()) {
    if (!batch) return;
    setStatus("busy", "正在撤销本批次入库成果...");
    try {
      await api(`/api/imports/${encodeURIComponent(batch.id)}/rollback`, { method: "POST" });
      state.activeBatchId = batch.id;
      await loadImportBatches();
      await loadImportAuditEvents();
      await loadQualityIssues();
      renderImportBatchDetail(activeBatch());
      setStatus("online", "本批次新增林班已撤销入库。");
    } catch (error) {
      setStatus("offline", `入库批次撤销失败：${error.message}`);
    }
  }

  async function reviewImportBatch(batch = activeBatch()) {
    if (!batch) return;
    const decision = $("#importBatchReviewDecision")?.value || "approved";
    const comment = $("#importBatchReviewComment")?.value.trim() || "";
    setStatus("busy", "正在提交批次审核...");
    try {
      await api(`/api/imports/${encodeURIComponent(batch.id)}/review`, {
        method: "POST",
        body: JSON.stringify({ decision, comment }),
      });
      state.activeBatchId = batch.id;
      await loadImportBatches();
      await loadImportAuditEvents();
      await loadQualityIssues();
      renderImportBatchDetail(activeBatch());
      setStatus("online", "批次审核已记录。");
    } catch (error) {
      setStatus("offline", `批次审核失败：${error.message}`);
    }
  }

  async function updateImportBatchAcceptance(batch = activeBatch()) {
    if (!batch) return;
    const status = $("#importBatchAcceptanceStatus")?.value || "pending";
    const comment = $("#importBatchAcceptanceComment")?.value.trim() || "";
    setStatus("busy", "正在记录批次验收...");
    try {
      await api(`/api/imports/${encodeURIComponent(batch.id)}/acceptance`, {
        method: "POST",
        body: JSON.stringify({ status, comment }),
      });
      state.activeBatchId = batch.id;
      await loadImportBatches();
      await loadImportAuditEvents();
      await loadQualityIssues();
      renderImportBatchDetail(activeBatch());
      setStatus("online", "批次验收已记录。");
    } catch (error) {
      setStatus("offline", `批次验收失败：${error.message}`);
    }
  }

  async function downloadFile(path, filename, messages) {
    setStatus("busy", messages.busy);
    try {
      const response = await AdminCommon.fetchWithSession(path, {
        headers: AdminCommon.buildHeaders(),
      });
      if (!response.ok) {
        const payload = await response.text();
        throw new Error(`${response.status} ${payload || response.statusText}`);
      }
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
      return true;
    } catch (error) {
      setStatus("offline", `${messages.fail}：${error.message}`);
      return false;
    }
  }

  async function exportImportAuditEvents() {
    await downloadFile(
      `/api/imports/forest-blocks/audit-events.csv?${auditQuery()}`,
      "import-audit-events.csv",
      {
        busy: "正在导出成果入库审计 CSV...",
        done: "成果入库审计 CSV 已导出。",
        fail: "成果入库审计导出失败",
      },
    );
  }

  async function exportQualityIssues() {
    await downloadFile(
      `/api/imports/forest-blocks/quality-issues.csv?${qualityIssueQuery()}`,
      "import-quality-issues.csv",
      {
        busy: "正在导出成果质检问题 CSV...",
        done: "成果质检问题 CSV 已导出。",
        fail: "成果质检问题导出失败",
      },
    );
  }

  async function exportImportWorkflowSummary() {
    await downloadFile(
      "/api/imports/forest-blocks/workflow-summary.json",
      "import-workflow-summary.json",
      {
        busy: "正在导出成果入库摘要 JSON...",
        done: "成果入库摘要 JSON 已导出。",
        fail: "成果入库摘要导出失败",
      },
    );
  }

  async function exportDeliveryPackages() {
    await downloadFile(
      `/api/imports/forest-blocks/delivery-packages.csv?${deliveryPackageQuery()}`,
      "import-delivery-packages.csv",
      {
        busy: "正在导出成果交付包 CSV...",
        done: "成果交付包 CSV 已导出。",
        fail: "成果交付包导出失败",
      },
    );
  }

  async function exportDeliveryPackagesJson() {
    await downloadFile(
      `/api/imports/forest-blocks/delivery-packages.json?${deliveryPackageQuery()}`,
      "import-delivery-packages.json",
      {
        busy: "正在导出成果交付包 JSON 回执...",
        done: "成果交付包 JSON 回执已导出。",
        fail: "成果交付包 JSON 回执导出失败",
      },
    );
  }

  async function exportDeliveryPackageReceipt(item) {
    if (!item?.batchId) return;
    const batchId = item.batchId;
    const exported = await downloadFile(
      `/api/imports/${encodeURIComponent(batchId)}/delivery-package-receipt.json`,
      `import-delivery-package-receipt-${batchId}.json`,
      {
        busy: "正在导出交付包总回执...",
        done: "交付包总回执已导出，审计流已刷新。",
        fail: "交付包总回执导出失败",
      },
    );
    if (!exported) return;
    state.activeBatchId = batchId;
    state.activeDeliveryBatchId = batchId;
    await loadImportBatches();
    await loadDeliveryPackages();
    await loadImportAuditEvents();
    renderImportBatchDetail(activeBatch());
    renderDeliveryPackageDetail(activeDeliveryPackage());
    setStatus("online", "交付包总回执已导出，审计流已刷新。");
  }

  async function exportDeliveryPackageAcceptanceReceipt(item) {
    if (!item?.batchId) return;
    const batchId = item.batchId;
    const exported = await downloadFile(
      item.acceptanceReceiptUrl || `/api/imports/${encodeURIComponent(batchId)}/acceptance-receipt.json`,
      `import-acceptance-receipt-${batchId}.json`,
      {
        busy: "正在导出交付包验收回执...",
        done: "交付包验收回执已导出，审计流已刷新。",
        fail: "交付包验收回执导出失败",
      },
    );
    if (!exported) return;
    state.activeBatchId = batchId;
    state.activeDeliveryBatchId = batchId;
    await loadImportBatches();
    await loadDeliveryPackages();
    await loadImportAuditEvents();
    renderImportBatchDetail(activeBatch());
    renderDeliveryPackageDetail(activeDeliveryPackage());
    setStatus("online", "交付包验收回执已导出，审计流已刷新。");
  }

  function deliveryPackageSceneReceiptUrl(item, sceneId = primaryDeliverySceneId(item)) {
    const matchedReceipt = (item?.sceneDeliveryReceiptUrls || []).find(
      (receipt) => String(receipt?.sceneId || "") === String(sceneId || ""),
    );
    const matchedReceiptUrl = matchedReceipt?.url || matchedReceipt?.href || matchedReceipt?.receiptUrl || matchedReceipt?.deliveryReceiptUrl;
    const primarySceneDeliveryReceiptUrl = item ? item.primarySceneDeliveryReceiptUrl : "";
    return (
      matchedReceiptUrl ||
      primarySceneDeliveryReceiptUrl ||
      `/api/scenes/${encodeURIComponent(sceneId)}/delivery-receipt.json`
    );
  }

  async function exportDeliveryPackageSceneReceipt(item, sceneId = primaryDeliverySceneId(item)) {
    if (!item || !sceneId) {
      setStatus("offline", "该交付包暂无可导出的影像交付回执。");
      return;
    }
    const receiptUrl = deliveryPackageSceneReceiptUrl(item, sceneId);
    const exported = await downloadFile(receiptUrl, `scene-delivery-receipt-${sceneId}.json`, {
      busy: "正在导出影像交付回执...",
      done: "影像交付回执已导出，交付包状态已刷新。",
      fail: "影像交付回执导出失败",
    });
    if (!exported) return;
    state.activeBatchId = item.batchId || state.activeBatchId;
    state.activeDeliveryBatchId = item.batchId || state.activeDeliveryBatchId;
    await loadDeliveryPackages();
    await loadBatchScenes({ silent: true });
    renderImportBatchDetail(activeBatch());
    renderDeliveryPackageDetail(activeDeliveryPackage());
    setStatus("online", "影像交付回执已导出，交付包状态已刷新。");
  }

  async function exportImportBatchReceipt(batch = activeBatch()) {
    if (!batch) return;
    const exported = await downloadFile(
      `/api/imports/${encodeURIComponent(batch.id)}/acceptance-receipt.json`,
      `import-acceptance-receipt-${batch.id}.json`,
      {
        busy: "正在导出验收回执...",
        done: "验收回执已导出，导出事件已写入审计流。",
        fail: "验收回执导出失败",
      },
    );
    if (!exported) return;
    await loadImportBatches();
    await loadImportAuditEvents();
    renderImportBatchDetail(activeBatch());
    setStatus("online", "验收回执已导出，导出事件已写入审计流。");
  }

  async function downloadImportBatchErrors(batch = activeBatch()) {
    if (!batch) return;
    await downloadFile(
      `/api/imports/${encodeURIComponent(batch.id)}/errors.csv`,
      `import-errors-${batch.id}.csv`,
      {
        busy: "正在生成错误行 CSV...",
        done: "错误行 CSV 已生成。",
        fail: "错误行下载失败",
      },
    );
  }

  async function downloadImportBatchReport(batch = activeBatch()) {
    if (!batch) return;
    await downloadFile(
      `/api/imports/${encodeURIComponent(batch.id)}/report.json`,
      `import-report-${batch.id}.json`,
      {
        busy: "正在导出入库报告...",
        done: "入库报告 JSON 已导出。",
        fail: "入库报告导出失败",
      },
    );
  }

  async function checkImportBatchPublishReadiness(batch = activeBatch()) {
    if (!batch) return;
    const body = publishReadinessPayload();
    if (!body.sceneId) {
      setStatus("warning", "请先填写需要预检的影像/场景 ID。");
      renderImportBatchPublishReadiness({
        ready: false,
        linkedBlockCount: 0,
        publishLayer: true,
        blockingReasons: ["scene_required"],
        warnings: [],
        checks: [{ key: "scene_selected", status: "blocked", message: "missing" }],
        quality: {},
      });
      return;
    }
    setStatus("busy", "正在执行批次发布预检...");
    try {
      const readiness = await api(`/api/imports/${encodeURIComponent(batch.id)}/publish-readiness`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      renderImportBatchPublishReadiness(readiness);
      setStatus(readiness.ready ? "online" : "warning", readiness.ready ? "发布预检通过。" : "发布预检存在阻断项。");
    } catch (error) {
      renderImportBatchPublishReadiness(null);
      setStatus("offline", `发布预检失败：${error.message}`);
    }
  }

  async function linkImportBatchSceneLayer(batch = activeBatch()) {
    if (!batch) return;
    if (batch.reviewStatus !== "approved") {
      setStatus("warning", "批次需审核通过后才能关联影像图层。");
      return;
    }
    const sceneId = $("#batchSceneId")?.value.trim() || "";
    if (!sceneId) {
      setStatus("warning", "\u8bf7\u5148\u586b\u5199\u9700\u8981\u5173\u8054\u7684\u5f71\u50cf/\u573a\u666f ID\u3002");
      return;
    }
    const body = publishReadinessPayload();
    setStatus("busy", "\u6b63\u5728\u5173\u8054\u6279\u6b21\u5f71\u50cf\u5e76\u53d1\u5e03\u56fe\u5c42...");
    try {
      const payload = await api(`/api/imports/${encodeURIComponent(batch.id)}/link-scene-layer`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      state.activeBatchId = batch.id;
      await loadImportBatches();
      await loadImportAuditEvents();
      await loadQualityIssues();
      renderImportBatchDetail(activeBatch());
      renderImportBatchOperationResult(payload);
      setStatus("online", "\u6279\u6b21\u5f71\u50cf\u56fe\u5c42\u5df2\u5173\u8054\u53d1\u5e03\u3002");
    } catch (error) {
      setStatus("offline", `\u6279\u6b21\u5f71\u50cf\u5173\u8054\u5931\u8d25\uff1a${error.message}`);
    }
  }

  function handleBatchRowAction(event) {
    const batchButton = event.target.closest("[data-batch-action]");
    if (batchButton) {
      event.preventDefault();
      event.stopPropagation();
      if (batchButton.disabled) return true;
      const row = batchButton.closest("tr[data-id]");
      const batch = state.batches.find((item) => String(item.id) === String(row?.dataset.id)) || null;
      if (!batch) return true;
      state.activeBatchId = batch.id;
      if (batchButton.dataset.batchAction === "restore") {
        restoreImportBatch(batch);
      } else if (batchButton.dataset.batchAction === "report") {
        downloadImportBatchReport(batch);
      } else if (batchButton.dataset.batchAction === "receipt") {
        exportImportBatchReceipt(batch);
      } else if (batchButton.dataset.batchAction === "rollback") {
        rollbackImportBatch(batch);
      }
      return true;
    }
    const button = event.target.closest("[data-row-action]");
    if (!button) return false;
    event.stopPropagation();
    if (button.disabled) return true;
    const row = button.closest("tr[data-id]");
    const batch = state.batches.find((item) => String(item.id) === String(row?.dataset.id)) || null;
    if (!batch) return true;
    state.activeBatchId = batch.id;
    const action = button.dataset.rowAction;
    if (action === "delete") {
      deleteImportBatch(batch);
    } else {
      renderImportBatchDetail(batch);
    }
    return true;
  }

  function renderSources() {
    const body = $("#sourceRows");
    if (!state.sources.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="5">暂无待入库文件</td></tr>';
      return;
    }
    body.innerHTML = state.sources
      .map((item) => {
        const checked = item.path === state.selectedPath ? "checked" : "";
        return `
          <tr>
            <td><input type="radio" name="sourceFile" value="${escapeHtml(item.path)}" aria-label="选择成果文件：${escapeHtml(item.name || item.path)}" ${checked} /></td>
            <td><div class="cell-stack"><strong>${escapeHtml(item.fileName || "-")}</strong><small>${escapeHtml(item.path || "-")}</small></div></td>
            <td>${escapeHtml(item.fileType || "-")}</td>
            <td>${escapeHtml(formatBytes(item.sizeBytes))}</td>
            <td>${escapeHtml(formatDateTime(item.updatedAt))}</td>
          </tr>
        `;
      })
      .join("");
  }

  function renderReport(report) {
    $("#reportTotal").textContent = String(report?.totalRows ?? 0);
    $("#reportValid").textContent = String(report?.validRows ?? 0);
    $("#reportInvalid").textContent = String(report?.invalidRows ?? 0);
    $("#reportStatus").textContent = report?.status || "待导入";
    $("#reportOutput").textContent = JSON.stringify(report || {}, null, 2);
  }

  async function loadSources() {
    setStatus("busy", "正在扫描待入库文件...");
    try {
      const payload = await api("/api/imports/forest-blocks/sources");
      state.sources = Array.isArray(payload.items) ? payload.items : [];
      if (!state.sources.some((item) => item.path === state.selectedPath)) state.selectedPath = "";
      renderSources();
      $("#sourceStatus").textContent = `发现 ${payload.total ?? state.sources.length} 个可入库文件。`;
      setStatus("online", "待入库文件已刷新。");
    } catch (error) {
      setStatus("offline", `待入库文件加载失败：${error.message}`);
    }
  }

  async function importSelectedSource() {
    if (!state.selectedPath) {
      setStatus("warning", "请先选择一个待入库文件。");
      return;
    }
    setStatus("busy", "正在导入选中文件...");
    try {
      const report = await api("/api/imports/forest-blocks/sources/import", {
        method: "POST",
        body: JSON.stringify({ path: state.selectedPath, strategy: $("#importStrategy").value }),
      });
      renderReport(report);
      state.activeBatchId = report.id || "";
      await loadImportBatches();
      await loadImportAuditEvents();
      await loadQualityIssues();
      setStatus("online", "选中文件已入库。");
    } catch (error) {
      setStatus("offline", `选中文件导入失败：${error.message}`);
    }
  }

  async function uploadImport(event) {
    event.preventDefault();
    const file = $("#importFile").files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("strategy", $("#importStrategy").value);
    setStatus("busy", "正在上传并入库...");
    try {
      const response = await AdminCommon.fetchWithSession("/api/imports/forest-blocks", {
        method: "POST",
        body: formData,
      });
      const report = await response.json();
      if (!response.ok) throw new Error(`${response.status} ${report.detail || JSON.stringify(report)}`);
      renderReport(report);
      state.activeBatchId = report.id || "";
      await loadImportBatches();
      await loadImportAuditEvents();
      await loadQualityIssues();
      setStatus("online", "上传文件已入库。");
    } catch (error) {
      setStatus("offline", `上传导入失败：${error.message}`);
    }
  }

  function handleImportReceiptSummaryAction(event) {
    const button = event.target.closest("[data-receipt-action]");
    if (!button) return false;
    event.preventDefault();
    event.stopPropagation();
    if (button.disabled) return true;
    const action = button.dataset.receiptAction;
    const batch = activeBatch();
    if (action === "import-acceptance") {
      exportImportBatchReceipt(batch);
    }
    return true;
  }

  function initialize() {
    initShell();
    if (initialBatchId && $("#batchKeyword")) $("#batchKeyword").value = initialBatchId;
    if (initialBatchId && $("#deliveryPackageKeyword")) $("#deliveryPackageKeyword").value = initialBatchId;
    if (initialWorkflowQueue && $("#batchWorkflowQueueFilter")) $("#batchWorkflowQueueFilter").value = initialWorkflowQueue;
    if (initialQualityIssueStatus && $("#qualityIssueStatusFilter")) $("#qualityIssueStatusFilter").value = initialQualityIssueStatus;
    if (initialDeliveryPackageStatus && $("#deliveryPackageStatusFilter")) $("#deliveryPackageStatusFilter").value = initialDeliveryPackageStatus;
    if (initialQualityIssueId) {
      if ($("#qualityIssueKeyword")) $("#qualityIssueKeyword").value = initialQualityIssueId;
      if (initialBatchId && $("#qualityIssueBatchFilter")) $("#qualityIssueBatchFilter").value = initialBatchId;
    }
    pager = createLedgerPager({ anchor: $("#importBatchRows").closest(".table-wrap"), onPageChange: loadImportBatches });
    setCompoundPermission("#linkImportBatchSceneLayer", IMPORT_SCENE_LAYER_LINK_PERMISSION, IMPORT_MAP_LAYER_REQUIRED_PERMISSION, IMPORT_MAP_LAYER_UPSERT_PERMISSIONS);
    setCompoundPermission("#checkImportBatchPublishReadiness", IMPORT_SCENE_LAYER_LINK_PERMISSION, IMPORT_MAP_LAYER_REQUIRED_PERMISSION, IMPORT_MAP_LAYER_UPSERT_PERMISSIONS);
    $("#reviewImportBatch")?.setAttribute("data-permission", IMPORT_REVIEW_PERMISSION);
    $("#updateImportBatchAcceptance")?.setAttribute("data-permission", IMPORT_ACCEPTANCE_PERMISSION);
    $("#rollbackImportBatch")?.setAttribute("data-permission", IMPORT_ROLLBACK_PERMISSION);
    $("#downloadImportBatchErrors")?.setAttribute("data-permission", IMPORT_EXPORT_PERMISSION);
    $("#downloadImportBatchReport")?.setAttribute("data-permission", IMPORT_EXPORT_PERMISSION);
    $("#downloadImportBatchReceipt")?.setAttribute("data-permission", IMPORT_EXPORT_PERMISSION);
    $("#exportImportAuditEvents")?.setAttribute("data-permission", IMPORT_EXPORT_PERMISSION);
    $("#exportQualityIssues")?.setAttribute("data-permission", IMPORT_EXPORT_PERMISSION);
    $("#exportImportWorkflowSummary")?.setAttribute("data-permission", IMPORT_EXPORT_PERMISSION);
    $("#exportDeliveryPackages")?.setAttribute("data-permission", IMPORT_EXPORT_PERMISSION);
    $("#exportDeliveryPackagesJson")?.setAttribute("data-permission", IMPORT_EXPORT_PERMISSION);
    $("#importSelectedSource")?.setAttribute("data-permission", IMPORT_CREATE_PERMISSION);
    $("#refreshImportWorkflowSummary")?.addEventListener("click", loadImportWorkflowSummary);
    $("#refreshImportOperationQueue")?.addEventListener("click", loadImportOperationQueue);
    $("#exportImportWorkflowSummary")?.addEventListener("click", exportImportWorkflowSummary);
    $("#refreshDeliveryPackages")?.addEventListener("click", loadDeliveryPackages);
    $("#exportDeliveryPackages")?.addEventListener("click", exportDeliveryPackages);
    $("#exportDeliveryPackagesJson")?.addEventListener("click", exportDeliveryPackagesJson);
    $("#refreshImportBatches").addEventListener("click", loadImportBatches);
    $("#refreshImportAuditEvents").addEventListener("click", loadImportAuditEvents);
    $("#exportImportAuditEvents")?.addEventListener("click", exportImportAuditEvents);
    $("#refreshQualityIssues").addEventListener("click", loadQualityIssues);
    $("#exportQualityIssues")?.addEventListener("click", exportQualityIssues);
    $("#refreshSources").addEventListener("click", loadSources);
    $("#refreshBatchScenes").addEventListener("click", () => loadBatchScenes());
    $("#importSelectedSource").addEventListener("click", importSelectedSource);
    $("#importForm").addEventListener("submit", uploadImport);
    $("#closeImportBatchDetail").addEventListener("click", closeImportBatchDetail);
    $("#closeDeliveryPackageDetail")?.addEventListener("click", closeDeliveryPackageDetail);
    $("#rollbackImportBatch").addEventListener("click", () => rollbackImportBatch(activeBatch()));
    $("#reviewImportBatch").addEventListener("click", () => reviewImportBatch(activeBatch()));
    $("#updateImportBatchAcceptance")?.addEventListener("click", () => updateImportBatchAcceptance(activeBatch()));
    $("#downloadImportBatchErrors").addEventListener("click", () => downloadImportBatchErrors(activeBatch()));
    $("#downloadImportBatchReport").addEventListener("click", () => downloadImportBatchReport(activeBatch()));
    $("#downloadImportBatchReceipt")?.addEventListener("click", () => exportImportBatchReceipt(activeBatch()));
    $("#importBatchReceiptSummary")?.addEventListener("click", handleImportReceiptSummaryAction);
    $("#linkImportBatchSceneLayer").addEventListener("click", () => linkImportBatchSceneLayer(activeBatch()));
    $("#checkImportBatchPublishReadiness").addEventListener("click", () => checkImportBatchPublishReadiness(activeBatch()));
    $("#batchSceneId").addEventListener("input", () => renderBatchScenePreview());
    $("#batchSceneId").addEventListener("input", () => renderImportBatchPublishReadiness(null));
    $("#batchSceneKeyword").addEventListener("input", () => window.setTimeout(() => loadBatchScenes({ silent: true }), 220));
    ["#batchKeyword", "#batchStatusFilter", "#batchReviewStatusFilter", "#batchAcceptanceStatusFilter", "#batchWorkflowQueueFilter", "#batchSceneIdFilter", "#batchQualityStatusFilter", "#batchPublishRiskStatusFilter"].forEach((selector) => {
      $(selector).addEventListener("input", () => {
        window.clearTimeout(batchFilterTimer);
        batchFilterTimer = window.setTimeout(reloadImportBatchesFromFirstPage, 180);
      });
    });
    $("#batchAcceptanceStatusFilter")?.addEventListener("change", reloadImportBatchesFromFirstPage);
    ["#deliveryPackageKeyword", "#deliveryPackageBlockFilter"].forEach((selector) => {
      $(selector)?.addEventListener("input", () => window.setTimeout(loadDeliveryPackages, 180));
    });
    ["#deliveryPackageStatusFilter", "#deliveryPackageAcceptanceFilter", "#deliveryPackageDeliveryFilter"].forEach((selector) => {
      $(selector)?.addEventListener("change", loadDeliveryPackages);
    });
    ["#importAuditActionFilter", "#importAuditBatchFilter"].forEach((selector) => {
      $(selector).addEventListener("input", () => window.setTimeout(loadImportAuditEvents, 180));
    });
    ["#qualityIssueKeyword", "#qualityIssueTypeFilter", "#qualityIssueSeverityFilter", "#qualityIssueBatchFilter"].forEach((selector) => {
      $(selector).addEventListener("input", () => window.setTimeout(loadQualityIssues, 180));
    });
    $("#qualityIssueStatusFilter")?.addEventListener("change", loadQualityIssues);
    $("#includeDeletedImportBatches").addEventListener("change", reloadImportBatchesFromFirstPage);
    $("#includeDeletedImportAuditEvents")?.addEventListener("change", loadImportAuditEvents);
    $("#includeDeletedQualityIssues")?.addEventListener("change", loadQualityIssues);
    $("#qualityIssueRows")?.addEventListener("click", (event) => {
      if (handleQualityIssueAction(event)) return;
      const row = event.target.closest("tr[data-issue-id]");
      if (!row) return;
      state.activeQualityIssueId = row.dataset.issueId;
      const issue = state.qualityIssues.find((item) => String(item.issueId || "") === String(row.dataset.issueId)) || null;
      if (issue?.batchId) {
        state.activeBatchId = issue.batchId;
        renderImportBatchDetail(activeBatch());
      }
      renderQualityIssueRows();
    });
    $("#importBatchRows").addEventListener("click", (event) => {
      if (handleBatchRowAction(event)) return;
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      state.activeBatchId = row.dataset.id;
      renderImportBatchDetail(activeBatch());
      renderDeliveryPackageRows();
    });
    $("#deliveryPackageRows")?.addEventListener("click", (event) => {
      if (handleDeliveryPackageAction(event)) return;
      if (event.target.closest("a")) return;
      const row = event.target.closest("tr[data-delivery-batch-id]");
      if (!row) return;
      state.activeDeliveryBatchId = row.dataset.deliveryBatchId;
      renderDeliveryPackageRows();
      renderDeliveryPackageDetail(activeDeliveryPackage());
    });
    $("#deliveryPackageReceiptList")?.addEventListener("click", handleDeliveryPackageAction);
    $("#deliveryPackageClosureSummary")?.addEventListener("click", handleDeliveryPackageAction);
    $("#importOperationQueueRows")?.addEventListener("click", handleOperationQueueAction);
    $("#sourceRows").addEventListener("change", (event) => {
      if (event.target.name === "sourceFile") state.selectedPath = event.target.value;
    });
    renderReport(null);
    loadImportWorkflowSummary();
    loadImportOperationQueue();
    loadDeliveryPackages();
    loadImportBatches();
    loadImportAuditEvents();
    loadQualityIssues();
    loadSources();
    loadBatchScenes({ silent: true });
  }

  initialize();
})();
