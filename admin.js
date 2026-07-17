const DEFAULT_API_BASE = "http://127.0.0.1:8010";

const STATUS_LABELS = {
  idle: "未连接",
  online: "已连接",
  busy: "处理中",
  warning: "需处理",
  offline: "不可用",
};

const LABELS = {
  baseType: {
    self_operated: "自营",
    franchise: "加盟",
    cooperative: "合作经营",
  },
  operationType: {
    timber: "竹材用林",
    dual_regular: "常规笋竹两用林",
    dual_high_yield: "高产笋竹两用林",
    understory: "林下经济",
  },
  riskLevel: {
    low: "低",
    medium: "中",
    high: "高",
    critical: "严重",
  },
  ownershipStatus: {
    certified: "已确权",
    pending: "待确权",
    disputed: "权属争议",
    collective: "集体林权",
  },
  managementStatus: {
    active: "经营中",
    archiving: "补档中",
    transferred: "已流转",
    paused: "暂停经营",
  },
  archiveStatus: {
    complete: "完整",
    partial: "待补充",
    missing: "缺档",
    review: "复核中",
  },
};

const EMPTY_BLOCK = {
  geometry: null,
  properties: {},
  tags: [],
};

const EMPTY_RIGHT_ARCHIVE = {
  properties: {},
  linkedBlockCodes: [],
  linkedBlockIds: [],
};

const EMPTY_BUSINESS_RECORD = {
  properties: {},
  linkedBlockCodes: [],
  linkedRightArchiveCodes: [],
  style: {},
  visibleOnDashboard: true,
};

const ADMIN_BUSINESS_MODULES = {
  farmers: { label: "竹农", endpoint: "/api/business/farmers" },
  cooperatives: { label: "合作社", endpoint: "/api/business/cooperatives" },
  enterprises: { label: "竹企", endpoint: "/api/business/enterprises" },
  "plant-protection-events": { label: "植保", endpoint: "/api/business/plant-protection-events" },
  materials: { label: "农资", endpoint: "/api/business/materials" },
  policies: { label: "政策法规", endpoint: "/api/business/policies" },
  "map-layers": { label: "图层发布", endpoint: "/api/map-layers", layerModule: true },
};

