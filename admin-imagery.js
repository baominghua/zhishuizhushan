(() => {
  const {
    $,
    api,
    applyActionPermissions,
    createLedgerPager,
    escapeHtml,
    formatDateTime,
    initShell,
    query,
    setStatus,
    splitValues,
    stringifyPretty,
  } = AdminCommon;

  const PAGE_PERMISSION = "imagery.scenes.view";
  const IMAGERY_SCENE_CREATE_PERMISSION = "imagery.scenes.create";
  const IMAGERY_SCENE_UPDATE_PERMISSION = "imagery.scenes.update";
  const IMAGERY_SCENE_DELETE_PERMISSION = "imagery.scenes.delete";
  const IMAGERY_SCENE_RESTORE_PERMISSION = "imagery.scenes.restore";
  const IMAGERY_SCENE_ARCHIVE_PERMISSION = "imagery.scenes.archive";
  const IMAGERY_SCENE_QUALITY_PERMISSION = "imagery.scenes.quality";
  const IMAGERY_SCENE_DELIVERY_PERMISSION = "imagery.scenes.delivery";
  const IMAGERY_SCENE_EXPORT_PERMISSION = "imagery.scenes.export";
  const IMAGERY_TASK_RETRY_PERMISSION = "imagery.tasks.retry";
  const IMAGERY_TASK_CANCEL_PERMISSION = "imagery.tasks.cancel";
  const IMAGERY_TASK_ARCHIVE_PERMISSION = "imagery.tasks.archive";
  const IMAGERY_LAYER_PUBLISH_PERMISSION = "imagery.layers.publish";
  const IMAGERY_MAP_LAYER_REQUIRED_PERMISSION = "map.layers.publish";
  const IMAGERY_MAP_LAYER_UPSERT_PERMISSIONS = "map.layers.create map.layers.update";
  const state = {
    scenes: [],
    tasks: [],
    sceneEvents: [],
    taskEvents: [],
    imageryIssues: [],
    sceneImportBatches: {},
    workflowSummary: null,
    operationQueue: null,
    activeId: "",
    activeTaskId: "",
    activeImageryIssueId: "",
  };
  let pager;
  let sceneFilterTimer;
  let initialSceneId = new URLSearchParams(window.location.search).get("sceneId") || "";
  let initialTaskId = new URLSearchParams(window.location.search).get("taskId") || "";
  let initialImageryIssueId = new URLSearchParams(window.location.search).get("imageryIssueId") || "";
  let initialPublished = new URLSearchParams(window.location.search).get("published") || "";
  let initialTaskStatus = new URLSearchParams(window.location.search).get("taskStatus") || "";
  let initialImageryIssueStatus = new URLSearchParams(window.location.search).get("imageryIssueStatus") || "";
  const RESTORE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.4-6.4"></path><path d="M18 3v5h-5"></path><path d="M21 12a9 9 0 0 1-15.4 6.4"></path><path d="M6 21v-5h5"></path></svg>';
  const ARCHIVE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 8v13H3V8"></path><path d="M1 3h22v5H1Z"></path><path d="M10 12h4"></path></svg>';
  const PUBLISH_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12"></path><path d="m7 8 5-5 5 5"></path><path d="M5 17v3h14v-3"></path></svg>';
  const RECEIPT_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l5 5v13H7Z"></path><path d="M14 3v5h5"></path><path d="M10 13h6"></path><path d="M10 17h4"></path></svg>';
  const INVESTIGATING_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 0 1 14-5.3"></path><path d="M18 3v5h-5"></path><path d="M20 12a8 8 0 0 1-14 5.3"></path><path d="M6 21v-5h5"></path></svg>';
  const RESOLVED_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"></path></svg>';
  const IGNORED_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>';

  function setCompoundPermission(selector, primaryPermission, allPermissions = "", anyPermissions = "") {
    const element = $(selector);
    if (!element) return;
    element.setAttribute("data-permission", primaryPermission);
    element.setAttribute("data-permission-all", allPermissions);
    element.setAttribute("data-permission-any", anyPermissions);
  }
  const ISSUE_STATUS_LABELS = {
    open: "\u5f85\u5904\u7406",
    investigating: "\u5904\u7406\u4e2d",
    resolved: "\u5df2\u89e3\u51b3",
    ignored: "\u5df2\u5ffd\u7565",
  };
  const SCENE_STATUS_LABELS = {
    active: "在库",
    archived: "已归档",
    deleted: "已删除",
    published: "已发布",
  };
  const DELIVERY_STATUS_LABELS = {
    pending: "待交付",
    delivered: "已交付",
    needs_correction: "需整改",
    rejected: "交付驳回",
  };
  const WORKFLOW_SUMMARY_KEY_LABELS = {
    unpublishedScenes: "影像发布队列",
    failedTasks: "失败任务队列",
    runningTasks: "运行任务队列",
    blockedImageryIssues: "影像问题队列",
  };
  const IMAGERY_OPERATION_QUEUE_LABELS = {
    failed_tasks: "转换失败",
    quality_issues: "质检问题",
    awaiting_publish: "待发布",
    awaiting_delivery: "待交付",
    ready: "已闭环",
  };
  const TASK_STATUS_LABELS = {
    queued: "排队中",
    running: "处理中",
    completed: "已完成",
    failed: "失败",
    canceled: "已取消",
  };
  const IMAGERY_ISSUE_TYPE_LABELS = {
    task_failure: "任务失败",
    task_canceled: "任务取消",
    missing_bounds: "缺少边界",
    missing_cog_path: "缺少 COG",
    transfer_failed: "传输失败",
  };
  const ISSUE_SEVERITY_LABELS = {
    blocked: "阻断",
    warning: "预警",
    info: "提示",
  };
  const BATCH_STATUS_LABELS = {
    completed: "已完成",
    deleted: "已删除",
    rolled_back: "已回滚",
    failed: "失败",
    pending: "待处理",
  };
  const PUBLISH_RISK_LABELS = {
    unknown: "待预检",
    ready: "可发布",
    warning: "需复核",
    blocked: "阻断",
  };
  const MAP_LAYER_SOURCE_TYPE_LABELS = {
    importBatch: "入库批次",
    imagery: "影像成果",
    manual: "手工维护",
  };
  const SCENE_LIFECYCLE_ACTION_LABELS = {
    "metadata-update": "元数据更新",
    "soft-delete": "删除影像",
    archive: "归档影像",
    restore: "恢复影像",
    "export-delivery-receipt": "导出交付回执",
  };
  const SCENE_EVENT_TYPE_LABELS = {
    publish: "发布",
    lifecycle: "生命周期",
    quality: "质量",
    delivery: "交付",
  };
  const SCENE_EVENT_ACTION_LABELS = {
    "publish-layer": "发布图层",
    delivery: "交付确认",
    "quality-issue-update": "质检处理",
    ...SCENE_LIFECYCLE_ACTION_LABELS,
  };

  function activeScene() {
    return state.scenes.find((scene) => String(scene.id) === String(state.activeId)) || null;
  }

  function activeTask() {
    return state.tasks.find((task) => String(task.id) === String(state.activeTaskId)) || null;
  }

  function formatBytes(bytes) {
    const numeric = Number(bytes);
    if (!Number.isFinite(numeric)) return "-";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = numeric;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
      value /= 1024;
      index += 1;
    }
    return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
  }

  function displayLabel(map, value, fallback = "-") {
    const key = String(value || "").trim();
    if (!key) return fallback;
    return map[key] || key;
  }

  function workflowSummaryKeyLabel(key) {
    return displayLabel(WORKFLOW_SUMMARY_KEY_LABELS, key, "业务指标");
  }

  function imageryOperationQueueLabel(key) {
    return displayLabel(IMAGERY_OPERATION_QUEUE_LABELS, key, "待处理");
  }

  function imageryOperationMetaLabel(value) {
    const key = String(value || "").trim();
    if (!key) return "-";
    const maps = [DELIVERY_STATUS_LABELS, TASK_STATUS_LABELS, ISSUE_STATUS_LABELS, SCENE_STATUS_LABELS, PUBLISH_RISK_LABELS];
    for (const map of maps) {
      if (Object.prototype.hasOwnProperty.call(map, key)) return map[key];
    }
    return key;
  }

  function workflowSummaryCardHref(card = {}) {
    return card.href || "#";
  }

  function workflowSummaryCardActionLabel(card = {}) {
    return workflowSummaryCardHref(card) === "#" ? "暂无队列" : "查看队列";
  }

  function sceneEventDisplayLabel(event) {
    const typeLabel = displayLabel(SCENE_EVENT_TYPE_LABELS, event.eventType, "事件");
    const actionLabel = displayLabel(SCENE_EVENT_ACTION_LABELS, event.action, event.action || "-");
    return `${typeLabel} · ${actionLabel}`;
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

  function renderImageryWorkflowSummary() {
    const target = $("#imageryWorkflowSummary");
    if (!target) return;
    target.innerHTML = renderWorkflowSummaryCards(state.workflowSummary);
  }

  async function loadImageryWorkflowSummary() {
    try {
      state.workflowSummary = await api("/api/scenes/workflow-summary");
      renderImageryWorkflowSummary();
    } catch (error) {
      const target = $("#imageryWorkflowSummary");
      if (target) {
        target.innerHTML = `<article class="workflow-summary-card tone-danger"><span>摘要加载失败</span><strong>!</strong><small>${escapeHtml(error.message)}</small></article>`;
      }
    }
  }

  function imageryOperationQueueToneClass(tone) {
    return tone ? `tone-${tone}` : "";
  }

  function imageryOperationQueuePillClass(key) {
    if (key === "ready") return "complete";
    if (key === "failed_tasks" || key === "quality_issues") return "missing";
    if (key === "awaiting_delivery") return "review";
    return "partial";
  }

  function imageryOperationQueueActionAttributes(item = {}, lane = {}) {
    const requiredPermission = item.requiredPermission || lane.requiredPermission || "";
    const allPermissions = item.allPermissions || lane.allPermissions || "";
    const anyPermissions = item.anyPermissions || lane.anyPermissions || "";
    return [
      requiredPermission ? `data-permission="${escapeHtml(requiredPermission)}"` : "",
      allPermissions ? `data-permission-all="${escapeHtml(allPermissions)}"` : "",
      anyPermissions ? `data-permission-any="${escapeHtml(anyPermissions)}"` : "",
    ]
      .filter(Boolean)
      .join(" ");
  }

  function imageryOperationQueueItem(item = {}, lane = {}) {
    const sceneId = item.sceneId || "";
    const taskId = item.taskId || "";
    const issueId = item.issueId || "";
    const title = item.name || item.sceneName || item.taskName || item.fileName || issueId || taskId || sceneId || "-";
    const meta = [sceneId, taskId, item.issueType, item.deliveryStatus, item.status].filter(Boolean);
    const actionAttrs = imageryOperationQueueActionAttributes(item, lane);
    return `
      <article class="operation-queue-row" data-imagery-operation-key="${escapeHtml(lane.key || "")}" data-scene-id="${escapeHtml(sceneId)}" data-task-id="${escapeHtml(taskId)}" data-issue-id="${escapeHtml(issueId)}">
        <div class="cell-stack">
          <strong>${traceLink(item.adminHref || lane.href || "admin-imagery.html", title)}</strong>
          <small>${escapeHtml(item.fileName || item.message || "-")}</small>
        </div>
        <div class="operation-queue-meta">
          ${meta.map((value) => `<span>${escapeHtml(imageryOperationMetaLabel(value))}</span>`).join("") || "<span>-</span>"}
        </div>
        <p>${escapeHtml(item.actionRequired || item.message || lane.label || "等待下一步处理")}</p>
        <button type="button" class="button-ghost" data-imagery-operation-action="open" data-imagery-operation-key="${escapeHtml(lane.key || "")}" data-scene-id="${escapeHtml(sceneId)}" data-task-id="${escapeHtml(taskId)}" data-issue-id="${escapeHtml(issueId)}" data-href="${escapeHtml(item.adminHref || lane.href || "admin-imagery.html")}" ${actionAttrs}>
          ${escapeHtml(lane.primaryActionLabel || "打开台账")}
        </button>
      </article>
    `;
  }

  function renderImageryOperationQueue() {
    const target = $("#imageryOperationQueueRows");
    if (!target) return;
    const lanes = Array.isArray(state.operationQueue?.items) ? state.operationQueue.items : [];
    if (!lanes.length) {
      target.innerHTML = '<article class="operation-queue-item"><div><span>暂无队列</span><strong>0</strong><small>后台暂无影像运维待办</small></div></article>';
      return;
    }
    target.innerHTML = lanes
      .map((lane) => {
        const items = Array.isArray(lane.items) ? lane.items : [];
        const itemHtml = items.length
          ? items.map((item) => imageryOperationQueueItem(item, lane)).join("")
          : '<p class="trace-empty">当前队列暂无影像待办。</p>';
        return `
          <section class="operation-queue-item ${imageryOperationQueueToneClass(lane.tone)}" data-imagery-operation-key="${escapeHtml(lane.key || "")}">
            <div class="operation-queue-head">
              <div>
                <span>${escapeHtml(lane.label || lane.key || "-")}</span>
                <strong>${escapeHtml(lane.count ?? 0)}</strong>
                <small>${escapeHtml(lane.description || "")}</small>
              </div>
              <span class="status-pill ${imageryOperationQueuePillClass(lane.key)}">${escapeHtml(imageryOperationQueueLabel(lane.key))}</span>
            </div>
            <div class="operation-queue-list">${itemHtml}</div>
            <a class="workflow-summary-link" href="${escapeHtml(lane.href || "#")}">查看全部</a>
          </section>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  async function loadImageryOperationQueue() {
    try {
      state.operationQueue = await api("/api/scenes/operation-queue?limit=3");
      renderImageryOperationQueue();
    } catch (error) {
      const target = $("#imageryOperationQueueRows");
      if (target) {
        target.innerHTML = `<article class="operation-queue-item tone-danger"><div><span>队列加载失败</span><strong>!</strong><small>${escapeHtml(error.message)}</small></div></article>`;
      }
    }
  }

  async function openImageryOperationQueueItem(laneKey, sceneId, taskId, issueId, href = "") {
    if (laneKey === "failed_tasks" && $("#taskStatusFilter")) $("#taskStatusFilter").value = "failed";
    if (laneKey === "quality_issues" && $("#imageryIssueStatusFilter")) $("#imageryIssueStatusFilter").value = "open";
    if (laneKey === "awaiting_publish" && $("#scenePublishedFilter")) $("#scenePublishedFilter").value = "false";
    if (laneKey === "ready" && $("#sceneDeliveryStatusFilter")) $("#sceneDeliveryStatusFilter").value = "delivered";
    if (sceneId && $("#sceneKeyword")) $("#sceneKeyword").value = sceneId;
    if (taskId && $("#taskEventTaskFilter")) $("#taskEventTaskFilter").value = taskId;
    if (taskId && $("#imageryIssueTaskFilter")) $("#imageryIssueTaskFilter").value = taskId;
    if (issueId && $("#imageryIssueKeyword")) $("#imageryIssueKeyword").value = issueId;
    state.activeId = sceneId || state.activeId;
    state.activeTaskId = taskId || state.activeTaskId;
    state.activeImageryIssueId = issueId || state.activeImageryIssueId;
    await loadScenes();
    await loadTasks();
    await loadImageryIssues();
    const targetSelector = laneKey === "failed_tasks" ? "#taskRows" : laneKey === "quality_issues" ? "#imageryIssueRows" : "#imageryRows";
    $(targetSelector)?.scrollIntoView({ block: "start", behavior: "smooth" });
    setStatus("online", href ? "已打开对应影像队列筛选。" : "已打开影像队列筛选。");
  }

  function handleImageryOperationQueueAction(event) {
    const button = event.target.closest("[data-imagery-operation-action]");
    if (!button) return false;
    event.preventDefault();
    if (button.disabled) return true;
    if (button.dataset.imageryOperationAction === "open") {
      openImageryOperationQueueItem(
        button.dataset.imageryOperationKey || "",
        button.dataset.sceneId || "",
        button.dataset.taskId || "",
        button.dataset.issueId || "",
        button.dataset.href || ""
      );
    }
    return true;
  }

  function traceLink(href, label) {
    return `<a class="trace-link" href="${escapeHtml(href)}">${escapeHtml(label)}</a>`;
  }

  function isDeletedScene(scene) {
    return Boolean(scene?.deletedAt) || scene?.status === "deleted";
  }

  function isArchivedScene(scene) {
    return scene?.status === "archived";
  }

  function canCancelTask(task) {
    return task?.status === "queued" && !task?.archivedAt;
  }

  function canRetryTask(task) {
    return task?.status === "failed" && !task?.archivedAt;
  }

  function canArchiveTask(task) {
    return ["completed", "failed", "canceled"].includes(String(task?.status || "")) && !task?.archivedAt;
  }

  function sceneActionButtons(scene) {
    if (isDeletedScene(scene)) {
      return `
      <div class="row-actions" aria-label="影像操作">
        <button type="button" class="icon-button" data-row-action="view" aria-label="查看影像" title="查看影像">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>
        </button>
        <button type="button" class="icon-button" data-scene-action="restore" data-permission="${IMAGERY_SCENE_RESTORE_PERMISSION}" aria-label="恢复影像" title="恢复影像">${RESTORE_ICON}</button>
      </div>
    `;
    }
    if (isArchivedScene(scene)) {
      return `
        <div class="row-actions" aria-label="影像操作">
          <button type="button" class="icon-button" data-row-action="view" aria-label="查看影像" title="查看影像">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>
          </button>
          <button type="button" class="icon-button" data-row-action="edit" data-permission="${IMAGERY_SCENE_UPDATE_PERMISSION}" aria-label="编辑影像" title="编辑影像">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 20 9-9-4-4-9 9-2 6Z"></path><path d="m15 8 1-1a2.8 2.8 0 0 1 4 4l-1 1"></path></svg>
          </button>
          <button type="button" class="icon-button danger" data-row-action="delete" data-permission="${IMAGERY_SCENE_DELETE_PERMISSION}" aria-label="删除影像" title="删除影像">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="m19 6-1 14H6L5 6"></path><path d="M10 11v5"></path><path d="M14 11v5"></path></svg>
          </button>
        </div>
      `;
    }
    return `
      <div class="row-actions row-actions-extra-wide" aria-label="影像操作">
        <button type="button" class="icon-button" data-row-action="view" aria-label="查看影像" title="查看影像">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>
        </button>
        <button type="button" class="icon-button" data-row-action="edit" data-permission="${IMAGERY_SCENE_UPDATE_PERMISSION}" aria-label="编辑影像" title="编辑影像">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 20 9-9-4-4-9 9-2 6Z"></path><path d="m15 8 1-1a2.8 2.8 0 0 1 4 4l-1 1"></path></svg>
        </button>
        <button type="button" class="icon-button" data-scene-action="publish-layer" data-permission="${IMAGERY_LAYER_PUBLISH_PERMISSION}" data-permission-all="${IMAGERY_MAP_LAYER_REQUIRED_PERMISSION}" data-permission-any="${IMAGERY_MAP_LAYER_UPSERT_PERMISSIONS}" aria-label="发布图层" title="发布图层">${PUBLISH_ICON}</button>
        <button type="button" class="icon-button" data-scene-action="publication-receipt" data-permission="${IMAGERY_SCENE_EXPORT_PERMISSION}" aria-label="\u5bfc\u51fa\u53d1\u5e03\u56de\u6267" title="\u5bfc\u51fa\u53d1\u5e03\u56de\u6267">${RECEIPT_ICON}</button>
        <button type="button" class="icon-button" data-scene-action="delivery-receipt" data-permission="${IMAGERY_SCENE_EXPORT_PERMISSION}" aria-label="导出交付回执" title="导出交付回执">${RECEIPT_ICON}</button>
        <button type="button" class="icon-button" data-scene-action="archive" data-permission="${IMAGERY_SCENE_ARCHIVE_PERMISSION}" aria-label="归档影像" title="归档影像">${ARCHIVE_ICON}</button>
        <button type="button" class="icon-button danger" data-row-action="delete" data-permission="${IMAGERY_SCENE_DELETE_PERMISSION}" aria-label="删除影像" title="删除影像">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="m19 6-1 14H6L5 6"></path><path d="M10 11v5"></path><path d="M14 11v5"></path></svg>
        </button>
      </div>
    `;
  }

  function renderRows() {
    const body = $("#imageryRows");
    if (!state.scenes.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无影像记录</td></tr>';
      return;
    }
    body.innerHTML = state.scenes
      .map((scene) => {
        const active = String(scene.id) === String(state.activeId) ? "active" : "";
        return `
          <tr data-id="${escapeHtml(scene.id)}" class="${active}">
            <td><div class="cell-stack"><strong>${escapeHtml(scene.name || scene.id)}</strong><small>${escapeHtml(scene.fileName || scene.id)} · ${escapeHtml(formatBytes(scene.size))}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(scene.projectId || "未分项目")}</strong><small>${escapeHtml(scene.areaCode || "未分区域")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(scene.satellite || "-")}</strong><small>${escapeHtml(scene.sensor || "-")}</small></div></td>
            <td>${escapeHtml(scene.capturedAt || "-")}</td>
            <td><div class="cell-stack"><span class="status-pill">${escapeHtml(displayLabel(SCENE_STATUS_LABELS, scene.status || scene.storage || scene.source || "COG"))}</span><small>${escapeHtml(displayLabel(DELIVERY_STATUS_LABELS, scene.deliveryStatus || "pending"))}</small></div></td>
            <td>${sceneActionButtons(scene)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  function detailItem(label, value) {
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "未填")}</dd></div>`;
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

  function sceneHasPublishedLayer(scene) {
    return Boolean(scene?.publishedLayerId || scene?.publishedLayerRecordCode || scene?.status === "published");
  }

  function sceneHasOpenQualityIssue(scene) {
    const events = [
      ...(Array.isArray(scene?.qualityEvents) ? scene.qualityEvents : []),
      ...(Array.isArray(scene?.qualityIssues) ? scene.qualityIssues : []),
    ];
    return events.some((event) => !["resolved", "ignored", "closed"].includes(String(event.status || "")));
  }

  function sceneCogState(scene) {
    if (["failed", "error"].includes(String(scene?.transferStatus || scene?.taskStatus || ""))) return "blocked";
    if (scene?.cogPath || scene?.tileUrl || scene?.tileJsonUrl || scene?.transferStatus === "cog-ready") return "complete";
    return "pending";
  }

  function sceneDeliveryState(scene) {
    const status = String(scene?.deliveryStatus || "pending");
    if (status === "delivered") return "complete";
    if (status === "rejected") return "blocked";
    if (status === "needs_correction") return "warning";
    return "pending";
  }

  function sceneWorkflowSteps(scene) {
    return [
      {
        key: "catalog",
        label: "影像入库",
        state: isDeletedScene(scene) ? "blocked" : "complete",
        meta: scene?.id || "未选择影像",
      },
      {
        key: "cog",
        label: "COG 切片",
        state: sceneCogState(scene),
        meta: scene?.transferStatus || scene?.storage || scene?.source || "等待转换",
      },
      {
        key: "quality",
        label: "质量核验",
        state: sceneHasOpenQualityIssue(scene) ? "warning" : "complete",
        meta: sceneHasOpenQualityIssue(scene) ? "存在未关闭问题" : "暂无未关闭问题",
      },
      {
        key: "layer-publish",
        label: "图层发布",
        state: sceneHasPublishedLayer(scene) ? "complete" : isArchivedScene(scene) ? "blocked" : "pending",
        meta: scene?.publishedLayerRecordCode || scene?.publishedLayerId || "等待发布图层",
      },
      {
        key: "delivery",
        label: "交付确认",
        state: sceneDeliveryState(scene),
        meta: displayLabel(DELIVERY_STATUS_LABELS, scene?.deliveryStatus || "pending"),
      },
    ];
  }

  function ensureSceneWorkflowStepper() {
    const detailGrid = $("#imageryDetailGrid");
    if (!detailGrid) return null;
    if (!$("#sceneWorkflowStepper")) {
      const wrapper = document.createElement("div");
      wrapper.className = "task-events workflow-stepper-panel";
      wrapper.innerHTML = '<h3>影像闭环进度</h3><div id="sceneWorkflowStepper" class="workflow-stepper" aria-label="影像闭环进度"></div>';
      detailGrid.insertAdjacentElement("afterend", wrapper);
    }
    return $("#sceneWorkflowStepper");
  }

  function renderSceneWorkflowSteps(scene) {
    const target = ensureSceneWorkflowStepper();
    if (!target) return;
    target.innerHTML = renderWorkflowStepper(sceneWorkflowSteps(scene));
  }

  function scenePermissionBoundaryItems(scene) {
    const published = sceneHasPublishedLayer(scene);
    return [
      {
        key: "metadata",
        label: "元数据维护",
        description: "编辑影像名称、范围、可见角色和基础属性。",
        permission: IMAGERY_SCENE_UPDATE_PERMISSION,
      },
      {
        key: "quality",
        label: "质量问题闭环",
        description: "处理影像任务失败、缺少边界和 COG 异常。",
        permission: IMAGERY_SCENE_QUALITY_PERMISSION,
      },
      {
        key: "layer-publish",
        label: "图层发布",
        description: published ? "已发布图层，可继续同步样式或重新发布。" : "发布影像图层需要地图图层跨模块权限。",
        permission: IMAGERY_LAYER_PUBLISH_PERMISSION,
        allPermissions: IMAGERY_MAP_LAYER_REQUIRED_PERMISSION,
        anyPermissions: IMAGERY_MAP_LAYER_UPSERT_PERMISSIONS,
      },
      {
        key: "delivery",
        label: "交付确认",
        description: "图层发布后记录交付状态、意见和交付人。",
        permission: IMAGERY_SCENE_DELIVERY_PERMISSION,
      },
      {
        key: "archive",
        label: "归档影像",
        description: "归档影像并暂停关联发布图层。",
        permission: IMAGERY_SCENE_ARCHIVE_PERMISSION,
      },
      {
        key: "export",
        label: "事件与回执导出",
        description: "导出影像事件、任务事件、质量问题和交付回执。",
        permission: IMAGERY_SCENE_EXPORT_PERMISSION,
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

  function ensureScenePermissionBoundary() {
    const detailGrid = $("#imageryDetailGrid");
    if (!detailGrid) return null;
    if (!$("#scenePermissionBoundary")) {
      const wrapper = document.createElement("div");
      wrapper.className = "task-events permission-boundary-panel";
      wrapper.innerHTML = '<h3>操作权限边界</h3><div id="scenePermissionBoundary" class="permission-boundary-list" aria-label="影像管理操作权限边界"></div>';
      const workflowPanel = $("#sceneWorkflowStepper")?.closest(".task-events");
      (workflowPanel || detailGrid).insertAdjacentElement("afterend", wrapper);
    }
    return $("#scenePermissionBoundary");
  }

  function renderScenePermissionBoundary(scene) {
    const target = ensureScenePermissionBoundary();
    if (!target) return;
    target.innerHTML = scenePermissionBoundaryItems(scene).map(permissionBoundaryItem).join("");
  }

  function sceneDeliveryEvents(scene) {
    return Array.isArray(scene?.deliveryEvents) ? scene.deliveryEvents : [];
  }

  function sceneDeliveryReceiptSummaryItems(scene) {
    const deliveryEvents = sceneDeliveryEvents(scene);
    const latestDelivery = deliveryEvents.length ? deliveryEvents[deliveryEvents.length - 1] : null;
    const deliveredAt = scene?.deliveredAt || latestDelivery?.at || "";
    const deliveredBy = scene?.deliveredBy || latestDelivery?.actor || "-";
    const publishedLayerRecordCode = scene?.publishedLayerRecordCode || scene?.publishedLayerId || "";
    return [
      {
        label: "\u4ea4\u4ed8\u72b6\u6001",
        value: displayLabel(DELIVERY_STATUS_LABELS, scene?.deliveryStatus || "pending"),
        meta: `${deliveredBy} / ${formatDateTime(deliveredAt)}`,
        tone: scene?.deliveryStatus === "delivered" ? "ready" : scene?.deliveryStatus === "rejected" ? "danger" : "warning",
      },
      {
        label: "\u53d1\u5e03\u56fe\u5c42",
        value: publishedLayerRecordCode || "\u672a\u53d1\u5e03",
        meta: publishedLayerRecordCode ? "\u53ef\u8ffd\u6eaf\u5230\u5730\u56fe\u56fe\u5c42" : "\u9700\u5148\u53d1\u5e03\u56fe\u5c42",
        tone: publishedLayerRecordCode ? "ready" : "warning",
      },
      {
        label: "\u4ea4\u4ed8\u4e8b\u4ef6",
        value: deliveryEvents.length,
        meta: latestDelivery?.comment || scene?.deliveryComment || "\u6682\u65e0\u4ea4\u4ed8\u610f\u89c1",
        tone: deliveryEvents.length ? "ready" : "warning",
      },
      {
        label: "\u4ea4\u4ed8\u56de\u6267",
        value: scene?.id || "-",
        meta: "\u5bfc\u51fa JSON \u56de\u6267\u5e76\u5199\u5165\u5f71\u50cf\u4e8b\u4ef6\u6d41",
        tone: "ready",
        action: "scene-delivery",
        permission: IMAGERY_SCENE_EXPORT_PERMISSION,
      },
    ];
  }

  function receiptSummaryCard(item) {
    const tone = item.tone ? ` tone-${item.tone}` : "";
    const actionAttribute =
      item.action === "scene-delivery"
        ? 'data-receipt-action="scene-delivery"'
        : `data-receipt-action="${escapeHtml(item.action || "")}"`;
    const command = item.action
      ? `<button type="button" class="button-ghost receipt-summary-command" ${actionAttribute} data-permission="${escapeHtml(item.permission || "")}">\u5bfc\u51fa\u56de\u6267</button>`
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

  function renderSceneDeliveryReceiptSummary(scene) {
    const target = $("#sceneDeliveryReceiptSummary");
    if (!target) return;
    if (!scene?.id) {
      target.innerHTML = '<p class="trace-empty">\u8bf7\u9009\u62e9\u5f71\u50cf\u751f\u6210\u4ea4\u4ed8\u56de\u6267\u6458\u8981\u3002</p>';
      return;
    }
    target.innerHTML = sceneDeliveryReceiptSummaryItems(scene).map(receiptSummaryCard).join("");
    applyActionPermissions();
  }

  function defaultSceneLayerName(scene = activeScene()) {
    return `${scene?.name || scene?.id || "影像"}图层`;
  }

  function sceneLayerPublishConfigMarkup() {
    return `
      <h3>图层发布配置</h3>
      <div class="field-grid scene-publish-grid">
        <label><span>图层名称</span><input id="sceneLayerName" type="text" placeholder="默认使用影像名称" /></label>
        <label><span>图层层级</span><input id="sceneLayerZIndex" type="number" step="1" placeholder="留空沿用后端默认" /></label>
        <label class="field-span-2"><span>关联林班编号</span><input id="sceneLayerLinkedBlockCodes" type="text" placeholder="多个编号用逗号分隔" /></label>
        <label class="field-span-2"><span>关联林权档案编号</span><input id="sceneLayerLinkedRightArchiveCodes" type="text" placeholder="多个档案编号用逗号分隔" /></label>
        <label>
          <span>大屏可见</span>
          <select id="sceneLayerVisibleOnDashboard">
            <option value="true">发布到大屏</option>
            <option value="false">仅后台管理</option>
          </select>
        </label>
      </div>
    `;
  }

  function ensureSceneLayerPublishConfig(detailGrid) {
    if (!detailGrid || $("#sceneLayerPublishConfig")) return;
    const wrapper = document.createElement("div");
    wrapper.id = "sceneLayerPublishConfig";
    wrapper.className = "task-events scene-publish-config";
    wrapper.innerHTML = sceneLayerPublishConfigMarkup();
    detailGrid.insertAdjacentElement("afterend", wrapper);
  }

  function syncSceneLayerPublishForm(scene = activeScene()) {
    const nameInput = $("#sceneLayerName");
    const blockInput = $("#sceneLayerLinkedBlockCodes");
    const rightsInput = $("#sceneLayerLinkedRightArchiveCodes");
    const zIndexInput = $("#sceneLayerZIndex");
    const dashboardSelect = $("#sceneLayerVisibleOnDashboard");
    if (nameInput) nameInput.value = defaultSceneLayerName(scene);
    if (blockInput) blockInput.value = Array.isArray(scene?.linkedBlockCodes) ? scene.linkedBlockCodes.join(", ") : "";
    if (rightsInput) rightsInput.value = Array.isArray(scene?.linkedRightArchiveCodes) ? scene.linkedRightArchiveCodes.join(", ") : "";
    if (zIndexInput) zIndexInput.value = scene?.publishedLayerZIndex ?? scene?.layerZIndex ?? "";
    if (dashboardSelect) dashboardSelect.value = isArchivedScene(scene) ? "false" : "true";
  }

  function sceneLayerPublishPayload(scene = activeScene()) {
    const zIndexValue = $("#sceneLayerZIndex")?.value.trim() || "";
    const zIndex = Number(zIndexValue);
    const payload = {
      name: $("#sceneLayerName")?.value.trim() || defaultSceneLayerName(scene),
      linkedBlockCodes: splitValues($("#sceneLayerLinkedBlockCodes")?.value || ""),
      linkedRightArchiveCodes: splitValues($("#sceneLayerLinkedRightArchiveCodes")?.value || ""),
      visibleOnDashboard: $("#sceneLayerVisibleOnDashboard")?.value !== "false",
    };
    if (zIndexValue && Number.isFinite(zIndex)) {
      payload.zIndex = zIndex;
    }
    return payload;
  }

  function ensureScenePublishControls() {
    const panel = $("#imageryDetailPanel");
    if (!panel) return;
    const actions = panel.querySelector(".panel-actions");
    if (actions && !$("#publishSceneLayer")) {
      const button = document.createElement("button");
      button.id = "publishSceneLayer";
      button.type = "button";
      button.className = "button-ghost";
      button.dataset.permission = IMAGERY_LAYER_PUBLISH_PERMISSION;
      button.textContent = "\u53d1\u5e03\u56fe\u5c42";
      actions.insertBefore(button, actions.firstChild);
      button.addEventListener("click", () => publishSceneLayer(activeScene()));
    }
    if (actions && !$("#archiveScene")) {
      const button = document.createElement("button");
      button.id = "archiveScene";
      button.type = "button";
      button.className = "button-ghost";
      button.dataset.permission = IMAGERY_SCENE_ARCHIVE_PERMISSION;
      button.textContent = "归档影像";
      actions.insertBefore(button, $("#publishSceneLayer") || actions.firstChild);
      button.addEventListener("click", () => archiveScene(activeScene()));
    }
    const detailGrid = $("#imageryDetailGrid");
    ensureSceneLayerPublishConfig(detailGrid);
    if (detailGrid && !$("#sceneOperationResult")) {
      const wrapper = document.createElement("div");
      wrapper.id = "sceneOperationResult";
      wrapper.className = "operation-result-shell";
      wrapper.setAttribute("aria-live", "polite");
      const publishConfig = $("#sceneLayerPublishConfig");
      (publishConfig || detailGrid).insertAdjacentElement("afterend", wrapper);
    }
    if (detailGrid && !$("#scenePublishEventList")) {
      const wrapper = document.createElement("div");
      wrapper.className = "task-events";
      wrapper.innerHTML = '<h3>\u53d1\u5e03\u8bb0\u5f55</h3><div id="scenePublishEventList" class="trace-list"></div>';
      const operationResult = $("#sceneOperationResult");
      (operationResult || $("#sceneLayerPublishConfig") || detailGrid).insertAdjacentElement("afterend", wrapper);
    }
    if (detailGrid && !$("#sceneLifecycleEventList")) {
      const wrapper = document.createElement("div");
      wrapper.className = "task-events";
      wrapper.innerHTML = '<h3>\u751f\u547d\u5468\u671f</h3><div id="sceneLifecycleEventList" class="trace-list"></div>';
      const publishWrapper = $("#scenePublishEventList")?.closest(".task-events");
      (publishWrapper || detailGrid).insertAdjacentElement("afterend", wrapper);
    }
    if (detailGrid && !$("#sceneImportBatchLinksList")) {
      const wrapper = document.createElement("div");
      wrapper.className = "task-events";
      wrapper.innerHTML = '<h3>\u5165\u5e93\u6279\u6b21\u8ffd\u6eaf</h3><div id="sceneImportBatchLinksList" class="trace-list"></div>';
      const lifecycleWrapper = $("#sceneLifecycleEventList")?.closest(".task-events");
      (lifecycleWrapper || detailGrid).insertAdjacentElement("afterend", wrapper);
    }
  }

  function renderScenePublishEventsLegacy(scene) {
    ensureScenePublishControls();
    const target = $("#scenePublishEventList");
    if (!target) return;
    const events = Array.isArray(scene?.publishEvents) ? scene.publishEvents : [];
    if (!events.length) {
      target.innerHTML = '<p class="trace-empty">\u6682\u65e0\u53d1\u5e03\u8bb0\u5f55</p>';
      return;
    }
    target.innerHTML = events
      .map(
        (event) => `
          <article class="trace-item">
            <strong>${escapeHtml(event.action || "publish-layer")} · ${escapeHtml(displayLabel(SCENE_STATUS_LABELS, event.status))}</strong>
            <span>${escapeHtml(formatDateTime(event.at))} · ${escapeHtml(event.layerRecordCode || event.layerId || "-")} · ${escapeHtml(event.actor || "-")}</span>
          </article>
        `,
      )
      .join("");
  }

  function renderScenePublishEvents(scene) {
    ensureScenePublishControls();
    const target = $("#scenePublishEventList");
    if (!target) return;
    const events = Array.isArray(scene?.publishEvents) ? scene.publishEvents : [];
    if (!events.length) {
      target.innerHTML = '<p class="trace-empty">暂无发布记录</p>';
      return;
    }
    target.innerHTML = events
      .map((event) => {
        const layerCode = event.layerRecordCode || event.layerId || "";
        return `
          <article class="trace-item">
            <strong>${escapeHtml(event.action || "publish-layer")} · ${escapeHtml(displayLabel(SCENE_STATUS_LABELS, event.status))}</strong>
            <span>${escapeHtml(formatDateTime(event.at))} · ${layerCode ? traceLink(`admin-map-layers.html?layerCode=${encodeURIComponent(layerCode)}`, `图层 ${layerCode}`) : "-"} · ${escapeHtml(event.actor || "-")}</span>
          </article>
        `;
      })
      .join("");
  }

  function sceneOperationResultLinks(layer = {}, payload = {}) {
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

  function renderSceneOperationResult(payload) {
    ensureScenePublishControls();
    const target = $("#sceneOperationResult");
    if (!target) return;
    if (!payload) {
      target.innerHTML = '<p class="trace-empty">暂无本次操作回执。</p>';
      return;
    }
    const layer = payload.layer || {};
    const event = payload.event || {};
    const scene = payload.scene || {};
    const sourceLinks = Array.isArray(layer.sourceLinks) ? layer.sourceLinks : [];
    const dashboardHref = layer.dashboardHref || "";
    const layerCode = layer.recordCode || layer.id || event.layerRecordCode || event.layerId || "-";
    const publishText = dashboardHref ? "已发布到大屏" : "仅后台管理";
    target.innerHTML = `
      <article class="operation-result">
        <div class="operation-result-header">
          <div>
            <strong class="operation-result-title">影像图层发布回执</strong>
            <span>${escapeHtml(formatDateTime(event.at || layer.updatedAt || layer.createdAt))}</span>
          </div>
          <span class="operation-result-status">${escapeHtml(publishText)}</span>
        </div>
        <div class="operation-result-meta">
          <span>图层 ${escapeHtml(layerCode)}</span>
          <span>影像 ${escapeHtml(scene.id || event.sceneId || "-")}</span>
          <span>来源 ${escapeHtml(displayLabel(MAP_LAYER_SOURCE_TYPE_LABELS, layer.sourceType || "imagery"))}</span>
          <span>风险 ${escapeHtml(displayLabel(PUBLISH_RISK_LABELS, layer.publishRiskStatus || "unknown"))}</span>
          <span>追溯 ${escapeHtml(sourceLinks.length)} 项</span>
        </div>
        ${sceneOperationResultLinks(layer, event)}
      </article>
    `;
  }

  function renderSceneLifecycleEvents(scene) {
    ensureScenePublishControls();
    const target = $("#sceneLifecycleEventList");
    if (!target) return;
    const events = Array.isArray(scene?.lifecycleEvents) ? scene.lifecycleEvents : [];
    if (!events.length) {
      target.innerHTML = '<p class="trace-empty">\u6682\u65e0\u751f\u547d\u5468\u671f\u8bb0\u5f55</p>';
      return;
    }
    target.innerHTML = events
      .map(
        (event) => `
          <article class="trace-item">
            <strong>${escapeHtml(displayLabel(SCENE_LIFECYCLE_ACTION_LABELS, event.action || "soft-delete"))} · ${escapeHtml(displayLabel(SCENE_STATUS_LABELS, event.status))}</strong>
            <span>${escapeHtml(formatDateTime(event.at))} · ${escapeHtml(event.actor || "-")}</span>
            ${event.message ? `<small>${escapeHtml(event.message)}</small>` : ""}
          </article>
        `,
      )
      .join("");
  }

  function renderSceneDeliveryEvents(scene) {
    ensureScenePublishControls();
    const target = $("#sceneDeliveryEventList");
    if (!target) return;
    const events = Array.isArray(scene?.deliveryEvents) ? scene.deliveryEvents : [];
    if (!events.length) {
      target.innerHTML = '<p class="trace-empty">暂无交付记录</p>';
      return;
    }
    target.innerHTML = events
      .map(
        (event) => `
          <article class="trace-item">
            <strong>${escapeHtml(displayLabel(DELIVERY_STATUS_LABELS, event.status || event.action))}</strong>
            <span>${escapeHtml(formatDateTime(event.at))} · ${escapeHtml(event.actor || "-")}</span>
            <span>${escapeHtml(event.comment || "-")}</span>
          </article>
        `,
      )
      .join("");
  }

  function renderSceneImportBatchLinksLegacy(scene) {
    ensureScenePublishControls();
    const target = $("#sceneImportBatchLinksList");
    if (!target) return;
    const sceneId = String(scene?.id || "");
    const batches = state.sceneImportBatches[sceneId] || [];
    if (!sceneId) {
      target.innerHTML = '<p class="trace-empty">\u8bf7\u5148\u9009\u62e9\u4e00\u666f\u5f71\u50cf</p>';
      return;
    }
    if (!batches.length) {
      target.innerHTML = '<p class="trace-empty">\u6682\u65e0\u5165\u5e93\u6279\u6b21\u5173\u8054</p>';
      return;
    }
    target.innerHTML = batches
      .map((batch) => {
        const latestLink = Array.isArray(batch.imageryLinks) ? batch.imageryLinks.find((item) => String(item.sceneId || "") === sceneId) : null;
        return `
          <article class="trace-item">
            <strong>${escapeHtml(batch.fileName || batch.id || "-")}</strong>
            <span>${escapeHtml(batch.id || "-")} · ${escapeHtml(displayLabel(BATCH_STATUS_LABELS, batch.status))} · \u6709\u6548 ${escapeHtml(batch.validRows ?? 0)} / \u603b\u884c ${escapeHtml(batch.totalRows ?? 0)}</span>
            <span>${escapeHtml(latestLink?.layerRecordCode || latestLink?.layerId || "-")} · ${escapeHtml(formatDateTime(latestLink?.at || batch.completedAt || batch.createdAt))}</span>
          </article>
        `;
      })
      .join("");
  }

  function renderSceneImportBatchLinks(scene) {
    ensureScenePublishControls();
    const target = $("#sceneImportBatchLinksList");
    if (!target) return;
    const sceneId = String(scene?.id || "");
    const batches = state.sceneImportBatches[sceneId] || [];
    if (!sceneId) {
      target.innerHTML = '<p class="trace-empty">请先选择一景影像</p>';
      return;
    }
    if (!batches.length) {
      target.innerHTML = '<p class="trace-empty">暂无入库批次关联</p>';
      return;
    }
    target.innerHTML = batches
      .map((batch) => {
        const latestLink = Array.isArray(batch.imageryLinks) ? batch.imageryLinks.find((item) => String(item.sceneId || "") === sceneId) : null;
        const batchId = batch.id || "";
        const layerCode = latestLink?.layerRecordCode || latestLink?.layerId || "";
        return `
          <article class="trace-item">
            <strong>${batchId ? traceLink(`admin-imports.html?batchId=${encodeURIComponent(batchId)}`, batch.fileName || batchId) : escapeHtml(batch.fileName || "-")}</strong>
            <span>${escapeHtml(batchId || "-")} · ${escapeHtml(displayLabel(BATCH_STATUS_LABELS, batch.status))} · 有效 ${escapeHtml(batch.validRows ?? 0)} / 总行 ${escapeHtml(batch.totalRows ?? 0)}</span>
            <span>${layerCode ? traceLink(`admin-map-layers.html?layerCode=${encodeURIComponent(layerCode)}`, `图层 ${layerCode}`) : "-"} · ${escapeHtml(formatDateTime(latestLink?.at || batch.completedAt || batch.createdAt))}</span>
          </article>
        `;
      })
      .join("");
  }

  async function loadSceneImportBatchLinks(scene = activeScene()) {
    if (!scene?.id) return;
    const sceneId = String(scene.id);
    const target = $("#sceneImportBatchLinksList");
    if (target) target.innerHTML = '<p class="trace-empty">\u6b63\u5728\u52a0\u8f7d\u5165\u5e93\u6279\u6b21\u8ffd\u6eaf...</p>';
    try {
      const payload = await api(`/api/imports/forest-blocks/batches?${query({ sceneId, limit: 100 })}`);
      state.sceneImportBatches[sceneId] = Array.isArray(payload.items) ? payload.items : [];
      renderSceneImportBatchLinks(scene);
    } catch (error) {
      if (target) target.innerHTML = `<p class="trace-empty">\u5165\u5e93\u6279\u6b21\u8ffd\u6eaf\u52a0\u8f7d\u5931\u8d25\uff1a${escapeHtml(error.message)}</p>`;
    }
  }

  function renderScenePreview(scene) {
    const image = $("#imageryPreviewImage");
    const status = $("#imageryPreviewStatus");
    if (!image || !status) return;
    image.hidden = true;
    image.removeAttribute("src");
    image.alt = scene?.name ? `${scene.name}影像成果预览` : "影像成果预览";
    image.dataset.sceneId = String(scene?.id || "");
    if (!scene?.thumbnailUrl) {
      status.hidden = false;
      status.textContent = "该影像尚未生成可预览的 COG 成果";
      return;
    }
    const previewUrl = new URL(scene.thumbnailUrl, window.location.href);
    previewUrl.searchParams.set("maxSize", "720");
    status.hidden = false;
    status.textContent = "正在生成影像预览...";
    image.src = previewUrl.toString();
  }

  function renderDetail(scene = activeScene()) {
    ensureScenePublishControls();
    const panel = $("#imageryDetailPanel");
    if (!scene) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      return;
    }
    $("#imageryDetailTitle").textContent = `${scene.name || scene.id}详情`;
    $("#imageryDetailEmpty").hidden = true;
    renderScenePreview(scene);
    $("#imageryDetailGrid").innerHTML = [
      detailItem("影像 ID", scene.id),
      detailItem("影像名称", scene.name || "-"),
      detailItem("文件名", scene.fileName || "-"),
      detailItem("项目 ID", scene.projectId || "-"),
      detailItem("区域编码", scene.areaCode || "-"),
      detailItem("卫星/平台", scene.satellite || "-"),
      detailItem("传感器", scene.sensor || "-"),
      detailItem("拍摄时间", scene.capturedAt || "-"),
      detailItem("分辨率", scene.resolution || "-"),
      detailItem("覆盖范围", Array.isArray(scene.bounds) ? scene.bounds.join(", ") : "-"),
      detailItem("可见角色", Array.isArray(scene.allowedRoles) ? scene.allowedRoles.join(", ") : "-"),
      detailItem("可见用户", Array.isArray(scene.allowedUsers) ? scene.allowedUsers.join(", ") : "-"),
      detailItem("交付状态", displayLabel(DELIVERY_STATUS_LABELS, scene.deliveryStatus || "pending")),
      detailItem("交付人", scene.deliveredBy || "-"),
      detailItem("交付时间", formatDateTime(scene.deliveredAt)),
      detailItem("交付意见", scene.deliveryComment || "-"),
      detailItem("更新日期", formatDateTime(scene.updatedAt)),
      detailItem("元数据 JSON", stringifyPretty(scene, {})),
    ].join("");
    renderSceneWorkflowSteps(scene);
    renderScenePermissionBoundary(scene);
    renderSceneDeliveryReceiptSummary(scene);
    syncSceneLayerPublishForm(scene);
    renderSceneOperationResult(null);
    renderScenePublishEvents(scene);
    renderSceneDeliveryEvents(scene);
    renderSceneLifecycleEvents(scene);
    renderSceneImportBatchLinks(scene);
    if ($("#sceneDeliveryStatus")) $("#sceneDeliveryStatus").value = scene.deliveryStatus || "pending";
    if ($("#sceneDeliveryComment")) $("#sceneDeliveryComment").value = scene.deliveryComment || "";
    const archiveButton = $("#archiveScene");
    if (archiveButton) {
      const blocked = isDeletedScene(scene) || isArchivedScene(scene);
      archiveButton.hidden = blocked;
      archiveButton.disabled = blocked;
    }
    const publishButton = $("#publishSceneLayer");
    if (publishButton) {
      publishButton.hidden = isDeletedScene(scene);
    }
    const deliveryButton = $("#updateSceneDelivery");
    if (deliveryButton && !deliveryButton.classList.contains("permission-disabled")) {
      const published = Boolean(scene.publishedLayerId || scene.publishedLayerRecordCode || scene.status === "published");
      deliveryButton.disabled = isDeletedScene(scene) || !published;
      deliveryButton.title = published ? "" : "影像需发布图层后才能确认交付";
    }
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    applyActionPermissions();
    renderRows();
    loadSceneImportBatchLinks(scene);
  }

  function fillForm(scene = {}) {
    state.activeId = scene.id || "";
    $("#imageryFormTitle").textContent = scene.id ? "编辑影像权限" : "编辑影像";
    $("#imageryId").value = scene.id || "";
    $("#imageryName").value = scene.name || "";
    $("#imagerySatellite").value = scene.satellite || "";
    $("#imagerySensor").value = scene.sensor || "";
    $("#imageryCapturedAt").value = scene.capturedAt || "";
    $("#imageryResolution").value = scene.resolution || "";
    $("#imageryProjectId").value = scene.projectId || "";
    $("#imageryAreaCode").value = scene.areaCode || "";
    $("#imageryBounds").value = Array.isArray(scene.bounds) ? scene.bounds.join(", ") : scene.bounds || "";
    $("#imageryOpacity").value = scene.opacity ?? "";
    $("#imageryVisible").checked = scene.visible !== false;
    $("#imageryAllowedRoles").value = Array.isArray(scene.allowedRoles) ? scene.allowedRoles.join(", ") : "";
    $("#imageryAllowedUsers").value = Array.isArray(scene.allowedUsers) ? scene.allowedUsers.join(", ") : "";
    renderRows();
  }

  function openImageryEditor(mode, scene = {}) {
    closeImageryDetail();
    fillForm(mode === "edit" ? scene : {});
    $("#imageryForm").classList.remove("hidden");
    $("#imageryForm").setAttribute("aria-hidden", "false");
    $("#imageryName").focus();
  }

  function closeImageryEditor() {
    $("#imageryForm").classList.add("hidden");
    $("#imageryForm").setAttribute("aria-hidden", "true");
  }

  function closeImageryDetail() {
    $("#imageryDetailPanel").classList.add("hidden");
    $("#imageryDetailPanel").setAttribute("aria-hidden", "true");
  }

  function scenePayloadFromForm() {
    return {
      name: $("#imageryName").value.trim(),
      satellite: $("#imagerySatellite").value.trim(),
      sensor: $("#imagerySensor").value.trim(),
      capturedAt: $("#imageryCapturedAt").value.trim(),
      resolution: $("#imageryResolution").value.trim(),
      bounds: $("#imageryBounds").value.trim(),
      projectId: $("#imageryProjectId").value.trim(),
      areaCode: $("#imageryAreaCode").value.trim(),
      opacity: $("#imageryOpacity").value === "" ? null : Number($("#imageryOpacity").value),
      visible: $("#imageryVisible").checked,
      allowedRoles: splitValues($("#imageryAllowedRoles").value),
      allowedUsers: splitValues($("#imageryAllowedUsers").value),
    };
  }

  function consumeInitialSceneSelection() {
    const targetId = String(initialSceneId || "").trim();
    if (!targetId) return;
    const matched = state.scenes.find((scene) => String(scene.id || "") === targetId);
    if (!matched) return;
    state.activeId = matched.id;
    initialSceneId = "";
  }

  async function consumeInitialTaskSelection() {
    const targetId = String(initialTaskId || "").trim();
    if (!targetId) return;

    let matched = state.tasks.find((task) => String(task.id || "") === targetId);
    if (!matched) {
      try {
        matched = await api(`/api/tasks/${encodeURIComponent(targetId)}`);
      } catch (error) {
        return;
      }
    }
    if (!matched?.id) return;

    if (!state.tasks.some((task) => String(task.id || "") === String(matched.id))) {
      state.tasks = [matched, ...state.tasks];
    }
    state.activeTaskId = matched.id;
    if (matched.sceneId && !state.activeId) state.activeId = matched.sceneId;
    initialTaskId = "";
  }

  function consumeInitialImageryIssueSelection() {
    const targetId = String(initialImageryIssueId || "").trim();
    if (!targetId) return;
    const matched = state.imageryIssues.find((issue) => String(issue.issueId || "") === targetId);
    if (!matched) return;
    state.activeImageryIssueId = matched.issueId || targetId;
    if (matched.sceneId && !state.activeId) state.activeId = matched.sceneId;
    if (matched.taskId && !state.activeTaskId) state.activeTaskId = matched.taskId;
    initialImageryIssueId = "";
  }

  function sceneQuery() {
    const sceneStatus = $("#sceneStatusFilter")?.value.trim() || "";
    return query({
      q: $("#sceneKeyword").value.trim(),
      status: sceneStatus,
      projectId: $("#projectFilter").value.trim(),
      areaCode: $("#areaFilter").value.trim(),
      published: $("#scenePublishedFilter")?.value.trim() || "",
      deliveryStatus: $("#sceneDeliveryStatusFilter")?.value.trim() || "",
      includeDeleted: $("#includeDeletedScenes")?.checked || sceneStatus === "deleted" ? "true" : "",
      limit: pager.limit,
      offset: pager.offset,
    });
  }

  function sceneEventQuery() {
    return query({
      q: $("#sceneEventKeyword")?.value.trim() || "",
      eventType: $("#sceneEventTypeFilter")?.value.trim() || "",
      action: $("#sceneEventActionFilter")?.value.trim() || "",
      sceneId: $("#sceneEventSceneFilter")?.value.trim() || "",
      limit: 100,
    });
  }

  function renderSceneEvents() {
    const body = $("#sceneEventRows");
    if (!body) return;
    if (!state.sceneEvents.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无影像事件记录</td></tr>';
      return;
    }
    body.innerHTML = state.sceneEvents
      .map((event) => {
        const eventLabel = sceneEventDisplayLabel(event);
        return `
          <tr>
            <td><div class="cell-stack"><strong>${escapeHtml(eventLabel)}</strong><small>${escapeHtml(event.eventId || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(event.sceneName || event.sceneId || "-")}</strong><small>${escapeHtml(event.sceneId || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(event.layerRecordCode || "-")}</strong><small>${escapeHtml(event.layerId || "-")}</small></div></td>
            <td>${escapeHtml(event.actor || "-")}</td>
            <td>${escapeHtml(formatDateTime(event.at))}</td>
            <td><span class="status-pill">${escapeHtml(displayLabel(SCENE_STATUS_LABELS, event.status || event.action))}</span></td>
          </tr>
        `;
      })
      .join("");
  }

  async function loadSceneEvents() {
    const body = $("#sceneEventRows");
    try {
      const payload = await api(`/api/scenes/events?${sceneEventQuery()}`);
      state.sceneEvents = Array.isArray(payload.items) ? payload.items : [];
      renderSceneEvents();
    } catch (error) {
      if (body) body.innerHTML = `<tr class="placeholder-row"><td colspan="6">${escapeHtml(error.message)}</td></tr>`;
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

  async function exportSceneEvents() {
    await downloadFile(
      `/api/scenes/events.csv?${sceneEventQuery()}`,
      "scene-events.csv",
      {
        busy: "正在导出影像事件 CSV...",
        done: "影像事件 CSV 已导出。",
        fail: "影像事件导出失败",
      },
    );
  }

  async function exportImageryWorkflowSummary() {
    await downloadFile(
      "/api/scenes/workflow-summary.json",
      "imagery-workflow-summary.json",
      {
        busy: "正在导出影像管理摘要 JSON...",
        done: "影像管理摘要 JSON 已导出。",
        fail: "影像管理摘要导出失败",
      },
    );
  }

  async function exportSceneDeliveryReceipt(scene = activeScene()) {
    if (!scene) return;
    const exported = await downloadFile(
      `/api/scenes/${encodeURIComponent(scene.id)}/delivery-receipt.json`,
      `scene-delivery-receipt-${scene.id}.json`,
      {
        busy: "正在导出交付回执...",
        done: "交付回执已导出，导出事件已写入影像事件流。",
        fail: "交付回执导出失败",
      },
    );
    if (!exported) return;
    await loadScenes();
    await loadSceneEvents();
    renderDetail(activeScene() || scene);
    setStatus("online", "交付回执已导出，导出事件已写入影像事件流。");
  }

  async function exportScenePublicationReceipt(scene = activeScene()) {
    if (!scene) return;
    const exported = await downloadFile(
      `/api/scenes/${encodeURIComponent(scene.id)}/publication-receipt.json`,
      `scene-publication-receipt-${scene.id}.json`,
      {
        busy: "\u6b63\u5728\u5bfc\u51fa\u53d1\u5e03\u56de\u6267...",
        done: "\u53d1\u5e03\u56de\u6267\u5df2\u5bfc\u51fa\uff0c\u5bfc\u51fa\u4e8b\u4ef6\u5df2\u5199\u5165\u5f71\u50cf\u4e8b\u4ef6\u6d41\u3002",
        fail: "\u53d1\u5e03\u56de\u6267\u5bfc\u51fa\u5931\u8d25",
      },
    );
    if (!exported) return;
    await loadScenes();
    await loadSceneEvents();
    renderDetail(activeScene() || scene);
    setStatus("online", "\u53d1\u5e03\u56de\u6267\u5df2\u5bfc\u51fa\uff0c\u5bfc\u51fa\u4e8b\u4ef6\u5df2\u5199\u5165\u5f71\u50cf\u4e8b\u4ef6\u6d41\u3002");
  }

  async function updateSceneDelivery(scene = activeScene()) {
    if (!scene) return;
    const status = $("#sceneDeliveryStatus")?.value || "pending";
    const comment = $("#sceneDeliveryComment")?.value.trim() || "";
    setStatus("busy", "正在记录影像交付...");
    try {
      const payload = await api(`/api/scenes/${encodeURIComponent(scene.id)}/delivery`, {
        method: "POST",
        body: JSON.stringify({ status, comment }),
      });
      state.activeId = payload.scene?.id || scene.id;
      await loadScenes();
      await loadSceneEvents();
      renderDetail(state.scenes.find((item) => String(item.id) === String(state.activeId)) || payload.scene);
      setStatus("online", "影像交付已记录。");
    } catch (error) {
      setStatus("offline", `影像交付失败：${error.message}`);
    }
  }

  async function loadScenes() {
    setStatus("busy", "正在加载影像目录...");
    pager.setBusy(true);
    try {
      const payload = await api(`/api/scenes?${sceneQuery()}`);
      if (pager.setTotal(payload.total ?? 0)) return loadScenes();
      state.scenes = Array.isArray(payload.scenes) ? payload.scenes : [];
      consumeInitialSceneSelection();
      if (state.activeId && !activeScene()) state.activeId = "";
      renderRows();
      renderDetail(activeScene());
      renderTaskTrace(activeTask());
      loadImageryWorkflowSummary();
      loadImageryOperationQueue();
      setStatus("online", `已加载 ${payload.total ?? state.scenes.length} 景影像。`);
    } catch (error) {
      setStatus("offline", `影像加载失败：${error.message}`);
    } finally {
      pager.setBusy(false);
    }
  }

  function reloadScenesFromFirstPage() {
    pager.reset();
    return loadScenes();
  }

  async function loadTasks() {
    try {
      const payload = await api(
        `/api/tasks?${query({
          status: $("#taskStatusFilter")?.value.trim() || "",
          limit: 50,
          includeArchived: $("#includeArchivedTasks")?.checked ? "true" : "",
        })}`
      );
      state.tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
      await consumeInitialTaskSelection();
      if (state.activeTaskId && !activeTask()) state.activeTaskId = "";
      renderTasks();
      renderTaskDetail(activeTask());
      loadImageryWorkflowSummary();
      loadImageryOperationQueue();
    } catch (error) {
      $("#taskRows").innerHTML = `<tr class="placeholder-row"><td colspan="6">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  function taskEventQuery() {
    return query({
      q: $("#taskEventKeyword")?.value.trim() || "",
      status: $("#taskEventStatusFilter")?.value.trim() || "",
      action: $("#taskEventActionFilter")?.value.trim() || "",
      taskId: $("#taskEventTaskFilter")?.value.trim() || "",
      limit: 100,
    });
  }

  function imageryIssueQuery() {
    return query({
      q: $("#imageryIssueKeyword")?.value.trim() || "",
      issueType: $("#imageryIssueTypeFilter")?.value.trim() || "",
      severity: $("#imageryIssueSeverityFilter")?.value.trim() || "",
      status: $("#imageryIssueStatusFilter")?.value.trim() || "",
      sceneId: $("#imageryIssueSceneFilter")?.value.trim() || "",
      taskId: $("#imageryIssueTaskFilter")?.value.trim() || "",
      includeArchived: $("#includeArchivedImageryIssues")?.checked ? "true" : "",
      limit: 100,
    });
  }

  function imageryIssueStatusLabel(status) {
    return ISSUE_STATUS_LABELS[status] || status || ISSUE_STATUS_LABELS.open;
  }

  function imageryIssueStatusClass(status) {
    if (status === "resolved") return "complete";
    if (status === "investigating") return "review";
    if (status === "open") return "partial";
    return "";
  }

  function imageryIssueActions(issue) {
    const issueId = escapeHtml(issue.issueId || "");
    return `
      <div class="row-actions" aria-label="\u5f71\u50cf\u95ee\u9898\u5904\u7406">
        <button type="button" class="icon-button" data-imagery-issue-action="investigating" data-issue-id="${issueId}" data-permission="${IMAGERY_SCENE_QUALITY_PERMISSION}" aria-label="\u6807\u8bb0\u5904\u7406\u4e2d" title="\u6807\u8bb0\u5904\u7406\u4e2d">${INVESTIGATING_ICON}</button>
        <button type="button" class="icon-button" data-imagery-issue-action="resolved" data-issue-id="${issueId}" data-permission="${IMAGERY_SCENE_QUALITY_PERMISSION}" aria-label="\u6807\u8bb0\u5df2\u89e3\u51b3" title="\u6807\u8bb0\u5df2\u89e3\u51b3">${RESOLVED_ICON}</button>
        <button type="button" class="icon-button danger" data-imagery-issue-action="ignored" data-issue-id="${issueId}" data-permission="${IMAGERY_SCENE_QUALITY_PERMISSION}" aria-label="\u6807\u8bb0\u5df2\u5ffd\u7565" title="\u6807\u8bb0\u5df2\u5ffd\u7565">${IGNORED_ICON}</button>
      </div>
    `;
  }

  function renderImageryIssueRows() {
    const body = $("#imageryIssueRows");
    if (!body) return;
    if (!state.imageryIssues.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="7">暂无影像异常问题</td></tr>';
      return;
    }
    body.innerHTML = state.imageryIssues
      .map((issue) => {
        const sceneId = issue.sceneId || "";
        const sceneLabel = issue.sceneName || sceneId || "-";
        const status = issue.status || "open";
        const active = String(issue.issueId || "") === String(state.activeImageryIssueId || "") ? "active" : "";
        return `
          <tr data-issue-id="${escapeHtml(issue.issueId || "")}" class="${active}">
            <td><span class="status-pill">${escapeHtml(displayLabel(ISSUE_SEVERITY_LABELS, issue.severity))}</span></td>
            <td><div class="cell-stack"><strong>${escapeHtml(displayLabel(IMAGERY_ISSUE_TYPE_LABELS, issue.issueType))}</strong><small>${escapeHtml(issue.issueKey || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${sceneId ? traceLink(`admin-imagery.html?sceneId=${encodeURIComponent(sceneId)}`, sceneLabel) : escapeHtml(sceneLabel)}</strong><small>${escapeHtml(sceneId || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(issue.taskName || issue.taskId || "-")}</strong><small>${escapeHtml(issue.taskId || "-")}</small></div></td>
            <td><div class="cell-stack"><span class="status-pill ${imageryIssueStatusClass(status)}">${escapeHtml(imageryIssueStatusLabel(status))}</span><small>${escapeHtml(issue.handledBy || "-")} / ${escapeHtml(formatDateTime(issue.handledAt))}</small><small>${escapeHtml(issue.handlingComment || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(issue.message || "-")}</strong><small>${escapeHtml(issue.actionRequired || "-")}</small></div></td>
            <td>${imageryIssueActions(issue)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  async function loadImageryIssues() {
    const body = $("#imageryIssueRows");
    try {
      const payload = await api(`/api/scenes/quality-issues?${imageryIssueQuery()}`);
      state.imageryIssues = Array.isArray(payload.items) ? payload.items : [];
      consumeInitialImageryIssueSelection();
      renderImageryIssueRows();
      renderTaskTrace(activeTask());
      loadImageryWorkflowSummary();
      loadImageryOperationQueue();
    } catch (error) {
      if (body) body.innerHTML = `<tr class="placeholder-row"><td colspan="7">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  async function exportImageryIssues() {
    await downloadFile(
      `/api/scenes/quality-issues.csv?${imageryIssueQuery()}`,
      "imagery-quality-issues.csv",
      {
        busy: "正在导出影像问题 CSV...",
        done: "影像问题 CSV 已导出。",
        fail: "影像问题导出失败",
      },
    );
  }

  async function updateImageryIssueStatus(issue, status) {
    if (!issue?.issueId || !status) return;
    const label = imageryIssueStatusLabel(status);
    const comment =
      typeof window.prompt === "function"
        ? window.prompt(`${label}\u5904\u7406\u610f\u89c1`, issue.handlingComment || "")
        : "";
    if (comment === null) return;
    setStatus("busy", "\u6b63\u5728\u66f4\u65b0\u5f71\u50cf\u95ee\u9898\u5904\u7406\u72b6\u6001...");
    try {
      const payload = await api(`/api/scenes/quality-issues/${encodeURIComponent(issue.issueId)}`, {
        method: "PATCH",
        body: JSON.stringify({ status, comment: comment || "" }),
      });
      if (payload.issue?.sceneId) state.activeId = payload.issue.sceneId;
      if (payload.issue?.taskId) state.activeTaskId = payload.issue.taskId;
      await loadImageryIssues();
      await loadScenes();
      await loadSceneEvents();
      await loadTasks();
      await loadTaskEvents();
      renderDetail(activeScene());
      renderTaskDetail(activeTask());
      setStatus("online", "\u5f71\u50cf\u95ee\u9898\u5904\u7406\u72b6\u6001\u5df2\u66f4\u65b0\u3002");
    } catch (error) {
      setStatus("offline", `\u5f71\u50cf\u95ee\u9898\u5904\u7406\u5931\u8d25\uff1a${error.message}`);
    }
  }

  function handleImageryIssueAction(event) {
    const button = event.target.closest("[data-imagery-issue-action]");
    if (!button) return false;
    event.preventDefault();
    event.stopPropagation();
    if (button.disabled) return true;
    const issue = state.imageryIssues.find((item) => String(item.issueId) === String(button.dataset.issueId));
    if (!issue) return true;
    state.activeImageryIssueId = issue.issueId || "";
    updateImageryIssueStatus(issue, button.dataset.imageryIssueAction);
    return true;
  }

  function renderTaskEventRows() {
    const body = $("#taskEventRows");
    if (!body) return;
    if (!state.taskEvents.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无任务事件记录</td></tr>';
      return;
    }
    body.innerHTML = state.taskEvents
      .map((event) => {
        const eventLabel = event.summary || `${displayLabel(TASK_STATUS_LABELS, event.status || event.action)}: ${event.message || "-"}`;
        return `
          <tr>
            <td><div class="cell-stack"><strong>${escapeHtml(eventLabel)}</strong><small>${escapeHtml(event.eventId || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(event.taskName || event.taskId || "-")}</strong><small>${escapeHtml(event.taskId || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(event.taskType || "-")}</strong><small>${escapeHtml(event.sceneId || "-")}</small></div></td>
            <td><span class="status-pill">${escapeHtml(displayLabel(TASK_STATUS_LABELS, event.status))}</span></td>
            <td>${escapeHtml(event.progress ?? 0)}%</td>
            <td><div class="cell-stack"><strong>${escapeHtml(event.actor || "-")}</strong><small>${escapeHtml(formatDateTime(event.at))}</small></div></td>
          </tr>
        `;
      })
      .join("");
  }

  async function loadTaskEvents() {
    const body = $("#taskEventRows");
    try {
      const payload = await api(`/api/tasks/events?${taskEventQuery()}`);
      state.taskEvents = Array.isArray(payload.items) ? payload.items : [];
      renderTaskEventRows();
    } catch (error) {
      if (body) body.innerHTML = `<tr class="placeholder-row"><td colspan="6">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  async function exportTaskEvents() {
    await downloadFile(
      `/api/tasks/events.csv?${taskEventQuery()}`,
      "task-events.csv",
      {
        busy: "正在导出任务事件 CSV...",
        done: "任务事件 CSV 已导出。",
        fail: "任务事件导出失败",
      },
    );
  }

  function renderTasks() {
    const body = $("#taskRows");
    if (!state.tasks.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无影像任务</td></tr>';
      return;
    }
    body.innerHTML = state.tasks
      .map((task) => {
        const active = String(task.id) === String(state.activeTaskId) ? "active" : "";
        const archived = task.archivedAt ? " archived" : "";
        return `
        <tr data-id="${escapeHtml(task.id)}" class="${active}${archived}">
          <td><div class="cell-stack"><strong>${escapeHtml(task.id || "-")}</strong><small>${escapeHtml(task.type || "-")}</small></div></td>
          <td>${escapeHtml(task.name || task.sceneId || "-")}</td>
          <td><span class="status-pill">${escapeHtml(displayLabel(TASK_STATUS_LABELS, task.status))}</span></td>
          <td>${escapeHtml(task.progress ?? 0)}%</td>
          <td>${escapeHtml(formatDateTime(task.updatedAt))}</td>
          <td>${taskActionButtons(task)}</td>
        </tr>
      `;
      })
      .join("");
    applyActionPermissions();
    syncTaskActionButtons();
  }

  function taskActionButtons(task) {
    return `
      <div class="row-actions" aria-label="任务操作">
        <button type="button" class="icon-button" data-task-action="view" aria-label="查看任务" title="查看任务">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>
        </button>
        <button type="button" class="icon-button" data-task-action="cancel" data-cancel-allowed="${canCancelTask(task) ? "true" : "false"}" data-permission="${IMAGERY_TASK_CANCEL_PERMISSION}" aria-label="取消任务" title="取消任务">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12"></path><path d="M18 6 6 18"></path></svg>
        </button>
        <button type="button" class="icon-button" data-task-action="retry" data-retry-allowed="${canRetryTask(task) ? "true" : "false"}" data-permission="${IMAGERY_TASK_RETRY_PERMISSION}" aria-label="重试任务" title="重试任务">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"></path><path d="M21 4v6h-6"></path></svg>
        </button>
        <button type="button" class="icon-button" data-task-action="archive" data-archive-allowed="${canArchiveTask(task) ? "true" : "false"}" data-permission="${IMAGERY_TASK_ARCHIVE_PERMISSION}" aria-label="归档任务" title="归档任务">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 8v13H3V8"></path><path d="M1 3h22v5H1Z"></path><path d="M10 12h4"></path></svg>
        </button>
      </div>
    `;
  }

  function syncTaskActionButtons() {
    document.querySelectorAll('[data-task-action="cancel"]').forEach((button) => {
      if (button.dataset.cancelAllowed !== "true") {
        button.disabled = true;
        button.setAttribute("aria-disabled", "true");
      }
    });
    document.querySelectorAll('[data-task-action="retry"]').forEach((button) => {
      if (button.dataset.retryAllowed !== "true") {
        button.disabled = true;
        button.setAttribute("aria-disabled", "true");
      }
    });
    document.querySelectorAll('[data-task-action="archive"]').forEach((button) => {
      if (button.dataset.archiveAllowed !== "true") {
        button.disabled = true;
        button.setAttribute("aria-disabled", "true");
      }
    });
  }

  function renderTaskEvents(task) {
    const target = $("#taskEventList");
    if (!target) return;
    const events = Array.isArray(task?.events) ? task.events : [];
    if (!events.length) {
      target.innerHTML = '<p class="trace-empty">暂无过程日志</p>';
      return;
    }
    target.innerHTML = events
      .map(
        (event) => `
          <article class="trace-item">
            <strong>${escapeHtml(displayLabel(TASK_STATUS_LABELS, event.status))} · ${escapeHtml(event.progress ?? 0)}%</strong>
            <span>${escapeHtml(formatDateTime(event.at))} · ${escapeHtml(event.message || "-")}</span>
          </article>
        `,
      )
      .join("");
  }

  function taskScene(task = activeTask()) {
    const sceneId = String(task?.sceneId || "").trim();
    if (!sceneId) return null;
    return state.scenes.find((scene) => String(scene.id || "") === sceneId) || null;
  }

  function taskQualityIssues(task = activeTask()) {
    const taskId = String(task?.id || "").trim();
    const sceneId = String(task?.sceneId || "").trim();
    return state.imageryIssues.filter((issue) => {
      const issueTaskId = String(issue.taskId || "").trim();
      const issueSceneId = String(issue.sceneId || "").trim();
      return (taskId && issueTaskId === taskId) || (sceneId && issueSceneId === sceneId);
    });
  }

  function taskTraceItems(task = activeTask()) {
    const scene = taskScene(task);
    const sceneId = String(task?.sceneId || "").trim();
    const taskLayerRecordCode = task && task.publishedLayerRecordCode ? task.publishedLayerRecordCode : task?.publishedLayerId || task?.layerRecordCode || task?.layerId || "";
    const sceneLayerRecordCode = scene && scene.publishedLayerRecordCode ? scene.publishedLayerRecordCode : scene?.publishedLayerId || "";
    const layerCode =
      taskLayerRecordCode ||
      sceneLayerRecordCode ||
      "";
    const items = [];

    if (sceneId) {
      items.push({
        label: "影像场景",
        value: scene?.name || sceneId,
        meta: [scene?.satellite || "", scene?.sensor || "", displayLabel(SCENE_STATUS_LABELS, scene?.status)].filter(Boolean).join(" / "),
        href: `admin-imagery.html?sceneId=${encodeURIComponent(sceneId)}`,
      });
    }

    if (layerCode) {
      items.push({
        label: "发布图层",
        value: layerCode,
        meta: scene?.publishedLayerAt ? `发布时间 ${formatDateTime(scene.publishedLayerAt)}` : "影像发布成果",
        href: `admin-map-layers.html?layerCode=${encodeURIComponent(layerCode)}`,
      });
    }

    taskQualityIssues(task)
      .slice(0, 5)
      .forEach((issue) => {
        const issueId = issue.issueId || "";
        const params = [];
        if (issue.sceneId || sceneId) params.push(`sceneId=${encodeURIComponent(issue.sceneId || sceneId)}`);
        if (issue.taskId || task?.id) params.push(`taskId=${encodeURIComponent(issue.taskId || task.id)}`);
        const issueTail = params.length ? `&${params.join("&")}` : "";
        items.push({
          label: "异常问题",
          value: displayLabel(IMAGERY_ISSUE_TYPE_LABELS, issue.issueType),
          meta: `${displayLabel(ISSUE_SEVERITY_LABELS, issue.severity)} / ${imageryIssueStatusLabel(issue.status)} / ${issue.message || "-"}`,
          href: issueId ? `admin-imagery.html?imageryIssueId=${encodeURIComponent(issueId)}${issueTail}` : `admin-imagery.html?${params.join("&")}`,
        });
      });

    if (task?.sourcePath) {
      items.push({
        label: "源文件",
        value: task.sourcePath,
        meta: "影像任务输入",
        href: "",
      });
    }

    if (task?.cogPath) {
      items.push({
        label: "输出 COG",
        value: task.cogPath,
        meta: "影像任务成果",
        href: "",
      });
    }

    return items;
  }

  function renderTaskTrace(task = activeTask()) {
    const target = $("#taskTraceList");
    if (!target) return;
    const items = taskTraceItems(task);
    if (!items.length) {
      target.innerHTML = '<p class="trace-empty">暂无任务追溯入口</p>';
      return;
    }
    target.innerHTML = items
      .map(
        (item) => `
          <article class="trace-item">
            <strong>${item.href ? traceLink(item.href, item.label) : escapeHtml(item.label)}</strong>
            <span>${escapeHtml(item.value || "-")}</span>
            <span>${escapeHtml(item.meta || "-")}</span>
          </article>
        `,
      )
      .join("");
  }

  function renderTaskDetail(task = activeTask()) {
    const panel = $("#taskDetailPanel");
    if (!task) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      return;
    }
    $("#taskDetailTitle").textContent = `${task.name || task.id || "任务"}详情`;
    $("#taskDetailEmpty").hidden = true;
    $("#taskDetailGrid").innerHTML = [
      detailItem("任务 ID", task.id || "-"),
      detailItem("任务类型", task.type || "-"),
      detailItem("状态", displayLabel(TASK_STATUS_LABELS, task.status)),
      detailItem("进度", `${task.progress ?? 0}%`),
      detailItem("影像/场景", task.sceneId || "-"),
      detailItem("源文件", task.sourcePath || "-"),
      detailItem("输出 COG", task.cogPath || "-"),
      detailItem("失败原因", task.message || "-"),
      detailItem("更新时间", formatDateTime(task.updatedAt)),
    ].join("");
    renderTaskTrace(task);
    renderTaskEvents(task);
    $("#taskDetailOutput").textContent = stringifyPretty(task, {});
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    renderTasks();
    const cancelButton = $("#cancelTask");
    if (cancelButton && !cancelButton.classList.contains("permission-disabled")) {
      cancelButton.disabled = !canCancelTask(task);
    }
    const retryButton = $("#retryTask");
    if (retryButton && !retryButton.classList.contains("permission-disabled")) {
      retryButton.disabled = !canRetryTask(task);
    }
    const archiveButton = $("#archiveTask");
    if (archiveButton && !archiveButton.classList.contains("permission-disabled")) {
      archiveButton.disabled = !canArchiveTask(task);
    }
  }

  function closeTaskDetail() {
    $("#taskDetailPanel").classList.add("hidden");
    $("#taskDetailPanel").setAttribute("aria-hidden", "true");
  }

  async function retryTask(task = activeTask()) {
    if (!task) return;
    setStatus("busy", "正在重试影像任务...");
    try {
      const payload = await api(`/api/tasks/${encodeURIComponent(task.id)}/retry`, { method: "POST" });
      state.activeTaskId = payload.task?.id || "";
      await loadTasks();
      await loadTaskEvents();
      await loadImageryIssues();
      renderTaskDetail(activeTask() || payload.task);
      setStatus("online", "影像任务已重新排队。");
    } catch (error) {
      setStatus("offline", `影像任务重试失败：${error.message}`);
    }
  }

  async function cancelTask(task = activeTask()) {
    if (!task) return;
    setStatus("busy", "正在取消影像任务...");
    try {
      const payload = await api(`/api/tasks/${encodeURIComponent(task.id)}/cancel`, { method: "POST" });
      state.activeTaskId = payload.task?.id || task.id;
      await loadTasks();
      await loadTaskEvents();
      await loadImageryIssues();
      renderTaskDetail(activeTask() || payload.task);
      setStatus("online", "影像任务已取消。");
    } catch (error) {
      setStatus("offline", `影像任务取消失败：${error.message}`);
    }
  }

  async function archiveTask(task = activeTask()) {
    if (!task) return;
    setStatus("busy", "正在归档影像任务...");
    try {
      const payload = await api(`/api/tasks/${encodeURIComponent(task.id)}/archive`, { method: "POST" });
      state.activeTaskId = payload.task?.id || task.id;
      await loadTasks();
      await loadTaskEvents();
      await loadImageryIssues();
      renderTaskDetail(activeTask() || payload.task);
      setStatus("online", "影像任务已归档。");
    } catch (error) {
      setStatus("offline", `影像任务归档失败：${error.message}`);
    }
  }

  function handleTaskRowAction(event) {
    const button = event.target.closest("[data-task-action]");
    if (!button) return false;
    event.stopPropagation();
    if (button.disabled) return true;
    const row = button.closest("tr[data-id]");
    const task = state.tasks.find((item) => String(item.id) === String(row?.dataset.id)) || null;
    if (!task) return true;
    state.activeTaskId = task.id;
    if (button.dataset.taskAction === "cancel") {
      cancelTask(task);
    } else if (button.dataset.taskAction === "retry") {
      retryTask(task);
    } else if (button.dataset.taskAction === "archive") {
      archiveTask(task);
    } else {
      renderTaskDetail(task);
    }
    return true;
  }

  async function saveSceneAccess(event) {
    event.preventDefault();
    const sceneId = $("#imageryId").value.trim();
    if (!sceneId) return;
    setStatus("busy", "正在保存影像权限...");
    try {
      const saved = await api(`/api/scenes/${encodeURIComponent(sceneId)}`, {
        method: "PATCH",
        body: JSON.stringify(scenePayloadFromForm()),
      });
      state.activeId = saved.id;
      closeImageryEditor();
      await loadScenes();
      await loadSceneEvents();
      await loadImageryIssues();
      renderDetail(state.scenes.find((scene) => String(scene.id) === String(saved.id)) || saved);
      setStatus("online", "影像权限已保存。");
    } catch (error) {
      setStatus("offline", `影像保存失败：${error.message}`);
    }
  }

  async function deleteScene(scene = activeScene()) {
    if (!scene) return;
    setStatus("busy", "正在删除影像...");
    try {
      await api(`/api/scenes/${encodeURIComponent(scene.id)}`, { method: "DELETE" });
      state.activeId = "";
      closeImageryEditor();
      closeImageryDetail();
      await loadScenes();
      await loadSceneEvents();
      await loadImageryIssues();
      setStatus("online", "影像已删除。");
    } catch (error) {
      setStatus("offline", `影像删除失败：${error.message}`);
    }
  }

  async function restoreScene(scene = activeScene()) {
    if (!scene) return;
    setStatus("busy", "正在恢复影像...");
    try {
      const payload = await api(`/api/scenes/${encodeURIComponent(scene.id)}/restore`, { method: "POST" });
      state.activeId = payload.scene?.id || scene.id;
      await loadScenes();
      await loadSceneEvents();
      await loadImageryIssues();
      renderDetail(state.scenes.find((item) => String(item.id) === String(state.activeId)) || payload.scene);
      setStatus("online", "影像已恢复。");
    } catch (error) {
      setStatus("offline", `影像恢复失败：${error.message}`);
    }
  }

  async function archiveScene(scene = activeScene()) {
    if (!scene) return;
    setStatus("busy", "正在归档影像...");
    try {
      const payload = await api(`/api/scenes/${encodeURIComponent(scene.id)}/archive`, { method: "POST" });
      state.activeId = payload.scene?.id || scene.id;
      await loadScenes();
      await loadSceneEvents();
      await loadImageryIssues();
      renderDetail(state.scenes.find((item) => String(item.id) === String(state.activeId)) || payload.scene);
      setStatus("online", "影像已归档，关联发布图层已暂停。");
    } catch (error) {
      setStatus("offline", `影像归档失败：${error.message}`);
    }
  }

  function uploadMetadata(prefix) {
    return {
      name: $(`#${prefix}Name`)?.value.trim() || "",
      satellite: $("#uploadSatellite")?.value.trim() || "",
      sensor: $("#uploadSensor")?.value.trim() || "",
      capturedAt: $("#uploadCapturedAt")?.value || "",
      resolution: $("#uploadResolution")?.value.trim() || "",
      bounds: $("#uploadBounds")?.value.trim() || "",
      projectId: $("#uploadProjectId")?.value.trim() || "",
      areaCode: $("#uploadAreaCode")?.value.trim() || "",
      allowedRoles: $("#uploadAllowedRoles")?.value.trim() || "",
      allowedUsers: $("#uploadAllowedUsers")?.value.trim() || "",
    };
  }

  async function uploadImagery(event) {
    event.preventDefault();
    const file = $("#imageryFile").files[0];
    if (!file) {
      setStatus("warning", "请选择需要上传的 GeoTIFF / TIFF 文件。");
      return;
    }
    const form = new FormData();
    Object.entries(uploadMetadata("upload")).forEach(([key, value]) => form.append(key, value));
    form.append("asyncMode", "true");
    form.append("file", file);
    setStatus("busy", "正在创建影像入库任务...");
    try {
      const response = await AdminCommon.fetchWithSession("/api/scenes/upload", {
        method: "POST",
        body: form,
      });
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json") ? await response.json() : await response.text();
      if (!response.ok) {
        const detail = payload && typeof payload === "object" ? payload.detail || JSON.stringify(payload) : String(payload || response.statusText);
        throw new Error(`${response.status} ${detail}`);
      }
      await loadTasks();
      await loadTaskEvents();
      await loadImageryIssues();
      setStatus("online", "影像入库任务已创建。");
    } catch (error) {
      setStatus("offline", `影像上传失败：${error.message}`);
    }
  }

  async function registerImagery(event) {
    event.preventDefault();
    const path = $("#registerPath").value.trim();
    if (!path) {
      setStatus("warning", "请填写服务器文件路径。");
      return;
    }
    setStatus("busy", "正在注册服务器影像...");
    try {
      await api("/api/scenes/register", {
        method: "POST",
        body: JSON.stringify({ ...uploadMetadata("register"), path, name: $("#registerName").value.trim() }),
      });
      await loadTasks();
      await loadTaskEvents();
      await loadImageryIssues();
      setStatus("online", "服务器影像注册任务已创建。");
    } catch (error) {
      setStatus("offline", `影像注册失败：${error.message}`);
    }
  }

  async function publishSceneLayer(scene = activeScene()) {
    if (!scene) return;
    setStatus("busy", "\u6b63\u5728\u53d1\u5e03\u5f71\u50cf\u56fe\u5c42...");
    try {
      const payload = await api(`/api/scenes/${encodeURIComponent(scene.id)}/publish-layer`, {
        method: "POST",
        body: JSON.stringify(sceneLayerPublishPayload(scene)),
      });
      state.activeId = payload.scene?.id || scene.id;
      await loadScenes();
      await loadSceneEvents();
      await loadImageryIssues();
      renderDetail(state.scenes.find((item) => String(item.id) === String(state.activeId)) || payload.scene);
      renderSceneOperationResult(payload);
      setStatus("online", "\u5f71\u50cf\u5df2\u53d1\u5e03\u5230\u5730\u56fe\u56fe\u5c42\u3002");
    } catch (error) {
      setStatus("offline", `\u5f71\u50cf\u53d1\u5e03\u5931\u8d25\uff1a${error.message}`);
    }
  }

  function handleRowAction(event) {
    const sceneButton = event.target.closest("[data-scene-action]");
    if (sceneButton) {
      event.preventDefault();
      event.stopPropagation();
      if (sceneButton.disabled) return true;
      const row = sceneButton.closest("tr[data-id]");
      const scene = state.scenes.find((item) => String(item.id) === String(row?.dataset.id)) || null;
      if (!scene) return true;
      state.activeId = scene.id;
      if (sceneButton.dataset.sceneAction === "restore") {
        restoreScene(scene);
      } else if (sceneButton.dataset.sceneAction === "archive") {
        archiveScene(scene);
      } else if (sceneButton.dataset.sceneAction === "publish-layer") {
        syncSceneLayerPublishForm(scene);
        publishSceneLayer(scene);
      } else if (sceneButton.dataset.sceneAction === "publication-receipt") {
        exportScenePublicationReceipt(scene);
      } else if (sceneButton.dataset.sceneAction === "delivery-receipt") {
        exportSceneDeliveryReceipt(scene);
      }
      return true;
    }
    const button = event.target.closest("[data-row-action]");
    if (!button) return false;
    event.stopPropagation();
    if (button.disabled) return true;
    const row = button.closest("tr[data-id]");
    const scene = state.scenes.find((item) => String(item.id) === String(row?.dataset.id)) || null;
    if (!scene) return true;
    state.activeId = scene.id;
    const action = button.dataset.rowAction;
    if (action === "view") {
      renderDetail(scene);
    } else if (action === "edit") {
      openImageryEditor("edit", scene);
      renderRows();
    } else if (action === "delete") {
      deleteScene(scene);
    }
    return true;
  }

  function handleSceneReceiptSummaryAction(event) {
    const button = event.target.closest("[data-receipt-action]");
    if (!button) return false;
    event.preventDefault();
    event.stopPropagation();
    if (button.disabled) return true;
    const action = button.dataset.receiptAction;
    const scene = activeScene();
    if (action === "scene-delivery") {
      exportSceneDeliveryReceipt(scene);
    }
    return true;
  }

  function initialize() {
    initShell();
    if (initialSceneId && $("#sceneKeyword")) $("#sceneKeyword").value = initialSceneId;
    if (initialPublished && $("#scenePublishedFilter")) $("#scenePublishedFilter").value = initialPublished;
    if (initialTaskStatus) {
      if ($("#taskStatusFilter")) $("#taskStatusFilter").value = initialTaskStatus;
      if ($("#taskEventStatusFilter")) $("#taskEventStatusFilter").value = initialTaskStatus;
    }
    if (initialImageryIssueStatus && $("#imageryIssueStatusFilter")) $("#imageryIssueStatusFilter").value = initialImageryIssueStatus;
    if (initialTaskId) {
      if ($("#taskEventTaskFilter")) $("#taskEventTaskFilter").value = initialTaskId;
      if ($("#imageryIssueTaskFilter")) $("#imageryIssueTaskFilter").value = initialTaskId;
    }
    if (initialImageryIssueId) {
      if ($("#imageryIssueKeyword")) $("#imageryIssueKeyword").value = initialImageryIssueId;
      if (initialSceneId && $("#imageryIssueSceneFilter")) $("#imageryIssueSceneFilter").value = initialSceneId;
      if (initialTaskId && $("#imageryIssueTaskFilter")) $("#imageryIssueTaskFilter").value = initialTaskId;
    }
    pager = createLedgerPager({ anchor: $("#imageryRows").closest(".table-wrap"), onPageChange: loadScenes });
    $("#openUploadPanel")?.setAttribute("data-permission", IMAGERY_SCENE_CREATE_PERMISSION);
    $("#uploadImagery")?.setAttribute("data-permission", IMAGERY_SCENE_CREATE_PERMISSION);
    $("#registerImagery")?.setAttribute("data-permission", IMAGERY_SCENE_CREATE_PERMISSION);
    $("#saveImagery")?.setAttribute("data-permission", IMAGERY_SCENE_UPDATE_PERMISSION);
    $("#deleteImagery")?.setAttribute("data-permission", IMAGERY_SCENE_DELETE_PERMISSION);
    $("#exportSceneEvents")?.setAttribute("data-permission", IMAGERY_SCENE_EXPORT_PERMISSION);
    $("#exportTaskEvents")?.setAttribute("data-permission", IMAGERY_SCENE_EXPORT_PERMISSION);
    $("#exportImageryIssues")?.setAttribute("data-permission", IMAGERY_SCENE_EXPORT_PERMISSION);
    $("#exportImageryWorkflowSummary")?.setAttribute("data-permission", IMAGERY_SCENE_EXPORT_PERMISSION);
    $("#exportSceneDeliveryReceipt")?.setAttribute("data-permission", IMAGERY_SCENE_EXPORT_PERMISSION);
    $("#exportScenePublicationReceipt")?.setAttribute("data-permission", IMAGERY_SCENE_EXPORT_PERMISSION);
    $("#updateSceneDelivery")?.setAttribute("data-permission", IMAGERY_SCENE_DELIVERY_PERMISSION);
    setCompoundPermission("#publishSceneLayer", IMAGERY_LAYER_PUBLISH_PERMISSION, IMAGERY_MAP_LAYER_REQUIRED_PERMISSION, IMAGERY_MAP_LAYER_UPSERT_PERMISSIONS);
    $("#cancelTask")?.setAttribute("data-permission", IMAGERY_TASK_CANCEL_PERMISSION);
    $("#retryTask")?.setAttribute("data-permission", IMAGERY_TASK_RETRY_PERMISSION);
    $("#archiveTask")?.setAttribute("data-permission", IMAGERY_TASK_ARCHIVE_PERMISSION);
    $("#refreshImageryWorkflowSummary")?.addEventListener("click", loadImageryWorkflowSummary);
    $("#refreshImageryOperationQueue")?.addEventListener("click", loadImageryOperationQueue);
    $("#exportImageryWorkflowSummary")?.addEventListener("click", exportImageryWorkflowSummary);
    $("#reloadScenes").addEventListener("click", () => {
      loadScenes();
      loadImageryIssues();
    });
    $("#reloadTasks").addEventListener("click", () => {
      loadTasks();
      loadImageryIssues();
    });
    $("#openUploadPanel").addEventListener("click", () => {
      $("#uploadPanel").classList.remove("hidden");
      $("#uploadPanel").setAttribute("aria-hidden", "false");
    });
    $("#closeUploadPanel").addEventListener("click", () => {
      $("#uploadPanel").classList.add("hidden");
      $("#uploadPanel").setAttribute("aria-hidden", "true");
    });
    $("#imageryForm").addEventListener("submit", saveSceneAccess);
    $("#cancelImageryEdit").addEventListener("click", closeImageryEditor);
    $("#closeImageryDetail").addEventListener("click", closeImageryDetail);
    $("#imageryPreviewImage")?.addEventListener("load", (event) => {
      const image = event.currentTarget;
      if (String(activeScene()?.id || "") !== image.dataset.sceneId) return;
      image.hidden = false;
      $("#imageryPreviewStatus").hidden = true;
    });
    $("#imageryPreviewImage")?.addEventListener("error", (event) => {
      const image = event.currentTarget;
      if (String(activeScene()?.id || "") !== image.dataset.sceneId) return;
      image.hidden = true;
      const status = $("#imageryPreviewStatus");
      status.hidden = false;
      status.textContent = "预览生成失败，请检查源 COG 文件和影像转换任务";
    });
    $("#exportSceneDeliveryReceipt")?.addEventListener("click", () => exportSceneDeliveryReceipt(activeScene()));
    $("#exportScenePublicationReceipt")?.addEventListener("click", () => exportScenePublicationReceipt(activeScene()));
    $("#sceneDeliveryReceiptSummary")?.addEventListener("click", handleSceneReceiptSummaryAction);
    $("#updateSceneDelivery")?.addEventListener("click", () => updateSceneDelivery(activeScene()));
    $("#closeTaskDetail").addEventListener("click", closeTaskDetail);
    $("#cancelTask").addEventListener("click", () => cancelTask(activeTask()));
    $("#retryTask").addEventListener("click", () => retryTask(activeTask()));
    $("#archiveTask").addEventListener("click", () => archiveTask(activeTask()));
    $("#deleteImagery").addEventListener("click", () => deleteScene(activeScene()));
    $("#uploadForm").addEventListener("submit", uploadImagery);
    $("#registerForm").addEventListener("submit", registerImagery);
    $("#publishSceneLayer")?.addEventListener("click", () => publishSceneLayer(activeScene()));
    $("#includeDeletedScenes")?.addEventListener("change", reloadScenesFromFirstPage);
    $("#includeArchivedTasks")?.addEventListener("change", () => {
      loadTasks();
      loadImageryIssues();
    });
    $("#includeArchivedImageryIssues")?.addEventListener("change", loadImageryIssues);
    $("#sceneStatusFilter")?.addEventListener("change", reloadScenesFromFirstPage);
    $("#scenePublishedFilter")?.addEventListener("change", reloadScenesFromFirstPage);
    $("#sceneDeliveryStatusFilter")?.addEventListener("change", reloadScenesFromFirstPage);
    $("#taskStatusFilter")?.addEventListener("change", () => {
      loadTasks();
      loadImageryIssues();
    });
    $("#refreshSceneEvents")?.addEventListener("click", loadSceneEvents);
    $("#exportSceneEvents")?.addEventListener("click", exportSceneEvents);
    $("#sceneEventTypeFilter")?.addEventListener("change", loadSceneEvents);
    $("#refreshTaskEvents")?.addEventListener("click", loadTaskEvents);
    $("#exportTaskEvents")?.addEventListener("click", exportTaskEvents);
    $("#taskEventStatusFilter")?.addEventListener("change", loadTaskEvents);
    $("#refreshImageryIssues")?.addEventListener("click", loadImageryIssues);
    $("#exportImageryIssues")?.addEventListener("click", exportImageryIssues);
    $("#imageryIssueSeverityFilter")?.addEventListener("change", loadImageryIssues);
    $("#imageryIssueStatusFilter")?.addEventListener("change", loadImageryIssues);
    ["#sceneKeyword", "#projectFilter", "#areaFilter"].forEach((selector) => {
      $(selector).addEventListener("input", () => {
        window.clearTimeout(sceneFilterTimer);
        sceneFilterTimer = window.setTimeout(reloadScenesFromFirstPage, 180);
      });
    });
    ["#sceneEventKeyword", "#sceneEventActionFilter", "#sceneEventSceneFilter"].forEach((selector) => {
      $(selector)?.addEventListener("input", () => window.setTimeout(loadSceneEvents, 180));
    });
    ["#taskEventKeyword", "#taskEventActionFilter", "#taskEventTaskFilter"].forEach((selector) => {
      $(selector)?.addEventListener("input", () => window.setTimeout(loadTaskEvents, 180));
    });
    ["#imageryIssueKeyword", "#imageryIssueTypeFilter", "#imageryIssueSceneFilter", "#imageryIssueTaskFilter"].forEach((selector) => {
      $(selector)?.addEventListener("input", () => window.setTimeout(loadImageryIssues, 180));
    });
    $("#imageryIssueRows")?.addEventListener("click", (event) => {
      if (handleImageryIssueAction(event)) return;
      const row = event.target.closest("tr[data-issue-id]");
      if (!row) return;
      state.activeImageryIssueId = row.dataset.issueId;
      const issue = state.imageryIssues.find((item) => String(item.issueId || "") === String(row.dataset.issueId)) || null;
      if (issue?.sceneId) {
        state.activeId = issue.sceneId;
        renderDetail(activeScene());
      }
      if (issue?.taskId) {
        state.activeTaskId = issue.taskId;
        renderTaskDetail(activeTask());
      }
      renderImageryIssueRows();
    });
    $("#imageryOperationQueueRows")?.addEventListener("click", handleImageryOperationQueueAction);
    $("#imageryRows").addEventListener("click", (event) => {
      if (handleRowAction(event)) return;
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      state.activeId = row.dataset.id;
      renderDetail(activeScene());
    });
    $("#taskRows").addEventListener("click", (event) => {
      if (handleTaskRowAction(event)) return;
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      state.activeTaskId = row.dataset.id;
      renderTaskDetail(activeTask());
    });
    loadImageryWorkflowSummary();
    loadImageryOperationQueue();
    loadScenes();
    loadSceneEvents();
    loadTasks();
    loadTaskEvents();
    loadImageryIssues();
  }

  initialize();
})();
