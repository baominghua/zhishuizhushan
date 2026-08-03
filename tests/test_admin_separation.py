import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


ADMIN_PAGES = {
    "overview": "admin.html",
    "deployment": "admin-deployment.html",
    "blocks": "admin-blocks.html",
    "rights": "admin-rights.html",
    "linkages": "admin-linkages.html",
    "farmers": "admin-farmers.html",
    "cooperatives": "admin-cooperatives.html",
    "enterprises": "admin-enterprises.html",
    "plantProtection": "admin-plant-protection.html",
    "materials": "admin-materials.html",
    "policies": "admin-policies.html",
    "stewardshipAgreements": "admin-stewardship-agreements.html",
    "franchiseBases": "admin-franchise-bases.html",
    "maintenanceTasks": "admin-maintenance-tasks.html",
    "workLogs": "admin-work-logs.html",
    "droneTasks": "admin-drone-tasks.html",
    "equipment": "admin-equipment.html",
    "pestWarnings": "admin-pest-warnings.html",
    "materialServices": "admin-material-services.html",
    "yieldForecasts": "admin-yield-forecasts.html",
    "harvestPlans": "admin-harvest-plans.html",
    "incomeEstimates": "admin-income-estimates.html",
    "performanceDashboards": "admin-performance-dashboards.html",
    "carbonEstimates": "admin-carbon-estimates.html",
    "tradeMatches": "admin-trade-matches.html",
    "logisticsTraces": "admin-logistics-traces.html",
    "productQrcodes": "admin-product-qrcodes.html",
    "supplyChainFinance": "admin-supply-chain-finance.html",
    "priceIndexes": "admin-price-indexes.html",
    "mobileServiceChannels": "admin-mobile-service-channels.html",
    "mapLayers": "admin-map-layers.html",
    "dictionaries": "admin-dictionaries.html",
    "imports": "admin-imports.html",
    "imagery": "admin-imagery.html",
    "roles": "admin-roles.html",
    "users": "admin-users.html",
}


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_admin_sidebar_links_to_independent_module_pages_instead_of_hash_sections():
    html = _read("admin.html")

    for page in ADMIN_PAGES.values():
        assert f'href="{page}"' in html
    assert 'href="#blockWorkbench"' not in html
    assert 'href="#rightsWorkbench"' not in html
    assert 'href="#businessWorkbench"' not in html
    assert 'href="#sourceWorkbench"' not in html


def test_each_admin_module_page_declares_a_permission_boundary():
    for module, page in ADMIN_PAGES.items():
        html = _read(page)
        assert f'data-admin-module="{module}"' in html
        assert "data-permission=" in html
        assert '<nav class="sidebar-nav" aria-label="后台模块导航"' in html


def test_each_admin_module_page_exposes_user_account_management_entry():
    for page in ADMIN_PAGES.values():
        html = _read(page)
        assert 'href="admin-users.html"' in html
        assert 'data-module="users"' in html


def test_each_admin_module_page_seeds_the_full_navigation_menu():
    for page in ADMIN_PAGES.values():
        html = _read(page)
        for linked_page in ADMIN_PAGES.values():
            assert f'href="{linked_page}"' in html


def test_dictionary_admin_is_a_full_width_ledger_with_independent_crud_drawers():
    html = _read("admin-dictionaries.html")
    js = _read("admin-dictionaries.js")

    assert 'data-admin-module="dictionaries"' in html
    assert 'data-permission="system.dictionaries.view"' in html
    assert 'data-admin-primary-ledger="true"' in html
    assert 'id="dictionaryRows"' in html
    assert "<th>操作</th>" in html
    assert 'id="dictionaryDetailPanel"' in html
    assert 'id="dictionaryForm"' in html
    assert 'id="dictionaryItemForm"' in html
    assert 'class="crud-modal hidden"' in html
    assert 'data-row-action="view"' in js
    assert 'data-row-action="edit"' in js
    assert 'data-row-action="delete"' in js
    assert "system.dictionaries.create" in js
    assert "system.dictionaries.update" in js
    assert "system.dictionaries.delete" in js
    assert "system.dictionaries.restore" in js
    assert "/api/dictionary-options/" in js


def test_dictionary_ledger_has_a_readable_mobile_summary_and_business_forms_hide_storage_details():
    html = _read("admin-dictionaries.html")
    js = _read("admin-dictionaries.js")
    css = _read("admin.css")
    business_js = _read("admin-business-module.js")

    assert 'class="dictionary-ledger-table"' in html
    assert "dictionary-primary-cell" in js
    assert "dictionary-mobile-meta" in js
    assert "dictionary-actions-cell" in js
    assert ".dictionary-ledger-table thead" in css
    assert ".dictionary-mobile-meta" in css
    assert "字段按后台数据模型校验" not in business_js
    assert "MySQL 结构化属性索引" not in business_js


def test_role_admin_surfaces_permission_closure_guides_for_first_stage_workflows():
    html = _read("admin-roles.html")
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert 'id="roleClosureGuides"' in html
    assert "permissionClosures" in js
    assert "renderPermissionClosureGuides" in js
    assert "roleClosureCard" in js
    assert 'data-closure-action="apply"' in js
    assert 'data-closure-action="export"' in js
    assert "applyPermissionClosure" in js
    assert "exportPermissionClosurePackage" in js
    assert "/api/admin/permission-closures.json" in js
    assert "permission-closure-package.json" in js
    assert "phase1-delivery-loop" in js
    assert "identity-access-loop" in js
    assert "permission-closure-grid" in css
    assert "role-closure-card" in css


def test_role_admin_surfaces_operation_queue_for_permission_closure():
    html = _read("admin-roles.html")
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert 'id="roleOperationQueueRows"' in html
    assert 'id="refreshRoleOperationQueue"' in html
    assert "/api/admin/roles/operation-queue" in js
    assert "state.operationQueue" in js
    assert "function loadRoleOperationQueue" in js
    assert "function renderRoleOperationQueue" in js
    assert "function roleOperationQueueItem" in js
    assert 'data-role-operation-action="open"' in js
    assert "requiredPermission" in js
    assert '$("#refreshRoleOperationQueue")?.addEventListener("click", loadRoleOperationQueue)' in js
    assert ".operation-queue-grid" in css
    assert ".operation-queue-item" in css


def test_user_admin_surfaces_operation_queue_for_access_closure():
    html = _read("admin-users.html")
    js = _read("admin-users.js")
    css = _read("admin.css")

    assert 'id="userOperationQueueRows"' in html
    assert 'id="refreshUserOperationQueue"' in html
    assert "/api/admin/users/operation-queue" in js
    assert "state.operationQueue" in js
    assert "function loadUserOperationQueue" in js
    assert "function renderUserOperationQueue" in js
    assert "function userOperationQueueItem" in js
    assert 'data-user-operation-action="open"' in js
    assert "requiredPermission" in js
    assert '$("#refreshUserOperationQueue")?.addEventListener("click", loadUserOperationQueue)' in js
    assert ".operation-queue-grid" in css
    assert ".operation-queue-item" in css


def test_role_admin_prioritizes_granular_phase1_closure_guides():
    js = _read("admin-roles.js")

    assert "phase1-import-acceptance-loop" in js
    assert "phase1-imagery-delivery-loop" in js
    assert "phase1-layer-publishing-loop" in js
    assert js.index("phase1-import-acceptance-loop") < js.index("phase1-delivery-loop")
    assert js.index("phase1-imagery-delivery-loop") < js.index("phase1-delivery-loop")
    assert js.index("phase1-layer-publishing-loop") < js.index("phase1-delivery-loop")


def test_role_closure_cards_show_intentionally_omitted_high_risk_permissions():
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert "function closureOmittedPermissionChips" in js
    assert "closure.omittedPermissions" in js
    assert "omitted-permission-chips" in js
    assert "未授予高危权限" in js
    assert ".omitted-permission-chips" in css


def test_role_closure_cards_show_expanded_action_permission_chips():
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert "function closureExpandedPermissionChips" in js
    assert "closure.expandedPermissions" in js
    assert "closure-permission-chips" in js
    assert "renderCompactList(expandedPermissions" in js
    assert "expandedPermissionCount" in js
    assert ".closure-permission-chips" in css


def test_role_admin_fallback_manage_implications_include_map_layer_export():
    js = _read("admin-roles.js")

    map_manage_block = js[js.index('"map.layers.manage"'): js.index('"map.layers.publish"')]
    assert '"map.layers.export"' in map_manage_block


def test_common_action_permission_fallback_includes_map_layer_manage_actions():
    js = _read("admin-common.js")

    map_manage_block = js[js.index('"map.layers.manage"'): js.index('"system.roles.manage"')]
    for permission in [
        "map.layers.view",
        "map.layers.create",
        "map.layers.update",
        "map.layers.delete",
        "map.layers.restore",
        "map.layers.export",
        "map.layers.publish",
    ]:
        assert f'"{permission}"' in map_manage_block


def test_admin_permission_fallbacks_expand_business_manage_actions():
    for filename in ["admin-common.js", "admin-roles.js"]:
        js = _read(filename)
        assert "BUSINESS_MANAGE_PERMISSION_PREFIXES" in js
        assert "function businessManagePermissionImplications" in js
        for prefix in [
            "business.farmers",
            "business.cooperatives",
            "business.enterprises",
            "business.plantProtection",
            "business.mobileServiceChannels",
        ]:
            assert f'"{prefix}"' in js
        for action in ["view", "create", "update", "delete", "restore", "export"]:
            assert f'`${{prefix}}.{action}`' in js


def test_forest_blocks_and_rights_are_not_rendered_on_the_same_page():
    blocks = _read("admin-blocks.html")
    rights = _read("admin-rights.html")

    assert 'id="blockForm"' in blocks
    assert 'id="rightForm"' not in blocks
    assert 'id="rightForm"' in rights
    assert 'id="blockForm"' not in rights


def test_forest_block_admin_uses_ledger_detail_and_separate_crud_actions():
    html = _read("admin-blocks.html")
    js = _read("admin-blocks.js")

    assert 'id="blockLedgerPanel"' in html
    assert 'id="blockDetailPanel"' in html
    assert 'id="blockEditorOverlay"' in html
    assert "ledger-workbench-full" in html
    assert "ledger-table-full" in html
    assert "<th>操作</th>" in html
    assert 'id="editBlock"' not in html
    assert 'id="deleteBlock"' not in html
    assert 'id="cancelBlockEdit"' in html
    assert 'data-mode="ledger"' in html
    assert "function renderDetail" in js
    assert "function openBlockEditor" in js
    assert "function closeBlockEditor" in js
    assert "function handleRowAction" in js
    assert 'data-row-action="view"' in js
    assert 'data-row-action="edit"' in js
    assert 'data-row-action="delete"' in js
    assert "forest.blocks.update" in js
    assert "forest.blocks.delete" in js
    assert "event.stopPropagation()" in js
    assert "renderDetail(activeBlock())" in js
    assert "fillForm(activeBlock())" not in js


def test_forest_block_admin_binds_actions_before_waiting_for_smart_fields():
    js = _read("admin-blocks.js")

    initialize = js.split("async function initialize()", 1)[1].split("initialize();", 1)[0]
    assert "const smartFieldsReady = setupSmartFields();" in initialize
    assert initialize.index("attachEvents();") < initialize.index("await smartFieldsReady;")
    assert "await loadBlocks();" in initialize
    assert "部分智能选项加载失败" in js
    assert "林班加载失败：" in js


def test_forest_block_admin_can_show_deleted_blocks_and_restore_them():
    html = _read("admin-blocks.html")
    js = _read("admin-blocks.js")

    assert 'id="includeDeletedBlocks"' in html
    assert "includeDeleted" in js
    assert "function isDeletedBlock" in js
    assert "function blockActionButtons" in js
    assert 'data-block-action="restore"' in js
    assert "function restoreBlock" in js
    assert "/restore" in js


def test_forest_block_admin_shows_version_history_and_rollback_action():
    html = _read("admin-blocks.html")
    js = _read("admin-blocks.js")

    assert 'id="blockVersionList"' in html
    assert "/versions" in js
    assert "/rollback" in js
    assert "function loadBlockVersions" in js
    assert "function renderBlockVersions" in js
    assert "function rollbackBlockVersion" in js
    assert 'data-version-action="rollback"' in js
    assert "forest.blocks.rollback" in js


def test_forest_right_admin_shows_version_history_and_rollback_action():
    html = _read("admin-rights.html")
    js = _read("admin-rights.js")

    assert 'id="rightVersionList"' in html
    assert "/versions" in js
    assert "/rollback" in js
    assert "function loadRightVersions" in js
    assert "function renderRightVersions" in js
    assert "function rollbackRightVersion" in js
    assert 'data-version-action="rollback"' in js
    assert "forest.rights.rollback" in js


def test_forest_right_admin_can_show_deleted_archives_and_restore_them():
    html = _read("admin-rights.html")
    js = _read("admin-rights.js")

    assert 'id="includeDeletedRights"' in html
    assert "includeDeleted" in js
    assert "function isDeletedRight" in js
    assert "function rightActionButtons" in js
    assert 'data-right-action="restore"' in js
    assert "function restoreRight" in js
    assert "/restore" in js


def test_business_entities_are_independent_pages_not_a_single_module_dropdown():
    for page in [
        "admin-farmers.html",
        "admin-cooperatives.html",
        "admin-enterprises.html",
        "admin-plant-protection.html",
        "admin-materials.html",
        "admin-policies.html",
        "admin-stewardship-agreements.html",
        "admin-franchise-bases.html",
        "admin-maintenance-tasks.html",
        "admin-work-logs.html",
        "admin-drone-tasks.html",
        "admin-equipment.html",
        "admin-pest-warnings.html",
        "admin-material-services.html",
        "admin-yield-forecasts.html",
        "admin-harvest-plans.html",
        "admin-income-estimates.html",
        "admin-performance-dashboards.html",
        "admin-carbon-estimates.html",
        "admin-trade-matches.html",
        "admin-logistics-traces.html",
        "admin-product-qrcodes.html",
        "admin-supply-chain-finance.html",
        "admin-price-indexes.html",
        "admin-mobile-service-channels.html",
    ]:
        html = _read(page)
        assert 'id="businessModuleSelect"' not in html
        assert 'data-business-endpoint="' in html
        assert 'id="businessForm"' in html


def test_business_admin_pages_use_localized_domain_kickers():
    for page in [
        "admin-farmers.html",
        "admin-cooperatives.html",
        "admin-enterprises.html",
        "admin-plant-protection.html",
        "admin-materials.html",
        "admin-policies.html",
    ]:
        html = _read(page)
        assert "Business Module" not in html


def test_management_ledgers_use_full_width_rows_with_action_column():
    pages = [
        "admin-rights.html",
        "admin-linkages.html",
        "admin-farmers.html",
        "admin-cooperatives.html",
        "admin-enterprises.html",
        "admin-plant-protection.html",
        "admin-materials.html",
        "admin-policies.html",
        "admin-stewardship-agreements.html",
        "admin-franchise-bases.html",
        "admin-maintenance-tasks.html",
        "admin-work-logs.html",
        "admin-drone-tasks.html",
        "admin-equipment.html",
        "admin-pest-warnings.html",
        "admin-material-services.html",
        "admin-yield-forecasts.html",
        "admin-harvest-plans.html",
        "admin-income-estimates.html",
        "admin-performance-dashboards.html",
        "admin-carbon-estimates.html",
        "admin-trade-matches.html",
        "admin-logistics-traces.html",
        "admin-product-qrcodes.html",
        "admin-supply-chain-finance.html",
        "admin-price-indexes.html",
        "admin-mobile-service-channels.html",
        "admin-map-layers.html",
        "admin-imagery.html",
        "admin-roles.html",
        "admin-users.html",
    ]

    for page in pages:
        html = _read(page)
        assert "ledger-workbench-full" in html
        assert "ledger-table-full" in html
        assert "<th>操作</th>" in html
        assert 'class="crud-modal' in html
        assert "detail-grid" in html


def test_summary_heavy_pages_promote_the_primary_ledger_after_filters():
    common_js = _read("admin-common.js")

    for page in [
        "admin-blocks.html",
        "admin-map-layers.html",
        "admin-roles.html",
        "admin-users.html",
        "admin-imports.html",
        "admin-imagery.html",
    ]:
        html = _read(page)
        assert 'data-admin-primary-ledger="true"' in html

    assert "function promotePrimaryLedger" in common_js
    assert '[data-admin-primary-ledger="true"]' in common_js
    assert 'main.insertBefore(ledger, config.nextElementSibling)' in common_js
    assert "promotePrimaryLedger();" in common_js


