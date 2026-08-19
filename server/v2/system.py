from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from server.modules.admin_roles import effective_permissions_for_context, require_permission
from server.modules.auth import AuthContext, has_admin_role, request_context
from server.modules.basemap_settings import public_basemap_settings, runtime_basemap_settings, save_basemap_settings
from server.modules.dictionaries import load_all_items, type_by_code


router = APIRouter(prefix="/system", tags=["v2-system"])


@router.get("/administrative-divisions")
def administrative_divisions(
    level: str = Query(default="province"),
    parentCode: str | None = Query(default=None),
    q: str = Query(default=""),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    """Return one lightweight level of the national division tree.

    Forest editors only need the visible branch, so this endpoint avoids sending
    the complete 40k+ national snapshot to every browser.
    """
    require_permission(context, "forest.blocks.view")
    dictionary_type = type_by_code("administrative-divisions")
    if dictionary_type is None:
        return {"items": [], "total": 0, "level": level, "parentCode": parentCode or ""}

    normalized_parent = None if parentCode is None else parentCode.strip()
    normalized_query = q.strip().lower()
    records = [
        item
        for item in load_all_items()
        if item["dictionaryTypeId"] == dictionary_type["id"]
        and not item["deletedAt"]
        and item["status"] == "active"
        and item["levelCode"] == level
        and (normalized_parent is None or item["parentCode"] == normalized_parent)
        and (
            not normalized_query
            or normalized_query in item["itemCode"].lower()
            or normalized_query in item["label"].lower()
            or normalized_query in item["fullName"].lower()
        )
    ]
    records.sort(key=lambda item: (item["sortOrder"], item["label"], item["itemCode"]))
    return {
        "items": [
            {
                "code": item["itemCode"],
                "name": item["label"],
                "parentCode": item["parentCode"],
                "level": item["levelCode"],
                "fullName": item["fullName"],
            }
            for item in records[:limit]
        ],
        "total": len(records),
        "level": level,
        "parentCode": normalized_parent or "",
    }


class BasemapSettingsPayload(BaseModel):
    serverKey: str = ""
    webKey: str = ""
    androidKey: str = ""
    iosKey: str = ""
    webDirectEnabled: bool = False
    proxyBaseUrl: str = ""
    referer: str = ""


V2_MODULES: tuple[dict[str, Any], ...] = (
    {
        "key": "workspace",
        "label": "我的工作台",
        "path": "/workspace",
        "requiredPermission": "",
        "status": "available",
    },
    {
        "key": "leadership-cockpit",
        "label": "领导驾驶舱",
        "path": "/cockpit/leadership",
        "requiredPermission": "cockpit.leadership.view",
        "status": "available",
    },
    {
        "key": "operations-todos",
        "label": "我的待办",
        "path": "/operations/todos",
        "requiredPermission": "operations.todos.view",
        "status": "available",
    },
    {
        "key": "operations-notifications",
        "label": "消息中心",
        "path": "/system/notifications",
        "requiredPermission": "operations.notifications.view",
        "status": "available",
    },
    {
        "key": "operations-audit",
        "label": "审计中心",
        "path": "/system/audit",
        "requiredPermission": "operations.audit.view",
        "status": "available",
    },
    {
        "key": "map",
        "label": "GIS 一张图",
        "path": "/map",
        "requiredPermission": "forest.blocks.view",
        "status": "available",
    },
    {
        "key": "forest-blocks",
        "label": "林班台账",
        "path": "/resources/forest-blocks",
        "requiredPermission": "forest.blocks.view",
        "status": "available",
    },
    {
        "key": "forest-subcompartments",
        "label": "小班台账",
        "path": "/resources/forest-subcompartments",
        "requiredPermission": "forest.subcompartments.view",
        "status": "available",
    },
    {
        "key": "resourceSurveys",
        "label": "资源调查",
        "path": "/resources/resource-surveys",
        "requiredPermission": "forest.surveys.view",
        "status": "available",
    },
    {
        "key": "attachments",
        "label": "附件中心",
        "path": "/system/attachments",
        "requiredPermission": "files.attachments.view",
        "status": "available",
    },
    {
        "key": "forest-rights",
        "label": "林权档案",
        "path": "/resources/forest-rights",
        "requiredPermission": "forest.rights.view",
        "status": "available",
    },
    {
        "key": "imports",
        "label": "数据接入",
        "path": "/resources/imports",
        "requiredPermission": "imports.forestBlocks.view",
        "status": "available",
    },
    {
        "key": "patrol",
        "label": "巡护办理",
        "path": "/operations/patrol",
        "requiredPermission": "business.maintenanceTasks.view",
        "status": "available",
    },
    {
        "key": "harvest",
        "label": "采伐办理",
        "path": "/operations/harvest",
        "requiredPermission": "operations.harvest.view",
        "status": "available",
    },
    {
        "key": "labor",
        "label": "劳务用工",
        "path": "/operations/labor",
        "requiredPermission": "labor.view",
        "status": "available",
    },
    {
        "key": "equipment",
        "label": "设备台账",
        "path": "/iot/devices",
        "requiredPermission": "iot.devices.view",
        "status": "available",
    },
    {
        "key": "drone-missions",
        "label": "无人机任务",
        "path": "/drone/missions",
        "requiredPermission": "drone.missions.view",
        "status": "available",
    },
    {
        "key": "imagery-assets",
        "label": "影像成果",
        "path": "/drone/imagery-assets",
        "requiredPermission": "imagery.scenes.view",
        "status": "available",
    },
    {
        "key": "ai-findings",
        "label": "AI 识别复核",
        "path": "/ai/reviews",
        "requiredPermission": "ai.findings.view",
        "status": "available",
    },
    {
        "key": "ai-models",
        "label": "AI 模型管理",
        "path": "/ai/models",
        "requiredPermission": "ai.models.view",
        "status": "available",
    },
    {
        "key": "ai-inference",
        "label": "AI 推理任务",
        "path": "/ai/inference-runs",
        "requiredPermission": "ai.inference.view",
        "status": "available",
    },
    {
        "key": "safety-events",
        "label": "事件中心",
        "path": "/safety/events",
        "requiredPermission": "safety.events.view",
        "status": "available",
    },
    {
        "key": "mobile-operations",
        "label": "现场同步",
        "path": "/operations/mobile-sync",
        "requiredPermission": "mobile.operations.view",
        "status": "available",
    },
    {
        "key": "carbon-estimates",
        "label": "碳汇项目",
        "path": "/carbon/estimates",
        "requiredPermission": "business.carbonEstimates.view",
        "status": "available",
    },
    {
        "key": "resource-intelligence",
        "label": "资源专题分析",
        "path": "/resources/intelligence",
        "requiredPermission": "forest.analytics.view",
        "status": "available",
    },
    {
        "key": "cost-management",
        "label": "经营成本",
        "path": "/operations/costs",
        "requiredPermission": "costs.view",
        "status": "available",
    },
    {
        "key": "workforce-development",
        "label": "劳务培训与资质",
        "path": "/workforce",
        "requiredPermission": "labor.view",
        "status": "available",
    },
    {
        "key": "integration-hub",
        "label": "集成与联调",
        "path": "/integrations",
        "requiredPermission": "integrations.view",
        "status": "available",
    },
    {
        "key": "system-governance",
        "label": "系统治理",
        "path": "/system/governance",
        "requiredPermission": "system.accessRequests.view",
        "status": "available",
    },
    {
        "key": "system-overview",
        "label": "系统管理",
        "path": "/system/overview",
        "requiredPermission": "system.users.view",
        "status": "available",
    },
    {
        "key": "organizations",
        "label": "组织架构",
        "path": "/system/organizations",
        "requiredPermission": "system.organizations.view",
        "status": "available",
    },
    {
        "key": "users",
        "label": "用户账号",
        "path": "/system/users",
        "requiredPermission": "system.users.view",
        "status": "available",
    },
    {
        "key": "roles",
        "label": "角色管理",
        "path": "/system/roles",
        "requiredPermission": "system.roles.view",
        "status": "available",
    },
    {
        "key": "permissions",
        "label": "权限目录",
        "path": "/system/permissions",
        "requiredPermission": "system.roles.view",
        "status": "available",
    },
    {
        "key": "basemap-settings",
        "label": "底图服务配置",
        "path": "/system/basemap-settings",
        "requiredPermission": "system.basemap.view",
        "status": "available",
    },
)


def module_visible(module: dict[str, Any], permissions: set[str]) -> bool:
    required = str(module.get("requiredPermission") or "")
    if not required:
        return True
    if "*" in permissions or required in permissions:
        return True
    domain = required.rsplit(".", 1)[0]
    return f"{domain}.manage" in permissions


@router.get("/capabilities")
def v2_capabilities(
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    permissions = set(effective_permissions_for_context(context))
    administrator = has_admin_role(context)
    modules = [
        {
            **module,
            "visible": administrator or module_visible(module, permissions),
        }
        for module in V2_MODULES
    ]
    return {
        "apiVersion": "v2",
        "storagePolicy": "v1-compatible-adapter",
        "principal": {
            "user": context.user,
            "roles": sorted(context.roles),
            "principalType": context.principal_type,
        },
        "modules": modules,
        "permissions": sorted(permissions),
    }


@router.get("/map-config")
def v2_map_config(
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.blocks.view")
    settings = runtime_basemap_settings()
    direct_web = bool(settings["webDirectEnabled"] and settings["webKey"])
    configured = bool(settings["serverKey"] or settings["proxyBaseUrl"] or direct_web)
    if direct_web:
        web_key = settings["webKey"]
        imagery_url = f"https://t0.tianditu.gov.cn/DataServer?T=img_w&x={{x}}&y={{y}}&l={{z}}&tk={web_key}"
        labels_url = f"https://t0.tianditu.gov.cn/DataServer?T=cia_w&x={{x}}&y={{y}}&l={{z}}&tk={web_key}"
    else:
        imagery_url = "/api/basemaps/tianditu/img_w/{z}/{x}/{y}.png"
        labels_url = "/api/basemaps/tianditu/cia_w/{z}/{x}/{y}.png"
    return {
        "provider": "tianditu",
        "available": configured,
        "accessMode": "web-direct" if direct_web else "server-proxy",
        "imageryUrl": imagery_url,
        "labelsUrl": labels_url,
        "maximumLevel": 18,
        "message": "天地图服务已连接" if configured else "当前环境尚未配置天地图服务端 Key",
    }


@router.get("/basemap-settings")
def v2_basemap_settings(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    require_permission(context, "system.basemap.view")
    return public_basemap_settings()


@router.put("/basemap-settings")
def update_v2_basemap_settings(
    payload: BasemapSettingsPayload,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.basemap.manage")
    current = runtime_basemap_settings()
    credentials: dict[str, str] = {}
    for supplied, settings_name, label in (
        (payload.serverKey, "serverKey", "服务端"),
        (payload.webKey, "webKey", "Web"),
        (payload.androidKey, "androidKey", "Android"),
        (payload.iosKey, "iosKey", "iOS"),
    ):
        key = supplied.strip()
        if not key or "*" in key:
            key = str(current[settings_name])
        if key and (len(key) != 32 or not key.isalnum()):
            raise HTTPException(status_code=422, detail=f"天地图 {label} Key 必须是 32 位字母或数字。")
        credentials[settings_name] = key
    proxy_base_url = payload.proxyBaseUrl.strip().rstrip("/")
    if proxy_base_url and not proxy_base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="上游代理地址必须以 http:// 或 https:// 开头。")
    if not credentials["serverKey"] and not proxy_base_url and not (payload.webDirectEnabled and credentials["webKey"]):
        raise HTTPException(status_code=422, detail="请配置服务端 Key、上游代理地址，或配置 Web Key 并开启 Web 直连。")
    if payload.webDirectEnabled and not credentials["webKey"]:
        raise HTTPException(status_code=422, detail="开启 Web 直连前必须配置 Web Key。")
    return save_basemap_settings(
        server_key=credentials["serverKey"],
        web_key=credentials["webKey"],
        android_key=credentials["androidKey"],
        ios_key=credentials["iosKey"],
        web_direct_enabled=payload.webDirectEnabled,
        proxy_base_url=proxy_base_url,
        referer=payload.referer,
    )