const state = {
  apiBase: DEFAULT_API_BASE,
  blocks: [],
  totalBlocks: 0,
  activeBlockId: "",
  rights: [],
  totalRights: 0,
  activeRightId: "",
  businessRecords: [],
  totalBusinessRecords: 0,
  activeBusinessRecordId: "",
  sources: [],
  selectedSourcePath: "",
  filters: {
    keyword: "",
    baseType: "",
    operationType: "",
    riskLevel: "",
  },
  rightFilters: {
    keyword: "",
    archiveStatus: "",
    linkedBlockCode: "",
  },
  businessFilters: {
    keyword: "",
    status: "",
    linkedBlockCode: "",
  },
  lastImportLabel: "无",
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
  metricTotal: $("#metricTotal"),
  metricArea: $("#metricArea"),
  metricCertified: $("#metricCertified"),
  metricMissing: $("#metricMissing"),
  keyword: $("#keyword"),
  baseTypeFilter: $("#baseTypeFilter"),
  operationTypeFilter: $("#operationTypeFilter"),
  riskLevelFilter: $("#riskLevelFilter"),
  blockRows: $("#blockRows"),
  newBlock: $("#newBlock"),
  blockForm: $("#blockForm"),
  formTitle: $("#formTitle"),
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
  tags: $("#tags"),
  properties: $("#properties"),
  geometry: $("#geometry"),
  sceneLinkSceneId: $("#sceneLinkSceneId"),
  sceneLinkRelationType: $("#sceneLinkRelationType"),
  sceneLinkCapturedAt: $("#sceneLinkCapturedAt"),
  sceneLinkConfidence: $("#sceneLinkConfidence"),
  sceneLinkStatus: $("#sceneLinkStatus"),
  linkScene: $("#linkScene"),
  linkedScenes: $("#linkedScenes"),
  rightKeyword: $("#rightKeyword"),
  rightArchiveStatusFilter: $("#rightArchiveStatusFilter"),
  rightLinkedBlockFilter: $("#rightLinkedBlockFilter"),
  rightRows: $("#rightRows"),
  newRightArchive: $("#newRightArchive"),
  rightForm: $("#rightForm"),
  rightFormTitle: $("#rightFormTitle"),
  rightArchiveId: $("#rightArchiveId"),
  rightArchiveCode: $("#rightArchiveCode"),
  rightArchiveCertificateNo: $("#rightArchiveCertificateNo"),
  rightArchiveHolder: $("#rightArchiveHolder"),
  rightArchiveCertificateType: $("#rightArchiveCertificateType"),
  rightArchiveRightType: $("#rightArchiveRightType"),
  rightArchiveOwnershipType: $("#rightArchiveOwnershipType"),
  rightArchiveRightStart: $("#rightArchiveRightStart"),
  rightArchiveRightEnd: $("#rightArchiveRightEnd"),
  rightArchiveContractNo: $("#rightArchiveContractNo"),
  rightArchiveStatus: $("#rightArchiveStatus"),
  rightArchiveRegistrar: $("#rightArchiveRegistrar"),
  rightArchiveAreaMu: $("#rightArchiveAreaMu"),
  rightArchiveLinkedBlockCodes: $("#rightArchiveLinkedBlockCodes"),
  rightArchiveMissingItems: $("#rightArchiveMissingItems"),
  rightArchiveProperties: $("#rightArchiveProperties"),
  businessModuleSelect: $("#businessModuleSelect"),
  businessKeyword: $("#businessKeyword"),
  businessStatusFilter: $("#businessStatusFilter"),
  businessLinkedBlockFilter: $("#businessLinkedBlockFilter"),
  businessRowsAdmin: $("#businessRowsAdmin"),
  newBusinessRecord: $("#newBusinessRecord"),
  businessForm: $("#businessForm"),
  businessFormTitle: $("#businessFormTitle"),
  businessRecordId: $("#businessRecordId"),
  businessRecordCode: $("#businessRecordCode"),
  businessRecordName: $("#businessRecordName"),
  businessRecordStatus: $("#businessRecordStatus"),
  businessLinkedRightArchiveCodes: $("#businessLinkedRightArchiveCodes"),
  businessLinkedBlockCodes: $("#businessLinkedBlockCodes"),
  businessLayerFields: $("#businessLayerFields"),
  businessLayerType: $("#businessLayerType"),
  businessDataSource: $("#businessDataSource"),
  businessZIndex: $("#businessZIndex"),
  businessVisibleOnDashboard: $("#businessVisibleOnDashboard"),
  businessLayerStyle: $("#businessLayerStyle"),
  businessProperties: $("#businessProperties"),
  deleteBusinessRecord: $("#deleteBusinessRecord"),
  refreshSources: $("#refreshSources"),
  importSelectedSource: $("#importSelectedSource"),
  sourceStatus: $("#sourceStatus"),
  sourceRows: $("#sourceRows"),
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

function setSourceStatus(message) {
  elements.sourceStatus.textContent = message;
}

function buildHeaders(extraHeaders) {
  const headers = new Headers(extraHeaders || {});
  const roles = splitHeaderValues(elements.authRoles.value) || "admin";
  const areas = splitHeaderValues(elements.authAreas.value);
  const user = String(elements.authUser.value || "").trim();

  headers.set("X-RS-Roles", roles);
  if (areas) headers.set("X-RS-Areas", areas);
  if (user) headers.set("X-RS-User", user);
  return headers;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

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

function labelFor(group, value) {
  if (value === null || value === undefined || value === "") return "未填";
  return LABELS[group]?.[value] || String(value);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatArea(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "未填";
  return `${numeric.toFixed(numeric % 1 === 0 ? 0 : 1)} 亩`;
}

function formatBytes(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(numeric) / Math.log(1024)), units.length - 1);
  return `${(numeric / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDateTime(value) {
  if (!value) return "未填";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function locationOf(block) {
  return [block.countyName || block.countyCode, block.townName || block.townCode, block.villageName || block.villageCode]
    .filter(Boolean)
    .join(" / ");
}

function activeBlock() {
  return state.blocks.find((block) => String(block.id) === String(state.activeBlockId)) || null;
}

function activeRightArchive() {
  return state.rights.find((right) => String(right.id) === String(state.activeRightId)) || null;
}

function activeBusinessRecord() {
  return state.businessRecords.find((record) => String(record.id) === String(state.activeBusinessRecordId)) || null;
}

function selectedBusinessModule() {
  return elements.businessModuleSelect.value || "farmers";
}

function selectedBusinessConfig() {
  return ADMIN_BUSINESS_MODULES[selectedBusinessModule()] || ADMIN_BUSINESS_MODULES.farmers;
}

function activeBlockId() {
  return String(state.activeBlockId || elements.blockId.value || "").trim();
}

function findBlockById(blockId) {
  return state.blocks.find((block) => String(block.id) === String(blockId)) || null;
}

function rightsForBlock(block) {
  const blockCode = String(block?.blockCode || "");
  if (!blockCode) return [];
  return state.rights.filter((right) => (right.linkedBlockCodes || []).includes(blockCode));
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
  if (state.filters.keyword) query.set("q", state.filters.keyword);
  if (state.filters.baseType) query.set("baseType", state.filters.baseType);
  if (state.filters.operationType) query.set("operationType", state.filters.operationType);
  if (state.filters.riskLevel) query.set("riskLevel", state.filters.riskLevel);
  query.set("limit", "500");
  return query.toString();
}

function updateRightFilterState() {
  state.rightFilters.keyword = elements.rightKeyword.value.trim();
  state.rightFilters.archiveStatus = elements.rightArchiveStatusFilter.value;
  state.rightFilters.linkedBlockCode = elements.rightLinkedBlockFilter.value.trim();
}

function buildRightQueryString() {
  updateRightFilterState();
  const query = new URLSearchParams();
  if (state.rightFilters.keyword) query.set("q", state.rightFilters.keyword);
  if (state.rightFilters.archiveStatus) query.set("archiveStatus", state.rightFilters.archiveStatus);
  if (state.rightFilters.linkedBlockCode) query.set("linkedBlockCode", state.rightFilters.linkedBlockCode);
  query.set("limit", "500");
  return query.toString();
}

function updateBusinessFilterState() {
  state.businessFilters.keyword = elements.businessKeyword.value.trim();
  state.businessFilters.status = elements.businessStatusFilter.value.trim();
  state.businessFilters.linkedBlockCode = elements.businessLinkedBlockFilter.value.trim();
}

function buildBusinessQueryString() {
  updateBusinessFilterState();
  const query = new URLSearchParams();
  if (state.businessFilters.keyword) query.set("q", state.businessFilters.keyword);
  if (state.businessFilters.status) query.set("status", state.businessFilters.status);
  if (state.businessFilters.linkedBlockCode) query.set("linkedBlockCode", state.businessFilters.linkedBlockCode);
  query.set("limit", "500");
  return query.toString();
}

function renderMetrics(payload) {
  const total = Number(payload?.total ?? state.blocks.length);
  const area = state.blocks.reduce((sum, block) => {
    const value = Number(block.areaMu);
    return Number.isFinite(value) ? sum + value : sum;
  }, 0);
  const certified = state.rights.filter(
    (right) => right.archiveStatus === "complete" || Boolean(right.certificateNo)
  ).length;
  const missing = state.rights.filter((right) => right.archiveStatus !== "complete").length;

  elements.blockCount.textContent = String(total);
  elements.metricTotal.textContent = String(total);
  elements.metricArea.textContent = `${area.toFixed(area % 1 === 0 ? 0 : 1)} 亩`;
  elements.metricCertified.textContent = String(certified);
  elements.metricMissing.textContent = String(missing);
}

function renderBlockRows() {
  const rows = state.blocks;

  if (!rows.length) {
    elements.blockRows.innerHTML = `
      <tr class="placeholder-row">
        <td colspan="5">正式台账暂无记录。请从“成果入库”选择林班文件入库，或新建档案。</td>
      </tr>
    `;
    return;
  }

  elements.blockRows.innerHTML = rows
    .map((block) => {
      const linkedRights = rightsForBlock(block);
      const firstRight = linkedRights[0] || {};
      const isActive = String(block.id) === String(state.activeBlockId);
      const rightLabel = linkedRights.length ? `${linkedRights.length} 份档案` : "未挂接";
      const certificate = firstRight.certificateNo || firstRight.archiveCode || "-";
      return `
        <tr data-block-id="${escapeHtml(block.id)}" class="${isActive ? "active" : ""}">
          <td><div class="cell-stack"><strong>${escapeHtml(block.blockCode || "-")}</strong><small>${escapeHtml(block.name || "-")}</small></div></td>
          <td><div class="cell-stack"><strong>${escapeHtml(locationOf(block) || "-")}</strong><small>${escapeHtml(formatArea(block.areaMu))}</small></div></td>
          <td><div class="cell-stack"><strong>${escapeHtml(labelFor("operationType", block.operationType))}</strong><small>${escapeHtml(block.forestType || labelFor("baseType", block.baseType))}</small></div></td>
          <td><div class="cell-stack"><strong>${escapeHtml(rightLabel)}</strong><small>${escapeHtml(certificate)}</small></div></td>
          <td><div class="cell-stack"><span class="status-pill ${escapeHtml(block.geometry ? "complete" : "partial")}">${escapeHtml(block.geometry ? "有边界" : "待补图")}</span><small>风险 ${escapeHtml(labelFor("riskLevel", block.riskLevel))}</small></div></td>
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

function sceneLinkPlaceholder(message) {
  elements.linkedScenes.innerHTML = `<div class="scene-link-empty">${escapeHtml(message)}</div>`;
}

function setSceneLinkStatus(message) {
  elements.sceneLinkStatus.textContent = message;
}

function setSceneLinkEnabled(enabled) {
  elements.linkScene.disabled = !enabled;
  [
    elements.sceneLinkSceneId,
    elements.sceneLinkRelationType,
    elements.sceneLinkCapturedAt,
    elements.sceneLinkConfidence,
  ].forEach((element) => {
    element.disabled = !enabled;
  });
}

function resetSceneLinkInputs() {
  elements.sceneLinkSceneId.value = "";
  elements.sceneLinkRelationType.value = elements.sceneLinkRelationType.value.trim() || "coverage";
  elements.sceneLinkCapturedAt.value = "";
  elements.sceneLinkConfidence.value = "";
}

function renderSceneLinks(items) {
  if (!items.length) {
    sceneLinkPlaceholder("当前林班还没有关联影像。");
    return;
  }

  elements.linkedScenes.innerHTML = items
    .map((item) => {
      const meta = [
        item.relationType || "coverage",
        item.capturedAt ? `采集 ${item.capturedAt}` : "",
        item.confidence === null || item.confidence === undefined ? "" : `置信度 ${item.confidence}`,
      ]
        .filter(Boolean)
        .join(" · ");
      return `
        <article class="scene-link-item">
          <div>
            <strong>${escapeHtml(item.sceneId || "-")}</strong>
            <p>${escapeHtml(meta || "已关联")}</p>
          </div>
          <button
            type="button"
            class="button-ghost scene-link-remove"
            data-scene-id="${escapeHtml(item.sceneId || "")}"
            data-relation-type="${escapeHtml(item.relationType || "")}"
          >
            移除
          </button>
        </article>
      `;
    })
    .join("");
}

async function loadSceneLinks(block) {
  if (!block?.id) {
    setSceneLinkEnabled(false);
    setSceneLinkStatus("请选择一个林班");
    sceneLinkPlaceholder("请选择一个林班后查看关联影像。");
    return null;
  }

  setSceneLinkEnabled(true);
  setSceneLinkStatus("正在加载");

  try {
    const payload = await api(`/api/forest-blocks/${encodeURIComponent(block.id)}/scenes`);
    renderSceneLinks(Array.isArray(payload.items) ? payload.items : []);
    setSceneLinkStatus(`已加载 ${payload.total ?? 0} 条关联`);
    return payload;
  } catch (error) {
    sceneLinkPlaceholder(`关联影像加载失败：${error.message}`);
    setSceneLinkStatus("加载失败");
    return null;
  }
}

function populateForm(block) {
  const nextBlock = block || EMPTY_BLOCK;
  state.activeBlockId = nextBlock.id || "";
  elements.formTitle.textContent = nextBlock.id ? "编辑林班" : "新建林班";
  elements.blockId.value = nextBlock.id || "";
  elements.blockCode.value = nextBlock.blockCode || "";
  elements.blockCode.readOnly = Boolean(nextBlock.id);
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
  elements.tags.value = Array.isArray(nextBlock.tags) ? nextBlock.tags.join(", ") : "";
  elements.properties.value = stringifyPretty(nextBlock.properties, {});
  elements.geometry.value = stringifyPretty(nextBlock.geometry, null);
  renderBlockRows();
  loadSceneLinks(nextBlock).catch(() => {});
}

function resetForm() {
  populateForm(EMPTY_BLOCK);
}

function parseJsonField(label, value, fallback) {
  const text = String(value || "").trim();
  if (!text) return fallback;
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`${label} 不是合法 JSON`);
  }
}