def test_shared_admin_shell_collapses_connection_context_outside_business_filters():
    common_js = _read("admin-common.js")
    css = _read("admin.css")

    assert "function groupConnectionContextFields" in common_js
    assert '["apiBase", "authRoles", "authAreas", "authUser"]' in common_js
    assert 'details.className = "connection-context-disclosure"' in common_js
    assert 'summary.textContent = "连接与权限上下文"' in common_js
    assert "groupConnectionContextFields();" in common_js
    assert ".connection-context-disclosure" in css
    assert ".connection-context-grid" in css


def test_role_ledger_uses_independent_crud_action_permissions():
    html = _read("admin-roles.html")
    js = _read("admin-roles.js")

    assert 'data-permission="system.roles.view"' in html
    assert 'id="newRole" type="button" class="button-ghost" data-permission="system.roles.create"' in html
    assert "const ROLE_CREATE_PERMISSION = \"system.roles.create\"" in js
    assert "const ROLE_UPDATE_PERMISSION = \"system.roles.update\"" in js
    assert "const ROLE_DELETE_PERMISSION = \"system.roles.delete\"" in js
    assert "const ROLE_RESTORE_PERMISSION = \"system.roles.restore\"" in js
    assert 'data-row-action="edit" data-permission="${ROLE_UPDATE_PERMISSION}"' in js
    assert 'data-row-action="delete" data-permission="${ROLE_DELETE_PERMISSION}"' in js
    assert 'data-role-action="restore" data-permission="${ROLE_RESTORE_PERMISSION}"' in js


def test_user_ledger_uses_independent_crud_action_permissions():
    html = _read("admin-users.html")
    js = _read("admin-users.js")

    assert 'data-permission="system.users.view"' in html
    assert 'id="newUser" type="button" class="button-ghost" data-permission="system.users.create"' in html
    assert "const USER_CREATE_PERMISSION = \"system.users.create\"" in js
    assert "const USER_UPDATE_PERMISSION = \"system.users.update\"" in js
    assert "const USER_DELETE_PERMISSION = \"system.users.delete\"" in js
    assert "const USER_RESTORE_PERMISSION = \"system.users.restore\"" in js
    assert "rowActionButtons({ edit: USER_UPDATE_PERMISSION, delete: USER_DELETE_PERMISSION })" in js
    assert 'data-user-action="restore" data-permission="${USER_RESTORE_PERMISSION}"' in js


def test_management_scripts_render_row_actions_and_permission_buttons():
    common_js = _read("admin-common.js")
    business_js = _read("admin-business-module.js")
    assert "function rowActionButtons" in common_js
    assert 'data-row-action="view"' in common_js
    assert 'data-row-action="edit"' in common_js
    assert 'data-row-action="delete"' in common_js
    assert 'id="includeDeletedBusinessRecords" type="checkbox" data-permission="${businessPermission("restore")}"' in business_js

    scripts = {
        "admin-rights.js": "forest.rights.update",
        "admin-linkages.js": "forest.linkages.manage",
        "admin-business-module.js": "pagePermission",
        "admin-map-layers.js": "map.layers.publish",
        "admin-imagery.js": "imagery.scenes.update",
        "admin-roles.js": "system.roles.manage",
    }

    for script, permission in scripts.items():
        js = _read(script)
        assert "function renderDetail" in js
        assert "function open" in js and "Editor" in js
        assert "function close" in js and "Editor" in js
        assert "function handleRowAction" in js
        if script in {"admin-rights.js", "admin-imagery.js", "admin-map-layers.js"}:
            assert 'data-row-action="edit"' in js
            assert 'data-row-action="delete"' in js
        else:
            assert "rowActionButtons" in js
        assert "event.stopPropagation()" in js
        assert "applyActionPermissions()" in js
        assert permission in js


def test_admin_role_page_surfaces_cross_module_permission_dependencies():
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert "permissionDependencyIssues" in js
    assert "requiresAllPermissions" in js
    assert "requiresAnyPermissions" in js
    assert "依赖权限" in js
    assert "跨模块依赖缺口" in js
    assert "permission-dependency-scope" in css


def test_admin_deployment_groups_core_api_checks_by_domain():
    html = _read("admin-deployment.html")
    js = _read("admin-deployment.js")
    css = _read("admin.css")

    assert 'id="apiCheckGroupSummary"' in html
    assert "groupApiChecksByDomain" in js
    assert "api-check-group-row" in js
    assert "api-check-group-summary" in css
    assert "api-check-group-row" in css


def test_admin_pages_use_page_specific_scripts_with_shared_shell():
    expected_scripts = {
        "admin.html": "admin-dashboard.js",
        "admin-deployment.html": "admin-deployment.js",
        "admin-blocks.html": "admin-blocks.js",
        "admin-rights.html": "admin-rights.js",
        "admin-linkages.html": "admin-linkages.js",
        "admin-farmers.html": "admin-business-module.js",
        "admin-cooperatives.html": "admin-business-module.js",
        "admin-enterprises.html": "admin-business-module.js",
        "admin-plant-protection.html": "admin-business-module.js",
        "admin-materials.html": "admin-business-module.js",
        "admin-policies.html": "admin-business-module.js",
        "admin-stewardship-agreements.html": "admin-business-module.js",
        "admin-franchise-bases.html": "admin-business-module.js",
        "admin-maintenance-tasks.html": "admin-business-module.js",
        "admin-work-logs.html": "admin-business-module.js",
        "admin-drone-tasks.html": "admin-business-module.js",
        "admin-equipment.html": "admin-business-module.js",
        "admin-pest-warnings.html": "admin-business-module.js",
        "admin-material-services.html": "admin-business-module.js",
        "admin-yield-forecasts.html": "admin-business-module.js",
        "admin-harvest-plans.html": "admin-business-module.js",
        "admin-income-estimates.html": "admin-business-module.js",
        "admin-performance-dashboards.html": "admin-business-module.js",
        "admin-carbon-estimates.html": "admin-business-module.js",
        "admin-trade-matches.html": "admin-business-module.js",
        "admin-logistics-traces.html": "admin-business-module.js",
        "admin-product-qrcodes.html": "admin-business-module.js",
        "admin-supply-chain-finance.html": "admin-business-module.js",
        "admin-price-indexes.html": "admin-business-module.js",
        "admin-mobile-service-channels.html": "admin-business-module.js",
        "admin-map-layers.html": "admin-map-layers.js",
        "admin-imports.html": "admin-imports.js",
        "admin-imagery.html": "admin-imagery.js",
        "admin-roles.html": "admin-roles.js",
        "admin-users.html": "admin-users.js",
    }

    for page, script in expected_scripts.items():
        html = _read(page)
        assert 'src="admin-common.js"' in html
        assert f'src="{script}' in html


def test_shared_admin_shell_loads_effective_menu_permissions_from_session_profile():
    js = _read("admin-common.js")

    assert 'authApi("/api/auth/me")' in js
    assert "function refreshSession" in js
    assert "applyMenuAndPermissions(payload)" in js
    assert "function visibleMenuKeys" in js
    assert "payload.visibleMenuModules" in js
    assert "allowedModules.includes(link.dataset.module)" in js
    assert "function renderEffectivePermissionStatus" in js
    assert "effectivePermissionSummary" in js


def test_shared_admin_shell_applies_button_level_permissions():
    js = _read("admin-common.js")

    assert "applyActionPermissions" in js
    assert "data-permission" in js
    assert "data-permission-all" in js
    assert "data-permission-any" in js
    assert "permissionRequirementState" in js
    assert "element.disabled = true" in js
    assert "const hasConfiguredPermissions = Array.isArray(permissions);" in js


def test_import_and_imagery_publish_buttons_declare_cross_module_map_layer_permissions():
    common_js = _read("admin-common.js")
    imports_html = _read("admin-imports.html")
    imports_js = _read("admin-imports.js")
    imagery_html = _read("admin-imagery.html")
    imagery_js = _read("admin-imagery.js")

    assert "permissionSatisfies(permissions, permission)" in common_js
    assert "some((permission) => permissionSatisfies(permissions, permission))" in common_js
    assert 'id="linkImportBatchSceneLayer"' in imports_html
    assert 'data-permission="imports.sceneLayers.link"' in imports_html
    assert 'data-permission-all="map.layers.publish"' in imports_html
    assert 'data-permission-any="map.layers.create map.layers.update"' in imports_html
    assert 'id="checkImportBatchPublishReadiness"' in imports_html
    assert "IMPORT_MAP_LAYER_REQUIRED_PERMISSION" in imports_js
    assert "IMPORT_MAP_LAYER_UPSERT_PERMISSIONS" in imports_js
    assert "setCompoundPermission" in imports_js
    assert 'id="publishSceneLayer"' in imagery_html
    assert 'data-permission="imagery.layers.publish"' in imagery_html
    assert 'data-permission-all="map.layers.publish"' in imagery_html
    assert 'data-permission-any="map.layers.create map.layers.update"' in imagery_html
    assert "IMAGERY_MAP_LAYER_REQUIRED_PERMISSION" in imagery_js
    assert "IMAGERY_MAP_LAYER_UPSERT_PERMISSIONS" in imagery_js
    assert "setCompoundPermission" in imagery_js


def test_shared_admin_shell_honors_manage_permission_implications_for_action_buttons():
    js = _read("admin-common.js")

    assert "let managePermissionImplications" in js
    assert "function syncPermissionImplications" in js
    assert "payload.permissionImplications" in js
    assert "function permissionSatisfies" in js
    assert "Object.entries(managePermissionImplications)" in js
    assert "permissionSatisfies(permissions, requiredPermission)" in js


def test_shared_admin_shell_warns_when_current_page_is_outside_role_menu():
    js = _read("admin-common.js")
    css = _read("admin.css")

    assert "function renderPageAccessGuard" in js
    assert "pageAccessGuard" in js
    assert "permission-page-denied" in js
    assert "document.body.dataset.permission" in js
    assert ".page-access-guard" in css
    assert ".permission-page-denied" in css
    assert ".permission-page-denied .admin-main > .panel:not(.config-panel)" in css
    assert "pointer-events: none;" in css


def test_admin_sidebar_handles_long_module_menus_without_losing_context():
    css = _read("admin.css")

    assert ".admin-sidebar" in css
    assert "position: sticky;" in css
    assert "overflow-y: auto;" in css
    assert "scrollbar-gutter: stable;" in css
    assert "position: static;" in css


def test_admin_common_groups_static_sidebar_menu_before_permission_api_returns():
    js = _read("admin-common.js")

    assert "const STATIC_MENU_GROUPS" in js
    assert "function staticModuleGroup" in js
    assert "function groupStaticNavigation" in js
    assert "nav.dataset.grouped = \"true\";" in js
    assert "groupStaticNavigation();" in js
    assert "空间与权属" in js
    assert "数据治理" in js
    assert "产业平台" in js


def test_shared_admin_shell_reuses_latest_permissions_for_dynamic_buttons():
    js = _read("admin-common.js")

    assert "currentAllowedPermissions" in js
    assert "allowedPermissions ?? currentAllowedPermissions" in js


def test_role_admin_loads_permission_catalog_for_menu_and_permission_inputs():
    html = _read("admin-roles.html")
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert 'list="menuModuleOptions"' in html
    assert 'id="menuModuleOptions"' in html
    assert 'id="permissionOptions"' in html
    assert 'id="menuModuleChecklist"' in html
    assert 'id="permissionChecklist"' in html
    assert 'id="rolePresetSelect"' in html
    assert 'id="rolePresetSummary"' in html
    assert 'id="applyRolePreset"' in html
    assert 'data-permission-any="system.roles.create system.roles.update"' in html
    assert 'id="dataScopeAreas"' in html
    assert 'id="dataScopeProjects"' in html
    assert 'id="dataScopeTowns"' in html
    assert 'id="dataScopeVillages"' in html
    assert 'id="dataScopeBlockCodes"' in html
    assert 'id="roleMenuPreview"' in html
    assert 'id="roleDetailMenuDiagnostics"' in html
    assert 'id="exportRoleReceipt"' in html
    assert 'data-permission="system.roles.export"' in html
    assert 'data-role-selection="menuModules"' in html
    assert 'data-role-selection="permissions"' in html
    assert 'data-role-scope="areas"' in html
    assert 'data-role-scope="projects"' in html
    assert "/api/admin/permission-catalog" in js
    assert "function loadPermissionCatalog" in js
    assert "rolePresets" in js
    assert "function renderRolePresetOptions" in js
    assert "function renderRolePresetSummary" in js
    assert "function applyRolePreset" in js
    assert "preset.menuModules" in js
    assert "preset.permissions" in js
    assert "renderCatalogOptions" in js
    assert "function renderPermissionMatrix" in js
    assert "permissionEntries" in js
    assert "function syncRoleSelectionsToFields" in js
    assert "function collectCheckedValues" in js
    assert "function syncDataScopesFromJson" in js
    assert "function syncDataScopesToJson" in js
    assert "dataScopeTowns" in js
    assert "dataScopeVillages" in js
    assert "dataScopeBlockCodes" in js
    assert "scopes.towns" in js
    assert "scopes.villages" in js
    assert "scopes.blockCodes" in js
    assert "function renderRoleMenuPreview" in js
    assert "function renderRoleDetailMenuDiagnostics" in js
    assert "function roleMenuDiagnosticsForRole" in js
    assert "function exportRoleReceipt" in js
    assert "/api/admin/roles/${encodeURIComponent(role.id)}/permission-receipt.json" in js
    assert '$("#exportRoleReceipt")?.addEventListener("click", () => exportRoleReceipt(activeRole()))' in js
    assert '$("#rolePresetSelect")?.addEventListener("change", renderRolePresetSummary)' in js
    assert '$("#applyRolePreset")?.addEventListener("click", applyRolePreset)' in js
    assert ".role-preset-panel" in css
    assert ".role-preset-summary" in css


def test_role_admin_distinguishes_menu_entry_and_action_permissions():
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert "function permissionMetaByCode" in js
    assert "function modulePermissionEntries" in js
    assert "module.permissionEntries" in js
    assert "function syncModuleBasePermissionFromMenu" in js
    assert "data-permission-kind" in js
    assert "permission-kind-page" in js
    assert "permission-kind-action" in js
    assert "permission-label" in js
    assert ".permission-module-header" in css
    assert ".permission-kind-action" in css


def test_role_admin_renders_long_menu_and_permission_lists_as_compact_chips():
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert "function renderCompactList" in js
    assert "ledger-chip-list" in js
    assert "ledger-chip-more" in js
    assert "renderCompactList(role.menuModules" in js
    assert "renderCompactList(role.permissions" in js
    assert "<td>${escapeHtml((role.menuModules || []).join" not in js
    assert ".ledger-chip-list" in css
    assert ".ledger-chip-more" in css


def test_role_admin_surfaces_module_api_scope_metadata():
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert "function moduleApiScopeText" in js
    assert "module.apiScopes" in js
    assert "module.dataDomain" in js
    assert "permission-module-scope" in js
    assert "data-domain:" in js
    assert "API:" in js
    assert ".permission-module-scope" in css


def test_quality_issue_ledgers_expose_status_filters_and_resolution_actions():
    imports_html = _read("admin-imports.html")
    imports_js = _read("admin-imports.js")
    imagery_html = _read("admin-imagery.html")
    imagery_js = _read("admin-imagery.js")

    assert 'id="qualityIssueStatusFilter"' in imports_html
    assert "<th>处理状态</th>" in imports_html
    assert "<th>操作</th>" in imports_html
    assert "function updateQualityIssueStatus" in imports_js
    assert 'data-quality-action="investigating"' in imports_js
    assert 'data-quality-action="resolved"' in imports_js
    assert 'data-quality-action="ignored"' in imports_js
    assert "/api/imports/forest-blocks/quality-issues/" in imports_js

    assert 'id="imageryIssueStatusFilter"' in imagery_html
    assert "<th>处理状态</th>" in imagery_html
    assert "<th>操作</th>" in imagery_html
    assert "function updateImageryIssueStatus" in imagery_js
    assert 'data-imagery-issue-action="investigating"' in imagery_js
    assert 'data-imagery-issue-action="resolved"' in imagery_js
    assert 'data-imagery-issue-action="ignored"' in imagery_js
    assert "/api/scenes/quality-issues/" in imagery_js


