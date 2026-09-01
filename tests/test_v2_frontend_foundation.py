from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_v2_frontend_serves_root_and_deep_routes(app_client):
    root = app_client.get("/v2/")
    deep_link = app_client.get("/v2/map")

    assert root.status_code == 200
    assert deep_link.status_code == 200
    assert "text/html" in root.headers["content-type"]
    assert '<div id="root"></div>' in root.text
    assert deep_link.text == root.text


def test_v2_frontend_rejects_missing_asset_instead_of_returning_html(app_client):
    response = app_client.get("/v2/assets/not-present.js")

    assert response.status_code == 404
    assert response.json()["detail"] == "V2 asset not found."


def test_v2_production_build_is_self_contained():
    dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")
    package = (ROOT_DIR / "apps" / "web-operations" / "package.json").read_text(
        encoding="utf-8"
    )

    assert "FROM node:22.22.0-alpine AS v2-web-builder" in dockerfile
    assert "pnpm install --frozen-lockfile" in dockerfile
    assert "pnpm run build" in dockerfile
    assert "/app/dist/web-operations" in dockerfile
    assert '"@tanstack/react-router"' in package
    assert '"ol"' in package


def test_v2_map_uses_vector_tiles_in_2d_and_viewport_geojson_in_3d():
    web_root = ROOT_DIR / "apps" / "web-operations" / "src"
    page = (web_root / "pages" / "MapPage.tsx").read_text(encoding="utf-8")
    client = (web_root / "api" / "client.ts").read_text(encoding="utf-8")
    canvas = (web_root / "components" / "MapCanvas.tsx").read_text(encoding="utf-8")
    open_layers = (web_root / "components" / "OpenLayersMap.tsx").read_text(
        encoding="utf-8"
    )
    cesium = (web_root / "components" / "CesiumGlobe.tsx").read_text(
        encoding="utf-8"
    )

    assert "/api/map/forest-blocks.geojson" in client
    assert "bbox: bufferedViewportBbox.join" in page
    assert "maxFeatures: 2000" in page
    assert "expandViewportBbox" in page
    assert "mergeForestBlockCollections" in page
    assert "forestBlockAggregates" in page
    assert "enabled: layers.forestBlocks" in page
    assert "buildMapAnnotations" in page
    assert "mergeSelectedForestBlock" in page
    assert "林班边界" in page
    assert "featureCollection" in canvas
    assert "new VectorLayer" in open_layers
    assert "new VectorTileLayer" in open_layers
    assert "new VectorTileSource" in open_layers
    assert "/api/map/forest-blocks/tiles/{z}/{x}/{y}.pbf?maxFeatures=5000" in open_layers
    assert 'idProperty: "id"' in open_layers
    assert "BLOCK_LABEL_MIN_ZOOM = 12" in open_layers
    assert "BLOCK_LABEL_MAX_HEIGHT = 120_000" in cesium
    assert "forestBlockLabelText" in cesium
    assert "new LabelGraphics" in cesium
    assert "updateForestBlockLabels" in cesium
    assert "SceneTransforms.worldToWindowCoordinates" in cesium
    assert "overlapsLabel" in cesium
    assert 'declutter: "forest-block-labels"' in open_layers
    assert 'blockCode.slice(-6)' in open_layers
    assert 'map.on("singleclick"' in open_layers
    assert "GeoJsonDataSource.load" in cesium
    assert "ScreenSpaceEventType.LEFT_CLICK" in cesium
    assert "viewer.flyTo" in cesium
    assert "OpenStreetMapImageryProvider" in cesium
    assert "maximumLevel: 19" in cesium
    assert "maximumLevel: config.maximumLevel" in cesium
    assert "viewer.useBrowserRecommendedResolution = false" in cesium
    assert "viewer.resolutionScale = performanceResolutionScale()" in cesium
    assert "return Math.min(1.1, 1.25 / devicePixelRatio)" in cesium
    assert "viewer.scene.globe.maximumScreenSpaceError = 2" in cesium
    assert "viewer.scene.globe.preloadSiblings = false" in cesium
    assert "labelLayerRef.current.show = false" in cesium
    assert "}, 1_500);" in cesium
    assert "targetHeight" in cesium
    assert 'zoomRequest.direction === "in"' in cesium
    assert "FAR_VIEW_PITCH_RESET_HEIGHT = 300_000" in cesium
    assert "restoreFarViewPitch(viewer, height)" in cesium
    assert "targetHeight >= FAR_VIEW_PITCH_RESET_HEIGHT ? FAR_VIEW_PITCH" in cesium
    assert '(asset.assetType || "orthophoto") === "orthophoto"' in page
    assert "Rectangle.fromDegrees(west, south, east, north)" in cesium
    assert "function tilesetTuning" in cesium
    assert 'qualityMode === "detail" || detailMode' in cesium
    assert "function focusTileset" in cesium
    assert "focusTileset(activeViewer, tileset, 1.2)" in cesium
    assert "const sphere = targetTileset.boundingSphere" in cesium
    assert "detailMode ? 10 : MINIMUM_SHARP_CAMERA_HEIGHT" in cesium
    assert "asset.maximumZoom ?? 22" in open_layers
    assert "cacheSize: 384" in open_layers
    assert "constrainResolution: true" in open_layers
    assert "maxDelta: 1" in open_layers
    assert "MAP_ANNOTATION_COLORS" in open_layers
    assert "MAP_ANNOTATION_GLYPHS" in cesium
    assert "inertiaZoom = 0.65" in cesium
    assert "maximumMovementRatio = 0.08" in cesium
    assert "preload: 0" in open_layers
    assert "maxZoom: 18, padding: [88, 88, 88, 88]" in open_layers
    assert 'requestedMode === "2d" || requestedMode === "3d"' in page
    assert 'asset.assetType === "orthophoto"' in page
    assert 'mode=2d`}' in (
        web_root / "pages" / "ImageryAssetsPage.tsx"
    ).read_text(encoding="utf-8")

    map_page = (web_root / "pages" / "MapPage.tsx").read_text(encoding="utf-8")
    assert 'aria-label="放大地图"' in map_page
    assert 'aria-label="缩小地图"' in map_page
    assert "const [resultsOpen, setResultsOpen] = useState(false)" in map_page
    assert "{resultsOpen && (" in map_page
    assert 'aria-label="关闭林班检索结果"' in map_page
    assert 'activeTown === town.name ? "active" : ""' in map_page
    assert 'aria-label="正式林班乡镇快速定位"' in map_page
    assert 'aria-label="林班详情浮动窗口"' in map_page
    assert 'aria-label={detailMaximized ? "还原详情窗口" : "放大详情窗口"}' in map_page
    assert "startDetailDrag" in map_page
    assert "PolylineGraphics" in cesium
    assert 'Color.fromCssColorString("#d9ffed")' in cesium


