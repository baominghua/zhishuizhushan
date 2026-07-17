import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_public_search_controls_have_accessible_names():
    mobile = _read("zhushan-mobile.html")
    satellite = _read("satellite-manager.html")

    assert 'id="mobileSearch" type="search" aria-label="搜索林班、村镇或图层"' in mobile
    assert 'id="catalogFilter" type="search" aria-label="搜索影像名称、卫星或传感器"' in satellite
    assert 'id="catalogBbox" type="text" aria-label="影像空间范围坐标"' in satellite


def test_bigdata_uses_one_current_asset_version_and_null_safe_controls():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")
    css = _read("zhushan-bigdata.css")

    assert 'zhushan-bigdata.css?v=20260716-interaction5' in html
    assert 'zhushan-bigdata.js?v=20260716-interaction5' in html
    assert 'document.querySelector("#zoomIn")?.addEventListener' in js
    assert 'document.querySelector("#zoomOut")?.addEventListener' in js
    assert 'document.querySelector("#closeBusinessCard")?.addEventListener' in js
    assert "max-height: clamp(180px, calc(100vh - 480px), 560px);" in css
    assert "min-height: 120px;" in css
    assert "z-index: 40;" in css


def test_bigdata_forest_filters_live_in_a_hidden_top_popover():
    html = _read("zhushan-bigdata.html")

    assert 'id="forestFilterToggle"' in html
    assert 'aria-controls="forestFilterPanel"' in html
    assert 'aria-expanded="false"' in html
    assert 'id="forestFilterBadge"' in html
    assert re.search(r'<section[^>]+id="forestFilterPanel"[^>]+hidden', html)

    layer_card_start = html.index('<section class="layer-card" id="layerCard">')
    layer_card_end = html.index("</section>", layer_card_start)
    assert 'id="forestFilterPanel"' not in html[layer_card_start:layer_card_end]


def test_bigdata_top_filter_popover_has_state_and_close_interactions():
    js = _read("zhushan-bigdata.js")

    assert "function activeForestFilterCount()" in js
    assert "function syncForestFilterToggleState()" in js
    assert "function setForestFilterPanelOpen(open" in js
    assert 'forestFilterToggle?.addEventListener("click"' in js
    assert 'event.key === "Escape"' in js
    assert "setForestFilterPanelOpen(false)" in js

    map_click = js[js.index('gisMap.on("singleclick"') : js.index('gisMap.on("moveend"')]
    assert "if (!feature)" in map_click
    assert "setForestFilterPanelOpen(false)" in map_click


def test_bigdata_top_filter_popover_is_responsive_and_versioned():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")
    css = _read("zhushan-bigdata.css")
    server = _read("server/app.py")

    assert 'zhushan-bigdata.css?v=20260716-interaction5' in html
    assert 'zhushan-bigdata.js?v=20260716-interaction5' in html
    assert 'SMART_BAMBOO_DASHBOARD_VERSION = "20260716-interaction5"' in js
    assert 'SMART_BAMBOO_DASHBOARD_VERSION = "20260716-interaction5"' in server
    assert ".forest-filter-popover" in css
    assert "width: min(960px, calc(100vw - 48px));" in css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in css
    assert "@media (max-width: 1100px)" in css
    assert "@media (max-width: 700px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_bigdata_top_filter_does_not_overlap_the_layer_ledger():
    js = _read("zhushan-bigdata.js")
    css = _read("zhushan-bigdata.css")

    assert 'layerCard?.classList.toggle("filter-open-hidden", open)' in js
    assert ".layer-card.filter-open-hidden" in css
    assert "top: 132px;" in css
    assert re.search(r"\.forest-filter-popover\s*\{[^}]*z-index: 32;", css, re.S)


def test_legacy_dashboard_does_not_bind_required_events_to_missing_elements():
    html = _read("index.html")
    js = _read("script.js")

    page_ids = set(re.findall(r'id="([^"]+)"', html))
    required_binding_ids = set(
        re.findall(r'document\.querySelector\("#([^"]+)"\)\.addEventListener', js)
    )

    assert required_binding_ids <= page_ids


def test_bigdata_screen_exposes_industry_platform_backend_entry():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")

    assert 'data-business="industry"' in html
    assert "/api/industry-platform/dashboard" in js
    assert "产业平台信息卡" in js
    assert "暂无后台数据" in js


