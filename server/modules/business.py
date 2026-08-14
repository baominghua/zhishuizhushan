from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .admin_roles import (
    csv_download_response,
    effective_data_scopes_for_context,
    json_download_response,
    require_permission,
    role_codes_for_context,
    safe_download_stem,
)
from .auth import AuthContext, request_context
from .business_forms import FORMAL_BUSINESS_FIELD_SCHEMAS
from .database import (
    business_json_path,
    load_json_records,
    map_layers_json_path,
    mysql_connect,
    save_json_records,
    use_mysql,
    use_postgis,
)
from .settings import get_settings


router = APIRouter(prefix="/api", tags=["business-modules"])

MAP_LAYER_PERMISSIONS = {
    "view": "map.layers.view",
    "create": "map.layers.create",
    "update": "map.layers.update",
    "delete": "map.layers.delete",
    "restore": "map.layers.restore",
    "export": "map.layers.export",
    "publish": "map.layers.publish",
}

MAP_LAYER_PUBLICATION_QUEUE_STAGES = [
    {
        "key": "blocked",
        "label": "发布阻断",
        "tone": "danger",
        "requiredPermission": MAP_LAYER_PERMISSIONS["update"],
    },
    {
        "key": "needs_review",
        "label": "发布前复核",
        "tone": "review",
        "requiredPermission": MAP_LAYER_PERMISSIONS["update"],
    },
    {
        "key": "awaiting_publish",
        "label": "待发布到大屏",
        "tone": "warning",
        "requiredPermission": MAP_LAYER_PERMISSIONS["publish"],
    },
    {
        "key": "receipt_ready",
        "label": "发布回执待导出",
        "tone": "ready",
        "requiredPermission": MAP_LAYER_PERMISSIONS["export"],
    },
]

POSTGIS_LAYER_SELECT_COLUMNS = [
    "id",
    "record_code",
    "name",
    "status",
    "layer_type",
    "data_source",
    "style",
    "z_index",
    "visible_on_dashboard",
    "linked_block_codes",
    "linked_right_archive_codes",
    "properties",
    "created_at",
    "updated_at",
    "deleted_at",
]

POSTGIS_LAYER_SELECT_SQL = """
    SELECT
        id::text,
        record_code,
        name,
        status,
        layer_type,
        data_source,
        COALESCE(style, '{}'::jsonb),
        z_index,
        visible_on_dashboard,
        COALESCE(linked_block_codes, '[]'::jsonb),
        COALESCE(linked_right_archive_codes, '[]'::jsonb),
        COALESCE(properties, '{}'::jsonb),
        created_at,
        updated_at,
        deleted_at
    FROM map_layers
"""
MYSQL_LAYER_SELECT_SQL = """
    SELECT
        ml.id,
        ml.record_code,
        ml.name,
        ml.status,
        ml.layer_type,
        ml.data_source,
        COALESCE(ml.style, JSON_OBJECT()),
        ml.z_index,
        ml.visible_on_dashboard,
        COALESCE((
            SELECT JSON_ARRAYAGG(b.block_code)
            FROM map_layer_block_links lbl
            JOIN forest_blocks b ON b.id = lbl.forest_block_id
            WHERE lbl.map_layer_id = ml.id
        ), JSON_ARRAY()),
        COALESCE((
            SELECT JSON_ARRAYAGG(fr.archive_code)
            FROM map_layer_right_links lrl
            JOIN forest_rights fr ON fr.id = lrl.forest_right_id
            WHERE lrl.map_layer_id = ml.id
        ), JSON_ARRAY()),
        COALESCE(ml.properties, JSON_OBJECT()),
        ml.created_at,
        ml.updated_at,
        ml.deleted_at
    FROM map_layers ml
"""

MYSQL_LAYER_SCALAR_SELECT_SQL = """
    SELECT
        ml.id,
        ml.record_code,
        ml.name,
        ml.status,
        ml.layer_type,
        ml.data_source,
        COALESCE(ml.style, JSON_OBJECT()),
        ml.z_index,
        ml.visible_on_dashboard,
        JSON_ARRAY(),
        JSON_ARRAY(),
        COALESCE(ml.properties, JSON_OBJECT()),
        ml.created_at,
        ml.updated_at,
        ml.deleted_at
    FROM map_layers ml
"""

MYSQL_LAYER_SUMMARY_SELECT_SQL = MYSQL_LAYER_SCALAR_SELECT_SQL.replace(
    "COALESCE(ml.properties, JSON_OBJECT()),",
    """
        JSON_SET(
            COALESCE(ml.properties, JSON_OBJECT()),
            '$.linkedBlockCount', (
                SELECT COUNT(*) FROM map_layer_block_links summary_blocks
                WHERE summary_blocks.map_layer_id = ml.id
            ),
            '$.linkedRightArchiveCount', (
                SELECT COUNT(*) FROM map_layer_right_links summary_rights
                WHERE summary_rights.map_layer_id = ml.id
            ),
            '$.linkedTargetsTruncated', (
                (SELECT COUNT(*) FROM map_layer_block_links summary_block_limit
                 WHERE summary_block_limit.map_layer_id = ml.id) > 100
                OR
                (SELECT COUNT(*) FROM map_layer_right_links summary_right_limit
                 WHERE summary_right_limit.map_layer_id = ml.id) > 100
            )
        ),
    """,
)

LAYER_DB_TO_API_FIELD = {
    "id": "id",
    "record_code": "recordCode",
    "name": "name",
    "status": "status",
    "layer_type": "layerType",
    "data_source": "dataSource",
    "style": "style",
    "z_index": "zIndex",
    "visible_on_dashboard": "visibleOnDashboard",
    "linked_block_codes": "linkedBlockCodes",
    "linked_right_archive_codes": "linkedRightArchiveCodes",
    "properties": "properties",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "deleted_at": "deletedAt",
}

POSTGIS_BUSINESS_SELECT_COLUMNS = [
    "id",
    "module_key",
    "record_code",
    "name",
    "status",
    "linked_block_codes",
    "linked_right_archive_codes",
    "properties",
    "payload",
    "created_at",
    "updated_at",
    "deleted_at",
]

POSTGIS_BUSINESS_SELECT_SQL = """
    SELECT
        id::text,
        module_key,
        record_code,
        name,
        status,
        COALESCE(linked_block_codes, '[]'::jsonb),
        COALESCE(linked_right_archive_codes, '[]'::jsonb),
        COALESCE(properties, '{}'::jsonb),
        COALESCE(payload, '{}'::jsonb),
        created_at,
        updated_at,
        deleted_at
    FROM business_records
"""
MYSQL_BUSINESS_SELECT_SQL = """
    SELECT
        br.id,
        br.module_key,
        br.record_code,
        br.name,
        br.status,
        COALESCE((
            SELECT JSON_ARRAYAGG(b.block_code)
            FROM business_record_block_links bbl
            JOIN forest_blocks b ON b.id = bbl.forest_block_id
            WHERE bbl.business_record_id = br.id
        ), JSON_ARRAY()),
        COALESCE((
            SELECT JSON_ARRAYAGG(fr.archive_code)
            FROM business_record_right_links brl
            JOIN forest_rights fr ON fr.id = brl.forest_right_id
            WHERE brl.business_record_id = br.id
        ), JSON_ARRAY()),
        COALESCE(br.properties, JSON_OBJECT()),
        JSON_SET(
            COALESCE(br.payload, JSON_OBJECT()),
            '$.linkedRecords',
            COALESCE((
                SELECT JSON_ARRAYAGG(JSON_OBJECT(
                    'relationType', links.relation_type,
                    'targetModuleKey', links.target_module_key,
                    'targetRecordId', links.target_record_id,
                    'targetRecordCode', targets.record_code,
                    'targetName', targets.name,
                    'targetStatus', targets.status,
                    'sortOrder', links.sort_order,
                    'properties', COALESCE(links.properties, JSON_OBJECT())
                ))
                FROM business_record_links links
                JOIN business_records targets ON targets.id = links.target_record_id
                WHERE links.source_record_id = br.id
                  AND targets.deleted_at IS NULL
            ), JSON_ARRAY())
        ),
        br.created_at,
        br.updated_at,
        br.deleted_at
    FROM business_records br
"""
MYSQL_BUSINESS_SUMMARY_SELECT_SQL = """
    SELECT
        br.id,
        br.module_key,
        br.record_code,
        br.name,
        br.status,
        JSON_ARRAY(),
        JSON_ARRAY(),
        JSON_SET(
            COALESCE(br.properties, JSON_OBJECT()),
            '$.linkedBlockCount', (
                SELECT COUNT(*)
                FROM business_record_block_links bbl
                WHERE bbl.business_record_id = br.id
            ),
            '$.linkedRightArchiveCount', (
                SELECT COUNT(*)
                FROM business_record_right_links brl
                WHERE brl.business_record_id = br.id
            ),
            '$.linkedTargetsTruncated', (
                (SELECT COUNT(*) FROM business_record_block_links bbl WHERE bbl.business_record_id = br.id) > 0
                OR (SELECT COUNT(*) FROM business_record_right_links brl WHERE brl.business_record_id = br.id) > 0
            )
        ),
        COALESCE(br.payload, JSON_OBJECT()),
        br.created_at,
        br.updated_at,
        br.deleted_at
    FROM business_records br
"""

BUSINESS_DB_TO_API_FIELD = {
    "id": "id",
    "record_code": "recordCode",
    "name": "name",
    "status": "status",
    "linked_block_codes": "linkedBlockCodes",
    "linked_right_archive_codes": "linkedRightArchiveCodes",
    "properties": "properties",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "deleted_at": "deletedAt",
}

BUSINESS_CANONICAL_FIELDS = {
    "id",
    "recordCode",
    "name",
    "status",
    "linkedBlockCodes",
    "linkedRightArchiveCodes",
    "properties",
    "createdAt",
    "updatedAt",
    "deletedAt",
}

BUSINESS_MODULES = {
    "farmers": {
        "formVersion": 2,
        "title": "竹农信息卡",
        "subtitle": "主体档案、承包林班与作业记录",
        "totalLabel": "竹农总数",
        "totalUnit": "户",
        "linkedLabel": "绑定林班",
        "linkedUnit": "个",
        "activeLabel": "活跃档案",
        "columns": ["姓名", "所属村镇", "关联林班", "状态"],
    },
    "cooperatives": {
        "title": "合作社信息卡",
        "subtitle": "合作社经营、服务能力与订单协同",
        "totalLabel": "合作社",
        "totalUnit": "家",
        "linkedLabel": "服务林班",
        "linkedUnit": "个",
        "activeLabel": "活跃合作社",
        "columns": ["合作社", "服务范围", "关联林班", "经营状态"],
    },
    "enterprises": {
        "title": "竹企信息卡",
        "subtitle": "加工企业、仓储流转与产销对接",
        "totalLabel": "竹企数量",
        "totalUnit": "家",
        "linkedLabel": "对接林班",
        "linkedUnit": "个",
        "activeLabel": "活跃企业",
        "columns": ["企业名称", "主营方向", "对接林班", "库存状态"],
    },
    "plant-protection-events": {
        "title": "植保信息卡",
        "subtitle": "病虫害、处置工单与防治进度",
        "totalLabel": "预警事件",
        "totalUnit": "项",
        "linkedLabel": "重点林班",
        "linkedUnit": "个",
        "activeLabel": "待处置",
        "columns": ["林班", "问题类型", "等级", "处置状态"],
    },
    "materials": {
        "title": "农资信息卡",
        "subtitle": "肥料、药剂、工具与领用记录",
        "totalLabel": "农资品类",
        "totalUnit": "类",
        "linkedLabel": "适用林班",
        "linkedUnit": "个",
        "activeLabel": "库存正常",
        "columns": ["物资名称", "库存", "适用环节", "状态"],
    },
    "policies": {
        "title": "政策法规信息卡",
        "subtitle": "补贴政策、采伐规范与生态保护要求",
        "totalLabel": "政策文件",
        "totalUnit": "份",
        "linkedLabel": "关联林班",
        "linkedUnit": "个",
        "activeLabel": "可申报",
        "columns": ["政策名称", "适用对象", "申报状态", "截止时间"],
    },
    "stewardship-agreements": {
        "title": "托管协议信息卡",
        "subtitle": "托管协议、服务主体、托管林班与履约状态",
        "totalLabel": "托管协议",
        "totalUnit": "份",
        "linkedLabel": "托管林班",
        "linkedUnit": "个",
        "activeLabel": "履约中",
        "columns": ["协议名称", "托管主体", "托管林班", "履约状态"],
    },
    "franchise-bases": {
        "title": "加盟基地信息卡",
        "subtitle": "加盟基地、基地范围、经营主体与服务等级",
        "totalLabel": "加盟基地",
        "totalUnit": "个",
        "linkedLabel": "覆盖林班",
        "linkedUnit": "个",
        "activeLabel": "运营中",
        "columns": ["基地名称", "所在区域", "覆盖林班", "运营状态"],
    },
    "maintenance-tasks": {
        "title": "管护任务信息卡",
        "subtitle": "巡护、抚育、防火、防盗伐等管护任务闭环",
        "totalLabel": "管护任务",
        "totalUnit": "项",
        "linkedLabel": "涉及林班",
        "linkedUnit": "个",
        "activeLabel": "待处理",
        "columns": ["任务名称", "任务类型", "涉及林班", "处理状态"],
    },
    "work-logs": {
        "title": "作业记录信息卡",
        "subtitle": "采伐、施肥、除草、运输等现场作业记录",
        "totalLabel": "作业记录",
        "totalUnit": "条",
        "linkedLabel": "作业林班",
        "linkedUnit": "个",
        "activeLabel": "有效记录",
        "columns": ["作业名称", "作业环节", "作业林班", "记录状态"],
    },
    "drone-tasks": {
        "title": "无人机任务信息卡",
        "subtitle": "航飞计划、影像采集、巡检任务与成果状态",
        "totalLabel": "无人机任务",
        "totalUnit": "项",
        "linkedLabel": "覆盖林班",
        "linkedUnit": "个",
        "activeLabel": "执行中",
        "columns": ["任务名称", "任务类型", "覆盖林班", "飞行状态"],
    },
    "equipment": {
        "title": "设备台账信息卡",
        "subtitle": "无人机、传感器、视频监控、定位终端等设备资产",
        "totalLabel": "设备数量",
        "totalUnit": "台",
        "linkedLabel": "绑定林班",
        "linkedUnit": "个",
        "activeLabel": "在线设备",
        "columns": ["设备名称", "设备类型", "绑定林班", "运行状态"],
    },
    "pest-warnings": {
        "title": "病虫害预警信息卡",
        "subtitle": "病虫害预警、风险等级、处置建议与复核结果",
        "totalLabel": "预警事件",
        "totalUnit": "项",
        "linkedLabel": "风险林班",
        "linkedUnit": "个",
        "activeLabel": "待处置",
        "columns": ["预警名称", "风险类型", "风险林班", "预警状态"],
    },
    "material-services": {
        "title": "农资服务信息卡",
        "subtitle": "农资配送、领用服务、供应协同与服务反馈",
        "totalLabel": "服务单",
        "totalUnit": "张",
        "linkedLabel": "服务林班",
        "linkedUnit": "个",
        "activeLabel": "服务中",
        "columns": ["服务名称", "服务类型", "服务林班", "服务状态"],
    },
    "yield-forecasts": {
        "title": "产量预测信息卡",
        "subtitle": "竹材、竹笋、林下经济等产量预测与模型参数",
        "totalLabel": "预测方案",
        "totalUnit": "个",
        "linkedLabel": "预测林班",
        "linkedUnit": "个",
        "activeLabel": "生效预测",
        "columns": ["预测名称", "预测对象", "预测林班", "预测状态"],
    },
    "harvest-plans": {
        "title": "采挖计划信息卡",
        "subtitle": "采伐、挖笋、抚育采收计划与执行排程",
        "totalLabel": "采挖计划",
        "totalUnit": "项",
        "linkedLabel": "计划林班",
        "linkedUnit": "个",
        "activeLabel": "执行中",
        "columns": ["计划名称", "采挖类型", "计划林班", "执行状态"],
    },
    "income-estimates": {
        "title": "收益测算信息卡",
        "subtitle": "经营收益、成本投入、现金流和主体分成测算",
        "totalLabel": "测算方案",
        "totalUnit": "个",
        "linkedLabel": "测算林班",
        "linkedUnit": "个",
        "activeLabel": "有效测算",
        "columns": ["测算名称", "测算类型", "测算林班", "测算状态"],
    },
    "performance-dashboards": {
        "title": "绩效看板信息卡",
        "subtitle": "管护绩效、经营绩效、主体绩效与指标口径",
        "totalLabel": "绩效看板",
        "totalUnit": "个",
        "linkedLabel": "覆盖林班",
        "linkedUnit": "个",
        "activeLabel": "已发布",
        "columns": ["看板名称", "指标类型", "覆盖林班", "发布状态"],
    },
    "carbon-estimates": {
        "title": "碳汇测算信息卡",
        "subtitle": "碳储量、碳汇增量、项目边界与核证测算",
        "totalLabel": "碳汇项目",
        "totalUnit": "个",
        "linkedLabel": "核算林班",
        "linkedUnit": "个",
        "activeLabel": "测算中",
        "columns": ["测算名称", "核算类型", "核算林班", "测算状态"],
    },
    "trade-matches": {
        "title": "交易撮合信息卡",
        "subtitle": "竹材、竹笋、林下产品供需发布、询价报价与订单撮合",
        "totalLabel": "撮合单",
        "totalUnit": "笔",
        "linkedLabel": "关联林班",
        "linkedUnit": "个",
        "activeLabel": "撮合中",
        "columns": ["交易名称", "供需类型", "关联林班", "撮合状态"],
    },
    "logistics-traces": {
        "title": "物流溯源信息卡",
        "subtitle": "采收批次、运输节点、仓储流转与质量追溯记录",
        "totalLabel": "溯源批次",
        "totalUnit": "批",
        "linkedLabel": "来源林班",
        "linkedUnit": "个",
        "activeLabel": "流转中",
        "columns": ["批次名称", "物流节点", "来源林班", "流转状态"],
    },
    "product-qrcodes": {
        "title": "二维码信息卡",
        "subtitle": "林班、批次、产品、订单二维码生成与扫码访问配置",
        "totalLabel": "二维码",
        "totalUnit": "个",
        "linkedLabel": "绑定林班",
        "linkedUnit": "个",
        "activeLabel": "已启用",
        "columns": ["二维码名称", "码类型", "绑定林班", "启用状态"],
    },
    "supply-chain-finance": {
        "title": "供应链金融信息卡",
        "subtitle": "订单融资、库存质押、主体授信与还款风险台账",
        "totalLabel": "金融事项",
        "totalUnit": "笔",
        "linkedLabel": "关联林班",
        "linkedUnit": "个",
        "activeLabel": "处理中",
        "columns": ["事项名称", "金融类型", "关联林班", "办理状态"],
    },
    "price-indexes": {
        "title": "价格指数信息卡",
        "subtitle": "竹材、竹笋、加工品价格采集、指数发布与行情监测",
        "totalLabel": "指数项",
        "totalUnit": "项",
        "linkedLabel": "采样林班",
        "linkedUnit": "个",
        "activeLabel": "已发布",
        "columns": ["指数名称", "品类", "采样林班", "发布状态"],
    },
    "mobile-service-channels": {
        "title": "移动端服务信息卡",
        "subtitle": "林农、合作社、企业移动端功能入口、服务事项与上线状态",
        "totalLabel": "服务入口",
        "totalUnit": "个",
        "linkedLabel": "服务林班",
        "linkedUnit": "个",
        "activeLabel": "已上线",
        "columns": ["入口名称", "服务对象", "服务林班", "上线状态"],
    },
}


def field_option(value: str, label: str) -> dict[str, str]:
    return {"value": value, "label": label}


