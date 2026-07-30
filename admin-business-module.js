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
    rowActionButtons,
    setStatus,
    splitValues,
    stringifyPretty,
  } = AdminCommon;
  const {
    bindDictionarySelect,
    bindReferencePicker,
  } = AdminSmartFields;

  const body = document.body;
  const endpoint = body.dataset.businessEndpoint;
  const title = body.dataset.businessTitle || "业务信息管理";
  const kind = body.dataset.businessKind || "业务记录";
  const pagePermission = body.dataset.permission || "";
  const moduleKey = body.dataset.adminModule || "";
  const endpointModuleKey = String(endpoint || "")
    .split("/")
    .filter(Boolean)
    .pop();
  const state = {
    records: [],
    businessEvents: [],
    fieldSchema: [],
    activeId: "",
    coreSmartControls: {},
    statusControl: null,
    linkedBlockPicker: null,
    linkedRightPicker: null,
  };
  let pager;
  let keywordTimer;
  let editorReturnFocus = null;
  let detailReturnFocus = null;
  const BUSINESS_CORE_FIELDS = {
    default: [
      { label: "类别", paths: ["businessType", "type", "properties.businessType", "properties.type", "payload.type"] },
      { label: "区域", paths: ["serviceArea", "region", "townName", "properties.serviceArea", "properties.region"] },
      { label: "负责人", paths: ["ownerName", "manager", "contactName", "properties.ownerName", "properties.manager"] },
    ],
    farmers: [
      { label: "村镇", paths: ["townVillage", "serviceArea", "townName", "properties.townVillage", "properties.serviceArea", "properties.townName"] },
      { label: "村", paths: ["villageName", "village", "properties.villageName", "properties.village"] },
      { label: "电话", paths: ["phone", "ownerPhone", "contactPhone", "properties.phone", "properties.ownerPhone"] },
      { label: "经营面积", paths: ["managedAreaMu", "areaMu", "area", "properties.managedAreaMu", "properties.areaMu"] },
    ],
    cooperatives: [
      { label: "服务范围", paths: ["serviceArea", "townVillage", "region", "properties.serviceArea", "properties.region"] },
      { label: "成员", paths: ["memberCount", "members", "properties.memberCount", "properties.members"] },
      { label: "托管林班", paths: ["managedBlockCount", "trustBlockCount", "properties.managedBlockCount", "properties.trustBlockCount"] },
      { label: "订单", paths: ["orderStatus", "serviceStatus", "properties.orderStatus", "properties.serviceStatus"] },
    ],
    enterprises: [
      { label: "主营方向", paths: ["mainBusiness", "businessType", "processingDirection", "properties.mainBusiness", "properties.processingDirection"] },
      { label: "采购批次", paths: ["purchaseBatch", "purchaseBatchNo", "properties.purchaseBatch", "properties.purchaseBatchNo"] },
      { label: "库存", paths: ["inventoryStatus", "stockStatus", "stock", "properties.inventoryStatus", "properties.stockStatus"] },
      { label: "联系人", paths: ["contactName", "manager", "properties.contactName", "properties.manager"] },
    ],
    plantProtection: [
      { label: "问题类型", paths: ["eventType", "pestType", "diseaseType", "properties.eventType", "properties.pestType"] },
      { label: "等级", paths: ["level", "riskLevel", "severity", "properties.level", "properties.riskLevel"] },
      { label: "位置", paths: ["location", "townVillage", "properties.location", "properties.townVillage"] },
      { label: "闭环", paths: ["closureStatus", "disposalStatus", "status", "properties.closureStatus", "properties.disposalStatus"] },
    ],
    materials: [
      { label: "品类", paths: ["materialType", "category", "type", "properties.materialType", "properties.category"] },
      { label: "库存", paths: ["stock", "inventory", "stockQuantity", "properties.stock", "properties.inventory"] },
      { label: "适用环节", paths: ["usageStage", "applyStage", "properties.usageStage", "properties.applyStage"] },
      { label: "预警", paths: ["warningStatus", "stockWarning", "properties.warningStatus", "properties.stockWarning"] },
    ],
    policies: [
      { label: "适用对象", paths: ["target", "applicableObject", "properties.target", "properties.applicableObject"] },
      { label: "申报事项", paths: ["applicationItem", "projectItem", "properties.applicationItem", "properties.projectItem"] },
      { label: "截止时间", paths: ["deadline", "dueDate", "properties.deadline", "properties.dueDate"] },
      { label: "审核", paths: ["reviewStatus", "approvalStatus", "status", "properties.reviewStatus", "properties.approvalStatus"] },
    ],
    stewardshipAgreements: [
      { label: "托管主体", paths: ["operator", "serviceProvider", "ownerName", "properties.operator", "properties.serviceProvider"] },
      { label: "期限", paths: ["term", "contractTerm", "expiresAt", "properties.term", "properties.contractTerm"] },
      { label: "面积", paths: ["areaMu", "managedAreaMu", "properties.areaMu", "properties.managedAreaMu"] },
      { label: "履约", paths: ["performanceStatus", "status", "properties.performanceStatus"] },
    ],
    franchiseBases: [
      { label: "区域", paths: ["region", "serviceArea", "townVillage", "properties.region", "properties.serviceArea"] },
      { label: "主体", paths: ["operator", "ownerName", "enterpriseName", "properties.operator", "properties.ownerName"] },
      { label: "面积", paths: ["areaMu", "baseAreaMu", "properties.areaMu", "properties.baseAreaMu"] },
      { label: "等级", paths: ["serviceLevel", "baseLevel", "properties.serviceLevel", "properties.baseLevel"] },
    ],
    maintenanceTasks: [
      { label: "任务类型", paths: ["taskType", "workType", "properties.taskType", "properties.workType"] },
      { label: "责任人", paths: ["assignee", "ownerName", "teamName", "properties.assignee", "properties.ownerName"] },
      { label: "计划时间", paths: ["plannedAt", "planDate", "deadline", "properties.plannedAt", "properties.planDate"] },
      { label: "闭环", paths: ["closureStatus", "status", "properties.closureStatus"] },
    ],
    workLogs: [
      { label: "作业环节", paths: ["workStage", "operationStage", "workType", "properties.workStage", "properties.operationStage"] },
      { label: "作业人", paths: ["worker", "teamName", "operator", "properties.worker", "properties.teamName"] },
      { label: "作业时间", paths: ["workDate", "startedAt", "properties.workDate", "properties.startedAt"] },
      { label: "用工", paths: ["laborCount", "workload", "properties.laborCount", "properties.workload"] },
    ],
    droneTasks: [
      { label: "任务类型", paths: ["taskType", "flightType", "properties.taskType", "properties.flightType"] },
      { label: "设备", paths: ["deviceCode", "droneCode", "properties.deviceCode", "properties.droneCode"] },
      { label: "航线", paths: ["routeName", "routeCode", "properties.routeName", "properties.routeCode"] },
      { label: "成果", paths: ["resultStatus", "sceneStatus", "properties.resultStatus", "properties.sceneStatus"] },
    ],
    equipment: [
      { label: "设备类型", paths: ["deviceType", "equipmentType", "properties.deviceType", "properties.equipmentType"] },
      { label: "编号", paths: ["deviceCode", "serialNo", "properties.deviceCode", "properties.serialNo"] },
      { label: "位置", paths: ["location", "installLocation", "properties.location", "properties.installLocation"] },
      { label: "运行", paths: ["onlineStatus", "runningStatus", "status", "properties.onlineStatus", "properties.runningStatus"] },
    ],
    pestWarnings: [
      { label: "风险类型", paths: ["riskType", "pestType", "eventType", "properties.riskType", "properties.pestType"] },
      { label: "等级", paths: ["riskLevel", "level", "severity", "properties.riskLevel", "properties.level"] },
      { label: "处置建议", paths: ["suggestion", "treatmentAdvice", "properties.suggestion", "properties.treatmentAdvice"] },
      { label: "复核", paths: ["reviewStatus", "status", "properties.reviewStatus"] },
    ],
    materialServices: [
      { label: "服务类型", paths: ["serviceType", "materialType", "properties.serviceType", "properties.materialType"] },
      { label: "供应商", paths: ["supplier", "provider", "properties.supplier", "properties.provider"] },
      { label: "配送", paths: ["deliveryStatus", "orderStatus", "properties.deliveryStatus", "properties.orderStatus"] },
      { label: "反馈", paths: ["feedbackStatus", "properties.feedbackStatus"] },
    ],
    yieldForecasts: [
      { label: "预测对象", paths: ["forecastObject", "productType", "properties.forecastObject", "properties.productType"] },
      { label: "周期", paths: ["forecastPeriod", "season", "properties.forecastPeriod", "properties.season"] },
      { label: "预测量", paths: ["forecastYield", "expectedYield", "properties.forecastYield", "properties.expectedYield"] },
      { label: "模型", paths: ["modelName", "modelVersion", "properties.modelName", "properties.modelVersion"] },
    ],
    harvestPlans: [
      { label: "采挖类型", paths: ["harvestType", "planType", "properties.harvestType", "properties.planType"] },
      { label: "计划时间", paths: ["plannedAt", "planDate", "properties.plannedAt", "properties.planDate"] },
      { label: "计划量", paths: ["plannedQuantity", "targetQuantity", "properties.plannedQuantity", "properties.targetQuantity"] },
      { label: "执行", paths: ["executionStatus", "status", "properties.executionStatus"] },
    ],
    incomeEstimates: [
      { label: "测算类型", paths: ["estimateType", "businessType", "properties.estimateType", "properties.businessType"] },
      { label: "周期", paths: ["estimatePeriod", "period", "properties.estimatePeriod", "properties.period"] },
      { label: "收益", paths: ["expectedIncome", "netIncome", "properties.expectedIncome", "properties.netIncome"] },
      { label: "成本", paths: ["cost", "inputCost", "properties.cost", "properties.inputCost"] },
    ],
    performanceDashboards: [
      { label: "指标类型", paths: ["metricType", "indicatorType", "properties.metricType", "properties.indicatorType"] },
      { label: "覆盖范围", paths: ["coverage", "serviceArea", "properties.coverage", "properties.serviceArea"] },
      { label: "口径", paths: ["caliber", "metricCaliber", "properties.caliber", "properties.metricCaliber"] },
      { label: "发布", paths: ["publishStatus", "status", "properties.publishStatus"] },
    ],
    carbonEstimates: [
      { label: "核算类型", paths: ["accountingType", "carbonType", "properties.accountingType", "properties.carbonType"] },
      { label: "边界", paths: ["projectBoundary", "boundary", "properties.projectBoundary", "properties.boundary"] },
      { label: "碳储量", paths: ["carbonStock", "carbonStorage", "properties.carbonStock", "properties.carbonStorage"] },
      { label: "核证", paths: ["verificationStatus", "status", "properties.verificationStatus"] },
    ],
    tradeMatches: [
      { label: "供需类型", paths: ["tradeType", "supplyDemandType", "properties.tradeType", "properties.supplyDemandType"] },
      { label: "品类", paths: ["productType", "category", "properties.productType", "properties.category"] },
      { label: "数量", paths: ["quantity", "volume", "properties.quantity", "properties.volume"] },
      { label: "撮合", paths: ["matchStatus", "status", "properties.matchStatus"] },
    ],
    logisticsTraces: [
      { label: "批次", paths: ["batchNo", "traceCode", "properties.batchNo", "properties.traceCode"] },
      { label: "承运", paths: ["carrier", "driver", "properties.carrier", "properties.driver"] },
      { label: "节点", paths: ["currentNode", "location", "properties.currentNode", "properties.location"] },
      { label: "物流", paths: ["logisticsStatus", "status", "properties.logisticsStatus"] },
    ],
    productQrcodes: [
      { label: "二维码", paths: ["qrCode", "traceCode", "properties.qrCode", "properties.traceCode"] },
      { label: "产品", paths: ["productType", "productName", "properties.productType", "properties.productName"] },
      { label: "批次", paths: ["batchNo", "properties.batchNo"] },
      { label: "发布", paths: ["publishStatus", "status", "properties.publishStatus"] },
    ],
    supplyChainFinance: [
      { label: "金融产品", paths: ["financeProduct", "loanProduct", "properties.financeProduct", "properties.loanProduct"] },
      { label: "主体", paths: ["borrower", "enterpriseName", "ownerName", "properties.borrower", "properties.enterpriseName"] },
      { label: "金额", paths: ["amount", "creditAmount", "properties.amount", "properties.creditAmount"] },
      { label: "审核", paths: ["reviewStatus", "approvalStatus", "status", "properties.reviewStatus"] },
    ],
    priceIndexes: [
      { label: "品类", paths: ["productType", "category", "properties.productType", "properties.category"] },
      { label: "区域", paths: ["region", "market", "properties.region", "properties.market"] },
      { label: "价格", paths: ["price", "indexValue", "properties.price", "properties.indexValue"] },
      { label: "周期", paths: ["period", "date", "properties.period", "properties.date"] },
    ],
    mobileServiceChannels: [
      { label: "服务对象", paths: ["target", "audience", "properties.target", "properties.audience"] },
      { label: "入口", paths: ["channel", "entry", "properties.channel", "properties.entry"] },
      { label: "负责人", paths: ["ownerName", "operator", "properties.ownerName", "properties.operator"] },
      { label: "上线", paths: ["publishStatus", "status", "properties.publishStatus"] },
    ],
  };
  const VIEW_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.8"></circle></svg>';
  const RESTORE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.4-6.4"></path><path d="M18 3v5h-5"></path><path d="M21 12a9 9 0 0 1-15.4 6.4"></path><path d="M6 21v-5h5"></path></svg>';
  const BUSINESS_EVENT_ACTION_LABELS = {
    create: "新建",
    update: "编辑",
    delete: "删除",
    restore: "恢复",
  };

  function hasCoreValue(value) {
    if (value === null || value === undefined) return false;
    if (Array.isArray(value)) return value.some((item) => hasCoreValue(item));
    if (typeof value === "string") return value.trim() !== "";
    return true;
  }

  function recordValueByPath(record, path) {
    if (!record || !path) return undefined;
    const pathText = String(path);
    if (!pathText.includes(".")) {
      if (hasCoreValue(record[pathText])) return record[pathText];
      if (hasCoreValue(record.properties?.[pathText])) return record.properties[pathText];
      if (hasCoreValue(record.payload?.[pathText])) return record.payload[pathText];
      return undefined;
    }
    return pathText.split(".").reduce((value, key) => {
      if (value === null || value === undefined) return undefined;
      return value[key];
    }, record);
  }

  function fieldPaths(field) {
    if (Array.isArray(field?.paths) && field.paths.length) return field.paths;
    return [field?.path || field?.key].filter(Boolean);
  }

  function formatCoreFieldValue(value) {
    if (!hasCoreValue(value)) return "";
    if (Array.isArray(value)) {
      return value
        .filter((item) => hasCoreValue(item))
        .map((item) => formatCoreFieldValue(item))
        .filter(Boolean)
        .join(", ");
    }
    if (typeof value === "object") {
      const named = value.label || value.name || value.value || value.title || value.code;
      return named ? String(named) : JSON.stringify(value);
    }
    return String(value).trim();
  }

  function coreFieldValue(record, field) {
    const paths = fieldPaths(field);
    for (const path of paths) {
      const value = formatCoreFieldValue(recordValueByPath(record, path));
      if (value) return value;
    }
    return "";
  }

  function coreFieldsForModule() {
    if (state.fieldSchema.length) return state.fieldSchema;
    return BUSINESS_CORE_FIELDS[moduleKey] || BUSINESS_CORE_FIELDS[endpointModuleKey] || BUSINESS_CORE_FIELDS.default;
  }

  function fieldPropertyKey(field) {
    const paths = fieldPaths(field);
    const propertyPath = paths.find((path) => String(path || "").startsWith("properties."));
    if (propertyPath) return String(propertyPath).slice("properties.".length).split(".")[0];
    const flatPath = paths.find((path) => path && !String(path).includes("."));
    return flatPath ? String(flatPath) : "";
  }

  function businessCorePropertyKeys() {
    return new Set(
      coreFieldsForModule()
        .flatMap((field) => {
          const paths = fieldPaths(field);
          return [field.key, ...paths]
            .filter(Boolean)
            .map((path) => String(path).startsWith("properties.") ? String(path).slice("properties.".length).split(".")[0] : String(path))
            .filter((key) => key && !key.includes("."));
        }),
    );
  }

  function editableCoreFields() {
    const seen = new Set();
    return coreFieldsForModule()
      .map((field) => ({ ...field, key: field.key || fieldPropertyKey(field) }))
      .filter((field) => {
        if (!field.key || seen.has(field.key)) return false;
        seen.add(field.key);
        return true;
      });
  }

  function renderCoreFields(record) {
    const fields = coreFieldsForModule();
    const chips = fields
      .map((field) => {
        const value = coreFieldValue(record, field);
        if (!value) return "";
        return `<span class="business-core-field"><b>${escapeHtml(field.label)}</b>${escapeHtml(value)}</span>`;
      })
      .filter(Boolean)
      .slice(0, 4);
    if (!chips.length) {
      return '<small class="business-core-fields business-core-empty">核心字段未填</small>';
    }
    return `<div class="business-core-fields">${chips.join("")}</div>`;
  }

  function ensureBusinessCoreFieldInputs() {
    if ($("#businessCoreFields")) return;
    const fields = editableCoreFields();
    const propertiesLabel = $("#businessProperties")?.closest("label");
    if (!fields.length || !propertiesLabel?.parentElement) return;
    const heading = document.createElement("div");
    heading.id = "businessCoreFields";
    heading.className = "business-core-form-heading field-span-2";
    heading.innerHTML = "<strong>模块核心字段</strong>";
    propertiesLabel.parentElement.insertBefore(heading, propertiesLabel);
    fields.forEach((field) => {
      const label = document.createElement("label");
      label.className = "business-core-field-input";
      const labelText = field.unit ? `${field.label}（${field.unit}）` : field.label;
      const required = field.required ? " required" : "";
      const readOnly = field.readOnly ? " readonly" : "";
      let control = "";
      if (field.inputType === "select") {
        const options = Array.isArray(field.options) ? field.options : [];
        control = `<select id="businessCoreField-${escapeHtml(field.key)}" data-business-core-field="${escapeHtml(field.key)}"${required}><option value="">请选择</option>${options
          .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label || option.value)}</option>`)
          .join("")}</select>`;
      } else if (field.inputType === "dictionary") {
        control = `<select id="businessCoreField-${escapeHtml(field.key)}" data-business-core-field="${escapeHtml(field.key)}"${required}><option value="">正在加载...</option></select>`;
      } else if (field.inputType === "reference" || field.inputType === "multi-reference") {
        control = `<input id="businessCoreField-${escapeHtml(field.key)}" data-business-core-field="${escapeHtml(field.key)}" type="text"${required} />`;
      } else if (field.inputType === "textarea") {
        control = `<textarea id="businessCoreField-${escapeHtml(field.key)}" data-business-core-field="${escapeHtml(field.key)}" rows="3"${required}${readOnly}></textarea>`;
      } else {
        const inputType = field.inputType === "number" || field.inputType === "integer"
          ? "number"
          : field.inputType === "date" || field.inputType === "datetime-local" || field.inputType === "month"
            ? field.inputType
            : "text";
        const step = field.step !== undefined ? ` step="${escapeHtml(field.step)}"` : field.inputType === "integer" ? ' step="1"' : "";
        const min = field.min !== undefined ? ` min="${escapeHtml(field.min)}"` : "";
        const max = field.max !== undefined ? ` max="${escapeHtml(field.max)}"` : "";
        control = `<input id="businessCoreField-${escapeHtml(field.key)}" data-business-core-field="${escapeHtml(field.key)}" type="${inputType}"${step}${min}${max}${required}${readOnly} />`;
      }
      label.innerHTML = `<span>${escapeHtml(labelText)}</span>${control}`;
      propertiesLabel.parentElement.insertBefore(label, propertiesLabel);
    });
  }

  function businessCoreInput(key) {
    return Array.from(document.querySelectorAll("[data-business-core-field]"))
      .find((input) => input.dataset.businessCoreField === key) || null;
  }

  async function setupSmartFields() {
    state.statusControl = bindDictionarySelect({
      element: $("#businessRecordStatus"),
      typeCode: "business-statuses",
      api,
      blankLabel: "请选择状态",
    });
    state.linkedBlockPicker = bindReferencePicker({
      input: $("#businessLinkedBlockCodes"),
      endpoint: "/api/forest-blocks",
      valueKey: "blockCode",
      labelKey: "name",
      api,
      placeholder: "搜索林班编号、名称或村镇",
    });
    state.linkedRightPicker = bindReferencePicker({
      input: $("#businessLinkedRightArchiveCodes"),
      endpoint: "/api/forest-rights",
      valueKey: "archiveCode",
      labelKey: "holder",
      api,
      placeholder: "搜索档案编号、证号或权利人",
    });
    editableCoreFields().forEach((field) => {
      const input = businessCoreInput(field.key);
      if (!input) return;
      if (field.inputType === "dictionary" && field.dictionaryCode) {
        state.coreSmartControls[field.key] = bindDictionarySelect({
          element: input,
          typeCode: field.dictionaryCode,
          query: field.dictionaryQuery || {},
          api,
          blankLabel: "请选择",
        });
      } else if (
        (field.inputType === "reference" || field.inputType === "multi-reference")
        && field.referenceEndpoint
      ) {
        state.coreSmartControls[field.key] = bindReferencePicker({
          input,
          endpoint: field.referenceEndpoint,
          valueKey: field.referenceValueKey || "recordCode",
          labelKey: field.referenceLabelKey || "name",
          api,
          multiple: field.inputType === "multi-reference",
          placeholder: `搜索${field.label}`,
        });
      }
    });
    await Promise.all([
      state.statusControl.ready,
      ...Object.values(state.coreSmartControls)
        .filter((control) => control.ready)
        .map((control) => control.ready),
    ]);
  }

  function fillBusinessCoreFields(record = {}) {
    ensureBusinessCoreFieldInputs();
    editableCoreFields().forEach((field) => {
      const input = businessCoreInput(field.key);
      if (!input) return;
      const value = coreFieldValue(record, field);
      const control = state.coreSmartControls[field.key];
      if (field.inputType === "dictionary" && control) {
        control.setValue(value);
      } else if ((field.inputType === "reference" || field.inputType === "multi-reference") && control) {
        control.setValues(field.inputType === "multi-reference" ? splitValues(value) : value ? [value] : []);
      } else {
        input.value = value;
      }
    });
  }

  function businessCoreFieldsFromForm() {
    return editableCoreFields().map((field) => {
      const input = businessCoreInput(field.key);
      return { ...field, value: parseBusinessCoreFieldValue(field, input?.value.trim() || "") };
    });
  }

  function parseBusinessCoreFieldValue(field, rawValue) {
    if (rawValue === "") return "";
    if (field.inputType === "integer") return Number.parseInt(rawValue, 10);
    if (field.inputType === "number") return Number(rawValue);
    if (field.inputType === "boolean") return rawValue === "true";
    if (field.inputType === "multi-reference") return splitValues(rawValue);
    return rawValue;
  }

  function mergeBusinessCoreFieldsIntoProperties(properties = {}) {
    const merged = { ...(properties || {}) };
    const coreKeys = businessCorePropertyKeys();
    coreKeys.forEach((key) => delete merged[key]);
    businessCoreFieldsFromForm().forEach((field) => {
      if (field.value !== "" && field.value !== null && field.value !== undefined) merged[field.key] = field.value;
    });
    return merged;
  }

  async function loadModuleFieldSchema() {
    try {
      const payload = await api("/api/business/modules");
      const modules = Array.isArray(payload.items) ? payload.items : [];
      const current = modules.find((item) => item.key === endpointModuleKey);
      state.fieldSchema = Array.isArray(current?.fieldSchema) ? current.fieldSchema : [];
    } catch (_error) {
      state.fieldSchema = [];
    }
  }

  function syncBusinessCoreFieldFilterInput() {
    const select = $("#businessCoreFieldFilter");
    const input = $("#businessCoreFieldValueFilter");
    if (!select || !input) return;
    const field = state.fieldSchema.find((item) => item.key === select.value);
    input.value = "";
    input.disabled = !field;
    input.type = field?.inputType === "number" || field?.inputType === "integer"
      ? "number"
      : field?.inputType === "date"
        ? "date"
        : "search";
    input.step = field?.step !== undefined ? String(field.step) : field?.inputType === "integer" ? "1" : "";
    input.placeholder = field ? `筛选${field.label}` : "先选择核心字段";
  }

  function ensureBusinessCoreFieldFilter() {
    if (!state.fieldSchema.length || $("#businessCoreFieldFilter")) return;
    const grid = $("#businessStatusFilter")?.closest(".field-grid");
    const keywordLabel = $("#businessKeyword")?.closest("label");
    if (!grid) return;
    const fieldLabel = document.createElement("label");
    fieldLabel.innerHTML = `<span>核心字段</span><select id="businessCoreFieldFilter"><option value="">全部字段</option>${state.fieldSchema
      .map((field) => `<option value="${escapeHtml(field.key)}">${escapeHtml(field.label)}</option>`)
      .join("")}</select>`;
    const valueLabel = document.createElement("label");
    valueLabel.innerHTML = '<span>字段值</span><input id="businessCoreFieldValueFilter" type="search" placeholder="先选择核心字段" disabled />';
    grid.insertBefore(fieldLabel, keywordLabel || null);
    grid.insertBefore(valueLabel, keywordLabel || null);
    $("#businessCoreFieldFilter").addEventListener("change", () => {
      syncBusinessCoreFieldFilterInput();
      reloadRecordsFromFirstPage();
    });
    $("#businessCoreFieldValueFilter").addEventListener("input", () => {
      window.clearTimeout(keywordTimer);
      keywordTimer = window.setTimeout(reloadRecordsFromFirstPage, 180);
    });
    syncBusinessCoreFieldFilterInput();
  }

  function activeRecord() {
    return state.records.find((record) => String(record.id) === String(state.activeId)) || null;
  }

  function businessPermission(action) {
    const base = pagePermission.endsWith(".view")
      ? pagePermission.slice(0, -".view".length)
      : pagePermission.endsWith(".manage")
        ? pagePermission.slice(0, -".manage".length)
        : pagePermission;
    return base ? `${base}.${action}` : "";
  }

  function ensureDeletedFilterToggle() {
    if ($("#includeDeletedBusinessRecords")) return;
    const userInput = $("#authUser");
    const grid = userInput?.closest(".field-grid");
    if (!grid) return;
    const label = document.createElement("label");
    label.className = "checkbox-field";
    label.innerHTML = `<span>显示已删除</span><input id="includeDeletedBusinessRecords" type="checkbox" data-permission="${businessPermission("restore")}" />`;
    grid.appendChild(label);
  }

  function ensureBusinessEventLedger() {
    if ($("#businessEventRows")) return;
    const main = $(".business-admin-main") || $(".admin-main");
    if (!main) return;
    const panel = document.createElement("section");
    panel.className = "panel table-panel business-event-panel";
    panel.innerHTML = `
      <div class="panel-header">
        <div>
          <p class="eyebrow">操作审计</p>
          <h2>${escapeHtml(kind)}操作台账</h2>
        </div>
        <div class="panel-actions">
          <button id="refreshBusinessEvents" type="button" class="button-ghost">刷新审计</button>
          <button id="exportBusinessEvents" type="button" class="button-ghost" data-permission="${businessPermission("export")}">导出 CSV</button>
        </div>
      </div>
      <div class="field-grid field-grid-wide filters-grid">
        <label><span>动作</span><select id="businessEventActionFilter"><option value="">全部</option><option value="create">新建</option><option value="update">编辑</option><option value="delete">删除</option><option value="restore">恢复</option></select></label>
        <label><span>记录编号</span><input id="businessEventRecordFilter" type="search" placeholder="recordCode" /></label>
        <label><span>关联林班</span><input id="businessEventLinkedBlockFilter" type="search" placeholder="林班编号" /></label>
        <label><span>关键词</span><input id="businessEventKeyword" type="search" placeholder="记录、操作人、字段" /></label>
      </div>
      <div class="table-wrap ledger-table-wrap business-event-table-wrap">
        <table>
          <thead><tr><th>动作</th><th>记录</th><th>操作人</th><th>关联林班</th><th>变更字段</th><th>时间</th></tr></thead>
          <tbody id="businessEventRows"><tr class="placeholder-row"><td colspan="6">等待加载操作审计</td></tr></tbody>
        </table>
      </div>
    `;
    main.appendChild(panel);
  }

  function isDeletedRecord(record) {
    return Boolean(record?.deletedAt);
  }

  function linkedTargetCount(record, kind = "blocks") {
    const propertyKey = kind === "blocks" ? "linkedBlockCount" : "linkedRightArchiveCount";
    const listKey = kind === "blocks" ? "linkedBlockCodes" : "linkedRightArchiveCodes";
    const propertyCount = Number(record?.properties?.[propertyKey]);
    return Number.isFinite(propertyCount) ? propertyCount : (Array.isArray(record?.[listKey]) ? record[listKey].length : 0);
  }

  function linkedTargetSummary(record, kind = "blocks") {
    const listKey = kind === "blocks" ? "linkedBlockCodes" : "linkedRightArchiveCodes";
    const values = Array.isArray(record?.[listKey]) ? record[listKey] : [];
    const total = linkedTargetCount(record, kind);
    if (!total) return "未挂接";
    const sample = values.slice(0, 8).join(", ");
    return `${total} 条${sample ? `：${sample}${total > values.length ? " ..." : ""}` : ""}`;
  }

  async function hydrateBusinessTargets(record) {
    if (!record?.id) return record;
    const recordId = encodeURIComponent(record.id);
    const [blocks, rights] = await Promise.all([
      api(`${endpoint}/${recordId}/targets?kind=blocks&limit=100&offset=0`),
      api(`${endpoint}/${recordId}/targets?kind=rights&limit=100&offset=0`),
    ]);
    const linkedBlockCodes = (blocks.items || []).map((item) => item.blockCode).filter(Boolean);
    const linkedRightArchiveCodes = (rights.items || []).map((item) => item.archiveCode).filter(Boolean);
    const hydrated = {
      ...record,
      linkedBlockCodes,
      linkedRightArchiveCodes,
      properties: {
        ...(record.properties || {}),
        linkedBlockCount: Number(blocks.total || 0),
        linkedRightArchiveCount: Number(rights.total || 0),
        linkedTargetsTruncated:
          Number(blocks.total || 0) > linkedBlockCodes.length ||
          Number(rights.total || 0) > linkedRightArchiveCodes.length,
      },
    };
    const index = state.records.findIndex((item) => String(item.id) === String(record.id));
    if (index >= 0) state.records[index] = hydrated;
    return hydrated;
  }

  function businessActionButtons(record) {
    if (isDeletedRecord(record)) {
      return `
        <div class="row-actions" aria-label="业务记录操作">
          <button type="button" class="icon-button" data-row-action="view" aria-label="查看记录" title="查看记录">${VIEW_ICON}</button>
          <button type="button" class="icon-button" data-business-action="restore" data-permission="${businessPermission("restore")}" aria-label="恢复记录" title="恢复记录">${RESTORE_ICON}</button>
        </div>
      `;
    }
    return rowActionButtons({
      edit: businessPermission("update"),
      delete: businessPermission("delete"),
    });
  }

  function renderRows() {
    const bodyEl = $("#businessRows");
    if (!state.records.length) {
      bodyEl.innerHTML = `<tr class="placeholder-row"><td colspan="6">暂无${escapeHtml(kind)}记录</td></tr>`;
      return;
    }
    bodyEl.innerHTML = state.records
      .map((record) => {
        const linked = record.linkedBlockCodes || [];
        const linkedCount = linkedTargetCount(record, "blocks");
        const active = String(record.id) === String(state.activeId) ? "active" : "";
        return `
          <tr data-id="${escapeHtml(record.id)}" class="${active}">
            <td><div class="cell-stack"><strong>${escapeHtml(record.recordCode || "-")}</strong><small>${escapeHtml(kind)}</small></div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(record.name || "-")}</strong>${renderCoreFields(record)}</div></td>
            <td><div class="cell-stack"><strong>${escapeHtml(linkedCount ? `${linkedCount} 个林班` : "未挂接")}</strong><small>${escapeHtml(linked.slice(0, 2).join(", ") || (linkedCount ? "按需加载关联明细" : "-"))}</small></div></td>
            <td><span class="status-pill">${escapeHtml(record.status || "未填")}</span></td>
            <td>${escapeHtml(formatDateTime(record.updatedAt))}</td>
            <td>${businessActionButtons(record)}</td>
          </tr>
        `;
      })
      .join("");
    applyActionPermissions();
  }

  function detailItem(label, value) {
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "未填")}</dd></div>`;
  }

  function detailMarkup(label, markup, className = "") {
    const classText = className ? ` class="${escapeHtml(className)}"` : "";
    return `<div${classText}><dt>${escapeHtml(label)}</dt><dd>${markup}</dd></div>`;
  }

  function businessPropertiesWithoutAudit(properties = {}) {
    const clean = { ...(properties || {}) };
    delete clean.auditEvents;
    return clean;
  }

  function businessPropertiesForEditing(record = {}) {
    const clean = businessPropertiesWithoutAudit(record.properties || {});
    businessCorePropertyKeys().forEach((key) => delete clean[key]);
    return clean;
  }

  function businessAuditEvents(record = {}) {
    const events = record.properties?.auditEvents;
    return Array.isArray(events) ? events.filter((event) => event && typeof event === "object") : [];
  }

  function renderBusinessAuditTrail(record = {}) {
    const events = businessAuditEvents(record).slice(-4).reverse();
    if (!events.length) {
      return '<span class="audit-summary-empty">暂无操作留痕</span>';
    }
    return `<div class="audit-summary">${events
      .map((event) => {
        const action = BUSINESS_EVENT_ACTION_LABELS[event.action] || event.action || "操作";
        const actor = event.actor || "-";
        const changed = Array.isArray(event.changedFields) && event.changedFields.length ? ` · ${event.changedFields.join(", ")}` : "";
        return `<span class="audit-summary-chip"><b>${escapeHtml(action)}</b><span>${escapeHtml(`${actor} · ${formatDateTime(event.at)}${changed}`)}</span></span>`;
      })
      .join("")}</div>`;
  }

  function renderDetail(record = activeRecord()) {
    const panel = $("#businessDetailPanel");
    if (!record) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      return;
    }
    if (panel.classList.contains("hidden")) detailReturnFocus = document.activeElement;
    $("#businessDetailTitle").textContent = `${record.name || record.recordCode || kind}详情`;
    $("#businessDetailEmpty").hidden = true;
    $("#businessDetailGrid").innerHTML = [
      detailItem("记录编号", record.recordCode || "-"),
      detailItem("名称", record.name || "-"),
      detailItem("业务类型", kind),
      detailItem("状态", record.status || "未填"),
      detailItem("关联林班", linkedTargetSummary(record, "blocks")),
      detailItem("关联林权档案", linkedTargetSummary(record, "rights")),
      detailItem("更新时间", formatDateTime(record.updatedAt)),
      detailMarkup("核心业务字段", renderCoreFields(record), "detail-wide"),
      detailMarkup("最近操作", renderBusinessAuditTrail(record), "detail-wide"),
      detailItem("扩展字段", stringifyPretty(businessPropertiesWithoutAudit(record.properties), {})),
    ].join("");
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    renderRows();
  }

  function fillForm(record = {}) {
    state.activeId = record.id || "";
    $("#businessFormTitle").textContent = record.id ? `编辑${kind}` : `新建${kind}`;
    $("#businessRecordId").value = record.id || "";
    $("#businessRecordCode").value = record.recordCode || "";
    $("#businessRecordName").value = record.name || "";
    state.statusControl.setValue(record.status || "active");
    state.linkedBlockPicker.setValues(Array.isArray(record.linkedBlockCodes) ? record.linkedBlockCodes : []);
    state.linkedRightPicker.setValues(Array.isArray(record.linkedRightArchiveCodes) ? record.linkedRightArchiveCodes : []);
    const relationsPartial = Boolean(record.properties?.linkedTargetsTruncated);
    [$("#businessLinkedBlockCodes"), $("#businessLinkedRightArchiveCodes")].forEach((input) => {
      input.dataset.preserveRelations = String(relationsPartial);
      input.title = relationsPartial ? "关联数据超过 100 条，请通过关联管理功能分批维护" : "";
    });
    state.linkedBlockPicker.setDisabled(relationsPartial);
    state.linkedRightPicker.setDisabled(relationsPartial);
    fillBusinessCoreFields(record);
    $("#businessProperties").value = stringifyPretty(businessPropertiesForEditing(record), {});
    const deleteButton = $("#deleteBusinessRecord");
    deleteButton.hidden = !record.id;
    deleteButton.disabled = !record.id;
    $("#saveBusinessRecord").setAttribute("data-permission", businessPermission(record.id ? "update" : "create"));
    applyActionPermissions();
    renderRows();
  }

  function openBusinessEditor(mode, record = {}) {
    editorReturnFocus = document.activeElement;
    closeBusinessDetail(false);
    fillForm(mode === "edit" ? record : {});
    $("#businessForm").classList.remove("hidden");
    $("#businessForm").setAttribute("aria-hidden", "false");
    $("#businessRecordCode").focus();
  }

  function closeBusinessEditor() {
    $("#businessForm").classList.add("hidden");
    $("#businessForm").setAttribute("aria-hidden", "true");
    restoreModalFocus(editorReturnFocus);
    editorReturnFocus = null;
  }

  function closeBusinessDetail(restoreFocus = true) {
    $("#businessDetailPanel").classList.add("hidden");
    $("#businessDetailPanel").setAttribute("aria-hidden", "true");
    if (restoreFocus) restoreModalFocus(detailReturnFocus);
    detailReturnFocus = null;
  }

  function focusableElements(container) {
    return Array.from(
      container.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((element) => !element.hidden && element.getAttribute("aria-hidden") !== "true" && element.getClientRects().length);
  }

  function restoreModalFocus(element) {
    if (element?.isConnected && typeof element.focus === "function") element.focus();
  }

  function activeBusinessModal() {
    if (!$("#businessForm").classList.contains("hidden")) return $("#businessForm");
    if (!$("#businessDetailPanel").classList.contains("hidden")) return $("#businessDetailPanel");
    return null;
  }

  function handleModalKeyboard(event) {
    const modal = activeBusinessModal();
    if (!modal) return;
    if (event.key === "Escape") {
      event.preventDefault();
      if (modal.id === "businessForm") closeBusinessEditor();
      else closeBusinessDetail();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = focusableElements(modal);
    if (!focusable.length) {
      event.preventDefault();
      modal.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function configureModal(modal, labelledBy) {
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", labelledBy);
    modal.setAttribute("tabindex", "-1");
  }

  function payloadFromForm() {
    const code = $("#businessRecordCode").value.trim();
    const payload = {
      recordCode: code || undefined,
      name: $("#businessRecordName").value.trim(),
      status: $("#businessRecordStatus").value.trim() || "active",
      linkedBlockCodes: splitValues($("#businessLinkedBlockCodes").value),
      linkedRightArchiveCodes: splitValues($("#businessLinkedRightArchiveCodes").value),
      properties: mergeBusinessCoreFieldsIntoProperties(parseJson("扩展 JSON", $("#businessProperties").value, {})),
    };
    if ($("#businessLinkedBlockCodes").dataset.preserveRelations === "true") delete payload.linkedBlockCodes;
    if ($("#businessLinkedRightArchiveCodes").dataset.preserveRelations === "true") delete payload.linkedRightArchiveCodes;
    return payload;
  }

  function currentQuery() {
    return query({
      q: $("#businessKeyword").value.trim(),
      status: $("#businessStatusFilter").value.trim(),
      linkedBlockCode: $("#businessLinkedBlockFilter").value.trim(),
      fieldKey: $("#businessCoreFieldFilter")?.value || "",
      fieldValue: $("#businessCoreFieldValueFilter")?.value.trim() || "",
      includeDeleted: $("#includeDeletedBusinessRecords")?.checked ? "true" : "",
      limit: pager.limit,
      offset: pager.offset,
    });
  }

  function businessEventQuery() {
    return query({
      q: $("#businessEventKeyword")?.value.trim() || "",
      action: $("#businessEventActionFilter")?.value.trim() || "",
      recordCode: $("#businessEventRecordFilter")?.value.trim() || "",
      linkedBlockCode: $("#businessEventLinkedBlockFilter")?.value.trim() || "",
      limit: 100,
    });
  }

  function eventActionLabel(action) {
    return BUSINESS_EVENT_ACTION_LABELS[action] || action || "-";
  }

  function compactEventList(values) {
    const items = Array.isArray(values) ? values.filter(Boolean) : [];
    if (!items.length) return '<span class="audit-summary-empty">-</span>';
    const visible = items.slice(0, 3);
    const more = items.length > visible.length ? `<span class="audit-summary-more">+${items.length - visible.length}</span>` : "";
    return `<div class="audit-summary">${visible
      .map((item) => `<span class="audit-summary-chip"><span>${escapeHtml(item)}</span></span>`)
      .join("")}${more}</div>`;
  }

  function renderBusinessEventRows() {
    const bodyEl = $("#businessEventRows");
    if (!bodyEl) return;
    if (!state.businessEvents.length) {
      bodyEl.innerHTML = '<tr class="placeholder-row"><td colspan="6">暂无操作审计记录</td></tr>';
      return;
    }
    bodyEl.innerHTML = state.businessEvents
      .map((event) => {
        return `
          <tr>
            <td><span class="status-pill">${escapeHtml(eventActionLabel(event.action))}</span></td>
            <td><div class="cell-stack"><strong>${escapeHtml(event.recordCode || "-")}</strong><small>${escapeHtml(event.recordName || "-")}</small></div></td>
            <td>${escapeHtml(event.actor || "-")}</td>
            <td>${compactEventList(event.linkedBlockCodes)}</td>
            <td>${compactEventList(event.changedFields)}</td>
            <td>${escapeHtml(formatDateTime(event.at))}</td>
          </tr>
        `;
      })
      .join("");
  }

  async function loadBusinessEvents() {
    const bodyEl = $("#businessEventRows");
    if (!bodyEl) return;
    try {
      const payload = await api(`${endpoint}/events?${businessEventQuery()}`);
      state.businessEvents = Array.isArray(payload.items) ? payload.items : [];
      renderBusinessEventRows();
    } catch (error) {
      bodyEl.innerHTML = `<tr class="placeholder-row"><td colspan="6">${escapeHtml(error.message)}</td></tr>`;
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
    } catch (error) {
      setStatus("offline", `${messages.fail}：${error.message}`);
    }
  }

  async function exportBusinessEvents() {
    await downloadFile(
      `${endpoint}/events.csv?${businessEventQuery()}`,
      `business-${endpointModuleKey || moduleKey || "module"}-events.csv`,
      {
        busy: "正在导出业务操作审计 CSV...",
        done: "业务操作审计 CSV 已开始下载。",
        fail: "业务操作审计导出失败",
      },
    );
  }

  async function loadRecords() {
    setStatus("busy", `正在加载${kind}记录...`);
    pager.setBusy(true);
    try {
      const payload = await api(`${endpoint}?${currentQuery()}`);
      if (pager.setTotal(payload.total ?? 0)) return loadRecords();
      state.records = Array.isArray(payload.items) ? payload.items : [];
      if (state.activeId && !activeRecord()) fillForm();
      renderRows();
      setStatus("online", `已加载 ${payload.total ?? state.records.length} 条${kind}记录。`);
    } catch (error) {
      setStatus("offline", `${kind}加载失败：${error.message}`);
    } finally {
      pager.setBusy(false);
    }
  }

  function reloadRecordsFromFirstPage() {
    pager.reset();
    return loadRecords();
  }

  async function saveRecord(event) {
    event.preventDefault();
    let bodyText;
    try {
      bodyText = JSON.stringify(payloadFromForm());
    } catch (error) {
      setStatus("offline", error.message);
      return;
    }
    const id = $("#businessRecordId").value.trim();
    const path = id ? `${endpoint}/${encodeURIComponent(id)}` : endpoint;
    const method = id ? "PATCH" : "POST";
    setStatus("busy", `正在保存${kind}...`);
    try {
      const saved = await api(path, { method, body: bodyText });
      state.activeId = saved.id;
      closeBusinessEditor();
      await loadRecords();
      await loadBusinessEvents();
      const detailRecord = state.records.find((record) => String(record.id) === String(saved.id)) || saved;
      renderDetail(await hydrateBusinessTargets(detailRecord));
      setStatus("online", `${kind}已保存。`);
    } catch (error) {
      setStatus("offline", `${kind}保存失败：${error.message}`);
    }
  }

  async function deleteRecord(record = activeRecord()) {
    if (!record) return;
    setStatus("busy", `正在删除${kind}...`);
    try {
      await api(`${endpoint}/${encodeURIComponent(record.id)}`, { method: "DELETE" });
      state.activeId = "";
      closeBusinessEditor();
      closeBusinessDetail();
      await loadRecords();
      await loadBusinessEvents();
      setStatus("online", `${kind}已软删除。`);
    } catch (error) {
      setStatus("offline", `${kind}删除失败：${error.message}`);
    }
  }

  async function restoreRecord(record = activeRecord()) {
    if (!record) return;
    setStatus("busy", `正在恢复${kind}...`);
    try {
      await api(`${endpoint}/${encodeURIComponent(record.id)}/restore`, { method: "POST" });
      state.activeId = record.id;
      await loadRecords();
      await loadBusinessEvents();
      renderDetail(activeRecord());
      setStatus("online", `${kind}已恢复。`);
    } catch (error) {
      setStatus("offline", `${kind}恢复失败：${error.message}`);
    }
  }

  function applyPagePermissionAttributes() {
    $("#newBusinessRecord")?.setAttribute("data-permission", businessPermission("create"));
    $("#deleteBusinessRecord")?.setAttribute("data-permission", businessPermission("delete"));
    $("#saveBusinessRecord")?.setAttribute("data-permission", businessPermission("create"));
    $("#exportBusinessEvents")?.setAttribute("data-permission", businessPermission("export"));
  }

  async function handleRowAction(event) {
    const businessButton = event.target.closest("[data-business-action]");
    if (businessButton) {
      event.stopPropagation();
      if (businessButton.disabled) return true;
      const row = businessButton.closest("tr[data-id]");
      const record = state.records.find((item) => String(item.id) === String(row?.dataset.id)) || null;
      if (!record) return true;
      state.activeId = record.id;
      if (businessButton.dataset.businessAction === "restore") {
        restoreRecord(record);
      }
      return true;
    }
    const button = event.target.closest("[data-row-action]");
    if (!button) return false;
    event.stopPropagation();
    if (button.disabled) return true;
    const row = button.closest("tr[data-id]");
    const record = state.records.find((item) => String(item.id) === String(row?.dataset.id)) || null;
    if (!record) return true;
    state.activeId = record.id;
    const action = button.dataset.rowAction;
    if (action === "view") {
      renderDetail(await hydrateBusinessTargets(record));
    } else if (action === "edit") {
      openBusinessEditor("edit", await hydrateBusinessTargets(record));
      renderRows();
    } else if (action === "delete") {
      deleteRecord(record);
    }
    return true;
  }

  async function initialize() {
    initShell();
    ensureDeletedFilterToggle();
    await loadModuleFieldSchema();
    ensureBusinessCoreFieldFilter();
    ensureBusinessCoreFieldInputs();
    await setupSmartFields();
    ensureBusinessEventLedger();
    configureModal($("#businessForm"), "businessFormTitle");
    configureModal($("#businessDetailPanel"), "businessDetailTitle");
    applyPagePermissionAttributes();
    pager = createLedgerPager({ anchor: $("#businessRows").closest(".table-wrap"), onPageChange: loadRecords });
    $("#businessPageTitle").textContent = title;
    $("#businessTableTitle").textContent = `${kind}列表`;
    $("#reloadBusiness").addEventListener("click", loadRecords);
    $("#newBusinessRecord").addEventListener("click", () => openBusinessEditor("create"));
    $("#businessForm").addEventListener("submit", saveRecord);
    $("#businessForm").addEventListener("click", (event) => {
      if (event.target === event.currentTarget) closeBusinessEditor();
    });
    $("#businessDetailPanel").addEventListener("click", (event) => {
      if (event.target === event.currentTarget) closeBusinessDetail();
    });
    document.addEventListener("keydown", handleModalKeyboard);
    $("#cancelBusinessEdit").addEventListener("click", closeBusinessEditor);
    $("#closeBusinessDetail").addEventListener("click", closeBusinessDetail);
    $("#deleteBusinessRecord").addEventListener("click", () => deleteRecord(activeRecord()));
    $("#businessStatusFilter").addEventListener("change", reloadRecordsFromFirstPage);
    $("#businessLinkedBlockFilter").addEventListener("change", reloadRecordsFromFirstPage);
    $("#includeDeletedBusinessRecords")?.addEventListener("change", reloadRecordsFromFirstPage);
    $("#refreshBusinessEvents")?.addEventListener("click", loadBusinessEvents);
    $("#exportBusinessEvents")?.addEventListener("click", exportBusinessEvents);
    $("#businessEventActionFilter")?.addEventListener("change", loadBusinessEvents);
    $("#businessEventRecordFilter")?.addEventListener("input", () => window.setTimeout(loadBusinessEvents, 180));
    $("#businessEventLinkedBlockFilter")?.addEventListener("input", () => window.setTimeout(loadBusinessEvents, 180));
    $("#businessEventKeyword")?.addEventListener("input", () => window.setTimeout(loadBusinessEvents, 180));
    $("#businessKeyword").addEventListener("input", () => {
      window.clearTimeout(keywordTimer);
      keywordTimer = window.setTimeout(reloadRecordsFromFirstPage, 180);
    });
    $("#businessRows").addEventListener("click", async (event) => {
      try {
        if (await handleRowAction(event)) return;
      } catch (error) {
        setStatus("offline", `${kind}关联数据加载失败：${error.message}`);
        return;
      }
      const row = event.target.closest("tr[data-id]");
      if (!row) return;
      state.activeId = row.dataset.id;
      try {
        renderDetail(await hydrateBusinessTargets(activeRecord()));
      } catch (error) {
        setStatus("offline", `${kind}关联数据加载失败：${error.message}`);
      }
    });
    loadRecords();
    loadBusinessEvents();
  }

  initialize().catch((error) => setStatus("offline", `页面初始化失败：${error.message}`));
})();