function pruneEmptyValues(object) {
  return Object.fromEntries(Object.entries(object).filter(([, value]) => value !== "" && value !== null && value !== undefined));
}

function buildBlockPayload() {
  const properties = parseJsonField("附加属性", elements.properties.value, {});
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
    tags: splitHeaderValues(elements.tags.value)
      .split(",")
      .filter(Boolean),
    properties,
    geometry: parseJsonField("GeoJSON 几何", elements.geometry.value, null),
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
  setStatus("busy", "正在加载正式林班与林权档案台账...");

  try {
    const payload = await api(`/api/forest-blocks?${queryString}`);
    state.blocks = Array.isArray(payload.items) ? payload.items : [];
    state.totalBlocks = Number(payload.total ?? state.blocks.length);

    const hiddenActiveBlock = Boolean(state.activeBlockId) && !activeBlock();
    if (hiddenActiveBlock) resetForm();

    renderMetrics(payload);
    renderBlockRows();
    if (state.activeBlockId) {
      populateForm(activeBlock());
    } else if (!elements.blockCode.value && !elements.blockName.value) {
      resetForm();
    }

    setStatus("online", `已加载 ${payload.total ?? state.blocks.length} 条正式档案。`);
    return payload;
  } catch (error) {
    state.blocks = [];
    state.activeBlockId = "";
    renderMetrics({ total: 0 });
    renderBlockRows();
    setStatus("offline", `接口不可用：${error.message}`);
    return null;
  }
}

