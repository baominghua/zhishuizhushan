from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from . import database
from .admin_roles import require_permission
from .auth import AuthContext, request_context
from .database import (
    dictionary_items_json_path,
    dictionary_types_json_path,
    load_json_records,
    mysql_connect,
    save_json_records,
    use_mysql,
    use_postgis,
)


router = APIRouter(prefix="/api", tags=["dictionaries"])

TYPE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,99}$")
ITEM_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
STANDARD_DIVISION_RESOURCE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "cn-administrative-divisions-2023.json"
)
STANDARD_DIVISION_SHA256 = "eaec154ce55f9683fbae09a21cea7d8523e4074f323602cf92b6840611139c5b"
ADMIN_DIVISION_NAMESPACE = uuid.UUID("8fa23946-eb3c-5f40-8ab3-d5cf10675b0a")
STANDARD_DIVISION_LEVELS = ("province", "city", "county", "town")
ADMIN_DIVISION_PARENT_LEVEL = {
    "city": "province",
    "county": "city",
    "town": "county",
    "village": "town",
}
STANDARD_DIVISION_SPECIAL_REGIONS = (
    ("710000", "台湾省"),
    ("810000", "香港特别行政区"),
    ("820000", "澳门特别行政区"),
)


DEFAULT_DICTIONARIES = [
    {
        "typeCode": "administrative-divisions",
        "name": "行政区划",
        "category": "administrative",
        "hierarchyEnabled": True,
        "valueMode": "code",
        "description": "省、市、县区、乡镇、村级行政区划",
        "sortOrder": 10,
        "items": [
            {
                "itemCode": "350000",
                "label": "福建省",
                "levelCode": "province",
                "fullName": "福建省",
                "sortOrder": 10,
            },
            {
                "itemCode": "350700",
                "label": "南平市",
                "parentCode": "350000",
                "levelCode": "city",
                "fullName": "福建省 / 南平市",
                "sortOrder": 10,
            },
            {
                "itemCode": "350703",
                "label": "建阳区",
                "parentCode": "350700",
                "levelCode": "county",
                "fullName": "福建省 / 南平市 / 建阳区",
                "sortOrder": 10,
            },
            {
                "itemCode": "350783",
                "label": "建瓯市",
                "parentCode": "350700",
                "levelCode": "county",
                "fullName": "福建省 / 南平市 / 建瓯市",
                "sortOrder": 20,
            },
            {
                "itemCode": "350703105",
                "label": "麻沙镇",
                "parentCode": "350703",
                "levelCode": "town",
                "fullName": "福建省 / 南平市 / 建阳区 / 麻沙镇",
                "sortOrder": 10,
                "searchAliases": ["麻沙镇", "105", "350784105"],
                "metadata": {
                    "codeSystem": "statistical-division",
                    "referenceYear": 2023,
                },
            },
            {
                "itemCode": "350703106",
                "label": "黄坑镇",
                "parentCode": "350703",
                "levelCode": "town",
                "fullName": "福建省 / 南平市 / 建阳区 / 黄坑镇",
                "sortOrder": 20,
                "searchAliases": ["黄坑镇", "106", "350784106"],
                "metadata": {
                    "codeSystem": "statistical-division",
                    "referenceYear": 2023,
                },
            },
            {
                "itemCode": "350703105217",
                "label": "杜潭村",
                "parentCode": "350703105",
                "levelCode": "village",
                "fullName": "福建省 / 南平市 / 建阳区 / 麻沙镇 / 杜潭村",
                "sortOrder": 10,
                "searchAliases": ["杜潭村", "217", "杜墰"],
            },
            {
                "itemCode": "350703105218",
                "label": "溪头村",
                "parentCode": "350703105",
                "levelCode": "village",
                "fullName": "福建省 / 南平市 / 建阳区 / 麻沙镇 / 溪头村",
                "sortOrder": 20,
                "searchAliases": ["溪头村", "218"],
            },
            {
                "itemCode": "350703106202",
                "label": "新峰村",
                "parentCode": "350703106",
                "levelCode": "village",
                "fullName": "福建省 / 南平市 / 建阳区 / 黄坑镇 / 新峰村",
                "sortOrder": 10,
                "searchAliases": ["新峰村", "202"],
            },
            {
                "itemCode": "350783105",
                "label": "小桥镇",
                "parentCode": "350783",
                "levelCode": "town",
                "fullName": "福建省 / 南平市 / 建瓯市 / 小桥镇",
                "sortOrder": 10,
                "metadata": {
                    "codeSystem": "statistical-division",
                    "referenceYear": 2023,
                },
            },
            {
                "itemCode": "350783105206",
                "label": "上屯村",
                "parentCode": "350783105",
                "levelCode": "village",
                "fullName": "福建省 / 南平市 / 建瓯市 / 小桥镇 / 上屯村",
                "sortOrder": 10,
                "searchAliases": ["上屯村", "206"],
            },
        ],
    },
    {
        "typeCode": "forest-base-types",
        "name": "基地类型",
        "category": "forestry",
        "items": [
            {"itemCode": "self_operated", "label": "自营"},
            {"itemCode": "franchise", "label": "加盟"},
            {"itemCode": "cooperative", "label": "合作经营"},
            {"itemCode": "other", "label": "其他"},
        ],
    },
    {
        "typeCode": "forest-operation-types",
        "name": "经营类型",
        "category": "forestry",
        "items": [
            {"itemCode": "timber", "label": "竹材用林"},
            {"itemCode": "dual_regular", "label": "常规笋竹两用林"},
            {"itemCode": "dual_high_yield", "label": "高产笋竹两用林"},
            {"itemCode": "understory", "label": "林下经济"},
        ],
    },
    {
        "typeCode": "forest-types",
        "name": "竹种 / 林种",
        "category": "forestry",
        "items": [
            {"itemCode": "moso-bamboo", "label": "毛竹"},
            {"itemCode": "lei-bamboo", "label": "雷竹"},
            {"itemCode": "bitter-bamboo", "label": "苦竹"},
            {"itemCode": "mixed-bamboo", "label": "混生竹林"},
            {"itemCode": "other", "label": "其他"},
        ],
    },
    {
        "typeCode": "forest-resource-tags",
        "name": "林班资源标签",
        "category": "forestry",
        "items": [
            {"itemCode": "high-yield-demo", "label": "高产示范"},
            {"itemCode": "priority-management", "label": "重点管护"},
            {"itemCode": "carbon-potential", "label": "碳汇潜力"},
            {"itemCode": "pest-risk", "label": "病虫风险"},
            {"itemCode": "needs-review", "label": "待复核"},
        ],
    },
    {
        "typeCode": "quality-grades",
        "name": "质量等级",
        "category": "forestry",
        "items": [
            {"itemCode": "excellent", "label": "优"},
            {"itemCode": "good", "label": "良"},
            {"itemCode": "medium", "label": "中"},
            {"itemCode": "poor", "label": "差"},
        ],
    },
    {
        "typeCode": "risk-levels",
        "name": "风险等级",
        "category": "system",
        "items": [
            {"itemCode": "low", "label": "低"},
            {"itemCode": "medium", "label": "中"},
            {"itemCode": "high", "label": "高"},
            {"itemCode": "critical", "label": "严重"},
        ],
    },
    {
        "typeCode": "health-statuses",
        "name": "健康状态",
        "category": "forestry",
        "items": [
            {"itemCode": "healthy", "label": "健康"},
            {"itemCode": "patrolling", "label": "巡护中"},
            {"itemCode": "warning", "label": "预警"},
            {"itemCode": "remediating", "label": "治理中"},
        ],
    },
    {
        "typeCode": "ownership-types",
        "name": "权属性质",
        "category": "rights",
        "items": [
            {"itemCode": "state", "label": "国有"},
            {"itemCode": "collective", "label": "集体"},
            {"itemCode": "individual", "label": "个人"},
            {"itemCode": "enterprise", "label": "企业"},
            {"itemCode": "other", "label": "其他"},
        ],
    },
    {
        "typeCode": "certificate-types",
        "name": "林权证照类型",
        "category": "rights",
        "items": [
            {"itemCode": "forest-right-certificate", "label": "林权证"},
            {"itemCode": "real-estate-certificate", "label": "不动产权证"},
            {"itemCode": "contract", "label": "承包合同"},
            {"itemCode": "transfer-agreement", "label": "流转协议"},
            {"itemCode": "other", "label": "其他"},
        ],
    },
    {
        "typeCode": "right-types",
        "name": "林权权利类型",
        "category": "rights",
        "items": [
            {"itemCode": "forest-land-ownership", "label": "林地所有权"},
            {"itemCode": "forest-land-use-right", "label": "林地使用权"},
            {"itemCode": "forest-ownership", "label": "林木所有权"},
            {"itemCode": "contract-management-right", "label": "承包经营权"},
            {"itemCode": "management-right", "label": "经营权"},
        ],
    },
    {
        "typeCode": "archive-statuses",
        "name": "档案状态",
        "category": "rights",
        "items": [
            {"itemCode": "complete", "label": "完整"},
            {"itemCode": "partial", "label": "待补充"},
            {"itemCode": "missing", "label": "缺档"},
            {"itemCode": "review", "label": "复核中"},
            {"itemCode": "draft", "label": "草稿"},
            {"itemCode": "active", "label": "有效"},
            {"itemCode": "incomplete", "label": "待补全"},
            {"itemCode": "disputed", "label": "争议中"},
            {"itemCode": "expired", "label": "已到期"},
            {"itemCode": "archived", "label": "已归档"},
        ],
    },
    {
        "typeCode": "business-statuses",
        "name": "业务状态",
        "category": "business",
        "items": [
            {"itemCode": "draft", "label": "草稿"},
            {"itemCode": "pending", "label": "待处理"},
            {"itemCode": "active", "label": "进行中"},
            {"itemCode": "paused", "label": "已暂停"},
            {"itemCode": "completed", "label": "已完成"},
            {"itemCode": "archived", "label": "已归档"},
        ],
    },
    {
        "typeCode": "material-units",
        "name": "农资计量单位",
        "category": "materials",
        "items": [
            {"itemCode": "kg", "label": "千克"},
            {"itemCode": "ton", "label": "吨"},
            {"itemCode": "bag", "label": "袋"},
            {"itemCode": "bottle", "label": "瓶"},
            {"itemCode": "piece", "label": "件"},
            {"itemCode": "set", "label": "套"},
        ],
    },
]


