from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from .auth import AuthContext, effective_areas, has_admin_role, request_context, split_header_list
from . import database
from .database import (
    admin_roles_json_path,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
    use_postgis,
)
from .settings import get_settings


router = APIRouter(prefix="/api/admin", tags=["admin-roles"])

POSTGIS_SELECT_COLUMNS = [
    "id",
    "role_code",
    "name",
    "status",
    "permissions",
    "menu_modules",
    "data_scopes",
    "properties",
    "created_at",
    "updated_at",
    "deleted_at",
]

POSTGIS_SELECT_SQL = """
    SELECT
        id::text,
        role_code,
        name,
        status,
        COALESCE(permissions, '[]'::jsonb),
        COALESCE(menu_modules, '[]'::jsonb),
        COALESCE(data_scopes, '{}'::jsonb),
        COALESCE(properties, '{}'::jsonb),
        created_at,
        updated_at,
        deleted_at
    FROM admin_roles
"""
MYSQL_SELECT_SQL = """
    SELECT
        ar.id,
        ar.role_code,
        ar.name,
        ar.status,
        COALESCE((
            SELECT JSON_ARRAYAGG(arp.permission_code)
            FROM admin_role_permissions arp
            WHERE arp.admin_role_id = ar.id
        ), JSON_ARRAY()),
        COALESCE((
            SELECT JSON_ARRAYAGG(arm.module_key)
            FROM admin_role_menu_modules arm
            WHERE arm.admin_role_id = ar.id
        ), JSON_ARRAY()),
        COALESCE(ar.data_scopes, JSON_OBJECT()),
        COALESCE(ar.properties, JSON_OBJECT()),
        ar.created_at,
        ar.updated_at,
        ar.deleted_at
    FROM admin_roles ar
"""

DB_TO_API_FIELD = {
    "id": "id",
    "role_code": "roleCode",
    "name": "name",
    "status": "status",
    "permissions": "permissions",
    "menu_modules": "menuModules",
    "data_scopes": "dataScopes",
    "properties": "properties",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "deleted_at": "deletedAt",
}

ADMIN_MENU_MODULES = [
    {"key": "overview", "label": "后台首页", "href": "admin.html", "permission": "admin.overview.view", "group": "系统"},
    {"key": "deployment", "label": "部署诊断", "href": "admin-deployment.html", "permission": "system.deployment.view", "group": "系统"},
    {"key": "blocks", "label": "林班空间台账", "href": "admin-blocks.html", "permission": "forest.blocks.view", "group": "空间与权属"},
    {"key": "rights", "label": "林权档案台账", "href": "admin-rights.html", "permission": "forest.rights.view", "group": "空间与权属"},
    {"key": "linkages", "label": "图档关联管理", "href": "admin-linkages.html", "permission": "forest.linkages.manage", "group": "空间与权属"},
    {"key": "farmers", "label": "竹农管理", "href": "admin-farmers.html", "permission": "business.farmers.manage", "group": "经营主体"},
    {"key": "cooperatives", "label": "合作社管理", "href": "admin-cooperatives.html", "permission": "business.cooperatives.manage", "group": "经营主体"},
    {"key": "enterprises", "label": "竹企管理", "href": "admin-enterprises.html", "permission": "business.enterprises.manage", "group": "经营主体"},
    {"key": "plantProtection", "label": "植保管理", "href": "admin-plant-protection.html", "permission": "business.plantProtection.manage", "group": "生产服务"},
    {"key": "materials", "label": "农资管理", "href": "admin-materials.html", "permission": "business.materials.manage", "group": "生产服务"},
    {"key": "policies", "label": "政策法规管理", "href": "admin-policies.html", "permission": "business.policies.manage", "group": "政策项目"},
    {"key": "stewardshipAgreements", "label": "托管协议", "href": "admin-stewardship-agreements.html", "permission": "business.stewardshipAgreements.manage", "group": "运营管护"},
    {"key": "franchiseBases", "label": "加盟基地", "href": "admin-franchise-bases.html", "permission": "business.franchiseBases.manage", "group": "运营管护"},
    {"key": "maintenanceTasks", "label": "管护任务", "href": "admin-maintenance-tasks.html", "permission": "business.maintenanceTasks.manage", "group": "运营管护"},
    {"key": "workLogs", "label": "作业记录", "href": "admin-work-logs.html", "permission": "business.workLogs.manage", "group": "运营管护"},
    {"key": "droneTasks", "label": "无人机任务", "href": "admin-drone-tasks.html", "permission": "business.droneTasks.manage", "group": "运营管护"},
    {"key": "equipment", "label": "设备台账", "href": "admin-equipment.html", "permission": "business.equipment.manage", "group": "运营管护"},
    {"key": "pestWarnings", "label": "病虫害预警", "href": "admin-pest-warnings.html", "permission": "business.pestWarnings.manage", "group": "运营管护"},
    {"key": "materialServices", "label": "农资服务", "href": "admin-material-services.html", "permission": "business.materialServices.manage", "group": "运营管护"},
    {"key": "yieldForecasts", "label": "产量预测", "href": "admin-yield-forecasts.html", "permission": "business.yieldForecasts.manage", "group": "经营决策"},
    {"key": "harvestPlans", "label": "采挖计划", "href": "admin-harvest-plans.html", "permission": "business.harvestPlans.manage", "group": "经营决策"},
    {"key": "incomeEstimates", "label": "收益测算", "href": "admin-income-estimates.html", "permission": "business.incomeEstimates.manage", "group": "经营决策"},
    {"key": "performanceDashboards", "label": "绩效看板", "href": "admin-performance-dashboards.html", "permission": "business.performanceDashboards.manage", "group": "经营决策"},
    {"key": "carbonEstimates", "label": "碳汇测算", "href": "admin-carbon-estimates.html", "permission": "business.carbonEstimates.manage", "group": "经营决策"},
    {"key": "tradeMatches", "label": "交易撮合", "href": "admin-trade-matches.html", "permission": "business.tradeMatches.manage", "group": "产业平台"},
    {"key": "logisticsTraces", "label": "物流溯源", "href": "admin-logistics-traces.html", "permission": "business.logisticsTraces.manage", "group": "产业平台"},
    {"key": "productQrcodes", "label": "二维码管理", "href": "admin-product-qrcodes.html", "permission": "business.productQrcodes.manage", "group": "产业平台"},
    {"key": "supplyChainFinance", "label": "供应链金融", "href": "admin-supply-chain-finance.html", "permission": "business.supplyChainFinance.manage", "group": "产业平台"},
    {"key": "priceIndexes", "label": "价格指数", "href": "admin-price-indexes.html", "permission": "business.priceIndexes.manage", "group": "产业平台"},
    {"key": "mobileServiceChannels", "label": "移动端服务", "href": "admin-mobile-service-channels.html", "permission": "business.mobileServiceChannels.manage", "group": "产业平台"},
    {"key": "mapLayers", "label": "地图图层发布", "href": "admin-map-layers.html", "permission": "map.layers.view", "group": "地图发布"},
    {"key": "imports", "label": "成果入库", "href": "admin-imports.html", "permission": "imports.forestBlocks.view", "group": "数据治理"},
    {"key": "imagery", "label": "影像管理", "href": "admin-imagery.html", "permission": "imagery.scenes.view", "group": "数据治理"},
    {"key": "roles", "label": "角色权限管理", "href": "admin-roles.html", "permission": "system.roles.view", "group": "系统"},
    {"key": "users", "label": "用户账号管理", "href": "admin-users.html", "permission": "system.users.view", "group": "系统"},
]

MODULE_RESOURCE_PROFILES = {
    "overview": {
        "dataDomain": "platform-overview",
        "apiScopes": ["/api/health"],
    },
    "deployment": {
        "dataDomain": "deployment-readiness",
        "apiScopes": ["/api/health"],
    },
    "blocks": {
        "dataDomain": "forest-spatial",
        "apiScopes": [
            "/api/forest-blocks",
            "/api/map/forest-blocks.geojson",
            "/api/map/forest-blocks/summary",
            "/api/map/forest-blocks/facets",
            "/api/map/forest-blocks/aggregates",
        ],
    },
    "rights": {
        "dataDomain": "forest-rights",
        "apiScopes": ["/api/forest-rights"],
    },
    "linkages": {
        "dataDomain": "forest-linkages",
        "apiScopes": ["/api/forest-blocks/{id}/scenes"],
    },
    "mapLayers": {
        "dataDomain": "map-publishing",
        "apiScopes": [
            "/api/map-layers",
            "/api/map-layers/events.csv",
            "/api/map-layers/{record_id}/publication-receipt.json",
            "/api/map-layers/{record_id}/publish",
        ],
    },
    "imports": {
        "dataDomain": "forest-imports",
        "apiScopes": [
            "/api/imports/forest-blocks",
            "/api/imports/forest-blocks/sources",
            "/api/imports/forest-blocks/sources/import",
            "/api/imports/forest-blocks/batches",
            "/api/imports/forest-blocks/workflow-summary",
            "/api/imports/forest-blocks/workflow-summary.json",
            "/api/imports/forest-blocks/operation-queue",
            "/api/imports/forest-blocks/delivery-packages",
            "/api/imports/forest-blocks/delivery-packages.csv",
            "/api/imports/forest-blocks/delivery-packages.json",
            "/api/imports/forest-blocks/quality-issues",
            "/api/imports/forest-blocks/quality-issues.csv",
            "/api/imports/forest-blocks/audit-events.csv",
            "/api/imports/{batch_id}",
            "/api/imports/{batch_id}/report.json",
            "/api/imports/{batch_id}/errors.csv",
            "/api/imports/{batch_id}/acceptance-receipt.json",
            "/api/imports/{batch_id}/delivery-package-receipt.json",
            "/api/imports/{batch_id}/review",
            "/api/imports/{batch_id}/acceptance",
            "/api/imports/{batch_id}/rollback",
            "/api/imports/{batch_id}/restore",
            "/api/imports/{batch_id}/publish-readiness",
            "/api/imports/{batch_id}/link-scene-layer",
        ],
    },
    "imagery": {
        "dataDomain": "remote-sensing",
        "apiScopes": [
            "/api/scenes",
            "/api/scenes/upload",
            "/api/scenes/register",
            "/api/scenes/workflow-summary",
            "/api/scenes/workflow-summary.json",
            "/api/scenes/operation-queue",
            "/api/scenes/events",
            "/api/scenes/events.csv",
            "/api/scenes/quality-issues",
            "/api/scenes/quality-issues.csv",
            "/api/scenes/{scene_id}",
            "/api/scenes/{scene_id}/archive",
            "/api/scenes/{scene_id}/restore",
            "/api/scenes/{scene_id}/publish-layer",
            "/api/scenes/{scene_id}/delivery",
            "/api/scenes/{scene_id}/delivery-receipt.json",
            "/api/scenes/{scene_id}/publication-receipt.json",
            "/api/tasks",
            "/api/tasks/events.csv",
            "/api/tasks/{task_id}/retry",
            "/api/tasks/{task_id}/cancel",
            "/api/tasks/{task_id}/archive",
        ],
    },
    "roles": {
        "dataDomain": "identity-access",
        "apiScopes": [
            "/api/admin/roles",
            "/api/admin/roles/operation-queue",
            "/api/admin/permission-catalog",
            "/api/admin/effective-permissions",
        ],
    },
    "users": {
        "dataDomain": "identity-access",
        "apiScopes": ["/api/admin/users", "/api/admin/users/operation-queue"],
    },
}