def test_v2_workspace_forest_block_locator_opens_the_selected_block_in_gis():
    web_root = ROOT_DIR / "apps" / "web-operations" / "src"
    workspace = (web_root / "pages" / "WorkspacePage.tsx").read_text(
        encoding="utf-8"
    )
    map_page = (web_root / "pages" / "MapPage.tsx").read_text(encoding="utf-8")

    assert "进入 GIS 定位" in workspace
    assert "blockId=${encodeURIComponent(selectedBlock.id)}" in workspace
    assert 'new URLSearchParams(window.location.search).get("blockId")' in map_page
    assert "api.forestBlockDetail(blockId)" in map_page
    assert "geometryBounds(record.geometry)" in map_page


def test_v2_workspace_routes_and_moso_markers_remain_distinct_from_green_canopy():
    web_root = ROOT_DIR / "apps" / "web-operations" / "src"
    workspace = (web_root / "pages" / "WorkspacePage.tsx").read_text(encoding="utf-8")
    evidence_map = (web_root / "components" / "MosoInventoryEvidenceMap.tsx").read_text(encoding="utf-8")

    assert 'to: "/resources/imports", label: "成果接入"' in workspace
    assert 'to: "/operations/patrol", label: "巡护办理"' in workspace
    assert 'to: "/imports"' not in workspace
    assert 'to: "/patrol"' not in workspace
    assert 'color: "#ffb000"' in evidence_map
    assert "new RegularShape" in evidence_map
    assert "declutter: false" in evidence_map