async function saveActiveBlock(event) {
  if (event && typeof event.preventDefault === "function") event.preventDefault();

  let payload;
  try {
    payload = buildBlockPayload();
  } catch (error) {
    setStatus("offline", error.message);
    throw error;
  }

  setStatus("busy", "正在保存林权档案...");
  const blockId = elements.blockId.value.trim();
  const request = buildSaveRequest(payload, blockId);

  try {
    const saved = await api(request.path, {
      method: request.method,
      body: request.body,
    });

    await loadBlocks();
    const visibleSavedBlock = findBlockById(saved.id);
    if (visibleSavedBlock) {
      populateForm(visibleSavedBlock);
      setStatus("online", `已保存档案 ${saved.blockCode || saved.name || ""}`.trim());
    } else {
      resetForm();
      setStatus("warning", `已保存，但当前筛选下不可见：${saved.blockCode || saved.name || ""}`.trim());
    }
    return saved;
  } catch (error) {
    setStatus("offline", `保存失败：${error.message}`);
    throw error;
  }
}

function renderRightRows() {
  const rows = state.rights;
  if (!rows.length) {
    elements.rightRows.innerHTML = `
      <tr class="placeholder-row">
        <td colspan="5">暂无林权档案。可从导入自动生成，或在右侧新建。</td>
      </tr>
    `;
    return;
  }

  elements.rightRows.innerHTML = rows
    .map((right) => {
      const isActive = String(right.id) === String(state.activeRightId);
      const linkedCodes = right.linkedBlockCodes || [];
      return `
        <tr data-right-id="${escapeHtml(right.id)}" class="${isActive ? "active" : ""}">
          <td><div class="cell-stack"><strong>${escapeHtml(right.archiveCode || "-")}</strong><small>${escapeHtml(right.contractNo || "-")}</small></div></td>
          <td><div class="cell-stack"><strong>${escapeHtml(right.holder || "-")}</strong><small>${escapeHtml(right.rightType || right.ownershipType || "-")}</small></div></td>
          <td><div class="cell-stack"><strong>${escapeHtml(right.certificateNo || "-")}</strong><small>${escapeHtml(right.rightEnd || "未填期限")}</small></div></td>
          <td><div class="cell-stack"><strong>${escapeHtml(linkedCodes.length ? `${linkedCodes.length} 个林班` : "未挂接")}</strong><small>${escapeHtml(linkedCodes.slice(0, 2).join(", ") || "-")}</small></div></td>
          <td><span class="status-pill ${escapeHtml(right.archiveStatus || "partial")}">${escapeHtml(labelFor("archiveStatus", right.archiveStatus || "partial"))}</span></td>
        </tr>
      `;
    })
    .join("");
}

function populateRightForm(right) {
  const nextRight = right || EMPTY_RIGHT_ARCHIVE;
  state.activeRightId = nextRight.id || "";
  elements.rightFormTitle.textContent = nextRight.id ? "编辑林权档案" : "新建林权档案";
  elements.rightArchiveId.value = nextRight.id || "";
  elements.rightArchiveCode.value = nextRight.archiveCode || "";
  elements.rightArchiveCertificateNo.value = nextRight.certificateNo || "";
  elements.rightArchiveHolder.value = nextRight.holder || "";
  elements.rightArchiveCertificateType.value = nextRight.certificateType || "";
  elements.rightArchiveRightType.value = nextRight.rightType || "";
  elements.rightArchiveOwnershipType.value = nextRight.ownershipType || "";
  elements.rightArchiveRightStart.value = nextRight.rightStart || "";
  elements.rightArchiveRightEnd.value = nextRight.rightEnd || "";
  elements.rightArchiveContractNo.value = nextRight.contractNo || "";
  elements.rightArchiveStatus.value = nextRight.archiveStatus || "partial";
  elements.rightArchiveRegistrar.value = nextRight.registrar || "";
  elements.rightArchiveAreaMu.value = nextRight.areaMu ?? "";
  elements.rightArchiveLinkedBlockCodes.value = Array.isArray(nextRight.linkedBlockCodes)
    ? nextRight.linkedBlockCodes.join(", ")
    : "";
  elements.rightArchiveMissingItems.value = nextRight.missingItems || "";
  elements.rightArchiveProperties.value = stringifyPretty(nextRight.properties, {});
  renderRightRows();
  renderBlockRows();
}

