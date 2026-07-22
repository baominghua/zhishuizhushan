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
    setStatus,
    splitValues,
    stringifyPretty,
  } = AdminCommon;

  const PAGE_PERMISSION = "map.layers.view";
  const ACTION_PERMISSIONS = {
    create: "map.layers.create",
    update: "map.layers.update",
    delete: "map.layers.delete",
    restore: "map.layers.restore",
    publish: "map.layers.publish",
    export: "map.layers.export",
  };
  const state = { layers: [], layerEvents: [], layerDashboard: null, activeId: "" };
  let pager;
  let keywordTimer;
  let initialLayerCode =
    new URLSearchParams(window.location.search).get("layerCode") ||
    new URLSearchParams(window.location.search).get("layerId") ||
    "";
  let initialVisibleOnDashboard = new URLSearchParams(window.location.search).get("visibleOnDashboard") || "";
  const VIEW_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>';
  const EDIT_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9"></path><path d="m16.5 3.5 4 4L8 20H4v-4L16.5 3.5Z"></path></svg>';
  const DELETE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M6 6l1 15h10l1-15"></path><path d="M10 11v6"></path><path d="M14 11v6"></path></svg>';
  const PUBLISH_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12"></path><path d="m7 8 5-5 5 5"></path><path d="M5 15v4h14v-4"></path></svg>';
  const PAUSE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14"></path><path d="M16 5v14"></path></svg>';
  const RESTORE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.4-6.4"></path><path d="M18 3v5h-5"></path><path d="M21 12a9 9 0 0 1-15.4 6.4"></path><path d="M6 21v-5h5"></path></svg>';
  const RECEIPT_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h8l4 4v14H7z"></path><path d="M15 3v5h5"></path><path d="M10 13h7"></path><path d="M10 17h5"></path></svg>';
  const LAYER_STATUS_LABELS = {
    published: "已发布",
    draft: "草稿",
    paused: "已暂停",
    archived: "已归档",
    deleted: "已删除",
  };
  const LAYER_TYPE_LABELS = {
    vector: "矢量图层",
    raster: "栅格图层",
    "forest-block": "林班边界",
    "forest-right": "林权档案",
    imagery: "影像图层",
    terrain: "地形图层",
    boundary: "行政边界",
  };
  const SOURCE_TYPE_LABELS = {
    importBatch: "成果批次",
    imagery: "影像发布",
    manual: "手动配置",
  };
  const LAYER_EVENT_ACTION_LABELS = {
    create: "新建",
    update: "更新",
    delete: "删除",
    restore: "恢复",
    publish: "发布",
    archive: "归档",
    "scene-publish": "影像发布",
    "import-publish": "成果发布",
  };
  const RISK_STATUS_LABELS = {
    clear: "低风险",
    warning: "需复核",
    blocked: "禁止发布",
    unknown: "未评估",
  };
  const QUALITY_STATUS_LABELS = {
    passed: "通过",
    warning: "需复核",
    blocked: "不通过",
    unknown: "未评估",
  };
  const REVIEW_RECOMMENDATION_LABELS = {
    can_publish: "可发布",
    needs_correction: "需修正",
    reject_publish: "暂缓发布",
    manual_review: "人工复核",
  };

  function activeLayer() {
    return state.layers.find((layer) => String(layer.id) === String(state.activeId)) || null;
  }

  function layerProperties(layer = {}) {
    return layer.properties && typeof layer.properties === "object" ? layer.properties : {};
  }

  function displayLabel(labels, value, fallback = "未评估") {
    if (!value) return fallback;
    return labels[value] || value;
  }

  function layerSourceLinks(layer = {}) {
    return Array.isArray(layer.sourceLinks) ? layer.sourceLinks.filter((link) => link && link.href) : [];
  }

  function layerSourceTrace(layer = {}) {
    const properties = layerProperties(layer);
    const sourceLinks = layerSourceLinks(layer);
    const sourceType = layer.sourceType || "";
    if (properties.importBatchId) {
      return {
        type: sourceType || "importBatch",
        label: "成果批次",
        primaryLabel: "入库批次",
        primaryValue: properties.importBatchId,
        sceneId: properties.sourceSceneId || "",
        sourceLinks,
      };
    }
    if (properties.sourceSceneId) {
      return {
        type: sourceType || "imagery",
        label: "影像发布",
        primaryLabel: "影像场景",
        primaryValue: properties.sourceSceneId,
        sceneId: properties.sourceSceneId,
        sourceLinks,
      };
    }
    return {
      type: sourceType || "manual",
      label: "手动配置",
      primaryLabel: "数据来源",
      primaryValue: layer.dataSource || "后台手动维护",
      sceneId: "",
      sourceLinks,
    };
  }

  function renderSourceCell(layer) {
    const trace = layerSourceTrace(layer);
    return `
      <div class="cell-stack">
        <strong>${escapeHtml(trace.label)}</strong>
        <small>${escapeHtml(trace.primaryValue || "-")}</small>
      </div>
    `;
  }

  function renderRiskCell(layer) {
    const properties = layerProperties(layer);
    const status = properties.publishRiskStatus || "unknown";
    return `
      <div class="cell-stack">
        <strong>${escapeHtml(displayLabel(RISK_STATUS_LABELS, status))}</strong>
        <small>${escapeHtml(displayLabel(QUALITY_STATUS_LABELS, properties.qualityStatus, "质量未评估"))}</small>
      </div>
    `;
  }

  function isDeletedLayer(layer) {
    return Boolean(layer?.deletedAt);
  }

  function layerActionButtons(layer) {
    if (isDeletedLayer(layer)) {
      return `
        <div class="row-actions" aria-label="图层操作">
          <button type="button" class="icon-button" data-row-action="view" aria-label="查看图层" title="查看图层">${VIEW_ICON}</button>
          <button type="button" class="icon-button" data-layer-action="restore" data-permission="${ACTION_PERMISSIONS.restore}" aria-label="恢复图层" title="恢复图层">${RESTORE_ICON}</button>
        </div>
      `;
    }
    const published = Boolean(layer.visibleOnDashboard) || String(layer.status || "") === "published";
    const publishToggle = published
      ? `<button type="button" class="icon-button" data-layer-action="pause" data-permission="${ACTION_PERMISSIONS.publish}" aria-label="暂停发布" title="暂停发布">${PAUSE_ICON}</button>`
      : `<button type="button" class="icon-button" data-layer-action="publish" data-permission="${ACTION_PERMISSIONS.publish}" aria-label="发布到大屏" title="发布到大屏">${PUBLISH_ICON}</button>`;
    return `
      <div class="row-actions row-actions-extra-wide" aria-label="图层操作">
        <button type="button" class="icon-button" data-row-action="view" aria-label="查看图层" title="查看图层">${VIEW_ICON}</button>
        <button type="button" class="icon-button" data-row-action="edit" data-permission="${ACTION_PERMISSIONS.update}" aria-label="编辑图层" title="编辑图层">${EDIT_ICON}</button>
        ${publishToggle}
        <button type="button" class="icon-button" data-layer-action="receipt" data-permission="${ACTION_PERMISSIONS.export}" aria-label="导出发布回执" title="导出发布回执">${RECEIPT_ICON}</button>
        <button type="button" class="icon-button danger" data-row-action="delete" data-permission="${ACTION_PERMISSIONS.delete}" aria-label="删除图层" title="删除图层">${DELETE_ICON}</button>
      </div>
    `;
  }

  function renderRows() {
    const body = $("#layerRows");
    if (!state.layers.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="8">暂无图层记录</td></tr>';
      return;
    }
    body.innerHTML = state.layers
      .map((layer) => {
        const active = String(layer.id) === String(state.activeId) ? "active" : "";
        return `
          <tr data-id="${escapeHtml(layer.id)}" class="${active}">
            <td>${escapeHtml(layer.recordCode || "-")}</td>
            <td>${escapeHtml(layer.name || "-")}</td>
            <td>${escapeHtml(displayLabel(LAYER_TYPE_LABELS, layer.layerType, "-"))}</td>
            <td>${renderSourceCell(layer)}</td>
            <td>${renderRiskCell(layer)}</td>
            <td><div class="cell-stack"><strong>${escapeHtml(displayLabel(LAYER_STATUS_LABELS, layer.status, "未填"))}</strong><small>${escapeHtml(layer.visibleOnDashboard ? "发布到大屏" : "不发布到大屏")}</small></div></td>
            <td>${escapeHtml(layer.zIndex ?? "-")}</td>
            <td>${layerActionButtons(layer)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  function detailItem(label, value) {
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "未填")}</dd></div>`;
  }

  function renderLayerSourceTraceLegacy(layer = activeLayer()) {
    const target = $("#layerSourceTraceList");
    if (!target) return;
    if (!layer) {
      target.innerHTML = '<p class="trace-empty">请选择图层查看来源。</p>';
      return;
    }
    const trace = layerSourceTrace(layer);
    const links = [];
    if (trace.sceneId) {
      links.push(`<a href="admin-imagery.html?sceneId=${encodeURIComponent(trace.sceneId)}">影像 ${escapeHtml(trace.sceneId)}</a>`);
    }
    if (trace.type === "importBatch" && trace.primaryValue) {
      links.push(`<a href="admin-imports.html?batchId=${encodeURIComponent(trace.primaryValue)}">批次 ${escapeHtml(trace.primaryValue)}</a>`);
    }
    target.innerHTML = `
      <article class="trace-item">
        <strong>${escapeHtml(trace.label)} · ${escapeHtml(trace.primaryLabel)}</strong>
        <span>${escapeHtml(trace.primaryValue || "-")}</span>
        <span>${links.length ? links.join(" · ") : "暂无可跳转追溯入口"}</span>
      </article>
    `;
  }

  function layerSourceTraceItems(layer = {}, trace = layerSourceTrace(layer)) {
    const properties = layerProperties(layer);
    const items = [];
    const seen = new Set();
    const addItem = (item) => {
      const key = [item.href || "", item.label || "", item.value || ""].join("|");
      if (seen.has(key)) return;
      seen.add(key);
      items.push(item);
    };
    const layerCode = layer.recordCode || layer.id || "";
    addItem({
      label: "图层后台",
      value: layerCode || "-",
      href: layer.adminHref || (layerCode ? `admin-map-layers.html?layerCode=${encodeURIComponent(layerCode)}` : "admin-map-layers.html"),
      meta: "当前图层详情",
    });
    const dashboardHref =
      layer.dashboardHref ||
      (String(layer.status || "") === "published" && layer.visibleOnDashboard !== false ? "zhushan-bigdata.html#mapLayers" : "");
    if (dashboardHref) {
      addItem({
        label: "大屏入口",
        value: "地图图层",
        href: dashboardHref,
        meta: layer.visibleOnDashboard === false ? "后台可见" : "已发布到大屏",
      });
    }
    if (properties.importBatchId) {
      addItem({
        label: "入库批次",
        value: properties.importBatchId,
        href: `admin-imports.html?batchId=${encodeURIComponent(properties.importBatchId)}`,
        meta: "成果入库来源",
      });
    }
    if (properties.sourceSceneId) {
      addItem({
        label: "影像场景",
        value: properties.sourceSceneId,
        href: `admin-imagery.html?sceneId=${encodeURIComponent(properties.sourceSceneId)}`,
        meta: "影像发布来源",
      });
    }
    trace.sourceLinks.forEach((link) => {
      if (!link?.href) return;
      addItem({
        label: link.label || link.type || "来源",
        value: link.value || "",
        href: link.href,
        meta: displayLabel(SOURCE_TYPE_LABELS, link.type, "来源记录"),
      });
    });
    return items;
  }

  function renderLayerSourceTrace(layer = activeLayer()) {
    const target = $("#layerSourceTraceList");
    if (!target) return;
    if (!layer) {
      target.innerHTML = '<p class="trace-empty">请选择图层查看来源。</p>';
      return;
    }
    const trace = layerSourceTrace(layer);
    const items = layerSourceTraceItems(layer, trace);
    target.innerHTML = items.length
      ? items
          .map(
            (item) => `
              <article class="trace-item source-trace-item">
                <strong><a class="trace-link" href="${escapeHtml(item.href || "#")}">${escapeHtml(item.label || "来源")}</a></strong>
                <span>${escapeHtml(item.value || "-")}</span>
                <span>${escapeHtml(item.meta || trace.label || "-")}</span>
              </article>
            `,
          )
          .join("")
      : '<p class="trace-empty">暂无可跳转追溯入口。</p>';
  }

  function layerPermissionBoundaryItems(layer) {
    const published = Boolean(layer?.visibleOnDashboard) || String(layer?.status || "") === "published";
    const deleted = isDeletedLayer(layer);
    return [
      {
        key: "create",
        label: "新建图层",
        description: "登记后台图层目录、数据来源、样式和发布属性。",
        permission: ACTION_PERMISSIONS.create,
      },
      {
        key: "update",
        label: "编辑配置",
        description: "维护图层样式、来源追溯、关联林班和扩展字段。",
        permission: ACTION_PERMISSIONS.update,
      },
      {
        key: "publish",
        label: published ? "暂停发布" : "发布到大屏",
        description: published ? "从大屏下线图层，但保留后台图层台账。" : "将图层发布到智慧竹山大屏地图。",
        permission: ACTION_PERMISSIONS.publish,
      },
      {
        key: "delete",
        label: "软删除图层",
        description: deleted ? "当前图层已删除，删除动作不可重复执行。" : "从图层目录软删除，保留事件审计。",
        permission: ACTION_PERMISSIONS.delete,
      },
      {
        key: "restore",
        label: "恢复图层",
        description: deleted ? "将软删除图层恢复到后台目录。" : "仅软删除图层需要恢复权限。",
        permission: ACTION_PERMISSIONS.restore,
      },
      {
        key: "export",
        label: "事件导出",
        description: "导出图层事件流和发布审计记录。",
        permission: ACTION_PERMISSIONS.export,
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
      >
        <div>
          <strong>${escapeHtml(item.label)}</strong>
          <span>${escapeHtml(item.description)}</span>
        </div>
        <div class="permission-boundary-permissions" aria-label="${escapeHtml(item.label)}所需权限">
          <span class="permission-boundary-label">必需</span>
          <div class="ledger-chip-list">${permissionBoundaryChipList(item.permission)}</div>
        </div>
      </article>
    `;
  }

  function ensureLayerPermissionBoundary() {
    const detailGrid = $("#layerDetailGrid");
    if (!detailGrid) return null;
    if (!$("#layerPermissionBoundary")) {
      const wrapper = document.createElement("div");
      wrapper.className = "task-events permission-boundary-panel";
      wrapper.innerHTML = '<h3>操作权限边界</h3><div id="layerPermissionBoundary" class="permission-boundary-list" aria-label="地图图层操作权限边界"></div>';
      detailGrid.insertAdjacentElement("afterend", wrapper);
    }
    return $("#layerPermissionBoundary");
  }

  function renderLayerPermissionBoundary(layer) {
    const target = ensureLayerPermissionBoundary();
    if (!target) return;
    target.innerHTML = layerPermissionBoundaryItems(layer).map(permissionBoundaryItem).join("");
  }

  function linkedBlockCount(layer = {}) {
    const properties = layerProperties(layer);
    const storedCount = Number(properties.linkedBlockCount);
    if (Number.isFinite(storedCount) && storedCount >= 0) return storedCount;
    return Array.isArray(layer.linkedBlockCodes) ? layer.linkedBlockCodes.length : 0;
  }

  async function hydrateLayerTargets(layer = {}) {
    if (!layer.id) return layer;
    const [blocks, rights] = await Promise.all([
      api(`/api/map-layers/${encodeURIComponent(layer.id)}/targets?kind=blocks&limit=100&offset=0`),
      api(`/api/map-layers/${encodeURIComponent(layer.id)}/targets?kind=rights&limit=100&offset=0`),
    ]);
    const hydrated = {
      ...layer,
      linkedBlockCodes: (blocks.items || []).map((item) => item.blockCode).filter(Boolean),
      linkedRightArchiveCodes: (rights.items || []).map((item) => item.archiveCode).filter(Boolean),
      properties: {
        ...layerProperties(layer),
        linkedBlockCount: Number(blocks.total || 0),
        linkedRightArchiveCount: Number(rights.total || 0),
        linkedTargetsTruncated: Number(blocks.total || 0) > 100 || Number(rights.total || 0) > 100,
      },
    };
    const index = state.layers.findIndex((item) => String(item.id) === String(layer.id));
    if (index >= 0) state.layers[index] = hydrated;
    return hydrated;
  }

  async function showLayerDetail(layer = activeLayer()) {
    if (!layer) return renderDetail(layer);
    renderDetail(layer);
    try {
      renderDetail(await hydrateLayerTargets(layer));
    } catch (error) {
      setStatus("offline", `图层关联目标加载失败：${error.message}`);
    }
  }

  function renderDetail(layer = activeLayer()) {
    const panel = $("#layerDetailPanel");
    if (!layer) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      return;
    }
    const linkedCodes = Array.isArray(layer.linkedBlockCodes) ? layer.linkedBlockCodes : [];
    const totalLinkedBlocks = linkedBlockCount(layer);
    const linkedSample = linkedCodes.join(", ");
    const linked = totalLinkedBlocks > linkedCodes.length
      ? `${linkedSample || "-"} (共 ${totalLinkedBlocks} 条，仅显示前 100 条)`
      : linkedSample;
    const sourceTrace = layerSourceTrace(layer);
    const properties = layerProperties(layer);
    $("#layerDetailTitle").textContent = `${layer.name || layer.recordCode || "图层"}详情`;
    $("#layerDetailEmpty").hidden = true;
    $("#layerDetailGrid").innerHTML = [
      detailItem("图层编号", layer.recordCode || "-"),
      detailItem("图层名称", layer.name || "-"),
      detailItem("图层类型", displayLabel(LAYER_TYPE_LABELS, layer.layerType, "-")),
      detailItem("状态", displayLabel(LAYER_STATUS_LABELS, layer.status, "未填")),
      detailItem("数据来源", layer.dataSource || "-"),
      detailItem("来源类型", sourceTrace.label),
      detailItem(sourceTrace.primaryLabel, sourceTrace.primaryValue || "-"),
      detailItem("来源影像", sourceTrace.sceneId || "-"),
      detailItem("质量状态", displayLabel(QUALITY_STATUS_LABELS, properties.qualityStatus, "未评估")),
      detailItem("发布风险", displayLabel(RISK_STATUS_LABELS, properties.publishRiskStatus || "unknown")),
      detailItem("审核建议", displayLabel(REVIEW_RECOMMENDATION_LABELS, properties.reviewRecommendation, "未填写")),
      detailItem("显示层级", layer.zIndex ?? "-"),
      detailItem("发布到大屏", layer.visibleOnDashboard ? "发布" : "不发布"),
      detailItem("关联林班", linked || "未挂接"),
      detailItem("更新时间", formatDateTime(layer.updatedAt)),
      detailItem("样式 JSON", stringifyPretty(layer.style, {})),
      detailItem("扩展字段", stringifyPretty(layer.properties, {})),
    ].join("");
    renderLayerPermissionBoundary(layer);
    renderLayerSourceTrace(layer);
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    renderRows();
  }

  function fillForm(layer = {}) {
    state.activeId = layer.id || "";
    $("#layerFormTitle").textContent = layer.id ? "编辑图层" : "新建图层";
    $("#saveLayer").dataset.permission = layer.id ? ACTION_PERMISSIONS.update : ACTION_PERMISSIONS.create;
    $("#layerId").value = layer.id || "";
    $("#layerCode").value = layer.recordCode || "";
    $("#layerName").value = layer.name || "";
    $("#layerType").value = layer.layerType || "";
    $("#layerStatus").value = layer.status || "published";
    $("#dataSource").value = layer.dataSource || "";
    $("#zIndex").value = layer.zIndex ?? "";
    $("#visibleOnDashboard").value = layer.visibleOnDashboard === false ? "false" : "true";
    const linkedInput = $("#linkedBlockCodes");
    const linkedCodes = Array.isArray(layer.linkedBlockCodes) ? layer.linkedBlockCodes : [];
    const partialTargets = linkedBlockCount(layer) > linkedCodes.length;
    linkedInput.value = linkedCodes.join(", ");
    linkedInput.disabled = partialTargets;
    linkedInput.dataset.preserveRelations = partialTargets ? "true" : "false";
    linkedInput.title = partialTargets ? "关联目标超过 100 条，请通过关系台账分页管理" : "";
    $("#layerStyle").value = stringifyPretty(layer.style, {});
    $("#layerProperties").value = stringifyPretty(layer.properties, {});
    renderRows();
    applyActionPermissions();
  }

  async function openLayerEditor(mode, layer = {}) {
    closeLayerDetail();
    let editorLayer = mode === "edit" ? layer : {};
    if (mode === "edit" && layer.id) {
      try {
        editorLayer = await hydrateLayerTargets(layer);
      } catch (error) {
        setStatus("offline", `图层关联目标加载失败：${error.message}`);
      }
    }
    fillForm(editorLayer);
    $("#layerForm").classList.remove("hidden");
    $("#layerForm").setAttribute("aria-hidden", "false");
    $("#layerCode").focus();
  }

  function closeLayerEditor() {
    $("#layerForm").classList.add("hidden");
    $("#layerForm").setAttribute("aria-hidden", "true");
  }

  function closeLayerDetail() {
    $("#layerDetailPanel").classList.add("hidden");
    $("#layerDetailPanel").setAttribute("aria-hidden", "true");
  }

  function payloadFromForm() {
    const payload = {
      recordCode: $("#layerCode").value.trim() || undefined,
      name: $("#layerName").value.trim(),
      layerType: $("#layerType").value.trim() || null,
      status: $("#layerStatus").value.trim() || "published",
      dataSource: $("#dataSource").value.trim() || null,
      zIndex: $("#zIndex").value ? Number($("#zIndex").value) : 0,
      visibleOnDashboard: $("#visibleOnDashboard").value === "true",
      style: parseJson("样式 JSON", $("#layerStyle").value, {}),
      properties: parseJson("扩展 JSON", $("#layerProperties").value, {}),
    };
    if ($("#linkedBlockCodes").dataset.preserveRelations !== "true") {
      payload.linkedBlockCodes = splitValues($("#linkedBlockCodes").value);
    }
    return payload;
  }

  function applyInitialLayerFilters() {
    if (initialVisibleOnDashboard !== "true" && initialVisibleOnDashboard !== "false") return;
    $("#layerVisibleFilter").value = initialVisibleOnDashboard;
    initialVisibleOnDashboard = "";
  }

  function consumeInitialLayerSelection() {
    const targetCode = String(initialLayerCode || "").trim();
    if (!targetCode) return;
    const matched = state.layers.find((layer) => String(layer.id || "") === targetCode || String(layer.recordCode || "") === targetCode);
    if (!matched) return;
    state.activeId = matched.id;
    initialLayerCode = "";
  }

  async function loadLayers() {
    setStatus("busy", "正在加载地图图层...");
    pager.setBusy(true);
    try {
      const qs = query({
        q: $("#layerKeyword").value.trim(),
        status: $("#layerStatusFilter").value.trim(),
        sourceType: $("#layerSourceTypeFilter").value.trim(),
        publishRiskStatus: $("#layerRiskStatusFilter").value.trim(),
        visibleOnDashboard: $("#layerVisibleFilter").value.trim(),
        includeDeleted: $("#includeDeletedLayers")?.checked ? "true" : "",
        limit: pager.limit,
        offset: pager.offset,
      });
      const payload = await api(`/api/map-layers?${qs}`);
      if (pager.setTotal(payload.total ?? 0)) return loadLayers();
      state.layers = Array.isArray(payload.items) ? payload.items : [];
      consumeInitialLayerSelection();
      if (state.activeId && !activeLayer()) state.activeId = "";
      renderRows();
      renderDetail(activeLayer());
      setStatus("online", `已加载 ${payload.total ?? state.layers.length} 个图层。`);
    } catch (error) {
      setStatus("offline", `图层加载失败：${error.message}`);
    } finally {
      pager.setBusy(false);
    }
  }

  function reloadLayersFromFirstPage() {
    pager.reset();
    return loadLayers();
  }

  function layerEventQuery() {
    return query({
      q: $("#layerEventKeyword")?.value.trim() || "",
      action: $("#layerEventActionFilter")?.value.trim() || "",
      layerId: $("#layerEventLayerFilter")?.value.trim() || "",
      recordCode: $("#layerEventCodeFilter")?.value.trim() || "",
      sourceType: $("#layerEventSourceTypeFilter")?.value.trim() || "",
      limit: 100,
    });
  }

  function renderLayerEvents() {
    const body = $("#layerEventRows");
    if (!body) return;
    if (!state.layerEvents.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无图层事件记录</td></tr>';
      return;
    }
    body.innerHTML = state.layerEvents
      .map((event) => `
        <tr>
          <td><div class="cell-stack"><strong>${escapeHtml(displayLabel(LAYER_EVENT_ACTION_LABELS, event.action, "-"))}</strong><small>${escapeHtml(event.eventId || "-")}</small></div></td>
          <td><div class="cell-stack"><strong>${escapeHtml(event.recordCode || "-")}</strong><small>${escapeHtml(event.layerName || event.layerId || "-")}</small></div></td>
          <td><div class="cell-stack"><strong>${escapeHtml(displayLabel(SOURCE_TYPE_LABELS, event.sourceType, "-"))}</strong><small>${escapeHtml(displayLabel(RISK_STATUS_LABELS, event.publishRiskStatus, "-"))}</small></div></td>
          <td>${escapeHtml(event.actor || "-")}</td>
          <td>${escapeHtml(formatDateTime(event.at))}</td>
          <td><span class="status-pill">${escapeHtml(displayLabel(LAYER_STATUS_LABELS, event.status, "-"))}</span></td>
        </tr>
      `)
      .join("");
  }

  function mapLayerPublicationSummaryCard(label, value, note, tone = "") {
    return `
      <article class="receipt-summary-card ${escapeHtml(tone)}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value ?? 0)}</strong>
        <small>${escapeHtml(note || "")}</small>
      </article>
    `;
  }

  function renderMapLayerPublicationSummary(payload = state.layerDashboard || {}) {
    const target = $("#mapLayerPublicationSummary");
    if (!target) return;
    const summary = payload.publicationSummary || {};
    target.innerHTML = [
      mapLayerPublicationSummaryCard("发布闭环事项", summary.publicationQueueTotal || 0, "待处理、待复核和回执事项"),
      mapLayerPublicationSummaryCard("待发布到大屏", summary.awaitingPublishTotal || 0, "具备发布条件的图层", "tone-warning"),
      mapLayerPublicationSummaryCard("发布前复核", summary.reviewTotal || 0, "质量或风险需要复核", "tone-warning"),
      mapLayerPublicationSummaryCard("发布阻断", summary.blockedTotal || 0, "禁止直接发布的图层", "tone-danger"),
      mapLayerPublicationSummaryCard("回执待导出", summary.receiptReadyTotal || 0, "已发布图层可导出回执", "tone-ready"),
    ].join("");
  }

  function mapLayerPublicationQueueItem(lane, item) {
    const requiredPermission = lane.requiredPermission || "";
    const blockCount = linkedBlockCount(item);
    const href = item.adminHref || `admin-map-layers.html?layerCode=${encodeURIComponent(item.recordCode || item.id || "")}`;
    const meta = [
      displayLabel(RISK_STATUS_LABELS, item.publishRiskStatus, "-"),
      displayLabel(SOURCE_TYPE_LABELS, item.sourceType, "-"),
      `${blockCount} 个林班`,
      item.dashboardHref ? "已挂大屏" : "后台待处理",
    ];
    return `
      <article class="operation-queue-row" data-publication-layer-id="${escapeHtml(item.id || "")}">
        <small>${escapeHtml(item.recordCode || item.id || "-")}</small>
        <p>${escapeHtml(item.name || item.recordCode || "未命名图层")}</p>
        <div class="operation-queue-meta">
          ${meta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}
        </div>
        <button
          type="button"
          class="button-ghost"
          data-publication-action="open"
          data-layer-id="${escapeHtml(item.id || "")}"
          data-layer-code="${escapeHtml(item.recordCode || "")}"
          data-href="${escapeHtml(href)}"
          data-permission="${escapeHtml(requiredPermission)}"
        >打开处理</button>
      </article>
    `;
  }

  function renderMapLayerPublicationQueue(payload = state.layerDashboard || {}) {
    const target = $("#mapLayerPublicationQueueRows");
    if (!target) return;
    const lanes = Array.isArray(payload.publicationQueue) ? payload.publicationQueue : [];
    renderMapLayerPublicationSummary(payload);
    target.innerHTML = lanes.length
      ? lanes
          .map((lane) => {
            const items = Array.isArray(lane.items) ? lane.items : [];
            return `
              <article class="operation-queue-item tone-${escapeHtml(lane.tone || "warning")}" data-publication-queue-key="${escapeHtml(lane.key || "")}">
                <div class="operation-queue-head">
                  <span>${escapeHtml(lane.label || lane.key || "发布事项")}</span>
                  <strong>${escapeHtml(lane.count ?? items.length)}</strong>
                </div>
                <div class="operation-queue-list">
                  ${
                    items.length
                      ? items.map((item) => mapLayerPublicationQueueItem(lane, item)).join("")
                      : '<div class="operation-queue-row"><p>暂无后台数据。</p></div>'
                  }
                </div>
              </article>
            `;
          })
          .join("")
      : '<article class="operation-queue-item"><div class="operation-queue-row"><p>暂无地图图层发布闭环数据。</p></div></article>';
    applyActionPermissions();
  }

  function dashboardPublicationItem(layerId, layerCode) {
    const lanes = Array.isArray(state.layerDashboard?.publicationQueue) ? state.layerDashboard.publicationQueue : [];
    for (const lane of lanes) {
      const items = Array.isArray(lane.items) ? lane.items : [];
      const matched = items.find(
        (item) =>
          (layerId && String(item.id || "") === String(layerId)) ||
          (layerCode && String(item.recordCode || "") === String(layerCode)),
      );
      if (matched) return matched;
    }
    return null;
  }

  function handleMapLayerPublicationQueueAction(event) {
    const button = event.target.closest("[data-publication-action]");
    if (!button) return;
    event.preventDefault();
    if (button.disabled) return;
    const item =
      state.layers.find(
        (layer) =>
          String(layer.id || "") === String(button.dataset.layerId || "") ||
          String(layer.recordCode || "") === String(button.dataset.layerCode || ""),
      ) || dashboardPublicationItem(button.dataset.layerId || "", button.dataset.layerCode || "");
    if (item) {
      state.activeId = item.id || "";
      if (!state.layers.some((layer) => String(layer.id || "") === String(item.id || ""))) {
        state.layers = [item, ...state.layers];
      }
      renderDetail(item);
      return;
    }
    if (button.dataset.href) window.location.href = button.dataset.href;
  }

  async function loadMapLayerPublicationQueue() {
    try {
      const payload = await api("/api/map-layers/dashboard");
      state.layerDashboard = payload;
      renderMapLayerPublicationQueue(payload);
    } catch (error) {
      const target = $("#mapLayerPublicationQueueRows");
      if (target) {
        target.innerHTML = `<article class="operation-queue-item tone-danger"><div class="operation-queue-row"><p>${escapeHtml(error.message)}</p></div></article>`;
      }
    }
  }

  async function loadLayerEvents() {
    const body = $("#layerEventRows");
    try {
      const payload = await api(`/api/map-layers/events?${layerEventQuery()}`);
      state.layerEvents = Array.isArray(payload.items) ? payload.items : [];
      renderLayerEvents();
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

  async function exportLayerEvents() {
    return downloadFile(`/api/map-layers/events.csv?${layerEventQuery()}`, "map-layer-events.csv", {
      busy: "正在导出图层事件",
      done: "图层事件已导出",
      fail: "图层事件导出失败",
    });
  }

  async function exportLayerPublicationReceipt(layer = activeLayer()) {
    if (!layer?.id) return false;
    const code = String(layer.recordCode || layer.id || "layer").replace(/[\\/:*?"<>|]+/g, "-");
    return downloadFile(
      `/api/map-layers/${encodeURIComponent(layer.id)}/publication-receipt.json`,
      `map-layer-publication-receipt-${code}.json`,
      {
        busy: "正在导出图层发布回执",
        done: "图层发布回执已导出",
        fail: "图层发布回执导出失败",
      },
    );
  }

  async function saveLayer(event) {
    event.preventDefault();
    let body;
    try {
      body = JSON.stringify(payloadFromForm());
    } catch (error) {
      setStatus("offline", error.message);
      return;
    }
    const id = $("#layerId").value.trim();
    const path = id ? `/api/map-layers/${encodeURIComponent(id)}` : "/api/map-layers";
    const method = id ? "PATCH" : "POST";
    setStatus("busy", "正在保存图层...");
    try {
      const saved = await api(path, { method, body });
      state.activeId = saved.id;
      closeLayerEditor();
      await loadLayers();
      await loadLayerEvents();
      await loadMapLayerPublicationQueue();
      renderDetail(state.layers.find((layer) => String(layer.id) === String(saved.id)) || saved);
      setStatus("online", "图层已保存。");
    } catch (error) {
      setStatus("offline", `图层保存失败：${error.message}`);
    }
  }

  async function deleteLayer(layer = activeLayer()) {
    if (!layer) return;
    setStatus("busy", "正在删除图层...");
    try {
      await api(`/api/map-layers/${encodeURIComponent(layer.id)}`, { method: "DELETE" });
      state.activeId = "";
      closeLayerEditor();
      closeLayerDetail();
      await loadLayers();
      await loadLayerEvents();
      await loadMapLayerPublicationQueue();
      setStatus("online", "图层已软删除。");
    } catch (error) {
      setStatus("offline", `图层删除失败：${error.message}`);
    }
  }

  async function restoreLayer(layer = activeLayer()) {
    if (!layer) return;
    setStatus("busy", "正在恢复图层...");
    try {
      await api(`/api/map-layers/${encodeURIComponent(layer.id)}/restore`, { method: "POST" });
      state.activeId = layer.id;
      await loadLayers();
      await loadLayerEvents();
      await loadMapLayerPublicationQueue();
      renderDetail(activeLayer());
      setStatus("online", "图层已恢复。");
    } catch (error) {
      setStatus("offline", `图层恢复失败：${error.message}`);
    }
  }

  async function publishLayer(layer = activeLayer(), visible = true) {
    if (!layer) return;
    const nextStatus = visible ? "published" : "paused";
    setStatus("busy", visible ? "正在发布图层..." : "正在暂停图层...");
    try {
      const payload = await api(`/api/map-layers/${encodeURIComponent(layer.id)}/publish`, {
        method: "POST",
        body: JSON.stringify({
          visibleOnDashboard: Boolean(visible),
          status: nextStatus,
        }),
      });
      state.activeId = payload.layer?.id || layer.id;
      await loadLayers();
      await loadLayerEvents();
      await loadMapLayerPublicationQueue();
      renderDetail(state.layers.find((item) => String(item.id) === String(state.activeId)) || payload.layer || layer);
      setStatus("online", visible ? "图层已发布到大屏。" : "图层已暂停发布。");
    } catch (error) {
      setStatus("offline", `图层发布状态更新失败：${error.message}`);
    }
  }

  async function handleRowAction(event) {
    const layerButton = event.target.closest("[data-layer-action]");
    if (layerButton) {
      event.preventDefault();
      event.stopPropagation();
      if (layerButton.disabled) return true;
      const row = layerButton.closest("tr[data-id]");
      const layer = state.layers.find((item) => String(item.id) === String(row?.dataset.id)) || null;
      if (!layer) return true;
      state.activeId = layer.id;
      if (layerButton.dataset.layerAction === "restore") {
        restoreLayer(layer);
      } else if (layerButton.dataset.layerAction === "publish") {
        publishLayer(layer, true);
      } else if (layerButton.dataset.layerAction === "pause") {
        publishLayer(layer, false);
      } else if (layerButton.dataset.layerAction === "receipt") {
        exportLayerPublicationReceipt(layer);
      }
      return true;
    }
    const button = event.target.closest("[data-row-action]");
    if (!button) return false;
    event.stopPropagation();
    if (button.disabled) return true;
    const row = button.closest("tr[data-id]");
    const layer = state.layers.find((item) => String(item.id) === String(row?.dataset.id)) || null;
    if (!layer) return true;
    state.activeId = layer.id;
    const action = button.dataset.rowAction;
    if (action === "view") {
      await showLayerDetail(layer);
    } else if (action === "edit") {
      await openLayerEditor("edit", layer);
      renderRows();
    } else if (action === "delete") {
      deleteLayer(layer);
    }
    return true;
  }

  function initialize() {
    initShell();
    if (initialLayerCode && $("#layerKeyword")) $("#layerKeyword").value = initialLayerCode;
    pager = createLedgerPager({ anchor: $("#layerRows").closest(".table-wrap"), onPageChange: loadLayers });
    $("#reloadLayers").addEventListener("click", loadLayers);
    $("#newLayer").addEventListener("click", () => openLayerEditor("create"));
    $("#layerForm").addEventListener("submit", saveLayer);
    $("#cancelLayerEdit").addEventListener("click", closeLayerEditor);
    $("#closeLayerDetail").addEventListener("click", closeLayerDetail);
    $("#deleteLayer").addEventListener("click", () => deleteLayer(activeLayer()));
    $("#layerStatusFilter").addEventListener("change", reloadLayersFromFirstPage);
    $("#layerSourceTypeFilter").addEventListener("change", reloadLayersFromFirstPage);
    $("#layerRiskStatusFilter").addEventListener("change", reloadLayersFromFirstPage);
    $("#layerVisibleFilter").addEventListener("change", reloadLayersFromFirstPage);
    $("#refreshLayerPublicationQueue")?.addEventListener("click", loadMapLayerPublicationQueue);
    $("#refreshLayerEvents")?.addEventListener("click", loadLayerEvents);
    $("#exportLayerEvents")?.addEventListener("click", exportLayerEvents);
    $("#layerEventSourceTypeFilter")?.addEventListener("change", loadLayerEvents);
    $("#includeDeletedLayers").addEventListener("change", reloadLayersFromFirstPage);
    $("#layerKeyword").addEventListener("input", () => {
      window.clearTimeout(keywordTimer);
      keywordTimer = window.setTimeout(reloadLayersFromFirstPage, 180);
    });
    ["#layerEventActionFilter", "#layerEventLayerFilter", "#layerEventCodeFilter", "#layerEventKeyword"].forEach((selector) => {
      $(selector)?.addEventListener("input", () => window.setTimeout(loadLayerEvents, 180));
    });
    $("#layerRows").addEventListener("click", async (event) => {
      if (await handleRowAction(event)) return;
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      state.activeId = row.dataset.id;
      showLayerDetail(activeLayer());
    });
    $("#mapLayerPublicationQueueRows")?.addEventListener("click", handleMapLayerPublicationQueueAction);
    applyInitialLayerFilters();
    loadLayers();
    loadLayerEvents();
    loadMapLayerPublicationQueue();
  }

  initialize();
})();