def test_v2_basemap_settings_are_managed_server_side():
    web_root = ROOT_DIR / "apps" / "web-operations" / "src"
    router = (web_root / "router.tsx").read_text(encoding="utf-8")
    shell = (web_root / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    client = (web_root / "api" / "client.ts").read_text(encoding="utf-8")
    page = (web_root / "pages" / "BasemapSettingsPage.tsx").read_text(encoding="utf-8")
    cesium = (web_root / "components" / "CesiumGlobe.tsx").read_text(encoding="utf-8")

    assert 'path: "/system/basemap-settings"' in router
    assert '"basemap-settings"' in shell
    assert '"/api/v2/system/basemap-settings"' in client
    assert "完整值不会返回浏览器" in page
    assert 'type="password"' in page
    assert 'name="webKey"' in page
    assert 'name="androidKey"' in page
    assert 'name="iosKey"' in page
    assert 'name="webDirectEnabled"' in page
    assert "?tk=" not in cesium


def test_v2_api_client_sends_and_recovers_human_session_csrf_tokens():
    client = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")

    assert 'const CSRF_COOKIE_NAME = "smart_bamboo_session_csrf"' in client
    assert 'headers["X-CSRF-Token"] = csrfToken()' in client
    assert 'fetch("/api/auth/session"' in client
    assert 'headers["X-CSRF-Token"] = freshToken' in client
    assert 'isCsrfFailure(response, responseBody)' in client


def test_v2_mobile_operations_page_exposes_sync_tracks_and_evidence_ledgers():
    web_root = ROOT_DIR / "apps" / "web-operations" / "src"
    router = (web_root / "router.tsx").read_text(encoding="utf-8")
    shell = (web_root / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    page = (web_root / "pages" / "MobileOperationsPage.tsx").read_text(encoding="utf-8")
    client = (web_root / "api" / "client.ts").read_text(encoding="utf-8")

    assert 'path: "/operations/mobile-sync"' in router
    assert '"mobile-operations"' in shell
    assert "api.mobileSyncOperations" in page
    assert "api.mobileTracks" in page
    assert "api.mobileEvidence" in page
    assert "operations-export.csv" in page
    assert "/api/v2/mobile/operations" in client
    assert "/api/v2/mobile/tracks" in client
    assert "/api/v2/mobile/evidence" in client


def test_v2_mobile_field_workspace_supports_offline_tasks_tracks_and_idempotent_sync():
    web_root = ROOT_DIR / "apps" / "web-operations" / "src"
    router = (web_root / "router.tsx").read_text(encoding="utf-8")
    shell = (web_root / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    page = (web_root / "pages" / "MobileFieldPage.tsx").read_text(encoding="utf-8")
    store = (web_root / "mobileFieldStore.ts").read_text(encoding="utf-8")
    client = (web_root / "api" / "client.ts").read_text(encoding="utf-8")
    native_bridge = (web_root / "nativeBridge.ts").read_text(encoding="utf-8")

    assert 'path: "/field/mobile"' in router
    assert 'pathname === "/field/mobile"' in shell
    assert 'className="field-mobile-dock"' in page
    assert "今日现场" in page
    assert "api.mobileOfflinePackage" in page
    assert "api.syncMobileOperations" in page
    assert "api.uploadMobileTrack" in page
    assert "navigator.geolocation.watchPosition" in page
    assert "nativeBridge()?.stopLocation" in page
    assert "subscribeNativeLocation" in page
    assert '"smart-bamboo-native:network"' in native_bridge
    assert '"smart-bamboo-native:location"' in native_bridge
    assert "bridge.isOnline()" in native_bridge
    assert "clientOperationId: createClientId" in page
    assert "crypto.subtle.digest" in page
    assert "readEvidenceBlob" in page
    assert "EVIDENCE_CHUNK_BYTES = 8 * 1024 * 1024" in page
    assert "localStorage.setItem" in store
    assert "indexedDB.open" in store
    assert 'const BLOB_STORE = "evidence-blobs"' in store
    assert '"/api/v2/mobile/offline-package"' in client
    assert '"/api/v2/mobile/sync"' in client
    assert '"/api/v2/mobile/tracks"' in client
    assert '"/api/v2/mobile/uploads"' in client
    assert '"/api/v2/mobile/devices/register"' in client
    assert "远程注销设备" in (web_root / "pages" / "MobileOperationsPage.tsx").read_text(encoding="utf-8")
    assert "registerCurrentDevice" in page
    assert "二次确认并提交 SOS" in page
    assert 'clientOperationId: createClientId("sos")' in page
    assert 'method: "PUT", body' in client
    assert '/complete`' in client


def test_v2_carbon_estimates_are_an_independent_permission_aware_ledger():
    web_root = ROOT_DIR / "apps" / "web-operations" / "src"
    router = (web_root / "router.tsx").read_text(encoding="utf-8")
    shell = (web_root / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    client = (web_root / "api" / "client.ts").read_text(encoding="utf-8")
    page = (web_root / "pages" / "CarbonEstimatesPage.tsx").read_text(encoding="utf-8")

    assert 'path: "/carbon/estimates"' in router
    assert '"carbon-estimates"' in shell
    assert "/api/v2/carbon/estimates" in client
    assert "ForestBlockSelector" in page
    assert "business.carbonEstimates.create" in page
    assert "business.carbonEstimates.update" in page
    assert "business.carbonEstimates.delete" in page
    for label in ("核算面积", "年碳汇量", "核证减排量", "预计收益"):
        assert label in page
    for action in ('label="查看"', 'label="编辑"', 'label="删除"'):
        assert action in page


def test_v2_resource_ledgers_are_independent_routes_with_row_actions():
    router = (ROOT_DIR / "apps" / "web-operations" / "src" / "router.tsx").read_text(
        encoding="utf-8"
    )
    blocks = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "pages" / "ForestBlocksPage.tsx"
    ).read_text(encoding="utf-8")
    rights = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "pages" / "ForestRightsPage.tsx"
    ).read_text(encoding="utf-8")
    subcompartments = (
        ROOT_DIR
        / "apps"
        / "web-operations"
        / "src"
        / "pages"
        / "ForestSubcompartmentsPage.tsx"
    ).read_text(encoding="utf-8")

    assert 'path: "/resources/forest-blocks"' in router
    assert 'path: "/resources/forest-subcompartments"' in router
    assert 'path: "/resources/forest-rights"' in router
    assert "forestBlockLedger" in blocks
    assert "forestSubcompartmentLedger" in subcompartments
    assert "forestRightLedger" in rights
    assert 'label="查看"' in blocks and 'label="编辑"' in blocks
    assert 'label="查看"' in subcompartments and 'label="编辑"' in subcompartments
    assert 'label="查看"' in rights and 'label="编辑"' in rights
    assert "ForestBlockSelector" in subcompartments
    assert "BoundaryEditor" in blocks
    assert 'entityLabel="林班"' in blocks
    assert "geometry" in blocks
    assert "forestBlockId: parent.id" in subcompartments
    assert "SubcompartmentBoundaryEditor" in subcompartments
    assert "geometry" in subcompartments
    assert "expectedVersion: record.version" in subcompartments
    assert "尚未选择林班" in subcompartments
    assert "ForestBlockSelector" in rights
    assert "linkedBlockCodes" in rights
    assert "SpatialVersionHistory" in blocks
    assert "SpatialVersionHistory" in subcompartments
    assert "forest.blocks.export" in blocks
    assert "/api/v2/resources/forest-blocks-export.csv" in blocks
    assert "downloadFile(exportHref" in blocks
    assert "forest.subcompartments.export" in subcompartments
    assert "/api/v2/resources/forest-subcompartments-export.csv" in subcompartments
    assert "downloadFile(exportHref" in subcompartments


def test_v2_spatial_version_history_supports_permission_aware_rollback():
    history = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "components" / "SpatialVersionHistory.tsx"
    ).read_text(encoding="utf-8")
    client = (ROOT_DIR / "apps" / "web-operations" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    assert "恢复此版本" in history
    assert "canRollback" in history
    assert "forestBlockVersions" in client
    assert "forestSubcompartmentVersions" in client
    assert "rollbackForestSubcompartment" in client


def test_v2_subcompartment_boundary_editor_supports_draw_modify_and_geojson_import():
    editor = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "components" / "SubcompartmentBoundaryEditor.tsx"
    ).read_text(encoding="utf-8")
    assert 'new Draw({ source: childSourceRef.current, type: "Polygon" })' in editor
    assert "new Modify({ source: childSourceRef.current })" in editor
    assert "new Snap({ source: childSourceRef.current })" in editor
    assert "粘贴 GeoJSON" in editor
    assert "导入文件" in editor
    assert "定位林班" in editor


def test_v2_import_page_uses_the_native_three_step_intake_flow():
    page = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "pages" / "ImportsPage.tsx"
    ).read_text(encoding="utf-8")

    assert "api.createImportJob" in page
    assert "api.confirmImportJob" in page
    assert "api.commitImportJob" in page
    assert "api.exportImportIssues" in page
    assert "质量规则检查" in page
    assert "跳过阻断记录" in page
    assert "上传并检查" in page
    assert "处理异常" in page
    assert "正式入库" in page
    assert "admin-imports.html" not in page