def test_import_admin_surfaces_operation_queue_for_delivery_workflow():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")
    css = _read("admin.css")

    assert 'id="importOperationQueueRows"' in html
    assert 'id="refreshImportOperationQueue"' in html
    assert "/api/imports/forest-blocks/operation-queue" in js
    assert "state.operationQueue" in js
    assert "function loadImportOperationQueue" in js
    assert "function renderImportOperationQueue" in js
    assert "data-operation-queue-key" in js
    assert 'data-operation-action="open"' in js
    assert "requiredPermission" in js
    assert "$(\"#refreshImportOperationQueue\")?.addEventListener(\"click\", loadImportOperationQueue)" in js
    assert ".operation-queue-grid" in css
    assert ".operation-queue-item" in css


def test_imagery_admin_surfaces_operation_queue_for_delivery_workflow():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")
    css = _read("admin.css")

    assert 'id="imageryOperationQueueRows"' in html
    assert 'id="refreshImageryOperationQueue"' in html
    assert "/api/scenes/operation-queue" in js
    assert "state.operationQueue" in js
    assert "function loadImageryOperationQueue" in js
    assert "function renderImageryOperationQueue" in js
    assert "function imageryOperationQueueItem" in js
    assert "data-imagery-operation-key" in js
    assert 'data-imagery-operation-action="open"' in js
    assert "requiredPermission" in js
    assert '$("#refreshImageryOperationQueue")?.addEventListener("click", loadImageryOperationQueue)' in js
    assert ".operation-queue-grid" in css
    assert ".operation-queue-item" in css


def test_role_admin_previews_effective_and_blocked_menu_modules():
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert "function selectedRoleDraft" in js
    assert "/api/admin/roles/preview" in js
    assert "function loadRoleDraftPreview" in js
    assert "state.rolePreview" in js
    assert "function roleDraftDiagnostics" in js
    assert "missingEntryPermission" in js
    assert "blockedMenuModules" in js
    assert "effectiveMenuModules" in js
    assert "preview-blocked" in js
    assert "preview-effective" in js
    assert "function roleMenuPreviewHtml" in js
    assert "roleDetailMenuDiagnostics" in js
    assert "role-detail-diagnostics-summary" in js
    assert ".preview-blocked" in css
    assert ".preview-effective" in css
    assert ".role-detail-diagnostics-summary" in css


def test_role_admin_previews_action_permission_coverage_and_orphans():
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert "actionPermissionCoverage" in js
    assert "orphanActionPermissions" in js
    assert "missingActionPermissions" in js
    assert "grantedActionPermissions" in js
    assert "function permissionPreviewGroup" in js
    assert "function actionCoveragePreviewGroup" in js
    assert "permission-coverage-item" in js
    assert "missingActionPermissions.map" in js
    assert "preview-action" in js
    assert "preview-orphan" in js
    assert ".preview-action" in css
    assert ".preview-orphan" in css
    assert ".permission-coverage-item" in css


def test_role_admin_preview_treats_manage_permissions_as_action_coverage():
    js = _read("admin-roles.js")

    assert "const MANAGE_PERMISSION_IMPLICATIONS" in js
    assert "function draftPermissionSatisfies" in js
    assert '"forest.blocks.manage"' in js
    assert '"imports.forestBlocks.review"' in js
    assert "draftPermissionSatisfies(permissions, module.permission)" in js
    assert "draftPermissionSatisfies(permissions, permission.code)" in js


def test_role_admin_previews_unknown_menu_modules_and_permissions():
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert "unknownMenuModules" in js
    assert "unknownPermissions" in js
    assert "preview-unknown" in js
    assert ".preview-unknown" in css


def test_role_admin_surfaces_draft_risk_summary_before_save():
    html = _read("admin-roles.html")
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert 'id="roleDraftSummary"' in html
    assert "function roleDraftSummary" in js
    assert "function draftRiskLevel" in js
    assert "function renderRoleDraftSummary" in js
    assert "saveRole.dataset.draftRisk" in js
    assert "renderRoleDraftSummary(diagnostics)" in js
    assert "summary.missingActionPermissions" in js
    assert "function roleDraftCanSave" in js
    assert "saveRole.disabled = !canSave" in js
    assert "role save blocked by draft risk" in js
    assert ".role-draft-summary" in css
    assert ".role-draft-summary[data-risk=\"error\"]" in css
    assert ".role-draft-summary[data-risk=\"warning\"]" in css


def test_role_admin_shows_permission_catalog_health_from_backend():
    html = _read("admin-roles.html")
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert 'id="permissionCatalogHealth"' in html
    assert 'id="permissionCatalogIssues"' in html
    assert 'id="refreshPermissionCatalogHealth"' in html
    assert 'id="exportPermissionCatalog"' in html
    assert 'data-permission="system.roles.export"' in html
    assert "state.catalog.coverage" in js
    assert "function renderPermissionCatalogHealth" in js
    assert "function exportPermissionCatalog" in js
    assert "/api/admin/permission-catalog.csv" in js
    assert "coverage.summary" in js
    assert "coverage.issues" in js
    assert "$(\"#refreshPermissionCatalogHealth\")?.addEventListener(\"click\", loadPermissionCatalog)" in js
    assert "$(\"#exportPermissionCatalog\")?.addEventListener(\"click\", exportPermissionCatalog)" in js
    assert ".permission-catalog-health" in css
    assert ".catalog-issue-list" in css


def test_role_admin_shows_permission_change_audit_events():
    html = _read("admin-roles.html")
    js = _read("admin-roles.js")

    assert "roleAuditEventList" in html
    assert "function renderRoleAuditEvents" in js
    assert "auditEvents" in js


def test_role_admin_has_cross_role_permission_event_ledger():
    html = _read("admin-roles.html")
    js = _read("admin-roles.js")

    assert 'id="roleEventActionFilter"' in html
    assert 'id="roleEventRoleFilter"' in html
    assert 'id="roleEventRows"' in html
    assert 'id="refreshRoleEvents"' in html
    assert 'id="exportRoleEvents"' in html
    assert 'data-permission="system.roles.export"' in html
    assert "/api/admin/roles/events" in js
    assert "/api/admin/roles/events.csv" in js
    assert "function roleEventQuery" in js
    assert "function loadRoleEvents" in js
    assert "function exportRoleEvents" in js
    assert "function renderRoleEventRows" in js
    assert "state.roleEvents" in js
    assert "event.roleCode" in js
    assert "event.changedFields" in js


def test_role_admin_detail_shows_assigned_user_accounts_and_deep_links():
    html = _read("admin-roles.html")
    js = _read("admin-roles.js")

    assert 'id="roleAssignedUsersList"' in html
    assert "关联账号" in html
    assert "assignedUsers" in js
    assert "function loadRoleAssignedUsers" in js
    assert "function renderRoleAssignedUsers" in js
    assert "/api/admin/users?" in js
    assert "role: role.roleCode || \"\"" in js
    assert "admin-users.html?role=" in js
    assert "admin-users.html?userId=" in js
    assert "loadRoleAssignedUsers(role)" in js


def test_user_admin_accepts_role_and_user_deep_links_from_role_detail():
    js = _read("admin-users.js")

    assert "new URLSearchParams(window.location.search)" in js
    assert "initialUserRole" in js
    assert "initialUserId" in js
    assert "function applyInitialUserQuery" in js
    assert '$("#userRoleFilter").value = initialUserRole' in js
    assert "function consumeInitialUserSelection" in js
    assert "consumeInitialUserSelection()" in js


def test_import_batch_detail_shows_delivery_package_trace():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="importBatchDeliveryPackageList"' in html
    assert "交付包追溯" in html
    assert "function importBatchDeliveryPackage" in js
    assert "function renderImportBatchDeliveryPackage" in js
    assert "#importBatchDeliveryPackageList" in js
    assert "state.deliveryPackages.find" in js
    assert "displayLabel(DELIVERY_PACKAGE_STATUS_LABELS" in js
    assert "deliveryPackageStatusClass(packageItem.packageStatus)" in js
    assert "renderImportBatchDeliveryPackage(batch)" in js


def test_role_admin_row_actions_can_export_permission_receipt():
    js = _read("admin-roles.js")

    assert "function roleActionButtons" in js
    assert 'data-role-action="receipt"' in js
    assert 'data-permission="${ROLE_EVENT_EXPORT_PERMISSION}"' in js
    assert "exportRoleReceipt(role)" in js
    assert 'roleButton.dataset.roleAction === "receipt"' in js
    assert "event.stopPropagation()" in js


def test_role_admin_renders_status_and_event_actions_as_chinese_labels():
    js = _read("admin-roles.js")

    assert "const ROLE_STATUS_LABELS" in js
    assert "const ROLE_EVENT_ACTION_LABELS" in js
    assert "function roleStatusLabel" in js
    assert "function roleEventActionLabel" in js
    assert "roleStatusLabel(role.status)" in js
    assert "roleEventActionLabel(event.action)" in js


def test_user_account_admin_has_independent_ledger_and_role_assignment_controls():
    html = _read("admin-users.html")
    js = _read("admin-users.js")
    roles_html = _read("admin-roles.html")

    assert 'data-admin-module="users"' in html
    assert 'data-permission="system.users.view"' in html
    assert 'id="userRows"' in html
    assert 'id="userForm"' in html
    assert 'id="userDetailPanel"' in html
    assert 'id="assignedRoles"' in html
    assert 'id="roleOptions"' in html
    assert 'id="includeDeletedUsers" type="checkbox" data-permission="system.users.restore"' in html
    assert 'href="admin-users.html"' in _read("admin.html")
    assert 'id="userRows"' not in roles_html
    assert "/api/admin/users" in js
    assert "function renderRows" in js
    assert "function renderDetail" in js
    assert "function openUserEditor" in js
    assert "function restoreUser" in js
    assert 'data-row-action="view"' in js
    assert "rowActionButtons" in js
    assert 'data-user-action="restore" data-permission="${USER_RESTORE_PERMISSION}"' in js
    assert "system.users.update" in js


def test_user_account_editor_renders_role_checklist_from_role_catalog():
    html = _read("admin-users.html")
    js = _read("admin-users.js")

    assert 'id="userRoleChecklist"' in html
    assert 'data-role-selection="userRoles"' in html
    assert "function renderUserRoleChecklist" in js
    assert "function syncUserRoleSelectionsFromField" in js
    assert "function syncAssignedRolesFromChecklist" in js
    assert "data-user-role-option" in js
    assert "role.roleCode" in js
    assert "renderUserRoleChecklist();" in js
    assert '$("#userRoleChecklist")?.addEventListener("change", syncAssignedRolesFromChecklist)' in js
    assert '$("#assignedRoles")?.addEventListener("input", syncUserRoleSelectionsFromField)' in js


def test_user_account_admin_has_cross_user_event_ledger():
    html = _read("admin-users.html")
    js = _read("admin-users.js")

    assert 'id="userEventActionFilter"' in html
    assert 'id="userEventUserFilter"' in html
    assert 'id="userEventRows"' in html
    assert 'id="refreshUserEvents"' in html
    assert 'id="exportUserEvents"' in html
    assert 'data-permission="system.users.export"' in html
    assert "/api/admin/users/events" in js
    assert "/api/admin/users/events.csv" in js
    assert "function userEventQuery" in js
    assert "function loadUserEvents" in js
    assert "function exportUserEvents" in js
    assert "function renderUserEventRows" in js
    assert "state.userEvents" in js
    assert "event.username" in js
    assert "event.changedFields" in js
    assert "No user account events" not in js
    assert "暂无账号权限变更记录" in js


def test_user_account_admin_previews_effective_permissions_and_menu_modules():
    html = _read("admin-users.html")
    js = _read("admin-users.js")
    css = _read("admin.css")

    assert 'id="userEffectivePermissionPreview"' in html
    assert 'id="userPermissionReceipt"' in html
    assert 'id="userDraftPermissionPreview"' in html
    assert 'id="userDraftPermissionReceipt"' in html
    assert 'id="refreshUserDraftPermissionPreview"' in html
    assert 'id="exportUserAccessReceipt"' in html
    assert 'data-permission="system.users.export"' in html
    assert 'id="userDataScopeTowns"' in html
    assert 'id="userDataScopeVillages"' in html
    assert 'id="userDataScopeBlockCodes"' in html
    assert "/api/admin/users/effective-permissions/preview" in js
    assert "/api/admin/users/" in js
    assert "/effective-permissions" in js
    assert "userEffectivePermissions" in js
    assert "userDraftEffectivePermissions" in js
    assert "function loadUserEffectivePermissions" in js
    assert "function loadUserDraftEffectivePermissions" in js
    assert "function renderUserEffectivePermissionPreview" in js
    assert "function renderUserPermissionReceipt" in js
    assert "function exportUserAccessReceipt" in js
    assert "/api/admin/users/${encodeURIComponent(user.id)}/access-receipt.json" in js
    assert '$("#exportUserAccessReceipt")?.addEventListener("click", () => exportUserAccessReceipt(activeUser()))' in js
    assert "userPermissionReceipt" in js
    assert "userDraftPermissionReceipt" in js
    assert "permission-receipt" in js
    assert "payload.visibleMenuModules" in js
    assert "payload.blockedMenuModules" in js
    assert "payload.permissions" in js
    assert "payload.dataScopes" in js
    assert "visibleMenuModules" in js
    assert "blockedMenuModules" in js
    assert "configuredMenuModules" in js
    assert "unknownRoles" in js
    assert "preview-unknown" in js
    assert "dataScopes" in js
    assert "userDataScopeTowns" in js
    assert "userDataScopeVillages" in js
    assert "userDataScopeBlockCodes" in js
    assert "scopes.towns" in js
    assert "scopes.villages" in js
    assert "scopes.blockCodes" in js
    assert ".permission-receipt" in css
    assert ".permission-receipt-grid" in css


def test_user_account_detail_renders_access_receipt_summary_cards():
    html = _read("admin-users.html")
    js = _read("admin-users.js")
    css = _read("admin.css")

    assert 'id="userAccessReceiptSummary"' in html
    assert "function userAccessReceiptSummaryItems" in js
    assert "function renderUserAccessReceiptSummary" in js
    assert "renderUserAccessReceiptSummary(user, payload)" in js
    assert "effectivePermissionCount" in js
    assert "visibleMenuCount" in js
    assert "blockedMenuCount" in js
    assert "dataScopeValueCount" in js
    assert "auditEventCount" in js
    assert "exportUserAccessReceipt(user)" in js
    assert 'data-receipt-action="user-access"' in js
    assert 'data-permission="${USER_EVENT_EXPORT_PERMISSION}"' in js
    assert ".receipt-summary-grid" in css
    assert ".receipt-summary-card" in css
    assert ".receipt-summary-command" in css


def test_user_account_admin_renders_module_permission_coverage_matrix():
    html = _read("admin-users.html")
    js = _read("admin-users.js")
    css = _read("admin.css")

    assert 'id="userEffectivePermissionCoverage"' in html
    assert 'id="userDraftPermissionCoverage"' in html
    assert "function userPermissionCoverageItems" in js
    assert "function renderUserPermissionCoverage" in js
    assert "renderUserPermissionCoverage(payload, \"#userEffectivePermissionCoverage\")" in js
    assert "renderUserPermissionCoverage(payload, \"#userDraftPermissionCoverage\")" in js
    assert "visibleMenuModules.map" in js
    assert "blockedMenuModules.map" in js
    assert "missingEntryPermission" in js
    assert "entryPermission" in js
    assert "permission-coverage-list" in js
    assert "permission-coverage-item" in js
    assert "permission-coverage-state-blocked" in js
    assert ".permission-coverage-list" in css
    assert ".permission-coverage-state-blocked" in css


def test_user_account_admin_refreshes_effective_menu_after_user_mutations():
    common_js = _read("admin-common.js")
    users_js = _read("admin-users.js")

    assert "refreshRoleMenu: refreshSession" in common_js
    assert "refreshRoleMenu" in users_js
    assert users_js.count("await refreshRoleMenu();") >= 3


def test_role_admin_can_show_deleted_roles_and_restore_them():
    html = _read("admin-roles.html")
    js = _read("admin-roles.js")

    assert 'id="includeDeletedRoles" type="checkbox" data-permission="system.roles.restore"' in html
    assert "includeDeleted" in js
    assert "/restore" in js
    assert "function restoreRole" in js
    assert "function isDeletedRole" in js
    assert 'data-role-action="restore"' in js
    assert "data-permission=\"${PAGE_PERMISSION}\"" in js
    assert "changedFields" in js