BUSINESS_FIELD_SCHEMAS: dict[str, list[dict[str, Any]]] = {
    "farmers": [
        {
            "key": "identityType",
            "label": "证件类型",
            "section": "身份信息",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("resident-id", "居民身份证"),
                field_option("unified-social-credit", "统一社会信用代码"),
                field_option("other", "其他证件"),
            ],
        },
        {
            "key": "identityNumber",
            "label": "证件号码",
            "section": "身份信息",
            "inputType": "text",
            "required": True,
            "minLength": 6,
            "maxLength": 30,
            "pattern": r"^[0-9A-Za-z()（）-]{6,30}$",
        },
        {
            "key": "phone",
            "label": "联系电话",
            "section": "身份信息",
            "inputType": "tel",
            "required": True,
            "pattern": r"^1[3-9]\d{9}$",
            "maxLength": 11,
        },
        {
            "key": "provinceCode",
            "label": "所属省份",
            "section": "行政区划",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/dictionary-options/administrative-divisions?level=province",
            "referenceValueKey": "value",
            "referenceLabelKey": "fullName",
            "multiple": False,
            "referenceDictionaryCode": "administrative-divisions",
            "referenceLevel": "province",
            "displayProperty": "provinceName",
        },
        {
            "key": "cityCode",
            "label": "所属地市",
            "section": "行政区划",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/dictionary-options/administrative-divisions?level=city",
            "referenceValueKey": "value",
            "referenceLabelKey": "fullName",
            "multiple": False,
            "referenceDictionaryCode": "administrative-divisions",
            "referenceLevel": "city",
            "parentField": "provinceCode",
            "displayProperty": "cityName",
        },
        {
            "key": "countyCode",
            "label": "所属区县",
            "section": "行政区划",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/dictionary-options/administrative-divisions?level=county",
            "referenceValueKey": "value",
            "referenceLabelKey": "fullName",
            "multiple": False,
            "referenceDictionaryCode": "administrative-divisions",
            "referenceLevel": "county",
            "parentField": "cityCode",
            "displayProperty": "countyName",
        },
        {
            "key": "townCode",
            "label": "所属乡镇",
            "section": "行政区划",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/dictionary-options/administrative-divisions?level=town",
            "referenceValueKey": "value",
            "referenceLabelKey": "fullName",
            "multiple": False,
            "referenceDictionaryCode": "administrative-divisions",
            "referenceLevel": "town",
            "parentField": "countyCode",
            "displayProperty": "townName",
        },
        {
            "key": "villageCode",
            "label": "所属村",
            "section": "行政区划",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/dictionary-options/administrative-divisions?level=village",
            "referenceValueKey": "value",
            "referenceLabelKey": "fullName",
            "multiple": False,
            "referenceDictionaryCode": "administrative-divisions",
            "referenceLevel": "village",
            "parentField": "townCode",
            "displayProperty": "villageName",
        },
        {
            "key": "address",
            "label": "详细地址",
            "section": "经营档案",
            "inputType": "textarea",
            "required": True,
            "maxLength": 300,
        },
        {
            "key": "operationAreaMu",
            "label": "经营面积",
            "section": "经营档案",
            "inputType": "number",
            "required": True,
            "unit": "亩",
            "min": 0,
            "step": 0.01,
        },
        {
            "key": "cooperativeIds",
            "label": "所属合作社",
            "section": "业务关联",
            "inputType": "business-relation",
            "referenceEndpoint": "/api/references/business/cooperatives",
            "referenceValueKey": "id",
            "referenceLabelKey": "name",
            "relationType": "member-of",
            "targetModuleKey": "cooperatives",
            "multiple": True,
            "allowedTargetStatuses": ["active"],
        },
    ],
    "cooperatives": [
        {
            "key": "serviceArea",
            "label": "服务范围",
            "inputType": "multi-reference",
            "required": True,
            "referenceEndpoint": "/api/dictionary-options/administrative-divisions",
            "referenceValueKey": "label",
            "referenceLabelKey": "fullName",
        },
        {"key": "memberCount", "label": "成员数量", "inputType": "integer", "unit": "人", "min": 0},
        {"key": "serviceCapacity", "label": "服务能力", "inputType": "text"},
        {
            "key": "orderStatus",
            "label": "订单状态",
            "inputType": "select",
            "options": [
                field_option("idle", "暂无订单"),
                field_option("active", "服务中"),
                field_option("busy", "任务饱和"),
                field_option("paused", "暂停服务"),
            ],
        },
    ],
    "enterprises": [
        {
            "key": "mainBusiness",
            "label": "主营方向",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("raw-bamboo", "原竹经营"),
                field_option("bamboo-shoot", "竹笋经营"),
                field_option("primary-processing", "竹材初加工"),
                field_option("deep-processing", "竹制品深加工"),
                field_option("equipment-service", "设备与技术服务"),
                field_option("trade-logistics", "贸易与物流"),
                field_option("comprehensive", "综合经营"),
            ],
        },
        {
            "key": "contactName",
            "label": "联系人",
            "inputType": "reference",
            "referenceEndpoint": "/api/business-reference-options/people",
            "referenceValueKey": "value",
            "referenceLabelKey": "label",
        },
        {
            "key": "purchaseStatus",
            "label": "采购状态",
            "inputType": "select",
            "options": [field_option("planning", "采购计划"), field_option("purchasing", "采购中"), field_option("completed", "已完成")],
        },
        {
            "key": "inventoryStatus",
            "label": "库存状态",
            "inputType": "select",
            "options": [field_option("normal", "库存正常"), field_option("low", "库存偏低"), field_option("high", "库存偏高")],
        },
    ],
    "plant-protection-events": [
        {
            "key": "issueType",
            "label": "问题类型",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("bamboo-locust", "竹蝗"),
                field_option("bamboo-shoot-pest", "竹笋害虫"),
                field_option("bamboo-witch-broom", "竹丛枝病"),
                field_option("bamboo-rust", "竹锈病"),
                field_option("rodent-damage", "鼠害"),
                field_option("other", "其他"),
            ],
        },
        {
            "key": "riskLevel",
            "label": "风险等级",
            "inputType": "dictionary",
            "dictionaryCode": "risk-levels",
        },
        {"key": "treatmentAdvice", "label": "处置建议", "inputType": "textarea"},
        {
            "key": "handlingStatus",
            "label": "处置状态",
            "inputType": "select",
            "options": [field_option("pending", "待处置"), field_option("handling", "处置中"), field_option("resolved", "已处置"), field_option("verified", "已复核")],
        },
    ],
    "materials": [
        {
            "key": "itemCategory",
            "label": "物资品类",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("fertilizer", "肥料"),
                field_option("pesticide", "植保药剂"),
                field_option("seedling", "苗木"),
                field_option("tool", "生产工具"),
                field_option("protective-equipment", "防护用品"),
                field_option("other", "其他"),
            ],
        },
        {"key": "stock", "label": "库存数量", "inputType": "number", "min": 0, "step": 0.01},
        {"key": "unit", "label": "计量单位", "inputType": "dictionary", "dictionaryCode": "material-units"},
        {
            "key": "usageStage",
            "label": "适用环节",
            "inputType": "select",
            "options": [
                field_option("planting", "栽植"),
                field_option("tending", "抚育"),
                field_option("fertilizing", "施肥"),
                field_option("plant-protection", "植保"),
                field_option("harvesting", "采收"),
                field_option("transport", "运输"),
                field_option("general", "通用"),
            ],
        },
        {
            "key": "inventoryStatus",
            "label": "库存状态",
            "inputType": "select",
            "options": [field_option("normal", "库存正常"), field_option("warning", "库存预警"), field_option("out", "缺货")],
        },
    ],
    "policies": [
        {
            "key": "target",
            "label": "适用对象",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("farmer", "竹农"),
                field_option("cooperative", "合作社"),
                field_option("enterprise", "竹企"),
                field_option("village-collective", "村集体"),
                field_option("operator", "经营主体"),
                field_option("all", "全部主体"),
            ],
        },
        {"key": "applicationItem", "label": "申报事项", "inputType": "text"},
        {"key": "deadline", "label": "截止日期", "inputType": "date"},
        {
            "key": "reviewStatus",
            "label": "申报状态",
            "inputType": "select",
            "options": [field_option("open", "可申报"), field_option("review", "审核中"), field_option("closed", "已截止")],
        },
    ],
    "stewardship-agreements": [
        {
            "key": "serviceProvider",
            "label": "托管主体",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/business/cooperatives",
            "referenceValueKey": "recordCode",
            "referenceLabelKey": "name",
        },
        {"key": "contractTerm", "label": "协议期限", "inputType": "text", "required": True},
        {"key": "areaMu", "label": "托管面积", "inputType": "number", "unit": "亩", "min": 0, "step": 0.01},
        {
            "key": "performanceStatus",
            "label": "履约状态",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("pending", "待履约"),
                field_option("active", "履约中"),
                field_option("completed", "已完成"),
                field_option("breached", "违约"),
                field_option("terminated", "已终止"),
            ],
        },
    ],
    "franchise-bases": [
        {
            "key": "region",
            "label": "所在区域",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/dictionary-options/administrative-divisions",
            "referenceValueKey": "label",
            "referenceLabelKey": "fullName",
            "multiple": False,
        },
        {
            "key": "operator",
            "label": "经营主体",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/business/enterprises",
            "referenceValueKey": "recordCode",
            "referenceLabelKey": "name",
        },
        {"key": "baseAreaMu", "label": "基地面积", "inputType": "number", "unit": "亩", "min": 0, "step": 0.01},
        {
            "key": "serviceLevel",
            "label": "服务等级",
            "inputType": "select",
            "options": [field_option("A", "A级"), field_option("B", "B级"), field_option("C", "C级")],
        },
        {
            "key": "operationStatus",
            "label": "运营状态",
            "inputType": "select",
            "options": [
                field_option("preparing", "筹备中"),
                field_option("active", "运营中"),
                field_option("paused", "暂停运营"),
                field_option("closed", "已关闭"),
            ],
        },
    ],
    "maintenance-tasks": [
        {
            "key": "taskType",
            "label": "任务类型",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("patrol", "巡护"),
                field_option("tending", "抚育"),
                field_option("fire-prevention", "防火"),
                field_option("anti-theft", "防盗伐"),
                field_option("other", "其他"),
            ],
        },
        {
            "key": "assignee",
            "label": "责任人/责任主体",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/business-reference-options/subjects",
            "referenceValueKey": "value",
            "referenceLabelKey": "label",
        },
        {"key": "planDate", "label": "计划日期", "inputType": "date", "required": True},
        {
            "key": "closureStatus",
            "label": "闭环状态",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("pending", "待处理"),
                field_option("in-progress", "处理中"),
                field_option("completed", "已完成"),
                field_option("verified", "已复核"),
                field_option("canceled", "已取消"),
            ],
        },
    ],
    "work-logs": [
        {
            "key": "workStage",
            "label": "作业环节",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("harvesting", "采伐"),
                field_option("shoot-digging", "挖笋"),
                field_option("fertilizing", "施肥"),
                field_option("weeding", "除草"),
                field_option("transport", "运输"),
                field_option("other", "其他"),
            ],
        },
        {
            "key": "worker",
            "label": "作业人/班组",
            "inputType": "multi-reference",
            "required": True,
            "referenceEndpoint": "/api/business-reference-options/people",
            "referenceValueKey": "value",
            "referenceLabelKey": "label",
        },
        {"key": "workDate", "label": "作业日期", "inputType": "date", "required": True},
        {"key": "laborCount", "label": "用工人数", "inputType": "integer", "unit": "人", "min": 0, "step": 1},
    ],
    "drone-tasks": [
        {
            "key": "taskType",
            "label": "任务类型",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("mapping", "测绘"),
                field_option("inspection", "巡检"),
                field_option("plant-protection", "植保"),
                field_option("emergency", "应急"),
            ],
        },
        {
            "key": "deviceCode",
            "label": "无人机编号",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/business/equipment",
            "referenceValueKey": "recordCode",
            "referenceLabelKey": "name",
        },
        {"key": "routeCode", "label": "航线编号", "inputType": "text"},
        {
            "key": "resultStatus",
            "label": "成果状态",
            "inputType": "select",
            "options": [
                field_option("pending", "待执行"),
                field_option("flying", "飞行中"),
                field_option("processing", "成果处理中"),
                field_option("ready", "成果已入库"),
                field_option("failed", "任务失败"),
            ],
        },
    ],
    "equipment": [
        {
            "key": "deviceType",
            "label": "设备类型",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("drone", "无人机"),
                field_option("sensor", "传感器"),
                field_option("camera", "视频监控"),
                field_option("positioning", "定位终端"),
                field_option("other", "其他"),
            ],
        },
        {"key": "deviceCode", "label": "设备编号", "inputType": "text", "required": True},
        {"key": "installLocation", "label": "安装位置", "inputType": "text"},
        {
            "key": "onlineStatus",
            "label": "运行状态",
            "inputType": "select",
            "options": [
                field_option("online", "在线"),
                field_option("offline", "离线"),
                field_option("maintenance", "检修中"),
                field_option("retired", "已报废"),
            ],
        },
    ],
    "pest-warnings": [
        {
            "key": "riskType",
            "label": "病虫害类型",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("bamboo-locust", "竹蝗"),
                field_option("bamboo-shoot-pest", "竹笋害虫"),
                field_option("bamboo-witch-broom", "竹丛枝病"),
                field_option("bamboo-rust", "竹锈病"),
                field_option("rodent-damage", "鼠害"),
                field_option("other", "其他"),
            ],
        },
        {
            "key": "riskLevel",
            "label": "风险等级",
            "inputType": "dictionary",
            "dictionaryCode": "risk-levels",
            "required": True,
        },
        {"key": "treatmentAdvice", "label": "处置建议", "inputType": "textarea"},
        {
            "key": "reviewStatus",
            "label": "复核状态",
            "inputType": "select",
            "options": [
                field_option("pending", "待处置"),
                field_option("handling", "处置中"),
                field_option("resolved", "已处置"),
                field_option("verified", "已复核"),
            ],
        },
    ],
    "material-services": [
        {
            "key": "serviceType",
            "label": "服务类型",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("fertilizer", "肥料配送"),
                field_option("pesticide", "药剂配送"),
                field_option("tools", "工具设备"),
                field_option("technical", "技术服务"),
            ],
        },
        {
            "key": "supplier",
            "label": "供应商",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/business/enterprises",
            "referenceValueKey": "recordCode",
            "referenceLabelKey": "name",
        },
        {
            "key": "deliveryStatus",
            "label": "配送状态",
            "inputType": "select",
            "options": [
                field_option("pending", "待受理"),
                field_option("preparing", "备货中"),
                field_option("delivering", "配送中"),
                field_option("delivered", "已送达"),
                field_option("canceled", "已取消"),
            ],
        },
        {
            "key": "feedbackStatus",
            "label": "反馈状态",
            "inputType": "select",
            "options": [
                field_option("pending", "待反馈"),
                field_option("satisfied", "满意"),
                field_option("follow-up", "需跟进"),
                field_option("closed", "已闭环"),
            ],
        },
    ],
    "yield-forecasts": [
        {
            "key": "forecastObject",
            "label": "预测对象",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("bamboo-timber", "竹材"),
                field_option("bamboo-shoot", "竹笋"),
                field_option("understory", "林下经济"),
            ],
        },
        {"key": "forecastPeriod", "label": "预测周期", "inputType": "month", "required": True},
        {"key": "forecastYield", "label": "预测产量", "inputType": "number", "unit": "吨", "min": 0, "step": 0.01},
        {"key": "modelName", "label": "模型名称/版本", "inputType": "text", "required": True},
        {"key": "confidence", "label": "置信度", "inputType": "number", "unit": "%", "min": 0, "max": 100, "step": 0.1},
    ],
    "harvest-plans": [
        {
            "key": "harvestType",
            "label": "采挖类型",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("timber", "竹材采伐"),
                field_option("shoot", "竹笋采挖"),
                field_option("tending", "抚育采收"),
            ],
        },
        {"key": "planDate", "label": "计划日期", "inputType": "date", "required": True},
        {"key": "plannedQuantity", "label": "计划数量", "inputType": "number", "unit": "吨", "min": 0, "step": 0.01},
        {
            "key": "executionStatus",
            "label": "执行状态",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("draft", "草稿"),
                field_option("approved", "已审批"),
                field_option("in-progress", "执行中"),
                field_option("completed", "已完成"),
                field_option("canceled", "已取消"),
            ],
        },
    ],
    "income-estimates": [
        {
            "key": "estimateType",
            "label": "测算类型",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("gross-income", "经营收入"),
                field_option("net-income", "净收益"),
                field_option("cash-flow", "现金流"),
                field_option("distribution", "主体分成"),
            ],
        },
        {"key": "estimatePeriod", "label": "测算周期", "inputType": "month", "required": True},
        {"key": "expectedIncome", "label": "预计收入", "inputType": "number", "unit": "元", "min": 0, "step": 0.01},
        {"key": "cost", "label": "预计成本", "inputType": "number", "unit": "元", "min": 0, "step": 0.01},
        {"key": "netIncome", "label": "预计净收益", "inputType": "number", "unit": "元", "step": 0.01, "readOnly": True},
    ],
    "performance-dashboards": [
        {
            "key": "metricType",
            "label": "指标类型",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("maintenance", "管护绩效"),
                field_option("operation", "经营绩效"),
                field_option("organization", "主体绩效"),
            ],
        },
        {
            "key": "coverage",
            "label": "覆盖范围",
            "inputType": "multi-reference",
            "referenceEndpoint": "/api/dictionary-options/administrative-divisions",
            "referenceValueKey": "label",
            "referenceLabelKey": "fullName",
        },
        {"key": "metricCaliber", "label": "指标口径", "inputType": "textarea", "required": True},
        {"key": "metricValue", "label": "指标值", "inputType": "number", "step": 0.01},
        {
            "key": "publishStatus",
            "label": "发布状态",
            "inputType": "select",
            "options": [
                field_option("draft", "草稿"),
                field_option("review", "待审核"),
                field_option("published", "已发布"),
                field_option("offline", "已下线"),
            ],
        },
    ],
    "carbon-estimates": [
        {
            "key": "accountingType",
            "label": "核算类型",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("stock", "碳储量"),
                field_option("increment", "碳汇增量"),
                field_option("project", "项目减排量"),
            ],
        },
        {"key": "projectBoundary", "label": "项目边界", "inputType": "text", "required": True},
        {"key": "carbonStock", "label": "碳储量/减排量", "inputType": "number", "unit": "tCO2e", "min": 0, "step": 0.01},
        {"key": "methodology", "label": "核算方法学", "inputType": "text"},
        {"key": "accountingStartDate", "label": "核算开始日期", "inputType": "date"},
        {"key": "accountingEndDate", "label": "核算结束日期", "inputType": "date"},
        {"key": "accountingAreaMu", "label": "核算面积", "inputType": "number", "unit": "亩", "min": 0, "step": 0.01},
        {"key": "annualSequestration", "label": "年碳汇量", "inputType": "number", "unit": "tCO2e", "min": 0, "step": 0.01},
        {"key": "verifiedAmount", "label": "核证减排量", "inputType": "number", "unit": "tCO2e", "min": 0, "step": 0.01},
        {"key": "carbonPrice", "label": "碳价", "inputType": "number", "unit": "元/tCO2e", "min": 0, "step": 0.01},
        {"key": "estimatedRevenue", "label": "预计收益", "inputType": "number", "unit": "元", "min": 0, "step": 0.01},
        {"key": "verificationAgency", "label": "核证机构", "inputType": "text"},
        {"key": "verificationDate", "label": "核证日期", "inputType": "date"},
        {"key": "beneficiary", "label": "收益主体", "inputType": "text"},
        {"key": "notes", "label": "测算说明", "inputType": "textarea"},
        {
            "key": "verificationStatus",
            "label": "核证状态",
            "inputType": "select",
            "options": [
                field_option("calculating", "测算中"),
                field_option("review", "待复核"),
                field_option("verified", "已核证"),
                field_option("rejected", "未通过"),
            ],
        },
    ],
    "trade-matches": [
        {
            "key": "tradeType",
            "label": "供需类型",
            "inputType": "select",
            "required": True,
            "options": [field_option("supply", "供应"), field_option("demand", "采购需求")],
        },
        {
            "key": "productType",
            "label": "产品品类",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("bamboo-timber", "竹材"),
                field_option("bamboo-shoot", "竹笋"),
                field_option("processed", "竹加工品"),
                field_option("understory", "林下产品"),
            ],
        },
        {"key": "quantity", "label": "交易数量", "inputType": "number", "unit": "吨", "min": 0, "step": 0.01},
        {"key": "unitPrice", "label": "意向单价", "inputType": "number", "unit": "元/吨", "min": 0, "step": 0.01},
        {
            "key": "counterparty",
            "label": "对接主体",
            "inputType": "reference",
            "referenceEndpoint": "/api/business-reference-options/subjects",
            "referenceValueKey": "value",
            "referenceLabelKey": "label",
        },
        {
            "key": "matchStatus",
            "label": "撮合状态",
            "inputType": "select",
            "options": [
                field_option("pending", "待撮合"),
                field_option("negotiating", "洽谈中"),
                field_option("matched", "已撮合"),
                field_option("closed", "已成交"),
                field_option("canceled", "已取消"),
            ],
        },
    ],
    "logistics-traces": [
        {"key": "batchNo", "label": "溯源批次", "inputType": "text", "required": True},
        {
            "key": "carrier",
            "label": "承运单位/司机",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/business/enterprises",
            "referenceValueKey": "recordCode",
            "referenceLabelKey": "name",
        },
        {"key": "currentNode", "label": "当前节点", "inputType": "text", "required": True},
        {"key": "quantity", "label": "流转数量", "inputType": "number", "unit": "吨", "min": 0, "step": 0.01},
        {
            "key": "logisticsStatus",
            "label": "物流状态",
            "inputType": "select",
            "options": [
                field_option("collected", "已采收"),
                field_option("in-transit", "运输中"),
                field_option("warehoused", "已入库"),
                field_option("delivered", "已交付"),
                field_option("exception", "异常"),
            ],
        },
    ],
    "product-qrcodes": [
        {"key": "qrCode", "label": "二维码编号", "inputType": "text", "readOnly": True},
        {
            "key": "codeType",
            "label": "码类型",
            "inputType": "select",
            "options": [
                field_option("product", "产品码"),
                field_option("batch", "批次码"),
                field_option("forest-block", "林班码"),
                field_option("order", "订单码"),
            ],
        },
        {
            "key": "productType",
            "label": "产品品类",
            "inputType": "select",
            "options": [
                field_option("bamboo-timber", "竹材"),
                field_option("bamboo-shoot", "竹笋"),
                field_option("processed", "竹加工品"),
            ],
        },
        {"key": "batchNo", "label": "产品批次", "inputType": "text"},
        {"key": "targetUrl", "label": "扫码地址", "inputType": "text"},
        {
            "key": "publishStatus",
            "label": "启用状态",
            "inputType": "select",
            "options": [field_option("draft", "草稿"), field_option("published", "已启用"), field_option("disabled", "已停用")],
        },
        {"key": "scanCount", "label": "扫码次数", "inputType": "integer", "min": 0, "readOnly": True},
    ],
    "supply-chain-finance": [
        {
            "key": "financeProduct",
            "label": "金融产品",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("order-finance", "订单融资"),
                field_option("inventory-pledge", "库存质押"),
                field_option("credit", "主体授信"),
            ],
        },
        {
            "key": "borrower",
            "label": "融资主体",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/business-reference-options/subjects",
            "referenceValueKey": "value",
            "referenceLabelKey": "label",
        },
        {"key": "amount", "label": "申请金额", "inputType": "number", "unit": "元", "min": 0, "step": 0.01},
        {"key": "dueDate", "label": "到期日期", "inputType": "date"},
        {
            "key": "reviewStatus",
            "label": "审核状态",
            "inputType": "select",
            "options": [
                field_option("draft", "草稿"),
                field_option("review", "审核中"),
                field_option("approved", "已通过"),
                field_option("rejected", "已驳回"),
                field_option("repaid", "已结清"),
            ],
        },
        {
            "key": "riskLevel",
            "label": "风险等级",
            "inputType": "select",
            "options": [field_option("low", "低"), field_option("medium", "中"), field_option("high", "高")],
        },
    ],
    "price-indexes": [
        {
            "key": "productType",
            "label": "产品品类",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("bamboo-timber", "竹材"),
                field_option("bamboo-shoot", "竹笋"),
                field_option("processed", "竹加工品"),
            ],
        },
        {
            "key": "region",
            "label": "采样区域/市场",
            "inputType": "reference",
            "required": True,
            "referenceEndpoint": "/api/dictionary-options/administrative-divisions",
            "referenceValueKey": "label",
            "referenceLabelKey": "fullName",
            "multiple": False,
        },
        {"key": "price", "label": "价格", "inputType": "number", "unit": "元/吨", "min": 0, "step": 0.01},
        {"key": "period", "label": "采样周期", "inputType": "month", "required": True},
        {
            "key": "publishStatus",
            "label": "发布状态",
            "inputType": "select",
            "options": [field_option("draft", "草稿"), field_option("review", "待审核"), field_option("published", "已发布")],
        },
    ],
    "mobile-service-channels": [
        {
            "key": "target",
            "label": "服务对象",
            "inputType": "select",
            "required": True,
            "options": [
                field_option("farmer", "竹农"),
                field_option("cooperative", "合作社"),
                field_option("enterprise", "竹企"),
                field_option("manager", "管理人员"),
            ],
        },
        {
            "key": "channel",
            "label": "服务渠道",
            "inputType": "select",
            "required": True,
            "options": [field_option("wechat", "微信端"), field_option("app", "移动 App"), field_option("h5", "H5")],
        },
        {"key": "entry", "label": "功能入口", "inputType": "text", "required": True},
        {
            "key": "ownerName",
            "label": "负责人",
            "inputType": "reference",
            "referenceEndpoint": "/api/business-reference-options/people",
            "referenceValueKey": "value",
            "referenceLabelKey": "label",
        },
        {
            "key": "publishStatus",
            "label": "上线状态",
            "inputType": "select",
            "options": [field_option("draft", "开发中"), field_option("review", "待上线"), field_option("published", "已上线"), field_option("offline", "已下线")],
        },
    ],
}