def test_v2_patrol_page_uses_formal_blocks_and_closed_loop_actions():
    router = (ROOT_DIR / "apps" / "web-operations" / "src" / "router.tsx").read_text(
        encoding="utf-8"
    )
    page = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "pages" / "PatrolPage.tsx"
    ).read_text(encoding="utf-8")

    assert 'path: "/operations/patrol"' in router
    assert "component: PatrolPage" in router
    assert "ForestBlockSelector" in page
    assert "api.applyPatrolAction" in page
    for action in ("assign", "accept", "start", "report", "resolve", "verify", "return", "close"):
        assert f'"{action}"' in page
    for label in ("待派发", "待接单", "巡护中", "待处置/复核", "待复核", "已完成"):
        assert label in page
    for capability in ("api.updatePatrolTask", "api.deletePatrolTask", "api.restorePatrolTask", "AttachmentSelector", "tasks-export.csv"):
        assert capability in page


def test_v2_harvest_page_uses_formal_relations_and_closed_loop_actions():
    router = (ROOT_DIR / "apps" / "web-operations" / "src" / "router.tsx").read_text(
        encoding="utf-8"
    )
    page = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "pages" / "HarvestPage.tsx"
    ).read_text(encoding="utf-8")
    selectors = (
        ROOT_DIR
        / "apps"
        / "web-operations"
        / "src"
        / "components"
        / "HarvestSelectors.tsx"
    ).read_text(encoding="utf-8")
    client = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")

    assert 'path: "/operations/harvest"' in router
    assert "component: HarvestPage" in router
    assert "PlannedPage" not in router
    for selector in (
        "HarvestSubjectSelector",
        "ForestBlockSelector",
        "ForestRightSelector",
    ):
        assert selector in page
    assert "linkedBlockCodes" in page
    assert "linkedRightIds" in page
    for capability in (
        "api.updateHarvestApplication",
        "api.deleteHarvestApplication",
        "api.restoreHarvestApplication",
        "applications-export.csv",
        "AttachmentSelector",
        "attachmentIds",
    ):
        assert capability in page
    for action in (
        "submit",
        "recheck",
        "approve",
        "return",
        "start",
        "record-alert",
        "report-complete",
        "verify",
        "return-operation",
    ):
        assert f'"{action}"' in page
    for path in (
        "/api/v2/harvest/subjects",
        "/api/v2/harvest/quotas",
        "/api/v2/harvest/applications",
    ):
        assert path in client
    assert "/api/v2/entities/forest-rights" in client
    assert "api.harvestSubjects" in selectors
    assert "api.forestRights" in selectors