def test_role_admin_refreshes_effective_menu_after_role_mutations():
    common_js = _read("admin-common.js")
    roles_js = _read("admin-roles.js")

    assert "refreshRoleMenu: refreshSession" in common_js
    assert "refreshRoleMenu" in roles_js
    assert roles_js.count("await refreshRoleMenu();") >= 3


def test_role_admin_filters_permission_matrix_live_without_removing_checked_values():
    js = _read("admin-roles.js")

    assert "function applyCatalogChecklistFilters" in js
    assert "#menuModuleChecklist .check-item" in js
    assert "#permissionChecklist .permission-module" in js
    assert "nodeMatchesFilterText" in js
    assert "item.hidden" in js
    assert "module.hidden" in js
    assert '$(selector).addEventListener("input"' in js
    assert "applyCatalogChecklistFilters();" in js
    assert "collectCheckedValues" in js


def test_role_admin_supports_module_level_permission_bulk_selection():
    js = _read("admin-roles.js")
    css = _read("admin.css")

    assert 'data-module-permission-action="select-module"' in js
    assert 'data-module-permission-action="clear-module"' in js
    assert "function handleModulePermissionBulkAction" in js
    assert "function setModulePermissionSelection" in js
    assert "function controlledSelectionValues" in js
    assert "function uncontrolledSelectionValues" in js
    assert 'mergeDraftValues(uncontrolledSelectionValues("permissions"' in js
    assert '$("#permissionChecklist").addEventListener("click"' in js
    assert ".permission-module-actions" in css


def test_role_admin_renders_permission_specific_api_scopes():
    js = _read("admin-roles.js")

    assert "function permissionApiScopeText" in js
    assert "permission.apiScopes" in js
    assert "permission-action-scope" in js
    assert "API: ${scopes.join" in js


def test_import_admin_has_batch_ledger_detail_and_row_actions():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert "ledger-workbench-full" in html
    assert "ledger-table-full" in html
    assert 'id="importBatchRows"' in html
    assert 'id="importBatchDetailPanel"' in html
    assert 'id="downloadImportBatchErrors"' in html
    assert 'id="downloadImportBatchReport"' in html
    assert 'id="rollbackImportBatch"' in html
    assert 'id="includeDeletedImportBatches"' in html
    assert 'id="importedBlocksList"' in html
    assert 'id="importedRightsList"' in html
    assert 'id="closeImportBatchDetail"' in html
    assert 'class="crud-modal detail-modal hidden"' in html
    assert "/api/imports/forest-blocks/batches" in js
    assert "/targets?" in js
    assert "function loadImportBatchTargets" in js
    assert "/errors.csv" in js
    assert "/report.json" in js
    assert "/rollback" in js
    assert "/restore" in js
    assert "includeDeleted" in js
    assert "function loadImportBatches" in js
    assert "function renderImportBatchRows" in js
    assert "function renderImportBatchDetail" in js
    assert "function deleteImportBatch" in js
    assert "function restoreImportBatch" in js
    assert 'data-batch-action="restore"' in js
    assert "function rollbackImportBatch" in js
    assert "function downloadImportBatchErrors" in js
    assert "function downloadImportBatchReport" in js
    assert "function renderImportTraceList" in js
    assert "importedBlocks" in js
    assert "kind=rights" in js
    assert "function handleBatchRowAction" in js
    assert 'data-row-action="view"' in js
    assert 'data-row-action="edit"' in js
    assert 'data-row-action="delete"' in js
    assert "button.dataset.rowAction" in js
    assert 'action === "delete"' in js


def test_import_batch_row_actions_can_export_report_receipt_and_rollback():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")
    css = _read("admin.css")

    assert "import-batch-table-wrap" in html
    assert "function batchActionButtons" in js
    assert 'data-batch-action="report"' in js
    assert 'data-batch-action="receipt"' in js
    assert 'data-batch-action="rollback"' in js
    assert 'data-permission="${IMPORT_EXPORT_PERMISSION}"' in js
    assert 'data-permission="${IMPORT_ROLLBACK_PERMISSION}"' in js
    assert 'batchButton.dataset.batchAction === "report"' in js
    assert "downloadImportBatchReport(batch)" in js
    assert 'batchButton.dataset.batchAction === "receipt"' in js
    assert "exportImportBatchReceipt(batch)" in js
    assert 'batchButton.dataset.batchAction === "rollback"' in js
    assert "rollbackImportBatch(batch)" in js
    assert "event.preventDefault()" in js
    assert "row-actions-extra-wide" in js
    assert ".import-batch-table-wrap" in css


def test_import_batch_process_row_action_is_permission_scoped():
    js = _read("admin-imports.js")

    assert 'data-row-action="edit" data-permission-any="${IMPORT_REVIEW_PERMISSION} ${IMPORT_ACCEPTANCE_PERMISSION} ${IMPORT_SCENE_LAYER_LINK_PERMISSION}" aria-label="处理批次" title="处理批次"' in js
    assert 'data-row-action="edit" aria-label="查看报告" title="查看报告"' not in js


def test_import_batch_direct_downloads_use_shared_download_helper():
    js = _read("admin-imports.js")

    errors_block = js[
        js.index("async function downloadImportBatchErrors"):
        js.index("async function downloadImportBatchReport")
    ]
    report_block = js[
        js.index("async function downloadImportBatchReport"):
        js.index("async function checkImportBatchPublishReadiness")
    ]
    assert "await downloadFile(" in errors_block
    assert "await downloadFile(" in report_block
    assert "AdminCommon.apiBase()" not in errors_block
    assert "AdminCommon.apiBase()" not in report_block


def test_import_admin_can_link_batch_to_imagery_layer_trace():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="batchSceneIdFilter"' in html
    assert 'id="batchSceneId"' in html
    assert 'list="batchSceneOptions"' in html
    assert 'id="batchSceneOptions"' in html
    assert 'id="batchSceneKeyword"' in html
    assert 'id="refreshBatchScenes"' in html
    assert 'id="batchScenePreview"' in html
    assert 'id="linkImportBatchSceneLayer"' in html
    assert 'id="importBatchOperationResult"' in html
    assert 'id="importBatchImageryLinksList"' in html
    assert 'id="importBatchCoverageCheck"' in html
    assert "/api/scenes?" in js
    assert "/link-scene-layer" in js
    assert "sceneId: $(\"#batchSceneIdFilter\")" in js
    assert "coverageCheck" in js
    assert "function loadBatchScenes" in js
    assert "payload.scenes" in js
    assert "function renderBatchSceneOptions" in js
    assert "function renderBatchScenePreview" in js
    assert "function linkImportBatchSceneLayer" in js
    assert "function renderImportBatchOperationResult" in js
    assert "importBatchOperationResult" in js
    assert "operation-result" in js
    assert "payload.layer" in js
    assert "dashboardHref" in js
    assert "sourceLinks" in js
    assert "function renderImportBatchImageryLinks" in js
    assert "function renderImportBatchCoverageCheck" in js
    assert "imageryLinks" in js
    assert "#batchSceneIdFilter" in js
    assert 'data-permission="imports.sceneLayers.link"' in html
    assert "IMPORT_SCENE_LAYER_LINK_PERMISSION" in js


def test_import_batch_detail_links_imported_blocks_and_rights_back_to_ledgers():
    imports_js = _read("admin-imports.js")
    blocks_js = _read("admin-blocks.js")
    rights_js = _read("admin-rights.js")

    assert "admin-blocks.html?blockCode=" in imports_js
    assert "admin-rights.html?archiveCode=" in imports_js
    assert 'new URLSearchParams(window.location.search).get("blockCode")' in blocks_js
    assert 'new URLSearchParams(window.location.search).get("archiveCode")' in rights_js
    assert 'if (initialBlockCode && $("#keyword")) $("#keyword").value = initialBlockCode;' in blocks_js
    assert 'if (initialArchiveCode && $("#rightKeyword")) $("#rightKeyword").value = initialArchiveCode;' in rights_js


def test_import_admin_supports_quality_issue_deep_links():
    js = _read("admin-imports.js")

    assert "let initialQualityIssueId" in js
    assert 'new URLSearchParams(window.location.search).get("qualityIssueId")' in js
    assert "function consumeInitialQualityIssueSelection" in js
    assert "state.activeQualityIssueId" in js
    assert 'data-issue-id="${escapeHtml(issue.issueId || "")}"' in js
    assert "initialQualityIssueId = \"\"" in js


def test_imagery_admin_supports_imagery_issue_deep_links():
    js = _read("admin-imagery.js")

    assert "let initialImageryIssueId" in js
    assert 'new URLSearchParams(window.location.search).get("imageryIssueId")' in js
    assert "function consumeInitialImageryIssueSelection" in js
    assert "state.activeImageryIssueId" in js
    assert 'data-issue-id="${escapeHtml(issue.issueId || "")}"' in js
    assert "initialImageryIssueId = \"\"" in js


def test_import_admin_shows_publish_readiness_preflight_before_scene_layer_link():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="checkImportBatchPublishReadiness"' in html
    assert 'id="importBatchPublishReadiness"' in html
    assert "/publish-readiness" in js
    assert "function renderImportBatchPublishReadiness" in js
    assert "function checkImportBatchPublishReadiness" in js
    assert "blockingReasons" in js
    assert "linkedBlockCount" in js
    assert "publishLayer: true" in js
    assert 'data-permission="imports.sceneLayers.link"' in html
    assert "checkImportBatchPublishReadiness(activeBatch())" in js


def test_import_and_imagery_admin_show_workflow_summary_from_backend():
    imports_html = _read("admin-imports.html")
    imports_js = _read("admin-imports.js")
    imagery_html = _read("admin-imagery.html")
    imagery_js = _read("admin-imagery.js")
    css = _read("admin.css")

    assert 'id="importWorkflowSummary"' in imports_html
    assert 'id="exportImportWorkflowSummary"' in imports_html
    assert 'data-permission="imports.forestBlocks.export"' in imports_html
    assert "/api/imports/forest-blocks/workflow-summary" in imports_js
    assert "/api/imports/forest-blocks/workflow-summary.json" in imports_js
    assert "state.workflowSummary" in imports_js
    assert "function loadImportWorkflowSummary" in imports_js
    assert "function renderImportWorkflowSummary" in imports_js
    assert "function exportImportWorkflowSummary" in imports_js
    assert '$("#exportImportWorkflowSummary")?.addEventListener("click", exportImportWorkflowSummary)' in imports_js
    assert 'id="downloadImportBatchReceipt"' in imports_html
    assert 'id="importBatchAcceptanceStatus"' in imports_html
    assert 'id="importBatchAcceptanceComment"' in imports_html
    assert 'id="updateImportBatchAcceptance"' in imports_html
    assert 'id="batchAcceptanceStatusFilter"' in imports_html
    assert 'data-permission="imports.forestBlocks.acceptance"' in imports_html
    assert "function exportImportBatchReceipt" in imports_js
    assert "function updateImportBatchAcceptance" in imports_js
    assert "function renderImportBatchAcceptanceEvents" in imports_js
    assert 'acceptanceStatus: $("#batchAcceptanceStatusFilter")?.value.trim() || ""' in imports_js
    assert "#batchAcceptanceStatusFilter" in imports_js
    assert "displayLabel(ACCEPTANCE_STATUS_LABELS, batch.acceptanceStatus" in imports_js
    assert "/api/imports/${encodeURIComponent(batch.id)}/acceptance-receipt.json" in imports_js
    assert "/api/imports/${encodeURIComponent(batch.id)}/acceptance" in imports_js
    assert (
        '$("#downloadImportBatchReceipt")?.addEventListener("click", () => exportImportBatchReceipt(activeBatch()))'
        in imports_js
    )
    assert '$("#updateImportBatchAcceptance")?.addEventListener("click", () => updateImportBatchAcceptance(activeBatch()))' in imports_js
    assert "renderWorkflowSummaryCards" in imports_js
    assert "loadImportWorkflowSummary();" in imports_js
    assert 'id="batchWorkflowQueueFilter"' in imports_html
    assert 'new URLSearchParams(window.location.search).get("workflowQueue")' in imports_js
    assert 'new URLSearchParams(window.location.search).get("qualityIssueStatus")' in imports_js
    assert "batchWorkflowQueueFilter" in imports_js
    assert "qualityIssueStatusFilter" in imports_js

    assert 'id="imageryWorkflowSummary"' in imagery_html
    assert 'id="exportImageryWorkflowSummary"' in imagery_html
    assert 'data-permission="imagery.scenes.export"' in imagery_html
    assert "/api/scenes/workflow-summary" in imagery_js
    assert "/api/scenes/workflow-summary.json" in imagery_js
    assert "state.workflowSummary" in imagery_js
    assert "function loadImageryWorkflowSummary" in imagery_js
    assert "function renderImageryWorkflowSummary" in imagery_js
    assert "function exportImageryWorkflowSummary" in imagery_js
    assert '$("#exportImageryWorkflowSummary")?.addEventListener("click", exportImageryWorkflowSummary)' in imagery_js
    assert 'id="exportSceneDeliveryReceipt"' in imagery_html
    assert 'id="sceneDeliveryStatus"' in imagery_html
    assert 'id="sceneDeliveryComment"' in imagery_html
    assert 'id="updateSceneDelivery"' in imagery_html
    assert 'id="sceneDeliveryStatusFilter"' in imagery_html
    assert 'data-permission="imagery.scenes.delivery"' in imagery_html
    assert "function exportSceneDeliveryReceipt" in imagery_js
    assert "function updateSceneDelivery" in imagery_js
    assert "function renderSceneDeliveryEvents" in imagery_js
    assert 'deliveryStatus: $("#sceneDeliveryStatusFilter")?.value.trim() || ""' in imagery_js
    assert "#sceneDeliveryStatusFilter" in imagery_js
    assert "displayLabel(DELIVERY_STATUS_LABELS, scene.deliveryStatus" in imagery_js
    assert "/api/scenes/${encodeURIComponent(scene.id)}/delivery" in imagery_js
    assert '$("#updateSceneDelivery")?.addEventListener("click", () => updateSceneDelivery(activeScene()))' in imagery_js
    assert "/api/scenes/${encodeURIComponent(scene.id)}/delivery-receipt.json" in imagery_js
    assert '$("#exportSceneDeliveryReceipt")?.addEventListener("click", () => exportSceneDeliveryReceipt(activeScene()))' in imagery_js
    assert "renderWorkflowSummaryCards" in imagery_js
    assert "loadImageryWorkflowSummary();" in imagery_js
    assert 'id="scenePublishedFilter"' in imagery_html
    assert 'id="taskStatusFilter"' in imagery_html
    assert 'new URLSearchParams(window.location.search).get("published")' in imagery_js
    assert 'new URLSearchParams(window.location.search).get("taskStatus")' in imagery_js
    assert 'new URLSearchParams(window.location.search).get("imageryIssueStatus")' in imagery_js
    assert "scenePublishedFilter" in imagery_js
    assert "taskStatusFilter" in imagery_js
    assert "imageryIssueStatusFilter" in imagery_js

    assert ".workflow-summary-grid" in css
    assert ".workflow-summary-card" in css


def test_import_and_imagery_workflows_translate_internal_keys_for_operators():
    imports_js = _read("admin-imports.js")
    imagery_js = _read("admin-imagery.js")

    assert "WORKFLOW_SUMMARY_KEY_LABELS" in imports_js
    assert "operationQueueStatusLabel(lane.key)" in imports_js
    assert '<small>${escapeHtml(workflowSummaryKeyLabel(card.key))}</small>' in imports_js
    assert '<small>${escapeHtml(card.key || "")}</small>' not in imports_js
    assert '${escapeHtml(lane.key || "-")}</span>' not in imports_js

    assert "WORKFLOW_SUMMARY_KEY_LABELS" in imagery_js
    assert "IMAGERY_OPERATION_QUEUE_LABELS" in imagery_js
    assert "imageryOperationQueueLabel(lane.key)" in imagery_js
    assert '<small>${escapeHtml(workflowSummaryKeyLabel(card.key))}</small>' in imagery_js
    assert '<small>${escapeHtml(card.key || "")}</small>' not in imagery_js
    assert '${escapeHtml(lane.key || "-")}</span>' not in imagery_js


