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

  const ACTION_PERMISSIONS = {
    create: "system.dictionaries.create",
    update: "system.dictionaries.update",
    delete: "system.dictionaries.delete",
    restore: "system.dictionaries.restore",
  };
  const CATEGORY_LABELS = {
    administrative: "行政区划",
    forestry: "林业资源",
    rights: "林权档案",
    business: "业务经营",
    materials: "农资物料",
    system: "系统通用",
  };
  const STATUS_LABELS = { active: "启用", disabled: "停用" };
  const SOURCE_LABELS = {
    seed: "系统种子",
    manual: "人工维护",
    import: "批量导入",
    "forest-block": "林班数据",
  };
  const ICONS = {
    view: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>',
    edit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 20 4.6-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z"></path><path d="m13.5 6.5 4 4"></path></svg>',
    delete: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M6 7l1 13h10l1-13"></path><path d="M9 7V4h6v3"></path></svg>',
    restore: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.4-6.4"></path><path d="M18 3v5h-5"></path><path d="M21 12a9 9 0 0 1-15.4 6.4"></path><path d="M6 21v-5h5"></path></svg>',
  };
  const state = {
    dictionaries: [],
    activeId: "",
    items: [],
    optionProbe: [],
  };
  let pager;
  let dictionaryKeywordTimer = 0;
  let itemKeywordTimer = 0;

  function activeDictionary() {
    return state.dictionaries.find((item) => String(item.id) === String(state.activeId)) || null;
  }

  function showModal(selector) {
    const target = $(selector);
    if (!target) return;
    target.classList.remove("hidden");
    target.setAttribute("aria-hidden", "false");
  }

  function hideModal(selector) {
    const target = $(selector);
    if (!target) return;
    target.classList.add("hidden");
    target.setAttribute("aria-hidden", "true");
  }

  function dictionaryQuery() {
    return query({
      q: $("#dictionaryKeyword").value.trim(),
      category: $("#dictionaryCategoryFilter").value,
      status: $("#dictionaryStatusFilter").value,
      includeDeleted: $("#includeDeletedDictionaries").checked ? "true" : "",
      limit: pager.limit,
      offset: pager.offset,
    });
  }

  function rowActions(dictionary) {
    if (dictionary.deletedAt) {
      return `
        <div class="row-actions" aria-label="行操作">
          <button type="button" class="icon-button" data-row-action="view" aria-label="查看" title="查看">${ICONS.view}</button>
          <button type="button" class="icon-button" data-row-action="restore" data-permission="${ACTION_PERMISSIONS.restore}" aria-label="恢复" title="恢复">${ICONS.restore}</button>
        </div>
      `;
    }
    return `
      <div class="row-actions" aria-label="行操作">
        <button type="button" class="icon-button" data-row-action="view" aria-label="查看" title="查看">${ICONS.view}</button>
        <button type="button" class="icon-button" data-row-action="edit" data-permission="${ACTION_PERMISSIONS.update}" aria-label="编辑" title="编辑">${ICONS.edit}</button>
        <button type="button" class="icon-button danger" data-row-action="delete" data-permission="${ACTION_PERMISSIONS.delete}" aria-label="删除" title="删除">${ICONS.delete}</button>
      </div>
    `;
  }

  function renderSummary() {
    $("#dictionaryTotal").textContent = String(pager.total || state.dictionaries.length);
    $("#dictionaryActiveTotal").textContent = String(
      state.dictionaries.filter((item) => !item.deletedAt && item.status === "active").length,
    );
    $("#dictionaryItemTotal").textContent = String(
      state.dictionaries.reduce((total, item) => total + Number(item.itemCount || 0), 0),
    );
    $("#dictionaryHierarchyTotal").textContent = String(
      state.dictionaries.filter((item) => !item.deletedAt && item.hierarchyEnabled).length,
    );
  }

  function renderDictionaryRows() {
    const target = $("#dictionaryRows");
    if (!state.dictionaries.length) {
      target.innerHTML = '<tr class="placeholder-row"><td colspan="7">暂无符合条件的字典</td></tr>';
      renderSummary();
      return;
    }
    target.innerHTML = state.dictionaries
      .map(
        (dictionary) => `
          <tr data-id="${escapeHtml(dictionary.id)}" class="${dictionary.deletedAt ? "row-deleted" : ""}">
            <td class="dictionary-primary-cell">
              <div class="cell-stack">
                <strong>${escapeHtml(dictionary.name)}</strong>
                <small>${escapeHtml(dictionary.typeCode)}</small>
                <div class="dictionary-mobile-meta" aria-label="字典摘要">
                  <span>${escapeHtml(CATEGORY_LABELS[dictionary.category] || dictionary.category)}</span>
                  <span>${dictionary.hierarchyEnabled ? "层级" : "平级"}</span>
                  <span>${Number(dictionary.itemCount || 0)} 个词条</span>
                  <span>${escapeHtml(dictionary.deletedAt ? "已删除" : STATUS_LABELS[dictionary.status] || dictionary.status)}</span>
                </div>
              </div>
            </td>
            <td class="dictionary-category-cell">${escapeHtml(CATEGORY_LABELS[dictionary.category] || dictionary.category)}</td>
            <td class="dictionary-structure-cell">
              <span class="status-pill ${dictionary.hierarchyEnabled ? "warning" : ""}">
                ${dictionary.hierarchyEnabled ? "层级" : "平级"}
              </span>
            </td>
            <td class="dictionary-count-cell">
              <div class="cell-stack">
                <strong>${Number(dictionary.itemCount || 0)}</strong>
                <small>${Number(dictionary.activeItemCount || 0)} 个启用</small>
              </div>
            </td>
            <td class="dictionary-status-cell"><span class="status-pill ${dictionary.status === "active" ? "" : "warning"}">${escapeHtml(dictionary.deletedAt ? "已删除" : STATUS_LABELS[dictionary.status] || dictionary.status)}</span></td>
            <td class="dictionary-updated-cell">${escapeHtml(formatDateTime(dictionary.updatedAt))}</td>
            <td class="dictionary-actions-cell">${rowActions(dictionary)}</td>
          </tr>
        `,
      )
      .join("");
    applyActionPermissions();
    renderSummary();
  }

  function renderDictionaryDetail() {
    const dictionary = activeDictionary();
    if (!dictionary) return;
    $("#dictionaryDetailTitle").textContent = dictionary.name;
    $("#dictionaryDetailGrid").innerHTML = `
      <div><dt>字典编码</dt><dd>${escapeHtml(dictionary.typeCode)}</dd></div>
      <div><dt>分类</dt><dd>${escapeHtml(CATEGORY_LABELS[dictionary.category] || dictionary.category)}</dd></div>
      <div><dt>结构</dt><dd>${dictionary.hierarchyEnabled ? "层级字典" : "平级字典"}</dd></div>
      <div><dt>取值方式</dt><dd>${dictionary.valueMode === "label" ? "保存名称" : "保存编码"}</dd></div>
      <div><dt>状态</dt><dd>${escapeHtml(dictionary.deletedAt ? "已删除" : STATUS_LABELS[dictionary.status] || dictionary.status)}</dd></div>
      <div><dt>系统字典</dt><dd>${dictionary.systemDefined ? "是" : "否"}</dd></div>
      <div class="detail-span-2"><dt>说明</dt><dd>${escapeHtml(dictionary.description || "未填")}</dd></div>
    `;
    $("#newDictionaryItem").disabled = Boolean(dictionary.deletedAt);
    $("#editDictionaryFromDetail").disabled = Boolean(dictionary.deletedAt);
    applyActionPermissions();
  }

  function filteredItems() {
    const q = $("#dictionaryItemKeyword").value.trim().toLowerCase();
    const level = $("#dictionaryItemLevelFilter").value.trim().toLowerCase();
    const parent = $("#dictionaryItemParentFilter").value;
    return state.items.filter((item) => {
      const text = [
        item.itemCode,
        item.label,
        item.fullName,
        item.pinyin,
        item.initials,
        ...(item.searchAliases || []),
      ]
        .join(" ")
        .toLowerCase();
      return (!q || text.includes(q)) && (!level || String(item.levelCode || "").toLowerCase().includes(level)) && (!parent || item.parentCode === parent);
    });
  }

  function itemActions(item) {
    if (item.deletedAt) {
      return `
        <div class="row-actions" aria-label="词条操作">
          <button type="button" class="icon-button" data-item-action="restore" data-permission="${ACTION_PERMISSIONS.restore}" aria-label="恢复词条" title="恢复词条">${ICONS.restore}</button>
        </div>
      `;
    }
    return `
      <div class="row-actions" aria-label="词条操作">
        <button type="button" class="icon-button" data-item-action="edit" data-permission="${ACTION_PERMISSIONS.update}" aria-label="编辑词条" title="编辑词条">${ICONS.edit}</button>
        <button type="button" class="icon-button danger" data-item-action="delete" data-permission="${ACTION_PERMISSIONS.delete}" aria-label="删除词条" title="删除词条">${ICONS.delete}</button>
      </div>
    `;
  }

  function renderItemParentFilters() {
    const currentFilter = $("#dictionaryItemParentFilter").value;
    $("#dictionaryItemParentFilter").innerHTML =
      '<option value="">全部父级</option>' +
      state.items
        .filter((item) => !item.deletedAt)
        .sort((left, right) => Number(left.sortOrder || 0) - Number(right.sortOrder || 0))
        .map((item) => `<option value="${escapeHtml(item.itemCode)}">${escapeHtml(item.label)} · ${escapeHtml(item.itemCode)}</option>`)
        .join("");
    if (state.items.some((item) => item.itemCode === currentFilter)) {
      $("#dictionaryItemParentFilter").value = currentFilter;
    }
  }

  function renderDictionaryItemRows() {
    const target = $("#dictionaryItemRows");
    const records = filteredItems();
    if (!records.length) {
      target.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无符合条件的词条</td></tr>';
      return;
    }
    target.innerHTML = records
      .map(
        (item) => `
          <tr data-item-id="${escapeHtml(item.id)}" class="${item.deletedAt ? "row-deleted" : ""}">
            <td>
              <div class="cell-stack">
                <strong>${escapeHtml(item.label)}</strong>
                <small>${escapeHtml(item.itemCode)}</small>
              </div>
            </td>
            <td>${escapeHtml(item.parentCode || "根级")}</td>
            <td>${escapeHtml(item.levelCode || "未分级")}</td>
            <td>${escapeHtml(SOURCE_LABELS[item.source] || item.source)}</td>
            <td><span class="status-pill ${item.status === "active" ? "" : "warning"}">${escapeHtml(item.deletedAt ? "已删除" : STATUS_LABELS[item.status] || item.status)}</span></td>
            <td>${itemActions(item)}</td>
          </tr>
        `,
      )
      .join("");
    applyActionPermissions();
  }

  async function loadDictionaries() {
    pager.setBusy(true);
    setStatus("busy", "正在读取字典台账。");
    try {
      const payload = await api(`/api/dictionaries?${dictionaryQuery()}`);
      state.dictionaries = payload.items || [];
      if (pager.setTotal(payload.total || 0)) return loadDictionaries();
      renderDictionaryRows();
      setStatus("online", `已加载 ${payload.total || 0} 个字典。`);
    } catch (error) {
      setStatus("offline", `字典加载失败：${error.message}`);
    } finally {
      pager.setBusy(false);
    }
  }

  async function loadDictionaryItems() {
    const dictionary = activeDictionary();
    if (!dictionary) return;
    try {
      const itemParams = query({
        includeDeleted: $("#includeDeletedDictionaryItems").checked ? "true" : "",
        limit: 1000,
        offset: 0,
      });
      const [payload, optionProbe] = await Promise.all([
        api(`/api/dictionaries/${encodeURIComponent(dictionary.typeCode)}/items?${itemParams}`),
        api(`/api/dictionary-options/${encodeURIComponent(dictionary.typeCode)}?limit=1`),
      ]);
      state.items = payload.items || [];
      state.optionProbe = optionProbe.items || [];
      renderItemParentFilters();
      renderDictionaryItemRows();
    } catch (error) {
      setStatus("offline", `词条加载失败：${error.message}`);
    }
  }

  async function openDictionaryDetail(dictionary) {
    state.activeId = dictionary.id;
    renderDictionaryDetail();
    showModal("#dictionaryDetailPanel");
    await loadDictionaryItems();
  }

  function closeDictionaryDetail() {
    hideModal("#dictionaryDetailPanel");
  }

  function openDictionaryEditor(dictionary = null) {
    const editing = Boolean(dictionary);
    $("#dictionaryFormTitle").textContent = editing ? "编辑字典" : "新建字典";
    $("#dictionaryId").value = dictionary?.id || "";
    $("#dictionaryTypeCode").value = dictionary?.typeCode || "";
    $("#dictionaryTypeCode").disabled = editing;
    $("#dictionaryName").value = dictionary?.name || "";
    $("#dictionaryCategory").value = dictionary?.category || "business";
    $("#dictionaryStatus").value = dictionary?.status || "active";
    $("#dictionaryValueMode").value = dictionary?.valueMode || "code";
    $("#dictionarySortOrder").value = Number(dictionary?.sortOrder || 0);
    $("#dictionaryHierarchyEnabled").checked = Boolean(dictionary?.hierarchyEnabled);
    $("#dictionaryDescription").value = dictionary?.description || "";
    $("#dictionaryProperties").value = stringifyPretty(dictionary?.properties || {});
    $("#saveDictionary").dataset.permission = editing ? ACTION_PERMISSIONS.update : ACTION_PERMISSIONS.create;
    applyActionPermissions();
    showModal("#dictionaryForm");
  }

  function closeDictionaryEditor() {
    hideModal("#dictionaryForm");
  }

  function renderParentOptions(excludedItemId = "") {
    $("#dictionaryItemParent").innerHTML =
      '<option value="">无父级</option>' +
      state.items
        .filter((item) => !item.deletedAt && String(item.id) !== String(excludedItemId))
        .map((item) => `<option value="${escapeHtml(item.itemCode)}">${escapeHtml(item.label)} · ${escapeHtml(item.itemCode)}</option>`)
        .join("");
  }

  function openDictionaryItemEditor(item = null) {
    const editing = Boolean(item);
    $("#dictionaryItemFormTitle").textContent = editing ? "编辑词条" : "新增词条";
    $("#dictionaryItemId").value = item?.id || "";
    $("#dictionaryItemCode").value = item?.itemCode || "";
    $("#dictionaryItemCode").disabled = editing;
    $("#dictionaryItemLabel").value = item?.label || "";
    renderParentOptions(item?.id || "");
    $("#dictionaryItemParent").value = item?.parentCode || "";
    $("#dictionaryItemLevel").value = item?.levelCode || "";
    $("#dictionaryItemFullName").value = item?.fullName || "";
    $("#dictionaryItemPinyin").value = item?.pinyin || "";
    $("#dictionaryItemInitials").value = item?.initials || "";
    $("#dictionaryItemAliases").value = (item?.searchAliases || []).join(", ");
    $("#dictionaryItemSortOrder").value = Number(item?.sortOrder || 0);
    $("#dictionaryItemStatus").value = item?.status || "active";
    $("#dictionaryItemSource").value = item?.source || "manual";
    $("#dictionaryItemMetadata").value = stringifyPretty(item?.metadata || {});
    $("#saveDictionaryItem").dataset.permission = editing ? ACTION_PERMISSIONS.update : ACTION_PERMISSIONS.create;
    applyActionPermissions();
    showModal("#dictionaryItemForm");
  }

  function closeDictionaryItemEditor() {
    hideModal("#dictionaryItemForm");
  }

  async function saveDictionary(event) {
    event.preventDefault();
    const id = $("#dictionaryId").value;
    const payload = {
      name: $("#dictionaryName").value.trim(),
      category: $("#dictionaryCategory").value,
      hierarchyEnabled: $("#dictionaryHierarchyEnabled").checked,
      valueMode: $("#dictionaryValueMode").value,
      description: $("#dictionaryDescription").value.trim(),
      status: $("#dictionaryStatus").value,
      sortOrder: Number($("#dictionarySortOrder").value || 0),
      properties: parseJson("扩展 JSON", $("#dictionaryProperties").value, {}),
    };
    if (!id) payload.typeCode = $("#dictionaryTypeCode").value.trim();
    try {
      const saved = await api(id ? `/api/dictionaries/${encodeURIComponent(id)}` : "/api/dictionaries", {
        method: id ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      state.activeId = saved.id;
      closeDictionaryEditor();
      await loadDictionaries();
      const current = activeDictionary() || saved;
      if (current) await openDictionaryDetail(current);
      setStatus("online", id ? "字典已更新。" : "字典已创建。");
    } catch (error) {
      setStatus("offline", `字典保存失败：${error.message}`);
    }
  }

  async function saveDictionaryItem(event) {
    event.preventDefault();
    const dictionary = activeDictionary();
    if (!dictionary) return;
    const id = $("#dictionaryItemId").value;
    const payload = {
      label: $("#dictionaryItemLabel").value.trim(),
      parentCode: $("#dictionaryItemParent").value,
      levelCode: $("#dictionaryItemLevel").value.trim(),
      fullName: $("#dictionaryItemFullName").value.trim(),
      pinyin: $("#dictionaryItemPinyin").value.trim(),
      initials: $("#dictionaryItemInitials").value.trim(),
      searchAliases: splitValues($("#dictionaryItemAliases").value),
      sortOrder: Number($("#dictionaryItemSortOrder").value || 0),
      status: $("#dictionaryItemStatus").value,
      source: $("#dictionaryItemSource").value,
      metadata: parseJson("元数据 JSON", $("#dictionaryItemMetadata").value, {}),
    };
    if (!id) payload.itemCode = $("#dictionaryItemCode").value.trim();
    const base = `/api/dictionaries/${encodeURIComponent(dictionary.typeCode)}/items`;
    try {
      await api(id ? `${base}/${encodeURIComponent(id)}` : base, {
        method: id ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      closeDictionaryItemEditor();
      await loadDictionaryItems();
      setStatus("online", id ? "词条已更新。" : "词条已创建。");
    } catch (error) {
      setStatus("offline", `词条保存失败：${error.message}`);
    }
  }

  async function deleteOrRestoreDictionary(dictionary, action) {
    const restoring = action === "restore";
    const path = restoring
      ? `/api/dictionaries/${encodeURIComponent(dictionary.id)}/restore`
      : `/api/dictionaries/${encodeURIComponent(dictionary.id)}`;
    try {
      await api(path, { method: restoring ? "POST" : "DELETE" });
      closeDictionaryDetail();
      await loadDictionaries();
      setStatus("online", restoring ? "字典已恢复。" : "字典已删除。");
    } catch (error) {
      setStatus("offline", `${restoring ? "恢复" : "删除"}失败：${error.message}`);
    }
  }

  async function deleteOrRestoreItem(item, action) {
    const dictionary = activeDictionary();
    if (!dictionary) return;
    const restoring = action === "restore";
    const base = `/api/dictionaries/${encodeURIComponent(dictionary.typeCode)}/items/${encodeURIComponent(item.id)}`;
    try {
      await api(restoring ? `${base}/restore` : base, { method: restoring ? "POST" : "DELETE" });
      await loadDictionaryItems();
      setStatus("online", restoring ? "词条已恢复。" : "词条已删除。");
    } catch (error) {
      setStatus("offline", `${restoring ? "恢复" : "删除"}失败：${error.message}`);
    }
  }

  function resetDictionaryPage() {
    pager.reset();
    loadDictionaries();
  }

  function initialize() {
    initShell();
    pager = createLedgerPager({
      anchor: $("#dictionaryRows").closest(".table-wrap"),
      pageSize: 25,
      onPageChange: loadDictionaries,
    });
    $("#reloadDictionaries").addEventListener("click", loadDictionaries);
    $("#newDictionary").addEventListener("click", () => openDictionaryEditor());
    $("#dictionaryForm").addEventListener("submit", saveDictionary);
    $("#dictionaryItemForm").addEventListener("submit", saveDictionaryItem);
    $("#cancelDictionaryEdit").addEventListener("click", closeDictionaryEditor);
    $("#cancelDictionaryItemEdit").addEventListener("click", closeDictionaryItemEditor);
    $("#closeDictionaryDetail").addEventListener("click", closeDictionaryDetail);
    $("#newDictionaryItem").addEventListener("click", () => openDictionaryItemEditor());
    $("#editDictionaryFromDetail").addEventListener("click", () => openDictionaryEditor(activeDictionary()));
    ["#dictionaryCategoryFilter", "#dictionaryStatusFilter", "#includeDeletedDictionaries"].forEach((selector) => {
      $(selector).addEventListener("change", resetDictionaryPage);
    });
    $("#dictionaryKeyword").addEventListener("input", () => {
      window.clearTimeout(dictionaryKeywordTimer);
      dictionaryKeywordTimer = window.setTimeout(resetDictionaryPage, 180);
    });
    ["#dictionaryItemParentFilter", "#includeDeletedDictionaryItems"].forEach((selector) => {
      $(selector).addEventListener("change", selector.includes("includeDeleted") ? loadDictionaryItems : renderDictionaryItemRows);
    });
    ["#dictionaryItemKeyword", "#dictionaryItemLevelFilter"].forEach((selector) => {
      $(selector).addEventListener("input", () => {
        window.clearTimeout(itemKeywordTimer);
        itemKeywordTimer = window.setTimeout(renderDictionaryItemRows, 160);
      });
    });
    $("#dictionaryRows").addEventListener("click", async (event) => {
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      const dictionary = state.dictionaries.find((item) => String(item.id) === String(row.dataset.id));
      if (!dictionary) return;
      const button = event.target.closest("[data-row-action]");
      if (!button) return openDictionaryDetail(dictionary);
      event.stopPropagation();
      if (button.disabled) return;
      const action = button.dataset.rowAction;
      if (action === "view") return openDictionaryDetail(dictionary);
      if (action === "edit") return openDictionaryEditor(dictionary);
      if (action === "delete" || action === "restore") return deleteOrRestoreDictionary(dictionary, action);
    });
    $("#dictionaryItemRows").addEventListener("click", (event) => {
      const button = event.target.closest("[data-item-action]");
      if (!button || button.disabled) return;
      const row = button.closest("tr[data-item-id]");
      const item = state.items.find((record) => String(record.id) === String(row?.dataset.itemId));
      if (!item) return;
      if (button.dataset.itemAction === "edit") return openDictionaryItemEditor(item);
      return deleteOrRestoreItem(item, button.dataset.itemAction);
    });
    loadDictionaries();
  }

  initialize();
})();