BUSINESS_FIELD_SCHEMAS.update(FORMAL_BUSINESS_FIELD_SCHEMAS)
for formal_module_key in FORMAL_BUSINESS_FIELD_SCHEMAS:
    BUSINESS_MODULES[formal_module_key]["formVersion"] = 2


def business_dictionary_code(module_key: str, field_key: str) -> str:
    kebab_field = re.sub(r"(?<!^)(?=[A-Z])", "-", field_key).lower().replace("_", "-")
    return f"business-{module_key}-{kebab_field}"


for business_module_key, field_schema in BUSINESS_FIELD_SCHEMAS.items():
    for field in field_schema:
        if field.get("inputType") != "select":
            continue
        field["inputType"] = "dictionary"
        field.setdefault(
            "dictionaryCode",
            business_dictionary_code(business_module_key, str(field.get("key") or "field")),
        )


for business_module_key, field_schema in BUSINESS_FIELD_SCHEMAS.items():
    BUSINESS_MODULES[business_module_key]["fieldSchema"] = field_schema


BUSINESS_DASHBOARD_FIELDS = {
    "farmers": ["@location", "@linked", "@status"],
    "cooperatives": ["serviceArea", "@linked", "orderStatus"],
    "enterprises": ["mainBusiness", "@linked", "inventoryStatus"],
    "stewardship-agreements": ["serviceProvider", "@linked", "performanceStatus"],
    "franchise-bases": ["region", "@linked", "operationStatus"],
    "maintenance-tasks": ["taskType", "@linked", "closureStatus"],
    "work-logs": ["workStage", "@linked", "@status"],
    "drone-tasks": ["taskType", "@linked", "resultStatus"],
    "equipment": ["deviceType", "@linked", "onlineStatus"],
    "pest-warnings": ["riskType", "@linked", "reviewStatus"],
    "material-services": ["serviceType", "@linked", "deliveryStatus"],
    "yield-forecasts": ["forecastObject", "@linked", "@status"],
    "harvest-plans": ["harvestType", "@linked", "executionStatus"],
    "income-estimates": ["estimateType", "@linked", "@status"],
    "performance-dashboards": ["metricType", "@linked", "publishStatus"],
    "carbon-estimates": ["accountingType", "@linked", "verificationStatus"],
    "trade-matches": ["tradeType", "@linked", "matchStatus"],
    "logistics-traces": ["currentNode", "@linked", "logisticsStatus"],
    "product-qrcodes": ["codeType", "@linked", "publishStatus"],
    "supply-chain-finance": ["financeProduct", "@linked", "reviewStatus"],
    "price-indexes": ["productType", "@linked", "publishStatus"],
    "mobile-service-channels": ["target", "@linked", "publishStatus"],
}

BUSINESS_ACTIVITY_RULES = {
    "farmers": ("@status", {"active", "published", "open"}),
    "cooperatives": ("orderStatus", {"active", "busy"}),
    "enterprises": ("purchaseStatus", {"planning", "purchasing"}),
    "plant-protection-events": ("handlingStatus", {"pending", "handling"}),
    "materials": ("inventoryStatus", {"normal", "warning"}),
    "policies": ("reviewStatus", {"open", "review"}),
    "stewardship-agreements": ("performanceStatus", {"active"}),
    "franchise-bases": ("operationStatus", {"active"}),
    "maintenance-tasks": ("closureStatus", {"pending", "in-progress"}),
    "work-logs": ("@status", {"active", "published", "open"}),
    "drone-tasks": ("resultStatus", {"pending", "flying", "processing"}),
    "equipment": ("onlineStatus", {"online"}),
    "pest-warnings": ("reviewStatus", {"pending", "handling"}),
    "material-services": ("deliveryStatus", {"pending", "preparing", "delivering"}),
    "yield-forecasts": ("@status", {"active", "published"}),
    "harvest-plans": ("executionStatus", {"approved", "in-progress"}),
    "income-estimates": ("@status", {"active", "published"}),
    "performance-dashboards": ("publishStatus", {"published"}),
    "carbon-estimates": ("verificationStatus", {"calculating", "review"}),
    "trade-matches": ("matchStatus", {"pending", "negotiating", "matched"}),
    "logistics-traces": ("logisticsStatus", {"collected", "in-transit", "warehoused"}),
    "product-qrcodes": ("publishStatus", {"published"}),
    "supply-chain-finance": ("reviewStatus", {"review", "approved"}),
    "price-indexes": ("publishStatus", {"published"}),
    "mobile-service-channels": ("publishStatus", {"published"}),
}

BUSINESS_AGGREGATE_RULES = {
    "farmers": [("managedAreaMu", "经营面积", "亩", "sum")],
    "cooperatives": [("memberCount", "成员数量", "人", "sum")],
    "materials": [("stock", "库存数量", "", "sum")],
    "yield-forecasts": [("forecastYield", "预测产量", "吨", "sum")],
    "harvest-plans": [("plannedQuantity", "计划数量", "吨", "sum")],
    "income-estimates": [
        ("expectedIncome", "预计收入", "元", "sum"),
        ("cost", "预计成本", "元", "sum"),
        ("netIncome", "预计净收益", "元", "sum"),
    ],
    "performance-dashboards": [("metricValue", "平均指标值", "", "average")],
    "carbon-estimates": [("carbonStock", "碳储量", "tCO2e", "sum")],
    "trade-matches": [("quantity", "撮合数量", "吨", "sum")],
    "logistics-traces": [("quantity", "流转数量", "吨", "sum")],
    "product-qrcodes": [("scanCount", "扫码次数", "次", "sum")],
    "supply-chain-finance": [("amount", "融资金额", "元", "sum")],
    "price-indexes": [("price", "平均价格", "元/吨", "average")],
}

BUSINESS_MODULE_PERMISSIONS = {
    "farmers": "business.farmers.manage",
    "cooperatives": "business.cooperatives.manage",
    "enterprises": "business.enterprises.manage",
    "plant-protection-events": "business.plantProtection.manage",
    "materials": "business.materials.manage",
    "policies": "business.policies.manage",
    "stewardship-agreements": "business.stewardshipAgreements.manage",
    "franchise-bases": "business.franchiseBases.manage",
    "maintenance-tasks": "business.maintenanceTasks.manage",
    "work-logs": "business.workLogs.manage",
    "drone-tasks": "business.droneTasks.manage",
    "equipment": "business.equipment.manage",
    "pest-warnings": "business.pestWarnings.manage",
    "material-services": "business.materialServices.manage",
    "yield-forecasts": "business.yieldForecasts.manage",
    "harvest-plans": "business.harvestPlans.manage",
    "income-estimates": "business.incomeEstimates.manage",
    "performance-dashboards": "business.performanceDashboards.manage",
    "carbon-estimates": "business.carbonEstimates.manage",
    "trade-matches": "business.tradeMatches.manage",
    "logistics-traces": "business.logisticsTraces.manage",
    "product-qrcodes": "business.productQrcodes.manage",
    "supply-chain-finance": "business.supplyChainFinance.manage",
    "price-indexes": "business.priceIndexes.manage",
    "mobile-service-channels": "business.mobileServiceChannels.manage",
}
BUSINESS_ACTIONS = {"view", "create", "update", "delete", "restore", "export", "manage"}

BUSINESS_ADMIN_PAGES = {
    "farmers": "admin-farmers.html",
    "cooperatives": "admin-cooperatives.html",
    "enterprises": "admin-enterprises.html",
    "plant-protection-events": "admin-plant-protection.html",
    "materials": "admin-materials.html",
    "policies": "admin-policies.html",
    "stewardship-agreements": "admin-stewardship-agreements.html",
    "franchise-bases": "admin-franchise-bases.html",
    "maintenance-tasks": "admin-maintenance-tasks.html",
    "work-logs": "admin-work-logs.html",
    "drone-tasks": "admin-drone-tasks.html",
    "equipment": "admin-equipment.html",
    "pest-warnings": "admin-pest-warnings.html",
    "material-services": "admin-material-services.html",
    "yield-forecasts": "admin-yield-forecasts.html",
    "harvest-plans": "admin-harvest-plans.html",
    "income-estimates": "admin-income-estimates.html",
    "performance-dashboards": "admin-performance-dashboards.html",
    "carbon-estimates": "admin-carbon-estimates.html",
    "trade-matches": "admin-trade-matches.html",
    "logistics-traces": "admin-logistics-traces.html",
    "product-qrcodes": "admin-product-qrcodes.html",
    "supply-chain-finance": "admin-supply-chain-finance.html",
    "price-indexes": "admin-price-indexes.html",
    "mobile-service-channels": "admin-mobile-service-channels.html",
}

INDUSTRY_PLATFORM_MODULES = [
    ("trade-matches", "交易撮合"),
    ("logistics-traces", "物流溯源"),
    ("product-qrcodes", "二维码管理"),
    ("supply-chain-finance", "供应链金融"),
    ("price-indexes", "价格指数"),
    ("mobile-service-channels", "移动端服务"),
]

BUSINESS_REFERENCE_GROUPS = {
    "people": ("farmers",),
    "subjects": ("farmers", "cooperatives", "enterprises"),
}

BUSINESS_REFERENCE_SOURCE_LABELS = {
    "farmers": "竹农",
    "cooperatives": "合作社",
    "enterprises": "竹企",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def postgis_connect():
    try:
        import psycopg
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"business PostGIS database requires psycopg. {exc}") from exc

    try:
        return psycopg.connect(get_settings().database_url)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="business PostGIS database is unavailable") from exc


def datetime_to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def decimal_to_float(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
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


def business_field_schema(module_key: str) -> list[dict[str, Any]]:
    return BUSINESS_FIELD_SCHEMAS.get(module_key, [])


def business_dictionary_catalog() -> dict[str, dict[str, Any]]:
    from .dictionaries import load_all_items, load_all_types

    catalog: dict[str, dict[str, Any]] = {}
    types_by_id: dict[str, dict[str, Any]] = {}
    for dictionary_type in load_all_types():
        type_code = str(dictionary_type.get("typeCode") or "")
        type_id = str(dictionary_type.get("id") or "")
        if not type_code or not type_id:
            continue
        entry = {"type": dictionary_type, "items": {}, "itemsByLevel": {}}
        catalog[type_code] = entry
        types_by_id[type_id] = entry
    for item in load_all_items():
        entry = types_by_id.get(str(item.get("dictionaryTypeId") or ""))
        item_code = str(item.get("itemCode") or "")
        if entry is not None and item_code:
            entry["items"][item_code] = item
            level_code = str(item.get("levelCode") or "")
            entry["itemsByLevel"][(level_code, item_code)] = item
    return catalog


def dictionary_field_items(
    field: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]] | None:
    type_code = str(field.get("dictionaryCode") or "")
    entry = catalog.get(type_code)
    if field.get("inputType") != "dictionary" or not type_code:
        return None
    if entry is None:
        return {}
    dictionary_type = entry["type"]
    if dictionary_type.get("deletedAt") or dictionary_type.get("status") != "active":
        return {}
    return entry["items"]


def business_value_is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return not value
    return False


def administrative_division_item(
    field: dict[str, Any],
    value: Any,
    catalog: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    type_code = str(field.get("referenceDictionaryCode") or "")
    if not type_code:
        return None
    entry = catalog.get(type_code)
    if entry is None:
        return {}
    expected_level = str(field.get("referenceLevel") or "")
    item = entry.get("itemsByLevel", {}).get((expected_level, str(value)))
    if item is None and not expected_level:
        item = entry.get("items", {}).get(str(value))
    if not item or item.get("deletedAt") or item.get("status") != "active":
        return {}
    if expected_level and str(item.get("levelCode") or "") != expected_level:
        return {}
    return item


def apply_computed_business_properties(
    module_key: str,
    properties: dict[str, Any],
) -> None:
    for field in business_field_schema(module_key):
        computed = field.get("computed")
        if not isinstance(computed, dict):
            continue
        key = str(field.get("key") or "")
        source_fields = [str(value) for value in computed.get("fields") or []]
        operation = str(computed.get("operation") or "")
        if not key or not source_fields:
            continue
        try:
            values = [Decimal(str(properties.get(source_key) or 0)) for source_key in source_fields]
        except (ArithmeticError, ValueError):
            continue
        if operation == "subtract" and len(values) >= 2:
            precision = int(computed.get("precision") or 2)
            properties[key] = round(float(values[0] - values[1]), precision)
        elif operation == "stock-status" and len(values) >= 2:
            stock, warning_threshold = values[:2]
            properties[key] = (
                "out"
                if stock <= 0
                else "warning"
                if warning_threshold > 0 and stock <= warning_threshold
                else "normal"
            )


def validate_business_chronology(
    module_key: str,
    properties: dict[str, Any],
) -> None:
    chronology_pairs = {
        "policies": [("publishDate", "effectiveDate")],
        "stewardship-agreements": [("startDate", "endDate")],
        "maintenance-tasks": [("plannedStartAt", "plannedEndAt")],
        "drone-tasks": [("actualStartAt", "actualEndAt")],
        "harvest-plans": [("plannedStartDate", "plannedEndDate")],
        "carbon-estimates": [("accountingStartDate", "accountingEndDate")],
        "trade-matches": [("deliveryStartDate", "deliveryEndDate")],
        "logistics-traces": [("departureAt", "arrivalAt")],
    }
    for start_key, end_key in chronology_pairs.get(module_key, []):
        start_value = str(properties.get(start_key) or "")
        end_value = str(properties.get(end_key) or "")
        if start_value and end_value and end_value < start_value:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid business field {end_key}: must not be earlier than {start_key}",
            )


def normalize_business_properties(
    module_key: str,
    properties: dict[str, Any] | None,
    *,
    previous_properties: dict[str, Any] | None = None,
    enforce_required: bool = False,
) -> dict[str, Any]:
    normalized = dict(properties or {})
    previous = dict(previous_properties or {})
    if module_key == "farmers":
        if "operationAreaMu" not in normalized and "managedAreaMu" in normalized:
            normalized["operationAreaMu"] = normalized["managedAreaMu"]
    apply_computed_business_properties(module_key, normalized)
    dictionary_catalog: dict[str, dict[str, Any]] | None = None
    for field in business_field_schema(module_key):
        key = str(field.get("key") or "")
        if not key:
            continue
        input_type = str(field.get("inputType") or "text")
        value = normalized.get(key)
        if key not in normalized or business_value_is_blank(value):
            normalized.pop(key, None)
            if enforce_required and field.get("required") and input_type != "business-relation":
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid business field {key}: field is required",
                )
            continue
        try:
            if input_type == "integer":
                numeric = Decimal(str(value))
                if numeric != numeric.to_integral_value():
                    raise ValueError("must be an integer")
                normalized[key] = int(numeric)
            elif input_type == "number":
                normalized[key] = float(Decimal(str(value)))
            elif input_type == "date":
                normalized[key] = date.fromisoformat(str(value).strip()).isoformat()
            elif input_type == "datetime-local":
                normalized[key] = datetime.fromisoformat(str(value).strip()).isoformat()
            elif input_type == "month":
                month_value = str(value).strip()
                if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month_value):
                    raise ValueError("must use YYYY-MM")
                normalized[key] = month_value
            elif input_type == "boolean":
                if isinstance(value, bool):
                    normalized[key] = value
                elif str(value).strip().lower() in {"true", "1", "yes", "on"}:
                    normalized[key] = True
                elif str(value).strip().lower() in {"false", "0", "no", "off"}:
                    normalized[key] = False
                else:
                    raise ValueError("must be a boolean")
            elif input_type in {"multi-reference", "business-relation"}:
                source_values = value if isinstance(value, list) else str(value).split(",")
                normalized[key] = [
                    str(item).strip()
                    for item in source_values
                    if str(item).strip()
                ]
            else:
                normalized[key] = str(value).strip()
        except (ValueError, ArithmeticError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid business field {key}: {exc}") from exc

        if field.get("inputType") == "dictionary" and not field.get("computed"):
            if dictionary_catalog is None:
                dictionary_catalog = business_dictionary_catalog()
            dictionary_items = dictionary_field_items(field, dictionary_catalog)
        else:
            dictionary_items = None
        reference_item = None
        if field.get("referenceDictionaryCode"):
            if dictionary_catalog is None:
                dictionary_catalog = business_dictionary_catalog()
            reference_item = administrative_division_item(field, normalized[key], dictionary_catalog)
            if not reference_item:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid business field {key}: reference code or level is invalid",
                )
            parent_field = str(field.get("parentField") or "")
            if parent_field and str(reference_item.get("parentCode") or "") != str(normalized.get(parent_field) or ""):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid business field {key}: parent division does not match {parent_field}",
                )
        if dictionary_items is None:
            options = field.get("options") or []
            allowed = {str(option.get("value")) for option in options if isinstance(option, dict)}
        else:
            allowed = {
                item_code
                for item_code, item in dictionary_items.items()
                if not item.get("deletedAt") and item.get("status") == "active"
            }
        normalized_value = str(normalized[key])
        historical_value_unchanged = key in previous and str(previous.get(key)) == normalized_value
        if (dictionary_items is not None or allowed) and normalized_value not in allowed and not historical_value_unchanged:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid business field {key}: expected one of {', '.join(sorted(allowed))}",
            )
        minimum = field.get("min")
        maximum = field.get("max")
        if minimum is not None and isinstance(normalized[key], (int, float)) and normalized[key] < minimum:
            raise HTTPException(status_code=422, detail=f"Invalid business field {key}: minimum is {minimum}")
        if maximum is not None and isinstance(normalized[key], (int, float)) and normalized[key] > maximum:
            raise HTTPException(status_code=422, detail=f"Invalid business field {key}: maximum is {maximum}")
        text_value = str(normalized[key])
        minimum_length = field.get("minLength")
        maximum_length = field.get("maxLength")
        if minimum_length is not None and len(text_value) < int(minimum_length):
            raise HTTPException(status_code=422, detail=f"Invalid business field {key}: minimum length is {minimum_length}")
        if maximum_length is not None and len(text_value) > int(maximum_length):
            raise HTTPException(status_code=422, detail=f"Invalid business field {key}: maximum length is {maximum_length}")
        pattern = str(field.get("pattern") or "")
        if pattern and not re.fullmatch(pattern, text_value):
            raise HTTPException(status_code=422, detail=f"Invalid business field {key}: value format is invalid")
        display_property = str(field.get("displayProperty") or "")
        if display_property and reference_item:
            normalized[display_property] = str(reference_item.get("label") or reference_item.get("itemCode") or "")
    apply_computed_business_properties(module_key, normalized)
    validate_business_chronology(module_key, normalized)
    if module_key == "farmers":
        if "operationAreaMu" in normalized:
            normalized["managedAreaMu"] = normalized["operationAreaMu"]
        town_name = str(normalized.get("townName") or "").strip()
        village_name = str(normalized.get("villageName") or "").strip()
        standardized_location = " / ".join(item for item in (town_name, village_name) if item)
        if standardized_location:
            normalized["townVillage"] = standardized_location
    return normalized


def business_relation_fields(module_key: str) -> list[dict[str, Any]]:
    return [
        field
        for field in business_field_schema(module_key)
        if field.get("inputType") == "business-relation"
    ]


def relation_links_from_properties(
    module_key: str,
    properties: dict[str, Any],
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for field in business_relation_fields(module_key):
        key = str(field.get("key") or "")
        values = properties.get(key)
        if business_value_is_blank(values):
            continue
        source_values = values if isinstance(values, list) else [values]
        for index, target_id in enumerate(source_values):
            links.append(
                {
                    "relationType": str(field.get("relationType") or key),
                    "targetModuleKey": str(field.get("targetModuleKey") or ""),
                    "targetRecordId": str(target_id).strip(),
                    "sortOrder": index,
                    "properties": {},
                }
            )
    return links


def normalize_business_record_links(
    module_key: str,
    linked_records: Any,
    properties: dict[str, Any],
    *,
    context: AuthContext,
    enforce_required: bool = False,
) -> list[dict[str, Any]]:
    relation_fields = business_relation_fields(module_key)
    field_by_contract = {
        (
            str(field.get("relationType") or field.get("key") or ""),
            str(field.get("targetModuleKey") or ""),
        ): field
        for field in relation_fields
    }
    raw_links = linked_records
    if raw_links is None:
        raw_links = relation_links_from_properties(module_key, properties)
    if not isinstance(raw_links, list):
        raise HTTPException(status_code=422, detail="Invalid business field linkedRecords: expected a list")

    normalized_links: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    values_by_field: dict[str, list[str]] = {}
    for index, raw_link in enumerate(raw_links):
        if not isinstance(raw_link, dict):
            raise HTTPException(status_code=422, detail="Invalid business field linkedRecords: invalid relation")
        relation_type = str(raw_link.get("relationType") or "").strip()
        target_module_key = str(raw_link.get("targetModuleKey") or "").strip()
        target_record_id = str(raw_link.get("targetRecordId") or "").strip()
        field = field_by_contract.get((relation_type, target_module_key))
        field_key = str(field.get("key") if field else "linkedRecords")
        if field is None or not target_record_id:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid business field {field_key}: relation contract is invalid",
            )
        require_permission(context, permission_for_business_module(target_module_key, "view"))
        target = find_business_record_for_upsert(target_module_key, target_record_id)
        if not target or target.get("deletedAt"):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid business field {field_key}: target record does not exist",
            )
        allowed_statuses = {str(value) for value in field.get("allowedTargetStatuses") or []}
        if allowed_statuses and str(target.get("status") or "") not in allowed_statuses:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid business field {field_key}: target status is not allowed",
            )
        identity = (relation_type, target_module_key, target_record_id)
        if identity in seen:
            continue
        seen.add(identity)
        values_by_field.setdefault(field_key, []).append(target_record_id)
        normalized_links.append(
            {
                "relationType": relation_type,
                "targetModuleKey": target_module_key,
                "targetRecordId": target_record_id,
                "targetRecordCode": str(target.get("recordCode") or ""),
                "targetName": str(target.get("name") or ""),
                "targetStatus": str(target.get("status") or ""),
                "sortOrder": int(raw_link.get("sortOrder") or index),
                "properties": dict(raw_link.get("properties") or {}),
            }
        )

    relation_groups: dict[str, dict[str, Any]] = {}
    for field in relation_fields:
        key = str(field.get("key") or "")
        values = values_by_field.get(key, [])
        if not field.get("multiple", False) and len(values) > 1:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid business field {key}: only one target is allowed",
            )
        if enforce_required and field.get("required") and not values:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid business field {key}: relation is required",
            )
        relation_group = str(field.get("relationGroup") or "").strip()
        minimum_group_targets = int(field.get("minGroupTargets") or 0)
        if relation_group:
            group = relation_groups.setdefault(
                relation_group,
                {"fields": [], "targets": set(), "minimum": 0},
            )
            group["fields"].append(key)
            group["targets"].update(values)
            group["minimum"] = max(int(group["minimum"]), minimum_group_targets)
        properties[key] = values
    if enforce_required:
        for relation_group, group in relation_groups.items():
            if len(group["targets"]) >= int(group["minimum"]):
                continue
            field_names = ", ".join(group["fields"])
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid business relation group {relation_group}: "
                    f"select at least {group['minimum']} target from {field_names}"
                ),
            )
    return normalized_links


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