def test_bigdata_business_cards_link_to_independent_admin_pages():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")

    assert 'id="businessAdminLinks"' in html
    assert "renderBusinessAdminLinks" in js
    for page in [
        "admin-farmers.html",
        "admin-cooperatives.html",
        "admin-enterprises.html",
        "admin-plant-protection.html",
        "admin-materials.html",
        "admin-policies.html",
        "admin-trade-matches.html",
        "admin-logistics-traces.html",
        "admin-product-qrcodes.html",
        "admin-supply-chain-finance.html",
        "admin-price-indexes.html",
        "admin-mobile-service-channels.html",
    ]:
        assert page in js


def test_bigdata_business_dashboard_prefers_backend_empty_state_and_admin_href():
    js = _read("zhushan-bigdata.js")
    business_loader = js[js.index("async function loadBackendBusinessCard") : js.index("const backendToolLoaders")]

    assert "function businessDashboardAdminLinks(payload, config)" in js
    assert "payload.emptyText ||" in business_loader
    assert "payload.adminHref" in business_loader
    assert "businessDashboardAdminLinks(payload, config)" in business_loader
    assert "adminLinks: Array.isArray(payload.adminLinks) ? payload.adminLinks : config.adminLinks" not in business_loader


def test_bigdata_carbon_tool_loads_backend_carbon_dashboard():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")

    assert 'data-tool="carbon"' in html
    assert "/api/business/carbon-estimates/dashboard" in js
    assert "admin-carbon-estimates.html" in js
    assert "南谷生态样方" not in js
    assert "18.7 万 tCO2e" not in js


def test_bigdata_search_tool_loads_backend_forest_block_search():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")

    assert 'data-tool="search"' in html
    assert "/api/forest-blocks?" in js
    assert "/api/map/forest-blocks/summary" in js
    assert "loadForestSearchCard" in js
    assert "486" not in js
    assert "1,286" not in js
    assert "北坡示范林班" not in js


def test_bigdata_satellite_track_tool_loads_backend_imagery_tasks():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")

    assert 'data-tool="satelliteTrack"' in html
    assert "/api/dashboard/satellite-track" in js
    assert "/api/tasks?limit=8" not in js
    assert "/api/scenes?limit=1" not in js
    assert "loadSatelliteTrackCard" in js
    assert "GF-2 PMS" not in js
    assert "Sentinel-2 MSI" not in js
    assert "7 轨" not in js


def test_bigdata_layer_card_loads_published_backend_layers():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")
    css = _read("zhushan-bigdata.css")

    assert 'id="dashboardPublishedLayerControls"' in html
    assert 'aria-label="后台发布图层"' in html
    assert "/api/map-layers/dashboard" in js
    assert "payload.summary" in js
    assert "loadDashboardPublishedLayers" in js
    assert "renderDashboardPublishedLayerControls" in js
    assert "暂无后台发布图层" in js
    assert "dashboard-published-layers" in css


def test_bigdata_layer_card_loads_backend_delivery_workflow_status():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")
    css = _read("zhushan-bigdata.css")

    assert 'id="dashboardWorkflowStatus"' in html
    assert 'aria-label="数据交付闭环"' in html
    assert "/api/dashboard/workflow-status" in js
    assert "/api/imports/forest-blocks/workflow-summary" not in js
    assert "/api/scenes/workflow-summary" not in js
    assert "/api/imports/forest-blocks/delivery-packages?limit=5" not in js
    assert "loadDashboardWorkflowStatus" in js
    assert "renderDashboardWorkflowStatus" in js
    assert "dashboardWorkflowCard" in js
    assert "admin-imports.html?workflowQueue=pendingReview" in js
    assert "admin-imagery.html?published=false" in js
    assert "admin-imports.html?deliveryPackageStatus=awaiting_delivery" in js
    assert "暂无后台交付闭环数据" in js
    assert "dashboard-workflow-status" in css


def test_bigdata_delivery_package_rows_deep_link_to_batch_detail():
    js = _read("zhushan-bigdata.js")

    assert "function dashboardWorkflowPackageHref" in js
    assert "item.adminHref" in js
    assert 'batchId=${encodeURIComponent(item.batchId || item.id || "")}' in js
    assert "dashboardWorkflowPackageHref(item)" in js


