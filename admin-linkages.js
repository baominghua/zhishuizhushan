(() => {
  const {
    $,
    api,
    applyActionPermissions,
    createLedgerPager,
    escapeHtml,
    formatDateTime,
    initShell,
    labelFor,
    query,
    rowActionButtons,
    setStatus,
    splitValues,
  } = AdminCommon;
  const PAGE_PERMISSION = "forest.linkages.manage";
  const state = { rights: [], activeId: "" };
  let pager;
  let keywordTimer;

  function activeRight() {
    return state.rights.find((right) => String(right.id) === String(state.activeId)) || null;
  }

  function renderRows() {
    const body = $("#linkageRows");
    if (!state.rights.length) {
      body.innerHTML = '<tr class="placeholder-row"><td colspan="5">暂无可挂接档案</td></tr>';
      return;
    }
    body.innerHTML = state.rights
      .map((right) => {
        const linked = right.linkedBlockCodes || [];
        const active = String(right.id) === String(state.activeId) ? "active" : "";
        return `
          <tr data-id="${escapeHtml(right.id)}" class="${active}">
            <td><div class="cell-stack"><strong>${escapeHtml(right.archiveCode || "-")}</strong><small>${escapeHtml(right.certificateNo || "-")}</small></div></td>
            <td>${escapeHtml(right.holder || "-")}</td>
            <td><div class="cell-stack"><strong>${escapeHtml(linked.length ? `${linked.length} 个林班` : "未挂接")}</strong><small>${escapeHtml(linked.join(", ") || "-")}</small></div></td>
            <td><span class="status-pill ${escapeHtml(right.archiveStatus || "partial")}">${escapeHtml(labelFor("archiveStatus", right.archiveStatus || "partial"))}</span></td>
            <td>${rowActionButtons(PAGE_PERMISSION, { edit: "编辑挂接", delete: "解除挂接" })}</td>
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
    const panel = $("#linkageDetailPanel");
    if (!right) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      return;
    }
    const linked = Array.isArray(right.linkedBlockCodes) ? right.linkedBlockCodes.join(", ") : "";
    $("#linkageDetailTitle").textContent = `${right.archiveCode || right.certificateNo || "档案"}挂接详情`;
    $("#linkageDetailEmpty").hidden = true;
    $("#linkageDetailGrid").innerHTML = [
      detailItem("档案编号", right.archiveCode || "-"),
      detailItem("林权证号", right.certificateNo || "-"),
      detailItem("权利人", right.holder || "-"),
      detailItem("档案状态", labelFor("archiveStatus", right.archiveStatus || "partial")),
      detailItem("关联林班", linked || "未挂接"),
      detailItem("更新时间", formatDateTime(right.updatedAt)),
    ].join("");
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    renderRows();
  }

  function fillForm(right = {}) {
    state.activeId = right.id || "";
    $("#linkageTitle").textContent = right.id ? "编辑图档挂接" : "选择档案";
    $("#rightId").value = right.id || "";
    $("#archiveCode").value = right.archiveCode || "";
    $("#certificateNo").value = right.certificateNo || "";
    $("#linkedBlockCodes").value = Array.isArray(right.linkedBlockCodes) ? right.linkedBlockCodes.join(", ") : "";
    renderRows();
  }

  function openLinkageEditor(mode, right = {}) {
    closeLinkageDetail();
    fillForm(mode === "edit" ? right : {});
    $("#linkageForm").classList.remove("hidden");
    $("#linkageForm").setAttribute("aria-hidden", "false");
    $("#linkedBlockCodes").focus();
  }

  function closeLinkageEditor() {
    $("#linkageForm").classList.add("hidden");
    $("#linkageForm").setAttribute("aria-hidden", "true");
  }

  function closeLinkageDetail() {
    $("#linkageDetailPanel").classList.add("hidden");
    $("#linkageDetailPanel").setAttribute("aria-hidden", "true");
  }

  async function loadLinkages() {
    setStatus("busy", "正在加载图档关联...");
    pager.setBusy(true);
    try {
      const qs = query({
        q: $("#linkageKeyword").value.trim(),
        linkedBlockCode: $("#linkedBlockFilter").value.trim(),
        limit: pager.limit,
        offset: pager.offset,
      });
      const payload = await api(`/api/forest-rights?${qs}`);
      if (pager.setTotal(payload.total ?? 0)) return loadLinkages();
      state.rights = Array.isArray(payload.items) ? payload.items : [];
      if (state.activeId && !activeRight()) state.activeId = "";
      renderRows();
      renderDetail(activeRight());
      setStatus("online", `已加载 ${payload.total ?? state.rights.length} 份档案关联。`);
    } catch (error) {
      setStatus("offline", `图档关联加载失败：${error.message}`);
    } finally {
      pager.setBusy(false);
    }
  }

  function reloadLinkagesFromFirstPage() {
    pager.reset();
    return loadLinkages();
  }

  async function saveLinkage(event) {
    event.preventDefault();
    const id = $("#rightId").value.trim();
    if (!id) {
      setStatus("warning", "请先选择一份林权档案。");
      return;
    }
    setStatus("busy", "正在保存挂接关系...");
    try {
      const saved = await api(`/api/forest-rights/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify({ linkedBlockCodes: splitValues($("#linkedBlockCodes").value) }),
      });
      state.activeId = saved.id;
      closeLinkageEditor();
      await loadLinkages();
      renderDetail(state.rights.find((right) => String(right.id) === String(saved.id)) || saved);
      setStatus("online", "图档挂接已保存。");
    } catch (error) {
      setStatus("offline", `图档挂接保存失败：${error.message}`);
    }
  }

  async function deleteLinkage(right = activeRight()) {
    if (!right) return;
    setStatus("busy", "正在解除图档挂接...");
    try {
      const saved = await api(`/api/forest-rights/${encodeURIComponent(right.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ linkedBlockCodes: [] }),
      });
      state.activeId = saved.id;
      closeLinkageEditor();
      await loadLinkages();
      renderDetail(state.rights.find((item) => String(item.id) === String(saved.id)) || saved);
      setStatus("online", "图档挂接已解除。");
    } catch (error) {
      setStatus("offline", `图档挂接解除失败：${error.message}`);
    }
  }

  function applyPagePermissionAttributes() {
    const pagePermission = document.body.dataset.permission || "";
    if (!pagePermission) return;
    ["#saveLinkage", "#deleteLinkage"].forEach((selector) => {
      const element = $(selector);
      if (element) element.setAttribute("data-permission", pagePermission);
    });
  }

  function handleRowAction(event) {
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
      renderDetail(right);
    } else if (action === "edit") {
      openLinkageEditor("edit", right);
      renderRows();
    } else if (action === "delete") {
      deleteLinkage(right);
    }
    return true;
  }

  function initialize() {
    applyPagePermissionAttributes();
    initShell();
    pager = createLedgerPager({ anchor: $("#linkageRows").closest(".table-wrap"), onPageChange: loadLinkages });
    $("#reloadLinkages").addEventListener("click", loadLinkages);
    $("#linkageForm").addEventListener("submit", saveLinkage);
    $("#cancelLinkageEdit").addEventListener("click", closeLinkageEditor);
    $("#closeLinkageDetail").addEventListener("click", closeLinkageDetail);
    $("#deleteLinkage").addEventListener("click", () => deleteLinkage(activeRight()));
    $("#linkedBlockFilter").addEventListener("change", reloadLinkagesFromFirstPage);
    $("#linkageKeyword").addEventListener("input", () => {
      window.clearTimeout(keywordTimer);
      keywordTimer = window.setTimeout(reloadLinkagesFromFirstPage, 180);
    });
    $("#linkageRows").addEventListener("click", (event) => {
      if (handleRowAction(event)) return;
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      state.activeId = row.dataset.id;
      renderDetail(activeRight());
    });
    loadLinkages();
  }

  initialize();
})();