def normalize_postgis_layer_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
    else:
        source = dict(zip(POSTGIS_LAYER_SELECT_COLUMNS, row))

    layer: dict[str, Any] = {}
    for db_field, api_field in LAYER_DB_TO_API_FIELD.items():
        value = source.get(db_field)
        if db_field in {"linked_block_codes", "linked_right_archive_codes"}:
            value = json_value(value, [])
        elif db_field in {"style", "properties"}:
            value = json_value(value, {})
        elif db_field in {"created_at", "updated_at", "deleted_at"}:
            value = datetime_to_iso(value)
        else:
            value = decimal_to_float(value)
        layer[api_field] = value
    layer.setdefault("style", {})
    layer.setdefault("properties", {})
    layer.setdefault("linkedBlockCodes", [])
    layer.setdefault("linkedRightArchiveCodes", [])
    if layer.get("visibleOnDashboard") is None:
        layer["visibleOnDashboard"] = True
    return layer


def normalize_postgis_business_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
    else:
        source = dict(zip(POSTGIS_BUSINESS_SELECT_COLUMNS, row))

    payload = json_value(source.get("payload"), {})
    record: dict[str, Any] = dict(payload if isinstance(payload, dict) else {})
    for db_field, api_field in BUSINESS_DB_TO_API_FIELD.items():
        value = source.get(db_field)
        if db_field in {"linked_block_codes", "linked_right_archive_codes"}:
            value = json_value(value, [])
        elif db_field == "properties":
            value = json_value(value, {})
        elif db_field in {"created_at", "updated_at", "deleted_at"}:
            value = datetime_to_iso(value)
        else:
            value = decimal_to_float(value)
        record[api_field] = value
    record.setdefault("linkedBlockCodes", [])
    record.setdefault("linkedRightArchiveCodes", [])
    record.setdefault("properties", {})
    return record


class ManagedRecordIn(BaseModel):
    recordCode: str | None = None
    name: str = Field(min_length=1)
    status: str | None = None
    linkedBlockCodes: list[str] = Field(default_factory=list)
    linkedRightArchiveCodes: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class ManagedRecordPatch(BaseModel):
    recordCode: str | None = None
    name: str | None = None
    status: str | None = None
    linkedBlockCodes: list[str] | None = None
    linkedRightArchiveCodes: list[str] | None = None
    properties: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class ManagedRecordOut(ManagedRecordIn):
    id: str
    createdAt: str
    updatedAt: str
    deletedAt: str | None = None

    model_config = {"extra": "allow"}


class MapLayerIn(ManagedRecordIn):
    layerType: str | None = None
    dataSource: str | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    zIndex: int | None = None
    visibleOnDashboard: bool = True


class MapLayerPatch(ManagedRecordPatch):
    layerType: str | None = None
    dataSource: str | None = None
    style: dict[str, Any] | None = None
    zIndex: int | None = None
    visibleOnDashboard: bool | None = None


class MapLayerPublishRequest(BaseModel):
    visibleOnDashboard: bool = True
    status: str | None = None


class MapLayerOut(ManagedRecordOut):
    layerType: str | None = None
    dataSource: str | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    zIndex: int | None = None
    visibleOnDashboard: bool = True
    sourceType: str = "manual"
    publishRiskStatus: str = "unknown"
    adminHref: str = ""
    dashboardHref: str = ""
    sourceLinks: list[dict[str, str]] = Field(default_factory=list)


class ManagedFilters(BaseModel):
    q: str = ""
    status: str = ""
    linkedBlockCode: str = ""
    fieldKey: str = ""
    fieldValue: str = ""
    sourceType: str = ""
    publishRiskStatus: str = ""
    visibleOnDashboard: str | bool | None = ""
    includeDeleted: bool = False
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


def compact_list(values: list[Any] | None) -> list[str]:
    return sorted({str(value).strip() for value in values or [] if str(value).strip()})


def validate_business_module(module_key: str) -> str:
    if module_key not in BUSINESS_MODULES:
        raise HTTPException(status_code=404, detail="Business module not found")
    return module_key


def permission_for_business_module(module_key: str, action: str = "manage") -> str:
    action_key = str(action or "manage").strip()
    if action_key not in BUSINESS_ACTIONS:
        raise ValueError(f"Unsupported business permission action: {action}")
    manage_permission = BUSINESS_MODULE_PERMISSIONS[module_key]
    if action_key == "manage":
        return manage_permission
    return f"{manage_permission.removesuffix('.manage')}.{action_key}"


def normalize_record(payload: dict[str, Any], *, default_status: str = "active") -> dict[str, Any]:
    record = dict(payload)
    timestamp = now_iso()
    record.setdefault("id", str(uuid.uuid4()))
    record.setdefault("createdAt", timestamp)
    record["updatedAt"] = timestamp
    record.setdefault("deletedAt", None)
    record["recordCode"] = str(record.get("recordCode") or record.get("name") or record["id"]).strip()
    record["name"] = str(record.get("name") or "").strip()
    record["status"] = str(record.get("status") or default_status).strip()
    record["linkedBlockCodes"] = compact_list(record.get("linkedBlockCodes"))
    record["linkedRightArchiveCodes"] = compact_list(record.get("linkedRightArchiveCodes"))
    record["linkedRecords"] = list(record.get("linkedRecords") or [])
    record.setdefault("properties", {})
    if not record["name"]:
        raise HTTPException(status_code=400, detail="name is required")
    return record


def active_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if not record.get("deletedAt")]


