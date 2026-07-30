(() => {
  const {
    $,
    api,
    applyActionPermissions,
    authProfile,
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
    bindDictionarySelect,
    bindReferencePicker,
  } = AdminSmartFields;

  const RIGHT_CREATE_PERMISSION = "forest.rights.create";
  const RIGHT_UPDATE_PERMISSION = "forest.rights.update";
  const RIGHT_DELETE_PERMISSION = "forest.rights.delete";
  const RIGHT_RESTORE_PERMISSION = "forest.rights.restore";
  const RIGHT_ROLLBACK_PERMISSION = "forest.rights.rollback";
  const state = {
    rights: [],
    rightVersions: [],
    activeId: "",
    dictionaryControls: {},
    linkedBlockPicker: null,
    holderPicker: null,
  };
  let pager;
  let keywordTimer;
  const initialArchiveCode = new URLSearchParams(window.location.search).get("archiveCode") || "";
  const VIEW_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>';
  const RESTORE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.4-6.4"></path><path d="M18 3v5h-5"></path><path d="M21 12a9 9 0 0 1-15.4 6.4"></path><path d="M6 21v-5h5"></path></svg>';
  const ROLLBACK_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 14 4 9l5-5"></path><path d="M4 9h9a7 7 0 1 1-6.3 4"></path></svg>';

  function activeRight() {
    return state.rights.find((right) => String(right.id) === String(state.activeId)) || null;
  }

  function isDeletedRight(right) {
    return Boolean(right?.deletedAt);
  }

  function linkedBlockCount(right) {
    const propertyCount = Number(right?.properties?.linkedBlockCount);
    return Number.isFinite(propertyCount)
      ? propertyCount
      : (Array.isArray(right?.linkedBlockCodes) ? right.linkedBlockCodes.length : 0);
  }

  function linkedBlockSummary(right) {
    const values = Array.isArray(right?.linkedBlockCodes) ? right.linkedBlockCodes : [];
    const total = linkedBlockCount(right);
    if (!total) return "未挂接";
    const sample = values.slice(0, 8).join(", ");
    return `${total} 个林班${sample ? `：${sample}${total > values.length ? " ..." : ""}` : ""}`;
  }

  async function hydrateRightTargets(right) {
    if (!right?.id) return right;
    const payload = await api(`/api/forest-rights/${encodeURIComponent(right.id)}/targets?limit=100&offset=0`);
    const linkedBlockCodes = (payload.items || []).map((item) => item.blockCode).filter(Boolean);
    const hydrated = {
      ...right,
      linkedBlockCodes,
      properties: {
        ...(right.properties || {}),
        linkedBlockCount: Number(payload.total || 0),
        linkedTargetsTruncated: Number(payload.total || 0) > linkedBlockCodes.length,
      },
    };
    const index = state.rights.findIndex((item) => String(item.id) === String(right.id));
    if (index >= 0) state.rights[index] = hydrated;
    return hydrated;
  }

  function rightActionButtons(right) {
    if (isDeletedRight(right)) {
      return `
        <div class="row-actions" aria-label="林权档案操作">
          <button type="button" class="icon-button" data-row-action="view" aria-label="查看档案" title="查看档案">${VIEW_ICON}</button>
          <button type="button" class="icon-button" data-right-action="restore" data-permission="${RIGHT_RESTORE_PERMISSION}" aria-label="恢复档案" title="恢复档案">${RESTORE_ICON}</button>
        </div>
      `;
    }
    return `
      <div class="row-actions" aria-label="林权档案操作">
        <button type="button" class="icon-button" data-row-action="view" aria-label="查看档案" title="查看档案">${VIEW_ICON}</button>
        <button type="button" class="icon-button" data-row-action="edit" data-permission="${RIGHT_UPDATE_PERMISSION}" aria-label="编辑档案" title="编辑档案">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4.5L19 9.5 14.5 5 4 15.5V20Z"></path><path d="m13.5 6 4.5 4.5"></path></svg>
        </button>
        <button type="button" class="icon-button danger" data-row-action="delete" data-permission="${RIGHT_DELETE_PERMISSION}" aria-label="删除档案" title="删除档案">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M7 7l1 13h8l1-13"></path><path d="M9 7V4h6v3"></path></svg>
        </button>
      </div>
    `;
  }

  function renderRows() {
    const body = $("#rightRows");
    if (!state.rights.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无林权档案</td></tr>';
      return;
    }
    body.innerHTML = state.rights
      .map((right) => {
        const linked = right.linkedBlockCodes || [];
        const linkedCount = linkedBlockCount(right);
        const active = String(right.id) === String(state.activeId) ? "active" : "";
        return `
          <tr data-id="${escapeHtml(right.id)}" class="${active}">
            <td><div class="cell-stack"><strong>${escapeHtml(right.archiveCode || "-")}</strong><small>${escapeHtml(right.contractNo || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(right.holder || "-")}</strong><small>${escapeHtml(right.rightType || right.ownershipType || "-")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(right.certificateNo || "-")}</strong><small>${escapeHtml(right.rightEnd || "未填期限")}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(linkedCount ? `${linkedCount} 个林班` : "未挂接")}</strong><small>${escapeHtml(linked.slice(0, 2).join(", ") || (linkedCount ? "按需加载关联明细" : "-"))}</small></div></td>
            <td><span class="status-pill ${escapeHtml(right.archiveStatus || "partial")}">${escapeHtml(labelFor("archiveStatus", right.archiveStatus || "partial"))}</span></td>
            <td>${rightActionButtons(right)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  function detailItem(label, value) {
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "未填")}</dd></div>`;
  }

  function renderDetail(right = activeRight()) {
    const panel = $("#rightDetailPanel");
    if (!right) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      renderRightVersions(null);
      return;
    }
    $("#rightDetailTitle").textContent = `${right.archiveCode || right.certificateNo || "林权档案"}详情`;
    $("#rightDetailEmpty").hidden = true;
    $("#rightDetailGrid").innerHTML = [
      detailItem("档案编号", right.archiveCode || "-"),
      detailItem("林权证号", right.certificateNo || "-"),
      detailItem("权利人", right.holder || "-"),
      detailItem("证照类型", right.certificateType || "-"),
      detailItem("权利类型", right.rightType || "-"),
      detailItem("权属性质", right.ownershipType || "-"),
      detailItem("权利期限", `${right.rightStart || "未填"} 至 ${right.rightEnd || "未填"}`),
      detailItem("合同编号", right.contractNo || "-"),
      detailItem("档案状态", labelFor("archiveStatus", right.archiveStatus || "partial")),
      detailItem("登记人", right.registrar || "-"),
      detailItem("归档面积", formatArea(right.areaMu)),
      detailItem("关联林班", linkedBlockSummary(right)),
      detailItem("缺失材料 / 备注", right.missingItems || "-"),
      detailItem("更新时间", formatDateTime(right.updatedAt)),
      detailItem("扩展字段", stringifyPretty(right.properties, {})),
    ].join("");
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    loadRightVersions(right);
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

  function renderRightVersions(right = activeRight()) {
    const target = $("#rightVersionList");
    if (!target) return;
    if (!right) {
      state.rightVersions = [];
      target.innerHTML = '<p class="trace-empty">选择林权档案后查看版本历史。</p>';
      return;
    }
    if (!state.rightVersions.length) {
      target.innerHTML = '<p class="trace-empty">暂无版本记录。</p>';
      return;
    }
    target.innerHTML = state.rightVersions
      .map((version) => {
        const snapshot = version.snapshot || {};
        return `
          <article class="trace-item">
            <strong>${escapeHtml(versionChangeLabel(version.changeType))} · ${escapeHtml(snapshot.archiveCode || right.archiveCode || "-")}</strong>
            <span>${escapeHtml(formatDateTime(version.createdAt))} · ${escapeHtml(version.createdBy || "-")} · 权利人 ${escapeHtml(snapshot.holder || "-")} · 面积 ${escapeHtml(formatArea(snapshot.areaMu))}</span>
            <button type="button" class="trace-link trace-button" data-version-action="rollback" data-version-id="${escapeHtml(version.id)}" data-permission="${RIGHT_ROLLBACK_PERMISSION}" title="回滚到此版本" aria-label="回滚到此版本">${ROLLBACK_ICON} 回滚到此版本</button>
          </article>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  async function loadRightVersions(right = activeRight()) {
    const target = $("#rightVersionList");
    if (!target) return;
    if (!right?.id) {
      renderRightVersions(null);
      return;
    }
    target.innerHTML = '<p class="trace-empty">正在加载版本历史...</p>';
    try {
      const payload = await api(`/api/forest-rights/${encodeURIComponent(right.id)}/versions`);
      if (String(state.activeId) !== String(right.id)) return;
      state.rightVersions = Array.isArray(payload.items) ? payload.items : [];
      renderRightVersions(right);
    } catch (error) {
      if (String(state.activeId) !== String(right.id)) return;
      state.rightVersions = [];
      target.innerHTML = `<p class="trace-empty">版本历史加载失败：${escapeHtml(error.message)}</p>`;
    }
  }

  async function rollbackRightVersion(versionId, right = activeRight()) {
    if (!right?.id || !versionId) return;
    setStatus("busy", "正在回滚林权档案版本...");
    try {
      const payload = await api(`/api/forest-rights/${encodeURIComponent(right.id)}/rollback`, {
        method: "POST",
        body: JSON.stringify({ versionId }),
      });
      state.activeId = payload.right?.id || right.id;
      await loadRights();
      const detailRight = state.rights.find((item) => String(item.id) === String(state.activeId)) || payload.right;
      renderDetail(await hydrateRightTargets(detailRight));
      setStatus("online", "林权档案已回滚到所选版本。");
    } catch (error) {
      setStatus("offline", `林权档案回滚失败：${error.message}`);
    }
  }

  function setupSmartFields() {
    [
      ["rightArchiveCertificateType", "certificate-types"],
      ["rightArchiveRightType", "right-types"],
      ["rightArchiveOwnershipType", "ownership-types"],
      ["rightArchiveStatus", "archive-statuses"],
    ].forEach(([fieldId, typeCode]) => {
      state.dictionaryControls[fieldId] = bindDictionarySelect({
        element: $(`#${fieldId}`),
        typeCode,
        api,
        blankLabel: fieldId === "rightArchiveStatus" ? "待补充" : "未填写",
      });
    });
    state.linkedBlockPicker = bindReferencePicker({
      input: $("#rightArchiveLinkedBlockCodes"),
      endpoint: "/api/forest-blocks",
      valueKey: "blockCode",
      labelKey: "name",
      api,
      placeholder: "输入林班编号、名称或村镇搜索",
    });
    state.holderPicker = bindReferencePicker({
      input: $("#rightArchiveHolder"),
      endpoint: "/api/business-reference-options/subjects",
      valueKey: "name",
      labelKey: "label",
      api,
      multiple: false,
      placeholder: "搜索已有竹农、合作社或竹企",
    });
    return Promise.all(Object.values(state.dictionaryControls).map((control) => control.ready));
  }

  async function fillForm(right = {}) {
    state.activeId = right.id || "";
    $("#rightFormTitle").textContent = right.id ? "编辑林权档案" : "新建林权档案";
    $("#rightArchiveId").value = right.id || "";
    $("#rightArchiveCode").value = right.archiveCode || "";
    $("#rightArchiveCertificateNo").value = right.certificateNo || "";
    state.holderPicker.setValues(
      right.holder
        ? [{ name: right.holder, label: right.holder, historic: true }]
        : [],
    );
    $("#rightArchiveRightStart").value = right.rightStart || "";
    $("#rightArchiveRightEnd").value = right.rightEnd || "";
    $("#rightArchiveContractNo").value = right.contractNo || "";
    $("#rightArchiveRegistrar").value = right.registrar || authProfile()?.user || $("#authUser")?.value.trim() || "";
    $("#rightArchiveAreaMu").value = right.areaMu ?? "";
    const relationsPartial = Boolean(right.properties?.linkedTargetsTruncated);
    state.linkedBlockPicker.setValues(Array.isArray(right.linkedBlockCodes) ? right.linkedBlockCodes : []);
    state.linkedBlockPicker.setDisabled(relationsPartial);
    $("#rightArchiveLinkedBlockCodes").dataset.preserveRelations = String(relationsPartial);
    $("#rightArchiveLinkedBlockCodes").title = relationsPartial
      ? "关联林班超过 100 条，请通过图档关联管理分批维护"
      : "";
    $("#rightArchiveMissingItems").value = right.missingItems || "";
    $("#rightArchiveProperties").value = stringifyPretty(right.properties, {});
    await Promise.all(Object.values(state.dictionaryControls).map((control) => control.ready));
    Object.entries({
      rightArchiveCertificateType: right.certificateType,
      rightArchiveRightType: right.rightType,
      rightArchiveOwnershipType: right.ownershipType,
      rightArchiveStatus: right.archiveStatus || "partial",
    }).forEach(([fieldId, value]) => state.dictionaryControls[fieldId].setValue(value || ""));
    renderRows();
  }

  async function openRightEditor(mode, right = {}) {
    closeRightDetail();
    await fillForm(mode === "edit" ? right : {});
    $("#saveRightArchive").dataset.permission = mode === "edit" ? RIGHT_UPDATE_PERMISSION : RIGHT_CREATE_PERMISSION;
    $("#rightForm").classList.remove("hidden");
    $("#rightForm").setAttribute("aria-hidden", "false");
    applyActionPermissions();
    $("#rightArchiveCode").focus();
  }

  function closeRightEditor() {
    $("#rightForm").classList.add("hidden");
    $("#rightForm").setAttribute("aria-hidden", "true");
  }

  function closeRightDetail() {
    $("#rightDetailPanel").classList.add("hidden");
    $("#rightDetailPanel").setAttribute("aria-hidden", "true");
    renderRightVersions(null);
  }

  function payloadFromForm() {
    const linkedBlockCodes = splitValues($("#rightArchiveLinkedBlockCodes").value);
    const certificateNo = $("#rightArchiveCertificateNo").value.trim();
    const contractNo = $("#rightArchiveContractNo").value.trim();
    const payload = {
      archiveCode: $("#rightArchiveCode").value.trim() || certificateNo || contractNo || (linkedBlockCodes[0] ? `RIGHT-${linkedBlockCodes[0]}` : ""),
      certificateNo: certificateNo || null,
      holder: $("#rightArchiveHolder").value.trim(),
      certificateType: $("#rightArchiveCertificateType").value.trim() || null,
      rightType: $("#rightArchiveRightType").value.trim() || null,
      ownershipType: $("#rightArchiveOwnershipType").value.trim() || null,
      rightStart: $("#rightArchiveRightStart").value || null,
      rightEnd: $("#rightArchiveRightEnd").value || null,
      contractNo: contractNo || null,
      archiveStatus: $("#rightArchiveStatus").value || "partial",
      registrar: $("#rightArchiveRegistrar").value.trim() || null,
      areaMu: $("#rightArchiveAreaMu").value ? Number($("#rightArchiveAreaMu").value) : null,
      linkedBlockCodes,
      missingItems: $("#rightArchiveMissingItems").value.trim() || null,
      properties: parseJson("档案扩展 JSON", $("#rightArchiveProperties").value, {}),
    };
    if ($("#rightArchiveLinkedBlockCodes").dataset.preserveRelations === "true") {
      delete payload.linkedBlockCodes;
    }
    return payload;
  }

  function currentQuery() {
    return query({
      q: $("#rightKeyword").value.trim(),
      archiveStatus: $("#rightArchiveStatusFilter").value,
      linkedBlockCode: $("#rightLinkedBlockFilter").value.trim(),
      includeDeleted: $("#includeDeletedRights")?.checked ? "true" : "",
      limit: pager.limit,
      offset: pager.offset,
    });
  }

  function reloadRightsFromFirstPage() {
    pager.reset();
    return loadRights();
  }

  async function loadRights() {
    setStatus("busy", "正在加载林权档案...");
    pager.setBusy(true);
    try {
      const payload = await api(`/api/forest-rights?${currentQuery()}`);
      if (pager.setTotal(payload.total ?? 0)) return loadRights();
      state.rights = Array.isArray(payload.items) ? payload.items : [];
      if (state.activeId && !activeRight()) state.activeId = "";
      renderRows();
      renderDetail(activeRight());
      setStatus("online", `已加载 ${payload.total ?? state.rights.length} 份林权档案。`);
    } catch (error) {
      setStatus("offline", `林权档案加载失败：${error.message}`);
    } finally {
      pager.setBusy(false);
    }
  }

  async function saveRight(event) {
    event.preventDefault();
    let body;
    try {
      body = JSON.stringify(payloadFromForm());
    } catch (error) {
      setStatus("offline", error.message);
      return;
    }
    const id = $("#rightArchiveId").value.trim();
    const path = id ? `/api/forest-rights/${encodeURIComponent(id)}` : "/api/forest-rights";
    const method = id ? "PATCH" : "POST";
    setStatus("busy", "正在保存林权档案...");
    try {
      const saved = await api(path, { method, body });
      state.activeId = saved.id;
      closeRightEditor();
      await loadRights();
      const detailRight = state.rights.find((right) => String(right.id) === String(saved.id)) || saved;
      renderDetail(await hydrateRightTargets(detailRight));
      setStatus("online", `已保存林权档案 ${saved.archiveCode || ""}`.trim());
    } catch (error) {
      setStatus("offline", `林权档案保存失败：${error.message}`);
    }
  }

  async function deleteRight(right = activeRight()) {
    if (!right) return;
    setStatus("busy", "正在删除林权档案...");
    try {
      await api(`/api/forest-rights/${encodeURIComponent(right.id)}`, { method: "DELETE" });
      state.activeId = "";
      closeRightEditor();
      closeRightDetail();
      await loadRights();
      setStatus("online", "林权档案已软删除。");
    } catch (error) {
      setStatus("offline", `林权档案删除失败：${error.message}`);
    }
  }

  async function restoreRight(right = activeRight()) {
    if (!right) return;
    setStatus("busy", "正在恢复林权档案...");
    try {
      await api(`/api/forest-rights/${encodeURIComponent(right.id)}/restore`, { method: "POST" });
      state.activeId = right.id;
      await loadRights();
      renderDetail(await hydrateRightTargets(activeRight()));
      setStatus("online", "林权档案已恢复。");
    } catch (error) {
      setStatus("offline", `林权档案恢复失败：${error.message}`);
    }
  }

  async function handleRowAction(event) {
    const rightButton = event.target.closest("[data-right-action]");
    if (rightButton) {
      event.stopPropagation();
      if (rightButton.disabled) return true;
      const row = rightButton.closest("tr[data-id]");
      const right = state.rights.find((item) => String(item.id) === String(row?.dataset.id)) || null;
      if (!right) return true;
      state.activeId = right.id;
      if (rightButton.dataset.rightAction === "restore") {
        restoreRight(right);
      }
      return true;
    }
    const button = event.target.closest("[data-row-action]");
    if (!button) return false;
    event.stopPropagation();
    if (button.disabled) return true;
    const row = button.closest("tr[data-id]");
    const right = state.rights.find((item) => String(item.id) === String(row?.dataset.id)) || null;
    if (!right) return true;
    state.activeId = right.id;
    const action = button.dataset.rowAction;
    if (action === "view") {
      renderDetail(await hydrateRightTargets(right));
    } else if (action === "edit") {
      openRightEditor("edit", await hydrateRightTargets(right));
      renderRows();
    } else if (action === "delete") {
      deleteRight(right);
    }
    return true;
  }

  function attachEvents() {
    $("#reloadRights").addEventListener("click", loadRights);
    $("#newRightArchive").addEventListener("click", () => openRightEditor("create"));
    $("#rightForm").addEventListener("submit", saveRight);
    $("#cancelRightEdit").addEventListener("click", closeRightEditor);
    $("#closeRightDetail").addEventListener("click", closeRightDetail);
    $("#deleteRightArchive").addEventListener("click", () => deleteRight(activeRight()));
    $("#rightArchiveStatusFilter").addEventListener("change", reloadRightsFromFirstPage);
    $("#rightLinkedBlockFilter").addEventListener("change", reloadRightsFromFirstPage);
    $("#includeDeletedRights").addEventListener("change", reloadRightsFromFirstPage);
    $("#rightKeyword").addEventListener("input", () => {
      window.clearTimeout(keywordTimer);
      keywordTimer = window.setTimeout(reloadRightsFromFirstPage, 180);
    });
    $("#rightRows").addEventListener("click", async (event) => {
      try {
        if (await handleRowAction(event)) return;
      } catch (error) {
        setStatus("offline", `林权关联数据加载失败：${error.message}`);
        return;
      }
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      state.activeId = row.dataset.id;
      try {
        renderDetail(await hydrateRightTargets(activeRight()));
      } catch (error) {
        setStatus("offline", `林权关联数据加载失败：${error.message}`);
      }
    });
    $("#rightVersionList")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-version-action]");
      if (!button || button.disabled) return;
      if (button.dataset.versionAction === "rollback") {
        rollbackRightVersion(button.dataset.versionId);
      }
    });
  }

  async function initialize() {
    initShell();
    if (initialArchiveCode && $("#rightKeyword")) $("#rightKeyword").value = initialArchiveCode;
    pager = createLedgerPager({ anchor: $("#rightRows").closest(".table-wrap"), onPageChange: loadRights });
    await setupSmartFields();
    attachEvents();
    loadRights();
  }

  initialize();
})();