def test_admin_homepage_aggregates_import_and_imagery_workflow_summaries():
    html = _read("admin.html")
    js = _read("admin-dashboard.js")

    assert 'id="adminWorkflowSummary"' in html
    assert 'id="refreshAdminWorkflowSummary"' in html
    assert "admin-imports.html" in html
    assert "admin-imagery.html" in html

    assert "/api/imports/forest-blocks/workflow-summary" in js
    assert "/api/scenes/workflow-summary" in js
    assert "function loadAdminWorkflowSummary" in js
    assert "function renderAdminWorkflowSummary" in js
    assert "renderWorkflowSummaryCards" in js
    assert "loadAdminWorkflowSummary();" in js
    assert "admin-imports.html" in js
    assert "admin-imagery.html" in js


def test_admin_homepage_work_queue_includes_delivery_and_permission_closure():
    html = _read("admin.html")
    js = _read("admin-dashboard.js")

    assert "数据与权限工作队列" in html
    assert 'id="metricOperationQueue"' in html
    assert "/api/imports/forest-blocks/operation-queue?limit=3" in js
    assert "/api/scenes/operation-queue?limit=3" in js
    assert "/api/map-layers/dashboard" in js
    assert "/api/admin/permission-catalog" in js
    assert "/api/admin/roles/operation-queue?limit=3" in js
    assert "/api/admin/users/operation-queue?limit=3" in js
    assert "/api/admin/roles?limit=1000" in js
    assert "function operationQueueRows" in js
    assert "function imageryOperationQueueRows" in js
    assert "function imageryOperationQueueSummaryTotal" in js
    assert "function roleOperationQueueRows" in js
    assert "function roleOperationQueueSummaryTotal" in js
    assert "function userOperationQueueRows" in js
    assert "function userOperationQueueSummaryTotal" in js
    assert "function mapLayerPublicationRows" in js
    assert "function mapLayerPublicationQueueTotal" in js
    assert "payload?.summary?.operationQueueTotal" in js
    assert "payload?.publicationSummary?.publicationQueueTotal" in js
    assert "state.roleOperationQueue = await loadQueuePayload(\"/api/admin/roles/operation-queue?limit=3\")" in js
    assert "state.userOperationQueue = await loadQueuePayload(\"/api/admin/users/operation-queue?limit=3\")" in js
    assert "roleOperationQueueSummaryTotal(state.roleOperationQueue)" in js
    assert "userOperationQueueSummaryTotal(state.userOperationQueue)" in js
    assert "roleOperationQueueRows(state.roleOperationQueue || { items: [] })" in js
    assert "userOperationQueueRows(state.userOperationQueue || { items: [] })" in js
    assert '$("#metricOperationQueue").textContent = String(operationQueueTotal);' in js
    assert "function loadPermissionQueue" in js
    assert "function roleCoverageQueueItems" in js
    assert "权限配置" in js
    assert "账号配置" in js
    assert "admin-roles.html" in js
    assert "admin-users.html" in js


def test_admin_homepage_work_queue_includes_permission_closure_guides():
    js = _read("admin-dashboard.js")

    assert "function permissionClosureQueueItems" in js
    assert "catalogPayload?.permissionClosures" in js
    assert "roleCoversPermissionClosure" in js
    assert "closure.menuModules" in js
    assert "closure.permissions" in js
    assert "闭环权限包" in js
    assert "admin-roles.html#roleClosureGuides" in js
    assert "permissionClosureQueueItems(rolesPayload || { items: [] }, catalogPayload" in js


def test_admin_homepage_surfaces_identity_access_metrics():
    html = _read("admin.html")
    js = _read("admin-dashboard.js")

    assert 'id="metricRoles"' in html
    assert 'id="metricUsers"' in html
    assert "角色配置" in html
    assert "后台账号" in html
    assert 'loadMetricTotal("/api/admin/roles?limit=1")' in js
    assert 'loadMetricTotal("/api/admin/users?limit=1")' in js
    assert '$("#metricRoles").textContent = String(roles);' in js
    assert '$("#metricUsers").textContent = String(users);' in js


def test_import_admin_shows_delivery_package_ledger_from_backend():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="deliveryPackageRows"' in html
    assert 'id="refreshDeliveryPackages"' in html
    assert 'id="exportDeliveryPackages"' in html
    assert 'id="exportDeliveryPackagesJson"' in html
    assert 'data-permission="imports.forestBlocks.export"' in html
    assert 'id="deliveryPackageKeyword"' in html
    assert 'id="deliveryPackageStatusFilter"' in html
    assert 'id="deliveryPackageAcceptanceFilter"' in html
    assert 'id="deliveryPackageDeliveryFilter"' in html
    assert 'id="deliveryPackageBlockFilter"' in html
    assert "/api/imports/forest-blocks/delivery-packages" in js
    assert "/api/imports/forest-blocks/delivery-packages.csv" in js
    assert "/api/imports/forest-blocks/delivery-packages.json" in js
    assert "deliveryPackages" in js
    assert "function deliveryPackageQuery" in js
    assert "function loadDeliveryPackages" in js
    assert "function renderDeliveryPackageRows" in js
    assert "function deliveryPackageActionButtons" in js
    assert "function exportDeliveryPackageAcceptanceReceipt" in js
    assert "function exportDeliveryPackageSceneReceipt" in js
    assert "function exportDeliveryPackageReceipt" in js
    assert "function exportDeliveryPackagesJson" in js
    assert "function handleDeliveryPackageAction" in js
    assert "function exportDeliveryPackages" in js
    assert 'data-delivery-action="delivery-package-receipt"' in js
    assert 'data-delivery-action="acceptance-receipt"' in js
    assert 'data-delivery-action="scene-delivery-receipt"' in js
    assert "/api/imports/${encodeURIComponent(batchId)}/delivery-package-receipt.json" in js
    assert 'data-permission="${IMPORT_EXPORT_PERMISSION}"' in js
    assert "item.acceptanceReceiptUrl" in js
    assert "item.primarySceneId" in js
    assert "item.primarySceneDeliveryReceiptUrl" in js
    assert "event.stopPropagation()" in js
    assert "if (handleDeliveryPackageAction(event)) return;" in js
    assert "packageStatus" in js
    assert "blockingReasons" in js
    assert "linkedSceneCount" in js
    assert "deliveredSceneCount" in js
    assert "publishedLayerCount" in js
    assert '$("#exportDeliveryPackages")?.addEventListener("click", exportDeliveryPackages)' in js
    assert '$("#exportDeliveryPackagesJson")?.addEventListener("click", exportDeliveryPackagesJson)' in js
    assert "loadDeliveryPackages();" in js


def test_import_admin_delivery_packages_have_own_detail_drawer():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="deliveryPackageDetailPanel"' in html
    assert 'id="deliveryPackageDetailTitle"' in html
    assert 'id="deliveryPackageDetailGrid"' in html
    assert 'id="deliveryPackageSceneList"' in html
    assert 'id="deliveryPackageBlockingList"' in html
    assert 'id="closeDeliveryPackageDetail"' in html
    assert "activeDeliveryBatchId" in js
    assert 'data-delivery-action="view"' in js
    assert "function activeDeliveryPackage" in js
    assert "function renderDeliveryPackageDetail" in js
    assert "function closeDeliveryPackageDetail" in js
    assert "renderDeliveryPackageDetail(item)" in js
    assert "deliveryPackageSceneList" in js
    assert "deliveryPackageBlockingList" in js
    assert "admin-imagery.html?sceneId=" in js
    assert "admin-map-layers.html?layerCode=" in js
    assert "admin-imports.html?batchId=" in js
    assert '$("#closeDeliveryPackageDetail")?.addEventListener("click", closeDeliveryPackageDetail)' in js


def test_delivery_package_detail_renders_closure_summary_cards():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")
    css = _read("admin.css")

    assert 'id="deliveryPackageClosureSummary"' in html
    assert "function deliveryPackageClosureSummaryItems" in js
    assert "function renderDeliveryPackageClosureSummary" in js
    assert "renderDeliveryPackageClosureSummary(item)" in js
    assert "deliveryPackageSceneProgress" in js
    assert "publishedLayerProgress" in js
    assert "blockingReasonCount" in js
    assert "deliveryPackageReceiptCount" in js
    assert 'data-delivery-action="acceptance-receipt"' in js
    assert 'data-delivery-action="scene-delivery-receipt"' in js
    assert ".receipt-summary-grid" in css
    assert ".receipt-summary-card" in css
    assert ".receipt-summary-command" in css


def test_delivery_package_detail_uses_authorized_receipt_exports_and_layer_links():
    js = _read("admin-imports.js")

    assert "function deliveryPackageReceiptButton" in js
    assert "renderDeliveryPackageReceipts(item)" in js
    assert 'data-delivery-action="${action}"' in js
    assert 'data-permission="${IMPORT_EXPORT_PERMISSION}"' in js
    assert 'button.closest("[data-batch-id]")' in js
    assert "candidateBatchId" in js
    assert "exportDeliveryPackageAcceptanceReceipt(item)" in js
    assert "exportDeliveryPackageSceneReceipt(item" in js
    assert "exportDeliveryPackageReceipt(item)" in js
    assert "item.publishedLayerRecordCodes" in js
    assert "admin-map-layers.html?layerCode=" in js
    assert '$("#deliveryPackageReceiptList")?.addEventListener("click", handleDeliveryPackageAction)' in js


def test_delivery_package_scene_receipt_export_uses_clicked_scene_receipt_url():
    js = _read("admin-imports.js")

    assert "function deliveryPackageSceneReceiptUrl(item, sceneId" in js
    assert "item?.sceneDeliveryReceiptUrls || []" in js
    assert 'String(receipt?.sceneId || "") === String(sceneId || "")' in js
    assert "matchedReceipt?.url || matchedReceipt?.href || matchedReceipt?.receiptUrl" in js
    assert "deliveryPackageSceneReceiptUrl(item, sceneId)" in js


def test_import_admin_batch_deep_link_opens_delivery_package_detail():
    js = _read("admin-imports.js")

    assert "let initialDeliveryBatchId = initialBatchId;" in js
    assert 'if (initialBatchId && $("#deliveryPackageKeyword")) $("#deliveryPackageKeyword").value = initialBatchId;' in js
    assert "function consumeInitialDeliveryPackageSelection" in js
    assert "state.activeDeliveryBatchId = matched.batchId || targetId;" in js
    assert "initialDeliveryBatchId = \"\";" in js
    assert "consumeInitialDeliveryPackageSelection();" in js
    assert "renderDeliveryPackageDetail(activeDeliveryPackage());" in js


def test_common_permission_implications_include_import_acceptance_and_imagery_delivery():
    js = _read("admin-common.js")

    assert '"imports.forestBlocks.acceptance"' in js
    assert '"imagery.scenes.delivery"' in js


def test_import_admin_can_review_batches_and_show_audit_events():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="batchReviewStatusFilter"' in html
    assert 'id="importBatchReviewDecision"' in html
    assert 'id="importBatchReviewComment"' in html
    assert 'id="reviewImportBatch"' in html
    assert 'id="importBatchReviewEventsList"' in html
    assert "/review" in js
    assert "function reviewImportBatch" in js


def test_import_admin_status_deleted_filter_includes_deleted_batches():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="batchStatusFilter"' in html
    assert 'id="includeDeletedImportBatches"' in html
    assert 'placeholder="完成、删除、回滚"' in html
    assert 'const batchStatus = $("#batchStatusFilter")?.value.trim() || ""' in js
    assert 'includeDeleted: $("#includeDeletedImportBatches")?.checked || batchStatus === "deleted" ? "true" : ""' in js
    assert "function renderImportBatchReviewEvents" in js
    assert "reviewEvents" in js
    assert "reviewStatus" in js


def test_sensitive_deleted_record_toggles_declare_restore_permissions():
    imports_html = _read("admin-imports.html")
    imports_js = _read("admin-imports.js")
    imagery_html = _read("admin-imagery.html")
    layers_html = _read("admin-map-layers.html")

    assert 'id="includeDeletedImportBatches" type="checkbox" data-permission="imports.forestBlocks.restore"' in imports_html
    assert 'id="includeDeletedImportAuditEvents" type="checkbox" data-permission="imports.forestBlocks.restore"' in imports_html
    assert 'id="includeDeletedQualityIssues" type="checkbox" data-permission="imports.forestBlocks.restore"' in imports_html
    assert 'includeDeleted: $("#includeDeletedImportAuditEvents")?.checked ? "true" : ""' in imports_js
    assert 'includeDeleted: $("#includeDeletedQualityIssues")?.checked ? "true" : ""' in imports_js
    assert 'id="includeDeletedScenes" type="checkbox" data-permission="imagery.scenes.restore"' in imagery_html
    assert '<option value="archived" data-permission="imagery.scenes.archive"' in imagery_html
    assert '<option value="deleted" data-permission="imagery.scenes.restore"' in imagery_html
    assert 'id="includeArchivedTasks" type="checkbox" data-permission="imagery.tasks.archive"' in imagery_html
    assert 'id="includeArchivedImageryIssues" type="checkbox" data-permission="imagery.tasks.archive"' in imagery_html
    assert 'id="includeDeletedLayers" type="checkbox" data-permission="map.layers.restore"' in layers_html


def test_admin_crud_overlay_keeps_light_product_ui_tone():
    css = _read("admin.css")

    assert "color-scheme: light;" in css
    assert "background: rgba(243, 246, 245, 0.88);" in css
    assert "backdrop-filter: blur(10px);" not in css


def test_admin_light_theme_defines_all_used_design_tokens():
    css = _read("admin.css")
    defined_tokens = set(re.findall(r"--([a-zA-Z0-9-]+)\s*:", css))
    used_tokens = set(re.findall(r"var\(--([a-zA-Z0-9-]+)", css))

    assert "--accent-strong" in css
    assert "--surface" in css
    assert used_tokens <= defined_tokens


def test_admin_login_uses_cookie_session_and_preserves_safe_return_path():
    html = _read("admin-login.html")
    js = _read("admin-login.js")
    common = _read("admin-common.js")

    assert 'id="accessToken"' not in html
    assert 'id="loginForm"' in html
    assert 'type="password"' in html
    assert "/api/auth/me" in js
    assert "sessionStorage.setItem" in js
    assert 'credentials: "include"' in js
    assert "safeReturnPath" in js
    assert 'credentials: "include"' in common
    assert 'headers.set("X-CSRF-Token", csrfToken())' in common
    assert "const LEGACY_TOKEN_KEYS" in common
    assert "clearLegacyTokenState" in common
    assert "redirectToLogin" in common
    assert "clearSessionState" in common


def test_smart_bamboo_ui_design_baseline_documents_product_admin_direction():
    doc = _read("docs/smart-bamboo-ui-design-baseline.md")

    assert "impeccable" in doc
    assert "taste skill" in doc
    assert "后台浅色台账" in doc
    assert "行级查看、编辑、删除" in doc
    assert "暂无后台数据" in doc
    assert "静态菜单分组兜底" in doc
    assert "大屏" in doc


def test_import_admin_shows_unified_batch_audit_events():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="importBatchAuditEventsList"' in html
    assert "function renderImportBatchAuditEvents" in js
    assert "auditEvents" in js
    assert "操作审计" in html


def test_import_admin_has_cross_batch_audit_event_ledger():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="importAuditActionFilter"' in html
    assert 'id="importAuditBatchFilter"' in html
    assert 'id="refreshImportAuditEvents"' in html
    assert 'id="exportImportAuditEvents"' in html
    assert 'data-permission="imports.forestBlocks.export"' in html
    assert 'id="importAuditRows"' in html
    assert "/api/imports/forest-blocks/audit-events" in js
    assert "/api/imports/forest-blocks/audit-events.csv" in js
    assert "function auditQuery" in js
    assert "function loadImportAuditEvents" in js
    assert "function exportImportAuditEvents" in js
    assert "function renderImportAuditEvents" in js
    assert "event.batchId" in js
    assert "event.action" in js


def test_import_admin_renders_audit_summaries_as_scannable_fields():
    js = _read("admin-imports.js")
    css = _read("admin.css")

    assert "function renderAuditSummary" in js
    assert "function auditSummaryPairs" in js
    assert "AUDIT_SUMMARY_LABELS" in js
    assert "renderAuditSummary(event.summary)" in js
    assert "renderAuditSummary(event.summary, { limit: 8 })" in js
    assert "<small>${escapeHtml(stringifyPretty(event.summary, {}))}</small>" not in js
    assert "<span>${escapeHtml(stringifyPretty(event.summary, {}))}</span>" not in js
    assert ".audit-summary" in css
    assert ".audit-summary-chip" in css


