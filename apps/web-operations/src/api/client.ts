import type {
  CapabilitiesResponse,
  BasemapSettingsPayload,
  BasemapSettingsResponse,
  AttachmentQuery,
  AttachmentRecord,
  AiFinding,
  AiFindingActionPayload,
  AiFindingPayload,
  AiModelAsset,
  AiModelAssetPayload,
  AiInferenceRun,
  AiInferenceRunPayload,
  AiInferenceActionPayload,
  AiInferenceFindingPayload,
  DeviceMaintenancePayload,
  DroneMission,
  DroneMissionActionPayload,
  DroneMissionPayload,
  ForestBlockPayload,
  ForestBlockFilterFacets,
  ForestBlockFeatureCollection,
  ForestBlockQuery,
  ForestBlockRecord,
  ForestBlockOptionsResponse,
  ForestSubcompartmentOptionsResponse,
  ForestSubcompartmentPatch,
  ForestSubcompartmentPayload,
  ForestSubcompartmentQuery,
  ForestSubcompartmentRecord,
  ForestRightPayload,
  ForestRightQuery,
  ForestRightRecord,
  ForestRightOptionsResponse,
  HarvestActionPayload,
  HarvestApplication,
  HarvestApplicationPayload,
  HarvestQuota,
  HarvestSubject,
  ImportJob,
  IotDevice,
  IotDevicePayload,
  ImageryAsset,
  ImageryAssetResponse,
  ImageryUploadPayload,
  LedgerResponse,
  LaborActionPayload,
  LaborJob,
  LaborJobPayload,
  LaborTeam,
  LaborTeamPayload,
  LaborWorker,
  LaborWorkerPayload,
  MapConfigResponse,
  MobileEvidenceRecord,
  MobileOfflinePackage,
  MobileUploadSession,
  MobilePendingOperation,
  MobileSyncBatchResult,
  MobileSyncOperationRecord,
  MobileTrackPayload,
  MobileTrackRecord,
  ResourceSnapshotComparison,
  ResourceSnapshotPayload,
  ResourceSnapshotRecord,
  ResourceSnapshotVersionRecord,
  ResourceSurveyPayload,
  ResourceSurveyQuery,
  ResourceSurveyRecord,
  PatrolActionPayload,
  PatrolTask,
  PatrolTaskPayload,
  SafetyActionPayload,
  SafetyAlert,
  SafetyEvent,
  SafetyEventPayload,
  SituationAssetResponse,
  SpatialVersionRecord,
  WorkspaceSummary,
  OperationsTodo,
  OperationsAuditEvent,
  AdministrativeDivisionResponse,
  CarbonEstimateLedgerResponse,
  CarbonEstimatePayload,
  CarbonEstimateQuery,
  CarbonEstimateRecord,
  LeadershipCockpitResponse,
  AdminOrganization,
  AdminOrganizationPayload,
  AdminUser,
  AdminUserPayload,
  AdminRole,
  AdminRolePayload,
  PermissionCatalogResponse,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

const CSRF_COOKIE_NAME = "smart_bamboo_session_csrf";
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let recoveredCsrfToken = "";

function cookieValue(name: string): string {
  const prefix = `${encodeURIComponent(name)}=`;
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : "";
}

function csrfToken(): string {
  return cookieValue(CSRF_COOKIE_NAME) || recoveredCsrfToken;
}

function isCsrfFailure(response: Response, body: unknown): boolean {
  return response.status === 403
    && typeof body === "object"
    && body !== null
    && "detail" in body
    && (body as { detail?: unknown }).detail === "CSRF validation failed";
}

async function recoverCsrfToken(): Promise<string> {
  const response = await fetch("/api/auth/session", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) return "";
  const body = await response.json() as { csrfToken?: string };
  recoveredCsrfToken = body.csrfToken || "";
  return recoveredCsrfToken;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = String(init.method || "GET").toUpperCase();
  const headers = requestHeaders({
    Accept: "application/json",
    ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
    ...(init.headers as Record<string, string> | undefined),
  });
  if (MUTATING_METHODS.has(method) && csrfToken()) {
    headers["X-CSRF-Token"] = csrfToken();
  }
  const requestInit = {
    ...init,
    credentials: "same-origin",
    headers,
  } satisfies RequestInit;
  let response = await fetch(path, requestInit);
  let responseBody: unknown = null;
  if (!response.ok) {
    responseBody = await response.clone().json().catch(() => null);
  }
  if (MUTATING_METHODS.has(method) && isCsrfFailure(response, responseBody)) {
    const freshToken = await recoverCsrfToken();
    if (freshToken) {
      headers["X-CSRF-Token"] = freshToken;
      response = await fetch(path, { ...requestInit, headers });
      responseBody = response.ok
        ? null
        : await response.clone().json().catch(() => null);
    }
  }
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    if (typeof responseBody === "object" && responseBody !== null && "detail" in responseBody) {
      message = String((responseBody as { detail?: unknown }).detail || message);
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

function requestHeaders(initial: Record<string, string> = {}): Record<string, string> {
  const headers = { ...initial };
  if (import.meta.env.DEV) {
    headers["X-RS-User"] = "v2-developer";
    headers["X-RS-Roles"] = "admin";
    headers["X-RS-Areas"] = "*";
  }
  return headers;
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: requestHeaders({ Accept: "text/csv,application/octet-stream" }),
  });
  if (!response.ok) {
    throw new ApiError(`导出失败 (${response.status})`, response.status);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function queryString(values: object) {
  const search = new URLSearchParams();
  Object.entries(values as Record<string, string | number | boolean | undefined>).forEach(([key, value]) => {
    if (value !== undefined && value !== "" && value !== false) search.set(key, String(value));
  });
  return search.toString();
}

export const api = {
  adminOrganizations: (query: { q?: string; status?: string; includeDeleted?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<AdminOrganization>>(`/api/admin/organizations?${queryString(query)}`),
  createAdminOrganization: (payload: AdminOrganizationPayload) =>
    request<AdminOrganization>("/api/admin/organizations", { method: "POST", body: JSON.stringify(payload) }),
  updateAdminOrganization: (id: string, payload: Partial<AdminOrganizationPayload>) =>
    request<AdminOrganization>(`/api/admin/organizations/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteAdminOrganization: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/admin/organizations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  adminUsers: (query: { q?: string; status?: string; role?: string; includeDeleted?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<AdminUser>>(`/api/admin/users?${queryString(query)}`),
  createAdminUser: (payload: AdminUserPayload) =>
    request<AdminUser>("/api/admin/users", { method: "POST", body: JSON.stringify(payload) }),
  updateAdminUser: (id: string, payload: Partial<Omit<AdminUserPayload, "username">>) =>
    request<AdminUser>(`/api/admin/users/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteAdminUser: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/admin/users/${encodeURIComponent(id)}`, { method: "DELETE" }),
  setAdminUserPassword: (id: string, temporaryPassword: string) =>
    request<{ ok: boolean }>(`/api/admin/users/${encodeURIComponent(id)}/set-password`, { method: "POST", body: JSON.stringify({ temporaryPassword }) }),
  revokeAdminUserSessions: (id: string) =>
    request<{ ok: boolean }>(`/api/admin/users/${encodeURIComponent(id)}/revoke-sessions`, { method: "POST" }),
  adminRoles: (query: { q?: string; status?: string; permission?: string; menuModule?: string; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<AdminRole>>(`/api/admin/roles?${queryString(query)}`),
  createAdminRole: (payload: AdminRolePayload) =>
    request<AdminRole>("/api/admin/roles", { method: "POST", body: JSON.stringify(payload) }),
  updateAdminRole: (id: string, payload: Partial<Omit<AdminRolePayload, "roleCode">>) =>
    request<AdminRole>(`/api/admin/roles/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteAdminRole: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/admin/roles/${encodeURIComponent(id)}`, { method: "DELETE" }),
  permissionCatalog: () => request<PermissionCatalogResponse>("/api/admin/permission-catalog"),
  leadershipCockpit: () => request<LeadershipCockpitResponse>("/api/v2/cockpit/leadership"),
  capabilities: () => request<CapabilitiesResponse>("/api/v2/system/capabilities"),
  workspaceSummary: () => request<WorkspaceSummary>("/api/v2/workspace/summary"),
  operationsTodos: (query: { q?: string; module?: string; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<OperationsTodo>>(`/api/v2/operations-center/todos?${queryString(query)}`),
  operationsNotifications: (query: { q?: string; module?: string; unreadOnly?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<OperationsAuditEvent>>(`/api/v2/operations-center/notifications?${queryString(query)}`),
  markNotificationRead: (id: string) =>
    request<{ ok: boolean; notificationId: string; read: boolean }>(`/api/v2/operations-center/notifications/${encodeURIComponent(id)}/read`, { method: "POST" }),
  markNotificationUnread: (id: string) =>
    request<{ ok: boolean; notificationId: string; read: boolean }>(`/api/v2/operations-center/notifications/${encodeURIComponent(id)}/read`, { method: "DELETE" }),
  markAllNotificationsRead: () =>
    request<{ ok: boolean; updated: number }>("/api/v2/operations-center/notifications/read-all", { method: "POST" }),
  operationsAudit: (query: { q?: string; module?: string; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<OperationsAuditEvent>>(`/api/v2/operations-center/audit?${queryString(query)}`),
  mapConfig: () => request<MapConfigResponse>("/api/v2/system/map-config"),
  basemapSettings: () => request<BasemapSettingsResponse>("/api/v2/system/basemap-settings"),
  administrativeDivisions: (
    level: "province" | "city" | "county" | "town" | "village",
    parentCode?: string,
  ) => request<AdministrativeDivisionResponse>(
    `/api/v2/system/administrative-divisions?${queryString({ level, parentCode, limit: 1000 })}`,
  ),
  updateBasemapSettings: (payload: BasemapSettingsPayload) =>
    request<BasemapSettingsResponse>("/api/v2/system/basemap-settings", { method: "PUT", body: JSON.stringify(payload) }),
  carbonEstimates: (query: CarbonEstimateQuery = {}) =>
    request<CarbonEstimateLedgerResponse>(`/api/v2/carbon/estimates?${queryString(query)}`),
  carbonEstimate: (id: string) =>
    request<CarbonEstimateRecord>(`/api/v2/carbon/estimates/${encodeURIComponent(id)}`),
  createCarbonEstimate: (payload: CarbonEstimatePayload) =>
    request<CarbonEstimateRecord>("/api/v2/carbon/estimates", { method: "POST", body: JSON.stringify(payload) }),
  updateCarbonEstimate: (id: string, payload: CarbonEstimatePayload) =>
    request<CarbonEstimateRecord>(`/api/v2/carbon/estimates/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteCarbonEstimate: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/v2/carbon/estimates/${encodeURIComponent(id)}`, { method: "DELETE" }),
  forestBlockMap: (query: ForestBlockQuery & { bbox: string; zoom: number; maxFeatures?: number }) =>
    request<ForestBlockFeatureCollection>(
      `/api/map/forest-blocks.geojson?${queryString(query)}`,
    ),
  forestBlocks: (query: string | ForestBlockQuery = "") => {
    const filters = typeof query === "string" ? { q: query } : query;
    const search = new URLSearchParams(queryString({ ...filters, limit: filters.limit ?? 20 }));
    return request<ForestBlockOptionsResponse>(
      `/api/v2/entities/forest-blocks?${search.toString()}`,
    );
  },
  forestRights: (query = "", linkedBlockCode = "") => {
    const search = new URLSearchParams({ q: query, linkedBlockCode, limit: "20" });
    return request<ForestRightOptionsResponse>(`/api/v2/entities/forest-rights?${search.toString()}`);
  },
  forestSubcompartments: (query = "", forestBlockId = "") => {
    const search = new URLSearchParams({ q: query, forestBlockId, limit: "20" });
    return request<ForestSubcompartmentOptionsResponse>(
      `/api/v2/entities/forest-subcompartments?${search.toString()}`,
    );
  },
  forestBlockLedger: (query: ForestBlockQuery) =>
    request<LedgerResponse<ForestBlockRecord>>(
      `/api/v2/resources/forest-blocks?${queryString(query)}`,
    ),
  forestBlockFacets: () =>
    request<ForestBlockFilterFacets>("/api/v2/resources/forest-blocks-facets"),
  forestBlockDetail: (id: string) =>
    request<ForestBlockRecord>(`/api/v2/resources/forest-blocks/${encodeURIComponent(id)}`),
  createForestBlock: (payload: ForestBlockPayload) =>
    request<ForestBlockRecord>("/api/v2/resources/forest-blocks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateForestBlock: (id: string, payload: Partial<ForestBlockPayload>) =>
    request<ForestBlockRecord>(`/api/v2/resources/forest-blocks/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteForestBlock: (id: string) =>
    request<{ ok: boolean; deleted: string }>(
      `/api/v2/resources/forest-blocks/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),
  forestBlockVersions: (id: string) =>
    request<LedgerResponse<SpatialVersionRecord>>(
      `/api/v2/resources/forest-blocks/${encodeURIComponent(id)}/versions`,
    ),
  rollbackForestBlock: (id: string, versionId: string) =>
    request<{ ok: boolean; block: ForestBlockRecord }>(
      `/api/v2/resources/forest-blocks/${encodeURIComponent(id)}/rollback`,
      { method: "POST", body: JSON.stringify({ versionId }) },
    ),
  forestSubcompartmentLedger: (query: ForestSubcompartmentQuery) =>
    request<LedgerResponse<ForestSubcompartmentRecord>>(
      `/api/v2/resources/forest-subcompartments?${queryString(query)}`,
    ),
  forestSubcompartmentDetail: (id: string) =>
    request<ForestSubcompartmentRecord>(
      `/api/v2/resources/forest-subcompartments/${encodeURIComponent(id)}`,
    ),
  createForestSubcompartment: (payload: ForestSubcompartmentPayload) =>
    request<ForestSubcompartmentRecord>("/api/v2/resources/forest-subcompartments", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateForestSubcompartment: (id: string, payload: ForestSubcompartmentPatch) =>
    request<ForestSubcompartmentRecord>(
      `/api/v2/resources/forest-subcompartments/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  deleteForestSubcompartment: (id: string) =>
    request<{ ok: boolean; deleted: string; version: number }>(
      `/api/v2/resources/forest-subcompartments/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),
  forestSubcompartmentVersions: (id: string) =>
    request<LedgerResponse<SpatialVersionRecord>>(
      `/api/v2/resources/forest-subcompartments/${encodeURIComponent(id)}/versions`,
    ),
  rollbackForestSubcompartment: (id: string, versionId: string, expectedVersion: number) =>
    request<{ ok: boolean; record: ForestSubcompartmentRecord }>(
      `/api/v2/resources/forest-subcompartments/${encodeURIComponent(id)}/rollback`,
      { method: "POST", body: JSON.stringify({ versionId, expectedVersion }) },
    ),
  resourceSurveys: (query: ResourceSurveyQuery = {}) =>
    request<LedgerResponse<ResourceSurveyRecord>>(
      `/api/v2/resources/resource-surveys?${queryString(query)}`,
    ),
  resourceSurvey: (id: string) =>
    request<ResourceSurveyRecord>(`/api/v2/resources/resource-surveys/${encodeURIComponent(id)}`),
  createResourceSurvey: (payload: ResourceSurveyPayload) =>
    request<ResourceSurveyRecord>("/api/v2/resources/resource-surveys", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateResourceSurvey: (id: string, payload: Partial<ResourceSurveyPayload> & { expectedVersion: number }) =>
    request<ResourceSurveyRecord>(`/api/v2/resources/resource-surveys/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteResourceSurvey: (id: string) =>
    request<{ ok: boolean; deleted: string; version: number }>(
      `/api/v2/resources/resource-surveys/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),
  resourceSnapshots: (surveyId: string, query: { q?: string; forestSubcompartmentId?: string; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<ResourceSnapshotRecord>>(
      `/api/v2/resources/resource-surveys/${encodeURIComponent(surveyId)}/snapshots?${queryString(query)}`,
    ),
  createResourceSnapshot: (surveyId: string, payload: ResourceSnapshotPayload) =>
    request<ResourceSnapshotRecord>(
      `/api/v2/resources/resource-surveys/${encodeURIComponent(surveyId)}/snapshots`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  updateResourceSnapshot: (id: string, payload: Partial<ResourceSnapshotPayload> & { expectedVersion: number }) =>
    request<ResourceSnapshotRecord>(`/api/v2/resources/resource-snapshots/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteResourceSnapshot: (id: string) =>
    request<{ ok: boolean; deleted: string; version: number }>(
      `/api/v2/resources/resource-snapshots/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),
  resourceSnapshotComparison: (id: string) =>
    request<ResourceSnapshotComparison>(
      `/api/v2/resources/resource-snapshots/${encodeURIComponent(id)}/comparison`,
    ),
  resourceSnapshotVersions: (id: string) =>
    request<{ items: ResourceSnapshotVersionRecord[]; total: number }>(
      `/api/v2/resources/resource-snapshots/${encodeURIComponent(id)}/versions`,
    ),
  attachments: (query: AttachmentQuery = {}) =>
    request<LedgerResponse<AttachmentRecord>>(`/api/v2/attachments?${queryString(query)}`),
  attachment: (id: string) =>
    request<AttachmentRecord>(`/api/v2/attachments/${encodeURIComponent(id)}`),
  uploadAttachment: (file: File, category: string, description = "") => {
    const body = new FormData();
    body.append("file", file);
    body.append("category", category);
    body.append("description", description);
    return request<AttachmentRecord>("/api/v2/attachments", { method: "POST", body });
  },
  updateAttachment: (id: string, payload: { expectedVersion: number; category?: string; description?: string | null }) =>
    request<AttachmentRecord>(`/api/v2/attachments/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteAttachment: (id: string) =>
    request<{ ok: boolean; deleted: string; version: number }>(`/api/v2/attachments/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreAttachment: (id: string) =>
    request<AttachmentRecord>(`/api/v2/attachments/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  forestRightLedger: (query: ForestRightQuery) =>
    request<LedgerResponse<ForestRightRecord>>(
      `/api/v2/resources/forest-rights?${queryString(query)}`,
    ),
  forestRightDetail: (id: string) =>
    request<ForestRightRecord>(`/api/v2/resources/forest-rights/${encodeURIComponent(id)}`),
  createForestRight: (payload: ForestRightPayload) =>
    request<ForestRightRecord>("/api/v2/resources/forest-rights", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateForestRight: (id: string, payload: Partial<ForestRightPayload>) =>
    request<ForestRightRecord>(`/api/v2/resources/forest-rights/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteForestRight: (id: string) =>
    request<{ ok: boolean; deleted: string }>(
      `/api/v2/resources/forest-rights/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),
  importJobs: () => request<LedgerResponse<ImportJob>>("/api/v2/imports/jobs?limit=20"),
  createImportJob: (file: File, strategy: "upsert" | "skip") => {
    const body = new FormData();
    body.append("file", file);
    body.append("strategy", strategy);
    return request<ImportJob>("/api/v2/imports/jobs", { method: "POST", body });
  },
  confirmImportJob: (id: string) =>
    request<ImportJob>(`/api/v2/imports/jobs/${encodeURIComponent(id)}/confirm`, {
      method: "POST",
      body: JSON.stringify({ skipInvalidRows: true }),
    }),
  commitImportJob: (id: string) =>
    request<ImportJob>(`/api/v2/imports/jobs/${encodeURIComponent(id)}/commit`, {
      method: "POST",
    }),
  exportImportIssues: (id: string) =>
    downloadFile(
      `/api/v2/imports/jobs/${encodeURIComponent(id)}/issues.csv`,
      `导入质检问题-${id}.csv`,
    ),
  patrolTasks: (query: { q?: string; status?: string; linkedBlockCode?: string; includeDeleted?: boolean; limit?: number; offset?: number }) =>
    request<LedgerResponse<PatrolTask>>(`/api/v2/patrol/tasks?${queryString(query)}`),
  patrolTask: (id: string) =>
    request<PatrolTask>(`/api/v2/patrol/tasks/${encodeURIComponent(id)}`),
  createPatrolTask: (payload: PatrolTaskPayload) =>
    request<PatrolTask>("/api/v2/patrol/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updatePatrolTask: (id: string, payload: Partial<PatrolTaskPayload>) =>
    request<PatrolTask>(`/api/v2/patrol/tasks/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deletePatrolTask: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/v2/patrol/tasks/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restorePatrolTask: (id: string) =>
    request<PatrolTask>(`/api/v2/patrol/tasks/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  applyPatrolAction: (id: string, action: string, payload: PatrolActionPayload = {}) =>
    request<PatrolTask>(`/api/v2/patrol/tasks/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  harvestSubjects: (query = "", subjectType = "") =>
    request<{ items: HarvestSubject[]; total: number }>(
      `/api/v2/harvest/subjects?${queryString({ q: query, subjectType })}`,
    ),
  harvestQuotas: (year?: number) =>
    request<{ items: HarvestQuota[]; total: number }>(
      `/api/v2/harvest/quotas?${queryString({ year })}`,
    ),
  harvestApplications: (query: { q?: string; status?: string; linkedBlockCode?: string; includeDeleted?: boolean; limit?: number; offset?: number }) =>
    request<LedgerResponse<HarvestApplication>>(`/api/v2/harvest/applications?${queryString(query)}`),
  harvestApplication: (id: string) =>
    request<HarvestApplication>(`/api/v2/harvest/applications/${encodeURIComponent(id)}`),
  createHarvestApplication: (payload: HarvestApplicationPayload) =>
    request<HarvestApplication>("/api/v2/harvest/applications", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateHarvestApplication: (id: string, payload: Partial<HarvestApplicationPayload>) =>
    request<HarvestApplication>(`/api/v2/harvest/applications/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteHarvestApplication: (id: string) =>
    request<HarvestApplication>(`/api/v2/harvest/applications/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreHarvestApplication: (id: string) =>
    request<HarvestApplication>(`/api/v2/harvest/applications/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  applyHarvestAction: (id: string, action: string, payload: HarvestActionPayload = {}) =>
    request<HarvestApplication>(`/api/v2/harvest/applications/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  laborWorkers: (query: { q?: string; status?: string; includeDeleted?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<LaborWorker>>(`/api/v2/labor/workers?${queryString(query)}`),
  createLaborWorker: (payload: LaborWorkerPayload) =>
    request<LaborWorker>("/api/v2/labor/workers", { method: "POST", body: JSON.stringify(payload) }),
  updateLaborWorker: (id: string, payload: Partial<LaborWorkerPayload>) =>
    request<LaborWorker>(`/api/v2/labor/workers/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteLaborWorker: (id: string) =>
    request<LaborWorker>(`/api/v2/labor/workers/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreLaborWorker: (id: string) =>
    request<LaborWorker>(`/api/v2/labor/workers/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  laborTeams: (query: { q?: string; status?: string; includeDeleted?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<LaborTeam>>(`/api/v2/labor/teams?${queryString(query)}`),
  createLaborTeam: (payload: LaborTeamPayload) =>
    request<LaborTeam>("/api/v2/labor/teams", { method: "POST", body: JSON.stringify(payload) }),
  updateLaborTeam: (id: string, payload: Partial<LaborTeamPayload>) =>
    request<LaborTeam>(`/api/v2/labor/teams/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteLaborTeam: (id: string) =>
    request<LaborTeam>(`/api/v2/labor/teams/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreLaborTeam: (id: string) =>
    request<LaborTeam>(`/api/v2/labor/teams/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  laborJobs: (query: { q?: string; status?: string; linkedBlockCode?: string; includeDeleted?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<LaborJob>>(`/api/v2/labor/jobs?${queryString(query)}`),
  laborJob: (id: string) => request<LaborJob>(`/api/v2/labor/jobs/${encodeURIComponent(id)}`),
  createLaborJob: (payload: LaborJobPayload) =>
    request<LaborJob>("/api/v2/labor/jobs", { method: "POST", body: JSON.stringify(payload) }),
  updateLaborJob: (id: string, payload: LaborJobPayload) =>
    request<LaborJob>(`/api/v2/labor/jobs/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteLaborJob: (id: string) =>
    request<LaborJob>(`/api/v2/labor/jobs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreLaborJob: (id: string) =>
    request<LaborJob>(`/api/v2/labor/jobs/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  applyLaborAction: (id: string, action: string, payload: LaborActionPayload = {}) =>
    request<LaborJob>(`/api/v2/labor/jobs/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`, {
      method: "POST", body: JSON.stringify(payload),
    }),
  safetyEvents: (query: { q?: string; status?: string; severity?: string; linkedBlockCode?: string; overdueOnly?: boolean; includeDeleted?: boolean; limit?: number; offset?: number }) =>
    request<LedgerResponse<SafetyEvent>>(`/api/v2/safety/events?${queryString(query)}`),
  safetyEvent: (id: string) =>
    request<SafetyEvent>(`/api/v2/safety/events/${encodeURIComponent(id)}`),
  createSafetyEvent: (payload: SafetyEventPayload) =>
    request<SafetyEvent>("/api/v2/safety/events", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateSafetyEvent: (id: string, payload: SafetyEventPayload) =>
    request<SafetyEvent>(`/api/v2/safety/events/${encodeURIComponent(id)}`, {
      method: "PATCH", body: JSON.stringify(payload),
    }),
  deleteSafetyEvent: (id: string) =>
    request<SafetyEvent>(`/api/v2/safety/events/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreSafetyEvent: (id: string) =>
    request<SafetyEvent>(`/api/v2/safety/events/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  applySafetyEventAction: (id: string, action: string, payload: SafetyActionPayload = {}) =>
    request<SafetyEvent>(`/api/v2/safety/events/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  safetyAlerts: (query: { q?: string; status?: string; severity?: string; limit?: number; offset?: number }) =>
    request<LedgerResponse<SafetyAlert>>(`/api/v2/safety/alerts?${queryString(query)}`),
  applySafetyAlertAction: (id: string, action: string, payload: SafetyActionPayload = {}) =>
    request<{ alert: SafetyAlert; event?: SafetyEvent } | SafetyAlert>(`/api/v2/safety/alerts/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  iotDevices: (query: { q?: string; status?: string; deviceType?: string; linkedBlockCode?: string; includeDeleted?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<IotDevice>>(`/api/v2/iot/devices?${queryString(query)}`),
  situationAssets: () => request<SituationAssetResponse>("/api/v2/iot/situation-assets"),
  seedSituationAssets: () => request<{ ok: boolean; created: string[]; existing: string[]; skipped: string[] }>("/api/v2/iot/situation-assets/seed", { method: "POST" }),
  iotDeviceOptions: (deviceType = "") =>
    request<{ items: IotDevice[]; total: number }>(`/api/v2/iot/devices/options?${queryString({ deviceType, limit: 200 })}`),
  iotDevice: (id: string) => request<IotDevice>(`/api/v2/iot/devices/${encodeURIComponent(id)}`),
  createIotDevice: (payload: IotDevicePayload) =>
    request<IotDevice>("/api/v2/iot/devices", { method: "POST", body: JSON.stringify(payload) }),
  updateIotDevice: (id: string, payload: Partial<IotDevicePayload>) =>
    request<IotDevice>(`/api/v2/iot/devices/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteIotDevice: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/v2/iot/devices/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreIotDevice: (id: string) =>
    request<IotDevice>(`/api/v2/iot/devices/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  addDeviceMaintenance: (id: string, payload: DeviceMaintenancePayload) =>
    request<IotDevice>(`/api/v2/iot/devices/${encodeURIComponent(id)}/maintenance`, { method: "POST", body: JSON.stringify(payload) }),
  droneMissions: (query: { q?: string; status?: string; linkedBlockCode?: string; deviceId?: string; includeDeleted?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<DroneMission>>(`/api/v2/drone/missions?${queryString(query)}`),
  droneMission: (id: string) => request<DroneMission>(`/api/v2/drone/missions/${encodeURIComponent(id)}`),
  createDroneMission: (payload: DroneMissionPayload) =>
    request<DroneMission>("/api/v2/drone/missions", { method: "POST", body: JSON.stringify(payload) }),
  updateDroneMission: (id: string, payload: Partial<DroneMissionPayload>) =>
    request<DroneMission>(`/api/v2/drone/missions/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteDroneMission: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/v2/drone/missions/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreDroneMission: (id: string) =>
    request<DroneMission>(`/api/v2/drone/missions/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  applyDroneMissionAction: (id: string, action: string, payload: DroneMissionActionPayload = {}) =>
    request<DroneMission>(`/api/v2/drone/missions/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`, { method: "POST", body: JSON.stringify(payload) }),
  imageryAssets: (query: { q?: string; status?: string; published?: boolean; includeDeleted?: boolean; bbox?: string; limit?: number; offset?: number } = {}) =>
    request<ImageryAssetResponse>(`/api/scenes?${queryString(query)}`),
  uploadImageryAsset: (file: File, payload: ImageryUploadPayload) => {
    const body = new FormData();
    body.append("file", file);
    body.append("name", payload.name);
    body.append("assetType", payload.assetType);
    body.append("missionId", payload.missionId || "");
    body.append("capturedAt", payload.capturedAt || "");
    body.append("resolution", payload.resolution || "");
    body.append("linkedBlockCodes", payload.linkedBlockCodes.join(","));
    body.append("processingStage", "ready");
    body.append("asyncMode", "false");
    return request<ImageryAsset>("/api/scenes/upload", { method: "POST", body });
  },
  updateImageryAsset: (id: string, payload: Partial<ImageryUploadPayload> & { visible?: boolean; opacity?: number }) =>
    request<ImageryAsset>(`/api/scenes/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteImageryAsset: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/scenes/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreImageryAsset: (id: string) =>
    request<{ scene: ImageryAsset }>(`/api/scenes/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  publishImageryAsset: (asset: ImageryAsset) =>
    request<{ ok: boolean; scene: ImageryAsset }>(`/api/scenes/${encodeURIComponent(asset.id)}/publish-layer`, {
      method: "POST",
      body: JSON.stringify({
        name: asset.name,
        linkedBlockCodes: asset.linkedBlockCodes,
        visibleOnDashboard: true,
        properties: { assetType: asset.assetType, missionId: asset.missionId, source: "v2-imagery-assets" },
      }),
    }),
  linkImageryAssetToBlock: (blockId: string, asset: ImageryAsset) =>
    request<{ item: unknown }>(`/api/forest-blocks/${encodeURIComponent(blockId)}/scenes`, {
      method: "POST",
      body: JSON.stringify({ sceneId: asset.id, relationType: "coverage", capturedAt: asset.capturedAt || null }),
    }),
  aiFindings: (query: { q?: string; status?: string; findingType?: string; linkedBlockCode?: string; includeDeleted?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<AiFinding>>(`/api/v2/ai/findings?${queryString(query)}`),
  aiFinding: (id: string) => request<AiFinding>(`/api/v2/ai/findings/${encodeURIComponent(id)}`),
  createAiFinding: (payload: AiFindingPayload) =>
    request<AiFinding>("/api/v2/ai/findings", { method: "POST", body: JSON.stringify(payload) }),
  updateAiFinding: (id: string, payload: Partial<AiFindingPayload>) =>
    request<AiFinding>(`/api/v2/ai/findings/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteAiFinding: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/v2/ai/findings/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreAiFinding: (id: string) =>
    request<AiFinding>(`/api/v2/ai/findings/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  applyAiFindingAction: (id: string, action: string, payload: AiFindingActionPayload = {}) =>
    request<AiFinding | { finding: AiFinding; alert: SafetyAlert }>(`/api/v2/ai/findings/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`, { method: "POST", body: JSON.stringify(payload) }),
  aiModelAssets: (query: { q?: string; assetType?: string; status?: string; includeDeleted?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<AiModelAsset>>(`/api/v2/ai/model-assets?${queryString(query)}`),
  aiModelAsset: (id: string) => request<AiModelAsset>(`/api/v2/ai/model-assets/${encodeURIComponent(id)}`),
  createAiModelAsset: (payload: AiModelAssetPayload) =>
    request<AiModelAsset>("/api/v2/ai/model-assets", { method: "POST", body: JSON.stringify(payload) }),
  updateAiModelAsset: (id: string, payload: Partial<AiModelAssetPayload>) =>
    request<AiModelAsset>(`/api/v2/ai/model-assets/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteAiModelAsset: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/v2/ai/model-assets/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreAiModelAsset: (id: string) =>
    request<AiModelAsset>(`/api/v2/ai/model-assets/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  aiInferenceRuns: (query: { q?: string; status?: string; modelAssetId?: string; linkedBlockCode?: string; includeDeleted?: boolean; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<AiInferenceRun>>(`/api/v2/ai/inference-runs?${queryString(query)}`),
  aiInferenceRun: (id: string) => request<AiInferenceRun>(`/api/v2/ai/inference-runs/${encodeURIComponent(id)}`),
  createAiInferenceRun: (payload: AiInferenceRunPayload) =>
    request<AiInferenceRun>("/api/v2/ai/inference-runs", { method: "POST", body: JSON.stringify(payload) }),
  updateAiInferenceRun: (id: string, payload: Partial<AiInferenceRunPayload>) =>
    request<AiInferenceRun>(`/api/v2/ai/inference-runs/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteAiInferenceRun: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/api/v2/ai/inference-runs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  restoreAiInferenceRun: (id: string) =>
    request<AiInferenceRun>(`/api/v2/ai/inference-runs/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  applyAiInferenceAction: (id: string, action: string, payload: AiInferenceActionPayload = {}) =>
    request<AiInferenceRun>(`/api/v2/ai/inference-runs/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`, { method: "POST", body: JSON.stringify(payload) }),
  createFindingFromInference: (id: string, payload: AiInferenceFindingPayload) =>
    request<{ run: AiInferenceRun; finding: AiFinding }>(`/api/v2/ai/inference-runs/${encodeURIComponent(id)}/finding`, { method: "POST", body: JSON.stringify(payload) }),
  mobileSyncOperations: (query: { q?: string; status?: string; userId?: string; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<MobileSyncOperationRecord>>(`/api/v2/mobile/operations?${queryString(query)}`),
  mobileOfflinePackage: () => request<MobileOfflinePackage>("/api/v2/mobile/offline-package"),
  syncMobileOperations: (operations: MobilePendingOperation[]) =>
    request<MobileSyncBatchResult>("/api/v2/mobile/sync", { method: "POST", body: JSON.stringify({ operations }) }),
  uploadMobileTrack: (payload: MobileTrackPayload) =>
    request<MobileTrackRecord>("/api/v2/mobile/tracks", { method: "POST", body: JSON.stringify(payload) }),
  createMobileUpload: (payload: { fileName: string; contentType: string; totalBytes: number; totalChunks: number; sha256: string; taskType: string; taskId: string }) =>
    request<MobileUploadSession>("/api/v2/mobile/uploads", { method: "POST", body: JSON.stringify(payload) }),
  mobileUploadStatus: (id: string) =>
    request<MobileUploadSession>(`/api/v2/mobile/uploads/${encodeURIComponent(id)}`),
  uploadMobileChunk: (id: string, index: number, blob: Blob, fileName: string) => {
    const body = new FormData();
    body.append("file", blob, fileName);
    return request<MobileUploadSession & { chunkIndex: number; chunkBytes: number }>(`/api/v2/mobile/uploads/${encodeURIComponent(id)}/chunks/${index}`, { method: "PUT", body });
  },
  completeMobileUpload: (id: string) =>
    request<MobileUploadSession>(`/api/v2/mobile/uploads/${encodeURIComponent(id)}/complete`, { method: "POST" }),
  resolveMobileSyncConflict: (id: string, strategy: "retry" | "discard", note: string) =>
    request<{ operation: MobileSyncOperationRecord; retryOperation: MobileSyncOperationRecord | null }>(`/api/v2/mobile/operations/${encodeURIComponent(id)}/resolve`, { method: "POST", body: JSON.stringify({ strategy, note }) }),
  mobileTracks: (query: { q?: string; status?: string; userId?: string; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<MobileTrackRecord>>(`/api/v2/mobile/tracks?${queryString(query)}`),
  mobileEvidence: (query: { q?: string; userId?: string; limit?: number; offset?: number } = {}) =>
    request<LedgerResponse<MobileEvidenceRecord>>(`/api/v2/mobile/evidence?${queryString(query)}`),
};