function resetRightForm() {
  populateRightForm(EMPTY_RIGHT_ARCHIVE);
}

function buildRightPayload() {
  const linkedBlockCodes = splitHeaderValues(elements.rightArchiveLinkedBlockCodes.value)
    .split(",")
    .filter(Boolean);
  const certificateNo = elements.rightArchiveCertificateNo.value.trim();
  const contractNo = elements.rightArchiveContractNo.value.trim();
  const archiveCode =
    elements.rightArchiveCode.value.trim() ||
    certificateNo ||
    contractNo ||
    (linkedBlockCodes[0] ? `RIGHT-${linkedBlockCodes[0]}` : "");
  return {
    archiveCode,
    certificateNo: certificateNo || null,
    holder: elements.rightArchiveHolder.value.trim(),
    certificateType: elements.rightArchiveCertificateType.value.trim() || null,
    rightType: elements.rightArchiveRightType.value.trim() || null,
    ownershipType: elements.rightArchiveOwnershipType.value.trim() || null,
    rightStart: elements.rightArchiveRightStart.value || null,
    rightEnd: elements.rightArchiveRightEnd.value || null,
    contractNo: contractNo || null,
    archiveStatus: elements.rightArchiveStatus.value || "partial",
    registrar: elements.rightArchiveRegistrar.value.trim() || null,
    areaMu: elements.rightArchiveAreaMu.value ? Number(elements.rightArchiveAreaMu.value) : null,
    linkedBlockCodes,
    missingItems: elements.rightArchiveMissingItems.value.trim() || null,
    properties: parseJsonField("档案扩展 JSON", elements.rightArchiveProperties.value, {}),
  };
}

function buildRightSaveRequest(payload, rightId) {
  if (!rightId) {
    return {
      method: "POST",
      path: "/api/forest-rights",
      body: JSON.stringify(payload),
    };
  }
  return {
    method: "PATCH",
    path: `/api/forest-rights/${encodeURIComponent(rightId)}`,
    body: JSON.stringify(payload),
  };
}

async function loadRights() {
  const queryString = buildRightQueryString();
  try {
    const payload = await api(`/api/forest-rights?${queryString}`);
    state.rights = Array.isArray(payload.items) ? payload.items : [];
    state.totalRights = Number(payload.total ?? state.rights.length);
    if (state.activeRightId && !activeRightArchive()) resetRightForm();
    renderRightRows();
    renderBlockRows();
    renderMetrics({ total: state.totalBlocks });
    return payload;
  } catch (error) {
    state.rights = [];
    state.totalRights = 0;
    renderRightRows();
    renderBlockRows();
    setStatus("offline", `林权档案接口不可用：${error.message}`);
    return null;
  }
}

async function saveActiveRight(event) {
  if (event && typeof event.preventDefault === "function") event.preventDefault();
  let payload;
  try {
    payload = buildRightPayload();
  } catch (error) {
    setStatus("offline", error.message);
    throw error;
  }

  setStatus("busy", "正在保存林权档案...");
  const request = buildRightSaveRequest(payload, elements.rightArchiveId.value.trim());
  try {
    const saved = await api(request.path, {
      method: request.method,
      body: request.body,
    });
    await loadRights();
    const visibleSavedRight = state.rights.find((right) => String(right.id) === String(saved.id));
    populateRightForm(visibleSavedRight || saved);
    setStatus("online", `已保存林权档案 ${saved.archiveCode || saved.certificateNo || ""}`.trim());
    return saved;
  } catch (error) {
    setStatus("offline", `林权档案保存失败：${error.message}`);
    throw error;
  }
}

function renderBusinessAdminRows() {
  const rows = state.businessRecords;
  if (!rows.length) {
    elements.businessRowsAdmin.innerHTML = `
      <tr class="placeholder-row">
        <td colspan="5">当前模块暂无后台记录。新建后才会发布到大屏业务卡片。</td>
      </tr>
    `;
    return;
  }

  elements.businessRowsAdmin.innerHTML = rows
    .map((record) => {
      const isActive = String(record.id) === String(state.activeBusinessRecordId);
      const linkedCodes = record.linkedBlockCodes || [];
      return `
        <tr data-business-record-id="${escapeHtml(record.id)}" class="${isActive ? "active" : ""}">
          <td><div class="cell-stack"><strong>${escapeHtml(record.recordCode || "-")}</strong><small>${escapeHtml(selectedBusinessConfig().label)}</small></div></td>
          <td><div class="cell-stack"><strong>${escapeHtml(record.name || "-")}</strong><small>${escapeHtml(record.layerType || record.dataSource || "-")}</small></div></td>
          <td><div class="cell-stack"><strong>${escapeHtml(linkedCodes.length ? `${linkedCodes.length} 个林班` : "未挂接")}</strong><small>${escapeHtml(linkedCodes.slice(0, 2).join(", ") || "-")}</small></div></td>
          <td><span class="status-pill ${escapeHtml(record.status || "partial")}">${escapeHtml(record.status || "未填写")}</span></td>
          <td>${escapeHtml(formatDateTime(record.updatedAt))}</td>
        </tr>
      `;
    })
    .join("");
}

function setBusinessLayerFieldsVisible() {
  elements.businessLayerFields.hidden = !selectedBusinessConfig().layerModule;
}