PERMISSION_API_SCOPES = {
    "system.roles.view": [
        "/api/admin/permission-catalog",
        "/api/admin/roles",
        "/api/admin/roles/{role_id}",
        "/api/admin/roles/events",
        "/api/admin/roles/operation-queue",
    ],
    "system.roles.manage": [
        "/api/admin/permission-catalog",
        "/api/admin/permission-catalog.csv",
        "/api/admin/permission-closures.json",
        "/api/admin/roles",
        "/api/admin/roles/preview",
        "/api/admin/roles/events",
        "/api/admin/roles/events.csv",
        "/api/admin/roles/operation-queue",
        "/api/admin/roles/{role_id}",
        "/api/admin/roles/{role_id}/restore",
        "/api/admin/roles/{role_id}/permission-receipt.json",
    ],
    "system.roles.create": ["/api/admin/roles", "/api/admin/roles/preview"],
    "system.roles.update": ["/api/admin/roles/{role_id}", "/api/admin/roles/preview"],
    "system.roles.delete": ["/api/admin/roles/{role_id}"],
    "system.roles.restore": ["/api/admin/roles/{role_id}/restore"],
    "system.roles.export": [
        "/api/admin/permission-catalog.csv",
        "/api/admin/permission-closures.json",
        "/api/admin/roles/events.csv",
        "/api/admin/roles/{role_id}/permission-receipt.json",
    ],
    "system.users.view": [
        "/api/admin/users",
        "/api/admin/users/{user_id}",
        "/api/admin/users/{user_id}/effective-permissions",
        "/api/admin/users/events",
        "/api/admin/users/operation-queue",
    ],
    "system.users.manage": [
        "/api/admin/users",
        "/api/admin/users/effective-permissions/preview",
        "/api/admin/users/events",
        "/api/admin/users/events.csv",
        "/api/admin/users/operation-queue",
        "/api/admin/users/{user_id}",
        "/api/admin/users/{user_id}/restore",
        "/api/admin/users/{user_id}/access-receipt.json",
        "/api/admin/users/{user_id}/effective-permissions",
        "/api/admin/users/{user_id}/set-password",
        "/api/admin/users/{user_id}/revoke-sessions",
    ],
    "system.users.create": ["/api/admin/users", "/api/admin/users/effective-permissions/preview"],
    "system.users.update": ["/api/admin/users/{user_id}", "/api/admin/users/effective-permissions/preview"],
    "system.users.delete": ["/api/admin/users/{user_id}"],
    "system.users.restore": ["/api/admin/users/{user_id}/restore"],
    "system.users.export": ["/api/admin/users/events.csv", "/api/admin/users/{user_id}/access-receipt.json"],
    "system.users.setPassword": ["/api/admin/users/{user_id}/set-password"],
    "system.users.revokeSessions": ["/api/admin/users/{user_id}/revoke-sessions"],
    "imports.forestBlocks.view": [
        "/api/imports/forest-blocks/batches",
        "/api/imports/{batch_id}",
        "/api/imports/{batch_id}/report",
        "/api/imports/forest-blocks/workflow-summary",
        "/api/imports/forest-blocks/operation-queue",
        "/api/imports/forest-blocks/delivery-packages",
    ],
    "imports.forestBlocks.create": [
        "/api/imports/forest-blocks",
        "/api/imports/forest-blocks/sources",
        "/api/imports/forest-blocks/sources/import",
    ],
    "imports.forestBlocks.review": ["/api/imports/{batch_id}/review"],
    "imports.forestBlocks.quality": ["/api/imports/forest-blocks/quality-issues/{issue_id}"],
    "imports.forestBlocks.acceptance": ["/api/imports/{batch_id}/acceptance"],
    "imports.forestBlocks.rollback": ["/api/imports/{batch_id}/rollback"],
    "imports.forestBlocks.delete": ["/api/imports/{batch_id}"],
    "imports.forestBlocks.restore": ["/api/imports/{batch_id}/restore"],
    "imports.forestBlocks.export": [
        "/api/imports/forest-blocks/workflow-summary.json",
        "/api/imports/forest-blocks/delivery-packages.csv",
        "/api/imports/forest-blocks/delivery-packages.json",
        "/api/imports/forest-blocks/audit-events.csv",
        "/api/imports/forest-blocks/quality-issues.csv",
        "/api/imports/{batch_id}/report.json",
        "/api/imports/{batch_id}/errors.csv",
        "/api/imports/{batch_id}/acceptance-receipt.json",
        "/api/imports/{batch_id}/delivery-package-receipt.json",
    ],
    "imports.sceneLayers.link": [
        "/api/imports/{batch_id}/link-scene-layer",
        "/api/imports/{batch_id}/publish-readiness",
    ],
    "imagery.scenes.view": [
        "/api/scenes",
        "/api/scenes/{scene_id}",
        "/api/scenes/events",
        "/api/scenes/quality-issues",
        "/api/scenes/workflow-summary",
        "/api/scenes/operation-queue",
    ],
    "imagery.scenes.create": ["/api/scenes/upload", "/api/scenes/register"],
    "imagery.scenes.update": ["/api/scenes/{scene_id}"],
    "imagery.scenes.delete": ["/api/scenes/{scene_id}"],
    "imagery.scenes.restore": ["/api/scenes/{scene_id}/restore"],
    "imagery.scenes.archive": ["/api/scenes/{scene_id}/archive"],
    "imagery.scenes.quality": ["/api/scenes/quality-issues/{issue_id}"],
    "imagery.scenes.delivery": ["/api/scenes/{scene_id}/delivery"],
    "imagery.scenes.export": [
        "/api/scenes/workflow-summary.json",
        "/api/scenes/events.csv",
        "/api/tasks/events.csv",
        "/api/scenes/quality-issues.csv",
        "/api/scenes/{scene_id}/delivery-receipt.json",
        "/api/scenes/{scene_id}/publication-receipt.json",
    ],
    "imagery.tasks.retry": ["/api/tasks/{task_id}/retry"],
    "imagery.tasks.cancel": ["/api/tasks/{task_id}/cancel"],
    "imagery.tasks.archive": ["/api/tasks/{task_id}/archive"],
    "imagery.layers.publish": ["/api/scenes/{scene_id}/publish-layer"],
    "map.layers.view": [
        "/api/map-layers",
        "/api/map-layers/events",
        "/api/map-layers/dashboard",
    ],
    "map.layers.create": ["/api/map-layers"],
    "map.layers.update": ["/api/map-layers/{record_id}"],
    "map.layers.delete": ["/api/map-layers/{record_id}"],
    "map.layers.restore": ["/api/map-layers/{record_id}/restore"],
    "map.layers.export": [
        "/api/map-layers/events.csv",
        "/api/map-layers/{record_id}/publication-receipt.json",
    ],
    "map.layers.publish": ["/api/map-layers/{record_id}/publish"],
}

PERMISSION_DEPENDENCY_RULES = {
    "imports.sceneLayers.link": {
        "requiresAllPermissions": ["map.layers.publish"],
        "requiresAnyPermissions": [["map.layers.create", "map.layers.update"]],
        "dependencyReason": "Linking an import batch to an imagery layer can create or update a map layer and publish it to the big-screen map.",
    },
    "imagery.layers.publish": {
        "requiresAllPermissions": ["map.layers.publish"],
        "requiresAnyPermissions": [["map.layers.create", "map.layers.update"]],
        "dependencyReason": "Publishing imagery as a map layer can create or update the map layer record and expose it on the big-screen map.",
    },
}

BUSINESS_MENU_API_MODULE_OVERRIDES = {
    "plantProtection": "plant-protection-events",
}