def test_mobile_screen_loads_industry_platform_backend_panel():
    html = _read("zhushan-mobile.html")
    js = _read("zhushan-mobile.js")

    assert 'data-nav="industry"' in html
    assert 'id="mobileIndustryPanel"' in html
    assert "/api/industry-platform/dashboard" in js
    assert "loadMobileIndustryDashboard" in js
    assert "暂无后台数据" in js


def test_mobile_industry_panel_links_to_independent_admin_pages():
    html = _read("zhushan-mobile.html")
    js = _read("zhushan-mobile.js")

    assert 'id="mobileIndustryAdminLinks"' in html
    assert "renderMobileIndustryAdminLinks" in js
    for page in [
        "admin-trade-matches.html",
        "admin-logistics-traces.html",
        "admin-product-qrcodes.html",
        "admin-supply-chain-finance.html",
        "admin-price-indexes.html",
        "admin-mobile-service-channels.html",
    ]:
        assert page in js


def test_mobile_business_nav_loads_backend_dashboards():
    html = _read("zhushan-mobile.html")
    js = _read("zhushan-mobile.js")

    for nav_key in ["farmers", "cooperatives", "enterprises", "plant-protection-events", "carbon-estimates"]:
        assert f'data-nav="{nav_key}"' in html
    for endpoint in [
        "/api/business/farmers/dashboard",
        "/api/business/cooperatives/dashboard",
        "/api/business/enterprises/dashboard",
        "/api/business/plant-protection-events/dashboard",
        "/api/business/carbon-estimates/dashboard",
    ]:
        assert endpoint in js
    assert "MOBILE_BUSINESS_DASHBOARDS" in js
    assert "loadMobileBusinessDashboard" in js
    assert "renderMobileBusinessDashboard" in js


def test_mobile_business_dashboard_prefers_backend_empty_state_and_admin_href():
    js = _read("zhushan-mobile.js")

    assert "payload.adminHref" in js
    assert "payload.adminLabel" in js
    assert "payload.emptyText || options.emptyText" in js


def test_mobile_resource_stats_load_from_backend_summary():
    html = _read("zhushan-mobile.html")
    js = _read("zhushan-mobile.js")

    assert 'id="mobileStats"' in html
    assert 'data-stat="totalAreaMu"' in html
    assert 'data-stat="totalBlocks"' in html
    assert 'data-stat="healthyRate"' in html
    assert "/api/map/forest-blocks/summary" in js
    assert "loadMobileResourceSummary" in js
    assert "10.32" not in html
    assert "486" not in html
    assert "86%" not in html


def test_mobile_map_search_loads_backend_forest_blocks():
    html = _read("zhushan-mobile.html")
    js = _read("zhushan-mobile.js")

    assert 'data-mobile-layer="backendBlocks"' in html
    assert "/api/forest-blocks?" in js
    assert "/api/map/forest-blocks.geojson" in js
    assert "MOBILE_FOREST_BLOCK_MAX_FEATURES" in js
    assert "loadMobileForestBlockSearch" in js
    assert "loadMobileForestBlockLayer" in js
    assert "renderBackendForestBlockCard" in js
    assert "backendForestBlock" in js


def test_mobile_layer_drawer_loads_published_backend_layers():
    html = _read("zhushan-mobile.html")
    js = _read("zhushan-mobile.js")
    css = _read("zhushan-mobile.css")

    assert 'id="publishedLayerControls"' in html
    assert 'aria-label="后台发布图层"' in html
    assert "/api/map-layers/dashboard" in js
    assert "payload.summary" in js
    assert "loadMobilePublishedLayers" in js
    assert "renderMobilePublishedLayerControls" in js
    assert "暂无后台发布图层" in js
    assert "published-layer-controls" in css


def test_bigdata_map_switches_between_admin_aggregates_and_block_boundaries():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")

    assert 'data-forest-filter="villageCode"' in html
    assert "/api/map/forest-blocks/aggregates" in js
    assert "function aggregateLevelForZoom" in js
    assert "function loadForestAggregates" in js
    assert "gisLayers.bambooAggregates" in js
    assert 'feature.set("aggregateLevel"' in js
    assert "clearForestAggregateFeatures" in js
    assert 'params.set("zoom", String(Math.round(gisMap.getView().getZoom())))' in js


