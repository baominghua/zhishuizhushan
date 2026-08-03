(() => {
  const {
    $,
    api,
    applyActionPermissions,
    createLedgerPager,
    escapeHtml,
    formatArea,
    formatDateTime,
    initShell,
    labelFor,
    parseJson,
    query,
    setStatus,
    splitValues,
    stringifyPretty,
  } = AdminCommon;
  const {
    bindAdministrativeDivision,
    bindDictionarySelect,
    bindReferencePicker,
  } = AdminSmartFields;

  const BLOCK_CREATE_PERMISSION = "forest.blocks.create";
  const BLOCK_UPDATE_PERMISSION = "forest.blocks.update";
  const BLOCK_DELETE_PERMISSION = "forest.blocks.delete";
  const BLOCK_RESTORE_PERMISSION = "forest.blocks.restore";
  const BLOCK_ROLLBACK_PERMISSION = "forest.blocks.rollback";
  const state = {
    blocks: [],
    blockVersions: [],
    activeId: "",
    editorMode: "",
    divisionControl: null,
    dictionaryControls: {},
    tagPicker: null,
    tagOptions: new Map(),
  };
  let pager;
  let keywordTimer;
  const initialBlockCode = new URLSearchParams(window.location.search).get("blockCode") || "";
  const ICONS = {
    view: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>',
    edit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4.5L19 9.5 14.5 5 4 15.5V20Z"></path><path d="m13.5 6 4.5 4.5"></path></svg>',
    delete: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M7 7l1 13h8l1-13"></path><path d="M9 7V4h6v3"></path></svg>',
    restore:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.4-6.4"></path><path d="M18 3v5h-5"></path><path d="M21 12a9 9 0 0 1-15.4 6.4"></path><path d="M6 21v-5h5"></path></svg>',
    rollback:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 14 4 9l5-5"></path><path d="M4 9h9a7 7 0 1 1-6.3 4"></path></svg>',
  };

  function activeBlock() {
    return state.blocks.find((block) => String(block.id) === String(state.activeId)) || null;
  }

  function locationOf(block) {
    return [block.countyName || block.countyCode, block.townName || block.townCode, block.villageName || block.villageCode]
      .filter(Boolean)
      .join(" / ");
  }

  function isDeletedBlock(block) {
    return Boolean(block?.deletedAt);
  }

  function dictionaryLabel(fieldId, value) {
    const normalized = String(value || "");
    if (!normalized) return "-";
    const element = state.dictionaryControls[fieldId]?.element;
    const selected = Array.from(element?.children || [])
      .find((option) => String(option.value) === normalized);
    return selected?.textContent?.replace(/^历史值：/, "") || normalized;
  }

  function resourceTagLabel(value) {
    return state.tagOptions.get(String(value || "")) || String(value || "");
  }

  function blockActionButtons(block) {
    if (isDeletedBlock(block)) {
      return `
        <div class="row-actions" aria-label="林班操作">
          <button type="button" class="icon-button" data-row-action="view" aria-label="查看" title="查看">${ICONS.view}</button>
          <button type="button" class="icon-button" data-block-action="restore" data-permission="${BLOCK_RESTORE_PERMISSION}" aria-label="恢复" title="恢复">${ICONS.restore}</button>
        </div>
      `;
    }
    return `
      <div class="row-actions" aria-label="林班操作">
        <button type="button" class="icon-button" data-row-action="view" aria-label="查看" title="查看">${ICONS.view}</button>
        <button type="button" class="icon-button" data-row-action="edit" data-permission="${BLOCK_UPDATE_PERMISSION}" aria-label="编辑" title="编辑">${ICONS.edit}</button>
        <button type="button" class="icon-button danger" data-row-action="delete" data-permission="${BLOCK_DELETE_PERMISSION}" aria-label="删除" title="删除">${ICONS.delete}</button>
      </div>
    `;
  }

  function renderRows() {
    const body = $("#blockRows");
    if (!state.blocks.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无林班数据</td></tr>';
      return;
    }
    body.innerHTML = state.blocks
      .map((block) => {
        const active = String(block.id) === String(state.activeId) ? "active" : "";
        const geometryLabel = block.geometry ? "有边界" : "待补图";
        return `
          <tr data-id="${escapeHtml(block.id)}" class="${active}">
            <td><div class="cell-stack"><strong>${escapeHtml(block.blockCode || "-")}</strong><small>${escapeHtml(block.name || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(locationOf(block) || "-")}</strong><small>${escapeHtml(formatArea(block.areaMu))}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(dictionaryLabel("operationType", block.operationType))}</strong><small>${escapeHtml(block.forestType ? dictionaryLabel("forestType", block.forestType) : dictionaryLabel("baseType", block.baseType))}</small></div></td>
            <td><span class="status-pill ${block.geometry ? "complete" : "partial"}">${escapeHtml(geometryLabel)}</span></td>
            <td>${escapeHtml(formatDateTime(block.updatedAt))}</td>
            <td>${blockActionButtons(block)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  function renderMetrics(total) {
    const area = state.blocks.reduce((sum, block) => {
      const value = Number(block.areaMu);
      return Number.isFinite(value) ? sum + value : sum;
    }, 0);
    const withGeometry = state.blocks.filter((block) => block.geometry).length;
    $("#metricTotal").textContent = String(total ?? state.blocks.length);
    $("#metricArea").textContent = `${area.toFixed(area % 1 === 0 ? 0 : 1)} 亩`;
    $("#metricGeometry").textContent = String(withGeometry);
    $("#metricNoGeometry").textContent = String(state.blocks.length - withGeometry);
  }

  function renderDetail(block = null) {
    const panel = $("#blockDetailPanel");
    const empty = $("#blockDetailEmpty");
    const grid = $("#blockDetailGrid");
    if (!block) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      $("#detailTitle").textContent = "选择林班查看详情";
      empty.classList.remove("hidden");
      grid.classList.add("hidden");
      grid.innerHTML = "";
      renderBlockVersions(null);
      renderRows();
      return;
    }

    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    $("#detailTitle").textContent = block.name || block.blockCode || "林班详情";
    empty.classList.add("hidden");
    grid.classList.remove("hidden");
    const rows = [
      ["林班编号", block.blockCode],
      ["林班名称", block.name],
      ["区划位置", locationOf(block) || "-"],
      ["面积", formatArea(block.areaMu)],
      ["竹种/林种", dictionaryLabel("forestType", block.forestType)],
      ["基地类型", dictionaryLabel("baseType", block.baseType)],
      ["经营类型", dictionaryLabel("operationType", block.operationType)],
      ["质量等级", dictionaryLabel("qualityGrade", block.qualityGrade)],
      ["健康状态", dictionaryLabel("healthStatus", block.healthStatus)],
      ["风险等级", dictionaryLabel("riskLevel", block.riskLevel)],
      ["图形状态", block.geometry ? "有空间边界" : "待补空间边界"],
      ["更新时间", formatDateTime(block.updatedAt)],
      ["标签", Array.isArray(block.tags) && block.tags.length ? block.tags.map(resourceTagLabel).join(", ") : "-"],
    ];
    grid.innerHTML = rows
      .map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "-")}</dd></div>`)
      .join("");
    loadBlockVersions(block);
    renderRows();
  }

  function versionChangeLabel(changeType) {
    const labels = {
      create: "创建",
      update: "编辑",
      delete: "删除",
      restore: "恢复",
      rollback: "回滚",
    };
    return labels[changeType] || changeType || "-";
  }

  function renderBlockVersions(block = activeBlock()) {
    const target = $("#blockVersionList");
    if (!target) return;
    if (!block) {
      state.blockVersions = [];
      target.innerHTML = '<p class="trace-empty">选择林班后查看版本历史。</p>';
      return;
    }
    if (!state.blockVersions.length) {
      target.innerHTML = '<p class="trace-empty">暂无版本记录。</p>';
      return;
    }
    target.innerHTML = state.blockVersions
      .map((version) => {
        const snapshot = version.snapshot || {};
        return `
          <article class="trace-item">
            <strong>${escapeHtml(versionChangeLabel(version.changeType))} · ${escapeHtml(snapshot.blockCode || block.blockCode || "-")}</strong>
            <span>${escapeHtml(formatDateTime(version.createdAt))} · ${escapeHtml(version.createdBy || "-")} · 风险 ${escapeHtml(snapshot.riskLevel || "-")} · 面积 ${escapeHtml(formatArea(snapshot.areaMu))}</span>
            <button type="button" class="trace-link trace-button" data-version-action="rollback" data-version-id="${escapeHtml(version.id)}" data-permission="${BLOCK_ROLLBACK_PERMISSION}" title="回滚到此版本" aria-label="回滚到此版本">${ICONS.rollback} 回滚到此版本</button>
          </article>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  async function loadBlockVersions(block = activeBlock()) {
    const target = $("#blockVersionList");
    if (!target) return;
    if (!block?.id) {
      renderBlockVersions(null);
      return;
    }
    target.innerHTML = '<p class="trace-empty">正在加载版本历史...</p>';
    try {
      const payload = await api(`/api/forest-blocks/${encodeURIComponent(block.id)}/versions`);
      if (String(state.activeId) !== String(block.id)) return;
      state.blockVersions = Array.isArray(payload.items) ? payload.items : [];
      renderBlockVersions(block);
    } catch (error) {
      if (String(state.activeId) !== String(block.id)) return;
      state.blockVersions = [];
      target.innerHTML = `<p class="trace-empty">版本历史加载失败：${escapeHtml(error.message)}</p>`;
    }
  }

  async function rollbackBlockVersion(versionId, block = activeBlock()) {
    if (!block?.id || !versionId) return;
    setStatus("busy", "正在回滚林班版本...");
    try {
      const payload = await api(`/api/forest-blocks/${encodeURIComponent(block.id)}/rollback`, {
        method: "POST",
        body: JSON.stringify({ versionId }),
      });
      state.activeId = payload.block?.id || block.id;
      await loadBlocks();
      renderDetail(state.blocks.find((item) => String(item.id) === String(state.activeId)) || payload.block);
      setStatus("online", "林班已回滚到所选版本。");
    } catch (error) {
      setStatus("offline", `林班版本回滚失败：${error.message}`);
    }
  }

  function setupSmartFields() {
    state.divisionControl = bindAdministrativeDivision({
      api,
      county: { code: $("#countyCode"), name: $("#countyName") },
      town: { code: $("#townCode"), name: $("#townName") },
      village: { code: $("#villageCode"), name: $("#villageName") },
    });
    [
      ["baseType", "forest-base-types"],
      ["operationType", "forest-operation-types"],
      ["qualityGrade", "quality-grades"],
      ["healthStatus", "health-statuses"],
      ["riskLevel", "risk-levels"],
      ["forestType", "forest-types"],
    ].forEach(([fieldId, typeCode]) => {
      state.dictionaryControls[fieldId] = bindDictionarySelect({
        element: $(`#${fieldId}`),
        typeCode,
        api,
        blankLabel: "未填写",
      });
    });
    state.tagPicker = bindReferencePicker({
      input: $("#tags"),
      endpoint: "/api/dictionary-options/forest-resource-tags",
      valueKey: "value",
      labelKey: "label",
      api,
      placeholder: "搜索并选择资源标签",
    });
    const tagOptionsReady = api("/api/dictionary-options/forest-resource-tags?limit=500&offset=0")
      .then((payload) => {
        state.tagOptions = new Map(
          (payload.items || []).map((item) => [String(item.value || ""), String(item.label || item.value || "")]),
        );
      });
    return Promise.all([
      state.divisionControl.ready,
      ...Object.values(state.dictionaryControls).map((control) => control.ready),
      tagOptionsReady,
    ]);
  }

  async function fillForm(block = {}) {
    $("#formTitle").textContent = block.id ? "编辑林班" : "新增林班";
    $("#blockId").value = block.id || "";
    $("#blockCode").value = block.blockCode || "";
    $("#blockCode").readOnly = Boolean(block.id);
    $("#blockName").value = block.name || "";
    $("#areaMu").value = block.areaMu ?? "";
    $("#properties").value = stringifyPretty(block.properties, {});
    $("#geometry").value = stringifyPretty(block.geometry, null);
    await Promise.all(Object.values(state.dictionaryControls).map((control) => control.ready));
    Object.entries({
      baseType: block.baseType,
      operationType: block.operationType,
      qualityGrade: block.qualityGrade,
      healthStatus: block.healthStatus,
      riskLevel: block.riskLevel,
      forestType: block.forestType,
    }).forEach(([fieldId, value]) => state.dictionaryControls[fieldId].setValue(value || ""));
    state.tagPicker.setValues(
      (Array.isArray(block.tags) ? block.tags : []).map((value) => ({
        value,
        label: resourceTagLabel(value),
        historic: !state.tagOptions.has(String(value)),
      })),
    );
    await state.divisionControl.setValue({
      countyCode: block.countyCode,
      countyName: block.countyName,
      townCode: block.townCode,
      townName: block.townName,
      villageCode: block.villageCode,
      villageName: block.villageName,
    });
  }

  async function openBlockEditor(mode, block = {}) {
    state.editorMode = mode;
    closeBlockDetail();
    const formReady = fillForm(mode === "edit" ? block : {});
    $("#saveBlock").dataset.permission = mode === "edit" ? BLOCK_UPDATE_PERMISSION : BLOCK_CREATE_PERMISSION;
    $("#blockEditorOverlay").classList.remove("hidden");
    $("#blockEditorOverlay").setAttribute("aria-hidden", "false");
    applyActionPermissions();
    $("#blockCode").focus();
    try {
      await formReady;
    } catch (error) {
      setStatus("warning", `部分智能选项加载失败：${error.message}`);
    }
  }

  function closeBlockEditor() {
    state.editorMode = "";
    $("#blockEditorOverlay").classList.add("hidden");
    $("#blockEditorOverlay").setAttribute("aria-hidden", "true");
  }

  function closeBlockDetail() {
    $("#blockDetailPanel").classList.add("hidden");
    $("#blockDetailPanel").setAttribute("aria-hidden", "true");
  }

  function payloadFromForm() {
    return {
      blockCode: $("#blockCode").value.trim(),
      name: $("#blockName").value.trim(),
      countyCode: $("#countyCode").value.trim() || null,
      countyName: $("#countyName").value.trim() || null,
      townCode: $("#townCode").value.trim() || null,
      townName: $("#townName").value.trim() || null,
      villageCode: $("#villageCode").value.trim() || null,
      villageName: $("#villageName").value.trim() || null,
      areaMu: $("#areaMu").value ? Number($("#areaMu").value) : null,
      forestType: $("#forestType").value.trim() || null,
      baseType: $("#baseType").value || null,
      operationType: $("#operationType").value || null,
      qualityGrade: $("#qualityGrade").value.trim() || null,
      healthStatus: $("#healthStatus").value.trim() || null,
      riskLevel: $("#riskLevel").value || null,
      tags: splitValues($("#tags").value),
      properties: parseJson("附加属性 JSON", $("#properties").value, {}),
      geometry: parseJson("GeoJSON 几何", $("#geometry").value, null),
    };
  }

  function currentQuery() {
    return query({
      q: $("#keyword").value.trim(),
      baseType: $("#baseTypeFilter").value,
      operationType: $("#operationTypeFilter").value,
      riskLevel: $("#riskLevelFilter").value,
      includeDeleted: $("#includeDeletedBlocks")?.checked ? "true" : "",
      limit: pager.limit,
      offset: pager.offset,
    });
  }

  function reloadBlocksFromFirstPage() {
    pager.reset();
    return loadBlocks();
  }

  async function loadBlocks() {
    setStatus("busy", "正在加载林班空间台账...");
    pager.setBusy(true);
    try {
      const payload = await api(`/api/forest-blocks?${currentQuery()}`);
      if (pager.setTotal(payload.total ?? 0)) return loadBlocks();
      state.blocks = Array.isArray(payload.items) ? payload.items : [];
      if (state.activeId && !activeBlock()) state.activeId = "";
      renderRows();
      renderDetail(activeBlock());
      renderMetrics(payload.total);
      setStatus("online", `已加载 ${payload.total ?? state.blocks.length} 条林班。`);
    } catch (error) {
      state.blocks = [];
      $("#blockRows").innerHTML = `<tr class="placeholder-row"><td colspan="6">林班加载失败：${escapeHtml(error.message)}</td></tr>`;
      renderMetrics(0);
      setStatus("offline", `林班加载失败：${error.message}`);
    } finally {
      pager.setBusy(false);
    }
  }

  async function saveBlock(event) {
    event.preventDefault();
    let body;
    try {
      body = JSON.stringify(payloadFromForm());
    } catch (error) {
      setStatus("offline", error.message);
      return;
    }
    const id = $("#blockId").value.trim();
    const path = id ? `/api/forest-blocks/${encodeURIComponent(id)}` : "/api/forest-blocks";
    const method = id ? "PATCH" : "POST";
    setStatus("busy", "正在保存林班...");
    try {
      const saved = await api(path, { method, body });
      state.activeId = saved.id;
      closeBlockEditor();
      await loadBlocks();
      renderDetail(state.blocks.find((block) => String(block.id) === String(saved.id)) || saved);
      setStatus("online", `已保存林班 ${saved.blockCode || ""}`.trim());
    } catch (error) {
      setStatus("offline", `林班保存失败：${error.message}`);
    }
  }

  async function deleteBlock(block = activeBlock()) {
    if (!block) {
      setStatus("warning", "请先从台账选择一条林班记录。");
      return;
    }
    setStatus("busy", "正在删除林班...");
    try {
      await api(`/api/forest-blocks/${encodeURIComponent(block.id)}`, { method: "DELETE" });
      state.activeId = "";
      closeBlockEditor();
      closeBlockDetail();
      await loadBlocks();
      renderDetail();
      setStatus("online", "林班已软删除。");
    } catch (error) {
      setStatus("offline", `林班删除失败：${error.message}`);
    }
  }

  async function restoreBlock(block = activeBlock()) {
    if (!block) return;
    setStatus("busy", "正在恢复林班...");
    try {
      await api(`/api/forest-blocks/${encodeURIComponent(block.id)}/restore`, { method: "POST" });
      state.activeId = block.id;
      await loadBlocks();
      renderDetail(activeBlock());
      setStatus("online", "林班已恢复。");
    } catch (error) {
      setStatus("offline", `林班恢复失败：${error.message}`);
    }
  }

  function handleRowAction(event) {
    const blockButton = event.target.closest("[data-block-action]");
    if (blockButton) {
      event.stopPropagation();
      if (blockButton.disabled) return true;
      const row = blockButton.closest("tr[data-id]");
      const block = state.blocks.find((item) => String(item.id) === String(row?.dataset.id)) || null;
      if (!block) return true;
      state.activeId = block.id;
      if (blockButton.dataset.blockAction === "restore") {
        restoreBlock(block);
      }
      return true;
    }
    const button = event.target.closest("[data-row-action]");
    if (!button) return false;
    event.stopPropagation();
    if (button.disabled) return true;
    const row = button.closest("tr[data-id]");
    const block = state.blocks.find((item) => String(item.id) === String(row?.dataset.id)) || null;
    if (!block) return true;
    state.activeId = block.id;
    const action = button.dataset.rowAction;
    if (action === "view") {
      renderDetail(block);
    } else if (action === "edit") {
      openBlockEditor("edit", block);
      renderRows();
    } else if (action === "delete") {
      deleteBlock(block);
    }
    return true;
  }

  function attachEvents() {
    $("#reloadBlocks").addEventListener("click", loadBlocks);
    $("#newBlock").addEventListener("click", () => openBlockEditor("create"));
    $("#blockForm").addEventListener("submit", saveBlock);
    $("#cancelBlockEdit").addEventListener("click", closeBlockEditor);
    $("#closeBlockDetail").addEventListener("click", closeBlockDetail);
    ["#baseTypeFilter", "#operationTypeFilter", "#riskLevelFilter"].forEach((selector) => {
      $(selector).addEventListener("change", reloadBlocksFromFirstPage);
    });
    $("#includeDeletedBlocks").addEventListener("change", reloadBlocksFromFirstPage);
    $("#keyword").addEventListener("input", () => {
      window.clearTimeout(keywordTimer);
      keywordTimer = window.setTimeout(reloadBlocksFromFirstPage, 180);
    });
    $("#blockRows").addEventListener("click", (event) => {
      if (handleRowAction(event)) return;
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      state.activeId = row.dataset.id;
      renderDetail(activeBlock());
    });
    $("#blockVersionList")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-version-action]");
      if (!button || button.disabled) return;
      if (button.dataset.versionAction === "rollback") {
        rollbackBlockVersion(button.dataset.versionId);
      }
    });
  }

  async function initialize() {
    initShell();
    if (initialBlockCode && $("#keyword")) $("#keyword").value = initialBlockCode;
    pager = createLedgerPager({ anchor: $("#blockRows").closest(".table-wrap"), onPageChange: loadBlocks });
    const smartFieldsReady = setupSmartFields();
    attachEvents();
    renderDetail();
    try {
      await smartFieldsReady;
    } catch (error) {
      setStatus("warning", `部分智能选项加载失败：${error.message}`);
    }
    await loadBlocks();
  }

  initialize();
})();