def test_import_admin_renders_audit_event_codes_as_chinese_labels():
    js = _read("admin-imports.js")

    assert "const IMPORT_AUDIT_ACTION_LABELS" in js
    assert "const IMPORT_REVIEW_RECOMMENDATION_LABELS" in js
    assert '"export-acceptance-receipt": "导出验收回执"' in js


def test_import_source_file_radios_have_accessible_names():
    js = _read("admin-imports.js")

    assert 'aria-label="选择成果文件：${escapeHtml(item.name || item.path)}"' in js
    assert 'permission: "权限"' in js
    assert 'receiptType: "回执类型"' in js
    assert "displayLabel(IMPORT_AUDIT_ACTION_LABELS, event.action" in js
    assert "displayLabel(BATCH_STATUS_LABELS, event.batchStatus" in js
    assert "displayLabel(REVIEW_STATUS_LABELS, event.reviewStatus" in js
    assert "displayLabel(PUBLISH_RISK_LABELS, event.publishRiskStatus" in js
    assert "displayLabel(IMPORT_REVIEW_RECOMMENDATION_LABELS, batch.reviewRecommendation" in js
    assert "displayLabel(BATCH_QUALITY_STATUS_LABELS, readiness.quality?.qualityStatus" in js
    assert "displayLabel(PUBLISH_RISK_LABELS, readiness.quality?.publishRiskStatus" in js


def test_import_receipt_export_refreshes_audit_ledgers():
    js = _read("admin-imports.js")

    assert "async function exportImportBatchReceipt" in js
    assert "await loadImportBatches();" in js
    assert "await loadImportAuditEvents();" in js
    assert "renderImportBatchDetail(activeBatch());" in js
    assert 'done: "验收回执已导出，导出事件已写入审计流。"' in js


def test_import_admin_shows_quality_status_and_publish_risk():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="batchQualityStatusFilter"' in html
    assert 'id="batchPublishRiskStatusFilter"' in html
    assert "qualityStatus" in js
    assert "publishRiskStatus" in js
    assert "reviewRecommendation" in js
    assert "质量状态" in js
    assert "发布风险" in js
    assert "审核建议" in js


def test_import_admin_detail_shows_batch_workflow_stepper():
    js = _read("admin-imports.js")
    css = _read("admin.css")

    assert "function importBatchWorkflowSteps" in js
    assert "function renderImportBatchWorkflowSteps" in js
    assert "renderWorkflowStepper(importBatchWorkflowSteps(batch))" in js
    assert "renderImportBatchWorkflowSteps(batch)" in js
    for key in [
        "imported",
        "quality",
        "review",
        "acceptance",
        "imagery-link",
        "layer-publish",
        "delivery-package",
    ]:
        assert f'key: "{key}"' in js
    assert ".workflow-stepper" in css
    assert ".workflow-step" in css
    assert '[data-state="complete"]' in css
    assert '[data-state="blocked"]' in css


def test_import_admin_disables_scene_layer_link_until_batch_is_approved():
    js = _read("admin-imports.js")

    assert 'batch.reviewStatus !== "approved"' in js
    assert "批次需审核通过后才能关联影像图层" in js


def test_import_admin_has_cross_batch_quality_issue_ledger():
    html = _read("admin-imports.html")
    js = _read("admin-imports.js")

    assert 'id="qualityIssueTypeFilter"' in html
    assert 'id="qualityIssueSeverityFilter"' in html
    assert 'id="qualityIssueBatchFilter"' in html
    assert 'id="refreshQualityIssues"' in html
    assert 'id="exportQualityIssues"' in html
    assert 'data-permission="imports.forestBlocks.export"' in html
    assert 'id="qualityIssueRows"' in html
    assert "/api/imports/forest-blocks/quality-issues" in js
    assert "/api/imports/forest-blocks/quality-issues.csv" in js
    assert "qualityIssues" in js
    assert "function qualityIssueQuery" in js
    assert "function loadQualityIssues" in js
    assert "function exportQualityIssues" in js
    assert '$("#exportQualityIssues")?.addEventListener("click", exportQualityIssues)' in js
    assert "function renderQualityIssueRows" in js
    assert "issue.issueType" in js
    assert "issue.actionRequired" in js


def test_imagery_admin_has_task_detail_and_retry_actions():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    assert 'id="taskDetailPanel"' in html
    assert 'id="taskDetailGrid"' in html
    assert 'id="taskEventList"' in html
    assert 'id="retryTask"' in html
    assert 'id="closeTaskDetail"' in html
    assert "/api/tasks/" in js
    assert "/retry" in js
    assert "function activeTask" in js
    assert "function renderTaskDetail" in js
    assert "function closeTaskDetail" in js
    assert "function retryTask" in js
    assert "function handleTaskRowAction" in js
    assert "function renderTaskEvents" in js


def test_imagery_task_detail_links_scene_layer_and_quality_issues():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    assert "任务追溯" in html
    assert 'id="taskTraceList"' in html
    assert "function taskTraceItems" in js
    assert "function renderTaskTrace" in js
    assert "taskTraceItems(task)" in js
    assert "renderTaskTrace(task)" in js
    assert "#taskTraceList" in js
    assert "admin-imagery.html?sceneId=" in js
    assert "admin-map-layers.html?layerCode=" in js
    assert "admin-imagery.html?imageryIssueId=" in js
    assert "state.imageryIssues.filter" in js
    assert "task.publishedLayerRecordCode" in js
    assert "scene.publishedLayerRecordCode" in js


def test_imagery_admin_can_cancel_and_archive_tasks_from_task_ledger():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    assert 'id="cancelTask"' in html
    assert 'id="archiveTask"' in html
    assert "/cancel" in js
    assert "/archive" in js
    assert "function cancelTask" in js
    assert "function archiveTask" in js
    assert 'data-task-action="cancel"' in js
    assert 'data-task-action="archive"' in js
    assert "data-cancel-allowed" in js
    assert "data-archive-allowed" in js
    assert "includeArchived" in js
    assert "syncTaskActionButtons" in js


def test_imagery_admin_has_cross_task_event_ledger():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    assert 'id="taskEventStatusFilter"' in html
    assert 'id="taskEventActionFilter"' in html
    assert 'id="taskEventRows"' in html
    assert 'id="refreshTaskEvents"' in html
    assert 'id="exportTaskEvents"' in html
    assert 'data-permission="imagery.scenes.export"' in html
    assert "/api/tasks/events" in js
    assert "/api/tasks/events.csv" in js
    assert "function taskEventQuery" in js
    assert "function loadTaskEvents" in js
    assert "function exportTaskEvents" in js
    assert "function renderTaskEventRows" in js
    assert "state.taskEvents" in js
    assert "event.taskId" in js
    assert "event.status" in js


def test_imagery_admin_has_quality_issue_ledger():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    assert 'id="imageryIssueTypeFilter"' in html
    assert 'id="imageryIssueSeverityFilter"' in html
    assert 'id="imageryIssueSceneFilter"' in html
    assert 'id="imageryIssueTaskFilter"' in html
    assert 'id="refreshImageryIssues"' in html
    assert 'id="exportImageryIssues"' in html
    assert 'data-permission="imagery.scenes.export"' in html
    assert 'id="imageryIssueRows"' in html
    assert "/api/scenes/quality-issues" in js
    assert "/api/scenes/quality-issues.csv" in js
    assert "imageryIssues" in js
    assert "function imageryIssueQuery" in js
    assert 'includeArchived: $("#includeArchivedImageryIssues")?.checked ? "true" : ""' in js
    assert '$("#includeArchivedImageryIssues")?.addEventListener("change", loadImageryIssues)' in js
    assert "function loadImageryIssues" in js
    assert "function exportImageryIssues" in js
    assert '$("#exportImageryIssues")?.addEventListener("click", exportImageryIssues)' in js
    assert "function renderImageryIssueRows" in js
    assert "issue.issueType" in js
    assert "issue.actionRequired" in js


def test_imagery_admin_renders_backend_codes_as_chinese_ledger_labels():
    js = _read("admin-imagery.js")

    assert "const SCENE_STATUS_LABELS" in js
    assert "const SCENE_EVENT_TYPE_LABELS" in js
    assert "const SCENE_EVENT_ACTION_LABELS" in js
    assert "const TASK_STATUS_LABELS" in js
    assert "const IMAGERY_ISSUE_TYPE_LABELS" in js
    assert "const ISSUE_SEVERITY_LABELS" in js
    assert "const BATCH_STATUS_LABELS" in js
    assert "function displayLabel" in js
    assert "function sceneEventDisplayLabel" in js
    assert "displayLabel(SCENE_STATUS_LABELS, scene.status" in js
    assert "displayLabel(SCENE_EVENT_TYPE_LABELS, event.eventType" in js
    assert "displayLabel(SCENE_EVENT_ACTION_LABELS, event.action" in js
    assert "sceneEventDisplayLabel(event)" in js
    assert "displayLabel(TASK_STATUS_LABELS, task.status" in js
    assert "displayLabel(TASK_STATUS_LABELS, event.status" in js
    assert "displayLabel(IMAGERY_ISSUE_TYPE_LABELS, issue.issueType" in js
    assert "displayLabel(ISSUE_SEVERITY_LABELS, issue.severity" in js
    assert "displayLabel(BATCH_STATUS_LABELS, batch.status" in js


def test_imagery_admin_can_publish_scene_layers_and_show_audit_events():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    assert 'id="publishSceneLayer"' in html
    assert 'id="sceneOperationResult"' in html
    assert 'id="sceneLayerName"' in html
    assert 'id="sceneLayerLinkedBlockCodes"' in html
    assert 'id="sceneLayerLinkedRightArchiveCodes"' in html
    assert 'id="sceneLayerZIndex"' in html
    assert 'id="sceneLayerVisibleOnDashboard"' in html
    assert 'id="scenePublishEventList"' in html
    assert 'id="sceneImportBatchLinksList"' in html
    assert "入库批次追溯" in html
    assert "/publish-layer" in js
    assert "/api/imports/forest-blocks/batches?" in js
    assert "function sceneLayerPublishPayload" in js
    assert 'name: $("#sceneLayerName")?.value.trim()' in js
    assert 'linkedBlockCodes: splitValues($("#sceneLayerLinkedBlockCodes")?.value || "")' in js
    assert 'linkedRightArchiveCodes: splitValues($("#sceneLayerLinkedRightArchiveCodes")?.value || "")' in js
    assert 'visibleOnDashboard: $("#sceneLayerVisibleOnDashboard")?.value !== "false"' in js
    assert "Number.isFinite(zIndex)" in js
    assert "function publishSceneLayer" in js
    assert "sceneLayerPublishPayload(scene)" in js
    assert "function renderSceneOperationResult" in js
    assert "sceneOperationResult" in js
    assert "operation-result" in js
    assert "payload.layer" in js
    assert "dashboardHref" in js
    assert "sourceLinks" in js
    assert '$("#publishSceneLayer")?.addEventListener("click"' in js
    assert "function renderScenePublishEvents" in js
    assert "function loadSceneImportBatchLinks" in js
    assert "function renderSceneImportBatchLinks" in js
    assert "publishEvents" in js
    assert "sceneImportBatchLinksList" in js
    assert " 路 " not in js
    assert 'data-permission="imagery.layers.publish"' in html
    assert "IMAGERY_LAYER_PUBLISH_PERMISSION" in js


def test_imagery_publish_controls_have_single_source_of_truth():
    html = _read("admin-imagery.html")

    assert 'id="scenePublishControlsTemplate"' not in html
    for control_id in [
        "publishSceneLayer",
        "sceneLayerPublishConfig",
        "sceneLayerName",
        "sceneLayerLinkedBlockCodes",
        "sceneLayerLinkedRightArchiveCodes",
        "sceneLayerZIndex",
        "sceneLayerVisibleOnDashboard",
        "sceneOperationResult",
        "scenePublishEventList",
        "sceneLifecycleEventList",
    ]:
        assert html.count(f'id="{control_id}"') == 1


def test_imagery_admin_shows_scene_lifecycle_events():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    assert "sceneLifecycleEventList" in html
    assert "function renderSceneLifecycleEvents" in js
    assert "const SCENE_LIFECYCLE_ACTION_LABELS" in js
    assert '"export-delivery-receipt": "导出交付回执"' in js
    assert "displayLabel(SCENE_LIFECYCLE_ACTION_LABELS, event.action" in js
    assert "lifecycleEvents" in js
    assert "soft-delete" in js


def test_imagery_receipt_export_refreshes_scene_events_and_detail():
    js = _read("admin-imagery.js")

    assert "async function exportSceneDeliveryReceipt" in js
    assert "await loadScenes();" in js
    assert "await loadSceneEvents();" in js
    assert "renderDetail(activeScene() || scene);" in js
    assert 'done: "交付回执已导出，导出事件已写入影像事件流。"' in js


def test_imagery_admin_has_cross_scene_event_ledger():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    assert 'id="sceneEventTypeFilter"' in html
    assert 'id="sceneEventActionFilter"' in html
    assert 'id="sceneEventRows"' in html
    assert 'id="refreshSceneEvents"' in html
    assert 'id="exportSceneEvents"' in html
    assert 'data-permission="imagery.scenes.export"' in html
    assert "/api/scenes/events" in js
    assert "/api/scenes/events.csv" in js
    assert "function sceneEventQuery" in js
    assert "function loadSceneEvents" in js
    assert "function exportSceneEvents" in js
    assert "function renderSceneEvents" in js
    assert "state.sceneEvents" in js
    assert "event.sceneId" in js
    assert "event.eventType" in js
    assert "event.action" in js


def test_imagery_admin_can_include_deleted_scenes_and_restore_them():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    assert 'id="includeDeletedScenes"' in html
    assert 'id="sceneStatusFilter"' in html
    assert "includeDeleted" in js
    assert "status:" in js
    assert 'sceneStatus === "deleted"' in js
    assert "/restore" in js
    assert "function restoreScene" in js
    assert 'data-scene-action="restore"' in js
    assert "restoreScene(scene)" in js


def test_imagery_admin_can_archive_scene_and_pause_published_layer():
    js = _read("admin-imagery.js")

    assert "/archive" in js
    assert "function archiveScene" in js
    assert 'data-scene-action="archive"' in js
    assert "archiveScene(scene)" in js
    assert "ARCHIVE_ICON" in js
    assert "归档影像" in js


def test_imagery_admin_row_actions_can_publish_layers_and_export_delivery_receipts():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")
    css = _read("admin.css")

    assert "imagery-scene-table-wrap" in html
    assert "function sceneActionButtons" in js
    assert 'data-scene-action="publish-layer"' in js
    assert 'data-scene-action="delivery-receipt"' in js
    assert 'data-scene-action="publication-receipt"' in js
    assert 'data-permission="${IMAGERY_LAYER_PUBLISH_PERMISSION}"' in js
    assert 'data-permission-all="${IMAGERY_MAP_LAYER_REQUIRED_PERMISSION}"' in js
    assert 'data-permission-any="${IMAGERY_MAP_LAYER_UPSERT_PERMISSIONS}"' in js
    assert 'data-permission="${IMAGERY_SCENE_EXPORT_PERMISSION}"' in js
    assert 'sceneButton.dataset.sceneAction === "publish-layer"' in js
    assert "publishSceneLayer(scene)" in js
    assert 'sceneButton.dataset.sceneAction === "delivery-receipt"' in js
    assert "exportSceneDeliveryReceipt(scene)" in js
    assert 'sceneButton.dataset.sceneAction === "publication-receipt"' in js
    assert "exportScenePublicationReceipt(scene)" in js
    assert "function exportScenePublicationReceipt" in js
    assert "/api/scenes/${encodeURIComponent(scene.id)}/publication-receipt.json" in js
    assert "scene-publication-receipt-" in js
    assert "event.preventDefault()" in js
    assert "row-actions-extra-wide" in js
    assert ".row-actions-extra-wide" in css


