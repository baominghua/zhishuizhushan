(() => {
  const { $, escapeHtml, fetchWithSession, initShell, setStatus } = AdminCommon;
  const PAGE_PERMISSION = "system.deployment.view";

  async function fetchDeploymentHealth() {
    const response = await fetchWithSession("/api/health");
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { ok: false, error: await response.text() };
    payload.httpStatus = response.status;
    return payload;
  }

  async function exportDeploymentReport() {
    setStatus("busy", "正在导出部署诊断报告...");
    try {
      const response = await fetchWithSession("/api/deployment/report.json");
      if (!response.ok) {
        const payload = await response.text();
        throw new Error(`${response.status} ${payload || response.statusText}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "deployment-report.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus("online", "部署诊断报告 JSON 已导出。");
    } catch (error) {
      setStatus("offline", `部署诊断报告导出失败：${error.message}`);
    }
  }

  function statusText(healthy) {
    return healthy ? "就绪" : "需处理";
  }

  function statusClass(healthy) {
    return healthy ? "complete" : "missing";
  }

  function statusPill(healthy) {
    return `<span class="status-pill ${statusClass(healthy)}">${escapeHtml(statusText(healthy))}</span>`;
  }

  function readinessStatusLabel(status) {
    const labels = {
      ready: "生产就绪",
      warning: "有警告",
      blocked: "阻断上线",
    };
    return labels[status] || "待检查";
  }

  function readinessStatusClass(status) {
    if (status === "ready") return "complete";
    if (status === "warning") return "partial";
    if (status === "blocked") return "missing";
    return "";
  }

  function readinessPill(status) {
    return `<span class="status-pill ${readinessStatusClass(status)}">${escapeHtml(readinessStatusLabel(status))}</span>`;
  }

  function readinessIssuePill(status) {
    const labels = {
      blocked: "阻断",
      warning: "警告",
      pass: "通过",
    };
    return `<span class="status-pill ${readinessStatusClass(status === "pass" ? "ready" : status)}">${escapeHtml(labels[status] || status || "-")}</span>`;
  }

  function booleanText(value) {
    return value ? "是" : "否";
  }

  function formatBytes(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = numeric;
    let index = 0;
    while (size >= 1024 && index < units.length - 1) {
      size /= 1024;
      index += 1;
    }
    return `${size.toFixed(index === 0 || size >= 10 ? 0 : 1)} ${units[index]}`;
  }

  function tableRow(columns) {
    return `<tr>${columns.map((column) => `<td>${column}</td>`).join("")}</tr>`;
  }

  function renderRows(selector, rows, colSpan = 4, emptyText = "暂无数据") {
    const body = $(selector);
    if (!body) return;
    if (!rows.length) {
      body.innerHTML = `<tr class="placeholder-row"><td colspan="${colSpan}">${escapeHtml(emptyText)}</td></tr>`;
      return;
    }
    body.innerHTML = rows.join("");
  }

  function renderReadinessRows(payload) {
    const readiness = payload.deployment?.readiness || {};
    const rows = [
      ...((readiness.blockingIssues || []).map((item) => ({ ...item, status: "blocked" }))),
      ...((readiness.warnings || []).map((item) => ({ ...item, status: "warning" }))),
    ];
    if (!rows.length) {
      renderRows(
        "#readinessRows",
        [
          tableRow([
            readinessIssuePill("pass"),
            "<strong>生产就绪</strong>",
            "未检测到阻断项或上线警告。",
            "-",
          ]),
        ],
        4,
        "暂无生产就绪结论",
      );
      return;
    }
    renderRows(
      "#readinessRows",
      rows.map((item) =>
        tableRow([
          readinessIssuePill(item.status),
          `<div class="cell-stack"><strong>${escapeHtml(item.label || item.key || "-")}</strong><small>${escapeHtml(item.section || "-")}</small></div>`,
          escapeHtml(item.message || "-"),
          escapeHtml(item.actionRequired || "-"),
        ]),
      ),
      4,
      "暂无生产就绪结论",
    );
  }

  function directoryReady(item) {
    return Boolean(item?.exists && item?.writable);
  }

  function databaseReady(item) {
    return Boolean(item?.reachable && item?.schemaReady);
  }

  function deploymentCheckRows(deployment) {
    const platform = deployment.database.platform || {};
    const remoteSensingCatalog = deployment.database.remoteSensingCatalog || {};
    const smartBamboo = deployment.smartBamboo || {};
    const jsonData = smartBamboo.jsonData || {};
    const imagery = deployment.imagery || {};
    const dataDir = jsonData.dataDir || {};
    const importDirs = Array.isArray(imagery.importDirs) ? imagery.importDirs : [];
    const rows = [
      {
        name: "平台数据库",
        healthy: databaseReady(platform),
        config: `${platform.backend || "json"} / ${smartBamboo.storageBackend || "-"}`,
        detail: platform.error || `缺失表：${(platform.missingTables || []).join(", ") || "无"}`,
      },
      {
        name: "影像目录数据库",
        healthy: databaseReady(remoteSensingCatalog),
        config: remoteSensingCatalog.backend || deployment.catalogBackend || "-",
        detail: remoteSensingCatalog.error || `缺失表：${(remoteSensingCatalog.missingTables || []).join(", ") || "无"}`,
      },
      {
        name: "数据根目录",
        healthy: directoryReady(dataDir),
        config: dataDir.path || deployment.dataDir || "-",
        detail: dataDir.exists ? `可写：${booleanText(dataDir.writable)}` : "目录不存在",
      },
      {
        name: "影像上传目录",
        healthy: directoryReady(imagery.uploadDir),
        config: imagery.uploadDir?.path || "-",
        detail: imagery.uploadDir?.exists ? `可写：${booleanText(imagery.uploadDir?.writable)}` : "目录不存在",
      },
      {
        name: "COG 输出目录",
        healthy: directoryReady(imagery.cogDir),
        config: imagery.cogDir?.path || "-",
        detail: imagery.cogDir?.exists ? `可写：${booleanText(imagery.cogDir?.writable)}` : "目录不存在",
      },
      {
        name: "成果入库目录",
        healthy: Boolean(importDirs.length && importDirs.every(directoryReady)),
        config: importDirs.map((item) => item.path).join(", ") || "-",
        detail: importDirs.length ? `${importDirs.length} 个目录已检查` : "未配置入库目录",
      },
    ];
    return rows.map((item) =>
      tableRow([
        `<strong>${escapeHtml(item.name)}</strong>`,
        statusPill(item.healthy),
        escapeHtml(item.config),
        escapeHtml(item.detail),
      ]),
    );
  }

  function groupApiChecksByDomain(deployment) {
    const checks = Array.isArray(deployment.apiChecks) ? deployment.apiChecks : [];
    const groups = [];
    const byKey = new Map();
    checks.forEach((item) => {
      const key = item.group || "other";
      if (!byKey.has(key)) {
        const group = {
          key,
          label: item.groupLabel || key,
          items: [],
        };
        byKey.set(key, group);
        groups.push(group);
      }
      byKey.get(key).items.push(item);
    });

    return groups.map((group) => {
      const total = group.items.length;
      const available = group.items.filter((item) => Boolean(item.available)).length;
      return {
        ...group,
        total,
        available,
        missing: total - available,
        healthy: total > 0 && available === total,
      };
    });
  }

  function renderApiCheckGroupSummary(deployment) {
    const container = $("#apiCheckGroupSummary");
    if (!container) return;
    const groups = groupApiChecksByDomain(deployment);
    if (!groups.length) {
      container.innerHTML = '<span class="api-check-group-empty">暂无关键业务接口</span>';
      return;
    }
    container.innerHTML = groups
      .map((group) => {
        const stateText = group.missing ? `${group.missing} 项待处理` : "全部就绪";
        return `
          <article class="api-check-group-card ${group.healthy ? "complete" : "missing"}">
            <span>${escapeHtml(group.label)}</span>
            <strong>${escapeHtml(`${group.available}/${group.total}`)}</strong>
            <small>${escapeHtml(stateText)}</small>
          </article>
        `;
      })
      .join("");
  }

  function apiCheckGroupRow(group) {
    const detail = group.missing ? `${group.available}/${group.total} 可用，${group.missing} 项待处理` : `${group.total} 项全部就绪`;
    return `
      <tr class="api-check-group-row">
        <td colspan="4">
          <div class="api-check-group-heading">
            <strong>${escapeHtml(group.label)}</strong>
            <small>${escapeHtml(detail)}</small>
          </div>
        </td>
      </tr>
    `;
  }

  function apiCheckRows(deployment) {
    return groupApiChecksByDomain(deployment).flatMap((group) => [
      apiCheckGroupRow(group),
      ...group.items.map((item) =>
        tableRow([
          `<div class="cell-stack"><strong>${escapeHtml(item.label || item.key || "-")}</strong><small>${escapeHtml(item.key || "-")}</small></div>`,
          statusPill(Boolean(item.available)),
          escapeHtml(`${item.method || "GET"} ${item.path || "-"}`),
          escapeHtml(item.permission || "-"),
        ]),
      ),
    ]);
  }

  function dependencyRows(payload) {
    return Object.entries(payload.dependencies || {}).map(([name, item]) => {
      const installed = Boolean(item?.installed ?? item?.ok ?? item);
      const detail = item?.error || item?.message || "-";
      const version = item?.version || item?.path || "-";
      return tableRow([
        `<strong>${escapeHtml(name)}</strong>`,
        statusPill(installed),
        escapeHtml(version),
        escapeHtml(detail),
      ]);
    });
  }

  function datasetStatus(item) {
    return Boolean(item?.exists && item?.writable && !item?.error);
  }

  function datasetRows(deployment) {
    deployment.smartBamboo = deployment.smartBamboo || {};
    deployment.smartBamboo.jsonData = deployment.smartBamboo.jsonData || {};
    deployment.imagery = deployment.imagery || {};
    deployment.imagery.catalog = deployment.imagery.catalog || {};
    deployment.imagery.tasks = deployment.imagery.tasks || {};
    const datasets = [
      ...((deployment.smartBamboo.jsonData.datasets || []).map((item) => ({ ...item, group: "平台" }))),
      ...((deployment.smartBamboo.jsonData.businessModules || []).map((item) => ({ ...item, group: "业务" }))),
      { ...deployment.imagery.catalog, key: deployment.imagery.catalog.key || "sceneCatalog", group: "影像" },
      { ...deployment.imagery.tasks, key: deployment.imagery.tasks.key || "imageryTasks", group: "影像" },
    ];
    return datasets.map((item) =>
      tableRow([
        `<div class="cell-stack"><strong>${escapeHtml(item.key || "-")}</strong><small>${escapeHtml(item.group || "-")}</small></div>`,
        statusPill(datasetStatus(item)),
        escapeHtml(`有效 ${item.recordCount ?? 0} / 删除 ${item.deletedCount ?? 0} / 总计 ${item.totalCount ?? 0}`),
        escapeHtml(item.error || item.path || "-"),
      ]),
    );
  }

  function cacheRows(deployment) {
    deployment.tileCache = deployment.tileCache || {};
    const tileCache = deployment.tileCache;
    const imagery = deployment.imagery || {};
    const tianditu = deployment.tiandituProxy || {};
    const geoserver = deployment.geoserver || {};
    const rows = [
      {
        name: "瓦片缓存",
        healthy: Boolean(tileCache.enabled !== false),
        config: tileCache.path || tileCache.root || "-",
        detail: `${tileCache.fileCount ?? 0} 文件 / ${formatBytes(tileCache.totalBytes ?? tileCache.sizeBytes ?? 0)}`,
      },
      {
        name: "影像目录",
        healthy: Boolean(imagery.catalog?.exists && !imagery.catalog?.error),
        config: imagery.catalog?.path || "-",
        detail: `场景 ${imagery.catalog?.recordCount ?? 0} / 已删除 ${imagery.catalog?.deletedCount ?? 0}`,
      },
      {
        name: "天地图代理",
        healthy: Boolean(tianditu.tokenConfigured || tianditu.enabled || tianditu.tkConfigured),
        config: tianditu.referer || tianditu.timeoutSeconds || "-",
        detail: tianditu.tokenConfigured || tianditu.tkConfigured ? "令牌已配置" : "未配置令牌",
      },
      {
        name: "GeoServer",
        healthy: Boolean(geoserver.baseUrl || geoserver.wmsUrl || geoserver.wfsUrl),
        config: geoserver.baseUrl || geoserver.wmsUrl || "-",
        detail: Array.isArray(geoserver.layers) ? `${geoserver.layers.length} 个图层` : "-",
      },
    ];
    return rows.map((item) =>
      tableRow([
        `<strong>${escapeHtml(item.name)}</strong>`,
        statusPill(item.healthy),
        escapeHtml(item.config),
        escapeHtml(item.detail),
      ]),
    );
  }

  function renderMetrics(payload) {
    const deployment = payload.deployment || {};
    const smartBamboo = deployment.smartBamboo || {};
    const imagery = deployment.imagery || {};
    const datasets = smartBamboo.jsonData?.datasets || [];
    const readiness = deployment.readiness || {};
    $("#deploymentHealthMetric").textContent = statusText(Boolean(payload.ok));
    $("#deploymentReadinessMetric").textContent = readinessStatusLabel(readiness.status);
    $("#platformStorageMetric").textContent = smartBamboo.storageBackend || "-";
    $("#imageryCatalogMetric").textContent = deployment.catalogBackend || imagery.catalog?.key || "-";
    $("#datasetMetric").textContent = String(datasets.length + (smartBamboo.jsonData?.businessModules || []).length);
  }

  function renderDeploymentRows(payload) {
    renderRows("#deploymentRows", deploymentCheckRows(payload.deployment || {}), 4, "暂无部署检查");
  }

  function renderApiCheckRows(payload) {
    const deployment = payload.deployment || {};
    renderApiCheckGroupSummary(deployment);
    renderRows("#apiCheckRows", apiCheckRows(deployment), 4, "暂无关键业务接口");
  }

  function renderDependencyRows(payload) {
    renderRows("#dependencyRows", dependencyRows(payload), 4, "暂无依赖状态");
  }

  function renderDatasetRows(payload) {
    renderRows("#datasetRows", datasetRows(payload.deployment || {}), 4, "暂无数据库存");
  }

  function renderCacheRows(payload) {
    renderRows("#cacheRows", cacheRows(payload.deployment || {}), 4, "暂无缓存状态");
  }

  function renderDeploymentHealth(payload) {
    renderMetrics(payload);
    renderReadinessRows(payload);
    renderDeploymentRows(payload);
    renderApiCheckRows(payload);
    renderDependencyRows(payload);
    renderDatasetRows(payload);
    renderCacheRows(payload);
  }

  async function loadDeployment() {
    setStatus("busy", "正在读取部署诊断...");
    try {
      const payload = await fetchDeploymentHealth();
      renderDeploymentHealth(payload);
      setStatus(payload.ok ? "online" : "warning", payload.ok ? "部署诊断已更新。" : "部署诊断存在需处理项目。");
    } catch (error) {
      setStatus("offline", `部署诊断读取失败：${error.message}`);
    }
  }

  function initialize() {
    initShell();
    $("#reloadDeployment")?.setAttribute("data-permission", PAGE_PERMISSION);
    $("#exportDeploymentReport")?.setAttribute("data-permission", PAGE_PERMISSION);
    $("#reloadDeployment")?.addEventListener("click", loadDeployment);
    $("#exportDeploymentReport")?.addEventListener("click", exportDeploymentReport);
    loadDeployment();
  }

  initialize();
})();
