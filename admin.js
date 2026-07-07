const DEFAULT_API_BASE = "http://127.0.0.1:8010";

const STATUS_LABELS = {
  idle: "\u672a\u8fde\u63a5",
  online: "\u5df2\u8fde\u63a5",
  busy: "\u5904\u7406\u4e2d",
  warning: "\u9700\u5904\u7406",
  offline: "\u4e0d\u53ef\u7528",
};

const EMPTY_BLOCK = {
  geometry: null,
  properties: {},
  tags: [],
};

const state = {
  apiBase: DEFAULT_API_BASE,
  blocks: [],
  activeBlockId: "",
  filters: {
    keyword: "",
    baseType: "",
    operationType: "",
    riskLevel: "",
  },
  lastImportLabel: "\u65e0",
};

const $ = (selector) => document.querySelector(selector);

const elements = {
  apiBase: $("#apiBase"),
  authRoles: $("#authRoles"),
  authAreas: $("#authAreas"),
  authUser: $("#authUser"),
  connectApi: $("#connectApi"),
  reloadBlocks: $("#reloadBlocks"),
  statusBadge: $("#statusBadge"),
  statusText: $("#statusText"),
  blockCount: $("#blockCount"),
  lastImport: $("#lastImport"),
  keyword: $("#keyword"),
  baseTypeFilter: $("#baseTypeFilter"),
  operationTypeFilter: $("#operationTypeFilter"),
  riskLevelFilter: $("#riskLevelFilter"),
  blockRows: $("#blockRows"),
  newBlock: $("#newBlock"),
  blockForm: $("#blockForm"),
  blockId: $("#blockId"),
  blockCode: $("#blockCode"),
  blockName: $("#blockName"),
  countyCode: $("#countyCode"),
  countyName: $("#countyName"),
  townCode: $("#townCode"),
  townName: $("#townName"),
  villageCode: $("#villageCode"),
  villageName: $("#villageName"),
  baseType: $("#baseType"),
  operationType: $("#operationType"),
  forestType: $("#forestType"),
  areaMu: $("#areaMu"),
  qualityGrade: $("#qualityGrade"),
  healthStatus: $("#healthStatus"),
  riskLevel: $("#riskLevel"),
  managementStatus: $("#managementStatus"),
  ownershipStatus: $("#ownershipStatus"),
  tags: $("#tags"),
  properties: $("#properties"),
  geometry: $("#geometry"),
  importForm: $("#importForm"),
  importFile: $("#importFile"),
  importStrategy: $("#importStrategy"),
  importReport: $("#importReport"),
  reportTotal: $("#reportTotal"),
  reportValid: $("#reportValid"),
  reportInvalid: $("#reportInvalid"),
  reportStatus: $("#reportStatus"),
};

let keywordTimer = 0;

function normalizeApiBase(value) {
  const raw = String(value || "").trim();
  return raw ? raw.replace(/\/+$/, "") : DEFAULT_API_BASE;
}