def text_matches(record: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = json.dumps(record, ensure_ascii=False).lower()
    return query.lower() in haystack


def parse_optional_bool(value: str | bool | None) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def dashboard_visibility_matches(record: dict[str, Any], value: str | bool | None) -> bool:
    expected = parse_optional_bool(value)
    if expected is None:
        return True
    actual_visible = record.get("visibleOnDashboard") is not False
    return actual_visible is expected


def record_matches(record: dict[str, Any], filters: ManagedFilters) -> bool:
    if filters.status and record.get("status") != filters.status:
        return False
    if filters.linkedBlockCode and filters.linkedBlockCode not in (record.get("linkedBlockCodes") or []):
        return False
    if filters.fieldKey:
        properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
        actual = properties.get(filters.fieldKey)
        if filters.fieldValue and str(actual) != filters.fieldValue:
            return False
        if not filters.fieldValue and filters.fieldKey not in properties:
            return False
    if filters.sourceType and layer_source_type(record) != filters.sourceType:
        return False
    if filters.publishRiskStatus:
        properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
        if properties.get("publishRiskStatus") != filters.publishRiskStatus:
            return False
    if not dashboard_visibility_matches(record, filters.visibleOnDashboard):
        return False
    return text_matches(record, filters.q)


def layer_source_type(record: dict[str, Any]) -> str:
    properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
    if properties.get("importBatchId"):
        return "importBatch"
    if properties.get("sourceSceneId"):
        return "imagery"
    return "manual"


def bucket_counts(records: list[dict[str, Any]], value_getter: Callable[[dict[str, Any]], Any]) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for record in records:
        value = str(value_getter(record) or "unknown").strip() or "unknown"
        buckets[value] = buckets.get(value, 0) + 1
    return dict(sorted(buckets.items()))


def map_layer_publish_risk_status(record: dict[str, Any]) -> str:
    properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
    return str(properties.get("publishRiskStatus") or "unknown")


def url_param(value: Any) -> str:
    return quote(str(value or "").strip(), safe="")


def map_layer_admin_href(record: dict[str, Any]) -> str:
    key = str(record.get("recordCode") or record.get("id") or "").strip()
    return f"admin-map-layers.html?layerCode={url_param(key)}" if key else "admin-map-layers.html"


def map_layer_dashboard_href(record: dict[str, Any]) -> str:
    if str(record.get("status") or "") == "published" and bool(record.get("visibleOnDashboard", True)):
        return "zhushan-bigdata.html#mapLayers"
    return ""


def map_layer_source_links(record: dict[str, Any]) -> list[dict[str, str]]:
    properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
    links: list[dict[str, str]] = []
    import_batch_id = str(properties.get("importBatchId") or "").strip()
    scene_id = str(properties.get("sourceSceneId") or "").strip()
    if import_batch_id:
        links.append(
            {
                "type": "importBatch",
                "label": "入库批次",
                "value": import_batch_id,
                "href": f"admin-imports.html?batchId={url_param(import_batch_id)}",
            }
        )
    if scene_id:
        links.append(
            {
                "type": "imagery",
                "label": "影像场景",
                "value": scene_id,
                "href": f"admin-imagery.html?sceneId={url_param(scene_id)}",
            }
        )
    return links


def enrich_map_layer_record(record: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(record)
    enriched["sourceType"] = layer_source_type(enriched)
    enriched["publishRiskStatus"] = map_layer_publish_risk_status(enriched)
    enriched["adminHref"] = map_layer_admin_href(enriched)
    enriched["dashboardHref"] = map_layer_dashboard_href(enriched)
    enriched["sourceLinks"] = map_layer_source_links(enriched)
    return enriched


def dashboard_map_layer_item(record: dict[str, Any]) -> dict[str, Any]:
    return enrich_map_layer_record(record)


def dashboard_map_layer_records() -> list[dict[str, Any]]:
    filters = ManagedFilters(
        status="published",
        visibleOnDashboard="true",
        limit=1000,
        offset=0,
    )
    if use_mysql():
        return fetch_layers_mysql(
            filters=filters,
            include_deleted=False,
            limit=1000,
            offset=0,
            include_targets=False,
        )
    if use_postgis():
        return fetch_layers_postgis(filters=filters, include_deleted=False, limit=1000, offset=0)
    return [record for record in active_records(layer_records()) if record_matches(record, filters)]


def dashboard_map_layer_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    linked_blocks = sorted({code for record in records for code in record.get("linkedBlockCodes", [])})
    return {
        "total": len(records),
        "linkedBlockTotal": count_dashboard_linked_blocks_mysql() if use_mysql() else len(linked_blocks),
        "byLayerType": bucket_counts(records, lambda record: record.get("layerType")),
        "bySourceType": bucket_counts(records, layer_source_type),
        "byPublishRiskStatus": bucket_counts(records, map_layer_publish_risk_status),
    }


def map_layer_publication_records() -> list[dict[str, Any]]:
    filters = ManagedFilters(limit=1000, offset=0)
    if use_mysql():
        return fetch_layers_mysql(
            filters=filters,
            include_deleted=False,
            limit=1000,
            offset=0,
            include_targets=False,
        )
    if use_postgis():
        return fetch_layers_postgis(filters=filters, include_deleted=False, limit=1000, offset=0)
    return active_records(layer_records())


def map_layer_publication_queue_key(record: dict[str, Any]) -> str:
    properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
    published = str(record.get("status") or "") == "published" and bool(record.get("visibleOnDashboard", True))
    if published:
        return "receipt_ready"

    risk_status = map_layer_publish_risk_status(record)
    quality_status = str(properties.get("qualityStatus") or "").strip()
    recommendation = str(properties.get("reviewRecommendation") or "").strip()
    if risk_status == "blocked" or quality_status == "blocked" or recommendation == "reject_publish":
        return "blocked"
    if risk_status in {"warning", "unknown"} or quality_status == "warning" or recommendation in {
        "needs_correction",
        "manual_review",
    }:
        return "needs_review"
    return "awaiting_publish"


def map_layer_publication_queue_item(record: dict[str, Any], lane_key: str) -> dict[str, Any]:
    item = enrich_map_layer_record(record)
    item["publicationQueueKey"] = lane_key
    return item


def map_layer_publication_queue(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {stage["key"]: [] for stage in MAP_LAYER_PUBLICATION_QUEUE_STAGES}
    for record in records:
        lane_key = map_layer_publication_queue_key(record)
        grouped.setdefault(lane_key, []).append(map_layer_publication_queue_item(record, lane_key))
    return [
        {
            **stage,
            "count": len(grouped.get(stage["key"], [])),
            "items": grouped.get(stage["key"], []),
        }
        for stage in MAP_LAYER_PUBLICATION_QUEUE_STAGES
    ]


def map_layer_publication_summary(records: list[dict[str, Any]], published_records: list[dict[str, Any]]) -> dict[str, Any]:
    queue = map_layer_publication_queue(records)
    lane_counts = {lane["key"]: int(lane["count"]) for lane in queue}
    return {
        "publicationQueueTotal": sum(lane_counts.values()),
        "awaitingPublishTotal": lane_counts.get("awaiting_publish", 0),
        "reviewTotal": lane_counts.get("needs_review", 0),
        "blockedTotal": lane_counts.get("blocked", 0),
        "receiptReadyTotal": lane_counts.get("receipt_ready", 0),
        "publishedDashboardTotal": len(published_records),
    }


def dashboard_map_layers_payload() -> dict[str, Any]:
    records = dashboard_map_layer_records()
    publication_records = map_layer_publication_records()
    return {
        "items": [dashboard_map_layer_item(record) for record in records],
        "total": len(records),
        "limit": 1000,
        "offset": 0,
        "summary": dashboard_map_layer_summary(records),
        "publicationQueue": map_layer_publication_queue(publication_records),
        "publicationSummary": map_layer_publication_summary(publication_records, records),
        "filters": {"status": "published", "visibleOnDashboard": True},
        "adminHref": "admin-map-layers.html",
    }


def list_records(records: list[dict[str, Any]], filters: ManagedFilters) -> dict[str, Any]:
    candidates = records if filters.includeDeleted else active_records(records)
    filtered = [record for record in candidates if record_matches(record, filters)]
    return {
        "items": filtered[filters.offset : filters.offset + filters.limit],
        "total": len(filtered),
        "limit": filters.limit,
        "offset": filters.offset,
    }


def map_layer_list_payload(records: list[dict[str, Any]], filters: ManagedFilters) -> dict[str, Any]:
    payload = list_records(records, filters)
    payload["items"] = [enrich_map_layer_record(record) for record in payload["items"]]
    return payload


def get_record_or_404(records: list[dict[str, Any]], record_id: str) -> dict[str, Any]:
    for record in active_records(records):
        if str(record.get("id")) == str(record_id):
            return record
    raise HTTPException(status_code=404, detail="Record not found")


def create_record(
    records: list[dict[str, Any]],
    payload: dict[str, Any],
    save: Callable[[list[dict[str, Any]]], None],
) -> dict[str, Any]:
    normalized = normalize_record(payload)
    records.append(normalized)
    save(records)
    return normalized


def patch_record(
    records: list[dict[str, Any]],
    record_id: str,
    payload: dict[str, Any],
    save: Callable[[list[dict[str, Any]]], None],
) -> dict[str, Any]:
    for index, record in enumerate(records):
        if str(record.get("id")) != str(record_id) or record.get("deletedAt"):
            continue
        updated = normalize_record(
            {
                **record,
                **{key: value for key, value in payload.items() if value is not None},
                "id": record_id,
                "createdAt": record.get("createdAt", now_iso()),
                "deletedAt": record.get("deletedAt"),
            }
        )
        records[index] = updated
        save(records)
        return updated
    raise HTTPException(status_code=404, detail="Record not found")


def delete_record(
    records: list[dict[str, Any]],
    record_id: str,
    save: Callable[[list[dict[str, Any]]], None],
) -> dict[str, Any]:
    for record in records:
        if str(record.get("id")) != str(record_id) or record.get("deletedAt"):
            continue
        record["deletedAt"] = now_iso()
        record["updatedAt"] = record["deletedAt"]
        save(records)
        return {"ok": True, "deleted": record_id}
    raise HTTPException(status_code=404, detail="Record not found")


def restore_record(
    records: list[dict[str, Any]],
    record_id: str,
    save: Callable[[list[dict[str, Any]]], None],
) -> dict[str, Any]:
    for record in records:
        if str(record.get("id")) != str(record_id):
            continue
        if not record.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Record is not deleted")
        record["deletedAt"] = None
        record["updatedAt"] = now_iso()
        save(records)
        return {"ok": True, "restored": record_id, "item": record}
    raise HTTPException(status_code=404, detail="Record not found")


BUSINESS_AUDIT_EVENT_LIMIT = 100
MAP_LAYER_AUDIT_EVENT_LIMIT = 100
BUSINESS_DASHBOARD_ROW_LIMIT = 100


def business_properties_without_audit(properties: dict[str, Any] | None) -> dict[str, Any]:
    clean = dict(properties or {})
    clean.pop("auditEvents", None)
    return clean


def business_audit_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "recordCode": record.get("recordCode") or "",
        "name": record.get("name") or "",
        "status": record.get("status") or "",
        "linkedBlockCodes": list(record.get("linkedBlockCodes") or []),
        "linkedRightArchiveCodes": list(record.get("linkedRightArchiveCodes") or []),
        "linkedRecords": list(record.get("linkedRecords") or []),
        "properties": business_properties_without_audit(record.get("properties") or {}),
        "payload": business_payload(record),
        "deletedAt": record.get("deletedAt"),
    }


def business_changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_snapshot = business_audit_snapshot(before)
    after_snapshot = business_audit_snapshot(after)
    fields = [
        "recordCode",
        "name",
        "status",
        "linkedBlockCodes",
        "linkedRightArchiveCodes",
        "linkedRecords",
        "properties",
        "deletedAt",
    ]
    changed = [field for field in fields if before_snapshot.get(field) != after_snapshot.get(field)]
    before_payload = before_snapshot.get("payload") if isinstance(before_snapshot.get("payload"), dict) else {}
    after_payload = after_snapshot.get("payload") if isinstance(after_snapshot.get("payload"), dict) else {}
    if before_payload != after_payload:
        changed.extend(
            f"payload.{key}"
            for key in sorted(set(before_payload) | set(after_payload))
            if before_payload.get(key) != after_payload.get(key)
        )
    return changed


def existing_business_audit_events(*records: dict[str, Any] | None) -> list[dict[str, Any]]:
    for record in records:
        properties = record.get("properties") if isinstance(record, dict) else {}
        events = properties.get("auditEvents") if isinstance(properties, dict) else None
        if isinstance(events, list):
            return [event for event in events if isinstance(event, dict)]
    return []


def append_business_audit_event(
    module_key: str,
    record: dict[str, Any],
    action: str,
    context: AuthContext,
    *,
    before: dict[str, Any] | None = None,
    changed_fields: list[str] | None = None,
) -> dict[str, Any]:
    updated = dict(record)
    properties = dict(updated.get("properties") or {})
    events = existing_business_audit_events(before, updated)
    event: dict[str, Any] = {
        "at": now_iso(),
        "action": action,
        "actor": context.user,
        "module": module_key,
        "recordId": updated.get("id") or "",
        "recordCode": updated.get("recordCode") or "",
        "changedFields": changed_fields or [],
        "after": business_audit_snapshot(updated),
    }
    if before is not None:
        event["before"] = business_audit_snapshot(before)
    events.append(event)
    properties["auditEvents"] = events[-BUSINESS_AUDIT_EVENT_LIMIT:]
    updated["properties"] = properties
    return updated


def business_event_record(module_key: str, record: dict[str, Any], event: dict[str, Any], index: int) -> dict[str, Any]:
    snapshot = event.get("after") if isinstance(event.get("after"), dict) else business_audit_snapshot(record)
    record_id = str(event.get("recordId") or record.get("id") or "")
    record_code = str(event.get("recordCode") or snapshot.get("recordCode") or record.get("recordCode") or "")
    action = str(event.get("action") or "")
    admin_link = admin_link_for_module(module_key)
    return {
        "eventId": f"{module_key}:{record_id}:{index}",
        "module": module_key,
        "recordId": record_id,
        "recordCode": record_code,
        "recordName": snapshot.get("name") or record.get("name") or "",
        "action": action,
        "actor": event.get("actor") or "",
        "at": event.get("at") or "",
        "status": snapshot.get("status") or record.get("status") or "",
        "linkedBlockCodes": list(snapshot.get("linkedBlockCodes") or record.get("linkedBlockCodes") or []),
        "linkedRightArchiveCodes": list(
            snapshot.get("linkedRightArchiveCodes") or record.get("linkedRightArchiveCodes") or []
        ),
        "changedFields": list(event.get("changedFields") or []),
        "deletedAt": snapshot.get("deletedAt"),
        "adminHref": admin_link["href"] if admin_link else "",
        "summary": f"{action}: {record_code or record_id}",
    }


def business_event_matches(
    event: dict[str, Any],
    *,
    q: str = "",
    action: str = "",
    record_id: str = "",
    record_code: str = "",
    linked_block_code: str = "",
) -> bool:
    if action and str(event.get("action") or "") != action:
        return False
    if record_id and str(event.get("recordId") or "") != record_id:
        return False
    if record_code and str(event.get("recordCode") or "") != record_code:
        return False
    if linked_block_code and linked_block_code not in (event.get("linkedBlockCodes") or []):
        return False
    keyword = q.strip().lower()
    if not keyword:
        return True
    haystack = " ".join(
        [
            str(event.get("eventId") or ""),
            str(event.get("module") or ""),
            str(event.get("recordId") or ""),
            str(event.get("recordCode") or ""),
            str(event.get("recordName") or ""),
            str(event.get("action") or ""),
            str(event.get("actor") or ""),
            str(event.get("status") or ""),
            " ".join(event.get("linkedBlockCodes") or []),
            " ".join(event.get("linkedRightArchiveCodes") or []),
            " ".join(event.get("changedFields") or []),
        ]
    ).lower()
    return keyword in haystack


def list_business_events(
    module_key: str,
    *,
    q: str = "",
    action: str = "",
    record_id: str = "",
    record_code: str = "",
    linked_block_code: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for record in all_business_records(module_key):
        properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
        for index, event in enumerate(properties.get("auditEvents") or []):
            if not isinstance(event, dict):
                continue
            event_record = business_event_record(module_key, record, event, index)
            if business_event_matches(
                event_record,
                q=q,
                action=action,
                record_id=record_id,
                record_code=record_code,
                linked_block_code=linked_block_code,
            ):
                events.append(event_record)
    events.sort(key=lambda item: (str(item.get("at") or ""), str(item.get("eventId") or "")), reverse=True)
    return {
        "items": events[offset : offset + limit],
        "total": len(events),
        "limit": limit,
        "offset": offset,
    }


def layer_properties_without_audit(properties: dict[str, Any] | None) -> dict[str, Any]:
    clean = dict(properties or {})
    clean.pop("auditEvents", None)
    return clean


def map_layer_audit_snapshot(layer: dict[str, Any]) -> dict[str, Any]:
    return {
        "recordCode": layer.get("recordCode") or "",
        "name": layer.get("name") or "",
        "status": layer.get("status") or "",
        "layerType": layer.get("layerType") or "",
        "dataSource": layer.get("dataSource") or "",
        "style": dict(layer.get("style") or {}),
        "zIndex": layer.get("zIndex"),
        "visibleOnDashboard": bool(layer.get("visibleOnDashboard", True)),
        "linkedBlockCodes": list(layer.get("linkedBlockCodes") or []),
        "linkedRightArchiveCodes": list(layer.get("linkedRightArchiveCodes") or []),
        "properties": layer_properties_without_audit(layer.get("properties") or {}),
        "deletedAt": layer.get("deletedAt"),
    }


def map_layer_changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_snapshot = map_layer_audit_snapshot(before)
    after_snapshot = map_layer_audit_snapshot(after)
    fields = [
        "recordCode",
        "name",
        "status",
        "layerType",
        "dataSource",
        "style",
        "zIndex",
        "visibleOnDashboard",
        "linkedBlockCodes",
        "linkedRightArchiveCodes",
        "properties",
        "deletedAt",
    ]
    return [field for field in fields if before_snapshot.get(field) != after_snapshot.get(field)]


def existing_map_layer_audit_events(*layers: dict[str, Any] | None) -> list[dict[str, Any]]:
    for layer in layers:
        properties = layer.get("properties") if isinstance(layer, dict) else {}
        events = properties.get("auditEvents") if isinstance(properties, dict) else None
        if isinstance(events, list):
            return [event for event in events if isinstance(event, dict)]
    return []


def append_map_layer_audit_event(
    layer: dict[str, Any],
    action: str,
    context: AuthContext,
    *,
    before: dict[str, Any] | None = None,
    changed_fields: list[str] | None = None,
) -> dict[str, Any]:
    updated = dict(layer)
    properties = dict(updated.get("properties") or {})
    events = existing_map_layer_audit_events(before, updated)
    event: dict[str, Any] = {
        "at": now_iso(),
        "action": action,
        "actor": context.user,
        "layerId": updated.get("id") or "",
        "recordCode": updated.get("recordCode") or "",
        "changedFields": changed_fields or [],
        "after": map_layer_audit_snapshot(updated),
    }
    if before is not None:
        event["before"] = map_layer_audit_snapshot(before)
    events.append(event)
    properties["auditEvents"] = events[-MAP_LAYER_AUDIT_EVENT_LIMIT:]
    updated["properties"] = properties
    return updated


def map_layer_event_record(layer: dict[str, Any], event: dict[str, Any], index: int) -> dict[str, Any]:
    snapshot = event.get("after") if isinstance(event.get("after"), dict) else map_layer_audit_snapshot(layer)
    properties = snapshot.get("properties") if isinstance(snapshot.get("properties"), dict) else {}
    layer_id = str(event.get("layerId") or layer.get("id") or "")
    record_code = str(event.get("recordCode") or snapshot.get("recordCode") or layer.get("recordCode") or "")
    action = str(event.get("action") or "")
    trace_record = {
        "id": layer_id,
        "recordCode": record_code,
        "status": snapshot.get("status") or layer.get("status") or "",
        "visibleOnDashboard": bool(snapshot.get("visibleOnDashboard", layer.get("visibleOnDashboard", True))),
        "properties": properties,
    }
    source_type = layer_source_type(trace_record)
    return {
        "eventId": f"{layer_id}:{index}",
        "layerId": layer_id,
        "recordCode": record_code,
        "layerName": snapshot.get("name") or layer.get("name") or "",
        "action": action,
        "actor": event.get("actor") or "",
        "at": event.get("at") or "",
        "status": snapshot.get("status") or layer.get("status") or "",
        "visibleOnDashboard": bool(snapshot.get("visibleOnDashboard", layer.get("visibleOnDashboard", True))),
        "sourceType": source_type,
        "publishRiskStatus": properties.get("publishRiskStatus") or "unknown",
        "adminHref": map_layer_admin_href(trace_record),
        "dashboardHref": map_layer_dashboard_href(trace_record),
        "sourceLinks": map_layer_source_links(trace_record),
        "changedFields": list(event.get("changedFields") or []),
        "summary": f"{action}: {record_code or layer_id}",
    }


def map_layer_event_matches(
    event: dict[str, Any],
    *,
    q: str = "",
    action: str = "",
    layer_id: str = "",
    record_code: str = "",
    source_type: str = "",
) -> bool:
    if action and str(event.get("action") or "") != action:
        return False
    if layer_id and str(event.get("layerId") or "") != layer_id:
        return False
    if record_code and str(event.get("recordCode") or "") != record_code:
        return False
    if source_type and str(event.get("sourceType") or "") != source_type:
        return False
    keyword = q.strip().lower()
    if not keyword:
        return True
    haystack = " ".join(
        [
            str(event.get("eventId") or ""),
            str(event.get("layerId") or ""),
            str(event.get("recordCode") or ""),
            str(event.get("layerName") or ""),
            str(event.get("action") or ""),
            str(event.get("actor") or ""),
            str(event.get("status") or ""),
            str(event.get("sourceType") or ""),
            str(event.get("publishRiskStatus") or ""),
            " ".join(event.get("changedFields") or []),
        ]
    ).lower()
    return keyword in haystack


def list_map_layer_events(
    *,
    q: str = "",
    action: str = "",
    layer_id: str = "",
    record_code: str = "",
    source_type: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    layers = (
        fetch_layers_mysql(include_deleted=True, include_targets=False)
        if use_mysql()
        else all_layer_records()
    )
    for layer in layers:
        properties = layer.get("properties") if isinstance(layer.get("properties"), dict) else {}
        for index, event in enumerate(properties.get("auditEvents") or []):
            if not isinstance(event, dict):
                continue
            record = map_layer_event_record(layer, event, index)
            if map_layer_event_matches(
                record,
                q=q,
                action=action,
                layer_id=layer_id,
                record_code=record_code,
                source_type=source_type,
            ):
                events.append(record)
    events.sort(key=lambda item: (str(item.get("at") or ""), str(item.get("eventId") or "")), reverse=True)
    return {
        "items": events[offset : offset + limit],
        "total": len(events),
        "limit": limit,
        "offset": offset,
    }


def map_layer_export_metadata(context: AuthContext, permission: str) -> dict[str, Any]:
    return {
        "exportedBy": context.user,
        "exportPermission": permission,
        "exportRoles": role_codes_for_context(context),
        "exportDataScopes": effective_data_scopes_for_context(context),
    }


def map_layer_publication_receipt(layer: dict[str, Any], context: AuthContext) -> dict[str, Any]:
    enriched = enrich_map_layer_record(layer)
    properties = enriched.get("properties") if isinstance(enriched.get("properties"), dict) else {}
    events = list_map_layer_events(
        layer_id=str(enriched.get("id") or ""),
        limit=1000,
        offset=0,
    ).get("items") or []
    events = sorted(events, key=lambda item: (str(item.get("at") or ""), str(item.get("eventId") or "")))
    return {
        "receiptType": "map-layer-publication",
        "exportedAt": now_iso(),
        **map_layer_export_metadata(context, MAP_LAYER_PERMISSIONS["export"]),
        "layer": enriched,
        "summary": {
            "layerId": enriched.get("id") or "",
            "recordCode": enriched.get("recordCode") or "",
            "status": enriched.get("status") or "",
            "published": str(enriched.get("status") or "") == "published" and bool(enriched.get("visibleOnDashboard")),
            "visibleOnDashboard": bool(enriched.get("visibleOnDashboard")),
            "dashboardHref": enriched.get("dashboardHref") or "",
            "sourceType": enriched.get("sourceType") or "manual",
            "publishRiskStatus": enriched.get("publishRiskStatus") or "unknown",
            "linkedBlockCount": int(properties.get("linkedBlockCount") or len(enriched.get("linkedBlockCodes") or [])),
            "linkedRightArchiveCount": int(
                properties.get("linkedRightArchiveCount") or len(enriched.get("linkedRightArchiveCodes") or [])
            ),
            "eventCount": len(events),
        },
        "sourceLinks": enriched.get("sourceLinks") or [],
        "events": events,
    }


def business_records(module_key: str) -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_business_records_mysql(module_key)
    if use_postgis():
        return fetch_business_records_postgis(module_key)
    return load_json_records(business_json_path(module_key))


def all_business_records(module_key: str) -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_business_records_mysql(module_key, include_deleted=True)
    if use_postgis():
        return fetch_business_records_postgis(module_key, include_deleted=True)
    return load_json_records(business_json_path(module_key))


def save_business_records(module_key: str, records: list[dict[str, Any]]) -> None:
    if use_mysql():
        upsert_business_records_mysql(module_key, records)
        return
    if use_postgis():
        upsert_business_records_postgis(module_key, records)
        return
    save_json_records(business_json_path(module_key), records)


def postgis_business_where(
    module_key: str,
    *,
    filters: ManagedFilters | None = None,
    include_deleted: bool = False,
    record_id: str | None = None,
) -> tuple[str, list[Any]]:
    clauses = ["module_key = %s"]
    params: list[Any] = [module_key]
    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    if record_id:
        clauses.append("id = %s")
        params.append(record_id)
    if filters:
        if filters.status:
            clauses.append("status = %s")
            params.append(filters.status)
        if filters.linkedBlockCode:
            clauses.append("linked_block_codes ? %s")
            params.append(filters.linkedBlockCode)
        if filters.fieldKey:
            if filters.fieldValue:
                clauses.append("properties ->> %s = %s")
                params.extend([filters.fieldKey, filters.fieldValue])
            else:
                clauses.append("properties ? %s")
                params.append(filters.fieldKey)
        if filters.sourceType == "importBatch":
            clauses.append("properties ? 'importBatchId'")
        elif filters.sourceType == "imagery":
            clauses.append("(properties ? 'sourceSceneId' AND NOT (properties ? 'importBatchId'))")
        elif filters.sourceType == "manual":
            clauses.append("(NOT (properties ? 'sourceSceneId') AND NOT (properties ? 'importBatchId'))")
        if filters.publishRiskStatus:
            clauses.append("properties->>'publishRiskStatus' = %s")
            params.append(filters.publishRiskStatus)
        if filters.q:
            query_text = f"%{filters.q}%"
            clauses.append(
                """
                (
                    record_code ILIKE %s
                    OR name ILIKE %s
                    OR properties::text ILIKE %s
                    OR payload::text ILIKE %s
                )
                """
            )
            params.extend([query_text, query_text, query_text, query_text])
    return " WHERE " + " AND ".join(clauses), params


def fetch_business_records_postgis(
    module_key: str,
    *,
    filters: ManagedFilters | None = None,
    include_deleted: bool = False,
    record_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where_sql, params = postgis_business_where(
        module_key,
        filters=filters,
        include_deleted=include_deleted,
        record_id=record_id,
    )
    sql = f"{POSTGIS_BUSINESS_SELECT_SQL}{where_sql} ORDER BY updated_at DESC, record_code"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_business_row(row) for row in cur.fetchall()]


def count_business_records_postgis(module_key: str, filters: ManagedFilters) -> int:
    where_sql, params = postgis_business_where(
        module_key,
        filters=filters,
        include_deleted=filters.includeDeleted,
    )
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM business_records{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def business_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in BUSINESS_CANONICAL_FIELDS}


def postgis_business_values(module_key: str, record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record.get("id"),
        module_key,
        record.get("recordCode"),
        record.get("name"),
        record.get("status"),
        serializable_json(record.get("linkedBlockCodes"), []),
        serializable_json(record.get("linkedRightArchiveCodes"), []),
        serializable_json(record.get("properties"), {}),
        serializable_json(business_payload(record), {}),
        record.get("createdAt"),
        record.get("updatedAt"),
        record.get("deletedAt"),
    )


def execute_upsert_business_postgis(cur: Any, module_key: str, record: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO business_records (
            id,
            module_key,
            record_code,
            name,
            status,
            linked_block_codes,
            linked_right_archive_codes,
            properties,
            payload,
            created_at,
            updated_at,
            deleted_at
        )
        VALUES (
            %s,
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
            module_key = EXCLUDED.module_key,
            record_code = EXCLUDED.record_code,
            name = EXCLUDED.name,
            status = EXCLUDED.status,
            linked_block_codes = EXCLUDED.linked_block_codes,
            linked_right_archive_codes = EXCLUDED.linked_right_archive_codes,
            properties = EXCLUDED.properties,
            payload = EXCLUDED.payload,
            updated_at = EXCLUDED.updated_at,
            deleted_at = EXCLUDED.deleted_at
        """,
        postgis_business_values(module_key, record),
    )


def upsert_business_records_postgis(module_key: str, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            for record in records:
                execute_upsert_business_postgis(cur, module_key, record)
        conn.commit()


def mysql_business_where(
    module_key: str,
    *,
    filters: ManagedFilters | None = None,
    include_deleted: bool = False,
    record_id: str | None = None,
) -> tuple[str, list[Any]]:
    clauses = ["br.module_key = %s"]
    params: list[Any] = [module_key]
    if not include_deleted:
        clauses.append("br.deleted_at IS NULL")
    if record_id:
        clauses.append("br.id = %s")
        params.append(record_id)
    if filters:
        if filters.status:
            clauses.append("br.status = %s")
            params.append(filters.status)
        if filters.linkedBlockCode:
            clauses.append(
                "EXISTS (SELECT 1 FROM business_record_block_links bbl "
                "JOIN forest_blocks b ON b.id = bbl.forest_block_id "
                "WHERE bbl.business_record_id = br.id AND b.block_code = %s)"
            )
            params.append(filters.linkedBlockCode)
        if filters.fieldKey:
            field = next(
                (item for item in business_field_schema(module_key) if item.get("key") == filters.fieldKey),
                None,
            )
            if field is None:
                raise HTTPException(status_code=422, detail=f"Unknown business field: {filters.fieldKey}")
            input_type = str(field.get("inputType") or "text")
            value_column = "text_value"
            field_value: Any = filters.fieldValue
            if input_type in {"number", "integer"}:
                value_column = "number_value"
                try:
                    field_value = Decimal(filters.fieldValue) if filters.fieldValue else None
                except ArithmeticError as exc:
                    raise HTTPException(status_code=422, detail=f"Invalid numeric field filter: {filters.fieldKey}") from exc
            elif input_type == "date":
                value_column = "date_value"
                try:
                    field_value = date.fromisoformat(filters.fieldValue) if filters.fieldValue else None
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=f"Invalid date field filter: {filters.fieldKey}") from exc
            elif input_type == "datetime-local":
                value_column = "datetime_value"
                field_value = mysql_datetime(filters.fieldValue) if filters.fieldValue else None
            elif input_type == "boolean":
                value_column = "boolean_value"
                field_value = str(filters.fieldValue).lower() in {"true", "1", "yes", "on"}
            clause = (
                "EXISTS (SELECT 1 FROM business_record_attributes bra "
                "WHERE bra.business_record_id = br.id AND bra.module_key = br.module_key "
                "AND bra.field_key = %s"
            )
            params.append(filters.fieldKey)
            if filters.fieldValue:
                clause += f" AND bra.{value_column} = %s"
                params.append(field_value)
            clauses.append(clause + ")")
        if filters.sourceType == "importBatch":
            clauses.append("JSON_CONTAINS_PATH(br.properties, 'one', '$.importBatchId')")
        elif filters.sourceType == "imagery":
            clauses.append(
                "JSON_CONTAINS_PATH(br.properties, 'one', '$.sourceSceneId') "
                "AND NOT JSON_CONTAINS_PATH(br.properties, 'one', '$.importBatchId')"
            )
        elif filters.sourceType == "manual":
            clauses.append(
                "NOT JSON_CONTAINS_PATH(br.properties, 'one', '$.sourceSceneId') "
                "AND NOT JSON_CONTAINS_PATH(br.properties, 'one', '$.importBatchId')"
            )
        if filters.publishRiskStatus:
            clauses.append("JSON_UNQUOTE(JSON_EXTRACT(br.properties, '$.publishRiskStatus')) = %s")
            params.append(filters.publishRiskStatus)
        if filters.q:
            query_text = f"%{filters.q}%"
            clauses.append(
                "(br.record_code LIKE %s OR br.name LIKE %s OR "
                "CAST(br.properties AS CHAR) LIKE %s OR CAST(br.payload AS CHAR) LIKE %s)"
            )
            params.extend([query_text] * 4)
    return " WHERE " + " AND ".join(clauses), params


def fetch_business_records_mysql(
    module_key: str,
    *,
    filters: ManagedFilters | None = None,
    include_deleted: bool = False,
    record_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    include_targets: bool = True,
) -> list[dict[str, Any]]:
    where_sql, params = mysql_business_where(
        module_key,
        filters=filters,
        include_deleted=include_deleted,
        record_id=record_id,
    )
    select_sql = MYSQL_BUSINESS_SELECT_SQL if include_targets else MYSQL_BUSINESS_SUMMARY_SELECT_SQL
    sql = f"{select_sql}{where_sql} ORDER BY br.updated_at DESC, br.record_code"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_business_row(row) for row in cur.fetchall()]


def count_business_records_mysql(module_key: str, filters: ManagedFilters) -> int:
    where_sql, params = mysql_business_where(
        module_key,
        filters=filters,
        include_deleted=filters.includeDeleted,
    )
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM business_records br{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def mysql_business_dashboard_summary(
    module_key: str,
    *,
    connection_factory: Any = mysql_connect,
) -> dict[str, Any]:
    activity_field, active_values = BUSINESS_ACTIVITY_RULES.get(
        module_key,
        ("@status", {"active", "published", "open"}),
    )
    active_values = sorted(active_values)
    active_placeholders = ", ".join(["%s"] * len(active_values))
    aggregate_rules = BUSINESS_AGGREGATE_RULES.get(module_key, [])
    aggregates: dict[str, float] = {}
    with connection_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM business_records br "
                "WHERE br.module_key = %s AND br.deleted_at IS NULL",
                (module_key,),
            )
            total_row = cur.fetchone()
            cur.execute(
                "SELECT COUNT(DISTINCT links.forest_block_id) "
                "FROM business_record_block_links links "
                "JOIN business_records br ON br.id = links.business_record_id "
                "JOIN forest_blocks blocks ON blocks.id = links.forest_block_id "
                "WHERE br.module_key = %s AND br.deleted_at IS NULL AND blocks.deleted_at IS NULL",
                (module_key,),
            )
            linked_row = cur.fetchone()
            if activity_field == "@status":
                cur.execute(
                    "SELECT COUNT(*) FROM business_records br "
                    f"WHERE br.module_key = %s AND br.deleted_at IS NULL AND br.status IN ({active_placeholders})",
                    tuple([module_key, *active_values]),
                )
            else:
                cur.execute(
                    "SELECT COUNT(DISTINCT br.id) FROM business_records br "
                    "JOIN business_record_attributes bra ON bra.business_record_id = br.id "
                    "AND bra.module_key = br.module_key "
                    "WHERE br.module_key = %s AND br.deleted_at IS NULL "
                    f"AND bra.field_key = %s AND bra.text_value IN ({active_placeholders})",
                    tuple([module_key, activity_field, *active_values]),
                )
            active_row = cur.fetchone()
            if aggregate_rules:
                aggregate_keys = [rule[0] for rule in aggregate_rules]
                placeholders = ", ".join(["%s"] * len(aggregate_keys))
                cur.execute(
                    "SELECT bra.field_key, SUM(bra.number_value), AVG(bra.number_value) "
                    "FROM business_record_attributes bra "
                    "JOIN business_records br ON br.id = bra.business_record_id "
                    "AND br.module_key = bra.module_key "
                    "WHERE br.module_key = %s AND br.deleted_at IS NULL "
                    f"AND bra.field_key IN ({placeholders}) GROUP BY bra.field_key",
                    tuple([module_key, *aggregate_keys]),
                )
                operations = {field_key: operation for field_key, _label, _unit, operation in aggregate_rules}
                for row in cur.fetchall():
                    field_key = str(row[0])
                    value = row[2] if operations.get(field_key) == "average" else row[1]
                    aggregates[field_key] = float(decimal_to_float(value) or 0)
    return {
        "total": int(total_row[0] if total_row else 0),
        "linkedBlockCount": int(linked_row[0] if linked_row else 0),
        "activeCount": int(active_row[0] if active_row else 0),
        "aggregates": aggregates,
    }


def find_business_record_for_upsert(
    module_key: str,
    record_id: str,
    record_code: str = "",
) -> dict[str, Any] | None:
    if use_mysql():
        clauses = ["br.module_key = %s", "(br.id = %s OR br.record_code = %s)"]
        params = (module_key, record_id, record_code or record_id)
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"{MYSQL_BUSINESS_SUMMARY_SELECT_SQL} WHERE " + " AND ".join(clauses) + " LIMIT 1",
                    params,
                )
                row = cur.fetchone()
        return normalize_postgis_business_row(row) if row else None
    records = fetch_business_records_postgis(module_key, include_deleted=True) if use_postgis() else load_json_records(
        business_json_path(module_key)
    )
    return next(
        (
            record
            for record in records
            if str(record.get("id") or "") == record_id
            or str(record.get("recordCode") or "") == (record_code or record_id)
        ),
        None,
    )


def list_business_record_targets_mysql(
    record_id: str,
    *,
    kind: str,
    q: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    query = q.strip()
    if kind == "blocks":
        from_sql = (
            " FROM business_record_block_links links "
            "JOIN forest_blocks targets ON targets.id = links.forest_block_id "
        )
        clauses = ["links.business_record_id = %s", "targets.deleted_at IS NULL"]
        params: list[Any] = [record_id]
        if query:
            like = f"%{query}%"
            clauses.append("(targets.block_code LIKE %s OR targets.name LIKE %s)")
            params.extend([like, like])
        select_sql = (
            "SELECT targets.id, targets.block_code, targets.name, targets.county_name, "
            "targets.town_name, targets.village_name"
        )
        order_sql = " ORDER BY targets.block_code"
    else:
        from_sql = (
            " FROM business_record_right_links links "
            "JOIN forest_rights targets ON targets.id = links.forest_right_id "
        )
        clauses = ["links.business_record_id = %s", "targets.deleted_at IS NULL"]
        params = [record_id]
        if query:
            like = f"%{query}%"
            clauses.append(
                "(targets.archive_code LIKE %s OR targets.certificate_no LIKE %s "
                "OR targets.holder_name LIKE %s)"
            )
            params.extend([like, like, like])
        select_sql = (
            "SELECT targets.id, targets.archive_code, targets.certificate_no, "
            "targets.holder_name, targets.status"
        )
        order_sql = " ORDER BY targets.archive_code"
    where_sql = " WHERE " + " AND ".join(clauses)
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*){from_sql}{where_sql}", tuple(params))
            count_row = cur.fetchone()
            total = int(count_row[0] if count_row else 0)
            cur.execute(
                f"{select_sql}{from_sql}{where_sql}{order_sql} LIMIT %s OFFSET %s",
                tuple([*params, limit, offset]),
            )
            rows = cur.fetchall()
    if kind == "blocks":
        items = [
            {
                "id": str(row[0]),
                "blockCode": row[1] or "",
                "name": row[2] or "",
                "countyName": row[3] or "",
                "townName": row[4] or "",
                "villageName": row[5] or "",
            }
            for row in rows
        ]
    else:
        items = [
            {
                "id": str(row[0]),
                "archiveCode": row[1] or "",
                "certificateNo": row[2] or "",
                "holderName": row[3] or "",
                "status": row[4] or "",
            }
            for row in rows
        ]
    return {"kind": kind, "items": items, "total": total, "limit": limit, "offset": offset}


def business_attribute_values(
    module_key: str,
    record: dict[str, Any],
    field: dict[str, Any],
) -> tuple[Any, ...] | None:
    key = str(field.get("key") or "")
    properties = record.get("properties") or {}
    if not key or not isinstance(properties, dict) or key not in properties:
        return None
    value = properties.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    value_type = str(field.get("inputType") or "text")
    text_value = None
    number_value = None
    date_value = None
    datetime_value = None
    boolean_value = None
    try:
        if value_type in {"number", "integer"}:
            number_value = Decimal(str(value))
        elif value_type == "date":
            date_value = date.fromisoformat(str(value).strip())
        elif value_type == "datetime-local":
            datetime_value = mysql_datetime(str(value))
        elif value_type == "boolean":
            boolean_value = bool(value)
        else:
            text_value = str(value)[:1024]
    except (ValueError, ArithmeticError):
        value_type = "text"
        text_value = str(value)[:1024]
    return (
        str(record.get("id") or ""),
        module_key,
        key,
        value_type,
        text_value,
        number_value,
        date_value,
        datetime_value,
        boolean_value,
        mysql_datetime(record.get("updatedAt")) or datetime.now(timezone.utc).replace(tzinfo=None),
    )


def inferred_business_attribute_field(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        input_type = "boolean"
    elif isinstance(value, int):
        input_type = "integer"
    elif isinstance(value, (float, Decimal)):
        input_type = "number"
    else:
        input_type = "text"
    return {"key": key, "inputType": input_type}


def sync_business_attributes_mysql(cur: Any, module_key: str, record: dict[str, Any]) -> int:
    record_id = str(record.get("id") or "")
    cur.execute("DELETE FROM business_record_attributes WHERE business_record_id = %s", (record_id,))
    written = 0
    fields = list(business_field_schema(module_key))
    known_keys = {str(field.get("key") or "") for field in fields}
    properties = record.get("properties") or {}
    if isinstance(properties, dict):
        fields.extend(
            inferred_business_attribute_field(str(key), value)
            for key, value in properties.items()
            if str(key) and str(key) not in known_keys
        )
    for field in fields:
        values = business_attribute_values(module_key, record, field)
        if values is None:
            continue
        cur.execute(
            """
            INSERT INTO business_record_attributes (
                business_record_id, module_key, field_key, value_type,
                text_value, number_value, date_value, datetime_value, boolean_value, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                module_key = VALUES(module_key),
                value_type = VALUES(value_type),
                text_value = VALUES(text_value),
                number_value = VALUES(number_value),
                date_value = VALUES(date_value),
                datetime_value = VALUES(datetime_value),
                boolean_value = VALUES(boolean_value),
                updated_at = VALUES(updated_at)
            """,
            values,
        )
        written += 1
    return written


def backfill_business_attribute_rows(cur: Any, rows: list[Any]) -> dict[str, Any]:
    records_processed = 0
    attributes_written = 0
    unknown_modules: set[str] = set()
    for row in rows:
        if hasattr(row, "get"):
            record_id = str(row.get("id") or "")
            module_key = str(row.get("module_key") or "")
            properties = json_value(row.get("properties"), {})
            updated_at = row.get("updated_at")
        else:
            record_id = str(row[0] or "")
            module_key = str(row[1] or "")
            properties = json_value(row[2], {})
            updated_at = row[3]
        if not business_field_schema(module_key):
            unknown_modules.add(module_key)
            continue
        attributes_written += sync_business_attributes_mysql(
            cur,
            module_key,
            {
                "id": record_id,
                "properties": properties if isinstance(properties, dict) else {},
                "updatedAt": datetime_to_iso(updated_at),
            },
        )
        records_processed += 1
    return {
        "recordsProcessed": records_processed,
        "attributesWritten": attributes_written,
        "unknownModules": sorted(item for item in unknown_modules if item),
    }


def sync_business_links_mysql(cur: Any, record: dict[str, Any], *, batch_size: int = 500) -> None:
    record_id = str(record.get("id") or "")
    size = max(1, int(batch_size))
    cur.execute("DELETE FROM business_record_block_links WHERE business_record_id = %s", (record_id,))
    block_codes = compact_list(record.get("linkedBlockCodes"))
    for start in range(0, len(block_codes), size):
        batch = block_codes[start : start + size]
        placeholders = ", ".join(["%s"] * len(batch))
        cur.execute(
            "INSERT IGNORE INTO business_record_block_links (business_record_id, forest_block_id) "
            f"SELECT %s, id FROM forest_blocks WHERE block_code IN ({placeholders})",
            tuple([record_id, *batch]),
        )
    cur.execute("DELETE FROM business_record_right_links WHERE business_record_id = %s", (record_id,))
    right_codes = compact_list(record.get("linkedRightArchiveCodes"))
    for start in range(0, len(right_codes), size):
        batch = right_codes[start : start + size]
        placeholders = ", ".join(["%s"] * len(batch))
        cur.execute(
            "INSERT IGNORE INTO business_record_right_links (business_record_id, forest_right_id) "
            f"SELECT %s, id FROM forest_rights WHERE archive_code IN ({placeholders})",
            tuple([record_id, *batch]),
        )


def sync_business_record_links_mysql(cur: Any, record: dict[str, Any]) -> None:
    record_id = str(record.get("id") or "")
    cur.execute("DELETE FROM business_record_links WHERE source_record_id = %s", (record_id,))
    for index, link in enumerate(record.get("linkedRecords") or []):
        cur.execute(
            """
            INSERT INTO business_record_links (
                source_record_id, relation_type, target_module_key, target_record_id,
                sort_order, properties
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                record_id,
                str(link.get("relationType") or ""),
                str(link.get("targetModuleKey") or ""),
                str(link.get("targetRecordId") or ""),
                int(link.get("sortOrder") or index),
                serializable_json(link.get("properties"), {}),
            ),
        )


def execute_upsert_business_scalar_mysql(cur: Any, module_key: str, record: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO business_records (
            id, module_key, record_code, name, status, properties, payload,
            created_at, updated_at, deleted_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            module_key = VALUES(module_key),
            record_code = VALUES(record_code),
            name = VALUES(name),
            status = VALUES(status),
            properties = VALUES(properties),
            payload = VALUES(payload),
            updated_at = VALUES(updated_at),
            deleted_at = VALUES(deleted_at)
        """,
        (
            record.get("id"),
            module_key,
            record.get("recordCode"),
            record.get("name"),
            record.get("status"),
            serializable_json(record.get("properties"), {}),
            serializable_json(business_payload(record), {}),
            mysql_datetime(record.get("createdAt")),
            mysql_datetime(record.get("updatedAt")),
            mysql_datetime(record.get("deletedAt")),
        ),
    )


def execute_upsert_business_mysql(cur: Any, module_key: str, record: dict[str, Any]) -> None:
    execute_upsert_business_scalar_mysql(cur, module_key, record)
    sync_business_links_mysql(cur, record)
    sync_business_record_links_mysql(cur, record)
    sync_business_attributes_mysql(cur, module_key, record)


def upsert_business_record_mysql(
    module_key: str,
    record: dict[str, Any],
    *,
    sync_links: bool = True,
    sync_record_links: bool = True,
    connection_factory: Any = mysql_connect,
) -> None:
    with connection_factory() as conn:
        with conn.cursor() as cur:
            execute_upsert_business_scalar_mysql(cur, module_key, record)
            if sync_links:
                sync_business_links_mysql(cur, record)
            if sync_record_links:
                sync_business_record_links_mysql(cur, record)
            sync_business_attributes_mysql(cur, module_key, record)
        conn.commit()


def upsert_business_records_mysql(module_key: str, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            for record in records:
                execute_upsert_business_mysql(cur, module_key, record)
        conn.commit()


def postgis_layer_where(
    *,
    filters: ManagedFilters | None = None,
    include_deleted: bool = False,
    layer_id: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    if layer_id:
        clauses.append("id = %s")
        params.append(layer_id)
    if filters:
        if filters.status:
            clauses.append("status = %s")
            params.append(filters.status)
        if filters.linkedBlockCode:
            clauses.append("linked_block_codes ? %s")
            params.append(filters.linkedBlockCode)
        if filters.sourceType == "importBatch":
            clauses.append("properties ? 'importBatchId'")
        elif filters.sourceType == "imagery":
            clauses.append("(properties ? 'sourceSceneId' AND NOT (properties ? 'importBatchId'))")
        elif filters.sourceType == "manual":
            clauses.append("(NOT (properties ? 'sourceSceneId') AND NOT (properties ? 'importBatchId'))")
        if filters.publishRiskStatus:
            clauses.append("properties->>'publishRiskStatus' = %s")
            params.append(filters.publishRiskStatus)
        visible_on_dashboard = parse_optional_bool(filters.visibleOnDashboard)
        if visible_on_dashboard is not None:
            clauses.append("COALESCE(visible_on_dashboard, TRUE) = %s")
            params.append(visible_on_dashboard)
        if filters.q:
            query_text = f"%{filters.q}%"
            clauses.append(
                """
                (
                    record_code ILIKE %s
                    OR name ILIKE %s
                    OR layer_type ILIKE %s
                    OR data_source ILIKE %s
                    OR properties::text ILIKE %s
                )
                """
            )
            params.extend([query_text, query_text, query_text, query_text, query_text])
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def fetch_layers_postgis(
    *,
    filters: ManagedFilters | None = None,
    include_deleted: bool = False,
    layer_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where_sql, params = postgis_layer_where(
        filters=filters,
        include_deleted=include_deleted,
        layer_id=layer_id,
    )
    sql = f"{POSTGIS_LAYER_SELECT_SQL}{where_sql} ORDER BY z_index NULLS LAST, updated_at DESC, record_code"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_layer_row(row) for row in cur.fetchall()]


def count_layers_postgis(filters: ManagedFilters) -> int:
    where_sql, params = postgis_layer_where(filters=filters, include_deleted=filters.includeDeleted)
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM map_layers{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def postgis_layer_values(layer: dict[str, Any]) -> tuple[Any, ...]:
    return (
        layer.get("id"),
        layer.get("recordCode"),
        layer.get("name"),
        layer.get("status"),
        layer.get("layerType"),
        layer.get("dataSource"),
        serializable_json(layer.get("style"), {}),
        layer.get("zIndex"),
        bool(layer.get("visibleOnDashboard", True)),
        serializable_json(layer.get("linkedBlockCodes"), []),
        serializable_json(layer.get("linkedRightArchiveCodes"), []),
        serializable_json(layer.get("properties"), {}),
        layer.get("createdAt"),
        layer.get("updatedAt"),
        layer.get("deletedAt"),
    )


def execute_upsert_layer_postgis(cur: Any, layer: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO map_layers (
            id,
            record_code,
            name,
            status,
            layer_type,
            data_source,
            style,
            z_index,
            visible_on_dashboard,
            linked_block_codes,
            linked_right_archive_codes,
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
            %s,
            %s,
            %s::jsonb,
            %s,
            %s,
            %s::jsonb,
            %s::jsonb,
            %s::jsonb,
            %s,
            %s,
            %s
        )
        ON CONFLICT (id) DO UPDATE SET
            record_code = EXCLUDED.record_code,
            name = EXCLUDED.name,
            status = EXCLUDED.status,
            layer_type = EXCLUDED.layer_type,
            data_source = EXCLUDED.data_source,
            style = EXCLUDED.style,
            z_index = EXCLUDED.z_index,
            visible_on_dashboard = EXCLUDED.visible_on_dashboard,
            linked_block_codes = EXCLUDED.linked_block_codes,
            linked_right_archive_codes = EXCLUDED.linked_right_archive_codes,
            properties = EXCLUDED.properties,
            updated_at = EXCLUDED.updated_at,
            deleted_at = EXCLUDED.deleted_at
        """,
        postgis_layer_values(layer),
    )


def upsert_layers_postgis(layers: list[dict[str, Any]]) -> None:
    if not layers:
        return
    with postgis_connect() as conn:
        with conn.cursor() as cur:
            for layer in layers:
                execute_upsert_layer_postgis(cur, layer)
        conn.commit()


def mysql_layer_where(
    *,
    filters: ManagedFilters | None = None,
    include_deleted: bool = False,
    layer_id: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_deleted:
        clauses.append("ml.deleted_at IS NULL")
    if layer_id:
        clauses.append("ml.id = %s")
        params.append(layer_id)
    if filters:
        if filters.status:
            clauses.append("ml.status = %s")
            params.append(filters.status)
        if filters.linkedBlockCode:
            clauses.append(
                "EXISTS (SELECT 1 FROM map_layer_block_links lbl "
                "JOIN forest_blocks b ON b.id = lbl.forest_block_id "
                "WHERE lbl.map_layer_id = ml.id AND b.block_code = %s)"
            )
            params.append(filters.linkedBlockCode)
        if filters.sourceType == "importBatch":
            clauses.append("JSON_CONTAINS_PATH(ml.properties, 'one', '$.importBatchId')")
        elif filters.sourceType == "imagery":
            clauses.append(
                "JSON_CONTAINS_PATH(ml.properties, 'one', '$.sourceSceneId') "
                "AND NOT JSON_CONTAINS_PATH(ml.properties, 'one', '$.importBatchId')"
            )
        elif filters.sourceType == "manual":
            clauses.append(
                "NOT JSON_CONTAINS_PATH(ml.properties, 'one', '$.sourceSceneId') "
                "AND NOT JSON_CONTAINS_PATH(ml.properties, 'one', '$.importBatchId')"
            )
        if filters.publishRiskStatus:
            clauses.append("JSON_UNQUOTE(JSON_EXTRACT(ml.properties, '$.publishRiskStatus')) = %s")
            params.append(filters.publishRiskStatus)
        visible = parse_optional_bool(filters.visibleOnDashboard)
        if visible is not None:
            clauses.append("COALESCE(ml.visible_on_dashboard, TRUE) = %s")
            params.append(visible)
        if filters.q:
            query_text = f"%{filters.q}%"
            clauses.append(
                "(ml.record_code LIKE %s OR ml.name LIKE %s OR ml.layer_type LIKE %s "
                "OR ml.data_source LIKE %s OR CAST(ml.properties AS CHAR) LIKE %s)"
            )
            params.extend([query_text] * 5)
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def fetch_layers_mysql(
    *,
    filters: ManagedFilters | None = None,
    include_deleted: bool = False,
    layer_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    include_targets: bool = True,
) -> list[dict[str, Any]]:
    where_sql, params = mysql_layer_where(
        filters=filters,
        include_deleted=include_deleted,
        layer_id=layer_id,
    )
    select_sql = MYSQL_LAYER_SELECT_SQL if include_targets else MYSQL_LAYER_SUMMARY_SELECT_SQL
    sql = (
        f"{select_sql}{where_sql} "
        "ORDER BY ml.z_index IS NULL, ml.z_index, ml.updated_at DESC, ml.record_code"
    )
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [normalize_postgis_layer_row(row) for row in cur.fetchall()]


def count_layers_mysql(filters: ManagedFilters) -> int:
    where_sql, params = mysql_layer_where(filters=filters, include_deleted=filters.includeDeleted)
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM map_layers ml{where_sql}", tuple(params))
            row = cur.fetchone()
    return int(row[0] if row else 0)


def count_dashboard_linked_blocks_mysql() -> int:
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT links.forest_block_id)
                FROM map_layer_block_links links
                JOIN map_layers layers ON layers.id = links.map_layer_id
                WHERE layers.deleted_at IS NULL
                  AND layers.status = 'published'
                  AND COALESCE(layers.visible_on_dashboard, TRUE) = TRUE
                """
            )
            row = cur.fetchone()
    return int(row[0] if row else 0)


def list_map_layer_targets_mysql(
    record_id: str,
    *,
    kind: str,
    q: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    query = q.strip()
    if kind == "blocks":
        from_sql = (
            " FROM map_layer_block_links links "
            "JOIN forest_blocks targets ON targets.id = links.forest_block_id "
        )
        clauses = ["links.map_layer_id = %s", "targets.deleted_at IS NULL"]
        params: list[Any] = [record_id]
        if query:
            like = f"%{query}%"
            clauses.append("(targets.block_code LIKE %s OR targets.name LIKE %s)")
            params.extend([like, like])
        select_sql = (
            "SELECT targets.id, targets.block_code, targets.name, targets.county_name, "
            "targets.town_name, targets.village_name"
        )
        order_sql = " ORDER BY targets.block_code"
    else:
        from_sql = (
            " FROM map_layer_right_links links "
            "JOIN forest_rights targets ON targets.id = links.forest_right_id "
        )
        clauses = ["links.map_layer_id = %s", "targets.deleted_at IS NULL"]
        params = [record_id]
        if query:
            like = f"%{query}%"
            clauses.append(
                "(targets.archive_code LIKE %s OR targets.certificate_no LIKE %s "
                "OR targets.holder_name LIKE %s)"
            )
            params.extend([like, like, like])
        select_sql = (
            "SELECT targets.id, targets.archive_code, targets.certificate_no, "
            "targets.holder_name, targets.status"
        )
        order_sql = " ORDER BY targets.archive_code"
    where_sql = " WHERE " + " AND ".join(clauses)
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*){from_sql}{where_sql}", tuple(params))
            count_row = cur.fetchone()
            total = int(count_row[0] if count_row else 0)
            cur.execute(
                f"{select_sql}{from_sql}{where_sql}{order_sql} LIMIT %s OFFSET %s",
                tuple([*params, limit, offset]),
            )
            rows = cur.fetchall()
    if kind == "blocks":
        items = [
            {
                "id": str(row[0]),
                "blockCode": row[1] or "",
                "name": row[2] or "",
                "countyName": row[3] or "",
                "townName": row[4] or "",
                "villageName": row[5] or "",
            }
            for row in rows
        ]
    else:
        items = [
            {
                "id": str(row[0]),
                "archiveCode": row[1] or "",
                "certificateNo": row[2] or "",
                "holderName": row[3] or "",
                "status": row[4] or "",
            }
            for row in rows
        ]
    return {"kind": kind, "items": items, "total": total, "limit": limit, "offset": offset}


def find_layer_record_for_upsert(layer_id: str, record_code: str) -> dict[str, Any] | None:
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"{MYSQL_LAYER_SCALAR_SELECT_SQL} "
                    "WHERE ml.id = %s OR ml.record_code = %s LIMIT 1",
                    (layer_id, record_code),
                )
                row = cur.fetchone()
        return normalize_postgis_layer_row(row) if row else None
    records = fetch_layers_postgis(include_deleted=True) if use_postgis() else load_json_records(map_layers_json_path())
    return next(
        (
            record
            for record in records
            if str(record.get("id") or "") == layer_id
            or str(record.get("recordCode") or "") == record_code
        ),
        None,
    )


def execute_upsert_layer_scalar_mysql(cur: Any, layer: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO map_layers (
            id, record_code, name, status, layer_type, data_source, style,
            z_index, visible_on_dashboard, properties, created_at, updated_at, deleted_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            record_code = VALUES(record_code),
            name = VALUES(name),
            status = VALUES(status),
            layer_type = VALUES(layer_type),
            data_source = VALUES(data_source),
            style = VALUES(style),
            z_index = VALUES(z_index),
            visible_on_dashboard = VALUES(visible_on_dashboard),
            properties = VALUES(properties),
            updated_at = VALUES(updated_at),
            deleted_at = VALUES(deleted_at)
        """,
        (
            layer.get("id"),
            layer.get("recordCode"),
            layer.get("name"),
            layer.get("status"),
            layer.get("layerType"),
            layer.get("dataSource"),
            serializable_json(layer.get("style"), {}),
            layer.get("zIndex"),
            bool(layer.get("visibleOnDashboard", True)),
            serializable_json(layer.get("properties"), {}),
            mysql_datetime(layer.get("createdAt")),
            mysql_datetime(layer.get("updatedAt")),
            mysql_datetime(layer.get("deletedAt")),
        ),
    )


def sync_layer_links_mysql(cur: Any, layer: dict[str, Any], *, batch_size: int = 500) -> None:
    layer_id = str(layer.get("id") or "")
    size = max(1, int(batch_size))
    cur.execute("DELETE FROM map_layer_block_links WHERE map_layer_id = %s", (layer_id,))
    block_codes = compact_list(layer.get("linkedBlockCodes"))
    for start in range(0, len(block_codes), size):
        batch = block_codes[start : start + size]
        placeholders = ", ".join(["%s"] * len(batch))
        cur.execute(
            "INSERT IGNORE INTO map_layer_block_links (map_layer_id, forest_block_id) "
            f"SELECT %s, id FROM forest_blocks WHERE block_code IN ({placeholders})",
            tuple([layer_id, *batch]),
        )
    cur.execute("DELETE FROM map_layer_right_links WHERE map_layer_id = %s", (layer_id,))
    right_codes = compact_list(layer.get("linkedRightArchiveCodes"))
    for start in range(0, len(right_codes), size):
        batch = right_codes[start : start + size]
        placeholders = ", ".join(["%s"] * len(batch))
        cur.execute(
            "INSERT IGNORE INTO map_layer_right_links (map_layer_id, forest_right_id) "
            f"SELECT %s, id FROM forest_rights WHERE archive_code IN ({placeholders})",
            tuple([layer_id, *batch]),
        )


def execute_upsert_layer_mysql(cur: Any, layer: dict[str, Any]) -> None:
    execute_upsert_layer_scalar_mysql(cur, layer)
    sync_layer_links_mysql(cur, layer)


def upsert_import_batch_layer_mysql(
    layer: dict[str, Any],
    *,
    import_batch_id: str,
    connection_factory: Any = mysql_connect,
) -> None:
    """Persist an imported imagery layer and copy its normalized target relations."""
    layer_id = str(layer.get("id") or "")
    with connection_factory() as conn:
        with conn.cursor() as cur:
            execute_upsert_layer_scalar_mysql(cur, layer)
            cur.execute("DELETE FROM map_layer_block_links WHERE map_layer_id = %s", (layer_id,))
            cur.execute(
                """
                INSERT IGNORE INTO map_layer_block_links (map_layer_id, forest_block_id)
                SELECT %s, links.forest_block_id
                FROM import_batch_block_links links
                JOIN forest_blocks blocks ON blocks.id = links.forest_block_id
                WHERE links.import_batch_id = %s
                  AND links.import_action IN ('created', 'updated')
                  AND blocks.deleted_at IS NULL
                """,
                (layer_id, import_batch_id),
            )
            cur.execute("DELETE FROM map_layer_right_links WHERE map_layer_id = %s", (layer_id,))
            cur.execute(
                """
                INSERT IGNORE INTO map_layer_right_links (map_layer_id, forest_right_id)
                SELECT %s, links.forest_right_id
                FROM import_batch_right_links links
                JOIN forest_rights rights ON rights.id = links.forest_right_id
                WHERE links.import_batch_id = %s
                  AND rights.deleted_at IS NULL
                """,
                (layer_id, import_batch_id),
            )
        conn.commit()


def upsert_layer_mysql(
    layer: dict[str, Any],
    *,
    sync_links: bool = True,
    connection_factory: Any = mysql_connect,
) -> None:
    with connection_factory() as conn:
        with conn.cursor() as cur:
            execute_upsert_layer_scalar_mysql(cur, layer)
            if sync_links:
                sync_layer_links_mysql(cur, layer)
        conn.commit()


def upsert_layers_mysql(layers: list[dict[str, Any]]) -> None:
    if not layers:
        return
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            for layer in layers:
                execute_upsert_layer_mysql(cur, layer)
        conn.commit()


def layer_records() -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_layers_mysql()
    if use_postgis():
        return fetch_layers_postgis()
    return load_json_records(map_layers_json_path())


def all_layer_records() -> list[dict[str, Any]]:
    if use_mysql():
        return fetch_layers_mysql(include_deleted=True)
    if use_postgis():
        return fetch_layers_postgis(include_deleted=True)
    return load_json_records(map_layers_json_path())


def save_layer_records(records: list[dict[str, Any]]) -> None:
    if use_mysql():
        upsert_layers_mysql(records)
        return
    if use_postgis():
        upsert_layers_postgis(records)
        return
    save_json_records(map_layers_json_path(), records)


def filters_from_query(
    q: str = Query(default=""),
    status: str = Query(default=""),
    linkedBlockCode: str = Query(default=""),
    fieldKey: str = Query(default=""),
    fieldValue: str = Query(default=""),
    sourceType: str = Query(default=""),
    publishRiskStatus: str = Query(default=""),
    visibleOnDashboard: str = Query(default=""),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> ManagedFilters:
    return ManagedFilters(
        q=q,
        status=status,
        linkedBlockCode=linkedBlockCode,
        fieldKey=fieldKey,
        fieldValue=fieldValue,
        sourceType=sourceType,
        publishRiskStatus=publishRiskStatus,
        visibleOnDashboard=visibleOnDashboard,
        includeDeleted=includeDeleted,
        limit=limit,
        offset=offset,
    )


def module_location(record: dict[str, Any]) -> str:
    properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
    typed_location = properties.get("townVillage") or properties.get("serviceArea")
    if typed_location:
        return str(typed_location)
    location = [record.get("townName"), record.get("villageName")]
    return " / ".join(str(item) for item in location if item) or str(record.get("serviceArea") or record.get("area") or "-")


def business_core_value(record: dict[str, Any], key: str) -> Any:
    if key == "@status":
        return record.get("status")
    if key in record and record.get(key) is not None and record.get(key) != "":
        return record.get(key)
    properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
    if key in properties:
        return properties.get(key)
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    return payload.get(key)


def business_core_display(
    module_key: str,
    record: dict[str, Any],
    key: str,
    *,
    dictionary_catalog: dict[str, dict[str, Any]] | None = None,
) -> str:
    value = business_core_value(record, key)
    field = next((item for item in business_field_schema(module_key) if item.get("key") == key), None)
    if field:
        catalog = dictionary_catalog if dictionary_catalog is not None else business_dictionary_catalog()
        dictionary_items = dictionary_field_items(field, catalog)
        dictionary_option = (
            dictionary_items.get(str(value))
            if dictionary_items is not None
            else None
        )
        if dictionary_option:
            return str(dictionary_option.get("label") or dictionary_option.get("itemCode") or "-")
        option = next(
            (item for item in field.get("options") or [] if str(item.get("value")) == str(value)),
            None,
        )
        if option:
            return str(option.get("label") or option.get("value") or "-")
    return str(value if value is not None and value != "" else "-")


def business_record_is_active(module_key: str, record: dict[str, Any]) -> bool:
    field_key, active_values = BUSINESS_ACTIVITY_RULES.get(
        module_key,
        ("@status", {"active", "published", "open"}),
    )
    return str(business_core_value(record, field_key) or "") in active_values


def business_linked_display(record: dict[str, Any]) -> str:
    linked_codes = compact_list(record.get("linkedBlockCodes"))
    if linked_codes:
        return ", ".join(linked_codes)
    properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
    linked_count = int(properties.get("linkedBlockCount") or 0)
    return f"已关联 {linked_count} 个林班" if linked_count else "-"


def dashboard_row(
    module_key: str,
    record: dict[str, Any],
    *,
    dictionary_catalog: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    linked = business_linked_display(record)
    if module_key in BUSINESS_DASHBOARD_FIELDS:
        values = []
        for field_key in BUSINESS_DASHBOARD_FIELDS[module_key]:
            if field_key == "@linked":
                values.append(linked)
            elif field_key == "@location":
                values.append(module_location(record))
            else:
                values.append(
                    business_core_display(
                        module_key,
                        record,
                        field_key,
                        dictionary_catalog=dictionary_catalog,
                    )
                )
        return [str(record.get("name") or "-"), *values]
    if module_key == "farmers":
        return [str(record.get("name") or "-"), module_location(record), linked, str(record.get("status") or "-")]
    if module_key == "cooperatives":
        return [str(record.get("name") or "-"), module_location(record), linked, str(record.get("status") or "-")]
    if module_key == "enterprises":
        return [
            str(record.get("name") or "-"),
            str(record.get("mainBusiness") or record.get("businessType") or "-"),
            linked,
            str(record.get("inventoryStatus") or record.get("status") or "-"),
        ]
    if module_key == "plant-protection-events":
        return [
            linked,
            business_core_display(module_key, record, "issueType"),
            business_core_display(module_key, record, "riskLevel"),
            business_core_display(module_key, record, "handlingStatus"),
        ]
    if module_key == "materials":
        return [
            str(record.get("name") or "-"),
            business_core_display(module_key, record, "stock"),
            business_core_display(module_key, record, "usageStage"),
            business_core_display(module_key, record, "inventoryStatus"),
        ]
    if module_key == "policies":
        return [
            str(record.get("name") or "-"),
            business_core_display(module_key, record, "target"),
            business_core_display(module_key, record, "reviewStatus"),
            business_core_display(module_key, record, "deadline"),
        ]
    return [str(record.get("name") or "-"), linked, str(record.get("status") or "-")]


def admin_link_for_module(module_key: str, label: str | None = None) -> dict[str, str] | None:
    href = BUSINESS_ADMIN_PAGES.get(module_key)
    if not href:
        return None
    config = BUSINESS_MODULES.get(module_key, {})
    return {
        "label": str(label or config.get("totalLabel") or module_key),
        "href": href,
    }


def business_numeric_aggregates(module_key: str, records: list[dict[str, Any]]) -> tuple[dict[str, float], list[list[str]]]:
    aggregates: dict[str, float] = {}
    metrics: list[list[str]] = []
    rules = BUSINESS_AGGREGATE_RULES.get(module_key, [])
    for field_key, _label, _unit, operation in rules:
        values: list[float] = []
        for record in records:
            value = business_core_value(record, field_key)
            if value is None or value == "":
                continue
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                continue
        aggregate = sum(values)
        if operation == "average":
            aggregate = aggregate / len(values) if values else 0
        aggregates[field_key] = round(aggregate, 4)
    metrics = business_aggregate_metrics(module_key, aggregates)
    return aggregates, metrics


def business_aggregate_metrics(module_key: str, aggregates: dict[str, float]) -> list[list[str]]:
    metrics: list[list[str]] = []
    for field_key, label, unit, _operation in BUSINESS_AGGREGATE_RULES.get(module_key, []):
        rounded = round(float(aggregates.get(field_key) or 0), 4)
        display = f"{rounded:,.4f}".rstrip("0").rstrip(".")
        metrics.append([label, f"{display} {unit}".strip()])
    return metrics


def dashboard_payload(
    module_key: str,
    records: list[dict[str, Any]],
    *,
    summary: dict[str, Any] | None = None,
    dictionary_catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = BUSINESS_MODULES[module_key]
    dictionary_catalog = (
        dictionary_catalog
        if dictionary_catalog is not None
        else business_dictionary_catalog()
    )
    visible = active_records(records)
    linked_blocks = sorted({code for record in visible for code in record.get("linkedBlockCodes", [])})
    calculated_aggregates, calculated_metrics = business_numeric_aggregates(module_key, visible)
    summary = summary or {}
    total = int(summary["total"]) if "total" in summary else len(visible)
    linked_count = int(summary["linkedBlockCount"]) if "linkedBlockCount" in summary else len(linked_blocks)
    active_count = (
        int(summary["activeCount"])
        if "activeCount" in summary
        else len([record for record in visible if business_record_is_active(module_key, record)])
    )
    aggregates = summary.get("aggregates") if isinstance(summary.get("aggregates"), dict) else calculated_aggregates
    aggregate_metrics = business_aggregate_metrics(module_key, aggregates) if "aggregates" in summary else calculated_metrics
    admin_link = admin_link_for_module(module_key)
    admin_links = [admin_link] if admin_link else []
    return {
        "module": module_key,
        "title": config["title"],
        "subtitle": config["subtitle"],
        "metrics": [
            [config["totalLabel"], f"{total} {config['totalUnit']}"],
            [config["linkedLabel"], f"{linked_count} {config['linkedUnit']}"],
            [config["activeLabel"], f"{active_count}"],
            *aggregate_metrics,
        ],
        "aggregates": aggregates,
        "columns": config["columns"],
        "rows": [
            dashboard_row(
                module_key,
                record,
                dictionary_catalog=dictionary_catalog,
            )
            for record in visible
        ],
        "rowLimit": BUSINESS_DASHBOARD_ROW_LIMIT,
        "rowsTruncated": total > len(visible),
        "adminHref": admin_link["href"] if admin_link else "",
        "adminLinks": admin_links,
    }


def mysql_business_dashboard_payload(module_key: str) -> dict[str, Any]:
    records = fetch_business_records_mysql(
        module_key,
        limit=BUSINESS_DASHBOARD_ROW_LIMIT,
        offset=0,
        include_targets=False,
    )
    return dashboard_payload(
        module_key,
        records,
        summary=mysql_business_dashboard_summary(module_key),
    )


def industry_platform_dashboard_payload() -> dict[str, Any]:
    rows: list[list[str]] = []
    module_dashboards: list[dict[str, Any]] = []
    admin_links: list[dict[str, str]] = []
    active_count = 0
    total_records = 0

    for module_key, label in INDUSTRY_PLATFORM_MODULES:
        records = [] if use_mysql() else business_records(module_key)
        visible = active_records(records)
        module_dashboard = mysql_business_dashboard_payload(module_key) if use_mysql() else dashboard_payload(module_key, records)
        module_dashboards.append(module_dashboard)
        metric_values = module_dashboard.get("metrics") or []
        try:
            total_records += int(str(metric_values[0][1]).split()[0].replace(",", ""))
            active_count += int(str(metric_values[2][1]).replace(",", "")) if use_mysql() else 0
        except (ValueError, IndexError):
            total_records += len(visible)
        admin_link = admin_link_for_module(module_key, label)
        if admin_link:
            admin_links.append(admin_link)
        if use_mysql():
            for module_row in module_dashboard.get("rows") or []:
                linked = module_row[2] if len(module_row) > 2 else "-"
                status = module_row[3] if len(module_row) > 3 else "-"
                rows.append([label, str(module_row[0] if module_row else "-"), linked, status])
            continue
        for record in visible:
            linked = business_linked_display(record)
            module_row = dashboard_row(module_key, record)
            row_status = module_row[3] if len(module_row) > 3 else "-"
            status = row_status if row_status != "-" else str(record.get("status") or "-")
            if business_record_is_active(module_key, record):
                active_count += 1
            rows.append([label, str(record.get("name") or record.get("recordCode") or "-"), linked, status])

    return {
        "module": "industry-platform",
        "title": "产业平台信息卡",
        "subtitle": "交易撮合、物流溯源、二维码、供应链金融、价格指数和移动端服务",
        "metrics": [
            ["产业模块", f"{len(INDUSTRY_PLATFORM_MODULES)} 个"],
            ["业务记录", f"{total_records if use_mysql() else len(rows)} 条"],
            ["活跃事项", f"{active_count}"],
        ],
        "columns": ["模块", "记录名称", "关联林班", "状态"],
        "rows": rows,
        "modules": module_dashboards,
        "adminLinks": admin_links,
    }


@router.get("/business/modules")
def list_business_modules(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    return {"items": [{"key": key, **value} for key, value in BUSINESS_MODULES.items()]}


def business_reference_source_payload(
    module_key: str,
    *,
    query_text: str,
    fetch_limit: int,
) -> tuple[list[dict[str, Any]], int]:
    filters = ManagedFilters(q=query_text, limit=fetch_limit, offset=0)
    if use_mysql():
        return (
            fetch_business_records_mysql(
                module_key,
                filters=filters,
                limit=fetch_limit,
                offset=0,
                include_targets=False,
            ),
            count_business_records_mysql(module_key, filters),
        )
    if use_postgis():
        return (
            fetch_business_records_postgis(
                module_key,
                filters=filters,
                limit=fetch_limit,
                offset=0,
            ),
            count_business_records_postgis(module_key, filters),
        )
    payload = list_records(business_records(module_key), filters)
    return payload["items"], int(payload["total"])


@router.get("/business-reference-options/{group_key}")
def list_business_reference_options(
    group_key: str,
    q: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    _ = context
    source_modules = BUSINESS_REFERENCE_GROUPS.get(group_key)
    if source_modules is None:
        raise HTTPException(status_code=404, detail="Business reference group not found")
    fetch_limit = min(500, max(100, limit + offset))
    items: list[dict[str, Any]] = []
    total = 0
    for module_key in source_modules:
        records, source_total = business_reference_source_payload(
            module_key,
            query_text=q.strip(),
            fetch_limit=fetch_limit,
        )
        total += source_total
        source_label = BUSINESS_REFERENCE_SOURCE_LABELS[module_key]
        for record in records:
            record_code = str(record.get("recordCode") or "").strip()
            name = str(record.get("name") or record_code).strip()
            if not record_code:
                continue
            items.append(
                {
                    "value": record_code,
                    "label": f"{name} · {source_label}",
                    "recordCode": record_code,
                    "name": name,
                    "moduleKey": module_key,
                    "moduleLabel": source_label,
                }
            )
    items.sort(key=lambda item: (item["label"], item["recordCode"]))
    return {
        "items": items[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/references/business/{module_key}")
def list_business_record_reference_options(
    module_key: str,
    q: str = Query(default=""),
    status: str = Query(default="active"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    module_key = validate_business_module(module_key)
    require_permission(context, permission_for_business_module(module_key, "view"))
    fetch_limit = min(500, max(100, limit + offset))
    records, _source_total = business_reference_source_payload(
        module_key,
        query_text=q.strip(),
        fetch_limit=fetch_limit,
    )
    items = []
    for record in records:
        if status and str(record.get("status") or "") != status:
            continue
        record_id = str(record.get("id") or "").strip()
        if not record_id:
            continue
        record_code = str(record.get("recordCode") or "").strip()
        name = str(record.get("name") or record_code or record_id).strip()
        items.append(
            {
                "id": record_id,
                "value": record_id,
                "label": f"{name} · {record_code}" if record_code else name,
                "recordCode": record_code,
                "name": name,
                "status": str(record.get("status") or ""),
                "moduleKey": module_key,
            }
        )
    items.sort(key=lambda item: (item["label"], item["id"]))
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


@router.get("/industry-platform/dashboard")
def get_industry_platform_dashboard(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    return industry_platform_dashboard_payload()


@router.get("/business/{module_key}/dashboard")
def get_business_dashboard(
    module_key: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    module_key = validate_business_module(module_key)
    if use_mysql():
        return mysql_business_dashboard_payload(module_key)
    return dashboard_payload(module_key, business_records(module_key))


@router.get("/business/{module_key}")
def list_business_records(
    module_key: str,
    filters: ManagedFilters = Depends(filters_from_query),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    module_key = validate_business_module(module_key)
    require_permission(
        context,
        permission_for_business_module(module_key, "restore" if filters.includeDeleted else "view"),
    )
    if use_mysql():
        return {
            "items": fetch_business_records_mysql(
                module_key,
                filters=filters,
                include_deleted=filters.includeDeleted,
                limit=filters.limit,
                offset=filters.offset,
                include_targets=False,
            ),
            "total": count_business_records_mysql(module_key, filters),
            "limit": filters.limit,
            "offset": filters.offset,
        }
    if use_postgis():
        return {
            "items": fetch_business_records_postgis(
                module_key,
                filters=filters,
                include_deleted=filters.includeDeleted,
                limit=filters.limit,
                offset=filters.offset,
            ),
            "total": count_business_records_postgis(module_key, filters),
            "limit": filters.limit,
            "offset": filters.offset,
        }
    return list_records(business_records(module_key), filters)


@router.post("/business/{module_key}")
def create_business_record(
    module_key: str,
    payload: ManagedRecordIn,
    context: AuthContext = Depends(request_context),
) -> ManagedRecordOut:
    module_key = validate_business_module(module_key)
    require_permission(context, permission_for_business_module(module_key, "create"))
    records = [] if use_mysql() else business_records(module_key)
    payload_data = payload.model_dump(mode="json")
    form_version = int(payload_data.get("formVersion") or 1)
    payload_data["formVersion"] = form_version
    payload_data["properties"] = normalize_business_properties(
        module_key,
        payload_data.get("properties"),
        enforce_required=form_version >= 2,
    )
    payload_data["linkedRecords"] = normalize_business_record_links(
        module_key,
        payload_data.get("linkedRecords"),
        payload_data["properties"],
        context=context,
        enforce_required=form_version >= 2,
    )
    normalized_record = normalize_record(payload_data)
    if module_key == "product-qrcodes":
        properties = dict(normalized_record.get("properties") or {})
        properties.setdefault("qrCode", f"SB-{normalized_record['recordCode']}")
        properties.setdefault("scanCount", 0)
        properties.setdefault("codeType", "batch" if properties.get("batchNo") else "product")
        properties.setdefault("publishStatus", "draft")
        normalized_record["properties"] = normalize_business_properties(module_key, properties)
    created = append_business_audit_event(
        module_key,
        normalized_record,
        "create",
        context,
        changed_fields=[
            "recordCode",
            "name",
            "status",
            "linkedBlockCodes",
            "linkedRightArchiveCodes",
            "linkedRecords",
            "properties",
        ],
    )
    if use_mysql():
        upsert_business_record_mysql(module_key, created, sync_links=True, sync_record_links=True)
    else:
        records.append(created)
        save_business_records(module_key, records)
    return ManagedRecordOut.model_validate(created)


@router.get("/business/{module_key}/events")
def list_business_record_audit_events(
    module_key: str,
    q: str = Query(default=""),
    action: str = Query(default=""),
    recordId: str = Query(default=""),
    recordCode: str = Query(default=""),
    linkedBlockCode: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    module_key = validate_business_module(module_key)
    require_permission(context, permission_for_business_module(module_key, "view"))
    return list_business_events(
        module_key,
        q=q,
        action=action,
        record_id=recordId,
        record_code=recordCode,
        linked_block_code=linkedBlockCode,
        limit=limit,
        offset=offset,
    )


@router.get("/business/{module_key}/events.csv")
def export_business_record_audit_events_csv(
    module_key: str,
    q: str = Query(default=""),
    action: str = Query(default=""),
    recordId: str = Query(default=""),
    recordCode: str = Query(default=""),
    linkedBlockCode: str = Query(default=""),
    context: AuthContext = Depends(request_context),
):
    module_key = validate_business_module(module_key)
    require_permission(context, permission_for_business_module(module_key, "export"))
    payload = list_business_events(
        module_key,
        q=q,
        action=action,
        record_id=recordId,
        record_code=recordCode,
        linked_block_code=linkedBlockCode,
        limit=1000,
        offset=0,
    )
    return csv_download_response(
        f"business-{module_key}-events.csv",
        [
            "eventId",
            "module",
            "recordId",
            "recordCode",
            "recordName",
            "action",
            "actor",
            "at",
            "status",
            "linkedBlockCodes",
            "linkedRightArchiveCodes",
            "changedFields",
            "deletedAt",
            "adminHref",
            "summary",
        ],
        payload.get("items") or [],
    )


@router.get("/business/{module_key}/{record_id}/targets")
def list_business_record_targets(
    module_key: str,
    record_id: str,
    kind: str = Query(default="blocks"),
    q: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    module_key = validate_business_module(module_key)
    require_permission(context, permission_for_business_module(module_key, "view"))
    if kind not in {"blocks", "rights"}:
        raise HTTPException(status_code=422, detail="kind must be blocks or rights")
    if use_mysql():
        existing = fetch_business_records_mysql(
            module_key,
            record_id=record_id,
            include_deleted=True,
            limit=1,
            include_targets=False,
        )
        if not existing or existing[0].get("deletedAt"):
            raise HTTPException(status_code=404, detail="Record not found")
        return list_business_record_targets_mysql(
            record_id,
            kind=kind,
            q=q,
            limit=limit,
            offset=offset,
        )
    records = business_records(module_key)
    existing = get_record_or_404(records, record_id)
    source_key = "linkedBlockCodes" if kind == "blocks" else "linkedRightArchiveCodes"
    value_key = "blockCode" if kind == "blocks" else "archiveCode"
    query = q.strip().lower()
    values = compact_list(existing.get(source_key))
    if query:
        values = [value for value in values if query in value.lower()]
    return {
        "kind": kind,
        "items": [{value_key: value} for value in values[offset : offset + limit]],
        "total": len(values),
        "limit": limit,
        "offset": offset,
    }


@router.get("/business/{module_key}/{record_id}")
def get_business_record(
    module_key: str,
    record_id: str,
    context: AuthContext = Depends(request_context),
) -> ManagedRecordOut:
    module_key = validate_business_module(module_key)
    require_permission(context, permission_for_business_module(module_key, "view"))
    if use_mysql():
        items = fetch_business_records_mysql(module_key, record_id=record_id, limit=1, include_targets=False)
        if not items:
            raise HTTPException(status_code=404, detail="Record not found")
        record = items[0]
    elif use_postgis():
        items = fetch_business_records_postgis(module_key, record_id=record_id, limit=1)
        if not items:
            raise HTTPException(status_code=404, detail="Record not found")
        record = items[0]
    else:
        record = get_record_or_404(business_records(module_key), record_id)
    return ManagedRecordOut.model_validate(record)


@router.patch("/business/{module_key}/{record_id}")
def patch_business_record(
    module_key: str,
    record_id: str,
    payload: ManagedRecordPatch,
    context: AuthContext = Depends(request_context),
) -> ManagedRecordOut:
    module_key = validate_business_module(module_key)
    require_permission(context, permission_for_business_module(module_key, "update"))
    if use_mysql():
        patch_data = {
            key: value
            for key, value in payload.model_dump(mode="json", exclude_unset=True).items()
            if value is not None
        }
        property_keys = set((patch_data.get("properties") or {}).keys())
        business_relation_keys = {str(field.get("key") or "") for field in business_relation_fields(module_key)}
        relation_update = bool({"linkedBlockCodes", "linkedRightArchiveCodes"} & set(patch_data))
        record_relation_update = "linkedRecords" in patch_data or bool(property_keys & business_relation_keys)
        if relation_update:
            matches = fetch_business_records_mysql(module_key, record_id=record_id, limit=1)
            record = matches[0] if matches else None
        else:
            record = find_business_record_for_upsert(module_key, record_id)
        if not record or record.get("deletedAt"):
            raise HTTPException(status_code=404, detail="Record not found")
        form_version = int(patch_data.get("formVersion") or record.get("formVersion") or 1)
        patch_data["formVersion"] = form_version
        if "properties" in patch_data:
            patch_data["properties"] = normalize_business_properties(
                module_key,
                patch_data.get("properties"),
                previous_properties=record.get("properties"),
                enforce_required=form_version >= 2,
            )
        if record_relation_update:
            relation_properties = patch_data.get("properties") or dict(record.get("properties") or {})
            patch_data["linkedRecords"] = normalize_business_record_links(
                module_key,
                patch_data.get("linkedRecords"),
                relation_properties,
                context=context,
                enforce_required=form_version >= 2,
            )
        patched = normalize_record(
            {
                **record,
                **patch_data,
                "id": record_id,
                "createdAt": record.get("createdAt", now_iso()),
                "deletedAt": record.get("deletedAt"),
            }
        )
        changed_fields = business_changed_fields(record, patched)
        patched = append_business_audit_event(
            module_key,
            patched,
            "update",
            context,
            before=record,
            changed_fields=changed_fields,
        )
        upsert_business_record_mysql(
            module_key,
            patched,
            sync_links=relation_update,
            sync_record_links=record_relation_update,
        )
        return ManagedRecordOut.model_validate(patched)
    records = business_records(module_key)
    for index, record in enumerate(records):
        if str(record.get("id")) != str(record_id) or record.get("deletedAt"):
            continue
        patch_data = {
            key: value
            for key, value in payload.model_dump(mode="json", exclude_unset=True).items()
            if value is not None
        }
        property_keys = set((patch_data.get("properties") or {}).keys())
        business_relation_keys = {str(field.get("key") or "") for field in business_relation_fields(module_key)}
        record_relation_update = "linkedRecords" in patch_data or bool(property_keys & business_relation_keys)
        form_version = int(patch_data.get("formVersion") or record.get("formVersion") or 1)
        patch_data["formVersion"] = form_version
        if "properties" in patch_data:
            patch_data["properties"] = normalize_business_properties(
                module_key,
                patch_data.get("properties"),
                previous_properties=record.get("properties"),
                enforce_required=form_version >= 2,
            )
        if record_relation_update:
            relation_properties = patch_data.get("properties") or dict(record.get("properties") or {})
            patch_data["linkedRecords"] = normalize_business_record_links(
                module_key,
                patch_data.get("linkedRecords"),
                relation_properties,
                context=context,
                enforce_required=form_version >= 2,
            )
        patched = normalize_record(
            {
                **record,
                **patch_data,
                "id": record_id,
                "createdAt": record.get("createdAt", now_iso()),
                "deletedAt": record.get("deletedAt"),
            }
        )
        changed_fields = business_changed_fields(record, patched)
        patched = append_business_audit_event(module_key, patched, "update", context, before=record, changed_fields=changed_fields)
        records[index] = patched
        save_business_records(module_key, records)
        return ManagedRecordOut.model_validate(patched)
    raise HTTPException(status_code=404, detail="Record not found")


@router.delete("/business/{module_key}/{record_id}")
def delete_business_record(
    module_key: str,
    record_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    module_key = validate_business_module(module_key)
    require_permission(context, permission_for_business_module(module_key, "delete"))
    if use_mysql():
        record = find_business_record_for_upsert(module_key, record_id)
        if not record or record.get("deletedAt"):
            raise HTTPException(status_code=404, detail="Record not found")
        deleted_at = now_iso()
        deleted = append_business_audit_event(
            module_key,
            {**record, "deletedAt": deleted_at, "updatedAt": deleted_at},
            "delete",
            context,
            before=record,
            changed_fields=["deletedAt"],
        )
        upsert_business_record_mysql(module_key, deleted, sync_links=False)
        return {"ok": True, "deleted": record_id}
    records = business_records(module_key)
    for index, record in enumerate(records):
        if str(record.get("id")) != str(record_id) or record.get("deletedAt"):
            continue
        deleted_at = now_iso()
        deleted = {
            **record,
            "deletedAt": deleted_at,
            "updatedAt": deleted_at,
        }
        deleted = append_business_audit_event(
            module_key,
            deleted,
            "delete",
            context,
            before=record,
            changed_fields=["deletedAt"],
        )
        records[index] = deleted
        save_business_records(module_key, records)
        return {"ok": True, "deleted": record_id}
    raise HTTPException(status_code=404, detail="Record not found")


@router.post("/business/{module_key}/{record_id}/restore")
def restore_business_record(
    module_key: str,
    record_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    module_key = validate_business_module(module_key)
    require_permission(context, permission_for_business_module(module_key, "restore"))
    if use_mysql():
        record = find_business_record_for_upsert(module_key, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        if not record.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Record is not deleted")
        restored = append_business_audit_event(
            module_key,
            {**record, "deletedAt": None, "updatedAt": now_iso()},
            "restore",
            context,
            before=record,
            changed_fields=["deletedAt"],
        )
        upsert_business_record_mysql(module_key, restored, sync_links=False)
        return {"ok": True, "restored": record_id, "item": restored}
    records = all_business_records(module_key)
    for index, record in enumerate(records):
        if str(record.get("id")) != str(record_id):
            continue
        if not record.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Record is not deleted")
        restored = {
            **record,
            "deletedAt": None,
            "updatedAt": now_iso(),
        }
        restored = append_business_audit_event(
            module_key,
            restored,
            "restore",
            context,
            before=record,
            changed_fields=["deletedAt"],
        )
        records[index] = restored
        save_business_records(module_key, records)
        return {"ok": True, "restored": record_id, "item": restored}
    raise HTTPException(status_code=404, detail="Record not found")


@router.get("/map-layers")
def list_map_layers(
    filters: ManagedFilters = Depends(filters_from_query),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    if filters.includeDeleted:
        require_permission(context, MAP_LAYER_PERMISSIONS["restore"])
    if use_mysql():
        items = fetch_layers_mysql(
            filters=filters,
            include_deleted=filters.includeDeleted,
            limit=filters.limit,
            offset=filters.offset,
            include_targets=False,
        )
        return {
            "items": [enrich_map_layer_record(item) for item in items],
            "total": count_layers_mysql(filters),
            "limit": filters.limit,
            "offset": filters.offset,
        }
    if use_postgis():
        items = fetch_layers_postgis(
            filters=filters,
            include_deleted=filters.includeDeleted,
            limit=filters.limit,
            offset=filters.offset,
        )
        return {
            "items": [enrich_map_layer_record(item) for item in items],
            "total": count_layers_postgis(filters),
            "limit": filters.limit,
            "offset": filters.offset,
        }
    return map_layer_list_payload(layer_records(), filters)


@router.get("/map-layers/events")
def list_map_layer_audit_events(
    q: str = Query(default=""),
    action: str = Query(default=""),
    layerId: str = Query(default=""),
    recordCode: str = Query(default=""),
    sourceType: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, MAP_LAYER_PERMISSIONS["view"])
    return list_map_layer_events(
        q=q,
        action=action,
        layer_id=layerId,
        record_code=recordCode,
        source_type=sourceType,
        limit=limit,
        offset=offset,
    )


@router.get("/map-layers/events.csv")
def export_map_layer_audit_events_csv(
    q: str = Query(default=""),
    action: str = Query(default=""),
    layerId: str = Query(default=""),
    recordCode: str = Query(default=""),
    sourceType: str = Query(default=""),
    context: AuthContext = Depends(request_context),
):
    require_permission(context, MAP_LAYER_PERMISSIONS["export"])
    payload = list_map_layer_events(
        q=q,
        action=action,
        layer_id=layerId,
        record_code=recordCode,
        source_type=sourceType,
        limit=1000,
        offset=0,
    )
    return csv_download_response(
        "map-layer-events.csv",
        [
            "eventId",
            "layerId",
            "recordCode",
            "layerName",
            "action",
            "actor",
            "at",
            "status",
            "visibleOnDashboard",
            "sourceType",
            "publishRiskStatus",
            "changedFields",
            "adminHref",
            "dashboardHref",
            "sourceLinks",
            "summary",
        ],
        payload.get("items") or [],
    )


@router.get("/map-layers/dashboard")
def get_dashboard_map_layers(context: AuthContext = Depends(request_context)) -> dict[str, Any]:
    return dashboard_map_layers_payload()


@router.get("/map-layers/{record_id}/targets")
def list_map_layer_targets(
    record_id: str,
    kind: str = Query(default="blocks"),
    q: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, MAP_LAYER_PERMISSIONS["view"])
    if kind not in {"blocks", "rights"}:
        raise HTTPException(status_code=422, detail="kind must be blocks or rights")
    existing = find_layer_record_for_upsert(record_id, record_id)
    if not existing or existing.get("deletedAt"):
        raise HTTPException(status_code=404, detail="Record not found")
    if use_mysql():
        return list_map_layer_targets_mysql(
            record_id,
            kind=kind,
            q=q,
            limit=limit,
            offset=offset,
        )
    source_key = "linkedBlockCodes" if kind == "blocks" else "linkedRightArchiveCodes"
    value_key = "blockCode" if kind == "blocks" else "archiveCode"
    query = q.strip().lower()
    values = compact_list(existing.get(source_key))
    if query:
        values = [value for value in values if query in value.lower()]
    return {
        "kind": kind,
        "items": [{value_key: value} for value in values[offset : offset + limit]],
        "total": len(values),
        "limit": limit,
        "offset": offset,
    }


@router.post("/map-layers")
def create_map_layer(
    payload: MapLayerIn,
    context: AuthContext = Depends(request_context),
) -> MapLayerOut:
    require_permission(context, MAP_LAYER_PERMISSIONS["create"])
    records = [] if use_mysql() else all_layer_records()
    created = normalize_record(payload.model_dump(mode="json"))
    created = append_map_layer_audit_event(
        created,
        "create",
        context,
        changed_fields=[
            "recordCode",
            "name",
            "status",
            "layerType",
            "dataSource",
            "style",
            "zIndex",
            "visibleOnDashboard",
            "linkedBlockCodes",
            "linkedRightArchiveCodes",
            "properties",
        ],
    )
    if use_mysql():
        upsert_layer_mysql(created, sync_links=True)
    else:
        records.append(created)
        save_layer_records(records)
    return MapLayerOut.model_validate(enrich_map_layer_record(created))


@router.get("/map-layers/{record_id}")
def get_map_layer(
    record_id: str,
    context: AuthContext = Depends(request_context),
) -> MapLayerOut:
    require_permission(context, MAP_LAYER_PERMISSIONS["view"])
    if use_mysql():
        items = fetch_layers_mysql(layer_id=record_id, limit=1, include_targets=False)
        if not items:
            raise HTTPException(status_code=404, detail="Record not found")
        record = items[0]
    elif use_postgis():
        items = fetch_layers_postgis(layer_id=record_id, limit=1)
        if not items:
            raise HTTPException(status_code=404, detail="Record not found")
        record = items[0]
    else:
        record = get_record_or_404(layer_records(), record_id)
    return MapLayerOut.model_validate(enrich_map_layer_record(record))


@router.get("/map-layers/{record_id}/publication-receipt.json")
def export_map_layer_publication_receipt(
    record_id: str,
    context: AuthContext = Depends(request_context),
):
    require_permission(context, MAP_LAYER_PERMISSIONS["export"])
    if use_mysql():
        matches = fetch_layers_mysql(layer_id=record_id, limit=1, include_targets=False)
        if not matches:
            raise HTTPException(status_code=404, detail="Record not found")
        layer = matches[0]
    elif use_postgis():
        matches = fetch_layers_postgis(layer_id=record_id, limit=1)
        if not matches:
            raise HTTPException(status_code=404, detail="Record not found")
        layer = matches[0]
    else:
        layer = get_record_or_404(layer_records(), record_id)
    record_code = safe_download_stem(str(layer.get("recordCode") or record_id), "layer")
    return json_download_response(
        f"map-layer-publication-receipt-{record_code}.json",
        map_layer_publication_receipt(layer, context),
    )


@router.patch("/map-layers/{record_id}")
def patch_map_layer(
    record_id: str,
    payload: MapLayerPatch,
    context: AuthContext = Depends(request_context),
) -> MapLayerOut:
    require_permission(context, MAP_LAYER_PERMISSIONS["update"])
    if use_mysql():
        patch_data = {
            key: value
            for key, value in payload.model_dump(mode="json", exclude_unset=True).items()
            if value is not None
        }
        relation_update = bool({"linkedBlockCodes", "linkedRightArchiveCodes"} & set(patch_data))
        if relation_update:
            matches = fetch_layers_mysql(layer_id=record_id, include_deleted=False, limit=1)
            record = matches[0] if matches else None
        else:
            record = find_layer_record_for_upsert(record_id, record_id)
        if not record or record.get("deletedAt"):
            raise HTTPException(status_code=404, detail="Record not found")
        patched = normalize_record(
            {
                **record,
                **patch_data,
                "id": record_id,
                "createdAt": record.get("createdAt", now_iso()),
                "deletedAt": record.get("deletedAt"),
            }
        )
        changed_fields = map_layer_changed_fields(record, patched)
        if "visibleOnDashboard" in changed_fields or (
            "status" in changed_fields and patched.get("status") == "published"
        ):
            require_permission(context, MAP_LAYER_PERMISSIONS["publish"])
        patched = append_map_layer_audit_event(
            patched,
            "update",
            context,
            before=record,
            changed_fields=changed_fields,
        )
        upsert_layer_mysql(patched, sync_links=relation_update)
        return MapLayerOut.model_validate(enrich_map_layer_record(patched))
    records = all_layer_records()
    for index, record in enumerate(records):
        if str(record.get("id")) != str(record_id) or record.get("deletedAt"):
            continue
        patched = normalize_record(
            {
                **record,
                **{key: value for key, value in payload.model_dump(mode="json", exclude_unset=True).items() if value is not None},
                "id": record_id,
                "createdAt": record.get("createdAt", now_iso()),
                "deletedAt": record.get("deletedAt"),
            }
        )
        changed_fields = map_layer_changed_fields(record, patched)
        if "visibleOnDashboard" in changed_fields or ("status" in changed_fields and patched.get("status") == "published"):
            require_permission(context, MAP_LAYER_PERMISSIONS["publish"])
        patched = append_map_layer_audit_event(patched, "update", context, before=record, changed_fields=changed_fields)
        records[index] = patched
        save_layer_records(records)
        return MapLayerOut.model_validate(enrich_map_layer_record(patched))
    raise HTTPException(status_code=404, detail="Record not found")


@router.post("/map-layers/{record_id}/publish")
def publish_map_layer(
    record_id: str,
    payload: MapLayerPublishRequest,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, MAP_LAYER_PERMISSIONS["publish"])
    if use_mysql():
        record = find_layer_record_for_upsert(record_id, record_id)
        if not record or record.get("deletedAt"):
            raise HTTPException(status_code=404, detail="Record not found")
        default_status = "published" if payload.visibleOnDashboard else "paused"
        next_status = str(payload.status or default_status).strip() or default_status
        updated = normalize_record(
            {
                **record,
                "id": record_id,
                "status": next_status,
                "visibleOnDashboard": bool(payload.visibleOnDashboard),
                "createdAt": record.get("createdAt", now_iso()),
                "deletedAt": record.get("deletedAt"),
            }
        )
        changed_fields = map_layer_changed_fields(record, updated)
        updated = append_map_layer_audit_event(
            updated,
            "publish",
            context,
            before=record,
            changed_fields=changed_fields,
        )
        upsert_layer_mysql(updated, sync_links=False)
        events = (updated.get("properties") or {}).get("auditEvents") or []
        return {
            "ok": True,
            "layer": MapLayerOut.model_validate(enrich_map_layer_record(updated)),
            "event": events[-1] if events else {},
        }
    records = all_layer_records()
    for index, record in enumerate(records):
        if str(record.get("id")) != str(record_id) or record.get("deletedAt"):
            continue
        default_status = "published" if payload.visibleOnDashboard else "paused"
        next_status = str(payload.status or default_status).strip() or default_status
        updated = normalize_record(
            {
                **record,
                "id": record_id,
                "status": next_status,
                "visibleOnDashboard": bool(payload.visibleOnDashboard),
                "createdAt": record.get("createdAt", now_iso()),
                "deletedAt": record.get("deletedAt"),
            }
        )
        changed_fields = map_layer_changed_fields(record, updated)
        updated = append_map_layer_audit_event(updated, "publish", context, before=record, changed_fields=changed_fields)
        records[index] = updated
        save_layer_records(records)
        events = (updated.get("properties") or {}).get("auditEvents") or []
        event = events[-1] if events else {}
        return {
            "ok": True,
            "layer": MapLayerOut.model_validate(enrich_map_layer_record(updated)),
            "event": event,
        }
    raise HTTPException(status_code=404, detail="Record not found")


@router.delete("/map-layers/{record_id}")
def delete_map_layer(
    record_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, MAP_LAYER_PERMISSIONS["delete"])
    if use_mysql():
        record = find_layer_record_for_upsert(record_id, record_id)
        if not record or record.get("deletedAt"):
            raise HTTPException(status_code=404, detail="Record not found")
        deleted_at = now_iso()
        deleted = append_map_layer_audit_event(
            {**record, "deletedAt": deleted_at, "updatedAt": deleted_at},
            "delete",
            context,
            before=record,
            changed_fields=["deletedAt"],
        )
        upsert_layer_mysql(deleted, sync_links=False)
        return {"ok": True, "deleted": record_id}
    records = all_layer_records()
    for index, record in enumerate(records):
        if str(record.get("id")) != str(record_id) or record.get("deletedAt"):
            continue
        deleted_at = now_iso()
        deleted = {
            **record,
            "deletedAt": deleted_at,
            "updatedAt": deleted_at,
        }
        deleted = append_map_layer_audit_event(deleted, "delete", context, before=record, changed_fields=["deletedAt"])
        records[index] = deleted
        save_layer_records(records)
        return {"ok": True, "deleted": record_id}
    raise HTTPException(status_code=404, detail="Record not found")


@router.post("/map-layers/{record_id}/restore")
def restore_map_layer(
    record_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, MAP_LAYER_PERMISSIONS["restore"])
    if use_mysql():
        record = find_layer_record_for_upsert(record_id, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        if not record.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Record is not deleted")
        restored = append_map_layer_audit_event(
            {**record, "deletedAt": None, "updatedAt": now_iso()},
            "restore",
            context,
            before=record,
            changed_fields=["deletedAt"],
        )
        upsert_layer_mysql(restored, sync_links=False)
        return {"ok": True, "restored": record_id, "item": enrich_map_layer_record(restored)}
    records = all_layer_records()
    for index, record in enumerate(records):
        if str(record.get("id")) != str(record_id):
            continue
        if not record.get("deletedAt"):
            raise HTTPException(status_code=409, detail="Record is not deleted")
        restored = {
            **record,
            "deletedAt": None,
            "updatedAt": now_iso(),
        }
        restored = append_map_layer_audit_event(restored, "restore", context, before=record, changed_fields=["deletedAt"])
        records[index] = restored
        save_layer_records(records)
        return {"ok": True, "restored": record_id, "item": enrich_map_layer_record(restored)}
    raise HTTPException(status_code=404, detail="Record not found")