function populateBusinessForm(record) {
  const nextRecord = record || EMPTY_BUSINESS_RECORD;
  state.activeBusinessRecordId = nextRecord.id || "";
  elements.businessFormTitle.textContent = nextRecord.id
    ? `编辑${selectedBusinessConfig().label}记录`
    : `新建${selectedBusinessConfig().label}记录`;
  elements.businessRecordId.value = nextRecord.id || "";
  elements.businessRecordCode.value = nextRecord.recordCode || "";
  elements.businessRecordName.value = nextRecord.name || "";
  elements.businessRecordStatus.value = nextRecord.status || "";
  elements.businessLinkedRightArchiveCodes.value = Array.isArray(nextRecord.linkedRightArchiveCodes)
    ? nextRecord.linkedRightArchiveCodes.join(", ")
    : "";
  elements.businessLinkedBlockCodes.value = Array.isArray(nextRecord.linkedBlockCodes)
    ? nextRecord.linkedBlockCodes.join(", ")
    : "";
  elements.businessLayerType.value = nextRecord.layerType || "";
  elements.businessDataSource.value = nextRecord.dataSource || "";
  elements.businessZIndex.value = nextRecord.zIndex ?? "";
  elements.businessVisibleOnDashboard.value = String(nextRecord.visibleOnDashboard !== false);
  elements.businessLayerStyle.value = stringifyPretty(nextRecord.style, {});
  elements.businessProperties.value = stringifyPretty(nextRecord.properties, {});
  elements.deleteBusinessRecord.disabled = !nextRecord.id;
  setBusinessLayerFieldsVisible();
  renderBusinessAdminRows();
}

function resetBusinessForm() {
  populateBusinessForm(EMPTY_BUSINESS_RECORD);
}

function buildBusinessPayload() {
  const payload = {
    recordCode: elements.businessRecordCode.value.trim() || null,
    name: elements.businessRecordName.value.trim(),
    status: elements.businessRecordStatus.value.trim() || "active",
    linkedBlockCodes: splitHeaderValues(elements.businessLinkedBlockCodes.value)
      .split(",")
      .filter(Boolean),
    linkedRightArchiveCodes: splitHeaderValues(elements.businessLinkedRightArchiveCodes.value)
      .split(",")
      .filter(Boolean),
    properties: parseJsonField("业务扩展 JSON", elements.businessProperties.value, {}),
  };

  if (selectedBusinessConfig().layerModule) {
    return {
      ...payload,
      layerType: elements.businessLayerType.value.trim() || null,
      dataSource: elements.businessDataSource.value.trim() || null,
      zIndex: elements.businessZIndex.value ? Number(elements.businessZIndex.value) : null,
      visibleOnDashboard: elements.businessVisibleOnDashboard.value === "true",
      style: parseJsonField("图层样式 JSON", elements.businessLayerStyle.value, {}),
      status: payload.status || "published",
    };
  }

  return payload;
}

function businessSaveRequest(payload, recordId) {
  const endpoint = selectedBusinessConfig().endpoint;
  if (!recordId) {
    return { method: "POST", path: endpoint, body: JSON.stringify(payload) };
  }
  return { method: "PATCH", path: `${endpoint}/${encodeURIComponent(recordId)}`, body: JSON.stringify(payload) };
}

async function loadBusinessRecords() {
  const queryString = buildBusinessQueryString();
  const endpoint = selectedBusinessConfig().endpoint;
  try {
    const payload = await api(`${endpoint}?${queryString}`);
    state.businessRecords = Array.isArray(payload.items) ? payload.items : [];
    state.totalBusinessRecords = Number(payload.total ?? state.businessRecords.length);
    if (state.activeBusinessRecordId && !activeBusinessRecord()) resetBusinessForm();
    renderBusinessAdminRows();
    setBusinessLayerFieldsVisible();
    return payload;
  } catch (error) {
    state.businessRecords = [];
    state.totalBusinessRecords = 0;
    renderBusinessAdminRows();
    setStatus("offline", `业务模块接口不可用：${error.message}`);
    return null;
  }
}

async function saveActiveBusinessRecord(event) {
  if (event && typeof event.preventDefault === "function") event.preventDefault();
  let payload;
  try {
    payload = buildBusinessPayload();
  } catch (error) {
    setStatus("offline", error.message);
    throw error;
  }
  setStatus("busy", `正在保存${selectedBusinessConfig().label}记录...`);
  const request = businessSaveRequest(payload, elements.businessRecordId.value.trim());
  try {
    const saved = await api(request.path, { method: request.method, body: request.body });
    await loadBusinessRecords();
    const visible = state.businessRecords.find((record) => String(record.id) === String(saved.id));
    populateBusinessForm(visible || saved);
    setStatus("online", `已保存${selectedBusinessConfig().label}记录 ${saved.recordCode || saved.name || ""}`.trim());
    return saved;
  } catch (error) {
    setStatus("offline", `业务记录保存失败：${error.message}`);
    throw error;
  }
}

async function deleteActiveBusinessRecord() {
  const recordId = elements.businessRecordId.value.trim();
  if (!recordId) return null;
  setStatus("busy", `正在删除${selectedBusinessConfig().label}记录...`);
  try {
    const deleted = await api(`${selectedBusinessConfig().endpoint}/${encodeURIComponent(recordId)}`, { method: "DELETE" });
    resetBusinessForm();
    await loadBusinessRecords();
    setStatus("online", "业务记录已删除");
    return deleted;
  } catch (error) {
    setStatus("offline", `业务记录删除失败：${error.message}`);
    throw error;
  }
}

function renderImportMetrics(report) {
  const nextReport = report || {};
  elements.reportTotal.textContent = String(nextReport.totalRows || 0);
  elements.reportValid.textContent = String(nextReport.validRows || 0);
  elements.reportInvalid.textContent = String(nextReport.invalidRows || 0);
  elements.reportStatus.textContent = String(nextReport.status || "未执行");
}

function renderImportReport(report) {
  renderImportMetrics(report);
  elements.importReport.textContent = report ? JSON.stringify(report, null, 2) : "等待导入结果";
}