def test_v2_safety_center_separates_alert_intake_from_event_closure():
    router = (ROOT_DIR / "apps" / "web-operations" / "src" / "router.tsx").read_text(
        encoding="utf-8"
    )
    page = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "pages" / "SafetyEventsPage.tsx"
    ).read_text(encoding="utf-8")
    client = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")

    assert 'path: "/safety/events"' in router
    assert "component: SafetyEventsPage" in router
    assert "事件台账" in page
    assert "告警收件箱" in page
    assert "ForestBlockSelector" in page
    assert "api.applySafetyEventAction" in page
    assert "api.applySafetyAlertAction" in page
    for action in (
        "triage", "assign", "accept", "progress", "resolve", "return",
        "verify", "close", "reopen", "escalate", "convert", "merge", "ignore",
    ):
        assert f'"{action}"' in page
    for label in ("待分级", "待派单", "待接单", "处置中", "待复核", "待关闭", "已关闭"):
        assert label in page
    assert "/api/v2/safety/events" in client
    assert "/api/v2/safety/alerts" in client
    for capability in ("updateSafetyEvent", "deleteSafetyEvent", "restoreSafetyEvent"):
        assert capability in client
    assert "events-export.csv" in page
    assert "显示已删除" in page
    assert "保存修改" in page
    assert 'record.status !== "new"' in page


def test_v2_labor_page_separates_master_ledgers_and_closes_the_job_flow():
    router = (ROOT_DIR / "apps" / "web-operations" / "src" / "router.tsx").read_text(
        encoding="utf-8"
    )
    page = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "pages" / "LaborPage.tsx"
    ).read_text(encoding="utf-8")
    client = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")

    assert 'path: "/operations/labor"' in router
    assert "component: LaborPage" in router
    for ledger in ("用工任务", "人员档案", "班组档案"):
        assert ledger in page
    assert "ForestBlockSelector" in page
    assert "linkedBlockCodes" in page
    assert "leaderWorkerId" in page
    assert "memberIds" in page
    assert "recordAttendanceMembers" in page
    for action in (
        "publish", "match", "contract", "start", "attendance", "submit",
        "return", "settle", "close",
    ):
        assert f'"{action}"' in page
    for label in (
        "草稿", "待匹配", "待签约", "待进场", "作业中", "待结算", "待归档", "已归档",
    ):
        assert label in page
    for path in (
        "/api/v2/labor/workers", "/api/v2/labor/teams", "/api/v2/labor/jobs",
    ):
        assert path in client
    for capability in (
        "updateLaborWorker", "deleteLaborWorker", "restoreLaborWorker",
        "updateLaborTeam", "deleteLaborTeam", "restoreLaborTeam",
        "updateLaborJob", "deleteLaborJob", "restoreLaborJob",
    ):
        assert capability in client
    assert "includeDeleted" in page
    assert "显示已删除" in page
    assert "导出台账" in page
    assert "RowActions" in page
    assert "record.status === \"draft\"" in page


def test_v2_equipment_page_is_an_independent_master_ledger():
    router = (ROOT_DIR / "apps" / "web-operations" / "src" / "router.tsx").read_text(
        encoding="utf-8"
    )
    page = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "pages" / "EquipmentPage.tsx"
    ).read_text(encoding="utf-8")
    client = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")

    assert 'path: "/iot/devices"' in router
    assert "component: EquipmentPage" in router
    assert "设备台账" in page
    assert "ForestBlockSelector" in page
    assert "linkedBlockCodes" in page
    assert "api.seedSituationAssets" in page
    assert "displayOnDashboard" in page
    assert "situationKind" in page
    assert "api.addDeviceMaintenance" in page
    for action in ("查看设备", "编辑设备", "删除设备", "恢复设备", "新增维保工单", "导出台账", "显示已删除"):
        assert action in page
    assert "/api/v2/iot/devices" in client
    assert "restoreIotDevice" in client
    assert "includeDeleted" in client
    assert "devices-export.csv" in page
    assert "/maintenance" in client


def test_v2_drone_page_links_formal_devices_blocks_and_task_transitions():
    router = (ROOT_DIR / "apps" / "web-operations" / "src" / "router.tsx").read_text(
        encoding="utf-8"
    )
    page = (
        ROOT_DIR
        / "apps"
        / "web-operations"
        / "src"
        / "pages"
        / "DroneMissionsPage.tsx"
    ).read_text(encoding="utf-8")
    flight_ledger = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "components" / "DroneFlightLedger.tsx"
    ).read_text(encoding="utf-8")
    client = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")

    assert 'path: "/drone/missions"' in router
    assert "component: DroneMissionsPage" in router
    assert 'api.iotDeviceOptions("drone")' in page
    assert "ForestBlockSelector" in page
    assert "linkedBlockCodes" in page
    assert "restoreDroneMission" in page
    assert "includeDeleted" in page
    assert "missions-export.csv" in page
    assert "AttachmentSelector" in page
    assert "resultAttachmentIds" in page
    assert "飞行记录台账" in page
    assert "DroneFlightLedger" in page
    assert "api.droneFlights" in flight_ledger
    assert "资料完整性" in flight_ledger
    assert "轨迹与成果" in flight_ledger
    assert "/api/v2/drone/flights" in client
    assert 'name="resultAssetUrls"' not in page
    for action in (
        "assign", "start", "upload-result", "review", "return", "complete", "cancel",
    ):
        assert f'"{action}"' in page
    for label in ("待安排", "已派发", "飞行中", "成果处理中", "待归档", "已完成"):
        assert label in page