def business_dictionary_seeds() -> list[dict[str, Any]]:
    from .business import BUSINESS_FIELD_SCHEMAS, BUSINESS_MODULES

    seeds: list[dict[str, Any]] = []
    for module_index, (module_key, fields) in enumerate(BUSINESS_FIELD_SCHEMAS.items()):
        module_title = str(BUSINESS_MODULES[module_key].get("title") or module_key).removesuffix("信息卡")
        for field_index, field in enumerate(fields):
            options = field.get("options") or []
            type_code = str(field.get("dictionaryCode") or "")
            if field.get("inputType") != "dictionary" or not type_code or not options:
                continue
            seeds.append(
                {
                    "typeCode": type_code,
                    "name": f"{module_title} · {field.get('label') or field.get('key')}",
                    "category": "business",
                    "description": f"{module_title}的{field.get('label') or field.get('key')}可选项",
                    "sortOrder": 1000 + module_index * 100 + field_index,
                    "items": [
                        {
                            "itemCode": str(option.get("value") or ""),
                            "label": str(option.get("label") or option.get("value") or ""),
                            "sortOrder": (option_index + 1) * 10,
                            "metadata": {
                                "moduleKey": module_key,
                                "fieldKey": str(field.get("key") or ""),
                            },
                        }
                        for option_index, option in enumerate(options)
                        if str(option.get("value") or "")
                    ],
                }
            )
    return seeds


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_text(value: Any) -> str:
    return str(value or "").strip()