function renderSources() {
  if (!state.sources.length) {
    elements.sourceRows.innerHTML = `
      <tr class="placeholder-row">
        <td colspan="5">没有发现可入库的 GeoJSON / CSV / XLSX / ZIP / KML / KMZ / OVKML / OVOBJ 成果。</td>
      </tr>
    `;
    return;
  }

  elements.sourceRows.innerHTML = state.sources
    .map((source) => {
      const isActive = source.path === state.selectedSourcePath;
      return `
        <tr data-source-path="${escapeHtml(source.path)}" class="${isActive ? "active" : ""}">
          <td><strong>${escapeHtml(source.fileName || source.name || "-")}</strong></td>
          <td>${escapeHtml(source.fileType || "-")}</td>
          <td>${escapeHtml(formatBytes(source.sizeBytes))}</td>
          <td>${escapeHtml(formatDateTime(source.updatedAt))}</td>
          <td>${escapeHtml(source.path || "-")}</td>
        </tr>
      `;
    })
    .join("");
}

async function loadImportSources() {
  setSourceStatus("正在扫描 converted-data、samples 与 inbox...");
  try {
    const payload = await api("/api/imports/forest-blocks/sources");
    state.sources = Array.isArray(payload.items) ? payload.items : [];
    if (!state.sources.some((item) => item.path === state.selectedSourcePath)) {
      state.selectedSourcePath = state.sources[0]?.path || "";
    }
    renderSources();
    setSourceStatus(`发现 ${payload.total ?? state.sources.length} 个可入库成果。`);
    return payload;
  } catch (error) {
    state.sources = [];
    state.selectedSourcePath = "";
    renderSources();
    setSourceStatus(`数据源扫描失败：${error.message}`);
    return null;
  }
}

async function importSelectedSource() {
  if (!state.selectedSourcePath) {
    setSourceStatus("请先选择一个可入库成果。");
    return null;
  }

  setStatus("busy", "正在将转换成果写入正式林班台账...");
  setSourceStatus(`正在入库：${state.selectedSourcePath}`);
  try {
    const payload = await api("/api/imports/forest-blocks/sources/import", {
      method: "POST",
      body: JSON.stringify({
        path: state.selectedSourcePath,
        strategy: elements.importStrategy.value,
      }),
    });
    const report = payload.report || payload;
    renderImportReport(report);
    state.lastImportLabel = `${report.fileName || state.selectedSourcePath} / ${report.status || "completed"}`;
    elements.lastImport.textContent = state.lastImportLabel;
    await loadBlocks();
    await loadRights();
    const hasValidationErrors = Number(report.invalidRows || 0) > 0;
    setStatus(
      hasValidationErrors ? "warning" : "online",
      hasValidationErrors
        ? `成果已处理，但有 ${report.invalidRows} 行未通过校验。`
        : `成果入库完成，共处理 ${report.totalRows || 0} 行。`
    );
    setSourceStatus(`入库完成：${report.fileName || state.selectedSourcePath}`);
    return payload;
  } catch (error) {
    setStatus("offline", `成果入库失败：${error.message}`);
    setSourceStatus(`成果入库失败：${error.message}`);
    throw error;
  }
}

function combineImportReports(reports, failures, totalFiles) {
  if (reports.length === 1 && failures.length === 0) return reports[0];
  const totalRows = reports.reduce((sum, report) => sum + Number(report.totalRows || 0), 0);
  const validRows = reports.reduce((sum, report) => sum + Number(report.validRows || 0), 0);
  const invalidRows =
    reports.reduce((sum, report) => sum + Number(report.invalidRows || 0), 0) + failures.length;
  return {
    id: "multi-file-import",
    fileName: `${reports.length}/${totalFiles} 个文件`,
    fileType: "multi",
    status: failures.length ? "partial" : "completed",
    totalRows,
    validRows,
    invalidRows,
    errors: [
      ...reports.flatMap((report) =>
        (report.errors || []).map((error) => ({
          file: report.fileName,
          row: error.row,
          message: error.message,
        }))
      ),
      ...failures.map((failure) => ({
        file: failure.fileName,
        message: failure.message,
      })),
    ],
  };
}

async function uploadForestBlockFile(file) {
  const formData = new FormData();
  formData.set("file", file);
  formData.set("strategy", elements.importStrategy.value);
  const payload = await api("/api/imports/forest-blocks", {
    method: "POST",
    body: formData,
  });
  return payload.report || payload;
}

async function importForestBlocks(event) {
  if (event && typeof event.preventDefault === "function") event.preventDefault();

  const files = Array.from(elements.importFile.files || []);
  if (!files.length) {
    const error = new Error("请选择导入文件");
    setStatus("offline", error.message);
    throw error;
  }

  setStatus("busy", files.length === 1 ? `正在导入 ${files[0].name}...` : `正在导入 ${files.length} 个文件...`);

  const reports = [];
  const failures = [];
  for (const file of files) {
    try {
      reports.push(await uploadForestBlockFile(file));
    } catch (error) {
      failures.push({ fileName: file.name, message: error.message });
    }
  }

  const report = combineImportReports(reports, failures, files.length);
  renderImportReport(report);
  state.lastImportLabel = `${report.fileName || files[0].name} / ${report.status || "completed"}`;
  elements.lastImport.textContent = state.lastImportLabel;
  await loadBlocks();
  await loadRights();

  if (failures.length === files.length) {
    elements.importReport.textContent = `导入失败\n${JSON.stringify(report, null, 2)}`;
    setStatus("offline", `导入失败：${failures[0]?.message || "全部文件未导入"}`);
    return report;
  }

  const hasValidationErrors = Number(report.invalidRows || 0) > 0;
  setStatus(
    hasValidationErrors ? "warning" : "online",
    hasValidationErrors
      ? `导入完成，存在校验错误：${report.invalidRows} 行或文件未通过。`
      : `导入完成，共处理 ${report.totalRows || 0} 行。`
  );
  return report;
}