def test_v2_ai_review_preserves_model_provenance_and_requires_human_decision():
    router = (ROOT_DIR / "apps" / "web-operations" / "src" / "router.tsx").read_text(
        encoding="utf-8"
    )
    page = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "pages" / "AiReviewPage.tsx"
    ).read_text(encoding="utf-8")
    client = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")

    assert 'path: "/ai/reviews"' in router
    assert "component: AiReviewPage" in router
    assert "AI 结果不是最终结论" in page
    assert "modelCode" in page and "modelVersion" in page
    assert "sourceAssetUrl" in page and "confidence" in page
    assert "ForestBlockSelector" in page
    assert "droneMissionId" in page and "deviceId" in page
    assert "updateAiFinding" in page
    assert "deleteAiFinding" in page
    assert "AttachmentSelector" in page
    assert "sourceAttachmentId" in page
    assert 'name="sourceAssetUrl"' not in page
    assert "restoreAiFinding" in page
    assert "includeDeleted" in page
    assert "findings-export.csv" in page
    for action in ("confirm", "ignore", "convert-alert"):
        assert f'"{action}"' in page
    assert "/api/v2/ai/findings" in client


def test_ai_model_management_is_an_independent_ledger_with_formal_relations():
    web_root = ROOT_DIR / "apps" / "web-operations"
    router = (web_root / "src" / "router.tsx").read_text(encoding="utf-8")
    shell = (web_root / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    page = (web_root / "src" / "pages" / "AiModelsPage.tsx").read_text(encoding="utf-8")
    client = (web_root / "src" / "api" / "client.ts").read_text(encoding="utf-8")

    assert 'path: "/ai/models"' in router
    assert "component: AiModelsPage" in router
    assert '"ai-models": BrainCircuit' in shell
    assert "训练数据集" in page and "模型版本" in page and "部署实例" in page and "评测记录" in page
    assert "PARENT_TYPE" in page and "parentId" in page
    assert "AttachmentSelector" in page and "attachmentIds" in page
    assert "row-actions" in page and "deleteAiModelAsset" in page and "restoreAiModelAsset" in page
    assert "/api/v2/ai/model-assets" in client


def test_ai_inference_is_an_independent_stateful_ledger_with_formal_inputs():
    web_root = ROOT_DIR / "apps" / "web-operations"
    router = (web_root / "src" / "router.tsx").read_text(encoding="utf-8")
    shell = (web_root / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    page = (web_root / "src" / "pages" / "AiInferencePage.tsx").read_text(encoding="utf-8")
    client = (web_root / "src" / "api" / "client.ts").read_text(encoding="utf-8")

    assert 'path: "/ai/inference-runs"' in router
    assert "component: AiInferencePage" in router
    assert '"ai-inference": PlaySquare' in shell
    assert "ForestBlockSelector" in page and "AttachmentSelector" in page
    assert "row-actions" in page and "applyAiInferenceAction" in page
    assert "createFindingFromInference" in page and "待转识别成果" in page
    assert "/api/v2/ai/inference-runs" in client


def test_resource_surveys_use_formal_relations_archive_permission_and_version_history():
    web_root = ROOT_DIR / "apps" / "web-operations"
    page = (web_root / "src" / "pages" / "ResourceSurveysPage.tsx").read_text(encoding="utf-8")
    client = (web_root / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    routes = (web_root / "src" / "router.tsx").read_text(encoding="utf-8")

    assert 'path: "/resources/resource-surveys"' in routes
    assert "ForestSubcompartmentSelector" in page
    assert 'forest.surveys.complete' in page
    assert "完成归档" in page
    assert 'value="completed">已完成并归档' not in page
    assert "resourceSnapshotVersions" in client
    assert "/versions" in client
    assert "version-timeline" in page


def test_attachment_center_and_resource_surveys_use_controlled_file_relations():
    web_root = ROOT_DIR / "apps" / "web-operations"
    page = (web_root / "src" / "pages" / "AttachmentsPage.tsx").read_text(encoding="utf-8")
    selector = (web_root / "src" / "components" / "AttachmentSelector.tsx").read_text(encoding="utf-8")
    survey = (web_root / "src" / "pages" / "ResourceSurveysPage.tsx").read_text(encoding="utf-8")
    client = (web_root / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    routes = (web_root / "src" / "router.tsx").read_text(encoding="utf-8")

    assert 'path: "/system/attachments"' in routes
    assert "附件中心" in page
    assert "includeDeleted" in page
    assert "uploadAttachment" in page and "deleteAttachment" in page and "restoreAttachment" in page
    assert "AttachmentSelector" in survey
    assert "attachmentIds" in survey
    assert 'name="evidenceUrls"' not in survey
    assert "uploadAttachment" in selector
    assert "/api/v2/attachments" in client


def test_imagery_assets_use_a_dedicated_ledger_and_published_map_layer():
    web_root = ROOT_DIR / "apps" / "web-operations"
    router = (web_root / "src" / "router.tsx").read_text(encoding="utf-8")
    page = (web_root / "src" / "pages" / "ImageryAssetsPage.tsx").read_text(encoding="utf-8")
    map_page = (web_root / "src" / "pages" / "MapPage.tsx").read_text(encoding="utf-8")
    client = (web_root / "src" / "api" / "client.ts").read_text(encoding="utf-8")

    assert 'path: "/drone/imagery-assets"' in router
    assert "ForestBlockSelector" in page
    assert "uploadImageryAsset" in page
    assert "publishImageryAsset" in page
    assert 'body.append("linkedBlockCodes"' in client
    assert 'toggleLayer("droneImagery")' in map_page
    assert "published: true" in map_page


def test_imagery_assets_have_independent_2d_and_3d_inspection_workspaces():
    web_root = ROOT_DIR / "apps" / "web-operations"
    router = (web_root / "src" / "router.tsx").read_text(encoding="utf-8")
    shell = (web_root / "src" / "components" / "AppShell.tsx").read_text(
        encoding="utf-8"
    )
    page = (web_root / "src" / "pages" / "AssetViewerPage.tsx").read_text(
        encoding="utf-8"
    )
    map_page = (web_root / "src" / "pages" / "MapPage.tsx").read_text(
        encoding="utf-8"
    )
    open_layers = (
        web_root / "src" / "components" / "OpenLayersMap.tsx"
    ).read_text(encoding="utf-8")
    clarity = (
        web_root / "src" / "components" / "ImageClarityStatus.tsx"
    ).read_text(encoding="utf-8")

    assert 'path: "/asset-viewer"' in router
    assert 'pathname === "/asset-viewer"' in shell
    assert "ImageClarityStatus" in page
    assert "showBasemap" in page
    assert "qualityMode={quality}" in page
    assert "onSpatialLoadProgress" in page
    assert "eastOffset" in page and "northOffset" in page and "heightOffset" in page
    assert "localStorage.setItem" in page
    assert "disabled" in page and "回波" in page and "反射强度" in page and "轨迹" in page
    assert "formatElevationRange(asset.nativeBounds)" in page
    assert "/v2/asset-viewer?sceneId=" in map_page
    assert "onViewMetricsChange" in open_layers
    assert "metresPerPixel" in open_layers
    assert "不会增加真实细节" in clarity


def test_forest_block_editor_uses_national_administrative_division_selector():
    web_root = ROOT_DIR / "apps" / "web-operations"
    system_source = (ROOT_DIR / "server" / "v2" / "system.py").read_text(encoding="utf-8")
    dictionary_source = (ROOT_DIR / "server" / "modules" / "dictionaries.py").read_text(encoding="utf-8")
    form_source = (web_root / "src" / "pages" / "ForestBlocksPage.tsx").read_text(encoding="utf-8")
    selector_source = (web_root / "src" / "components" / "AdministrativeDivisionSelector.tsx").read_text(encoding="utf-8")

    assert '@router.get("/administrative-divisions")' in system_source
    assert '("710000", "台湾省")' in dictionary_source
    assert "<AdministrativeDivisionSelector" in form_source
    assert 'name="countyCode"' in selector_source
    assert 'name="townCode"' in selector_source
    assert 'name="villageCode"' in selector_source
    assert "请从省级开始选择行政区划" in selector_source


def test_v2_dictionary_governance_reuses_formal_dictionary_storage():
    web_root = ROOT_DIR / "apps" / "web-operations"
    router = (web_root / "src" / "router.tsx").read_text(encoding="utf-8")
    shell = (web_root / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    page = (web_root / "src" / "pages" / "DictionariesPage.tsx").read_text(encoding="utf-8")
    client = (web_root / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    system = (ROOT_DIR / "server" / "v2" / "system.py").read_text(encoding="utf-8")
    dictionaries = (ROOT_DIR / "server" / "modules" / "dictionaries.py").read_text(encoding="utf-8")

    assert 'path: "/system/dictionaries"' in router
    assert "dictionaries: BookOpenText" in shell
    assert '"requiredPermission": "system.dictionaries.view"' in system
    assert 'request<LedgerResponse<DictionaryTypeRecord>>(`/api/dictionaries?' in client
    assert 'request<DictionaryImportResult>' in client
    assert "批量导入词项" in page
    assert "预检数据" in page and "确认写入" in page
    assert '@router.post("/dictionaries/{type_code}/imports")' in dictionaries
    assert "_save_item_records(ordered)" in dictionaries


def test_leadership_cockpit_and_carbon_dashboard_use_live_api_metrics():
    web_root = ROOT_DIR / "apps" / "web-operations"
    router = (web_root / "src" / "router.tsx").read_text(encoding="utf-8")
    shell = (web_root / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    page = (web_root / "src" / "pages" / "LeadershipCockpitPage.tsx").read_text(encoding="utf-8")
    client = (web_root / "src" / "api" / "client.ts").read_text(encoding="utf-8")

    assert 'path: "/cockpit/leadership"' in router
    assert "component: LeadershipCockpitPage" in router
    assert '"leadership-cockpit": LayoutDashboard' in shell
    assert "/api/v2/cockpit/leadership" in client
    assert "综合态势" in page and "碳汇专题" in page
    assert "未接入" in page and "districtRanking" in page


def test_v2_standalone_display_wall_uses_live_cockpit_and_gis_data():
    web_root = ROOT_DIR / "apps" / "web-operations"
    router = (web_root / "src" / "router.tsx").read_text(encoding="utf-8")
    shell = (web_root / "src" / "components" / "AppShell.tsx").read_text(
        encoding="utf-8"
    )
    page = (web_root / "src" / "pages" / "DisplayDashboardPage.tsx").read_text(
        encoding="utf-8"
    )

    assert 'path: "/display"' in router
    assert "component: DisplayDashboardPage" in router
    assert 'pathname === "/display"' in shell
    assert "api.leadershipCockpit" in page
    assert "api.mapConfig" in page
    assert "MapCanvas" in page
    assert "mode={mode}" in page
    assert 'setMode("2d")' in page and 'setMode("3d")' in page
    assert "api.forestBlockMap" in page
    assert "setLeftRailOpen(false)" in page
    assert "setRightRailOpen(false)" in page
    assert "document.documentElement.requestFullscreen()" in page
    assert "综合态势" in page and "碳汇专题" in page
    assert "暂无数据" in page
    assert "搜索与图层" in page
    assert "situationAssets={situationAssets}" in page
    assert "buildMapAnnotations" in page
    assert "MAP_ANNOTATION_KINDS" in page
    assert "api.imageryAssets" in page
    assert "layers={layers}" in page
    assert "imageryAssets={displayedImageryAssets}" in page
    assert "spatial3dAssets={displayedSpatial3dAssets}" in page
    assert "地图图层" in page and "无人机正射成果" in page
    assert "DisplayAnnotationDialog" in page
    assert "api.situationAssets" in page
    assert "DEMO_ASSETS" not in page
    annotations = (web_root / "src" / "maps" / "mapAnnotations.ts").read_text(
        encoding="utf-8"
    )
    assert "高位卡口" in annotations and "安全帽" in annotations
    assert "无人机机巢" in annotations and "无人机任务" in annotations
    assert "无人机正射" in annotations and "实景三维" in annotations
    assert "实时视频播放窗口" in page
    assert "进入运营后台" in page
    assert "前端大屏" in shell


def test_gis_annotation_selection_keeps_point_details_separate_from_forest_blocks():
    page = (
        ROOT_DIR / "apps" / "web-operations" / "src" / "pages" / "MapPage.tsx"
    ).read_text(encoding="utf-8")

    assert "selectedMapAnnotationId" in page
    assert "onSelectSituationAsset={selectMapAnnotation}" in page
    assert "<MapAnnotationCard" in page
    assert "查看关联林班" in page
    assert "setSelectedMapAnnotationId(null)" in page


def test_gis_boundaries_remain_visible_during_viewport_and_filter_refreshes():
    web_root = ROOT_DIR / "apps" / "web-operations" / "src"
    page = (web_root / "pages" / "MapPage.tsx").read_text(encoding="utf-8")
    canvas = (web_root / "components" / "MapCanvas.tsx").read_text(encoding="utf-8")
    client = (web_root / "api" / "client.ts").read_text(encoding="utf-8")

    assert "placeholderData: (previous) => previous" in page
    assert "filterChanged && mapBlocks.isPlaceholderData" in page
    assert "setCachedMapBlocks(EMPTY_FOREST_BLOCK_COLLECTION)" not in page
    assert "forestBlockLoading={mapBlocks.isFetching}" in page
    assert "forestBlockError={Boolean(mapBlocks.error)}" in page
    assert "更新中 · 已保留当前边界" in canvas
    assert "更新失败 · 已保留上次边界" in canvas
    assert "requestDurationMs: Math.max(0, performance.now() - startedAt)" in client


def test_forest_road_ledger_and_spatial_layer_are_wired_into_both_map_engines():
    web_root = ROOT_DIR / "apps" / "web-operations" / "src"
    page = (web_root / "pages" / "MapPage.tsx").read_text(encoding="utf-8")
    canvas = (web_root / "components" / "MapCanvas.tsx").read_text(encoding="utf-8")
    open_layers = (web_root / "components" / "OpenLayersMap.tsx").read_text(encoding="utf-8")
    cesium = (web_root / "components" / "CesiumGlobe.tsx").read_text(encoding="utf-8")
    road_page = (web_root / "pages" / "ForestRoadsPage.tsx").read_text(encoding="utf-8")
    router = (web_root / "router.tsx").read_text(encoding="utf-8")

    assert 'queryFn: api.forestRoadMap' in page
    assert 'toggleLayer("forestRoads")' in page
    assert "林区道路" in page
    assert "roadFeatureCollection={roadFeatureCollection}" in canvas
    assert "roadSourceRef" in open_layers and "createRoadStyle" in open_layers
    assert '"#ffc928"' in open_layers and '"#ff5b5b"' in open_layers
    assert "roadDataSourceRef" in cesium and "clampToGround: true" in cesium
    assert "ForestRoadsPage" in router and 'path: "/resources/roads"' in router
    assert "RoadGeometryEditor" in road_page and "巡检维护记录" in road_page