def test_bigdata_high_zoom_prefers_mvt_tiles_with_geojson_fallback():
    js = _read("zhushan-bigdata.js")

    assert "new ol.source.VectorTile" in js
    assert "new ol.format.MVT" in js
    assert "/api/map/forest-blocks/tiles/{z}/{x}/{y}.pbf" in js
    assert "refreshForestVectorTileSource" in js
    assert "forestVectorTileAvailable" in js
    assert "/api/map/forest-blocks.geojson" in js
    assert "tileloaderror" in js


def test_bigdata_zoom_controls_can_reach_vector_tile_levels():
    js = _read("zhushan-bigdata.js")

    assert "const MAP_ZOOM_PER_SCALE_UNIT = 7.5;" in js
    assert "10 + (zoom - 1) * MAP_ZOOM_PER_SCALE_UNIT" in js
    assert "1 + (mapZoom - 10) / MAP_ZOOM_PER_SCALE_UNIT" in js


def test_bigdata_map_persists_view_filters_and_layer_visibility():
    js = _read("zhushan-bigdata.js")

    assert "SMART_BAMBOO_MAP_STATE_KEY" in js


def test_bigdata_map_keeps_neutral_fallback_until_online_tiles_load():
    js = _read("zhushan-bigdata.js")
    css = _read("zhushan-bigdata.css")

    assert 'url("assets/nanping-3d-map.png")' not in css
    assert ".map-scene::before" in css
    assert "body.basemap-loaded .map-scene::before" in css
    assert "body.basemap-failed .map-scene::before" in css
    assert 'document.body.classList.add("basemap-loaded")' in js
    assert 'document.body.classList.remove("basemap-failed")' in js
    assert 'document.body.classList.add("basemap-failed")' in js
    assert 'document.body.classList.remove("basemap-loaded")' in js
    assert 'source.on("tileloadend", markBasemapCanvasLoaded)' in js
    assert "function readDashboardMapState" in js
    assert "function persistDashboardMapState" in js
    assert "function restoreDashboardLayerState" in js
    assert "restoredFilters" in js
    assert "localStorage.setItem(SMART_BAMBOO_MAP_STATE_KEY" in js
    assert "function syncZoomControlFromMap" in js
    assert "syncZoomControlFromMap();" in js
    assert "setZoom(1);" not in js
    assert "function hasStoredDashboardView" in js
    assert "!hasStoredDashboardView()" in js


def test_bigdata_does_not_seed_static_demo_map_features():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")

    assert 'data-map-layer=' not in html
    assert "function createEmptyDataLayer" in js
    assert "gisLayers.quality = createEmptyDataLayer();" in js
    assert "gisLayers.soil = createEmptyDataLayer();" in js
    assert "gisLayers.growth = createEmptyDataLayer();" in js
    assert "gisLayers.yield = createEmptyDataLayer();" in js
    assert "gisLayers.pest = createEmptyDataLayer();" in js
    assert "gisLayers.ownership = createEmptyDataLayer();" in js
    assert "createPointLayer(" not in js
    assert "createLineLayer(" not in js
    assert "createOverlayLayer(" not in js


def test_bigdata_remote_imagery_uses_published_layers_instead_of_admin_scene_catalog():
    js = _read("zhushan-bigdata.js")

    assert "function publishedImagerySceneFromLayer" in js
    assert "function syncDashboardPublishedImageryLayers" in js
    assert "syncDashboardPublishedImageryLayers(payload.items || [])" in js
    assert "remoteSensing.client.listRemoteScenes()" not in js
    assert "syncRemoteSensingScenes();" not in js


def test_bigdata_detects_stale_open_tabs_and_reloads_current_build():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")

    assert "SMART_BAMBOO_DASHBOARD_VERSION" in js
    assert "/api/system/frontend-version" in js
    assert "startDashboardVersionMonitor" in js
    assert "window.location.replace" in js
    assert "serverVersion <= SMART_BAMBOO_DASHBOARD_VERSION" in js
    assert "20260716-interaction5" in html