def json_value(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def mysql_datetime(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def api_datetime(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


@lru_cache(maxsize=1)
def standard_administrative_division_seeds() -> list[dict[str, Any]]:
    payload_bytes = STANDARD_DIVISION_RESOURCE.read_bytes()
    digest = hashlib.sha256(payload_bytes).hexdigest()
    if digest != STANDARD_DIVISION_SHA256:
        raise RuntimeError("Administrative division snapshot checksum mismatch")
    payload = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("Administrative division snapshot must contain a list")

    records: list[dict[str, Any]] = []

    def normalized_code(raw_code: str, level_index: int) -> str:
        if level_index <= 1:
            return raw_code.ljust(6, "0")
        return raw_code

    def append_level(
        nodes: list[dict[str, Any]],
        level_index: int,
        parent_code: str = "",
        parent_names: tuple[str, ...] = (),
    ) -> None:
        level_code = STANDARD_DIVISION_LEVELS[level_index]
        for index, node in enumerate(nodes):
            raw_code = compact_text(node.get("code"))
            label = compact_text(node.get("name"))
            if not raw_code or not label:
                raise RuntimeError("Administrative division snapshot contains an invalid node")
            item_code = normalized_code(raw_code, level_index)
            full_names = (*parent_names, label)
            code_system = (
                "GB/T 2260-2007"
                if level_index <= 2
                else "GB/T 10114-2003 / statistical-division"
            )
            records.append(
                {
                    "id": str(
                        uuid.uuid5(
                            ADMIN_DIVISION_NAMESPACE,
                            f"{level_code}:{item_code}",
                        )
                    ),
                    "itemCode": item_code,
                    "label": label,
                    "parentCode": parent_code,
                    "levelCode": level_code,
                    "fullName": " / ".join(full_names),
                    "sortOrder": (index + 1) * 10,
                    "source": "national-standard-snapshot",
                    "searchAliases": list(dict.fromkeys([label, item_code, raw_code])),
                    "metadata": {
                        "codeSystem": code_system,
                        "referenceYear": 2023,
                        "datasetVersion": "2023-06-30",
                        "snapshotStatus": "historical-public-snapshot",
                        "officialRuleUrl": (
                            "https://www.stats.gov.cn/sj/tjbz/gjtjbz/"
                            "202302/t20230213_1902741.html"
                        ),
                        "officialSnapshotUrl": (
                            "https://www.stats.gov.cn/sj/tjbz/"
                            "tjyqhdmhcxhfdm/2023/index.html"
                        ),
                        "packagingSource": (
                            "https://github.com/modood/"
                            "Administrative-divisions-of-China/releases/tag/2.7.0"
                        ),
                        "resourceSha256": STANDARD_DIVISION_SHA256,
                    },
                }
            )
            children = node.get("children")
            if level_index < len(STANDARD_DIVISION_LEVELS) - 1 and isinstance(children, list):
                append_level(children, level_index + 1, item_code, full_names)

    append_level(payload, 0)
    for index, (item_code, label) in enumerate(STANDARD_DIVISION_SPECIAL_REGIONS):
        records.append(
            {
                "id": str(
                    uuid.uuid5(
                        ADMIN_DIVISION_NAMESPACE,
                        f"province:{item_code}",
                    )
                ),
                "itemCode": item_code,
                "label": label,
                "parentCode": "",
                "levelCode": "province",
                "fullName": label,
                "sortOrder": (len(payload) + index + 1) * 10,
                "source": "national-standard-snapshot",
                "searchAliases": [label, item_code],
                "metadata": {
                    "codeSystem": "GB/T 2260-2007",
                    "referenceYear": 2023,
                    "datasetVersion": "2023-06-30",
                    "snapshotStatus": "province-code-only",
                    "coverageNote": "Province-level code only; lower levels use separate systems.",
                    "resourceSha256": STANDARD_DIVISION_SHA256,
                },
            }
        )
    return records


def standard_division_seed_enabled() -> bool:
    value = os.getenv("SMART_BAMBOO_SEED_STANDARD_DIVISIONS", "1")
    return compact_text(value).lower() not in {"0", "false", "no", "off"}


def dictionary_item_identity(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        compact_text(item.get("dictionaryTypeId")),
        compact_text(item.get("levelCode")),
        compact_text(item.get("itemCode")),
    )


def parent_level_for(level_code: Any) -> str:
    return ADMIN_DIVISION_PARENT_LEVEL.get(compact_text(level_code), "")


def system_dictionary_seeds() -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for dictionary_seed in DEFAULT_DICTIONARIES:
        cloned = {key: value for key, value in dictionary_seed.items() if key != "items"}
        items = list(dictionary_seed.get("items") or [])
        if (
            cloned.get("typeCode") == "administrative-divisions"
            and standard_division_seed_enabled()
        ):
            standard_items = standard_administrative_division_seeds()
            items = [*standard_items, *items]
            cloned["properties"] = {
                **(cloned.get("properties") or {}),
                "referenceYear": 2023,
                "datasetVersion": "2023-06-30",
                "standardItemCount": len(standard_items),
                "coverage": "National province/city/county/town plus curated project villages",
                "snapshotStatus": "historical-public-snapshot",
                "resourceSha256": STANDARD_DIVISION_SHA256,
            }
        cloned["items"] = items
        seeds.append(cloned)
    return [*seeds, *business_dictionary_seeds()]


class DictionaryTypeIn(BaseModel):
    typeCode: str
    name: str
    category: str = "business"
    hierarchyEnabled: bool = False
    valueMode: str = "code"
    description: str = ""
    status: str = "active"
    sortOrder: int = 0
    systemDefined: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("typeCode")
    @classmethod
    def validate_type_code(cls, value: str) -> str:
        normalized = compact_text(value).lower()
        if not TYPE_CODE_PATTERN.fullmatch(normalized):
            raise ValueError("typeCode must use lower-case letters, numbers, and hyphens")
        return normalized

    @field_validator("name", "category", "valueMode", "status")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = compact_text(value)
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized


class DictionaryTypePatch(BaseModel):
    name: str | None = None
    category: str | None = None
    hierarchyEnabled: bool | None = None
    valueMode: str | None = None
    description: str | None = None
    status: str | None = None
    sortOrder: int | None = None
    properties: dict[str, Any] | None = None


class DictionaryItemIn(BaseModel):
    itemCode: str
    label: str
    parentCode: str = ""
    levelCode: str = ""
    fullName: str = ""
    pinyin: str = ""
    initials: str = ""
    searchAliases: list[str] = Field(default_factory=list)
    sortOrder: int = 0
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = "manual"

    @field_validator("itemCode")
    @classmethod
    def validate_item_code(cls, value: str) -> str:
        normalized = compact_text(value)
        if not ITEM_CODE_PATTERN.fullmatch(normalized):
            raise ValueError("itemCode contains unsupported characters")
        return normalized

    @field_validator("label", "status", "source")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = compact_text(value)
        if not normalized:
            raise ValueError("field cannot be empty")
        return normalized


class DictionaryItemPatch(BaseModel):
    label: str | None = None
    parentCode: str | None = None
    levelCode: str | None = None
    fullName: str | None = None
    pinyin: str | None = None
    initials: str | None = None
    searchAliases: list[str] | None = None
    sortOrder: int | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None
    source: str | None = None


def normalize_type(record: dict[str, Any]) -> dict[str, Any]:
    created_at = record.get("createdAt") or now_iso()
    return {
        "id": compact_text(record.get("id")) or str(uuid.uuid4()),
        "typeCode": compact_text(record.get("typeCode")).lower(),
        "name": compact_text(record.get("name")),
        "category": compact_text(record.get("category")) or "business",
        "hierarchyEnabled": bool(record.get("hierarchyEnabled")),
        "valueMode": compact_text(record.get("valueMode")) or "code",
        "description": compact_text(record.get("description")),
        "status": compact_text(record.get("status")) or "active",
        "sortOrder": int(record.get("sortOrder") or 0),
        "systemDefined": bool(record.get("systemDefined")),
        "properties": record.get("properties") if isinstance(record.get("properties"), dict) else {},
        "createdAt": api_datetime(created_at),
        "updatedAt": api_datetime(record.get("updatedAt") or created_at),
        "deletedAt": api_datetime(record.get("deletedAt")),
    }


def normalize_item(record: dict[str, Any]) -> dict[str, Any]:
    created_at = record.get("createdAt") or now_iso()
    aliases = record.get("searchAliases")
    if not isinstance(aliases, list):
        aliases = []
    return {
        "id": compact_text(record.get("id")) or str(uuid.uuid4()),
        "dictionaryTypeId": compact_text(record.get("dictionaryTypeId")),
        "typeCode": compact_text(record.get("typeCode")).lower(),
        "itemCode": compact_text(record.get("itemCode")),
        "label": compact_text(record.get("label")),
        "parentItemId": compact_text(record.get("parentItemId")),
        "parentCode": compact_text(record.get("parentCode")),
        "levelCode": compact_text(record.get("levelCode")),
        "fullName": compact_text(record.get("fullName")) or compact_text(record.get("label")),
        "pinyin": compact_text(record.get("pinyin")),
        "initials": compact_text(record.get("initials")),
        "searchAliases": [compact_text(item) for item in aliases if compact_text(item)],
        "sortOrder": int(record.get("sortOrder") or 0),
        "status": compact_text(record.get("status")) or "active",
        "metadata": record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
        "source": compact_text(record.get("source")) or "manual",
        "createdAt": api_datetime(created_at),
        "updatedAt": api_datetime(record.get("updatedAt") or created_at),
        "deletedAt": api_datetime(record.get("deletedAt")),
    }


def _mysql_types() -> list[dict[str, Any]]:
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, type_code, name, category, hierarchy_enabled, value_mode,
                       description, status, sort_order, system_defined, properties,
                       created_at, updated_at, deleted_at
                FROM dictionary_types
                """
            )
            rows = cur.fetchall()
    return [
        normalize_type(
            {
                "id": row[0],
                "typeCode": row[1],
                "name": row[2],
                "category": row[3],
                "hierarchyEnabled": row[4],
                "valueMode": row[5],
                "description": row[6],
                "status": row[7],
                "sortOrder": row[8],
                "systemDefined": row[9],
                "properties": json_value(row[10], {}),
                "createdAt": row[11],
                "updatedAt": row[12],
                "deletedAt": row[13],
            }
        )
        for row in rows
    ]


def _mysql_items() -> list[dict[str, Any]]:
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT di.id, di.dictionary_type_id, dt.type_code, di.item_code,
                       di.label, di.parent_item_id, parent.item_code, di.level_code,
                       di.full_name, di.pinyin, di.initials, di.search_aliases,
                       di.sort_order, di.status, di.metadata, di.source,
                       di.created_at, di.updated_at, di.deleted_at
                FROM dictionary_items di
                JOIN dictionary_types dt ON dt.id = di.dictionary_type_id
                LEFT JOIN dictionary_items parent ON parent.id = di.parent_item_id
                """
            )
            rows = cur.fetchall()
    return [
        normalize_item(
            {
                "id": row[0],
                "dictionaryTypeId": row[1],
                "typeCode": row[2],
                "itemCode": row[3],
                "label": row[4],
                "parentItemId": row[5],
                "parentCode": row[6],
                "levelCode": row[7],
                "fullName": row[8],
                "pinyin": row[9],
                "initials": row[10],
                "searchAliases": json_value(row[11], []),
                "sortOrder": row[12],
                "status": row[13],
                "metadata": json_value(row[14], {}),
                "source": row[15],
                "createdAt": row[16],
                "updatedAt": row[17],
                "deletedAt": row[18],
            }
        )
        for row in rows
    ]


def _postgis_records(table: str, columns: str) -> list[dict[str, Any]]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(database.get_settings().database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {columns} FROM {table}")
            return [dict(row) for row in cur.fetchall()]


def load_all_types() -> list[dict[str, Any]]:
    if use_mysql():
        return _mysql_types()
    if use_postgis():
        rows = _postgis_records(
            "dictionary_types",
            "id::text AS id, type_code, name, category, hierarchy_enabled, value_mode, "
            "description, status, sort_order, system_defined, properties, "
            "created_at, updated_at, deleted_at",
        )
        return [
            normalize_type(
                {
                    "id": row.get("id"),
                    "typeCode": row.get("type_code"),
                    "name": row.get("name"),
                    "category": row.get("category"),
                    "hierarchyEnabled": row.get("hierarchy_enabled"),
                    "valueMode": row.get("value_mode"),
                    "description": row.get("description"),
                    "status": row.get("status"),
                    "sortOrder": row.get("sort_order"),
                    "systemDefined": row.get("system_defined"),
                    "properties": row.get("properties"),
                    "createdAt": row.get("created_at"),
                    "updatedAt": row.get("updated_at"),
                    "deletedAt": row.get("deleted_at"),
                }
            )
            for row in rows
        ]
    return [normalize_type(record) for record in load_json_records(dictionary_types_json_path())]


def load_all_items() -> list[dict[str, Any]]:
    if use_mysql():
        return _mysql_items()
    if use_postgis():
        rows = _postgis_records(
            "dictionary_items di JOIN dictionary_types dt ON dt.id = di.dictionary_type_id "
            "LEFT JOIN dictionary_items parent ON parent.id = di.parent_item_id",
            "di.id::text AS id, di.dictionary_type_id::text AS dictionary_type_id, "
            "dt.type_code, di.item_code, di.label, "
            "COALESCE(di.parent_item_id::text, '') AS parent_item_id, "
            "COALESCE(parent.item_code, '') AS parent_code, di.level_code, "
            "di.full_name, di.pinyin, di.initials, di.search_aliases, di.sort_order, "
            "di.status, di.metadata, di.source, di.created_at, di.updated_at, di.deleted_at",
        )
        return [
            normalize_item(
                {
                    "id": row.get("id"),
                    "dictionaryTypeId": row.get("dictionary_type_id"),
                    "typeCode": row.get("type_code"),
                    "itemCode": row.get("item_code"),
                    "label": row.get("label"),
                    "parentItemId": row.get("parent_item_id"),
                    "parentCode": row.get("parent_code"),
                    "levelCode": row.get("level_code"),
                    "fullName": row.get("full_name"),
                    "pinyin": row.get("pinyin"),
                    "initials": row.get("initials"),
                    "searchAliases": row.get("search_aliases"),
                    "sortOrder": row.get("sort_order"),
                    "status": row.get("status"),
                    "metadata": row.get("metadata"),
                    "source": row.get("source"),
                    "createdAt": row.get("created_at"),
                    "updatedAt": row.get("updated_at"),
                    "deletedAt": row.get("deleted_at"),
                }
            )
            for row in rows
        ]
    return [normalize_item(record) for record in load_json_records(dictionary_items_json_path())]


def _save_type_record(record: dict[str, Any]) -> None:
    normalized = normalize_type(record)
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dictionary_types (
                        id, type_code, name, category, hierarchy_enabled, value_mode,
                        description, status, sort_order, system_defined, properties,
                        created_at, updated_at, deleted_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name),
                        category = VALUES(category),
                        hierarchy_enabled = VALUES(hierarchy_enabled),
                        value_mode = VALUES(value_mode),
                        description = VALUES(description),
                        status = VALUES(status),
                        sort_order = VALUES(sort_order),
                        system_defined = VALUES(system_defined),
                        properties = VALUES(properties),
                        updated_at = VALUES(updated_at),
                        deleted_at = VALUES(deleted_at)
                    """,
                    (
                        normalized["id"],
                        normalized["typeCode"],
                        normalized["name"],
                        normalized["category"],
                        normalized["hierarchyEnabled"],
                        normalized["valueMode"],
                        normalized["description"],
                        normalized["status"],
                        normalized["sortOrder"],
                        normalized["systemDefined"],
                        json.dumps(normalized["properties"], ensure_ascii=False),
                        mysql_datetime(normalized["createdAt"]),
                        mysql_datetime(normalized["updatedAt"]),
                        mysql_datetime(normalized["deletedAt"]),
                    ),
                )
            conn.commit()
        return
    if use_postgis():
        import psycopg

        with psycopg.connect(database.get_settings().database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dictionary_types (
                        id, type_code, name, category, hierarchy_enabled, value_mode,
                        description, status, sort_order, system_defined, properties,
                        created_at, updated_at, deleted_at
                    ) VALUES (
                        %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                        %s::timestamptz, %s::timestamptz, %s::timestamptz
                    )
                    ON CONFLICT (type_code) DO UPDATE SET
                        name = EXCLUDED.name,
                        category = EXCLUDED.category,
                        hierarchy_enabled = EXCLUDED.hierarchy_enabled,
                        value_mode = EXCLUDED.value_mode,
                        description = EXCLUDED.description,
                        status = EXCLUDED.status,
                        sort_order = EXCLUDED.sort_order,
                        system_defined = EXCLUDED.system_defined,
                        properties = EXCLUDED.properties,
                        updated_at = EXCLUDED.updated_at,
                        deleted_at = EXCLUDED.deleted_at
                    """,
                    (
                        normalized["id"],
                        normalized["typeCode"],
                        normalized["name"],
                        normalized["category"],
                        normalized["hierarchyEnabled"],
                        normalized["valueMode"],
                        normalized["description"],
                        normalized["status"],
                        normalized["sortOrder"],
                        normalized["systemDefined"],
                        json.dumps(normalized["properties"], ensure_ascii=False),
                        normalized["createdAt"],
                        normalized["updatedAt"],
                        normalized["deletedAt"],
                    ),
                )
            conn.commit()
        return
    records = load_all_types()
    for index, current in enumerate(records):
        if current["id"] == normalized["id"] or current["typeCode"] == normalized["typeCode"]:
            records[index] = normalized
            break
    else:
        records.append(normalized)
    save_json_records(dictionary_types_json_path(), records)


def _save_item_record(record: dict[str, Any]) -> None:
    normalized = normalize_item(record)
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dictionary_items (
                        id, dictionary_type_id, item_code, label, parent_item_id,
                        level_code, full_name, pinyin, initials, search_aliases,
                        sort_order, status, metadata, source, created_at, updated_at, deleted_at
                    ) VALUES (
                        %s, %s, %s, %s, NULLIF(%s, ''), %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    ON DUPLICATE KEY UPDATE
                        label = VALUES(label),
                        parent_item_id = VALUES(parent_item_id),
                        level_code = VALUES(level_code),
                        full_name = VALUES(full_name),
                        pinyin = VALUES(pinyin),
                        initials = VALUES(initials),
                        search_aliases = VALUES(search_aliases),
                        sort_order = VALUES(sort_order),
                        status = VALUES(status),
                        metadata = VALUES(metadata),
                        source = VALUES(source),
                        updated_at = VALUES(updated_at),
                        deleted_at = VALUES(deleted_at)
                    """,
                    (
                        normalized["id"],
                        normalized["dictionaryTypeId"],
                        normalized["itemCode"],
                        normalized["label"],
                        normalized["parentItemId"],
                        normalized["levelCode"],
                        normalized["fullName"],
                        normalized["pinyin"],
                        normalized["initials"],
                        json.dumps(normalized["searchAliases"], ensure_ascii=False),
                        normalized["sortOrder"],
                        normalized["status"],
                        json.dumps(normalized["metadata"], ensure_ascii=False),
                        normalized["source"],
                        mysql_datetime(normalized["createdAt"]),
                        mysql_datetime(normalized["updatedAt"]),
                        mysql_datetime(normalized["deletedAt"]),
                    ),
                )
            conn.commit()
        return
    if use_postgis():
        import psycopg

        with psycopg.connect(database.get_settings().database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dictionary_items (
                        id, dictionary_type_id, item_code, label, parent_item_id,
                        level_code, full_name, pinyin, initials, search_aliases,
                        sort_order, status, metadata, source, created_at, updated_at, deleted_at
                    ) VALUES (
                        %s::uuid, %s::uuid, %s, %s, NULLIF(%s, '')::uuid,
                        %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s,
                        %s::timestamptz, %s::timestamptz, %s::timestamptz
                    )
                    ON CONFLICT (dictionary_type_id, level_code, item_code) DO UPDATE SET
                        label = EXCLUDED.label,
                        parent_item_id = EXCLUDED.parent_item_id,
                        level_code = EXCLUDED.level_code,
                        full_name = EXCLUDED.full_name,
                        pinyin = EXCLUDED.pinyin,
                        initials = EXCLUDED.initials,
                        search_aliases = EXCLUDED.search_aliases,
                        sort_order = EXCLUDED.sort_order,
                        status = EXCLUDED.status,
                        metadata = EXCLUDED.metadata,
                        source = EXCLUDED.source,
                        updated_at = EXCLUDED.updated_at,
                        deleted_at = EXCLUDED.deleted_at
                    """,
                    (
                        normalized["id"],
                        normalized["dictionaryTypeId"],
                        normalized["itemCode"],
                        normalized["label"],
                        normalized["parentItemId"],
                        normalized["levelCode"],
                        normalized["fullName"],
                        normalized["pinyin"],
                        normalized["initials"],
                        json.dumps(normalized["searchAliases"], ensure_ascii=False),
                        normalized["sortOrder"],
                        normalized["status"],
                        json.dumps(normalized["metadata"], ensure_ascii=False),
                        normalized["source"],
                        normalized["createdAt"],
                        normalized["updatedAt"],
                        normalized["deletedAt"],
                    ),
                )
            conn.commit()
        return
    records = load_all_items()
    for index, current in enumerate(records):
        if current["id"] == normalized["id"] or (
            current["dictionaryTypeId"] == normalized["dictionaryTypeId"]
            and current["levelCode"] == normalized["levelCode"]
            and current["itemCode"] == normalized["itemCode"]
        ):
            records[index] = normalized
            break
    else:
        records.append(normalized)
    save_json_records(dictionary_items_json_path(), records)


def _save_item_records(records: list[dict[str, Any]]) -> None:
    normalized_records = [normalize_item(record) for record in records]
    if not normalized_records:
        return
    if use_mysql():
        sql = """
            INSERT INTO dictionary_items (
                id, dictionary_type_id, item_code, label, parent_item_id,
                level_code, full_name, pinyin, initials, search_aliases,
                sort_order, status, metadata, source, created_at, updated_at, deleted_at
            ) VALUES (
                %s, %s, %s, %s, NULLIF(%s, ''), %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                label = VALUES(label),
                parent_item_id = VALUES(parent_item_id),
                level_code = VALUES(level_code),
                full_name = VALUES(full_name),
                pinyin = VALUES(pinyin),
                initials = VALUES(initials),
                search_aliases = VALUES(search_aliases),
                sort_order = VALUES(sort_order),
                status = VALUES(status),
                metadata = VALUES(metadata),
                source = VALUES(source),
                updated_at = VALUES(updated_at),
                deleted_at = VALUES(deleted_at)
        """
        values = [
            (
                item["id"],
                item["dictionaryTypeId"],
                item["itemCode"],
                item["label"],
                item["parentItemId"],
                item["levelCode"],
                item["fullName"],
                item["pinyin"],
                item["initials"],
                json.dumps(item["searchAliases"], ensure_ascii=False),
                item["sortOrder"],
                item["status"],
                json.dumps(item["metadata"], ensure_ascii=False),
                item["source"],
                mysql_datetime(item["createdAt"]),
                mysql_datetime(item["updatedAt"]),
                mysql_datetime(item["deletedAt"]),
            )
            for item in normalized_records
        ]
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                for start in range(0, len(values), 1000):
                    cur.executemany(sql, values[start : start + 1000])
            conn.commit()
        return
    if use_postgis():
        import psycopg

        sql = """
            INSERT INTO dictionary_items (
                id, dictionary_type_id, item_code, label, parent_item_id,
                level_code, full_name, pinyin, initials, search_aliases,
                sort_order, status, metadata, source, created_at, updated_at, deleted_at
            ) VALUES (
                %s::uuid, %s::uuid, %s, %s, NULLIF(%s, '')::uuid,
                %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s,
                %s::timestamptz, %s::timestamptz, %s::timestamptz
            )
            ON CONFLICT (dictionary_type_id, level_code, item_code) DO UPDATE SET
                label = EXCLUDED.label,
                parent_item_id = EXCLUDED.parent_item_id,
                level_code = EXCLUDED.level_code,
                full_name = EXCLUDED.full_name,
                pinyin = EXCLUDED.pinyin,
                initials = EXCLUDED.initials,
                search_aliases = EXCLUDED.search_aliases,
                sort_order = EXCLUDED.sort_order,
                status = EXCLUDED.status,
                metadata = EXCLUDED.metadata,
                source = EXCLUDED.source,
                updated_at = EXCLUDED.updated_at,
                deleted_at = EXCLUDED.deleted_at
        """
        values = [
            (
                item["id"],
                item["dictionaryTypeId"],
                item["itemCode"],
                item["label"],
                item["parentItemId"],
                item["levelCode"],
                item["fullName"],
                item["pinyin"],
                item["initials"],
                json.dumps(item["searchAliases"], ensure_ascii=False),
                item["sortOrder"],
                item["status"],
                json.dumps(item["metadata"], ensure_ascii=False),
                item["source"],
                item["createdAt"],
                item["updatedAt"],
                item["deletedAt"],
            )
            for item in normalized_records
        ]
        with psycopg.connect(database.get_settings().database_url) as conn:
            with conn.cursor() as cur:
                for start in range(0, len(values), 1000):
                    cur.executemany(sql, values[start : start + 1000])
            conn.commit()
        return

    existing = load_all_items()
    by_id = {item["id"]: index for index, item in enumerate(existing)}
    by_identity = {
        dictionary_item_identity(item): index
        for index, item in enumerate(existing)
    }
    for item in normalized_records:
        index = by_id.get(item["id"])
        if index is None:
            index = by_identity.get(dictionary_item_identity(item))
        if index is None:
            index = len(existing)
            existing.append(item)
        else:
            existing[index] = item
        by_id[item["id"]] = index
        by_identity[dictionary_item_identity(item)] = index
    save_json_records(dictionary_items_json_path(), existing)


def type_by_code(type_code: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    normalized = compact_text(type_code).lower()
    return next(
        (
            item
            for item in load_all_types()
            if item["typeCode"] == normalized and (include_deleted or not item["deletedAt"])
        ),
        None,
    )


def type_by_id(dictionary_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in load_all_types()
            if item["id"] == str(dictionary_id) and (include_deleted or not item["deletedAt"])
        ),
        None,
    )


def item_by_code(
    dictionary_type_id: str,
    item_code: str,
    *,
    level_code: str = "",
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    normalized_level = compact_text(level_code)
    return next(
        (
            item
            for item in load_all_items()
            if item["dictionaryTypeId"] == dictionary_type_id
            and item["itemCode"] == compact_text(item_code)
            and (not normalized_level or item["levelCode"] == normalized_level)
            and (include_deleted or not item["deletedAt"])
        ),
        None,
    )


def item_by_id(item_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in load_all_items()
            if item["id"] == str(item_id) and (include_deleted or not item["deletedAt"])
        ),
        None,
    )


def ensure_system_dictionaries() -> None:
    seeds = system_dictionary_seeds()
    existing_types = load_all_types()
    existing_items = load_all_items()
    types_by_code = {item["typeCode"]: item for item in existing_types}
    items_by_identity = {
        dictionary_item_identity(item): item
        for item in existing_items
    }
    items_by_code: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in existing_items:
        items_by_code.setdefault(
            (item["dictionaryTypeId"], item["itemCode"]),
            [],
        ).append(item)
    pending_types: list[dict[str, Any]] = []
    pending_items: list[dict[str, Any]] = []

    for dictionary_seed in seeds:
        seed = {key: value for key, value in dictionary_seed.items() if key != "items"}
        dictionary_type = types_by_code.get(seed["typeCode"])
        if dictionary_type is None:
            dictionary_type = normalize_type(
                {
                    **seed,
                    "status": "active",
                    "systemDefined": True,
                    "properties": {"source": "system-seed"},
                }
            )
            pending_types.append(dictionary_type)
            types_by_code[dictionary_type["typeCode"]] = dictionary_type
        for index, item_seed in enumerate(dictionary_seed.get("items") or []):
            level_code = compact_text(item_seed.get("levelCode"))
            identity = (dictionary_type["id"], level_code, item_seed["itemCode"])
            if identity in items_by_identity:
                continue
            parent_code = compact_text(item_seed.get("parentCode"))
            parent_level = parent_level_for(level_code)
            parent = None
            if parent_code and parent_level:
                parent = items_by_identity.get(
                    (dictionary_type["id"], parent_level, parent_code)
                )
            if parent_code and parent is None:
                candidates = items_by_code.get((dictionary_type["id"], parent_code), [])
                parent = candidates[0] if candidates else None
            item = normalize_item(
                {
                    **item_seed,
                    "dictionaryTypeId": dictionary_type["id"],
                    "typeCode": dictionary_type["typeCode"],
                    "parentItemId": parent["id"] if parent else "",
                    "parentCode": parent_code,
                    "status": "active",
                    "sortOrder": item_seed.get("sortOrder", (index + 1) * 10),
                    "source": item_seed.get("source") or "seed",
                    "searchAliases": item_seed.get("searchAliases") or [item_seed["label"]],
                    "metadata": {
                        **(item_seed.get("metadata") or {}),
                        "systemDefined": True,
                    },
                }
            )
            pending_items.append(item)
            items_by_identity[identity] = item
            items_by_code.setdefault(
                (dictionary_type["id"], item["itemCode"]),
                [],
            ).append(item)

    if use_mysql() or use_postgis():
        for dictionary_type in pending_types:
            _save_type_record(dictionary_type)
        _save_item_records(pending_items)
    else:
        if pending_types:
            save_json_records(
                dictionary_types_json_path(),
                [*existing_types, *pending_types],
            )
        if pending_items:
            _save_item_records(pending_items)
    sync_administrative_divisions_from_blocks()


def sync_administrative_divisions_from_blocks(
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    if blocks is None:
        from .forest_blocks import load_all_blocks

        blocks = load_all_blocks()

    dictionary_type = type_by_code("administrative-divisions", include_deleted=True)
    if dictionary_type is None:
        return {"created": 0, "updated": 0, "examined": 0}

    existing = {
        (item["levelCode"], item["itemCode"]): item
        for item in _dictionary_items(dictionary_type["id"], include_deleted=True)
    }
    created = 0
    updated = 0
    examined = 0
    for block in blocks:
        if block.get("deletedAt"):
            continue
        county_code = compact_text(block.get("countyCode"))
        town_code = compact_text(block.get("townCode"))
        village_code = compact_text(block.get("villageCode"))
        hierarchy = [
            {
                "itemCode": county_code,
                "label": compact_text(block.get("countyName")),
                "parentCode": f"{county_code[:4]}00" if len(county_code) >= 4 else "",
                "levelCode": "county",
            },
            {
                "itemCode": town_code,
                "label": compact_text(block.get("townName")),
                "parentCode": county_code,
                "levelCode": "town",
            },
            {
                "itemCode": village_code,
                "label": compact_text(block.get("villageName")),
                "parentCode": town_code,
                "levelCode": "village",
            },
        ]
        for entry in hierarchy:
            if not entry["itemCode"] or not entry["label"]:
                continue
            examined += 1
            parent = existing.get(
                (parent_level_for(entry["levelCode"]), entry["parentCode"])
            )
            parent_full_name = compact_text(parent.get("fullName")) if parent else ""
            identity = (entry["levelCode"], entry["itemCode"])
            current = existing.get(identity)
            if current is not None:
                metadata = current.get("metadata") if isinstance(current.get("metadata"), dict) else {}
                if (
                    current.get("deletedAt")
                    or current.get("source") != "forest-block-sync"
                    or metadata.get("curated") is True
                ):
                    continue
                refreshed = normalize_item(
                    {
                        **current,
                        **entry,
                        "parentItemId": parent["id"] if parent else "",
                        "fullName": " / ".join(
                            value for value in [parent_full_name, entry["label"]] if value
                        ),
                        "searchAliases": [entry["label"], entry["itemCode"]],
                        "updatedAt": now_iso(),
                    }
                )
                compared_fields = (
                    "label",
                    "parentItemId",
                    "parentCode",
                    "levelCode",
                    "fullName",
                    "searchAliases",
                )
                if any(current.get(key) != refreshed.get(key) for key in compared_fields):
                    _save_item_record(refreshed)
                    existing[identity] = refreshed
                    updated += 1
                continue
            item = normalize_item(
                {
                    **entry,
                    "dictionaryTypeId": dictionary_type["id"],
                    "typeCode": dictionary_type["typeCode"],
                    "parentItemId": parent["id"] if parent else "",
                    "fullName": " / ".join(
                        value for value in [parent_full_name, entry["label"]] if value
                    ),
                    "status": "active",
                    "sortOrder": 1000 + created,
                    "source": "forest-block-sync",
                    "searchAliases": [entry["label"], entry["itemCode"]],
                    "metadata": {
                        "derivedFrom": "forest-blocks",
                        "curated": False,
                    },
                }
            )
            _save_item_record(item)
            existing[identity] = item
            created += 1
    return {"created": created, "updated": updated, "examined": examined}


def _require_dictionary(type_code: str, *, include_deleted: bool = False) -> dict[str, Any]:
    dictionary_type = type_by_code(type_code, include_deleted=include_deleted)
    if dictionary_type is None:
        raise HTTPException(status_code=404, detail="Dictionary not found")
    return dictionary_type


def _dictionary_items(dictionary_type_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
    return [
        item
        for item in load_all_items()
        if item["dictionaryTypeId"] == dictionary_type_id
        and (include_deleted or not item["deletedAt"])
    ]


def _item_search_text(item: dict[str, Any]) -> str:
    return " ".join(
        [
            compact_text(item.get("itemCode")),
            compact_text(item.get("label")),
            compact_text(item.get("fullName")),
            compact_text(item.get("pinyin")),
            compact_text(item.get("initials")),
            " ".join(str(value) for value in item.get("searchAliases") or []),
        ]
    ).lower()


@router.get("/dictionaries")
def list_dictionaries(
    q: str = Query(default=""),
    category: str = Query(default=""),
    status: str = Query(default=""),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.view")
    if includeDeleted:
        require_permission(context, "system.dictionaries.restore")
    query = compact_text(q).lower()
    all_items = load_all_items()
    records = [
        item
        for item in load_all_types()
        if (includeDeleted or not item["deletedAt"])
        and (not category or item["category"] == category)
        and (not status or item["status"] == status)
        and (
            not query
            or query
            in " ".join(
                [
                    item["typeCode"],
                    item["name"],
                    item["category"],
                    item["description"],
                ]
            ).lower()
        )
    ]
    for record in records:
        dictionary_items = [
            item
            for item in all_items
            if item["dictionaryTypeId"] == record["id"] and not item["deletedAt"]
        ]
        record["itemCount"] = len(dictionary_items)
        record["activeItemCount"] = sum(
            1 for item in dictionary_items if item["status"] == "active"
        )
    records.sort(key=lambda item: (item["sortOrder"], item["name"], item["typeCode"]))
    return {
        "items": records[offset : offset + limit],
        "total": len(records),
        "limit": limit,
        "offset": offset,
    }


@router.post("/dictionaries")
def create_dictionary(
    payload: DictionaryTypeIn,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.create")
    if type_by_code(payload.typeCode, include_deleted=True):
        raise HTTPException(status_code=409, detail="typeCode already exists")
    record = normalize_type(payload.model_dump())
    _save_type_record(record)
    return record


@router.get("/dictionaries/{type_code}/items")
def list_dictionary_items(
    type_code: str,
    q: str = Query(default=""),
    parentCode: str | None = Query(default=None),
    level: str = Query(default=""),
    status: str = Query(default=""),
    includeDeleted: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.view")
    if includeDeleted:
        require_permission(context, "system.dictionaries.restore")
    dictionary_type = _require_dictionary(type_code, include_deleted=includeDeleted)
    query = compact_text(q).lower()
    records = [
        item
        for item in _dictionary_items(dictionary_type["id"], include_deleted=includeDeleted)
        if (parentCode is None or item["parentCode"] == compact_text(parentCode))
        and (not level or item["levelCode"] == level)
        and (not status or item["status"] == status)
        and (not query or query in _item_search_text(item))
    ]
    records.sort(key=lambda item: (item["sortOrder"], item["label"], item["itemCode"]))
    return {
        "items": records[offset : offset + limit],
        "total": len(records),
        "limit": limit,
        "offset": offset,
    }


@router.post("/dictionaries/{type_code}/items")
def create_dictionary_item(
    type_code: str,
    payload: DictionaryItemIn,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.create")
    dictionary_type = _require_dictionary(type_code)
    if item_by_code(
        dictionary_type["id"],
        payload.itemCode,
        level_code=payload.levelCode,
        include_deleted=True,
    ):
        raise HTTPException(status_code=409, detail="itemCode already exists")
    parent_code = compact_text(payload.parentCode)
    parent = (
        item_by_code(
            dictionary_type["id"],
            parent_code,
            level_code=parent_level_for(payload.levelCode),
        )
        if parent_code
        else None
    )
    if parent_code and parent is None:
        raise HTTPException(status_code=422, detail="parentCode does not exist")
    record = normalize_item(
        {
            **payload.model_dump(),
            "dictionaryTypeId": dictionary_type["id"],
            "typeCode": dictionary_type["typeCode"],
            "parentItemId": parent["id"] if parent else "",
            "parentCode": parent_code,
        }
    )
    _save_item_record(record)
    return record


@router.patch("/dictionaries/{type_code}/items/{item_id}")
def patch_dictionary_item(
    type_code: str,
    item_id: str,
    payload: DictionaryItemPatch,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.update")
    dictionary_type = _require_dictionary(type_code)
    item = item_by_id(item_id)
    if item is None or item["dictionaryTypeId"] != dictionary_type["id"]:
        raise HTTPException(status_code=404, detail="Dictionary item not found")
    changes = payload.model_dump(exclude_unset=True)
    if "parentCode" in changes or "levelCode" in changes:
        parent_code = compact_text(changes.get("parentCode", item["parentCode"]))
        target_level = compact_text(changes.get("levelCode", item["levelCode"]))
        parent = (
            item_by_code(
                dictionary_type["id"],
                parent_code,
                level_code=parent_level_for(target_level),
            )
            if parent_code
            else None
        )
        if parent_code and parent is None:
            raise HTTPException(status_code=422, detail="parentCode does not exist")
        if parent and parent["id"] == item["id"]:
            raise HTTPException(status_code=422, detail="Dictionary item cannot be its own parent")
        changes["parentCode"] = parent_code
        changes["parentItemId"] = parent["id"] if parent else ""
    if item.get("source") == "forest-block-sync":
        metadata_changes = changes.get("metadata") if isinstance(changes.get("metadata"), dict) else {}
        changes["metadata"] = {
            **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
            **metadata_changes,
            "curated": True,
        }
    updated = normalize_item({**item, **changes, "updatedAt": now_iso()})
    _save_item_record(updated)
    return updated


@router.delete("/dictionaries/{type_code}/items/{item_id}")
def delete_dictionary_item(
    type_code: str,
    item_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.delete")
    dictionary_type = _require_dictionary(type_code)
    item = item_by_id(item_id)
    if item is None or item["dictionaryTypeId"] != dictionary_type["id"]:
        raise HTTPException(status_code=404, detail="Dictionary item not found")
    deleted_at = now_iso()
    _save_item_record({**item, "deletedAt": deleted_at, "updatedAt": deleted_at})
    return {"ok": True, "deleted": item_id}


@router.post("/dictionaries/{type_code}/items/{item_id}/restore")
def restore_dictionary_item(
    type_code: str,
    item_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.restore")
    dictionary_type = _require_dictionary(type_code, include_deleted=True)
    item = item_by_id(item_id, include_deleted=True)
    if item is None or item["dictionaryTypeId"] != dictionary_type["id"]:
        raise HTTPException(status_code=404, detail="Dictionary item not found")
    if not item["deletedAt"]:
        raise HTTPException(status_code=409, detail="Dictionary item is not deleted")
    updated = normalize_item({**item, "deletedAt": None, "updatedAt": now_iso()})
    _save_item_record(updated)
    return {"ok": True, "restored": item_id, "item": updated}


@router.get("/dictionary-options/{type_code}")
def dictionary_options(
    type_code: str,
    q: str = Query(default=""),
    parentCode: str | None = Query(default=None),
    level: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    _ = context
    dictionary_type = _require_dictionary(type_code)
    query = compact_text(q).lower()
    records = [
        item
        for item in _dictionary_items(dictionary_type["id"])
        if item["status"] == "active"
        and (parentCode is None or item["parentCode"] == compact_text(parentCode))
        and (not level or item["levelCode"] == level)
        and (not query or query in _item_search_text(item))
    ]
    records.sort(key=lambda item: (item["sortOrder"], item["label"], item["itemCode"]))
    options = [
        {
            "value": item["itemCode"],
            "label": item["label"],
            "parentCode": item["parentCode"],
            "levelCode": item["levelCode"],
            "fullName": item["fullName"],
            "disabled": item["status"] != "active",
            "metadata": item["metadata"],
        }
        for item in records
    ]
    return {
        "items": options[offset : offset + limit],
        "total": len(options),
        "limit": limit,
        "offset": offset,
    }


@router.get("/dictionaries/{dictionary_id}")
def get_dictionary(
    dictionary_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.view")
    record = type_by_id(dictionary_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dictionary not found")
    return record


@router.patch("/dictionaries/{dictionary_id}")
def patch_dictionary(
    dictionary_id: str,
    payload: DictionaryTypePatch,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.update")
    record = type_by_id(dictionary_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dictionary not found")
    updated = normalize_type(
        {
            **record,
            **payload.model_dump(exclude_unset=True),
            "updatedAt": now_iso(),
        }
    )
    _save_type_record(updated)
    return updated


@router.delete("/dictionaries/{dictionary_id}")
def delete_dictionary(
    dictionary_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.delete")
    record = type_by_id(dictionary_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dictionary not found")
    deleted_at = now_iso()
    _save_type_record({**record, "deletedAt": deleted_at, "updatedAt": deleted_at})
    return {"ok": True, "deleted": dictionary_id}


@router.post("/dictionaries/{dictionary_id}/restore")
def restore_dictionary(
    dictionary_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "system.dictionaries.restore")
    record = type_by_id(dictionary_id, include_deleted=True)
    if record is None:
        raise HTTPException(status_code=404, detail="Dictionary not found")
    if not record["deletedAt"]:
        raise HTTPException(status_code=409, detail="Dictionary is not deleted")
    updated = normalize_type({**record, "deletedAt": None, "updatedAt": now_iso()})
    _save_type_record(updated)
    return {"ok": True, "restored": dictionary_id, "item": updated}
