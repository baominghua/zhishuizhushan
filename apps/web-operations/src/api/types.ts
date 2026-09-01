export type ModuleStatus = "available" | "planned";

export interface V2Module {
  key:
    | "workspace"
    | "operations-todos"
    | "operations-notifications"
    | "operations-audit"
    | "map"
    | "forest-blocks"
    | "forest-subcompartments"
    | "forest-roads"
    | "resourceSurveys"
    | "attachments"
    | "forest-rights"
    | "imports"
    | "patrol"
    | "harvest"
    | "labor"
    | "equipment"
    | "drone-missions"
    | "imagery-assets"
    | "ai-findings"
    | "ai-models"
    | "ai-inference"
    | "safety-events"
    | "mobile-operations"
    | "carbon-estimates"
    | "basemap-settings"
    | "system-overview"
    | "organizations"
    | "users"
    | "roles"
    | "dictionaries"
    | "permissions";
  label: string;
  path: string;
  requiredPermission: string;
  status: ModuleStatus;
  visible: boolean;
}

export interface CapabilitiesResponse {
  apiVersion: "v2";
  storagePolicy: string;
  principal: {
    user: string;
    roles: string[];
    principalType: string;
  };
  modules: V2Module[];
  permissions: string[];
}

export interface AdminOrganization {
  id: string;
  organizationCode: string;
  name: string;
  shortName: string | null;
  parentId: string | null;
  organizationType: "platform" | "government" | "department" | "town" | "village" | "enterprise" | "cooperative" | "project" | "team";
  status: string;
  sortOrder: number;
  leader: string | null;
  phone: string | null;
  address: string | null;
  administrativeDivisionCode: string | null;
  dataScopes: Record<string, unknown>;
  properties: Record<string, unknown>;
  userCount: number;
  childCount: number;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export type AdminOrganizationPayload = Omit<AdminOrganization, "id" | "userCount" | "childCount" | "createdAt" | "updatedAt" | "deletedAt">;

export interface AdminUser {
  id: string;
  username: string;
  displayName: string;
  status: string;
  roles: string[];
  dataScopes: Record<string, string[]>;
  properties: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export type AdminUserPayload = Pick<AdminUser, "username" | "displayName" | "status" | "roles" | "dataScopes" | "properties">;

export interface AdminRole {
  id: string;
  roleCode: string;
  name: string;
  status: string;
  permissions: string[];
  menuModules: string[];
  dataScopes: Record<string, string[]>;
  properties: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export type AdminRolePayload = Pick<AdminRole, "roleCode" | "name" | "status" | "permissions" | "menuModules" | "dataScopes" | "properties">;

export interface DictionaryTypeRecord {
  id: string;
  typeCode: string;
  name: string;
  category: string;
  hierarchyEnabled: boolean;
  valueMode: string;
  description: string;
  status: string;
  sortOrder: number;
  systemDefined: boolean;
  properties: Record<string, unknown>;
  itemCount: number;
  activeItemCount: number;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export type DictionaryTypePayload = Pick<DictionaryTypeRecord, "typeCode" | "name" | "category" | "hierarchyEnabled" | "valueMode" | "description" | "status" | "sortOrder" | "properties">;

export interface DictionaryItemRecord {
  id: string;
  dictionaryTypeId: string;
  typeCode: string;
  itemCode: string;
  label: string;
  parentItemId: string;
  parentCode: string;
  levelCode: string;
  fullName: string;
  pinyin: string;
  initials: string;
  searchAliases: string[];
  sortOrder: number;
  status: string;
  metadata: Record<string, unknown>;
  source: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export type DictionaryItemPayload = Pick<DictionaryItemRecord, "itemCode" | "label" | "parentCode" | "levelCode" | "fullName" | "pinyin" | "initials" | "searchAliases" | "sortOrder" | "status" | "metadata" | "source">;

export interface DictionaryImportResult {
  dryRun: boolean;
  mode: "append" | "upsert";
  received: number;
  created: number;
  updated: number;
  restored: number;
  errors: Array<{ row: number; itemCode: string; message: string }>;
  canCommit: boolean;
  preview: DictionaryItemRecord[];
  committed?: number;
}

export interface PermissionCatalogItem {
  code: string;
  label: string;
  module?: string;
  kind: string;
  kindLabel: string;
  apiScopes: string[];
  impliedPermissions?: string[];
}

export interface PermissionMenuModule {
  key: string;
  label: string;
  group: string;
  href: string;
  permission: string;
  permissions?: PermissionCatalogItem[];
}

export interface PermissionCatalogResponse {
  menuModules: PermissionMenuModule[];
  v2MenuModules?: PermissionMenuModule[];
  permissions: PermissionCatalogItem[];
  groups: string[];
  permissionImplications: Record<string, string[]>;
  rolePresets: Array<{ key: string; label: string; description?: string; permissions: string[]; menuModules: string[]; dataScopes?: Record<string, string[]> }>;
  coverage: Record<string, number>;
}

export interface WorkspaceSummary {
  source: "live";
  principal: { user: string; roles: string[] };
  metrics: {
    forestBlocks: number;
    forestRights: number;
    openQualityIssues: number;
  };
  todos: OperationsTodo[];
  alerts: OperationsAuditEvent[];
  moduleAvailability: Record<string, "available" | "planned">;
  emptyState: string;
}

export interface ForestBlockOption {
  id: string;
  code: string;
  name: string;
  location: string;
  areaMu: number | null;
  hasGeometry: boolean;
  riskLevel: string | null;
}

export interface ForestBlockOptionsResponse {
  kind: "forest-block";
  items: ForestBlockOption[];
  total: number;
  limit: number;
  offset: number;
}

export interface ForestRightOption {
  id: string;
  code: string;
  certificateNo: string;
  holder: string;
  status: string;
  linkedBlockCodes: string[];
}

export interface ForestRightOptionsResponse {
  kind: "forest-right";
  items: ForestRightOption[];
  total: number;
  limit: number;
  offset: number;
}

export interface MapConfigResponse {
  provider: "tianditu";
  available: boolean;
  accessMode: "server-proxy" | "web-direct";
  imageryUrl: string;
  labelsUrl: string;
  maximumLevel: number;
  message: string;
}

export type ImageryAssetType = "orthophoto" | "dsm" | "dtm" | "oblique3d" | "pointcloud" | "flight-photos";

export interface SpatialCoverageMatch {
  blockId: string;
  blockCode: string;
  blockName: string;
  location: string;
  blockAreaMu: number | null;
  intersectionAreaHa: number;
  blockCoveragePercent: number;
  imageryCoveragePercent: number;
  suggested: boolean;
}

export interface SpatialCoverageAnalysis {
  algorithmVersion: string;
  analyzedAt: string;
  effectiveAreaHa?: number;
  footprintBounds?: [number, number, number, number];
  matches: SpatialCoverageMatch[];
  suggestedBlockCodes: string[];
  requiresConfirmation: boolean;
  confirmedAt?: string | null;
  confirmedBy?: string;
  confirmedBlockCodes?: string[];
  error?: string;
}

export interface ImageryAsset {
  id: string;
  name: string;
  fileName: string;
  fileType: string;
  size: number;
  originalSize: number;
  assetType: ImageryAssetType;
  missionId: string;
  linkedBlockCodes: string[];
  spatialRelation?: {
    type: "forest-block" | "independent-point";
    pointName?: string;
    pointCategory?: string;
    longitude?: number;
    latitude?: number;
  };
  processingStage: string;
  capturedAt: string;
  resolution: string;
  bounds: [number, number, number, number];
  crs: string;
  width: number;
  height: number;
  bands: number;
  opacity: number;
  visible: boolean;
  status?: string;
  transferStatus: string;
  publishedLayerId?: string;
  publishedLayerRecordCode?: string;
  tileUrl: string;
  tileJsonUrl: string;
  thumbnailUrl: string;
  originalDownloadUrl?: string;
  archiveDownloadUrl?: string;
  resourceFormats?: string[];
  recordedAt?: string;
  recordedAtSource?: "captured" | "uploaded";
  temporalSeriesKey?: string;
  tileFormat?: "webp" | "png" | string;
  metresPerPixel?: number;
  maximumZoom?: number;
  coverageAnalysis?: SpatialCoverageAnalysis;
  footprint?: { type: string; coordinates: unknown };
  pointCount?: number;
  pointCloudFileCount?: number;
  pointCloudVersions?: string[];
  pointCloudFormats?: number[];
  pointCloudDimensions?: string[];
  pointCloudAttributeModes?: Array<"rgb" | "elevation" | "return" | "intensity" | "gps-time">;
  pointCloudRenderableModes?: Array<"rgb" | "elevation" | "return" | "intensity">;
  pointCloudRenderableProperties?: Partial<Record<"return" | "intensity", string>>;
  pointCloudSourcePaths?: string[];
  trajectoryAvailable?: boolean;
  trajectoryFileCount?: number;
  trajectorySize?: number;
  trajectoryFormats?: string[];
  trajectoryPath?: string;
  tilesetCount?: number;
  tileCount?: number;
  tileFormats?: Record<string, number>;
  tilesetAssetVersions?: string[];
  tilesetContentType?: "pnts" | "b3dm" | "mixed" | "3dtiles" | string;
  tilesetSource?: string;
  tilesetVersionNormalized?: boolean;
  nativeBounds?: [number, number, number, number, number, number];
  copcUrl?: string;
  tilesetUrl?: string;
  createdAt: string;
  updatedAt: string;
  deletedAt?: string | null;
}

export interface ImageryAssetResponse {
  scenes: ImageryAsset[];
  total: number;
  limit: number;
  offset: number;
  bbox: [number, number, number, number] | null;
  summary: {
    byAssetType: Record<string, number>;
    byResourceFormat: Record<string, number>;
    pendingCoverage: number;
    published: number;
  };
}

export interface ImageryUploadPayload {
  name: string;
  assetType: ImageryAssetType;
  missionId?: string;
  capturedAt?: string;
  resolution?: string;
  linkedBlockCodes: string[];
}

export interface ImageryInventoryResponse {
  total: number;
  typeCount: number;
  totalAreaMu: number;
  totalSizeBytes: number;
  areaUnit: "亩" | string;
  areaMethod: string;
  asOf: string;
  items: Array<{ assetType: string; count: number; areaMu: number; sizeBytes: number }>;
  bambooResources: {
    formal: {
      available: boolean;
      stock: number | null;
      unit: string;
      blockCount: number;
      snapshotCount: number;
      surveyedAreaMu: number | null;
      standingVolumeM3: number | null;
      biomassTons: number | null;
      source: string;
    };
    estimated: { available: boolean; stock: number | null; unit: string; biomassTons: number | null; blockCount: number; source: string; estimatedAt: string };
    policy: string;
  };
}

export interface ImageryCoverageConfirmationPayload {
  blockCodes: string[];
  relationType?: "forest-block" | "independent-point";
  pointName?: string;
  pointCategory?: string;
  longitude?: number;
  latitude?: number;
}

export interface SpatialAssetTask {
  id: string;
  type: string;
  name?: string;
  kind?: string;
  status: "queued" | "running" | "completed" | "failed" | "canceled" | string;
  progress: number;
  message: string;
  sceneId: string;
  assetType?: ImageryAssetType;
  sceneUrl?: string;
  scene?: ImageryAsset;
  sourceBytes?: number;
  outputBytes?: number;
  sourceFileCount?: number;
  createdAt?: string;
  startedAt?: string;
  completedAt?: string;
  failedAt?: string;
  heartbeatAt?: string;
  retryAttempt?: number;
  retryOf?: string;
  archivedAt?: string;
}

export interface SpatialAssetTaskResponse {
  tasks: SpatialAssetTask[];
  total: number;
  limit: number;
  offset: number;
}

export interface PointCloudUploadFileState {
  index: number;
  name: string;
  size: number;
  chunkSize: number;
  totalChunks: number;
  receivedChunks: number[];
  uploadedBytes: number;
}

export interface PointCloudUploadSession {
  id: string;
  name: string;
  missionId: string;
  capturedAt: string;
  status: string;
  outputs: Array<"copc" | "3dtiles">;
  files: PointCloudUploadFileState[];
  uploadedBytes: number;
  totalBytes: number;
  progress: number;
  taskId: string;
  createdAt: string;
  updatedAt: string;
}

export interface BasemapSettingsResponse {
  provider: "tianditu";
  available: boolean;
  hasServerKey: boolean;
  serverKeyMasked: string;
  hasWebKey: boolean;
  webKeyMasked: string;
  hasAndroidKey: boolean;
  androidKeyMasked: string;
  hasIosKey: boolean;
  iosKeyMasked: string;
  webDirectEnabled: boolean;
  proxyBaseUrl: string;
  referer: string;
  source: "stored" | "environment";
}

export interface BasemapSettingsPayload {
  serverKey: string;
  webKey: string;
  androidKey: string;
  iosKey: string;
  webDirectEnabled: boolean;
  proxyBaseUrl: string;
  referer: string;
}

export type ForestBlockGeometry = {
  type: "Polygon" | "MultiPolygon";
  coordinates: unknown[];
};

export interface ForestBlockMapFeature {
  type: "Feature";
  id: string;
  geometry: ForestBlockGeometry | null;
  properties: Omit<ForestBlockRecord, "geometry">;
}

export interface ForestBlockFeatureCollection {
  type: "FeatureCollection";
  meta: {
    total: number;
    returned: number;
    maxFeatures: number;
    truncated: boolean;
    zoom: number;
    geometryMode: "full" | "simplified";
    simplificationTolerance: number;
    /** Browser-observed API round trip. Added client-side for GIS diagnostics. */
    requestDurationMs?: number;
  };
  features: ForestBlockMapFeature[];
}

export interface LedgerResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface CarbonEstimateRecord {
  id: string;
  projectCode: string;
  name: string;
  accountingType: "stock" | "increment" | "project";
  verificationStatus: "calculating" | "review" | "verified" | "rejected";
  projectBoundary: string;
  methodology: string;
  accountingStartDate: string;
  accountingEndDate: string;
  accountingAreaMu: number | null;
  carbonStock: number | null;
  annualSequestration: number | null;
  verifiedAmount: number | null;
  carbonPrice: number | null;
  estimatedRevenue: number | null;
  verificationAgency: string;
  verificationDate: string;
  beneficiary: string;
  notes: string;
  linkedBlockCodes: string[];
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export type CarbonEstimatePayload = Omit<CarbonEstimateRecord, "id" | "createdAt" | "updatedAt" | "deletedAt">;

export interface CarbonEstimateQuery {
  q?: string;
  verificationStatus?: string;
  linkedBlockCode?: string;
  limit?: number;
  offset?: number;
}

export interface CarbonEstimateLedgerResponse extends LedgerResponse<CarbonEstimateRecord> {
  summary: {
    accountingAreaMu: number;
    annualSequestration: number;
    verifiedAmount: number;
    estimatedRevenue: number;
  };
}

export interface CockpitMetric {
  value: number | null;
  unit: string;
  available: boolean;
  source: string;
}

export interface CockpitRankingItem {
  name: string;
  projects: number;
  annualSequestration: number;
  verifiedAmount: number;
}

export interface LeadershipCockpitResponse {
  source: string;
  asOf: string;
  scope: { user: string; roles: string[]; areas: string[] };
  overview: Record<string, CockpitMetric>;
  carbon: Record<string, CockpitMetric | CockpitRankingItem[] | Array<{ status: string; count: number }> | Array<{ period: string; price: number }>>;
  operations: Record<string, CockpitMetric>;
  availability: Record<string, boolean>;
}

export interface ForestBlockRecord {
  id: string;
  blockCode: string;
  name: string;
  countyCode: string | null;
  countyName: string | null;
  townCode: string | null;
  townName: string | null;
  villageCode: string | null;
  villageName: string | null;
  baseType: string | null;
  operationType: string | null;
  forestType: string | null;
  areaMu: number | null;
  slopeDegree: number | null;
  qualityGrade: string | null;
  healthStatus: string | null;
  riskLevel: string | null;
  bambooAge: string | null;
  avgDbhCm: number | null;
  avgHeightM: number | null;
  standingDensity: number | null;
  carbonEstimateTco2e: number | null;
  yieldEstimate: Record<string, unknown>;
  tags: string[];
  properties: Record<string, unknown>;
  geometry: Record<string, unknown> | null;
  sourceBatchId: string | null;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export interface MosoInventoryEstimate {
  modelVersion: string;
  status: "trial" | string;
  species: string;
  scientificName?: string;
  estimatedAt: string;
  blockArea: { value: number; unit: string };
  canopyClosure: { value: number; unit: string };
  crownEquivalentCount: { value: number; unit: string };
  resourceStock: { value: number; lower: number; upper: number; unit: string; label: string; basis?: string };
  stemDensity: { value: number; lower: number; upper: number; unit: string };
  abovegroundBiomass: { value: number; lower: number; upper: number; unit: string; dbhCm: number; dbhSource: string };
  standingVolume: { value: number | null; unit: string; status: string; reason: string };
  confidence: { score: number; level: string; reasons: string[] };
  imageryEvidence: Record<string, unknown>;
  crownCandidateLocations?: Array<{ longitude: number; latitude: number; score: number }>;
  crownCandidateLocationCount?: number;
  crownCandidateLocationsComplete?: boolean;
  pointCloudEvidence: Record<string, unknown> & { available?: boolean };
  method?: { name?: string; assumption?: string; references?: Array<Record<string, unknown>> };
  disclaimer: string;
}

export interface MosoInventoryEstimateResponse {
  estimate: MosoInventoryEstimate;
  saved: boolean;
  block?: ForestBlockRecord;
}

export interface MosoInventoryBatchTask {
  id: string;
  type: "moso-bamboo-inventory" | string;
  status: string;
  progress: number;
  message: string;
  blockTotal: number;
  result?: {
    completed: Array<{ blockId: string; blockCode: string; estimatedCulms: number }>;
    failed: Array<{ blockId: string; blockCode: string; message: string }>;
  };
}

export interface ForestBlockPayload {
  blockCode: string;
  name: string;
  countyCode?: string | null;
  countyName?: string | null;
  townCode?: string | null;
  townName?: string | null;
  villageCode?: string | null;
  villageName?: string | null;
  baseType?: string | null;
  operationType?: string | null;
  forestType?: string | null;
  areaMu?: number | null;
  slopeDegree?: number | null;
  qualityGrade?: string | null;
  healthStatus?: string | null;
  riskLevel?: string | null;
  bambooAge?: string | null;
  avgDbhCm?: number | null;
  avgHeightM?: number | null;
  standingDensity?: number | null;
  carbonEstimateTco2e?: number | null;
  yieldEstimate?: Record<string, unknown>;
  tags?: string[];
  properties?: Record<string, unknown>;
  geometry?: Record<string, unknown> | null;
}

export interface SpatialVersionRecord {
  id: string;
  changeType: "create" | "update" | "delete" | "rollback" | string;
  version?: number;
  snapshot: Record<string, unknown>;
  createdBy: string;
  createdAt: string;
  sourceVersionId?: string;
}

export interface ForestBlockQuery {
  q?: string;
  countyCode?: string;
  townCode?: string;
  villageCode?: string;
  baseType?: string;
  operationType?: string;
  qualityGrade?: string;
  healthStatus?: string;
  riskLevel?: string;
  includeDeleted?: boolean;
  limit?: number;
  offset?: number;
}

export interface ForestBlockFilterFacets {
  total: number;
  counties: Array<{ code: string; name: string }>;
  towns: Array<{ code: string; name: string; countyCode: string }>;
  qualityGrades: string[];
  healthStatuses: string[];
  riskLevels: string[];
  baseTypes: string[];
  operationTypes: string[];
}

export interface ForestBlockAggregateItem {
  code: string;
  name: string;
  blockCount: number;
  areaMu: number;
  centroid: [number, number] | null;
  riskLevel: string;
  riskCounts: Record<string, number>;
  qualityCounts: Record<string, number>;
}

export interface ForestBlockAggregateResponse {
  level: "county" | "town" | "village";
  totalGroups: number;
  totalBlocks: number;
  totalAreaMu: number;
  items: ForestBlockAggregateItem[];
}

export interface AdministrativeDivisionItem {
  code: string;
  name: string;
  parentCode: string;
  level: "province" | "city" | "county" | "town" | "village";
  fullName: string;
}

export interface AdministrativeDivisionResponse {
  items: AdministrativeDivisionItem[];
  total: number;
  level: AdministrativeDivisionItem["level"];
  parentCode: string;
}

export interface ForestSubcompartmentOption {
  id: string;
  code: string;
  name: string;
  forestBlockId: string;
  forestBlockCode: string;
  forestBlockName: string;
  location: string;
  areaMu: number | null;
  hasGeometry: boolean;
  riskLevel: string | null;
}

export interface ForestSubcompartmentOptionsResponse {
  kind: "forest-subcompartment";
  items: ForestSubcompartmentOption[];
  total: number;
  limit: number;
  offset: number;
}

export interface ForestSubcompartmentRecord {
  id: string;
  subcompartmentCode: string;
  name: string;
  forestBlockId: string;
  forestBlockCode: string;
  forestBlockName: string;
  countyCode: string | null;
  countyName: string | null;
  townCode: string | null;
  townName: string | null;
  villageCode: string | null;
  villageName: string | null;
  areaMu: number | null;
  landCategory: string | null;
  forestCategory: string | null;
  origin: string | null;
  ageGroup: string | null;
  bambooSpecies: string | null;
  slopeDegree: number | null;
  aspect: string | null;
  elevationM: number | null;
  qualityGrade: string | null;
  healthStatus: string | null;
  riskLevel: string | null;
  managementStatus: string | null;
  tags: string[];
  properties: Record<string, unknown>;
  geometry: Record<string, unknown> | null;
  sourceBatchId: string | null;
  version: number;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export interface ForestSubcompartmentPayload {
  subcompartmentCode: string;
  name: string;
  forestBlockId: string;
  areaMu?: number | null;
  landCategory?: string | null;
  forestCategory?: string | null;
  origin?: string | null;
  ageGroup?: string | null;
  bambooSpecies?: string | null;
  slopeDegree?: number | null;
  aspect?: string | null;
  elevationM?: number | null;
  qualityGrade?: string | null;
  healthStatus?: string | null;
  riskLevel?: string | null;
  managementStatus?: string | null;
  tags?: string[];
  properties?: Record<string, unknown>;
  geometry?: Record<string, unknown> | null;
}

export interface ForestSubcompartmentPatch extends Partial<Omit<ForestSubcompartmentPayload, "subcompartmentCode">> {
  expectedVersion: number;
}

export interface ForestSubcompartmentQuery {
  q?: string;
  forestBlockId?: string;
  countyCode?: string;
  townCode?: string;
  villageCode?: string;
  managementStatus?: string;
  riskLevel?: string;
  includeDeleted?: boolean;
  limit?: number;
  offset?: number;
}

export type RoadClass = "main" | "branch" | "operation" | "firebreak" | "footpath" | "other";
export type RoadSurface = "paved" | "gravel" | "earth" | "boardwalk" | "other";
export type RoadCondition = "good" | "fair" | "poor" | "closed";

export interface ForestRoadRecord {
  id: string;
  roadCode: string;
  name: string;
  roadClass: RoadClass;
  surfaceType: RoadSurface;
  condition: RoadCondition;
  widthM: number | null;
  lengthKm: number;
  linkedBlockCodes: string[];
  responsibleUnit: string;
  lastInspectedOn: string;
  notes: string;
  geometry: { type: "LineString" | "MultiLineString"; coordinates: unknown[] };
  version: number;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
  maintenance?: RoadMaintenanceRecord[];
}

export interface ForestRoadFeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    id: string;
    geometry: ForestRoadRecord["geometry"];
    properties: Pick<
      ForestRoadRecord,
      "id" | "roadCode" | "name" | "roadClass" | "surfaceType" | "condition" | "widthM" | "lengthKm" | "linkedBlockCodes"
    >;
  }>;
}

export interface ForestRoadPayload {
  roadCode: string;
  name: string;
  roadClass: RoadClass;
  surfaceType: RoadSurface;
  condition: RoadCondition;
  widthM?: number | null;
  lengthKm?: number | null;
  linkedBlockCodes: string[];
  responsibleUnit?: string;
  lastInspectedOn?: string;
  notes?: string;
  geometry: ForestRoadRecord["geometry"];
}

export interface RoadMaintenanceRecord {
  id: string;
  roadId: string;
  maintenanceType: "inspection" | "repair" | "clearing" | "drainage" | "closure" | "reopen";
  occurredOn: string;
  conditionAfter?: RoadCondition | null;
  costYuan?: number | null;
  responsibleUnit: string;
  note: string;
  createdBy: string;
  createdAt: string;
}

export interface RoadMaintenancePayload extends Omit<RoadMaintenanceRecord, "id" | "roadId" | "createdBy" | "createdAt"> {}

export interface ResourceSurveyRecord {
  id: string;
  surveyNo: string;
  name: string;
  surveyType: string;
  surveyDate: string;
  status: string;
  organization: string | null;
  surveyor: string | null;
  sourceType: string | null;
  method: string | null;
  notes: string | null;
  properties: Record<string, unknown>;
  snapshotCount: number;
  version: number;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  deletedAt: string | null;
}

export interface ResourceSurveyPayload {
  surveyNo: string;
  name: string;
  surveyType: string;
  surveyDate: string;
  status?: string;
  organization?: string | null;
  surveyor?: string | null;
  sourceType?: string | null;
  method?: string | null;
  notes?: string | null;
  properties?: Record<string, unknown>;
}

export interface ResourceSurveyQuery {
  q?: string;
  status?: string;
  surveyType?: string;
  includeDeleted?: boolean;
  limit?: number;
  offset?: number;
}

export interface ResourceSnapshotRecord {
  id: string;
  resourceSurveyId: string;
  previousSnapshotId: string | null;
  forestSubcompartmentId: string;
  surveyNo: string;
  surveyName: string;
  surveyDate: string;
  subcompartmentCode: string;
  subcompartmentName: string;
  forestBlockId: string;
  forestBlockCode: string;
  forestBlockName: string;
  sampledAt: string | null;
  areaMu: number | null;
  bambooSpecies: string | null;
  origin: string | null;
  ageGroup: string | null;
  bambooDensityPerMu: number | null;
  avgDbhCm: number | null;
  avgHeightM: number | null;
  standingVolumeM3: number | null;
  biomassT: number | null;
  carbonEstimateTco2e: number | null;
  qualityGrade: string | null;
  healthStatus: string | null;
  riskLevel: string | null;
  samplePlotCount: number | null;
  evidenceUrls: string[];
  attachmentIds: string[];
  attachments: AttachmentRecord[];
  properties: Record<string, unknown>;
  version: number;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export interface ResourceSnapshotPayload {
  forestSubcompartmentId: string;
  sampledAt?: string | null;
  areaMu?: number | null;
  bambooSpecies?: string | null;
  origin?: string | null;
  ageGroup?: string | null;
  bambooDensityPerMu?: number | null;
  avgDbhCm?: number | null;
  avgHeightM?: number | null;
  standingVolumeM3?: number | null;
  biomassT?: number | null;
  carbonEstimateTco2e?: number | null;
  qualityGrade?: string | null;
  healthStatus?: string | null;
  riskLevel?: string | null;
  samplePlotCount?: number | null;
  evidenceUrls?: string[];
  attachmentIds?: string[];
  properties?: Record<string, unknown>;
}

export interface AttachmentLink {
  id: string;
  attachmentId: string;
  entityType: string;
  entityId: string;
  relationType: string;
  createdBy: string | null;
  createdAt: string;
  deletedAt: string | null;
}

export interface AttachmentRecord {
  id: string;
  originalName: string;
  contentType: string | null;
  sizeBytes: number;
  sha256: string;
  category: string;
  description: string | null;
  status: "active" | "deleted";
  properties: Record<string, unknown>;
  version: number;
  uploadedBy: string | null;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
  links: AttachmentLink[];
  linkCount: number;
  downloadUrl: string | null;
}

export interface AttachmentQuery {
  q?: string;
  category?: string;
  entityType?: string;
  entityId?: string;
  includeDeleted?: boolean;
  limit?: number;
  offset?: number;
}

export interface ResourceSnapshotComparison {
  current: ResourceSnapshotRecord;
  previous: ResourceSnapshotRecord | null;
  changedCount: number;
  changes: Array<{ field: string; label: string; before: unknown; after: unknown; delta: number | null }>;
}

export interface ResourceSnapshotVersionRecord {
  id: string;
  resourceSnapshotId: string;
  changeType: "create" | "update" | "delete";
  version: number;
  snapshot: ResourceSnapshotRecord;
  createdBy: string | null;
  createdAt: string;
}

export interface ForestRightRecord {
  id: string;
  archiveCode: string;
  certificateNo: string | null;
  holder: string;
  certificateType: string | null;
  rightType: string | null;
  ownershipType: string | null;
  rightStart: string | null;
  rightEnd: string | null;
  contractNo: string | null;
  circulationStatus: string | null;
  archiveStatus: string | null;
  registrar: string | null;
  missingItems: string | null;
  areaMu: number | null;
  countyCode: string | null;
  countyName: string | null;
  townCode: string | null;
  townName: string | null;
  villageCode: string | null;
  villageName: string | null;
  linkedBlockIds: string[];
  linkedBlockCodes: string[];
  documents: Array<Record<string, unknown>>;
  properties: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export interface ForestRightPayload {
  archiveCode?: string | null;
  certificateNo?: string | null;
  holder: string;
  certificateType?: string | null;
  rightType?: string | null;
  ownershipType?: string | null;
  rightStart?: string | null;
  rightEnd?: string | null;
  contractNo?: string | null;
  circulationStatus?: string | null;
  archiveStatus?: string | null;
  registrar?: string | null;
  missingItems?: string | null;
  areaMu?: number | null;
  countyCode?: string | null;
  countyName?: string | null;
  townCode?: string | null;
  townName?: string | null;
  villageCode?: string | null;
  villageName?: string | null;
  linkedBlockIds?: string[];
  linkedBlockCodes?: string[];
  documents?: Array<Record<string, unknown>>;
  properties?: Record<string, unknown>;
}

export interface ForestRightQuery {
  q?: string;
  archiveStatus?: string;
  linkedBlockCode?: string;
  includeDeleted?: boolean;
  limit?: number;
  offset?: number;
}

export interface ImportJobIssue {
  id: string;
  row: number;
  code: string;
  severity: "blocking" | "warning";
  message: string;
  suggestion: string;
  blockCode: string;
  name: string;
}

export interface ImportJobPreview {
  row: number;
  blockCode: string;
  name: string;
  villageName: string;
  areaMu: number | null;
  hasGeometry: boolean;
  valid: boolean;
  warnings: number;
}

export interface ImportJob {
  id: string;
  fileName: string;
  fileType: string;
  sizeBytes: number;
  sha256: string;
  strategy: "upsert" | "skip";
  status: "needs_confirmation" | "ready_to_commit" | "completed" | "failed";
  phase: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  confirmedAt: string | null;
  committedAt: string | null;
  batchId: string | null;
  totalRows: number;
  validRows: number;
  invalidRows: number;
  existingRows: number;
  newRows: number;
  blockingIssues?: number;
  warningIssues?: number;
  qualityStatus?: "passed" | "warning" | "blocked";
  issues: ImportJobIssue[];
  preview: ImportJobPreview[];
  error?: string;
  commitSummary?: {
    totalRows: number;
    validRows: number;
    invalidRows: number;
    importedBlocks: number;
    importedRightsArchives: number;
  };
}

export type PatrolStatus =
  | "planned"
  | "assigned"
  | "accepted"
  | "patrolling"
  | "reported"
  | "resolved"
  | "verified"
  | "closed";

export interface PatrolTimelineEntry {
  id: string;
  action: string;
  label: string;
  status: PatrolStatus;
  actor: string;
  at: string;
  note: string;
}

export interface PatrolReport {
  summary?: string;
  issueType?: string;
  issueLevel?: string;
  locationText?: string;
  attachmentIds?: string[];
  trackPoints?: Record<string, unknown>[];
  distanceKm?: number | null;
  durationSeconds?: number | null;
  reportedAt?: string;
  reportedBy?: string;
}

export interface PatrolDisposition {
  summary?: string;
  result?: string;
  attachmentIds?: string[];
  resolvedAt?: string;
  resolvedBy?: string;
}

export interface PatrolTask {
  id: string;
  patrolNo: string;
  name: string;
  status: PatrolStatus;
  priority: "low" | "normal" | "high" | "urgent";
  plannedStartAt: string;
  plannedEndAt: string;
  assigneeName: string;
  instructions: string;
  linkedBlockCodes: string[];
  report: PatrolReport;
  disposition: PatrolDisposition;
  attachments: AttachmentRecord[];
  attachmentIds: string[];
  timeline: PatrolTimelineEntry[];
  deletedAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PatrolTaskPayload {
  name: string;
  priority: "low" | "normal" | "high" | "urgent";
  plannedStartAt: string;
  plannedEndAt: string;
  assigneeName: string;
  linkedBlockCodes: string[];
  instructions: string;
}

export interface PatrolActionPayload {
  assigneeName?: string;
  note?: string;
  summary?: string;
  issueType?: string;
  issueLevel?: string;
  locationText?: string;
  attachmentIds?: string[];
  dispositionSummary?: string;
  dispositionResult?: string;
  trackPoints?: Record<string, unknown>[];
  distanceKm?: number;
  durationSeconds?: number;
  clientOperationId?: string;
}

export type HarvestStatus =
  | "draft"
  | "submitted"
  | "quota_check"
  | "approving"
  | "approved"
  | "operating"
  | "verifying"
  | "completed";

export interface HarvestSubject {
  id: string;
  type: "farmer" | "cooperative" | "enterprise";
  code: string;
  name: string;
  status: string;
  linkedBlockCodes: string[];
}

export interface HarvestQuota {
  id: string;
  quotaYear: number;
  authorityName: string;
  forestType: string;
  blockCode: string;
  quotaAreaMu: number;
  quotaQuantityTon: number;
  usedAreaMu: number;
  usedQuantityTon: number;
  status: string;
  notes: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export interface HarvestTimelineEntry {
  id: string;
  action: string;
  fromStatus: string;
  toStatus: HarvestStatus;
  actor: string;
  note: string;
  data: Record<string, unknown>;
  createdAt: string;
}

export interface HarvestApplication {
  id: string;
  applicationNo: string;
  name: string;
  applicantType: HarvestSubject["type"];
  applicantId: string;
  applicantName: string;
  status: HarvestStatus;
  harvestType: "timber" | "shoot" | "tending";
  requestedAreaMu: number;
  requestedQuantityTon: number;
  quotaId: string;
  workStartAt: string;
  workEndAt: string;
  purpose: string;
  quotaCheck: {
    passed?: boolean;
    checkedAt?: string;
    reasons?: string[];
    remainingAreaMu?: number;
    remainingQuantityTon?: number;
  };
  approval: Record<string, unknown>;
  operation: {
    startedAt?: string;
    startedBy?: string;
    workWindow?: { startAt: string; endAt: string };
    geofence?: { mode: string; blockCodes: string[] };
    alerts?: Array<{
      id: string;
      type: string;
      level: string;
      message: string;
      locationText: string;
      deviceCode: string;
      reportedBy: string;
      reportedAt: string;
    }>;
  };
  verification: {
    reportedAt?: string;
    reportedBy?: string;
    actualAreaMu?: number;
    actualQuantityTon?: number;
    evidenceUrls?: string[];
    attachmentIds?: string[];
    workSummary?: string;
    decision?: string;
    verifiedBy?: string;
    verifiedAt?: string;
    note?: string;
  };
  version: number;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
  blocks: Array<{ id: string; code: string; declaredAreaMu: number }>;
  rights: Array<{ id: string; archiveCode: string }>;
  timeline: HarvestTimelineEntry[];
  attachments: AttachmentRecord[];
  attachmentIds: string[];
  batch: null | {
    id: string;
    batchNo: string;
    traceCode: string;
    actualAreaMu: number;
    actualQuantityTon: number;
    blockCodes: string[];
    resourceVersionIds: string[];
    createdBy: string;
    createdAt: string;
  };
}

export interface HarvestApplicationPayload {
  name: string;
  applicantType: HarvestSubject["type"];
  applicantId: string;
  harvestType: HarvestApplication["harvestType"];
  requestedAreaMu: number;
  requestedQuantityTon: number;
  quotaId: string;
  workStartAt: string;
  workEndAt: string;
  purpose: string;
  linkedBlockCodes: string[];
  linkedRightIds: string[];
}

export interface HarvestActionPayload {
  note?: string;
  actualAreaMu?: number;
  actualQuantityTon?: number;
  evidenceUrls?: string[];
  attachmentIds?: string[];
  alertType?: string;
  alertLevel?: string;
  alertMessage?: string;
  locationText?: string;
  deviceCode?: string;
}

export type SafetySeverity = "low" | "medium" | "high" | "critical";
export type SafetyEventStatus = "new" | "triaged" | "assigned" | "handling" | "resolved" | "verified" | "closed";
export type SafetyEventType = "fire" | "pest" | "theft" | "geofence" | "sos" | "equipment" | "weather" | "other";

export interface SafetyTimelineEntry {
  id: string;
  action: string;
  fromStatus: string;
  toStatus: SafetyEventStatus;
  actor: string;
  note: string;
  data: Record<string, unknown>;
  createdAt: string;
}

export interface SafetyEvent {
  id: string;
  incidentNo: string;
  title: string;
  eventType: SafetyEventType;
  severity: SafetySeverity;
  status: SafetyEventStatus;
  sourceType: "manual" | "device" | "patrol" | "harvest" | "ai" | "system" | "alert";
  sourceRef: string;
  locationText: string;
  longitude: number | null;
  latitude: number | null;
  responsibilityUnit: string;
  assigneeName: string;
  deadlineAt: string | null;
  description: string;
  resolution: {
    summary?: string;
    evidenceUrls?: string[];
    resolvedBy?: string;
    resolvedAt?: string;
  };
  review: Record<string, unknown>;
  version: number;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  closedAt: string | null;
  deletedAt: string | null;
  blocks: Array<{ id: string; code: string }>;
  timeline: SafetyTimelineEntry[];
}

export interface SafetyEventPayload {
  title: string;
  eventType: SafetyEventType;
  severity: SafetySeverity;
  sourceType: SafetyEvent["sourceType"];
  sourceRef: string;
  locationText: string;
  longitude?: number;
  latitude?: number;
  description: string;
  linkedBlockCodes: string[];
}

export interface SafetyActionPayload {
  note?: string;
  title?: string;
  eventType?: SafetyEventType;
  severity?: SafetySeverity;
  responsibilityUnit?: string;
  assigneeName?: string;
  deadlineAt?: string;
  resolutionSummary?: string;
  evidenceUrls?: string[];
  eventId?: string;
  linkedBlockCodes?: string[];
}

export interface SafetyAlert {
  id: string;
  alertNo: string;
  title: string;
  alertType: string;
  severity: SafetySeverity;
  status: "new" | "converted" | "merged" | "ignored";
  sourceType: "device" | "patrol" | "harvest" | "ai" | "system";
  sourceRef: string;
  deviceCode: string;
  locationText: string;
  longitude: number | null;
  latitude: number | null;
  description: string;
  linkedBlockCodes: string[];
  rawPayload: Record<string, unknown>;
  review: {
    decision?: string;
    reviewedBy?: string;
    reviewedAt?: string;
    note?: string;
  };
  eventId: string;
  occurredAt: string;
  createdAt: string;
  updatedAt: string;
}

export type LaborJobStatus = "draft" | "published" | "matched" | "contracted" | "working" | "submitted" | "settled" | "closed";

export interface LaborWorker {
  id: string;
  workerNo: string;
  name: string;
  mobile: string;
  idCardMask: string;
  gender: string;
  employmentStatus: "available" | "working" | "inactive";
  skillCodes: string[];
  qualifications: string[];
  trainingStatus: "valid" | "expiring" | "missing";
  creditScore: number;
  homeAddress: string;
  emergencyContact: string;
  notes: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export interface LaborWorkerPayload {
  name: string;
  mobile: string;
  idCardMask?: string;
  gender?: string;
  employmentStatus: LaborWorker["employmentStatus"];
  skillCodes: string[];
  qualifications: string[];
  trainingStatus: LaborWorker["trainingStatus"];
  creditScore?: number;
  homeAddress?: string;
  emergencyContact?: string;
  notes?: string;
}

export interface LaborTeamMember {
  id: string;
  workerNo: string;
  name: string;
  role: "leader" | "member";
  joinedAt: string;
}

export interface LaborTeam {
  id: string;
  teamNo: string;
  name: string;
  status: "active" | "busy" | "inactive";
  leaderWorkerId: string;
  leaderName: string;
  contactPhone: string;
  serviceArea: string;
  skillCodes: string[];
  notes: string;
  members: LaborTeamMember[];
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export interface LaborTeamPayload {
  name: string;
  status: LaborTeam["status"];
  leaderWorkerId: string;
  memberIds: string[];
  contactPhone?: string;
  serviceArea: string;
  skillCodes: string[];
  notes?: string;
}

export interface LaborAttendance {
  id: string;
  workerId: string;
  workerNo: string;
  workerName: string;
  workDate: string;
  checkInAt: string | null;
  checkOutAt: string | null;
  workHours: number;
  workQuantity: number | null;
  status: string;
  verifierName: string;
  note: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface LaborTimelineEntry {
  id: string;
  action: string;
  fromStatus: string;
  toStatus: string;
  actor: string;
  note: string;
  data: Record<string, unknown>;
  createdAt: string;
}

export interface LaborJob {
  id: string;
  jobNo: string;
  title: string;
  status: LaborJobStatus;
  employerType: "farmer" | "cooperative" | "enterprise" | "government" | "other";
  employerId: string;
  employerName: string;
  workType: "tending" | "harvest" | "transport" | "fertilization" | "pest-control" | "survey" | "other";
  requiredHeadcount: number;
  unitPrice: number;
  priceUnit: "mu" | "day" | "ton" | "job";
  plannedStartAt: string;
  plannedEndAt: string;
  teamId: string;
  teamName: string;
  contractNo: string;
  contractStartAt: string | null;
  contractEndAt: string | null;
  paymentTerms: string;
  actualQuantity: number | null;
  settlementAmount: number | null;
  settlement: { amount?: number; settledBy?: string; settledAt?: string; note?: string };
  instructions: string;
  version: number;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  closedAt: string | null;
  deletedAt: string | null;
  blocks: Array<{ id: string; code: string }>;
  attendance: LaborAttendance[];
  timeline: LaborTimelineEntry[];
}

export interface LaborJobPayload {
  title: string;
  employerType: LaborJob["employerType"];
  employerId?: string;
  employerName: string;
  workType: LaborJob["workType"];
  requiredHeadcount: number;
  unitPrice: number;
  priceUnit: LaborJob["priceUnit"];
  plannedStartAt: string;
  plannedEndAt: string;
  linkedBlockCodes: string[];
  instructions: string;
}

export interface LaborActionPayload {
  note?: string;
  teamId?: string;
  contractNo?: string;
  contractStartAt?: string;
  contractEndAt?: string;
  paymentTerms?: string;
  workerId?: string;
  workDate?: string;
  checkInAt?: string;
  checkOutAt?: string;
  workHours?: number;
  workQuantity?: number;
  attendanceStatus?: string;
  actualQuantity?: number;
  settlementAmount?: number;
  evidenceUrls?: string[];
}

export type DeviceType = "drone" | "helmet" | "sensor" | "camera" | "machinery" | "gateway" | "other";
export type DeviceStatus = "active" | "maintenance" | "retired";

export interface DeviceMaintenance {
  id: string;
  workOrderNo: string;
  maintenanceType: "inspection" | "repair" | "calibration" | "firmware" | "battery" | "other";
  status: "planned" | "completed";
  scheduledAt: string | null;
  completedAt: string | null;
  assigneeName: string;
  description: string;
  result: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface IotDevice {
  id: string;
  deviceCode: string;
  name: string;
  deviceType: DeviceType;
  vendor: string;
  model: string;
  serialNo: string;
  status: DeviceStatus;
  connectivityStatus: "online" | "offline" | "unknown";
  ownerUnit: string;
  custodian: string;
  firmwareVersion: string;
  installedAt: string | null;
  lastSeenAt: string | null;
  longitude: number | null;
  latitude: number | null;
  locationText: string;
  metadata: Record<string, unknown>;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
  blocks: Array<{ id: string; code: string }>;
  maintenance: DeviceMaintenance[];
}

export interface IotDevicePayload {
  name: string;
  deviceType: DeviceType;
  vendor?: string;
  model?: string;
  serialNo?: string;
  status: DeviceStatus;
  connectivityStatus: IotDevice["connectivityStatus"];
  ownerUnit?: string;
  custodian?: string;
  firmwareVersion?: string;
  installedAt?: string;
  lastSeenAt?: string;
  longitude?: number;
  latitude?: number;
  locationText?: string;
  linkedBlockCodes: string[];
  metadata?: Record<string, unknown>;
}

export type SituationAssetKind = "camera" | "helmet" | "dock" | "mission";

export interface SituationAssetRecord {
  id: string;
  sourceType: "device" | "mission";
  kind: SituationAssetKind;
  name: string;
  subtitle: string;
  status: string;
  blockCode: string;
  longitude: number | null;
  latitude: number | null;
  parameters: Array<[string, string]>;
  managementPath: string;
}

export interface SituationAssetResponse {
  items: SituationAssetRecord[];
  total: number;
  source: "device-and-mission-ledgers";
}

export interface DeviceMaintenancePayload {
  maintenanceType: DeviceMaintenance["maintenanceType"];
  scheduledAt?: string;
  completedAt?: string;
  assigneeName?: string;
  description: string;
  result?: string;
}

export type DroneMissionStatus = "planned" | "assigned" | "flying" | "processing" | "reviewed" | "completed" | "cancelled";
export type DroneMissionType = "survey" | "patrol" | "mapping" | "pest" | "fire" | "delivery" | "other";

export interface DroneMission {
  id: string;
  missionNo: string;
  title: string;
  missionType: DroneMissionType;
  status: DroneMissionStatus;
  droneDeviceId: string;
  deviceCode: string;
  deviceName: string;
  pilotName: string;
  routeName: string;
  objective: string;
  plannedStartAt: string | null;
  plannedEndAt: string | null;
  actualStartAt: string | null;
  actualEndAt: string | null;
  flightSummary: Record<string, unknown>;
  resultAssetUrls: string[];
  resultAttachmentIds: string[];
  resultAttachments: AttachmentRecord[];
  version: number;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  closedAt: string | null;
  deletedAt: string | null;
  blocks: Array<{ id: string; code: string }>;
  timeline: Array<{ id: string; action: string; fromStatus: string; toStatus: string; actor: string; note: string; data: Record<string, unknown>; createdAt: string }>;
}

export interface DroneMissionPayload {
  title: string;
  missionType: DroneMissionType;
  droneDeviceId: string;
  plannedStartAt: string;
  plannedEndAt: string;
  linkedBlockCodes: string[];
  objective?: string;
}

export interface DroneMissionActionPayload {
  note?: string;
  pilotName?: string;
  routeName?: string;
  resultAssetUrls?: string[];
  resultAttachmentIds?: string[];
  flightDurationMinutes?: number;
  flightDistanceKm?: number;
  coverageAreaMu?: number;
  reviewNote?: string;
}

export interface SceneTrajectoryFeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    id: string;
    properties: { kind: "path" | "start" | "end"; label?: string };
    geometry: { type: "LineString" | "Point"; coordinates: number[] | number[][] };
  }>;
  meta: {
    available: boolean;
    sourceFormat: string;
    sourcePointCount: number;
    sourcePointCountEstimated: boolean;
    returnedPointCount: number;
    segmentCount: number;
    distanceKm: number;
    fileCount: number;
    formats: string[];
  };
}

export interface DroneFlightRecord {
  id: string;
  missionId: string;
  missionNo: string;
  title: string;
  origin: "mission" | "trajectory";
  status: DroneMissionStatus;
  deviceCode: string;
  deviceName: string;
  pilotName: string;
  routeName: string;
  actualStartAt: string | null;
  actualEndAt: string | null;
  durationMinutes: number | null;
  distanceKm: number | null;
  coverageAreaMu: number | null;
  trajectoryPath: string;
  trajectoryFormats: string[];
  trajectoryFileCount: number;
  trajectorySizeBytes: number;
  sourceSceneIds: string[];
  resultAttachmentCount: number;
  missingFields: string[];
  completeness: "complete" | "incomplete";
  blocks: Array<{ id: string; code: string }>;
  updatedAt: string;
}

export type AiFindingStatus = "pending" | "confirmed" | "converted" | "ignored";
export type AiFindingType = "pest" | "fire" | "disease" | "illegal-cutting" | "road-damage" | "tree-fall" | "other";

export interface AiFinding {
  id: string;
  findingNo: string;
  title: string;
  findingType: AiFindingType;
  status: AiFindingStatus;
  modelCode: string;
  modelVersion: string;
  confidence: number;
  sourceAssetUrl: string;
  sourceAttachmentId: string;
  sourceAttachments: AttachmentRecord[];
  droneMissionId: string;
  deviceId: string;
  deviceCode: string;
  locationText: string;
  longitude: number | null;
  latitude: number | null;
  result: Record<string, unknown>;
  review: { decision?: string; reviewedBy?: string; reviewedAt?: string; note?: string; safetyAlertId?: string };
  safetyAlertId: string;
  occurredAt: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
  blocks: Array<{ id: string; code: string }>;
  timeline: Array<{ id: string; action: string; fromStatus: string; toStatus: string; actor: string; note: string; data: Record<string, unknown>; createdAt: string }>;
}

export interface AiFindingPayload {
  title: string;
  findingType: AiFindingType;
  modelCode: string;
  modelVersion: string;
  confidence: number;
  sourceAssetUrl?: string;
  sourceAttachmentId?: string;
  droneMissionId?: string;
  deviceId?: string;
  locationText?: string;
  longitude?: number;
  latitude?: number;
  linkedBlockCodes: string[];
  occurredAt?: string;
  result?: Record<string, unknown>;
}

export interface AiFindingActionPayload {
  note?: string;
  title?: string;
  severity?: SafetySeverity;
}

export type AiModelAssetType = "dataset" | "model-version" | "deployment" | "evaluation";
export type AiModelAssetStatus = "draft" | "ready" | "active" | "paused" | "failed" | "retired" | "archived";

export interface AiModelAsset {
  id: string;
  assetNo: string;
  assetType: AiModelAssetType;
  name: string;
  code: string;
  version: string;
  status: AiModelAssetStatus;
  parentId: string;
  parent: { id: string; assetNo: string; name: string; assetType: AiModelAssetType } | null;
  framework: string;
  runtimeTarget: string;
  description: string;
  metrics: Record<string, unknown>;
  metadata: Record<string, unknown>;
  attachmentIds: string[];
  attachments: AttachmentRecord[];
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export interface AiModelAssetPayload {
  assetType: AiModelAssetType;
  name: string;
  code: string;
  version?: string;
  status: AiModelAssetStatus;
  parentId?: string;
  framework?: string;
  runtimeTarget?: string;
  description?: string;
  metrics?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  attachmentIds?: string[];
}

export type AiInferenceStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface AiInferenceRun {
  id: string;
  runNo: string;
  title: string;
  status: AiInferenceStatus;
  modelAssetId: string;
  deploymentAssetId: string;
  findingId: string;
  model: AiModelAsset | null;
  deployment: AiModelAsset | null;
  parameters: Record<string, unknown>;
  output: Record<string, unknown>;
  errorMessage: string;
  inputAttachmentId: string;
  inputAttachments: AttachmentRecord[];
  outputAttachmentIds: string[];
  outputAttachments: AttachmentRecord[];
  blocks: Array<{ id: string; code: string }>;
  requestedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number | null;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
}

export interface AiInferenceRunPayload {
  title: string;
  modelAssetId: string;
  deploymentAssetId?: string;
  inputAttachmentId: string;
  linkedBlockCodes: string[];
  parameters?: Record<string, unknown>;
}

export interface AiInferenceActionPayload {
  output?: Record<string, unknown>;
  outputAttachmentIds?: string[];
  errorMessage?: string;
}

export interface AiInferenceFindingPayload {
  title?: string;
  findingType: AiFindingType;
  confidence: number;
  locationText?: string;
  longitude?: number | null;
  latitude?: number | null;
}

export type MobileSyncStatus = "processing" | "completed" | "conflict" | "failed" | "resolved" | "discarded";

export interface MobileFieldTask {
  id: string;
  taskType: "patrol" | "labor" | "safety";
  taskNo: string;
  title: string;
  status: string;
  priority: string;
  assigneeName: string;
  plannedStartAt: string;
  dueAt: string;
  linkedBlockCodes: string[];
  instructions: string;
  version: string;
  overdue: boolean;
  detail: Record<string, unknown>;
}

export interface MobileOfflinePackage {
  serverTime: string;
  principal: { user: string; roles: string[]; areas: string[] };
  domainAccess: Record<string, boolean>;
  tasks: MobileFieldTask[];
  operations: MobileSyncOperationRecord[];
  messages: Array<{ id: string; type: string; title: string; body: string; createdAt: string; operationId?: string }>;
  syncCursor: string;
  packageId: string;
  packageVersion: string;
  generatedAt: string;
  expiresAt: string;
  downloadPolicy: string;
  clientPolicy: MobileClientPolicy;
}

export interface MobileClientPolicy {
  minimumVersions: Record<"android" | "ios" | "web", string>;
  latestVersions: Record<"android" | "ios" | "web", string>;
  updateUrls: Partial<Record<"android" | "ios", string>>;
}

export interface MobileDeviceRecord {
  deviceId: string;
  deviceName: string;
  userId: string;
  platform: "android" | "ios" | "web";
  appVersion: string;
  osVersion: string;
  pushToken: string;
  pushTokenRegistered?: boolean;
  capabilities: string[];
  status: "active" | "revoked";
  registeredAt: string;
  lastSeenAt: string;
  revokedAt: string;
  revokedBy: string;
  revocationNote: string;
}

export interface MobileDeviceLedger extends LedgerResponse<MobileDeviceRecord> {
  clientPolicy: MobileClientPolicy;
}

export interface MobilePendingOperation {
  clientOperationId: string;
  entityType: "patrol" | "labor" | "safety";
  entityId: string;
  action: string;
  baseVersion: string;
  occurredAt: string;
  payload: Record<string, unknown>;
}

export interface MobileSyncBatchResult {
  serverTime: string;
  results: MobileSyncOperationRecord[];
  completed: number;
  conflicts: number;
  failed: number;
}

export interface MobileTrackPayload {
  clientTrackId: string;
  taskType: "patrol" | "labor";
  taskId: string;
  status: "recording" | "completed";
  points: Array<{ longitude: number; latitude: number; capturedAt: string; accuracyMeters?: number; altitudeMeters?: number }>;
}

export interface MobileEvidenceUpload {
  clientEvidenceId: string;
  taskType: "patrol" | "labor" | "safety";
  taskId: string;
  fileName: string;
  contentType: string;
  totalBytes: number;
  totalChunks: number;
  sha256: string;
  sessionId: string;
  receivedChunks: number[];
  status: "queued" | "uploading";
  createdAt: string;
}

export interface MobileUploadSession {
  id: string;
  userId: string;
  taskType: string;
  taskId: string;
  fileName: string;
  contentType: string;
  totalBytes: number;
  totalChunks: number;
  expectedSha256: string;
  receivedChunks: number[];
  status: "uploading" | "completed" | "cancelled";
  evidenceId: string;
  createdAt: string;
  updatedAt: string;
  expiresAt: string;
  deletedAt: string | null;
}

export interface MobileSyncOperationRecord {
  id: string;
  clientOperationId: string;
  userId: string;
  entityType: string;
  entityId: string;
  action: string;
  baseVersion: string;
  status: MobileSyncStatus;
  request: Record<string, unknown>;
  result: Record<string, unknown>;
  errorCode: string;
  occurredAt: string;
  receivedAt: string;
  completedAt: string | null;
}

export interface MobileTrackRecord {
  id: string;
  clientTrackId: string;
  userId: string;
  taskType: string;
  taskId: string;
  status: string;
  points: Array<{ longitude: number; latitude: number; capturedAt: string; accuracyMeters?: number }>;
  pointCount: number;
  distanceMeters: number;
  startedAt: string;
  endedAt: string;
  createdAt: string;
  deletedAt: string | null;
}

export interface MobileEvidenceRecord {
  id: string;
  evidenceNo: string;
  userId: string;
  taskType: string;
  taskId: string;
  fileName: string;
  contentType: string;
  byteSize: number;
  sha256: string;
  capturedAt: string | null;
  longitude: number | null;
  latitude: number | null;
  createdAt: string;
  url: string;
}

export interface MobileUploadSessionRecord {
  id: string;
  userId: string;
  taskType: string;
  taskId: string;
  fileName: string;
  contentType: string;
  totalBytes: number;
  totalChunks: number;
  expectedSha256: string;
  receivedChunks: number[];
  status: "uploading" | "completed" | "cancelled";
  evidenceId: string;
  createdAt: string;
  updatedAt: string;
  expiresAt: string;
  deletedAt: string | null;
}

export interface OperationsTodo {
  id: string;
  recordId: string;
  recordNo: string;
  title: string;
  module: string;
  moduleLabel: string;
  status: string;
  statusLabel: string;
  priority: string;
  assigneeName: string;
  dueAt: string;
  updatedAt: string;
  linkedBlockCodes: string[];
  targetPath: string;
}

export interface OperationsAuditEvent {
  id: string;
  module: string;
  moduleLabel: string;
  recordId: string;
  recordNo: string;
  recordName: string;
  action: string;
  actor: string;
  fromStatus: string;
  toStatus: string;
  message: string;
  createdAt: string;
  targetPath: string;
  read?: boolean;
}

export interface ExtensionRecord {
  id: string;
  version: number;
  status?: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  [key: string]: unknown;
}

export interface CostRate extends ExtensionRecord {
  workType: string;
  name: string;
  unit: string;
  rateCents: number;
  effectiveFrom: string;
  effectiveTo?: string | null;
}

export interface CostMaterial extends ExtensionRecord {
  materialCode: string;
  name: string;
  unit: string;
  stockQuantity: string;
  stockValueCents: number;
  movingAverageUnitCostCents: number;
}

export interface CostEntry extends ExtensionRecord {
  costType: "labor" | "material" | "adjustment";
  blockCode: string;
  amountCents: number;
  occurredOn: string;
  period: string;
  sourceType: string;
  sourceId: string;
}

export interface CostReportRow {
  blockCode: string;
  laborCents: number;
  materialCents: number;
  adjustmentCents: number;
  totalCents: number;
  entryCount: number;
}

export interface CostAlert {
  budgetId: string;
  period: string;
  blockCode: string;
  budgetCents: number;
  actualCents: number;
  varianceCents: number;
  variancePct: number;
  level: "normal" | "yellow" | "red";
}

export interface CostMonthlyReport {
  period: string;
  asOf: string;
  currency: "CNY";
  amountScale: 2;
  items: CostReportRow[];
  total: number;
  grandTotalCents: number;
  alerts: CostAlert[];
}

export interface ResourceStatisticRow {
  name: string;
  count: number;
  areaMu: number;
}

export interface ResourceStatisticsResponse {
  source: string;
  asOf: string;
  groupBy: "bambooSpecies" | "ageGroup" | "slope" | "town";
  filters: Record<string, string | number | null>;
  items: ResourceStatisticRow[];
  total: number;
  totalAreaMu: number;
}

export interface CockpitMetricDefinition {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  available: boolean;
  source: string;
  definition: string;
  drilldown: string;
}

export interface CockpitTopic {
  key: "overview" | "emergency" | "harvest" | "drone" | "cost";
  label: string;
  available: boolean;
  asOf: string;
  metrics: CockpitMetricDefinition[];
  featureGates?: Record<string, string | boolean>;
  alerts?: CostAlert[];
}

export interface CockpitTopicsResponse {
  source: "live";
  asOf: string;
  scope: { user: string; roles: string[]; areas: string[] };
  topics: CockpitTopic[];
  metricPolicy: string;
}

export interface RequirementsBaseline {
  baselineCommit: string;
  scopeVersion: string;
  packages: Array<{ key: string; priority: string; delivery: string; status: string; entry?: string; reuse?: string[] }>;
  roleCount: number;
  roleCodes: string[];
  nonDuplicateRule: string;
  externalAcceptanceDisclaimer: string;
}