async function linkSceneToActive() {
  const blockId = activeBlockId();
  const sceneId = elements.sceneLinkSceneId.value.trim();
  if (!blockId) {
    setSceneLinkStatus("请先保存并选中一个林班");
    return null;
  }
  if (!sceneId) {
    setSceneLinkStatus("请输入 Scene ID");
    elements.sceneLinkSceneId.focus();
    return null;
  }

  const relationType = elements.sceneLinkRelationType.value.trim() || "coverage";
  const confidenceText = elements.sceneLinkConfidence.value.trim();
  const payload = {
    sceneId,
    relationType,
    capturedAt: elements.sceneLinkCapturedAt.value || null,
    confidence: confidenceText ? Number(confidenceText) : null,
  };

  setSceneLinkStatus("正在关联");
  await api(`/api/forest-blocks/${encodeURIComponent(blockId)}/scenes`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  resetSceneLinkInputs();
  elements.sceneLinkRelationType.value = relationType;
  await loadSceneLinks(activeBlock() || { id: blockId });
  setSceneLinkStatus("关联成功");
  return true;
}

async function removeSceneLink(sceneId, relationType) {
  const blockId = activeBlockId();
  if (!blockId || !sceneId) return null;

  const query = new URLSearchParams();
  if (relationType) query.set("relationType", relationType);

  setSceneLinkStatus("正在移除");
  await api(
    `/api/forest-blocks/${encodeURIComponent(blockId)}/scenes/${encodeURIComponent(sceneId)}${
      query.toString() ? `?${query.toString()}` : ""
    }`,
    { method: "DELETE" }
  );
  await loadSceneLinks(activeBlock() || { id: blockId });
  setSceneLinkStatus("已移除关联");
  return true;
}

function attachEvents() {
  elements.connectApi.addEventListener("click", () => {
    loadBlocks();
    loadRights();
    loadBusinessRecords();
    loadImportSources();
  });
  elements.reloadBlocks.addEventListener("click", loadBlocks);
  elements.newBlock.addEventListener("click", resetForm);
  elements.blockForm.addEventListener("submit", saveActiveBlock);
  elements.newRightArchive.addEventListener("click", resetRightForm);
  elements.rightForm.addEventListener("submit", saveActiveRight);
  elements.newBusinessRecord.addEventListener("click", resetBusinessForm);
  elements.businessForm.addEventListener("submit", saveActiveBusinessRecord);
  elements.deleteBusinessRecord.addEventListener("click", () => {
    deleteActiveBusinessRecord().catch(() => {});
  });
  elements.importForm.addEventListener("submit", importForestBlocks);
  elements.refreshSources.addEventListener("click", loadImportSources);
  elements.importSelectedSource.addEventListener("click", () => {
    importSelectedSource().catch(() => {});
  });

  [
    elements.baseTypeFilter,
    elements.operationTypeFilter,
    elements.riskLevelFilter,
  ].forEach((element) => {
    element.addEventListener("change", loadBlocks);
  });

  elements.keyword.addEventListener("input", () => {
    window.clearTimeout(keywordTimer);
    keywordTimer = window.setTimeout(loadBlocks, 220);
  });

  [
    elements.rightArchiveStatusFilter,
    elements.rightLinkedBlockFilter,
  ].forEach((element) => {
    element.addEventListener("change", loadRights);
  });

  elements.rightKeyword.addEventListener("input", () => {
    window.clearTimeout(keywordTimer);
    keywordTimer = window.setTimeout(loadRights, 220);
  });

  elements.businessModuleSelect.addEventListener("change", () => {
    state.activeBusinessRecordId = "";
    resetBusinessForm();
    loadBusinessRecords();
  });

  [
    elements.businessStatusFilter,
    elements.businessLinkedBlockFilter,
  ].forEach((element) => {
    element.addEventListener("change", loadBusinessRecords);
  });

  elements.businessKeyword.addEventListener("input", () => {
    window.clearTimeout(keywordTimer);
    keywordTimer = window.setTimeout(loadBusinessRecords, 220);
  });

  elements.blockRows.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-block-id]");
    if (!row) return;
    state.activeBlockId = row.getAttribute("data-block-id") || "";
    populateForm(activeBlock());
  });

  elements.rightRows.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-right-id]");
    if (!row) return;
    state.activeRightId = row.getAttribute("data-right-id") || "";
    populateRightForm(activeRightArchive());
  });

  elements.businessRowsAdmin.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-business-record-id]");
    if (!row) return;
    state.activeBusinessRecordId = row.getAttribute("data-business-record-id") || "";
    populateBusinessForm(activeBusinessRecord());
  });

  elements.sourceRows.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-source-path]");
    if (!row) return;
    state.selectedSourcePath = row.getAttribute("data-source-path") || "";
    renderSources();
    setSourceStatus(`已选择：${state.selectedSourcePath}`);
  });

  elements.linkScene.addEventListener("click", () => {
    linkSceneToActive().catch((error) => {
      setSceneLinkStatus(`关联失败：${error.message}`);
    });
  });

  elements.linkedScenes.addEventListener("click", (event) => {
    const button = event.target.closest(".scene-link-remove");
    if (!button) return;
    removeSceneLink(button.dataset.sceneId || "", button.dataset.relationType || "").catch((error) => {
      setSceneLinkStatus(`移除失败：${error.message}`);
    });
  });
}

function initialize() {
  attachEvents();
  renderImportReport(null);
  resetForm();
  resetRightForm();
  resetBusinessForm();
  loadBlocks();
  loadRights();
  loadBusinessRecords();
  loadImportSources();
}

window.SmartBambooAdmin = {
  loadBlocks,
  loadRights,
  loadBusinessRecords,
  loadImportSources,
  saveActiveBlock,
  saveActiveRight,
  saveActiveBusinessRecord,
  importForestBlocks,
  importSelectedSource,
};

initialize();