function splitHeaderValues(value) {
  return String(value || "")
    .split(/[,\s;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .join(",");
}

function setStatus(kind, message) {
  elements.statusBadge.className = `status-badge ${kind}`;
  elements.statusBadge.textContent = STATUS_LABELS[kind] || STATUS_LABELS.idle;
  elements.statusText.textContent = message;
}

function buildHeaders(extraHeaders) {
  const headers = new Headers(extraHeaders || {});
  const roles = splitHeaderValues(elements.authRoles.value) || "admin";
  const areas = splitHeaderValues(elements.authAreas.value);
  const user = String(elements.authUser.value || "").trim();

  headers.set("X-RS-Roles", roles);
  if (areas) {
    headers.set("X-RS-Areas", areas);
  }
  if (user) {
    headers.set("X-RS-User", user);
  }
  return headers;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object"
        ? payload.detail || JSON.stringify(payload)
        : String(payload || response.statusText);
    throw new Error(`${response.status} ${detail}`);
  }

  return payload;
}

async function api(path, options) {
  state.apiBase = normalizeApiBase(elements.apiBase.value);
  const requestOptions = { ...(options || {}) };
  const headers = buildHeaders(requestOptions.headers);
  if (requestOptions.body && !(requestOptions.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  requestOptions.headers = headers;
  const response = await fetch(`${state.apiBase}${path}`, requestOptions);
  return parseResponse(response);
}

function updateFilterState() {
  state.filters.keyword = elements.keyword.value.trim();
  state.filters.baseType = elements.baseTypeFilter.value;
  state.filters.operationType = elements.operationTypeFilter.value;
  state.filters.riskLevel = elements.riskLevelFilter.value;
}

function buildQueryString() {
  updateFilterState();
  const query = new URLSearchParams();
  if (state.filters.keyword) {
    query.set("q", state.filters.keyword);
  }
  if (state.filters.baseType) {
    query.set("baseType", state.filters.baseType);
  }
  if (state.filters.operationType) {
    query.set("operationType", state.filters.operationType);
  }
  if (state.filters.riskLevel) {
    query.set("riskLevel", state.filters.riskLevel);
  }
  query.set("limit", "500");
  return query.toString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function activeBlock() {
  return state.blocks.find((block) => String(block.id) === String(state.activeBlockId)) || null;
}

function renderBlockRows() {
  const rows = state.blocks;
  elements.blockCount.textContent = String(rows.length);

  if (!rows.length) {
    elements.blockRows.innerHTML = `
      <tr class="placeholder-row">
        <td colspan="7">\u5f53\u524d\u7b5b\u9009\u6761\u4ef6\u4e0b\u6ca1\u6709\u53ef\u663e\u793a\u7684\u5c0f\u73ed</td>
      </tr>
    `;
    return;
  }

  elements.blockRows.innerHTML = rows
    .map((block) => {
      const isActive = String(block.id) === String(state.activeBlockId);
      return `
        <tr data-block-id="${escapeHtml(block.id)}" class="${isActive ? "active" : ""}">
          <td>${escapeHtml(block.blockCode)}</td>
          <td>${escapeHtml(block.name)}</td>
          <td>${escapeHtml(block.countyName || block.countyCode || "-")}</td>
          <td>${escapeHtml(block.townName || block.townCode || "-")}</td>
          <td>${escapeHtml(block.areaMu ?? "-")}</td>
          <td>${escapeHtml(block.operationType || "-")}</td>
          <td>${escapeHtml(block.riskLevel || "-")}</td>
        </tr>
      `;
    })
    .join("");
}

function stringifyPretty(value, fallback) {
  try {
    return JSON.stringify(value ?? fallback, null, 2);
  } catch (error) {
    return JSON.stringify(fallback, null, 2);
  }
}

function populateForm(block) {
  const nextBlock = block || EMPTY_BLOCK;
  state.activeBlockId = nextBlock.id || "";
  elements.blockId.value = nextBlock.id || "";
  elements.blockCode.value = nextBlock.blockCode || "";
  elements.blockName.value = nextBlock.name || "";
  elements.countyCode.value = nextBlock.countyCode || "";
  elements.countyName.value = nextBlock.countyName || "";
  elements.townCode.value = nextBlock.townCode || "";
  elements.townName.value = nextBlock.townName || "";
  elements.villageCode.value = nextBlock.villageCode || "";
  elements.villageName.value = nextBlock.villageName || "";
  elements.baseType.value = nextBlock.baseType || "";
  elements.operationType.value = nextBlock.operationType || "";
  elements.forestType.value = nextBlock.forestType || "";
  elements.areaMu.value = nextBlock.areaMu ?? "";
  elements.qualityGrade.value = nextBlock.qualityGrade || "";
  elements.healthStatus.value = nextBlock.healthStatus || "";
  elements.riskLevel.value = nextBlock.riskLevel || "";
  elements.managementStatus.value = nextBlock.managementStatus || "";
  elements.ownershipStatus.value = nextBlock.ownershipStatus || "";
  elements.tags.value = Array.isArray(nextBlock.tags) ? nextBlock.tags.join(", ") : "";
  elements.properties.value = stringifyPretty(nextBlock.properties, {});
  elements.geometry.value = stringifyPretty(nextBlock.geometry, null);
  renderBlockRows();
}

function resetForm() {
  populateForm(EMPTY_BLOCK);
}

function parseJsonField(label, value, fallback) {
  const text = String(value || "").trim();
  if (!text) {
    return fallback;
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`${label} \u4e0d\u662f\u5408\u6cd5 JSON`);
  }
}

function buildBlockPayload() {
  return {
    blockCode: elements.blockCode.value.trim(),
    name: elements.blockName.value.trim(),
    countyCode: elements.countyCode.value.trim() || null,
    countyName: elements.countyName.value.trim() || null,
    townCode: elements.townCode.value.trim() || null,
    townName: elements.townName.value.trim() || null,
    villageCode: elements.villageCode.value.trim() || null,
    villageName: elements.villageName.value.trim() || null,
    baseType: elements.baseType.value || null,
    operationType: elements.operationType.value || null,
    forestType: elements.forestType.value.trim() || null,
    areaMu: elements.areaMu.value ? Number(elements.areaMu.value) : null,
    qualityGrade: elements.qualityGrade.value.trim() || null,
    healthStatus: elements.healthStatus.value.trim() || null,
    riskLevel: elements.riskLevel.value || null,
    managementStatus: elements.managementStatus.value.trim() || null,
    ownershipStatus: elements.ownershipStatus.value.trim() || null,
    tags: splitHeaderValues(elements.tags.value)
      .split(",")
      .filter(Boolean),
    properties: parseJsonField("\u9644\u52a0\u5c5e\u6027", elements.properties.value, {}),
    geometry: parseJsonField("GeoJSON \u51e0\u4f55", elements.geometry.value, null),
  };
}

function buildSaveRequest(payload, blockId) {
  if (!blockId) {
    return {
      method: "POST",
      path: "/api/forest-blocks",
      body: JSON.stringify(payload),
    };
  }

  const patchPayload = { ...payload };
  delete patchPayload.blockCode;
  return {
    method: "PATCH",
    path: `/api/forest-blocks/${encodeURIComponent(blockId)}`,
    body: JSON.stringify(patchPayload),
  };
}

async function loadBlocks() {
  const queryString = buildQueryString();
  setStatus("busy", "\u6b63\u5728\u52a0\u8f7d\u68ee\u6797\u5c0f\u73ed\u5217\u8868...");

  try {
    const payload = await api(`/api/forest-blocks?${queryString}`);
    state.blocks = Array.isArray(payload.items) ? payload.items : [];

    const hiddenActiveBlock = Boolean(state.activeBlockId) && !activeBlock();
    if (hiddenActiveBlock) {
      resetForm();
    }

    renderBlockRows();
    if (state.activeBlockId) {
      populateForm(activeBlock());
    } else if (!elements.blockCode.value && !elements.blockName.value) {
      resetForm();
    }

    setStatus("online", `\u5df2\u52a0\u8f7d ${payload.total ?? state.blocks.length} \u4e2a\u5c0f\u73ed\u3002`);
    return payload;
  } catch (error) {
    state.blocks = [];
    state.activeBlockId = "";
    renderBlockRows();
    setStatus("offline", `\u63a5\u53e3\u4e0d\u53ef\u7528\uff1a${error.message}`);
    return null;
  }
}

async function saveActiveBlock(event) {
  if (event && typeof event.preventDefault === "function") {
    event.preventDefault();
  }

  let payload;
  try {
    payload = buildBlockPayload();
  } catch (error) {
    setStatus("offline", error.message);
    throw error;
  }

  setStatus("busy", "\u6b63\u5728\u4fdd\u5b58\u5c0f\u73ed...");
  const blockId = elements.blockId.value.trim();
  const request = buildSaveRequest(payload, blockId);

  try {
    const saved = await api(request.path, {
      method: request.method,
      body: request.body,
    });

    await loadBlocks();
    populateForm(saved);
    setStatus("online", `\u5df2\u4fdd\u5b58\u5c0f\u73ed ${saved.blockCode || saved.name || ""}`.trim());
    return saved;
  } catch (error) {
    setStatus("offline", `\u4fdd\u5b58\u5931\u8d25\uff1a${error.message}`);
    throw error;
  }
}

function renderImportMetrics(report) {
  const nextReport = report || {};
  elements.reportTotal.textContent = String(nextReport.totalRows || 0);
  elements.reportValid.textContent = String(nextReport.validRows || 0);
  elements.reportInvalid.textContent = String(nextReport.invalidRows || 0);
  elements.reportStatus.textContent = String(nextReport.status || "\u672a\u6267\u884c");
}

async function importForestBlocks(event) {
  if (event && typeof event.preventDefault === "function") {
    event.preventDefault();
  }

  const file = elements.importFile.files && elements.importFile.files[0];
  if (!file) {
    const error = new Error("\u8bf7\u9009\u62e9\u5bfc\u5165\u6587\u4ef6");
    setStatus("offline", error.message);
    throw error;
  }

  const formData = new FormData();
  formData.set("file", file);
  formData.set("strategy", elements.importStrategy.value);

  setStatus("busy", `\u6b63\u5728\u5bfc\u5165 ${file.name}...`);

  try {
    const payload = await api("/api/imports/forest-blocks", {
      method: "POST",
      body: formData,
    });
    const report = payload.report || payload;
    renderImportMetrics(report);
    elements.importReport.textContent = JSON.stringify(report, null, 2);
    state.lastImportLabel = `${report.fileName || file.name} / ${report.status || "completed"}`;
    elements.lastImport.textContent = state.lastImportLabel;
    await loadBlocks();

    const hasValidationErrors = Number(report.invalidRows || 0) > 0;
    setStatus(
      hasValidationErrors ? "warning" : "online",
      hasValidationErrors
        ? `\u5bfc\u5165\u5b8c\u6210\uff0c\u5b58\u5728\u6821\u9a8c\u9519\u8bef\uff1a${report.invalidRows} \u884c\u672a\u901a\u8fc7\u3002`
        : `\u5bfc\u5165\u5b8c\u6210\uff0c\u5171\u5904\u7406 ${report.totalRows || 0} \u884c\u3002`
    );
    return payload;
  } catch (error) {
    renderImportMetrics(null);
    elements.importReport.textContent = `\u5bfc\u5165\u5931\u8d25\n${error.message}`;
    setStatus("offline", `\u5bfc\u5165\u5931\u8d25\uff1a${error.message}`);
    throw error;
  }
}

function attachEvents() {
  elements.connectApi.addEventListener("click", loadBlocks);
  elements.reloadBlocks.addEventListener("click", loadBlocks);
  elements.newBlock.addEventListener("click", resetForm);
  elements.blockForm.addEventListener("submit", saveActiveBlock);
  elements.importForm.addEventListener("submit", importForestBlocks);

  [elements.baseTypeFilter, elements.operationTypeFilter, elements.riskLevelFilter].forEach((element) => {
    element.addEventListener("change", loadBlocks);
  });

  elements.keyword.addEventListener("input", () => {
    window.clearTimeout(keywordTimer);
    keywordTimer = window.setTimeout(loadBlocks, 220);
  });

  elements.blockRows.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-block-id]");
    if (!row) {
      return;
    }
    state.activeBlockId = row.getAttribute("data-block-id") || "";
    populateForm(activeBlock());
  });
}

function initialize() {
  attachEvents();
  renderImportMetrics(null);
  resetForm();
  loadBlocks();
}

window.SmartBambooAdmin = {
  loadBlocks,
  saveActiveBlock,
  importForestBlocks,
};

initialize();