def camel_to_kebab(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts: list[str] = []
    current = ""
    for char in text:
        if char.isupper() and current:
            parts.append(current)
            current = char.lower()
        else:
            current += char.lower()
    if current:
        parts.append(current)
    return "-".join(parts)


def business_api_module_key(menu_key: str) -> str:
    key = str(menu_key or "").strip()
    return BUSINESS_MENU_API_MODULE_OVERRIDES.get(key) or camel_to_kebab(key)


def business_module_api_scopes(menu_key: str) -> list[str]:
    api_key = business_api_module_key(menu_key)
    if not api_key:
        return []
    return [
        f"/api/business/{api_key}",
        f"/api/business/{api_key}/dashboard",
        f"/api/business/{api_key}/events",
        f"/api/business/{api_key}/events.csv",
    ]


def business_permission_api_scopes(module_key: str, action: str) -> list[str]:
    api_key = business_api_module_key(module_key)
    if not api_key:
        return []
    base = f"/api/business/{api_key}"
    action_scopes = {
        "view": [base, f"{base}/{{record_id}}", f"{base}/dashboard", f"{base}/events"],
        "manage": [
            base,
            f"{base}/{{record_id}}",
            f"{base}/{{record_id}}/restore",
            f"{base}/dashboard",
            f"{base}/events",
            f"{base}/events.csv",
        ],
        "create": [base],
        "update": [f"{base}/{{record_id}}"],
        "delete": [f"{base}/{{record_id}}"],
        "restore": [f"{base}/{{record_id}}/restore"],
        "export": [f"{base}/events.csv"],
    }
    return action_scopes.get(action, [])


def parse_business_permission(code: str) -> tuple[str, str] | None:
    parts = str(code or "").split(".")
    if len(parts) != 3 or parts[0] != "business":
        return None
    return parts[1], parts[2]


for module in ADMIN_MENU_MODULES:
    profile = MODULE_RESOURCE_PROFILES.get(module["key"], {})
    if not profile and str(module.get("permission") or "").startswith("business."):
        profile = {
            "dataDomain": f"business-{business_api_module_key(module['key'])}",
            "apiScopes": business_module_api_scopes(module["key"]),
        }
    module.setdefault("dataDomain", profile.get("dataDomain", ""))
    module.setdefault("apiScopes", list(profile.get("apiScopes") or []))

BUSINESS_ACTION_PERMISSIONS = [
    ("view", "查看"),
    ("manage", "全权管理"),
    ("create", "新增"),
    ("update", "编辑"),
    ("delete", "删除"),
    ("restore", "恢复"),
    ("export", "导出"),
]
BUSINESS_MODULE_KEYS = {
    module["key"]
    for module in ADMIN_MENU_MODULES
    if str(module.get("permission") or "").startswith("business.")
}

for module in ADMIN_MENU_MODULES:
    permission = str(module.get("permission") or "")
    if module["key"] in BUSINESS_MODULE_KEYS and permission.endswith(".manage"):
        module["permission"] = f"{permission.removesuffix('.manage')}.view"

EXTRA_PERMISSIONS = [
    {"code": "forest.blocks.view", "label": "林班台账查看", "module": "blocks"},
    {"code": "forest.blocks.manage", "label": "林班台账全权管理", "module": "blocks"},
    {"code": "forest.blocks.create", "label": "林班台账新增", "module": "blocks"},
    {"code": "forest.blocks.update", "label": "林班台账编辑", "module": "blocks"},
    {"code": "forest.blocks.delete", "label": "林班台账删除", "module": "blocks"},
    {"code": "forest.blocks.restore", "label": "林班台账恢复", "module": "blocks"},
    {"code": "forest.blocks.rollback", "label": "林班台账版本回滚", "module": "blocks"},
    {"code": "forest.rights.view", "label": "林权档案查看", "module": "rights"},
    {"code": "forest.rights.manage", "label": "林权档案全权管理", "module": "rights"},
    {"code": "forest.rights.create", "label": "林权档案新增", "module": "rights"},
    {"code": "forest.rights.update", "label": "林权档案编辑", "module": "rights"},
    {"code": "forest.rights.delete", "label": "林权档案删除", "module": "rights"},
    {"code": "forest.rights.restore", "label": "林权档案恢复", "module": "rights"},
    {"code": "forest.rights.rollback", "label": "林权档案版本回滚", "module": "rights"},
    {"code": "forest.linkages.manage", "label": "图档关联管理", "module": "linkages"},
    {"code": "imports.forestBlocks.view", "label": "成果入库查看", "module": "imports"},
    {"code": "imports.forestBlocks.manage", "label": "成果入库全权管理", "module": "imports"},
    {"code": "imports.forestBlocks.create", "label": "成果文件导入", "module": "imports"},
    {"code": "imports.forestBlocks.review", "label": "成果批次审核", "module": "imports"},
    {"code": "imports.forestBlocks.quality", "label": "成果质检处理", "module": "imports"},
    {"code": "imports.forestBlocks.acceptance", "label": "成果批次验收", "module": "imports"},
    {"code": "imports.forestBlocks.rollback", "label": "成果批次回滚", "module": "imports"},
    {"code": "imports.forestBlocks.delete", "label": "成果批次删除", "module": "imports"},
    {"code": "imports.forestBlocks.restore", "label": "成果批次恢复", "module": "imports"},
    {"code": "imports.forestBlocks.export", "label": "成果交付材料导出", "module": "imports"},
    {"code": "imports.sceneLayers.link", "label": "成果批次关联影像图层", "module": "imports"},
    {"code": "imagery.scenes.view", "label": "影像目录查看", "module": "imagery"},
    {"code": "imagery.scenes.manage", "label": "影像目录全权管理", "module": "imagery"},
    {"code": "imagery.scenes.create", "label": "影像入库", "module": "imagery"},
    {"code": "imagery.scenes.update", "label": "影像元数据编辑", "module": "imagery"},
    {"code": "imagery.scenes.delete", "label": "影像删除", "module": "imagery"},
    {"code": "imagery.scenes.restore", "label": "影像恢复", "module": "imagery"},
    {"code": "imagery.scenes.archive", "label": "影像归档", "module": "imagery"},
    {"code": "imagery.scenes.quality", "label": "影像质检处理", "module": "imagery"},
    {"code": "imagery.scenes.delivery", "label": "影像交付确认", "module": "imagery"},
    {"code": "imagery.scenes.export", "label": "影像交付材料导出", "module": "imagery"},
    {"code": "imagery.tasks.retry", "label": "影像任务重试", "module": "imagery"},
    {"code": "imagery.tasks.cancel", "label": "影像任务取消", "module": "imagery"},
    {"code": "imagery.tasks.archive", "label": "影像任务归档", "module": "imagery"},
    {"code": "imagery.layers.publish", "label": "影像发布为地图图层", "module": "imagery"},
    {"code": "map.layers.view", "label": "地图图层查看", "module": "mapLayers"},
    {"code": "map.layers.manage", "label": "地图图层全权管理", "module": "mapLayers"},
    {"code": "map.layers.create", "label": "地图图层新增", "module": "mapLayers"},
    {"code": "map.layers.update", "label": "地图图层编辑", "module": "mapLayers"},
    {"code": "map.layers.delete", "label": "地图图层删除", "module": "mapLayers"},
    {"code": "map.layers.restore", "label": "地图图层恢复", "module": "mapLayers"},
    {"code": "map.layers.export", "label": "地图图层事件导出", "module": "mapLayers"},
    {"code": "map.layers.publish", "label": "地图图层发布", "module": "mapLayers"},
    {"code": "system.roles.view", "label": "角色台账查看", "module": "roles"},
    {"code": "system.roles.manage", "label": "角色权限全权管理", "module": "roles"},
    {"code": "system.roles.create", "label": "角色新增", "module": "roles"},
    {"code": "system.roles.update", "label": "角色编辑", "module": "roles"},
    {"code": "system.roles.delete", "label": "角色删除", "module": "roles"},
    {"code": "system.roles.restore", "label": "角色恢复", "module": "roles"},
    {"code": "system.roles.export", "label": "角色审计导出", "module": "roles"},
    {"code": "system.deployment.view", "label": "部署诊断查看", "module": "deployment"},
    {"code": "system.users.view", "label": "用户账号查看", "module": "users"},
    {"code": "system.users.manage", "label": "用户账号全权管理", "module": "users"},
    {"code": "system.users.create", "label": "用户账号新增", "module": "users"},
    {"code": "system.users.update", "label": "用户账号编辑", "module": "users"},
    {"code": "system.users.delete", "label": "用户账号删除", "module": "users"},
    {"code": "system.users.restore", "label": "用户账号恢复", "module": "users"},
    {"code": "system.users.export", "label": "用户审计导出", "module": "users"},
    {"code": "system.users.setPassword", "label": "设置临时密码", "module": "users"},
    {"code": "system.users.revokeSessions", "label": "撤销用户会话", "module": "users"},
    {"code": "business.farmers.manage", "label": "竹农管理", "module": "farmers"},
    {"code": "business.cooperatives.manage", "label": "合作社管理", "module": "cooperatives"},
    {"code": "business.enterprises.manage", "label": "竹企管理", "module": "enterprises"},
    {"code": "business.plantProtection.manage", "label": "植保管理", "module": "plantProtection"},
    {"code": "business.materials.manage", "label": "农资管理", "module": "materials"},
    {"code": "business.policies.manage", "label": "政策法规管理", "module": "policies"},
    {"code": "business.stewardshipAgreements.manage", "label": "托管协议", "module": "stewardshipAgreements"},
    {"code": "business.franchiseBases.manage", "label": "加盟基地", "module": "franchiseBases"},
    {"code": "business.maintenanceTasks.manage", "label": "管护任务", "module": "maintenanceTasks"},
    {"code": "business.workLogs.manage", "label": "作业记录", "module": "workLogs"},
    {"code": "business.droneTasks.manage", "label": "无人机任务", "module": "droneTasks"},
    {"code": "business.equipment.manage", "label": "设备台账", "module": "equipment"},
    {"code": "business.pestWarnings.manage", "label": "病虫害预警", "module": "pestWarnings"},
    {"code": "business.materialServices.manage", "label": "农资服务", "module": "materialServices"},
    {"code": "business.yieldForecasts.manage", "label": "产量预测", "module": "yieldForecasts"},
    {"code": "business.harvestPlans.manage", "label": "采挖计划", "module": "harvestPlans"},
    {"code": "business.incomeEstimates.manage", "label": "收益测算", "module": "incomeEstimates"},
    {"code": "business.performanceDashboards.manage", "label": "绩效看板", "module": "performanceDashboards"},
    {"code": "business.carbonEstimates.manage", "label": "碳汇测算", "module": "carbonEstimates"},
    {"code": "business.tradeMatches.manage", "label": "交易撮合", "module": "tradeMatches"},
    {"code": "business.logisticsTraces.manage", "label": "物流溯源", "module": "logisticsTraces"},
    {"code": "business.productQrcodes.manage", "label": "二维码管理", "module": "productQrcodes"},
    {"code": "business.supplyChainFinance.manage", "label": "供应链金融", "module": "supplyChainFinance"},
    {"code": "business.priceIndexes.manage", "label": "价格指数", "module": "priceIndexes"},
    {"code": "business.mobileServiceChannels.manage", "label": "移动端服务", "module": "mobileServiceChannels"},
]


MANAGE_PERMISSION_IMPLICATIONS = {
    "forest.blocks.manage": [
        "forest.blocks.view",
        "forest.blocks.create",
        "forest.blocks.update",
        "forest.blocks.delete",
        "forest.blocks.restore",
        "forest.blocks.rollback",
    ],
    "forest.rights.manage": [
        "forest.rights.view",
        "forest.rights.create",
        "forest.rights.update",
        "forest.rights.delete",
        "forest.rights.restore",
        "forest.rights.rollback",
    ],
    "imports.forestBlocks.manage": [
        "imports.forestBlocks.view",
        "imports.forestBlocks.create",
        "imports.forestBlocks.review",
        "imports.forestBlocks.quality",
        "imports.forestBlocks.acceptance",
        "imports.forestBlocks.rollback",
        "imports.forestBlocks.delete",
        "imports.forestBlocks.restore",
        "imports.forestBlocks.export",
        "imports.sceneLayers.link",
    ],
    "imagery.scenes.manage": [
        "imagery.scenes.view",
        "imagery.scenes.create",
        "imagery.scenes.update",
        "imagery.scenes.delete",
        "imagery.scenes.restore",
        "imagery.scenes.archive",
        "imagery.scenes.quality",
        "imagery.scenes.delivery",
        "imagery.scenes.export",
        "imagery.tasks.retry",
        "imagery.tasks.cancel",
        "imagery.tasks.archive",
        "imagery.layers.publish",
    ],
    "map.layers.manage": [
        "map.layers.view",
        "map.layers.create",
        "map.layers.update",
        "map.layers.delete",
        "map.layers.restore",
        "map.layers.export",
        "map.layers.publish",
    ],
    "map.layers.publish": [
        "map.layers.view",
    ],
    "system.roles.manage": [
        "system.roles.view",
        "system.roles.create",
        "system.roles.update",
        "system.roles.delete",
        "system.roles.restore",
        "system.roles.export",
    ],
    "system.roles.create": ["system.roles.view"],
    "system.roles.update": ["system.roles.view"],
    "system.roles.delete": ["system.roles.view"],
    "system.roles.restore": ["system.roles.view"],
    "system.roles.export": ["system.roles.view"],
    "system.users.manage": [
        "system.users.view",
        "system.users.create",
        "system.users.update",
        "system.users.delete",
        "system.users.restore",
        "system.users.export",
        "system.users.setPassword",
        "system.users.revokeSessions",
        "system.roles.view",
    ],
    "system.users.create": ["system.users.view", "system.roles.view"],
    "system.users.update": ["system.users.view", "system.roles.view"],
    "system.users.delete": ["system.users.view"],
    "system.users.restore": ["system.users.view"],
    "system.users.export": ["system.users.view"],
}
MANAGE_PERMISSION_IMPLICATIONS.update(
    {
        f"business.{module_key}.manage": [
            f"business.{module_key}.view",
            f"business.{module_key}.create",
            f"business.{module_key}.update",
            f"business.{module_key}.delete",
            f"business.{module_key}.restore",
            f"business.{module_key}.export",
        ]
        for module_key in sorted(BUSINESS_MODULE_KEYS)
    }
)

ROLE_PERMISSION_PRESETS = [
    {
        "key": "phase1-data-foundation",
        "label": "第一阶段：数据底座管理员",
        "group": "阶段规划",
        "description": "林班、林权、图档关联、地图图层、成果入库和影像管理的第一阶段建设权限。",
        "menuModules": ["blocks", "rights", "linkages", "mapLayers", "imports", "imagery"],
        "permissions": [
            "forest.blocks.manage",
            "forest.rights.manage",
            "forest.linkages.manage",
            "map.layers.manage",
            "imports.forestBlocks.manage",
            "imagery.scenes.manage",
        ],
    },
    {
        "key": "phase2-operations",
        "label": "第二阶段：运营管护管理员",
        "group": "阶段规划",
        "description": "托管、基地、管护任务、作业、无人机、设备、病虫害和农资服务运营权限。",
        "menuModules": [
            "stewardshipAgreements",
            "franchiseBases",
            "maintenanceTasks",
            "workLogs",
            "droneTasks",
            "equipment",
            "pestWarnings",
            "materialServices",
            "plantProtection",
            "materials",
        ],
        "permissions": [
            "business.stewardshipAgreements.manage",
            "business.franchiseBases.manage",
            "business.maintenanceTasks.manage",
            "business.workLogs.manage",
            "business.droneTasks.manage",
            "business.equipment.manage",
            "business.pestWarnings.manage",
            "business.materialServices.manage",
            "business.plantProtection.manage",
            "business.materials.manage",
        ],
    },
    {
        "key": "phase3-decision",
        "label": "第三阶段：经营决策管理员",
        "group": "阶段规划",
        "description": "产量预测、采挖计划、收益测算、绩效看板和碳汇测算权限。",
        "menuModules": ["yieldForecasts", "harvestPlans", "incomeEstimates", "performanceDashboards", "carbonEstimates"],
        "permissions": [
            "business.yieldForecasts.manage",
            "business.harvestPlans.manage",
            "business.incomeEstimates.manage",
            "business.performanceDashboards.manage",
            "business.carbonEstimates.manage",
        ],
    },
    {
        "key": "phase4-industry-platform",
        "label": "第四阶段：产业平台管理员",
        "group": "阶段规划",
        "description": "交易撮合、物流溯源、二维码、供应链金融、价格指数和移动端服务权限。",
        "menuModules": [
            "tradeMatches",
            "logisticsTraces",
            "productQrcodes",
            "supplyChainFinance",
            "priceIndexes",
            "mobileServiceChannels",
        ],
        "permissions": [
            "business.tradeMatches.manage",
            "business.logisticsTraces.manage",
            "business.productQrcodes.manage",
            "business.supplyChainFinance.manage",
            "business.priceIndexes.manage",
            "business.mobileServiceChannels.manage",
        ],
    },
    {
        "key": "business-subjects",
        "label": "经营主体管理",
        "group": "业务角色",
        "description": "竹农、合作社、竹企和政策法规等主体服务权限。",
        "menuModules": ["farmers", "cooperatives", "enterprises", "policies"],
        "permissions": [
            "business.farmers.manage",
            "business.cooperatives.manage",
            "business.enterprises.manage",
            "business.policies.manage",
        ],
    },
    {
        "key": "system-admin",
        "label": "系统与权限管理员",
        "group": "系统角色",
        "description": "角色、用户和部署诊断权限，适合平台管理员配置权限边界。",
        "menuModules": ["roles", "users", "deployment"],
        "permissions": ["system.roles.manage", "system.users.manage", "system.deployment.view"],
    },
]

PERMISSION_CLOSURES = [
    {
        "key": "phase1-import-acceptance-loop",
        "label": "成果入库与验收操作闭环",
        "group": "第一阶段分工闭环",
        "description": "面向入库员、质检员和验收员，只开放导入、审核、质检、验收和交付材料导出，不包含删除、回滚、恢复等高危操作。",
        "menuModules": ["imports"],
        "permissions": [
            "imports.forestBlocks.view",
            "imports.forestBlocks.create",
            "imports.forestBlocks.review",
            "imports.forestBlocks.quality",
            "imports.forestBlocks.acceptance",
            "imports.forestBlocks.export",
        ],
        "omittedPermissions": [
            "imports.forestBlocks.manage",
            "imports.forestBlocks.rollback",
            "imports.forestBlocks.delete",
            "imports.forestBlocks.restore",
        ],
        "workflowEndpoints": [
            "/api/imports/forest-blocks",
            "/api/imports/forest-blocks/batches",
            "/api/imports/forest-blocks/operation-queue",
            "/api/imports/forest-blocks/quality-issues",
            "/api/imports/{batch_id}/review",
            "/api/imports/{batch_id}/acceptance",
            "/api/imports/{batch_id}/report.json",
            "/api/imports/{batch_id}/errors.csv",
            "/api/imports/{batch_id}/acceptance-receipt.json",
            "/api/imports/{batch_id}/delivery-package-receipt.json",
        ],
    },
    {
        "key": "phase1-imagery-delivery-loop",
        "label": "影像入库与交付操作闭环",
        "group": "第一阶段分工闭环",
        "description": "面向影像目录和交付人员，只开放影像入库、元数据编辑、质检处理、交付确认和交付材料导出。",
        "menuModules": ["imagery"],
        "permissions": [
            "imagery.scenes.view",
            "imagery.scenes.create",
            "imagery.scenes.update",
            "imagery.scenes.quality",
            "imagery.scenes.delivery",
            "imagery.scenes.export",
        ],
        "omittedPermissions": [
            "imagery.scenes.manage",
            "imagery.scenes.delete",
            "imagery.scenes.restore",
            "imagery.scenes.archive",
        ],
        "workflowEndpoints": [
            "/api/scenes",
            "/api/scenes/upload",
            "/api/scenes/register",
            "/api/scenes/operation-queue",
            "/api/scenes/quality-issues",
            "/api/scenes/{scene_id}",
            "/api/scenes/{scene_id}/delivery",
            "/api/scenes/{scene_id}/delivery-receipt.json",
            "/api/scenes/{scene_id}/publication-receipt.json",
        ],
    },
    {
        "key": "phase1-layer-publishing-loop",
        "label": "成果影像图层发布闭环",
        "group": "第一阶段分工闭环",
        "description": "面向地图发布人员，开放成果批次挂接、影像发布和地图图层创建、更新、发布、导出，不包含图层删除和恢复。",
        "menuModules": ["imports", "imagery", "mapLayers"],
        "permissions": [
            "imports.forestBlocks.view",
            "imports.sceneLayers.link",
            "imagery.scenes.view",
            "imagery.layers.publish",
            "map.layers.view",
            "map.layers.create",
            "map.layers.update",
            "map.layers.publish",
            "map.layers.export",
        ],
        "omittedPermissions": [
            "imports.forestBlocks.manage",
            "imports.forestBlocks.rollback",
            "imports.forestBlocks.delete",
            "imports.forestBlocks.restore",
            "imagery.scenes.manage",
            "imagery.scenes.delete",
            "imagery.scenes.restore",
            "map.layers.manage",
            "map.layers.delete",
            "map.layers.restore",
        ],
        "workflowEndpoints": [
            "/api/imports/{batch_id}/publish-readiness",
            "/api/imports/{batch_id}/link-scene-layer",
            "/api/scenes/{scene_id}/publish-layer",
            "/api/scenes/operation-queue",
            "/api/map-layers",
            "/api/map-layers/{record_id}",
            "/api/map-layers/{record_id}/publish",
            "/api/map-layers/{record_id}/publication-receipt.json",
            "/api/map-layers/events.csv",
            "/api/map-layers/dashboard",
        ],
    },
    {
        "key": "phase1-delivery-loop",
        "label": "成果入库与影像发布闭环",
        "group": "第一阶段闭环",
        "description": "把成果入库、影像目录和地图图层发布放在同一个权限配置包里，支撑大屏真实数据交付。",
        "menuModules": ["imports", "imagery", "mapLayers"],
        "permissions": [
            "imports.forestBlocks.manage",
            "imagery.scenes.manage",
            "map.layers.manage",
        ],
        "workflowEndpoints": [
            "/api/imports/forest-blocks/workflow-summary",
            "/api/imports/forest-blocks/operation-queue",
            "/api/scenes/workflow-summary",
            "/api/scenes/operation-queue",
            "/api/imports/forest-blocks/delivery-packages",
            "/api/imports/{batch_id}/delivery-package-receipt.json",
            "/api/map-layers/dashboard",
        ],
    },
    {
        "key": "identity-access-loop",
        "label": "权限菜单与账号配置闭环",
        "group": "第一阶段闭环",
        "description": "把角色、账号和部署诊断放在同一个权限配置包里，便于后续按菜单模块配置权限边界。",
        "menuModules": ["roles", "users", "deployment"],
        "permissions": ["system.roles.manage", "system.users.manage", "system.deployment.view"],
        "workflowEndpoints": [
            "/api/admin/permission-catalog",
            "/api/admin/roles",
            "/api/admin/roles/operation-queue",
            "/api/admin/users",
            "/api/admin/users/operation-queue",
            "/api/health",
        ],
    },
]


def permission_implications_payload() -> dict[str, list[str]]:
    return {key: list(values) for key, values in sorted(MANAGE_PERMISSION_IMPLICATIONS.items())}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def postgis_connect():
    try:
        import psycopg
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"admin roles PostGIS database requires psycopg. {exc}") from exc

    try:
        return psycopg.connect(get_settings().database_url)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="admin roles PostGIS database is unavailable") from exc