def test_imagery_admin_detail_shows_scene_workflow_stepper():
    js = _read("admin-imagery.js")
    css = _read("admin.css")

    assert "function sceneWorkflowSteps" in js
    assert "function renderSceneWorkflowSteps" in js
    assert "renderWorkflowStepper(sceneWorkflowSteps(scene))" in js
    assert "renderSceneWorkflowSteps(scene)" in js
    for key in [
        "catalog",
        "cog",
        "quality",
        "layer-publish",
        "delivery",
    ]:
        assert f'key: "{key}"' in js
    assert ".workflow-stepper" in css
    assert ".workflow-step" in css
    assert '[data-state="pending"]' in css
    assert '[data-state="warning"]' in css


def test_import_admin_detail_shows_operation_permission_boundary():
    js = _read("admin-imports.js")
    css = _read("admin.css")

    assert "function importBatchPermissionBoundaryItems" in js
    assert "function renderImportBatchPermissionBoundary" in js
    assert "renderImportBatchPermissionBoundary(batch)" in js
    assert "permission-boundary-list" in js
    assert "permission-boundary-item" in js
    assert "IMPORT_REVIEW_PERMISSION" in js
    assert "IMPORT_ACCEPTANCE_PERMISSION" in js
    assert "IMPORT_SCENE_LAYER_LINK_PERMISSION" in js
    assert "IMPORT_MAP_LAYER_REQUIRED_PERMISSION" in js
    assert "IMPORT_MAP_LAYER_UPSERT_PERMISSIONS" in js
    assert "IMPORT_ROLLBACK_PERMISSION" in js
    assert "IMPORT_EXPORT_PERMISSION" in js
    assert ".permission-boundary-list" in css
    assert ".permission-boundary-item" in css
    assert ".permission-boundary-permissions" in css


def test_imagery_admin_detail_shows_operation_permission_boundary():
    js = _read("admin-imagery.js")
    css = _read("admin.css")

    assert "function scenePermissionBoundaryItems" in js
    assert "function renderScenePermissionBoundary" in js
    assert "renderScenePermissionBoundary(scene)" in js
    assert "permission-boundary-list" in js
    assert "permission-boundary-item" in js
    assert "IMAGERY_SCENE_UPDATE_PERMISSION" in js
    assert "IMAGERY_LAYER_PUBLISH_PERMISSION" in js
    assert "IMAGERY_MAP_LAYER_REQUIRED_PERMISSION" in js
    assert "IMAGERY_MAP_LAYER_UPSERT_PERMISSIONS" in js
    assert "IMAGERY_SCENE_DELIVERY_PERMISSION" in js
    assert "IMAGERY_SCENE_ARCHIVE_PERMISSION" in js
    assert "IMAGERY_SCENE_EXPORT_PERMISSION" in js
    assert ".permission-boundary-list" in css
    assert ".permission-boundary-item" in css
    assert ".permission-boundary-permissions" in css


def test_imagery_admin_can_edit_scene_metadata_fields():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    for field_id in [
        "imageryName",
        "imagerySatellite",
        "imagerySensor",
        "imageryCapturedAt",
        "imageryResolution",
        "imageryBounds",
        "imageryVisible",
        "imageryOpacity",
    ]:
        assert f'id="{field_id}"' in html
    assert "function scenePayloadFromForm" in js
    assert "imagerySatellite" in js
    assert "imageryBounds" in js
    assert "imageryVisible" in js
    assert "imageryOpacity" in js
    assert "`/api/scenes/${encodeURIComponent(sceneId)}`" in js
    assert "metadata-update" in js or "元数据" in html


def test_map_layer_admin_shows_source_traceability_controls():
    html = _read("admin-map-layers.html")
    js = _read("admin-map-layers.js")

    assert 'id="layerSourceTypeFilter"' in html
    assert 'id="layerRiskStatusFilter"' in html
    assert 'id="includeDeletedLayers"' in html
    assert '<th>来源</th>' in html
    assert '<th>发布风险</th>' in html
    assert 'id="layerSourceTraceList"' in html
    assert "sourceType" in js
    assert "publishRiskStatus" in js
    assert "includeDeleted" in js
    assert "/restore" in js
    assert "function restoreLayer" in js
    assert 'data-layer-action="restore"' in js
    assert "qualityStatus" in js
    assert "reviewRecommendation" in js
    assert "发布风险" in js
    assert "质量状态" in js
    assert "审核建议" in js
    assert "function layerSourceTrace" in js
    assert "function renderLayerSourceTrace" in js
    assert "sourceLinks" in js
    assert "layer.sourceType" in js
    assert "trace.sourceLinks" in js
    assert "link.href" in js
    assert "sourceSceneId" in js
    assert "importBatchId" in js


def test_map_layer_detail_renders_full_source_trace_with_dashboard_and_origin_links():
    html = _read("admin-map-layers.html")
    js = _read("admin-map-layers.js")

    assert "来源追溯" in html
    assert "function layerSourceTraceItems" in js
    assert "layer.adminHref" in js
    assert "layer.dashboardHref" in js
    assert "zhushan-bigdata.html#mapLayers" in js
    assert "admin-map-layers.html?layerCode=" in js
    assert "admin-imports.html?batchId=" in js
    assert "admin-imagery.html?sceneId=" in js
    assert "properties.importBatchId" in js
    assert "properties.sourceSceneId" in js
    assert "trace.sourceLinks.forEach" in js
    assert "layerSourceTraceItems(layer, trace)" in js
    assert "source-trace-item" in js


def test_map_layer_admin_has_layer_event_ledger():
    html = _read("admin-map-layers.html")
    js = _read("admin-map-layers.js")

    assert 'id="layerEventActionFilter"' in html
    assert 'id="layerEventLayerFilter"' in html
    assert 'id="layerEventRows"' in html
    assert 'id="refreshLayerEvents"' in html
    assert 'id="exportLayerEvents"' in html
    assert 'data-permission="map.layers.export"' in html
    assert "/api/map-layers/events" in js
    assert "/api/map-layers/events.csv" in js
    assert "function layerEventQuery" in js
    assert "function loadLayerEvents" in js
    assert "function exportLayerEvents" in js
    assert "function renderLayerEvents" in js
    assert '$("#exportLayerEvents")?.addEventListener("click", exportLayerEvents)' in js
    assert "AdminCommon.buildHeaders()" in js
    assert "state.layerEvents" in js
    assert "event.layerId" in js
    assert "event.action" in js


def test_map_layer_admin_row_actions_can_publish_and_pause_layers():
    html = _read("admin-map-layers.html")
    js = _read("admin-map-layers.js")
    css = _read("admin.css")

    assert "map-layer-table-wrap" in html
    assert "PUBLISH_ICON" in js
    assert "PAUSE_ICON" in js
    assert 'data-layer-action="publish"' in js
    assert 'data-layer-action="pause"' in js
    assert 'data-permission="${ACTION_PERMISSIONS.publish}"' in js
    assert 'layerButton.dataset.layerAction === "publish"' in js
    assert "publishLayer(layer, true)" in js
    assert 'layerButton.dataset.layerAction === "pause"' in js
    assert "publishLayer(layer, false)" in js
    assert "`/api/map-layers/${encodeURIComponent(layer.id)}/publish`" in js
    assert "event.preventDefault()" in js
    assert "row-actions-extra-wide" in js
    assert ".map-layer-table-wrap" in css


def test_map_layer_admin_row_actions_can_export_publication_receipt():
    js = _read("admin-map-layers.js")

    assert "RECEIPT_ICON" in js
    assert 'data-layer-action="receipt"' in js
    assert 'data-permission="${ACTION_PERMISSIONS.export}"' in js
    assert 'layerButton.dataset.layerAction === "receipt"' in js
    assert "exportLayerPublicationReceipt(layer)" in js
    assert "function exportLayerPublicationReceipt" in js
    assert "publication-receipt.json" in js
    assert "map-layer-publication-receipt-" in js


def test_map_layer_admin_surfaces_publication_queue():
    html = _read("admin-map-layers.html")
    js = _read("admin-map-layers.js")
    css = _read("admin.css")

    assert 'id="mapLayerPublicationSummary"' in html
    assert 'id="mapLayerPublicationQueueRows"' in html
    assert 'id="refreshLayerPublicationQueue"' in html
    assert "/api/map-layers/dashboard" in js
    assert "state.layerDashboard" in js
    assert "function loadMapLayerPublicationQueue" in js
    assert "function renderMapLayerPublicationQueue" in js
    assert "function mapLayerPublicationQueueItem" in js
    assert "payload.publicationQueue" in js
    assert 'data-publication-action="open"' in js
    assert "requiredPermission" in js
    assert '$("#refreshLayerPublicationQueue")?.addEventListener("click", loadMapLayerPublicationQueue)' in js
    assert ".operation-queue-grid" in css


def test_map_layer_detail_shows_operation_permission_boundary():
    js = _read("admin-map-layers.js")
    css = _read("admin.css")

    assert "function layerPermissionBoundaryItems" in js
    assert "function renderLayerPermissionBoundary" in js
    assert "renderLayerPermissionBoundary(layer)" in js
    assert "permission-boundary-list" in js
    assert "permission-boundary-item" in js
    assert "ACTION_PERMISSIONS.create" in js
    assert "ACTION_PERMISSIONS.update" in js
    assert "ACTION_PERMISSIONS.publish" in js
    assert "ACTION_PERMISSIONS.delete" in js
    assert "ACTION_PERMISSIONS.restore" in js
    assert "ACTION_PERMISSIONS.export" in js
    assert ".permission-boundary-list" in css
    assert ".permission-boundary-item" in css


def test_map_layer_admin_consumes_dashboard_visibility_deep_link():
    html = _read("admin-map-layers.html")
    js = _read("admin-map-layers.js")

    assert 'id="layerVisibleFilter"' in html
    assert '<option value="true">发布到大屏</option>' in html
    assert '<option value="false">未发布到大屏</option>' in html
    assert "let initialVisibleOnDashboard" in js
    assert 'new URLSearchParams(window.location.search).get("visibleOnDashboard")' in js
    assert "function applyInitialLayerFilters" in js
    assert '$("#layerVisibleFilter").value = initialVisibleOnDashboard;' in js
    assert 'visibleOnDashboard: $("#layerVisibleFilter").value.trim(),' in js
    assert '$("#layerVisibleFilter").addEventListener("change", reloadLayersFromFirstPage)' in js


def test_map_layer_admin_renders_backend_codes_as_chinese_ledger_labels():
    js = _read("admin-map-layers.js")

    assert "const LAYER_STATUS_LABELS" in js
    assert "const LAYER_TYPE_LABELS" in js
    assert "const SOURCE_TYPE_LABELS" in js
    assert "const LAYER_EVENT_ACTION_LABELS" in js
    assert "function displayLabel" in js
    assert "displayLabel(LAYER_TYPE_LABELS, layer.layerType" in js
    assert "displayLabel(LAYER_STATUS_LABELS, layer.status" in js
    assert "displayLabel(SOURCE_TYPE_LABELS, event.sourceType" in js
    assert "displayLabel(LAYER_EVENT_ACTION_LABELS, event.action" in js
    assert "displayLabel(RISK_STATUS_LABELS, event.publishRiskStatus" in js
    assert "displayLabel(LAYER_STATUS_LABELS, event.status" in js


def test_import_imagery_and_map_layers_support_cross_module_deep_links():
    imports_js = _read("admin-imports.js")
    imagery_js = _read("admin-imagery.js")
    layers_js = _read("admin-map-layers.js")
    css = _read("admin.css")

    assert "let initialBatchId" in imports_js
    assert 'new URLSearchParams(window.location.search).get("batchId")' in imports_js
    assert "function consumeInitialBatchSelection" in imports_js
    assert "function traceLink" in imports_js
    assert "admin-imagery.html?sceneId=" in imports_js
    assert "admin-map-layers.html?layerCode=" in imports_js

    assert "let initialSceneId" in imagery_js
    assert 'new URLSearchParams(window.location.search).get("sceneId")' in imagery_js
    assert "let initialTaskId" in imagery_js
    assert 'new URLSearchParams(window.location.search).get("taskId")' in imagery_js
    assert "function consumeInitialSceneSelection" in imagery_js
    assert "function consumeInitialTaskSelection" in imagery_js
    assert "`/api/tasks/${encodeURIComponent(targetId)}`" in imagery_js
    assert "function traceLink" in imagery_js
    assert "admin-imports.html?batchId=" in imagery_js
    assert "admin-map-layers.html?layerCode=" in imagery_js

    assert "let initialLayerCode" in layers_js
    assert 'new URLSearchParams(window.location.search).get("layerCode")' in layers_js
    assert 'new URLSearchParams(window.location.search).get("layerId")' in layers_js
    assert "function consumeInitialLayerSelection" in layers_js
    assert 'class="trace-link"' in layers_js
    assert "admin-imagery.html?sceneId=" in layers_js
    assert "admin-imports.html?batchId=" in layers_js

    assert ".trace-link" in css


def test_import_and_imagery_workflow_summary_cards_expose_queue_drilldowns():
    imports_js = _read("admin-imports.js")
    imagery_js = _read("admin-imagery.js")
    css = _read("admin.css")

    for js in (imports_js, imagery_js):
        assert "function workflowSummaryCardHref" in js
        assert "function workflowSummaryCardActionLabel" in js
        assert 'class="workflow-summary-link"' in js
        assert 'aria-label="' in js
        assert "查看队列" in js
        assert "card.href || \"#\"" in js

    assert ".workflow-summary-link" in css
    assert ".workflow-summary-card:hover .workflow-summary-link" in css


def test_import_and_imagery_detail_panels_render_receipt_summaries():
    imports_html = _read("admin-imports.html")
    imports_js = _read("admin-imports.js")
    imagery_html = _read("admin-imagery.html")
    imagery_js = _read("admin-imagery.js")
    css = _read("admin.css")

    assert 'id="importBatchReceiptSummary"' in imports_html
    assert "function importBatchReceiptSummaryItems" in imports_js
    assert "function renderImportBatchReceiptSummary" in imports_js
    assert "renderImportBatchReceiptSummary(batch)" in imports_js
    assert "importBatchAcceptanceEvents" in imports_js
    assert "qualityIssueCount" in imports_js
    assert "auditEventCount" in imports_js
    assert "exportImportBatchReceipt(batch)" in imports_js
    assert 'data-receipt-action="import-acceptance"' in imports_js

    assert 'id="sceneDeliveryReceiptSummary"' in imagery_html
    assert "function sceneDeliveryReceiptSummaryItems" in imagery_js
    assert "function renderSceneDeliveryReceiptSummary" in imagery_js
    assert "renderSceneDeliveryReceiptSummary(scene)" in imagery_js
    assert "sceneDeliveryEvents" in imagery_js
    assert "publishedLayerRecordCode" in imagery_js
    assert "exportSceneDeliveryReceipt(scene)" in imagery_js
    assert 'data-receipt-action="scene-delivery"' in imagery_js
    assert ".receipt-summary-grid" in css
    assert ".receipt-summary-card" in css
    assert ".receipt-summary-command" in css


def test_imagery_detail_panel_renders_a_scene_thumbnail_preview():
    html = _read("admin-imagery.html")
    js = _read("admin-imagery.js")

    assert 'id="imageryPreview"' in html
    assert 'id="imageryPreviewImage"' in html
    assert 'id="imageryPreviewStatus"' in html
    assert "function renderScenePreview" in js
    assert "scene.thumbnailUrl" in js
    assert 'addEventListener("load"' in js
    assert 'addEventListener("error"' in js


def test_business_admin_uses_backend_typed_field_schema_for_form_controls():
    js = _read("admin-business-module.js")

    assert "state.fieldSchema" in js
    assert "function loadModuleFieldSchema" in js
    assert 'api("/api/business/modules")' in js
    assert 'field.inputType === "select"' in js
    assert 'field.inputType === "number"' in js
    assert 'field.inputType === "integer"' in js
    assert 'field.inputType === "date"' in js
    assert "field.options" in js
    assert "parseBusinessCoreFieldValue" in js
    assert "function ensureBusinessCoreFieldFilter" in js
    assert 'id="businessCoreFieldFilter"' in js
    assert 'id="businessCoreFieldValueFilter"' in js
    assert "fieldKey:" in js
    assert "fieldValue:" in js
    assert 'deleteButton.hidden = !record.id' in js
    assert "field.readOnly" in js