def datetime_to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def serializable_json(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, ensure_ascii=False)


def mysql_datetime(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value or None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def normalize_postgis_role_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
    else:
        source = dict(zip(POSTGIS_SELECT_COLUMNS, row))

    role: dict[str, Any] = {}
    for db_field, api_field in DB_TO_API_FIELD.items():
        value = source.get(db_field)
        if db_field in {"permissions", "menu_modules"}:
            value = json_value(value, [])
        elif db_field in {"data_scopes", "properties"}:
            value = json_value(value, {})
        elif db_field in {"created_at", "updated_at", "deleted_at"}:
            value = datetime_to_iso(value)
        role[api_field] = value
    role.setdefault("permissions", [])
    role.setdefault("menuModules", [])
    role.setdefault("dataScopes", {})
    role.setdefault("properties", {})
    return role


def compact_list(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


class AdminRoleBase(BaseModel):
    roleCode: str = Field(min_length=1)
    name: str = Field(min_length=1)
    status: str | None = "active"
    permissions: list[str] = Field(default_factory=list)
    menuModules: list[str] = Field(default_factory=list)
    dataScopes: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("permissions", "menuModules", mode="after")
    @classmethod
    def normalize_list(cls, values: list[str]) -> list[str]:
        return compact_list(values)


class AdminRoleIn(AdminRoleBase):
    model_config = {"extra": "forbid"}


class AdminRolePatch(BaseModel):
    name: str | None = None
    status: str | None = None
    permissions: list[str] | None = None
    menuModules: list[str] | None = None
    dataScopes: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None

    @field_validator("permissions", "menuModules", mode="after")
    @classmethod
    def normalize_patch_list(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else compact_list(values)

    model_config = {"extra": "forbid"}


class RolePreviewRequest(BaseModel):
    permissions: list[str] = Field(default_factory=list)
    menuModules: list[str] = Field(default_factory=list)

    @field_validator("permissions", "menuModules", mode="after")
    @classmethod
    def normalize_preview_list(cls, values: list[str]) -> list[str]:
        return compact_list(values)

    model_config = {"extra": "forbid"}


class AdminRoleOut(AdminRoleBase):
    id: str
    createdAt: str
    updatedAt: str
    deletedAt: str | None = None


class RoleFilters(BaseModel):
    q: str = ""
    status: str = ""
    permission: str = ""
    menuModule: str = ""
    includeDeleted: bool = False
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


def normalize_role(payload: dict[str, Any]) -> dict[str, Any]:
    role = dict(payload)
    timestamp = now_iso()
    role.setdefault("id", str(uuid.uuid4()))
    role.setdefault("createdAt", timestamp)
    role["updatedAt"] = timestamp
    role.setdefault("deletedAt", None)
    role["permissions"] = compact_list(role.get("permissions"))
    role["menuModules"] = compact_list(role.get("menuModules"))
    role.setdefault("status", "active")
    role.setdefault("dataScopes", {})
    role.setdefault("properties", {})
    return role


ROLE_AUDIT_EVENT_LIMIT = 100


def properties_without_audit(properties: dict[str, Any] | None) -> dict[str, Any]:
    clean = dict(properties or {})
    clean.pop("auditEvents", None)
    return clean


def role_audit_snapshot(role: dict[str, Any]) -> dict[str, Any]:
    return {
        "roleCode": role.get("roleCode") or "",
        "name": role.get("name") or "",
        "status": role.get("status") or "active",
        "permissions": list(role.get("permissions") or []),
        "menuModules": list(role.get("menuModules") or []),
        "dataScopes": dict(role.get("dataScopes") or {}),
        "properties": properties_without_audit(role.get("properties") or {}),
        "deletedAt": role.get("deletedAt"),
    }


def role_changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_snapshot = role_audit_snapshot(before)
    after_snapshot = role_audit_snapshot(after)
    fields = ["name", "status", "permissions", "menuModules", "dataScopes", "properties", "deletedAt"]
    return sorted(field for field in fields if before_snapshot.get(field) != after_snapshot.get(field))


def existing_role_audit_events(*roles: dict[str, Any] | None) -> list[dict[str, Any]]:
    for role in roles:
        properties = role.get("properties") if isinstance(role, dict) else {}
        events = properties.get("auditEvents") if isinstance(properties, dict) else None
        if isinstance(events, list):
            return [event for event in events if isinstance(event, dict)]
    return []


def append_role_audit_event(
    role: dict[str, Any],
    action: str,
    context: AuthContext,
    *,
    before: dict[str, Any] | None = None,
    changed_fields: list[str] | None = None,
) -> dict[str, Any]:
    updated = dict(role)
    properties = dict(updated.get("properties") or {})
    events = existing_role_audit_events(before, updated)
    event: dict[str, Any] = {
        "at": now_iso(),
        "action": action,
        "actor": context.user,
        "roleCode": updated.get("roleCode") or "",
        "changedFields": changed_fields or [],
        "after": role_audit_snapshot(updated),
    }
    if before is not None:
        event["before"] = role_audit_snapshot(before)
    events.append(event)
    properties["auditEvents"] = events[-ROLE_AUDIT_EVENT_LIMIT:]
    updated["properties"] = properties
    return updated


def role_event_record(role: dict[str, Any], event: dict[str, Any], index: int) -> dict[str, Any]:
    after = event.get("after") if isinstance(event.get("after"), dict) else {}
    before = event.get("before") if isinstance(event.get("before"), dict) else {}
    changed_fields = event.get("changedFields") if isinstance(event.get("changedFields"), list) else []
    role_code = str(event.get("roleCode") or role.get("roleCode") or after.get("roleCode") or "")
    permissions = after.get("permissions") if isinstance(after.get("permissions"), list) else []
    menu_modules = after.get("menuModules") if isinstance(after.get("menuModules"), list) else []
    summary_bits = [str(event.get("action") or "-"), role_code]
    if changed_fields:
        summary_bits.append(", ".join(str(item) for item in changed_fields))
    if permissions:
        summary_bits.append(", ".join(str(item) for item in permissions))
    return {
        "eventId": f"{role.get('id') or role_code}:{index}",
        "roleId": str(role.get("id") or ""),
        "roleCode": role_code,
        "roleName": str(after.get("name") or role.get("name") or ""),
        "action": str(event.get("action") or ""),
        "actor": str(event.get("actor") or ""),
        "at": event.get("at") or "",
        "changedFields": [str(item) for item in changed_fields],
        "permissions": [str(item) for item in permissions],
        "menuModules": [str(item) for item in menu_modules],
        "before": before,
        "after": after,
        "summary": " | ".join(item for item in summary_bits if item),
    }


def role_event_matches(
    record: dict[str, Any],
    q: str = "",
    action: str = "",
    role_code: str = "",
) -> bool:
    if action and str(record.get("action") or "") != action:
        return False
    if role_code and str(record.get("roleCode") or "") != role_code:
        return False
    keyword = q.strip().lower()
    if not keyword:
        return True
    haystack = " ".join(
        [
            str(record.get("eventId") or ""),
            str(record.get("roleId") or ""),
            str(record.get("roleCode") or ""),
            str(record.get("roleName") or ""),
            str(record.get("action") or ""),
            str(record.get("actor") or ""),
            " ".join(record.get("changedFields") or []),
            " ".join(record.get("permissions") or []),
            " ".join(record.get("menuModules") or []),
            str(record.get("summary") or ""),
        ]
    ).lower()
    return keyword in haystack


def list_role_event_records(q: str = "", action: str = "", role_code: str = "") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for role in load_all_roles():
        properties = role.get("properties") if isinstance(role, dict) else {}
        audit_events = properties.get("auditEvents") if isinstance(properties, dict) else []
        for index, event in enumerate(audit_events or [], start=1):
            if isinstance(event, dict):
                records.append(role_event_record(role, event, index))
    matched = [
        record
        for record in records
        if role_event_matches(record, q=q, action=action, role_code=role_code)
    ]
    return sorted(
        matched,
        key=lambda item: (str(item.get("at") or ""), str(item.get("eventId") or "")),
        reverse=True,
    )


def csv_cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value)


def csv_download_response(filename: str, columns: list[str], records: list[dict[str, Any]]) -> Response:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    for record in records:
        writer.writerow([csv_cell(record.get(column)) for column in columns])
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def safe_download_stem(value: str, fallback: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip("-")
    return stem or fallback


def json_download_response(filename: str, payload: dict[str, Any]) -> Response:
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def postgis_where(
    *,
    filters: RoleFilters | None = None,
    include_deleted: bool = False,
    role_id: str | None = None,
    role_code: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    if role_id:
        clauses.append("id = %s")
        params.append(role_id)
    if role_code:
        clauses.append("role_code = %s")
        params.append(role_code)
    if filters:
        if filters.status:
            clauses.append("status = %s")
            params.append(filters.status)
        if filters.permission:
            clauses.append("permissions ? %s")
            params.append(filters.permission)
        if filters.menuModule:
            clauses.append("menu_modules ? %s")
            params.append(filters.menuModule)
        if filters.q:
            query_text = f"%{filters.q}%"
            clauses.append(
                """
                (
                    role_code ILIKE %s
                    OR name ILIKE %s
                    OR permissions::text ILIKE %s
                    OR menu_modules::text ILIKE %s
                    OR properties::text ILIKE %s
                )
                """
            )
            params.extend([query_text, query_text, query_text, query_text, query_text])
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def fetch_roles_postgis(
    *,
    filters: RoleFilters | None = None,
    include_deleted: bool = False,
    role_id: str | None = None,
    role_code: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where_sql, params = postgis_where(
        filters=filters,
        include_deleted=include_deleted,
        role_id=role_id,
        role_code=role_code,
    )
    sql = f"{POSTGIS_SELECT_SQL}{where_sql} ORDER BY updated_at DESC, role_code"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_role_row(row) for row in cur.fetchall()]


def count_roles_postgis(filters: RoleFilters) -> int:
    where_sql, params = postgis_where(filters=filters, include_deleted=filters.includeDeleted)
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM admin_roles{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def first_role_postgis(
    *,
    role_id: str | None = None,
    role_code: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    items = fetch_roles_postgis(
        role_id=role_id,
        role_code=role_code,
        include_deleted=include_deleted,
        limit=1,
    )
    return items[0] if items else None


def postgis_role_values(role: dict[str, Any]) -> tuple[Any, ...]:
    return (
        role.get("id"),
        role.get("roleCode"),
        role.get("name"),
        role.get("status"),
        serializable_json(role.get("permissions"), []),
        serializable_json(role.get("menuModules"), []),
        serializable_json(role.get("dataScopes"), {}),
        serializable_json(role.get("properties"), {}),
        role.get("createdAt"),
        role.get("updatedAt"),
        role.get("deletedAt"),
    )


def execute_upsert_role_postgis(cur: Any, role: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO admin_roles (
            id,
            role_code,
            name,
            status,
            permissions,
            menu_modules,
            data_scopes,
            properties,
            created_at,
            updated_at,
            deleted_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s::jsonb,
            %s::jsonb,
            %s::jsonb,
            %s::jsonb,
            %s,
            %s,
            %s
        )
        ON CONFLICT (id) DO UPDATE SET
            role_code = EXCLUDED.role_code,
            name = EXCLUDED.name,
            status = EXCLUDED.status,
            permissions = EXCLUDED.permissions,
            menu_modules = EXCLUDED.menu_modules,
            data_scopes = EXCLUDED.data_scopes,
            properties = EXCLUDED.properties,
            updated_at = EXCLUDED.updated_at,
            deleted_at = EXCLUDED.deleted_at
        """,
        postgis_role_values(role),
    )


def upsert_roles_postgis(roles: list[dict[str, Any]]) -> None:
    if not roles:
        return
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            for role in roles:
                execute_upsert_role_postgis(cur, role)
        conn.commit()


def mysql_where(
    *,
    filters: RoleFilters | None = None,
    include_deleted: bool = False,
    role_id: str | None = None,
    role_code: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_deleted:
        clauses.append("ar.deleted_at IS NULL")
    if role_id:
        clauses.append("ar.id = %s")
        params.append(role_id)
    if role_code:
        clauses.append("ar.role_code = %s")
        params.append(role_code)
    if filters:
        if filters.status:
            clauses.append("ar.status = %s")
            params.append(filters.status)
        if filters.permission:
            clauses.append(
                "EXISTS (SELECT 1 FROM admin_role_permissions arp "
                "WHERE arp.admin_role_id = ar.id AND arp.permission_code = %s)"
            )
            params.append(filters.permission)
        if filters.menuModule:
            clauses.append(
                "EXISTS (SELECT 1 FROM admin_role_menu_modules arm "
                "WHERE arm.admin_role_id = ar.id AND arm.module_key = %s)"
            )
            params.append(filters.menuModule)
        if filters.q:
            query_text = f"%{filters.q}%"
            clauses.append(
                "(ar.role_code LIKE %s OR ar.name LIKE %s OR CAST(ar.properties AS CHAR) LIKE %s "
                "OR EXISTS (SELECT 1 FROM admin_role_permissions arp "
                "WHERE arp.admin_role_id = ar.id AND arp.permission_code LIKE %s) "
                "OR EXISTS (SELECT 1 FROM admin_role_menu_modules arm "
                "WHERE arm.admin_role_id = ar.id AND arm.module_key LIKE %s))"
            )
            params.extend([query_text] * 5)
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def fetch_roles_mysql(
    *,
    filters: RoleFilters | None = None,
    include_deleted: bool = False,
    role_id: str | None = None,
    role_code: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where_sql, params = mysql_where(
        filters=filters,
        include_deleted=include_deleted,
        role_id=role_id,
        role_code=role_code,
    )
    sql = f"{MYSQL_SELECT_SQL}{where_sql} ORDER BY ar.updated_at DESC, ar.role_code"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_role_row(row) for row in cur.fetchall()]


def count_roles_mysql(filters: RoleFilters) -> int:
    where_sql, params = mysql_where(filters=filters, include_deleted=filters.includeDeleted)
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM admin_roles ar{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def first_role_mysql(
    *,
    role_id: str | None = None,
    role_code: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    items = fetch_roles_mysql(
        role_id=role_id,
        role_code=role_code,
        include_deleted=include_deleted,
        limit=1,
    )
    return items[0] if items else None


def execute_upsert_role_mysql(cur: Any, role: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO admin_roles (
            id, role_code, name, status, data_scopes, properties,
            created_at, updated_at, deleted_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            role_code = VALUES(role_code),
            name = VALUES(name),
            status = VALUES(status),
            data_scopes = VALUES(data_scopes),
            properties = VALUES(properties),
            updated_at = VALUES(updated_at),
            deleted_at = VALUES(deleted_at)
        """,
        (
            role.get("id"),
            role.get("roleCode"),
            role.get("name"),
            role.get("status"),
            serializable_json(role.get("dataScopes"), {}),
            serializable_json(role.get("properties"), {}),
            mysql_datetime(role.get("createdAt")),
            mysql_datetime(role.get("updatedAt")),
            mysql_datetime(role.get("deletedAt")),
        ),
    )
    role_id = str(role.get("id") or "")
    cur.execute("DELETE FROM admin_role_permissions WHERE admin_role_id = %s", (role_id,))
    permissions = compact_list(role.get("permissions"))
    if permissions:
        cur.executemany(
            "INSERT INTO admin_role_permissions (admin_role_id, permission_code) VALUES (%s, %s)",
            [(role_id, permission) for permission in permissions],
        )
    cur.execute("DELETE FROM admin_role_menu_modules WHERE admin_role_id = %s", (role_id,))
    menu_modules = compact_list(role.get("menuModules"))
    if menu_modules:
        cur.executemany(
            "INSERT INTO admin_role_menu_modules (admin_role_id, module_key) VALUES (%s, %s)",
            [(role_id, module_key) for module_key in menu_modules],
        )


def upsert_roles_mysql(roles: list[dict[str, Any]]) -> None:
    if not roles:
        return
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            for role in roles:
                execute_upsert_role_mysql(cur, role)
        conn.commit()


def load_all_roles() -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_roles_mysql(include_deleted=True)
    if use_postgis():
        return fetch_roles_postgis(include_deleted=True)
    return load_json_records(admin_roles_json_path())


def load_roles() -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_roles_mysql()
    if use_postgis():
        return fetch_roles_postgis()
    return [role for role in load_all_roles() if not role.get("deletedAt")]


def save_roles(roles: list[dict[str, Any]]) -> None:
    if use_mysql():
        upsert_roles_mysql(roles)
        return
    if use_postgis():
        upsert_roles_postgis(roles)
        return
    with database.JSON_STORE_LOCK:
        save_json_records(admin_roles_json_path(), roles)


def text_matches(role: dict[str, Any], q: str) -> bool:
    if not q:
        return True
    haystack = " ".join(
        [
            str(role.get("roleCode") or ""),
            str(role.get("name") or ""),
            " ".join(role.get("permissions") or []),
            " ".join(role.get("menuModules") or []),
            json.dumps(role.get("properties") or {}, ensure_ascii=False),
        ]
    ).lower()
    return q.lower() in haystack


def role_matches(role: dict[str, Any], filters: RoleFilters) -> bool:
    if filters.status and role.get("status") != filters.status:
        return False
    if filters.permission and filters.permission not in (role.get("permissions") or []):
        return False
    if filters.menuModule and filters.menuModule not in (role.get("menuModules") or []):
        return False
    return text_matches(role, filters.q)


def filter_params(
    q: str = Query(default=""),
    status: str = Query(default=""),
    permission: str = Query(default=""),
    menuModule: str = Query(default=""),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> RoleFilters:
    return RoleFilters(
        q=q,
        status=status,
        permission=permission,
        menuModule=menuModule,
        includeDeleted=includeDeleted,
        limit=limit,
        offset=offset,
    )


def find_role(role_id: str) -> dict[str, Any] | None:
    if use_mysql():
        return first_role_mysql(role_id=role_id)
    if use_postgis():
        return first_role_postgis(role_id=role_id)
    for role in load_roles():
        if str(role.get("id")) == str(role_id):
            return role
    return None


def role_by_code(role_code: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    if use_mysql():
        return first_role_mysql(role_code=role_code, include_deleted=include_deleted)
    if use_postgis():
        return first_role_postgis(role_code=role_code, include_deleted=include_deleted)
    source_roles = load_all_roles() if include_deleted else load_roles()
    for role in source_roles:
        if str(role.get("roleCode")) == str(role_code):
            return role
    return None


def is_builtin_or_direct_permission_role(code: str) -> bool:
    builtin_roles = {"admin", "operator", "gis-admin"}
    direct_permissions = {item["code"] for item in permission_catalog()}
    return code in builtin_roles or code in direct_permissions


def unknown_role_entries(role_codes: list[str] | set[str]) -> list[dict[str, str]]:
    unknown_roles: list[dict[str, str]] = []
    seen: set[str] = set()
    for role_code in role_codes:
        code = str(role_code or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        if is_builtin_or_direct_permission_role(code):
            continue
        if role_by_code(code, include_deleted=True) is not None:
            continue
        unknown_roles.append({"roleCode": code, "label": code})
    return unknown_roles


def invalid_role_entries(role_codes: list[str] | set[str]) -> list[dict[str, str]]:
    invalid_roles: list[dict[str, str]] = []
    seen: set[str] = set()
    for role_code in role_codes:
        code = str(role_code or "").strip()
        if not code or code in seen or is_builtin_or_direct_permission_role(code):
            continue
        seen.add(code)
        role = role_by_code(code, include_deleted=True)
        if role is None:
            continue
        status = str(role.get("status") or "active")
        if role.get("deletedAt") or status == "deleted":
            invalid_roles.append(
                {
                    "roleCode": code,
                    "label": str(role.get("name") or code),
                    "status": "deleted",
                    "reason": "deleted",
                }
            )
            continue
        if status not in ("active", ""):
            invalid_roles.append(
                {
                    "roleCode": code,
                    "label": str(role.get("name") or code),
                    "status": status,
                    "reason": "inactive",
                }
            )
    return invalid_roles


def union_ordered(items: list[str], values: list[str]) -> list[str]:
    seen = set(items)
    for value in values:
        if value not in seen:
            seen.add(value)
            items.append(value)
    return items


def permissions_for_roles(role_codes: set[str] | list[str]) -> list[str]:
    permissions: list[str] = []
    for code in role_codes:
        role = role_by_code(str(code))
        if role is None or role.get("status") not in ("active", None, ""):
            continue
        union_ordered(permissions, role.get("permissions") or [])
    return permissions


def merge_scope_values(existing: list[str], value: Any) -> list[str]:
    return union_ordered(existing, sorted(split_header_list(value)))


def data_scopes_for_roles(role_codes: set[str] | list[str]) -> dict[str, list[str]]:
    scopes: dict[str, list[str]] = {}
    for code in role_codes:
        role = role_by_code(str(code))
        if role is None or role.get("status") not in ("active", None, ""):
            continue
        role_scopes = role.get("dataScopes") or {}
        if not isinstance(role_scopes, dict):
            continue
        for key, value in role_scopes.items():
            scopes.setdefault(str(key), [])
            scopes[str(key)] = merge_scope_values(scopes[str(key)], value)
    return scopes


def direct_permission_codes(role_codes: set[str] | list[str]) -> list[str]:
    known_permissions = {item["code"] for item in permission_catalog()}
    return [code for code in sorted(str(item) for item in role_codes) if code in known_permissions]


def expand_permission_codes(permission_codes: list[str] | set[str]) -> list[str]:
    expanded: list[str] = []
    for code in permission_codes:
        compact = str(code or "").strip()
        if not compact:
            continue
        union_ordered(expanded, [compact])
        union_ordered(expanded, MANAGE_PERMISSION_IMPLICATIONS.get(compact, []))
    return expanded


def permission_satisfied_by(permission_set: set[str], permission: str) -> bool:
    required = str(permission or "").strip()
    if not required:
        return True
    if required in permission_set:
        return True
    return any(
        manage_permission in permission_set and required in implied_permissions
        for manage_permission, implied_permissions in MANAGE_PERMISSION_IMPLICATIONS.items()
    )


def role_codes_for_context(context: AuthContext) -> list[str]:
    roles = sorted(str(role) for role in context.roles if str(role).strip())
    try:
        from .admin_users import roles_for_user

        union_ordered(roles, roles_for_user(context.user))
    except Exception:
        pass
    return roles


def effective_permissions_for_context(context: AuthContext) -> list[str]:
    if has_admin_role(context):
        return [item["code"] for item in permission_catalog()]
    role_codes = role_codes_for_context(context)
    if "operator" in role_codes or "gis-admin" in role_codes:
        return [item["code"] for item in permission_catalog()]
    permissions = permissions_for_roles(role_codes)
    union_ordered(permissions, direct_permission_codes(role_codes))
    return expand_permission_codes(permissions)


def effective_menu_modules_for_context(context: AuthContext) -> list[str]:
    if has_admin_role(context):
        return [module["key"] for module in ADMIN_MENU_MODULES]
    role_codes = role_codes_for_context(context)
    if "operator" in role_codes or "gis-admin" in role_codes:
        return [module["key"] for module in ADMIN_MENU_MODULES]
    modules: list[str] = []
    for code in role_codes:
        role = role_by_code(str(code))
        if role is None or role.get("status") not in ("active", None, ""):
            continue
        union_ordered(modules, role.get("menuModules") or [])
    direct_permissions = direct_permission_codes(role_codes)
    if direct_permissions:
        permission_set = set(expand_permission_codes(direct_permissions))
        union_ordered(
            modules,
            [
                module["key"]
                for module in ADMIN_MENU_MODULES
                if permission_satisfied_by(permission_set, str(module.get("permission") or ""))
            ],
        )
    return menu_modules_allowed_by_permissions(modules, effective_permissions_for_context(context))


def effective_data_scopes_for_context(context: AuthContext) -> dict[str, list[str]]:
    scopes = data_scopes_for_roles(role_codes_for_context(context))
    try:
        from .admin_users import data_scopes_for_user

        for key, values in data_scopes_for_user(context.user).items():
            scopes.setdefault(key, [])
            scopes[key] = merge_scope_values(scopes[key], values)
    except Exception:
        pass
    areas = sorted(effective_areas(context))
    if areas:
        scopes["areas"] = areas
    if context.projects:
        role_projects = set(scopes.get("projects") or [])
        request_projects = set(context.projects)
        if role_projects and "*" not in role_projects and "*" not in request_projects:
            scopes["projects"] = sorted(role_projects & request_projects)
        else:
            scopes["projects"] = sorted(role_projects or request_projects)
    return {key: value for key, value in scopes.items() if value}


def has_permission(context: AuthContext, permission: str) -> bool:
    if has_admin_role(context):
        return True
    role_codes = role_codes_for_context(context)
    if "operator" in role_codes or "gis-admin" in role_codes:
        return True
    if not role_codes:
        return False
    permissions = permissions_for_roles(role_codes)
    union_ordered(permissions, direct_permission_codes(role_codes))
    return permission_satisfied_by(set(permissions), permission)


def require_permission(context: AuthContext, permission: str) -> None:
    if has_permission(context, permission):
        return
    raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def require_any_permission(context: AuthContext, permissions: list[str]) -> None:
    if any(has_permission(context, permission) for permission in permissions):
        return
    raise HTTPException(status_code=403, detail=f"One permission required: {', '.join(permissions)}")


def permission_api_scopes(code: str, module_key: str = "") -> list[str]:
    scopes = list(PERMISSION_API_SCOPES.get(code) or [])
    if scopes:
        return scopes
    business_permission = parse_business_permission(code)
    if business_permission:
        business_module_key, business_action = business_permission
        business_scopes = business_permission_api_scopes(business_module_key, business_action)
        if business_scopes:
            return business_scopes
    module = module_catalog_by_key().get(module_key)
    if module and str(module.get("permission") or "") == code:
        return list(module.get("apiScopes") or [])
    return []


def permission_dependency_payload(code: str) -> dict[str, Any]:
    rule = PERMISSION_DEPENDENCY_RULES.get(str(code or "").strip()) or {}
    requires_any_permissions: list[list[str]] = []
    for group in rule.get("requiresAnyPermissions") or []:
        values = compact_list(list(group or []))
        if values:
            requires_any_permissions.append(values)
    return {
        "requiresAllPermissions": compact_list(list(rule.get("requiresAllPermissions") or [])),
        "requiresAnyPermissions": requires_any_permissions,
        "dependencyReason": str(rule.get("dependencyReason") or ""),
    }


def permission_catalog_entry(item: dict[str, Any]) -> dict[str, Any]:
    entry = dict(item)
    code = str(entry.get("code") or "")
    entry["apiScopes"] = permission_api_scopes(code, str(entry.get("module") or ""))
    entry.update(permission_dependency_payload(code))
    return entry


def business_permission_catalog_entries() -> list[dict[str, Any]]:
    modules = module_catalog_by_key()
    entries: list[dict[str, Any]] = []
    for module_key in sorted(BUSINESS_MODULE_KEYS):
        module = modules.get(module_key)
        if not module:
            continue
        for action, action_label in BUSINESS_ACTION_PERMISSIONS:
            entries.append(
                {
                    "code": f"business.{module_key}.{action}",
                    "label": f"{module['label']}{action_label}",
                    "module": module_key,
                }
            )
    return entries


def permission_catalog() -> list[dict[str, Any]]:
    seen: set[str] = set()
    permissions: list[dict[str, Any]] = []
    for item in [*EXTRA_PERMISSIONS, *business_permission_catalog_entries()]:
        if item["code"] in seen:
            continue
        seen.add(item["code"])
        permissions.append(permission_catalog_entry(item))
    for module in ADMIN_MENU_MODULES:
        code = module.get("permission") or ""
        if not code or code in seen:
            continue
        seen.add(code)
        permissions.append(
            permission_catalog_entry({"code": code, "label": module["label"], "module": module["key"]})
        )
    return permissions


def module_catalog_by_key() -> dict[str, dict[str, str]]:
    return {module["key"]: module for module in ADMIN_MENU_MODULES}


def menu_modules_allowed_by_permissions(menu_modules: list[str], permissions: list[str]) -> list[str]:
    modules_by_key = module_catalog_by_key()
    permission_set = set(permissions)
    allowed: list[str] = []
    for key in menu_modules:
        module = modules_by_key.get(key)
        if not module:
            continue
        required_permission = module.get("permission") or ""
        if required_permission and not permission_satisfied_by(permission_set, required_permission):
            continue
        allowed.append(key)
    return allowed


def permission_matrix() -> list[dict[str, Any]]:
    permissions = permission_catalog()
    permissions_by_module: dict[str, list[str]] = {}
    for permission in permissions:
        module_key = permission.get("module") or ""
        if not module_key:
            continue
        permissions_by_module.setdefault(module_key, [])
        if permission["code"] not in permissions_by_module[module_key]:
            permissions_by_module[module_key].append(permission["code"])

    group_order: list[str] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for module in ADMIN_MENU_MODULES:
        group = module["group"]
        if group not in grouped:
            grouped[group] = []
            group_order.append(group)
        module_permissions = list(permissions_by_module.get(module["key"], []))
        module_permission = module.get("permission") or ""
        if module_permission and module_permission not in module_permissions:
            module_permissions.insert(0, module_permission)
        module_entry = {**module, "permissions": module_permissions}
        module_entry["permissionEntries"] = module_permission_entries(module_entry)
        grouped[group].append(module_entry)

    return [{"group": group, "modules": grouped[group]} for group in group_order]


def permission_catalog_export_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    preset_refs = permission_preset_refs_by_code()
    for group in permission_matrix():
        group_name = group.get("group") or ""
        for module in group.get("modules") or []:
            module_key = module.get("key") or ""
            module_label = module.get("label") or module_key
            module_permission = module.get("permission") or ""
            for entry in module.get("permissionEntries") or []:
                code = entry.get("code") or ""
                implied_by = [
                    manage_permission
                    for manage_permission, implied_permissions in MANAGE_PERMISSION_IMPLICATIONS.items()
                    if code in implied_permissions
                ]
                preset_ref = preset_refs.get(code) or {"keys": [], "labels": []}
                records.append(
                    {
                        "group": group_name,
                        "moduleKey": module_key,
                        "moduleLabel": module_label,
                        "href": module.get("href") or "",
                        "entryPermission": module_permission,
                        "permissionCode": code,
                        "permissionLabel": entry.get("label") or code,
                        "permissionKind": entry.get("kind") or "",
                        "permissionKindLabel": entry.get("kindLabel") or "",
                        "apiScopes": module.get("apiScopes") or [],
                        "permissionApiScopes": entry.get("apiScopes") or [],
                        "requiresAllPermissions": entry.get("requiresAllPermissions") or [],
                        "requiresAnyPermissions": entry.get("requiresAnyPermissions") or [],
                        "dependencyReason": entry.get("dependencyReason") or "",
                        "impliedBy": implied_by,
                        "presetKeys": preset_ref["keys"],
                        "presetLabels": preset_ref["labels"],
                    }
                )
    return records


def permission_catalog_coverage() -> dict[str, Any]:
    permissions = permission_catalog()
    matrix = permission_matrix()
    known_modules = {module["key"] for module in ADMIN_MENU_MODULES}
    known_codes = {permission["code"] for permission in permissions}
    matrix_modules = [module for group in matrix for module in group.get("modules", [])]
    permission_entries = [entry for module in matrix_modules for entry in module.get("permissionEntries", [])]
    missing_page_permissions = [
        {
            "module": module["key"],
            "label": module["label"],
            "permission": module.get("permission") or "",
        }
        for module in ADMIN_MENU_MODULES
        if module.get("permission") and module.get("permission") not in known_codes
    ]
    permissions_without_known_module = [
        dict(permission)
        for permission in permissions
        if permission.get("module") and permission.get("module") not in known_modules
    ]
    missing_manage_implications = [
        {"managePermission": manage_permission, "permission": permission}
        for manage_permission, implied_permissions in MANAGE_PERMISSION_IMPLICATIONS.items()
        for permission in implied_permissions
        if permission not in known_codes
    ]
    permission_dependency_targets = [
        {"permission": permission, "dependency": dependency}
        for permission, rule in PERMISSION_DEPENDENCY_RULES.items()
        for dependency in [
            *compact_list(list(rule.get("requiresAllPermissions") or [])),
            *[
                value
                for group in rule.get("requiresAnyPermissions") or []
                for value in compact_list(list(group or []))
            ],
        ]
    ]
    missing_permission_dependency_targets = [
        item for item in permission_dependency_targets if item["dependency"] not in known_codes
    ]
    issues = {
        "missingPagePermissions": missing_page_permissions,
        "permissionsWithoutKnownModule": permissions_without_known_module,
        "missingManageImplications": missing_manage_implications,
        "missingPermissionDependencyTargets": missing_permission_dependency_targets,
    }
    summary = {
        "menuModuleTotal": len(ADMIN_MENU_MODULES),
        "permissionTotal": len(permissions),
        "matrixModuleTotal": len(matrix_modules),
        "pagePermissionTotal": sum(1 for entry in permission_entries if entry.get("kind") == "page"),
        "actionPermissionTotal": sum(1 for entry in permission_entries if entry.get("kind") == "action"),
        "missingPagePermissions": len(missing_page_permissions),
        "permissionsWithoutKnownModule": len(permissions_without_known_module),
        "missingManageImplications": len(missing_manage_implications),
        "permissionDependencyRules": len(PERMISSION_DEPENDENCY_RULES),
        "missingPermissionDependencyTargets": len(missing_permission_dependency_targets),
    }
    risk_level = "ready"
    if missing_page_permissions or permissions_without_known_module:
        risk_level = "error"
    elif missing_manage_implications or missing_permission_dependency_targets:
        risk_level = "warning"
    return {"summary": summary, "issues": issues, "riskLevel": risk_level}


def permission_meta_by_code(code: str) -> dict[str, str]:
    permission = next((item for item in permission_catalog() if item["code"] == code), None)
    if permission:
        return dict(permission)
    return {"code": code, "label": code, "module": ""}


def permission_dependency_issues_for_set(permission_set: set[str]) -> list[dict[str, Any]]:
    modules_by_key = module_catalog_by_key()
    issues: list[dict[str, Any]] = []
    for code in sorted(permission_set):
        payload = permission_dependency_payload(code)
        requires_all = payload["requiresAllPermissions"]
        requires_any = payload["requiresAnyPermissions"]
        if not requires_all and not requires_any:
            continue
        missing_all = [
            permission
            for permission in requires_all
            if not permission_satisfied_by(permission_set, permission)
        ]
        missing_any = [
            group
            for group in requires_any
            if not any(permission_satisfied_by(permission_set, permission) for permission in group)
        ]
        if not missing_all and not missing_any:
            continue
        meta = permission_meta_by_code(code)
        module = modules_by_key.get(str(meta.get("module") or ""))
        issues.append(
            {
                **meta,
                "permissionCode": code,
                "permissionLabel": meta.get("label") or code,
                "moduleLabel": (module or {}).get("label") or meta.get("module") or "",
                "requiresAllPermissions": requires_all,
                "missingAllPermissions": missing_all,
                "requiresAnyPermissions": requires_any,
                "missingAnyPermissionGroups": missing_any,
                "dependencyReason": payload.get("dependencyReason") or "",
            }
        )
    return issues


def module_permission_entries(module: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    codes: list[str] = []
    module_permission = str(module.get("permission") or "")
    if module_permission:
        codes.append(module_permission)
    for permission in permission_catalog():
        if permission.get("module") == module.get("key"):
            codes.append(permission["code"])
    entries: list[dict[str, Any]] = []
    for code in codes:
        if not code or code in seen:
            continue
        seen.add(code)
        meta = permission_meta_by_code(code)
        kind = "page" if code == module_permission else "action"
        entries.append({**meta, "kind": kind, "kindLabel": "入口权限" if kind == "page" else "动作权限"})
    return entries


def role_draft_preview(menu_modules: list[str], permissions: list[str]) -> dict[str, Any]:
    permission_set = set(expand_permission_codes(permissions))
    modules_by_key = module_catalog_by_key()
    known_permission_codes = {item["code"] for item in permission_catalog()}
    effective_menu_modules: list[dict[str, Any]] = []
    blocked_menu_modules: list[dict[str, Any]] = []
    unknown_menu_modules: list[dict[str, str]] = []
    for key in menu_modules:
        module = modules_by_key.get(key)
        if not module:
            unknown_menu_modules.append({"key": key, "label": key})
            continue
        required_permission = str(module.get("permission") or "")
        missing_entry_permission = required_permission if required_permission and not permission_satisfied_by(permission_set, required_permission) else ""
        item = {**module, "missingEntryPermission": missing_entry_permission}
        if missing_entry_permission:
            blocked_menu_modules.append(item)
        else:
            effective_menu_modules.append(item)

    effective_module_keys = {module["key"] for module in effective_menu_modules}
    action_permission_coverage: list[dict[str, Any]] = []
    for module in effective_menu_modules:
        action_permissions = [item for item in module_permission_entries(module) if item["kind"] == "action"]
        if not action_permissions:
            continue
        action_permission_coverage.append(
            {
                **module,
                "grantedActionPermissions": [item for item in action_permissions if permission_satisfied_by(permission_set, item["code"])],
                "missingActionPermissions": [item for item in action_permissions if not permission_satisfied_by(permission_set, item["code"])],
            }
        )

    orphan_action_permissions: list[dict[str, Any]] = []
    unknown_permissions: list[dict[str, str]] = []
    for code in permissions:
        if code not in known_permission_codes:
            unknown_permissions.append({"code": code, "label": code, "module": ""})
            continue
        meta = permission_meta_by_code(code)
        module = modules_by_key.get(meta.get("module") or "")
        if not module:
            continue
        if code == module.get("permission") or meta.get("module") in effective_module_keys:
            continue
        orphan_action_permissions.append({**meta, "moduleLabel": module.get("label") or module.get("key")})

    permission_dependency_issues = permission_dependency_issues_for_set(permission_set)
    preview = {
        "menuModules": menu_modules,
        "permissions": permissions,
        "effectiveMenuModules": effective_menu_modules,
        "blockedMenuModules": blocked_menu_modules,
        "actionPermissionCoverage": action_permission_coverage,
        "orphanActionPermissions": orphan_action_permissions,
        "permissionDependencyIssues": permission_dependency_issues,
        "unknownMenuModules": unknown_menu_modules,
        "unknownPermissions": unknown_permissions,
    }
    summary = role_draft_preview_summary(preview)
    preview["summary"] = summary
    preview["riskLevel"] = role_draft_preview_risk_level(summary)
    return preview


def role_draft_preview_summary(preview: dict[str, Any]) -> dict[str, int]:
    action_permission_coverage = preview.get("actionPermissionCoverage") or []
    missing_action_permissions = sum(
        len(item.get("missingActionPermissions") or [])
        for item in action_permission_coverage
        if isinstance(item, dict)
    )
    return {
        "configuredMenuModules": len(preview.get("menuModules") or []),
        "configuredPermissions": len(preview.get("permissions") or []),
        "effectiveMenuModules": len(preview.get("effectiveMenuModules") or []),
        "blockedMenuModules": len(preview.get("blockedMenuModules") or []),
        "actionPermissionGroups": len(action_permission_coverage),
        "missingActionPermissions": missing_action_permissions,
        "orphanActionPermissions": len(preview.get("orphanActionPermissions") or []),
        "permissionDependencyIssues": len(preview.get("permissionDependencyIssues") or []),
        "unknownMenuModules": len(preview.get("unknownMenuModules") or []),
        "unknownPermissions": len(preview.get("unknownPermissions") or []),
    }


def role_draft_preview_risk_level(summary: dict[str, int]) -> str:
    if summary.get("blockedMenuModules") or summary.get("unknownMenuModules") or summary.get("unknownPermissions"):
        return "error"
    if summary.get("orphanActionPermissions") or summary.get("missingActionPermissions") or summary.get("permissionDependencyIssues"):
        return "warning"
    if summary.get("configuredMenuModules") or summary.get("configuredPermissions"):
        return "ready"
    return "empty"


ROLE_OPERATION_QUEUE_STAGES = [
    {
        "key": "blocked_roles",
        "label": "入口阻断角色",
        "description": "菜单入口缺少对应入口权限，角色保存或实际可见菜单存在阻断。",
        "tone": "danger",
        "requiredPermission": "system.roles.manage",
        "primaryActionLabel": "修复角色",
    },
    {
        "key": "review_roles",
        "label": "待复核角色",
        "description": "存在孤立动作权限、缺少动作权限或跨模块依赖缺口，需要业务复核。",
        "tone": "warning",
        "requiredPermission": "system.roles.manage",
        "primaryActionLabel": "复核权限",
    },
    {
        "key": "empty_roles",
        "label": "空配置角色",
        "description": "角色尚未配置菜单和权限，不能形成可用后台职责。",
        "tone": "review",
        "requiredPermission": "system.roles.manage",
        "primaryActionLabel": "配置角色",
    },
    {
        "key": "ready_roles",
        "label": "已闭环角色",
        "description": "菜单入口、权限、依赖关系已形成闭环，可导出权限回执。",
        "tone": "ready",
        "requiredPermission": "system.roles.export",
        "primaryActionLabel": "查看回执",
    },
]


def role_operation_stage_by_key(key: str) -> dict[str, str]:
    return next((stage for stage in ROLE_OPERATION_QUEUE_STAGES if stage["key"] == key), ROLE_OPERATION_QUEUE_STAGES[-1])


def role_operation_stage_key(preview: dict[str, Any]) -> str:
    risk_level = str(preview.get("riskLevel") or "")
    if risk_level == "error":
        return "blocked_roles"
    if risk_level == "warning":
        return "review_roles"
    if risk_level == "empty":
        return "empty_roles"
    return "ready_roles"


def role_operation_admin_href(role: dict[str, Any], lane_key: str) -> str:
    role_code = str(role.get("roleCode") or "")
    return f"admin-roles.html?roleQueue={quote(lane_key)}&roleCode={quote(role_code)}"


def role_operation_summary(role: dict[str, Any], preview: dict[str, Any]) -> str:
    summary = preview.get("summary") or {}
    risk_level = str(preview.get("riskLevel") or "")
    if risk_level == "error":
        unknown_total = (summary.get("unknownMenuModules") or 0) + (summary.get("unknownPermissions") or 0)
        return f"入口阻断 {summary.get('blockedMenuModules') or 0} 项，未知配置 {unknown_total} 项"
    if risk_level == "warning":
        return (
            f"孤立动作 {summary.get('orphanActionPermissions') or 0} 项，"
            f"缺少动作 {summary.get('missingActionPermissions') or 0} 项，"
            f"依赖缺口 {summary.get('permissionDependencyIssues') or 0} 项"
        )
    if risk_level == "empty":
        return "尚未配置菜单入口和权限动作"
    return f"已配置菜单 {summary.get('configuredMenuModules') or 0} 个，权限 {summary.get('configuredPermissions') or 0} 项"


def role_operation_queue_item(role: dict[str, Any], preview: dict[str, Any], lane: dict[str, str]) -> dict[str, Any]:
    summary = preview.get("summary") or {}
    lane_key = str(lane.get("key") or "")
    return {
        "itemType": "role",
        "roleId": role.get("id"),
        "roleCode": role.get("roleCode"),
        "name": role.get("name") or role.get("roleCode") or "",
        "status": role.get("status") or "active",
        "riskLevel": preview.get("riskLevel") or "",
        "summary": role_operation_summary(role, preview),
        "blockedMenuModuleCount": summary.get("blockedMenuModules") or 0,
        "missingActionPermissionCount": summary.get("missingActionPermissions") or 0,
        "unknownPermissionCount": summary.get("unknownPermissions") or 0,
        "unknownMenuModuleCount": summary.get("unknownMenuModules") or 0,
        "orphanActionPermissionCount": summary.get("orphanActionPermissions") or 0,
        "permissionDependencyIssueCount": summary.get("permissionDependencyIssues") or 0,
        "configuredMenuModuleCount": summary.get("configuredMenuModules") or 0,
        "configuredPermissionCount": summary.get("configuredPermissions") or 0,
        "updatedAt": role.get("updatedAt") or role.get("createdAt") or "",
        "adminHref": role_operation_admin_href(role, lane_key),
        "requiredPermission": lane.get("requiredPermission") or "system.roles.manage",
    }


def role_operation_queue_lane(stage: dict[str, str], lane_items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    return {
        "key": stage["key"],
        "label": stage["label"],
        "description": stage["description"],
        "tone": stage["tone"],
        "requiredPermission": stage["requiredPermission"],
        "primaryActionLabel": stage["primaryActionLabel"],
        "count": len(lane_items),
        "items": lane_items[:limit],
    }


def role_operation_queue(limit: int = 5) -> dict[str, Any]:
    lanes: dict[str, list[dict[str, Any]]] = {stage["key"]: [] for stage in ROLE_OPERATION_QUEUE_STAGES}
    for role in load_roles():
        preview = role_draft_preview(compact_list(role.get("menuModules") or []), compact_list(role.get("permissions") or []))
        stage_key = role_operation_stage_key(preview)
        stage = role_operation_stage_by_key(stage_key)
        lanes[stage_key].append(role_operation_queue_item(role, preview, stage))

    for lane_items in lanes.values():
        lane_items.sort(key=lambda item: (str(item.get("updatedAt") or ""), str(item.get("roleCode") or "")), reverse=True)

    items = [role_operation_queue_lane(stage, lanes[stage["key"]], limit) for stage in ROLE_OPERATION_QUEUE_STAGES]
    blocked_total = len(lanes["blocked_roles"])
    review_total = len(lanes["review_roles"])
    empty_total = len(lanes["empty_roles"])
    ready_total = len(lanes["ready_roles"])
    actionable_total = blocked_total + review_total + empty_total
    summary = {
        "blockedRoleTotal": blocked_total,
        "reviewRoleTotal": review_total,
        "emptyRoleTotal": empty_total,
        "readyRoleTotal": ready_total,
        "actionableQueueTotal": actionable_total,
        "operationQueueTotal": actionable_total + ready_total,
    }
    return {
        "items": items,
        "operationQueue": items,
        "summary": summary,
        "limit": limit,
    }


def role_permission_presets() -> list[dict[str, Any]]:
    modules_by_key = module_catalog_by_key()
    known_permissions = {item["code"] for item in permission_catalog()}
    presets: list[dict[str, Any]] = []
    for preset in ROLE_PERMISSION_PRESETS:
        menu_modules = [
            module_key
            for module_key in compact_list(preset.get("menuModules") or [])
            if module_key in modules_by_key
        ]
        permissions = [
            permission
            for permission in compact_list(preset.get("permissions") or [])
            if permission in known_permissions
        ]
        expanded_permissions = expand_permission_codes(permissions)
        preview = role_draft_preview(menu_modules, permissions)
        presets.append(
            {
                "key": preset["key"],
                "label": preset["label"],
                "group": preset.get("group") or "",
                "description": preset.get("description") or "",
                "menuModules": menu_modules,
                "permissions": permissions,
                "expandedPermissions": expanded_permissions,
                "summary": {
                    "menuModuleCount": len(menu_modules),
                    "permissionCount": len(permissions),
                    "expandedPermissionCount": len(expanded_permissions),
                },
                "preview": preview,
            }
        )
    return presets


def permission_closure_guides() -> list[dict[str, Any]]:
    modules_by_key = module_catalog_by_key()
    known_permissions = {item["code"] for item in permission_catalog()}
    guides: list[dict[str, Any]] = []
    for closure in PERMISSION_CLOSURES:
        menu_modules = [
            module_key
            for module_key in compact_list(closure.get("menuModules") or [])
            if module_key in modules_by_key
        ]
        permissions = [
            permission
            for permission in compact_list(closure.get("permissions") or [])
            if permission in known_permissions
        ]
        preview = role_draft_preview(menu_modules, permissions)
        guides.append(
            {
                "key": closure["key"],
                "label": closure["label"],
                "group": closure.get("group") or "",
                "description": closure.get("description") or "",
                "menuModules": menu_modules,
                "permissions": permissions,
                "expandedPermissions": expand_permission_codes(permissions),
                "omittedPermissions": compact_list(closure.get("omittedPermissions") or []),
                "workflowEndpoints": compact_list(closure.get("workflowEndpoints") or []),
                "preview": preview,
                "summary": {
                    "menuModuleCount": len(menu_modules),
                    "permissionCount": len(permissions),
                    "expandedPermissionCount": len(expand_permission_codes(permissions)),
                    "workflowEndpointCount": len(compact_list(closure.get("workflowEndpoints") or [])),
                },
            }
        )
    return guides


def permission_closure_package(context: AuthContext) -> dict[str, Any]:
    closures = permission_closure_guides()
    phase1_closures = [closure for closure in closures if str(closure.get("key") or "").startswith("phase1-")]
    permissions: list[str] = []
    expanded_permissions: list[str] = []
    menu_modules: list[str] = []
    workflow_endpoints: list[str] = []
    omitted_permissions: list[str] = []
    for closure in closures:
        union_ordered(menu_modules, [str(item) for item in closure.get("menuModules") or []])
        union_ordered(permissions, [str(item) for item in closure.get("permissions") or []])
        union_ordered(expanded_permissions, [str(item) for item in closure.get("expandedPermissions") or []])
        union_ordered(workflow_endpoints, [str(item) for item in closure.get("workflowEndpoints") or []])
        union_ordered(omitted_permissions, [str(item) for item in closure.get("omittedPermissions") or []])
    return {
        "receiptType": "permission-closure-package",
        "exportedAt": now_iso(),
        "exportedBy": context.user,
        "exportPermission": "system.roles.export",
        "exportRoles": role_codes_for_context(context),
        "exportDataScopes": effective_data_scopes_for_context(context),
        "summary": {
            "closureCount": len(closures),
            "phase1ClosureCount": len(phase1_closures),
            "menuModuleCount": len(menu_modules),
            "permissionCount": len(permissions),
            "expandedPermissionCount": len(expanded_permissions),
            "workflowEndpointCount": len(workflow_endpoints),
            "omittedPermissionCount": len(omitted_permissions),
        },
        "permissionClosures": closures,
        "permissionImplications": permission_implications_payload(),
        "rolePresets": role_permission_presets(),
        "catalogHealth": permission_catalog_coverage(),
    }


def permission_preset_refs_by_code() -> dict[str, dict[str, list[str]]]:
    refs: dict[str, dict[str, list[str]]] = {}
    for preset in role_permission_presets():
        preset_codes = set([*(preset.get("permissions") or []), *(preset.get("expandedPermissions") or [])])
        for code in preset_codes:
            refs.setdefault(code, {"keys": [], "labels": []})
            refs[code]["keys"].append(preset["key"])
            refs[code]["labels"].append(preset["label"])
    return refs


def validate_role_draft_for_save(menu_modules: list[str], permissions: list[str]) -> None:
    preview = role_draft_preview(menu_modules, permissions)
    if preview.get("riskLevel") != "error":
        return
    raise HTTPException(
        status_code=400,
        detail={
            "message": "role menu modules require matching entry permissions",
            "riskLevel": preview.get("riskLevel"),
            "summary": preview.get("summary") or {},
            "blockedMenuModules": preview.get("blockedMenuModules") or [],
            "unknownMenuModules": preview.get("unknownMenuModules") or [],
            "unknownPermissions": preview.get("unknownPermissions") or [],
        },
    )


def role_permission_coverage_state(module_key: str, preview: dict[str, Any]) -> str:
    effective_keys = {str(item.get("key") or "") for item in preview.get("effectiveMenuModules") or []}
    configured_keys = {str(item or "") for item in preview.get("menuModules") or []}
    if module_key in effective_keys:
        return "visible"
    if module_key in configured_keys:
        return "blocked"
    return "pending"


def role_effective_permission_coverage(menu_modules: list[str], permissions: list[str]) -> dict[str, Any]:
    preview = role_draft_preview(menu_modules, permissions)
    permission_set = set(expand_permission_codes(permissions))
    modules_by_key = module_catalog_by_key()
    blocked_by_key = {
        str(item.get("key") or ""): item
        for item in preview.get("blockedMenuModules") or []
        if str(item.get("key") or "")
    }
    module_keys: list[str] = []
    union_ordered(module_keys, menu_modules)
    for code in permissions:
        module_key = str(permission_meta_by_code(code).get("module") or "")
        if module_key:
            union_ordered(module_keys, [module_key])

    items: list[dict[str, Any]] = []
    for module_key in module_keys:
        module = modules_by_key.get(module_key)
        if not module:
            items.append(
                {
                    "key": module_key,
                    "label": module_key,
                    "group": "未知模块",
                    "state": "blocked",
                    "stateLabel": "未知模块",
                    "entryPermission": "",
                    "missingEntryPermission": "",
                    "grantedPermissions": [],
                    "missingPermissions": [],
                    "apiScopes": [],
                    "reason": "角色配置了权限目录中不存在的菜单模块",
                }
            )
            continue
        entries = module_permission_entries(module)
        granted_permissions = [
            str(entry.get("code") or "")
            for entry in entries
            if permission_satisfied_by(permission_set, str(entry.get("code") or ""))
        ]
        missing_permissions = [
            str(entry.get("code") or "")
            for entry in entries
            if not permission_satisfied_by(permission_set, str(entry.get("code") or ""))
        ]
        state = role_permission_coverage_state(module_key, preview)
        blocked_item = blocked_by_key.get(module_key) or {}
        missing_entry_permission = str(blocked_item.get("missingEntryPermission") or "")
        state_labels = {"visible": "可见", "blocked": "入口阻断", "pending": "未配置入口"}
        reason = "菜单入口与权限匹配"
        if state == "blocked":
            reason = f"缺少入口权限 {missing_entry_permission or module.get('permission') or '-'}"
        elif state == "pending":
            reason = "已配置动作权限但未加入菜单"
        items.append(
            {
                "key": module_key,
                "label": module.get("label") or module_key,
                "group": module.get("group") or "",
                "state": state,
                "stateLabel": state_labels.get(state, state),
                "entryPermission": module.get("permission") or "",
                "missingEntryPermission": missing_entry_permission,
                "grantedPermissions": granted_permissions,
                "missingPermissions": missing_permissions,
                "apiScopes": module.get("apiScopes") or [],
                "reason": reason,
            }
        )

    configured_item_states = {"visible", "blocked"}
    summary = {
        "totalModules": len(items),
        "visibleMenuModules": sum(1 for item in items if item.get("state") == "visible"),
        "blockedMenuModules": sum(1 for item in items if item.get("state") == "blocked"),
        "pendingMenuModules": sum(1 for item in items if item.get("state") == "pending"),
        "grantedPermissionCount": len([code for code in permissions if str(code or "").strip()]),
        "missingPermissionCount": sum(
            len(item.get("missingPermissions") or [])
            for item in items
            if item.get("state") in configured_item_states
        ),
    }
    return {"summary": summary, "items": items}


def role_permission_receipt(role: dict[str, Any]) -> dict[str, Any]:
    permissions = [str(item) for item in role.get("permissions") or [] if str(item or "").strip()]
    menu_modules = [str(item) for item in role.get("menuModules") or [] if str(item or "").strip()]
    data_scopes = role.get("dataScopes") if isinstance(role.get("dataScopes"), dict) else {}
    return {
        "receiptType": "role-permission-configuration",
        "exportedAt": now_iso(),
        "role": AdminRoleOut.model_validate(role).model_dump(mode="json"),
        "configuredPermissions": permissions,
        "expandedPermissions": expand_permission_codes(permissions),
        "menuDiagnostics": role_draft_preview(menu_modules, permissions),
        "effectivePermissionCoverage": role_effective_permission_coverage(menu_modules, permissions),
        "dataScopes": data_scopes,
        "permissionImplications": permission_implications_payload(),
    }


@router.get("/permission-catalog")
def get_permission_catalog(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.roles.view")
    return {
        "menuModules": ADMIN_MENU_MODULES,
        "permissions": permission_catalog(),
        "permissionImplications": permission_implications_payload(),
        "rolePresets": role_permission_presets(),
        "permissionClosures": permission_closure_guides(),
        "matrix": permission_matrix(),
        "groups": sorted({module["group"] for module in ADMIN_MENU_MODULES}),
        "coverage": permission_catalog_coverage(),
    }


@router.get("/permission-catalog.csv")
def export_permission_catalog_csv(context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "system.roles.export")
    return csv_download_response(
        "permission-catalog.csv",
        [
            "group",
            "moduleKey",
            "moduleLabel",
            "href",
            "entryPermission",
            "permissionCode",
            "permissionLabel",
            "permissionKind",
            "permissionKindLabel",
            "apiScopes",
            "permissionApiScopes",
            "requiresAllPermissions",
            "requiresAnyPermissions",
            "dependencyReason",
            "impliedBy",
            "presetKeys",
            "presetLabels",
        ],
        permission_catalog_export_records(),
    )


@router.get("/permission-closures.json")
def export_permission_closure_package(context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "system.roles.export")
    return json_download_response("permission-closure-package.json", permission_closure_package(context))


@router.get("/roles/menu")
def role_menu(roles: str = Query(default=""), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    role_codes = compact_list(roles.split(","))
    permissions: list[str] = []
    configured_menu_modules: list[str] = []
    for code in role_codes:
        role = role_by_code(code)
        if role is None or role.get("status") not in ("active", None, ""):
            continue
        union_ordered(permissions, role.get("permissions") or [])
        union_ordered(configured_menu_modules, role.get("menuModules") or [])
    menu_modules = menu_modules_allowed_by_permissions(configured_menu_modules, permissions)
    modules_by_key = module_catalog_by_key()
    visible_modules = [modules_by_key[key] for key in menu_modules if key in modules_by_key]
    return {
        "roles": role_codes,
        "permissions": permissions,
        "configuredMenuModules": configured_menu_modules,
        "menuModules": menu_modules,
        "visibleMenuModules": visible_modules,
        "permissionImplications": permission_implications_payload(),
        "unknownRoles": unknown_role_entries(role_codes),
        "invalidRoles": invalid_role_entries(role_codes),
    }


@router.post("/roles/preview")
def preview_role_draft(payload: RolePreviewRequest, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_any_permission(context, ["system.roles.create", "system.roles.update"])
    return role_draft_preview(payload.menuModules, payload.permissions)


@router.get("/effective-permissions")
def effective_permissions(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    roles = role_codes_for_context(context)
    permissions = effective_permissions_for_context(context)
    menu_modules = effective_menu_modules_for_context(context)
    modules_by_key = module_catalog_by_key()
    return {
        "user": context.user,
        "roles": roles,
        "permissions": permissions,
        "menuModules": menu_modules,
        "visibleMenuModules": [modules_by_key[key] for key in menu_modules if key in modules_by_key],
        "dataScopes": effective_data_scopes_for_context(context),
        "permissionImplications": permission_implications_payload(),
        "unknownRoles": unknown_role_entries(roles),
        "invalidRoles": invalid_role_entries(roles),
    }


@router.get("/roles")
def list_roles(filters: RoleFilters = Depends(filter_params), context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.roles.view")
    if filters.includeDeleted:
        require_permission(context, "system.roles.restore")
    if use_mysql():
        return {
            "items": fetch_roles_mysql(
                filters=filters,
                include_deleted=filters.includeDeleted,
                limit=filters.limit,
                offset=filters.offset,
            ),
            "total": count_roles_mysql(filters),
            "limit": filters.limit,
            "offset": filters.offset,
        }
    if use_postgis():
        return {
            "items": fetch_roles_postgis(
                filters=filters,
                include_deleted=filters.includeDeleted,
                limit=filters.limit,
                offset=filters.offset,
            ),
            "total": count_roles_postgis(filters),
            "limit": filters.limit,
            "offset": filters.offset,
        }
    source_roles = load_all_roles() if filters.includeDeleted else load_roles()
    roles = [role for role in source_roles if role_matches(role, filters)]
    return {
        "items": roles[filters.offset : filters.offset + filters.limit],
        "total": len(roles),
        "limit": filters.limit,
        "offset": filters.offset,
    }


@router.get("/roles/events")
def list_role_events(
    q: str = Query(default=""),
    action: str = Query(default=""),
    roleCode: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.roles.view")
    records = list_role_event_records(q=q, action=action, role_code=roleCode)
    page = records[offset : offset + limit]
    return {
        "items": page,
        "total": len(records),
        "limit": limit,
        "offset": offset,
    }


@router.get("/roles/events.csv")
def export_role_events_csv(
    q: str = Query(default=""),
    action: str = Query(default=""),
    roleCode: str = Query(default=""),
    context: AuthContext = Depends(request_context),
) -> Response:
    require_permission(context, "system.roles.export")
    records = list_role_event_records(q=q, action=action, role_code=roleCode)
    return csv_download_response(
        "role-events.csv",
        ["eventId", "roleId", "roleCode", "roleName", "action", "actor", "at", "changedFields", "permissions", "menuModules", "summary"],
        records,
    )


@router.get("/roles/operation-queue")
def get_role_operation_queue(
    limit: int = Query(default=5, ge=1, le=20),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.roles.view")
    return role_operation_queue(limit=limit)


@router.get("/roles/{role_id}/permission-receipt.json")
def export_role_permission_receipt(role_id: str, context: AuthContext = Depends(request_context)) -> Response:
    require_permission(context, "system.roles.export")
    role = find_role(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    role_code = safe_download_stem(str(role.get("roleCode") or role_id), "role")
    return json_download_response(
        f"role-permission-receipt-{role_code}.json",
        role_permission_receipt(role),
    )


@router.post("/roles")
def create_role(payload: AdminRoleIn, context: AuthContext = Depends(request_context)) -> AdminRoleOut:
    require_permission(context, "system.roles.create")
    if role_by_code(payload.roleCode):
        raise HTTPException(status_code=409, detail="roleCode already exists")
    role = normalize_role(payload.model_dump())
    validate_role_draft_for_save(role.get("menuModules") or [], role.get("permissions") or [])
    role = append_role_audit_event(
        role,
        "create",
        context,
        changed_fields=["roleCode", "name", "status", "permissions", "menuModules", "dataScopes", "properties"],
    )
    if use_mysql() or use_postgis():
        save_roles([role])
        return AdminRoleOut.model_validate(role)
    roles = load_all_roles()
    roles.append(role)
    save_roles(roles)
    return AdminRoleOut.model_validate(role)


@router.get("/roles/{role_id}")
def get_role(role_id: str, context: AuthContext = Depends(request_context)) -> AdminRoleOut:
    require_permission(context, "system.roles.view")
    role = find_role(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return AdminRoleOut.model_validate(role)


@router.patch("/roles/{role_id}")
def patch_role(role_id: str, payload: AdminRolePatch, context: AuthContext = Depends(request_context)) -> AdminRoleOut:
    require_permission(context, "system.roles.update")
    roles = load_all_roles()
    for index, role in enumerate(roles):
        if str(role.get("id")) != str(role_id) or role.get("deletedAt"):
            continue
        changes = payload.model_dump(exclude_unset=True)
        updated = normalize_role(
            {
                **role,
                **changes,
                "id": role_id,
                "createdAt": role.get("createdAt", now_iso()),
                "deletedAt": role.get("deletedAt"),
            }
        )
        validate_role_draft_for_save(updated.get("menuModules") or [], updated.get("permissions") or [])
        changed_fields = role_changed_fields(role, updated)
        updated = append_role_audit_event(updated, "update", context, before=role, changed_fields=changed_fields)
        roles[index] = updated
        save_roles(roles)
        return AdminRoleOut.model_validate(updated)
    raise HTTPException(status_code=404, detail="Role not found")


@router.delete("/roles/{role_id}")
def delete_role(role_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.roles.delete")
    roles = load_all_roles()
    for index, role in enumerate(roles):
        if str(role.get("id")) != str(role_id) or role.get("deletedAt"):
            continue
        deleted_at = now_iso()
        deleted_role = {
            **role,
            "deletedAt": deleted_at,
            "updatedAt": deleted_at,
        }
        deleted_role = append_role_audit_event(
            deleted_role,
            "delete",
            context,
            before=role,
            changed_fields=["deletedAt"],
        )
        roles[index] = deleted_role
        save_roles(roles)
        return {"ok": True, "deleted": role_id}
    raise HTTPException(status_code=404, detail="Role not found")


@router.post("/roles/{role_id}/restore")
def restore_role(role_id: str, context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.roles.restore")
    roles = load_all_roles()
    for index, role in enumerate(roles):
        if str(role.get("id")) != str(role_id):
            continue
        if not role.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Role is not deleted")
        duplicate = next(
            (
                item
                for item in roles
                if str(item.get("id")) != str(role_id)
                and not item.get("deletedAt")
                and str(item.get("roleCode") or "") == str(role.get("roleCode") or "")
            ),
            None,
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="roleCode already exists")
        restored_at = now_iso()
        restored_role = {
            **role,
            "deletedAt": None,
            "updatedAt": restored_at,
        }
        restored_role = append_role_audit_event(
            restored_role,
            "restore",
            context,
            before=role,
            changed_fields=["deletedAt"],
        )
        roles[index] = restored_role
        save_roles(roles)
        return {
            "ok": True,
            "restored": role_id,
            "role": AdminRoleOut.model_validate(restored_role).model_dump(),
        }
    raise HTTPException(status_code=404, detail="Role not found")