def test_governed_admin_fields_use_shared_dictionary_division_and_reference_controls():
    blocks_html = _read("admin-blocks.html")
    blocks_js = _read("admin-blocks.js")
    rights_html = _read("admin-rights.html")
    rights_js = _read("admin-rights.js")
    business_js = _read("admin-business-module.js")

    assert '<select id="countyCode"' in blocks_html
    assert '<input id="countyName" type="hidden"' in blocks_html
    assert "bindAdministrativeDivision" in blocks_js
    for dictionary_code in [
        "forest-base-types",
        "forest-operation-types",
        "quality-grades",
        "health-statuses",
        "risk-levels",
    ]:
        assert dictionary_code in blocks_js

    assert "admin-smart-fields.js" in rights_html
    assert "bindReferencePicker" in rights_js
    assert "/api/forest-blocks" in rights_js
    for dictionary_code in [
        "certificate-types",
        "right-types",
        "ownership-types",
        "archive-statuses",
    ]:
        assert dictionary_code in rights_js

    assert "bindReferencePicker" in business_js
    assert "/api/forest-blocks" in business_js
    assert "/api/forest-rights" in business_js
    assert 'field.inputType === "dictionary"' in business_js


def test_all_generic_business_pages_load_smart_fields_before_the_module_script():
    business_pages = [
        page
        for page in ADMIN_PAGES.values()
        if 'admin-business-module.js' in _read(page)
    ]
    assert business_pages
    for page in business_pages:
        html = _read(page)
        assert "admin-smart-fields.js" in html
        assert html.index("admin-smart-fields.js") < html.index("admin-business-module.js")


def test_role_detail_panel_renders_permission_receipt_summary():
    roles_html = _read("admin-roles.html")
    roles_js = _read("admin-roles.js")
    css = _read("admin.css")

    assert 'id="rolePermissionReceiptSummary"' in roles_html
    assert "function rolePermissionReceiptSummaryItems" in roles_js
    assert "function renderRolePermissionReceiptSummary" in roles_js
    assert "renderRolePermissionReceiptSummary(role)" in roles_js
    assert "configuredPermissionCount" in roles_js
    assert "dataScopeValueCount" in roles_js
    assert "auditEventCount" in roles_js
    assert "exportRoleReceipt(role)" in roles_js
    assert 'data-receipt-action="role-permission"' in roles_js
    assert 'data-permission="${ROLE_EVENT_EXPORT_PERMISSION}"' in roles_js
    assert ".receipt-summary-grid" in css
    assert ".receipt-summary-card" in css
    assert ".receipt-summary-command" in css


def test_role_detail_panel_renders_effective_permission_coverage_matrix():
    roles_html = _read("admin-roles.html")
    roles_js = _read("admin-roles.js")
    css = _read("admin.css")

    assert 'id="roleEffectivePermissionCoverage"' in roles_html
    assert "function roleEffectivePermissionCoverageItems" in roles_js
    assert "function renderRoleEffectivePermissionCoverage" in roles_js
    assert "renderRoleEffectivePermissionCoverage(role)" in roles_js
    assert "rolePermissionCoverageModuleState" in roles_js
    assert "rolePermissionCoverageSummary" in roles_js
    assert "roleMenuDiagnosticsForRole(role)" in roles_js
    assert "expandedDraftPermissionSet(role.permissions || [])" in roles_js
    assert 'data-coverage-state="visible"' in roles_js
    assert 'data-coverage-state="blocked"' in roles_js
    assert 'data-coverage-state="pending"' in roles_js
    assert ".permission-coverage-summary" in css
    assert ".permission-coverage-list" in css
    assert ".permission-coverage-item" in css


def test_module_write_buttons_declare_required_permissions():
    expectations = {
        "admin-blocks.html": ["forest.blocks.view", "forest.blocks.create"],
        "admin-rights.html": ["forest.rights.view", "forest.rights.create", "forest.rights.delete"],
        "admin-linkages.html": ["forest.linkages.manage"],
        "admin-roles.html": [
            "system.roles.view",
            "system.roles.create",
            "system.roles.delete",
            "system.roles.restore",
            "system.roles.export",
        ],
        "admin-users.html": [
            "system.users.view",
            "system.users.create",
            "system.users.delete",
            "system.users.restore",
            "system.users.export",
        ],
        "admin-deployment.html": ["system.deployment.view"],
        "admin-map-layers.html": [
            "map.layers.view",
            "map.layers.create",
            "map.layers.delete",
            "map.layers.restore",
            "map.layers.publish",
        ],
        "admin-imports.html": [
            "imports.forestBlocks.view",
            "imports.forestBlocks.create",
            "imports.forestBlocks.review",
            "imports.forestBlocks.rollback",
            "imports.forestBlocks.export",
            "imports.sceneLayers.link",
        ],
        "admin-imagery.html": [
            "imagery.scenes.view",
            "imagery.scenes.create",
            "imagery.scenes.update",
            "imagery.scenes.delete",
            "imagery.tasks.cancel",
            "imagery.tasks.retry",
            "imagery.tasks.archive",
            "imagery.layers.publish",
        ],
    }

    for page, permissions in expectations.items():
        html = _read(page)
        for permission in permissions:
            assert f'data-permission="{permission}"' in html


def test_business_module_write_buttons_use_crud_action_permissions():
    js = _read("admin-business-module.js")

    assert "applyPagePermissionAttributes" in js
    assert 'businessPermission("create")' in js
    assert 'businessPermission("update")' in js
    assert 'businessPermission("delete")' in js
    assert 'businessPermission("restore")' in js
    assert 'businessPermission("export")' in js
    assert "#newBusinessRecord" in js
    assert "#deleteBusinessRecord" in js
    assert "#exportBusinessEvents" in js


def test_business_module_modals_support_keyboard_focus_and_dialog_semantics():
    js = _read("admin-business-module.js")

    assert 'setAttribute("role", "dialog")' in js
    assert 'setAttribute("aria-modal", "true")' in js
    assert 'event.key === "Escape"' in js
    assert 'event.key !== "Tab"' in js
    assert "focusableElements" in js
    assert "restoreModalFocus" in js


def test_business_module_admin_can_show_deleted_records_and_restore_them():
    js = _read("admin-business-module.js")

    assert "includeDeletedBusinessRecords" in js
    assert "ensureDeletedFilterToggle" in js
    assert "includeDeleted" in js
    assert "function isDeletedRecord" in js
    assert "function businessActionButtons" in js
    assert 'data-business-action="restore"' in js
    assert "function restoreRecord" in js
    assert "/restore" in js


def test_business_module_admin_renders_audit_trail_without_editing_audit_json():
    js = _read("admin-business-module.js")
    css = _read("admin.css")

    assert "const BUSINESS_EVENT_ACTION_LABELS" in js
    assert "function businessPropertiesWithoutAudit" in js
    assert "function businessPropertiesForEditing" in js
    assert "function businessAuditEvents" in js
    assert "function renderBusinessAuditTrail" in js
    assert "auditEvents" in js
    assert 'detailMarkup("最近操作", renderBusinessAuditTrail(record), "detail-wide")' in js
    assert "stringifyPretty(businessPropertiesWithoutAudit(record.properties), {})" in js
    assert "stringifyPretty(businessPropertiesForEditing(record), {})" in js
    assert ".detail-grid .detail-wide" in css


def test_business_module_admin_has_cross_record_event_ledger_and_export():
    js = _read("admin-business-module.js")
    css = _read("admin.css")

    assert "businessEvents" in js
    assert "function ensureBusinessEventLedger" in js
    assert 'id="businessEventRows"' in js
    assert 'id="refreshBusinessEvents"' in js
    assert 'id="exportBusinessEvents"' in js
    assert 'data-permission="${businessPermission("export")}"' in js
    assert "function businessEventQuery" in js
    assert "function renderBusinessEventRows" in js
    assert "function loadBusinessEvents" in js
    assert "function exportBusinessEvents" in js
    assert "function downloadFile" in js
    assert '`${endpoint}/events?${businessEventQuery()}`' in js
    assert '`${endpoint}/events.csv?${businessEventQuery()}`' in js
    assert 'businessPermission("export")' in js
    assert "businessEventActionFilter" in js
    assert "businessEventRecordFilter" in js
    assert "businessEventLinkedBlockFilter" in js
    assert "businessEventKeyword" in js
    assert "loadBusinessEvents();" in js
    assert ".business-event-table-wrap table" in css


def test_business_module_export_reports_backend_download_errors():
    js = _read("admin-business-module.js")

    assert "document.body.appendChild(link)" in js
    assert "link.remove()" in js
    assert 'setStatus("offline", `${messages.fail}：${error.message}`)' in js


def test_business_module_admin_renders_domain_core_fields_in_ledger_rows():
    js = _read("admin-business-module.js")
    css = _read("admin.css")

    assert "const moduleKey" in js
    assert "const BUSINESS_CORE_FIELDS" in js
    for module_key in [
        "farmers",
        "cooperatives",
        "enterprises",
        "plantProtection",
        "materials",
        "policies",
        "carbonEstimates",
        "supplyChainFinance",
    ]:
        assert f"{module_key}:" in js
    assert "function recordValueByPath" in js
    assert "function renderCoreFields" in js
    assert "business-core-fields" in js
    assert "business-core-field" in js
    assert "renderCoreFields(record)" in js
    assert ".business-core-fields" in css
    assert ".business-core-field" in css


def test_business_module_admin_edits_domain_core_fields_without_forcing_json_entry():
    js = _read("admin-business-module.js")
    css = _read("admin.css")

    assert "function editableCoreFields" in js
    assert "function ensureBusinessCoreFieldInputs" in js
    assert 'heading.id = "businessCoreFields"' in js
    assert 'data-business-core-field="${escapeHtml(field.key)}"' in js
    assert "function businessCoreInput" in js
    assert "function fillBusinessCoreFields" in js
    assert "function businessCoreFieldsFromForm" in js
    assert "function mergeBusinessCoreFieldsIntoProperties" in js
    assert "function businessCorePropertyKeys" in js
    assert "stringifyPretty(businessPropertiesForEditing(record), {})" in js
    assert "properties: mergeBusinessCoreFieldsIntoProperties(" in js
    assert 'detailMarkup("核心业务字段", renderCoreFields(record), "detail-wide")' in js
    assert "ensureBusinessCoreFieldInputs();" in js
    assert ".business-core-form-heading" in css
    assert ".business-core-field-input" in css


def test_admin_shell_defers_permissions_to_the_session_profile():
    js = _read("admin-common.js")

    assert "currentProfile" in js
    assert "sessionReadyPromise" in js
    assert "document.body.classList.add(\"admin-session-pending\")" in js
    assert "sessionReadyPromise" in js
    assert "blockBusinessRequests" in js
    assert "releaseBusinessRequests" in js


def test_admin_shell_rebuilds_sidebar_navigation_from_effective_menu_modules():
    js = _read("admin-common.js")

    assert "function renderBackendNavigation" in js
    assert "visibleMenuModules" in js
    assert "sidebar-nav-group" in js
    assert "module.group" in js
    assert "module.href" in js
    assert "module.key" in js
    assert "module.label" in js


def test_imagery_manage_permission_implies_layer_publish_in_frontend_permission_checks():
    common_js = _read("admin-common.js")
    roles_js = _read("admin-roles.js")

    assert "syncPermissionImplications(payload.permissionImplications)" in common_js
    assert "state.catalog.permissionImplications" in roles_js
    assert "syncPermissionImplications(payload.permissionImplications)" in roles_js


def test_linkage_save_button_inherits_page_permission_boundary():
    js = _read("admin-linkages.js")

    assert "applyPagePermissionAttributes" in js
    assert 'setAttribute("data-permission", pagePermission)' in js
    assert "#saveLinkage" in js


def test_zhushan_bigdata_has_backend_driven_forest_filter_panel():
    html = _read("zhushan-bigdata.html")
    js = _read("zhushan-bigdata.js")

    assert 'id="forestFilterPanel"' in html
    assert 'data-forest-filter="countyCode"' in html
    assert 'data-forest-filter="townCode"' in html
    assert "/api/map/forest-blocks/facets" in js
    assert "collectForestFilters" in js
    assert "renderForestFacets" in js
    assert "LIVE_FOREST_BLOCK_MAX_FEATURES" in js
    assert "maxFeatures" in js
    assert "geojson.meta?.truncated" in js


def test_zhushan_bigdata_does_not_render_static_demo_forest_blocks():
    js = _read("zhushan-bigdata.js")

    assert "const blocks = [];" in js
    assert "demoBlockFeatures" not in js
    assert "applyDemoForestBlocks" not in js
    assert "BP-001" not in js
    assert "source: new ol.source.Vector({ features: [] })" in js
    assert "地图不展示本地演示地块" in js


def test_primary_admin_ledgers_use_shared_server_side_pagination():
    common_js = _read("admin-common.js")
    css = _read("admin.css")

    assert "function createLedgerPager" in common_js
    assert 'className = "ledger-pagination"' in common_js
    assert "offset" in common_js
    assert "limit" in common_js
    assert ".ledger-pagination" in css

    for script_name in (
        "admin-blocks.js",
        "admin-rights.js",
        "admin-business-module.js",
        "admin-linkages.js",
        "admin-map-layers.js",
        "admin-imports.js",
        "admin-imagery.js",
        "admin-roles.js",
        "admin-users.js",
    ):
        js = _read(script_name)
        assert "createLedgerPager" in js
        assert "limit: pager.limit" in js
        assert "offset: pager.offset" in js
        assert "pager.setTotal" in js
        assert "pager.reset" in js
        assert "limit: 500" not in js


def test_map_layer_admin_pages_large_relation_targets_without_overwriting_them():
    html = _read("admin-map-layers.html")
    js = _read("admin-map-layers.js")

    assert "admin-map-layers.js?v=20260715-targets1" in html
    assert "/targets?kind=blocks&limit=100&offset=0" in js
    assert "/targets?kind=rights&limit=100&offset=0" in js
    assert "linkedTargetsTruncated" in js
    assert "preserveRelations" in js
    assert 'payload.linkedBlockCodes = splitValues($("#linkedBlockCodes").value)' in js


def test_business_admin_pages_large_relation_targets_without_overwriting_them():
    js = _read("admin-business-module.js")

    assert "/targets?kind=blocks&limit=100&offset=0" in js
    assert "/targets?kind=rights&limit=100&offset=0" in js
    assert "hydrateBusinessTargets" in js
    assert "linkedTargetsTruncated" in js
    assert "preserveRelations" in js
    assert "delete payload.linkedBlockCodes" in js
    assert "delete payload.linkedRightArchiveCodes" in js


def test_forest_right_admin_pages_large_block_relations_without_overwriting_them():
    js = _read("admin-rights.js")

    assert "/targets?limit=100&offset=0" in js
    assert "hydrateRightTargets" in js
    assert "linkedBlockCount" in js
    assert "linkedTargetsTruncated" in js
    assert "preserveRelations" in js
    assert "delete payload.linkedBlockCodes" in js


def test_admin_mobile_row_actions_meet_touch_target_size():
    css = _read("admin.css")
    mobile_css = css.split("@media (max-width: 860px)", 1)[1]

    assert ".icon-button,\n  .ledger-page-button" in mobile_css
    assert "width: 44px;" in mobile_css
    assert "min-width: 44px;" in mobile_css
    assert "height: 44px;" in mobile_css
    assert "min-height: 44px;" in mobile_css


def test_core_ledgers_replace_selectable_free_text_with_smart_controls():
    blocks_html = _read("admin-blocks.html")
    blocks_js = _read("admin-blocks.js")
    rights_html = _read("admin-rights.html")
    rights_js = _read("admin-rights.js")
    common_js = _read("admin-common.js")

    assert '<select id="forestType">' in blocks_html
    assert '["forestType", "forest-types"]' in blocks_js
    assert 'endpoint: "/api/dictionary-options/forest-resource-tags"' in blocks_js
    assert 'valueKey: "value"' in blocks_js
    assert 'labelKey: "label"' in blocks_js
    assert "state.tagPicker.setValues" in blocks_js

    assert 'id="rightArchiveHolder"' in rights_html
    assert 'endpoint: "/api/business-reference-options/subjects"' in rights_js
    assert 'valueKey: "name"' in rights_js
    assert "state.holderPicker.setValues" in rights_js
    assert 'id="rightArchiveRegistrar" type="text" readonly' in rights_html
    assert "authProfile" in common_js
    assert "authProfile()?.user" in rights_js


def test_business_forms_render_standard_month_inputs_for_period_fields():
    js = _read("admin-business-module.js")

    assert 'field.inputType === "month"' in js
    assert '? field.inputType' in js
