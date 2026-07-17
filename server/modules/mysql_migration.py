from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


MIGRATION_DATASET_KEYS = (
    "forestBlocks",
    "forestBlockVersions",
    "forestRights",
    "forestRightVersions",
    "forestSceneLinks",
    "mapLayers",
    "adminRoles",
    "adminUsers",
    "importBatches",
    "imageryScenes",
    "imageryTasks",
)


def load_json_list(path: Path, wrapper_key: str = "") -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read migration source {path}: {exc}") from exc
    if wrapper_key:
        if not isinstance(payload, dict) or wrapper_key not in payload:
            raise ValueError(
                f"Invalid migration source {path}: expected object key {wrapper_key!r}"
            )
        payload = payload[wrapper_key]
    if not isinstance(payload, list):
        raise ValueError(f"Invalid migration source {path}: expected a JSON list")
    invalid_indexes = [index for index, item in enumerate(payload) if not isinstance(item, dict)]
    if invalid_indexes:
        raise ValueError(
            f"Invalid migration source {path}: records at indexes "
            f"{invalid_indexes[:10]} are not JSON objects"
        )
    return payload


def migration_sources(data_dir: Path) -> dict[str, Any]:
    business_dir = data_dir / "business"
    business_modules = {
        path.stem: load_json_list(path)
        for path in sorted(business_dir.glob("*.json"))
        if path.is_file()
    } if business_dir.exists() else {}
    return {
        "forestBlocks": load_json_list(data_dir / "forest-blocks" / "forest_blocks.json"),
        "forestBlockVersions": load_json_list(data_dir / "forest-blocks" / "forest_block_versions.json"),
        "forestSceneLinks": load_json_list(data_dir / "forest-blocks" / "forest_block_scene_links.json"),
        "forestRights": load_json_list(data_dir / "forest-rights" / "forest_rights.json"),
        "forestRightVersions": load_json_list(data_dir / "forest-rights" / "forest_right_versions.json"),
        "mapLayers": load_json_list(data_dir / "map-layers" / "map_layers.json"),
        "adminRoles": load_json_list(data_dir / "admin" / "roles.json"),
        "adminUsers": load_json_list(data_dir / "admin" / "users.json"),
        "importBatches": load_json_list(data_dir / "imports" / "import_batches.json"),
        "imageryScenes": load_json_list(data_dir / "catalog.json", "scenes"),
        "imageryTasks": load_json_list(data_dir / "tasks.json", "tasks"),
        "businessModules": business_modules,
    }


def collect_json_migration_inventory(data_dir: Path) -> dict[str, Any]:
    sources = migration_sources(Path(data_dir))
    business_counts = {
        module_key: len(records)
        for module_key, records in sources["businessModules"].items()
    }
    inventory = {
        key: len(value)
        for key, value in sources.items()
        if key != "businessModules"
    }
    total_records = sum(inventory.values()) + sum(business_counts.values())
    inventory["businessModules"] = business_counts
    inventory["totalRecords"] = total_records
    return inventory


def collect_mysql_migration_inventory(
    *,
    platform_database_url: str | None = None,
    catalog_database_url: str | None = None,
) -> dict[str, Any]:
    from .database import mysql_connect

    inventory: dict[str, Any] = {key: 0 for key in MIGRATION_DATASET_KEYS}
    business_counts: dict[str, int] = {}
    platform_sql = """
        SELECT 'forestBlocks' AS dataset_key, '' AS module_key, COUNT(*) AS record_count FROM forest_blocks
        UNION ALL SELECT 'forestBlockVersions', '', COUNT(*) FROM forest_block_versions
        UNION ALL SELECT 'forestRights', '', COUNT(*) FROM forest_rights
        UNION ALL SELECT 'forestRightVersions', '', COUNT(*) FROM forest_right_versions
        UNION ALL SELECT 'forestSceneLinks', '', COUNT(*) FROM forest_block_scene_links
        UNION ALL SELECT 'mapLayers', '', COUNT(*) FROM map_layers
        UNION ALL SELECT 'adminRoles', '', COUNT(*) FROM admin_roles
        UNION ALL SELECT 'adminUsers', '', COUNT(*) FROM admin_users
        UNION ALL SELECT 'importBatches', '', COUNT(*) FROM import_batches
        UNION ALL SELECT 'businessModules', module_key, COUNT(*)
        FROM business_records GROUP BY module_key
    """
    catalog_sql = """
        SELECT 'imageryScenes' AS dataset_key, '' AS module_key, COUNT(*) AS record_count
        FROM remote_sensing_scenes
        UNION ALL SELECT 'imageryTasks', '', COUNT(*) FROM remote_sensing_tasks
    """

    def merge_rows(rows: Any) -> None:
        for row in rows:
            if hasattr(row, "get"):
                dataset_key = str(row.get("dataset_key") or "")
                module_key = str(row.get("module_key") or "")
                record_count = int(row.get("record_count") or 0)
            else:
                dataset_key = str(row[0] or "")
                module_key = str(row[1] or "")
                record_count = int(row[2] or 0)
            if dataset_key == "businessModules":
                if module_key:
                    business_counts[module_key] = record_count
            elif dataset_key in inventory:
                inventory[dataset_key] = record_count

    with mysql_connect(platform_database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(platform_sql)
            merge_rows(cur.fetchall())
    with mysql_connect(catalog_database_url or platform_database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(catalog_sql)
            merge_rows(cur.fetchall())

    inventory["businessModules"] = business_counts
    inventory["totalRecords"] = sum(
        int(inventory.get(key) or 0) for key in MIGRATION_DATASET_KEYS
    ) + sum(business_counts.values())
    return inventory


def build_migration_verification_report(
    source_inventory: dict[str, Any],
    target_inventory: dict[str, Any],
) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []

    def compare(dataset: str, source_count: Any, target_count: Any) -> None:
        source_value = int(source_count or 0)
        target_value = int(target_count or 0)
        missing = max(source_value - target_value, 0)
        if missing:
            mismatches.append(
                {
                    "dataset": dataset,
                    "source": source_value,
                    "target": target_value,
                    "missing": missing,
                }
            )

    for dataset in MIGRATION_DATASET_KEYS:
        compare(dataset, source_inventory.get(dataset), target_inventory.get(dataset))

    source_business = source_inventory.get("businessModules") or {}
    target_business = target_inventory.get("businessModules") or {}
    for module_key in sorted(source_business):
        compare(
            f"businessModules.{module_key}",
            source_business.get(module_key),
            target_business.get(module_key),
        )

    missing_records = sum(int(item["missing"]) for item in mismatches)
    verified = not mismatches
    return {
        "status": "passed" if verified else "failed",
        "verified": verified,
        "missingRecords": missing_records,
        "mismatches": mismatches,
    }


def upsert_version_records(
    records: list[dict[str, Any]],
    *,
    table: str,
    owner_field: str,
    owner_column: str,
) -> None:
    if not records:
        return
    from .database import mysql_connect

    with mysql_connect() as conn:
        with conn.cursor() as cur:
            for record in records:
                cur.execute(
                    f"""
                    INSERT INTO {table} (
                        id, {owner_column}, change_type, snapshot,
                        source_version_id, created_by, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        change_type = VALUES(change_type),
                        snapshot = VALUES(snapshot),
                        source_version_id = VALUES(source_version_id),
                        created_by = VALUES(created_by),
                        created_at = VALUES(created_at)
                    """,
                    (
                        record.get("id"),
                        record.get(owner_field),
                        record.get("changeType") or "migration",
                        json.dumps(record.get("snapshot") or {}, ensure_ascii=False),
                        record.get("sourceVersionId") or None,
                        record.get("createdBy") or "migration",
                        record.get("createdAt"),
                    ),
                )
        conn.commit()


def migrate_json_to_mysql(data_dir: Path) -> dict[str, Any]:
    sources = migration_sources(Path(data_dir))

    from .admin_roles import upsert_roles_mysql
    from .admin_users import upsert_users_mysql
    from .business import upsert_business_records_mysql, upsert_layers_mysql
    from .database import init_platform_schema
    from .forest_blocks import upsert_blocks_mysql
    from .forest_rights import upsert_rights_mysql
    from .forest_scene_links import save_scene_links_mysql_batch
    from .imports import upsert_import_report_mysql

    init_platform_schema()
    upsert_blocks_mysql(sources["forestBlocks"])
    upsert_rights_mysql(sources["forestRights"])
    upsert_layers_mysql(sources["mapLayers"])
    for module_key, records in sources["businessModules"].items():
        upsert_business_records_mysql(module_key, records)
    upsert_roles_mysql(sources["adminRoles"])
    upsert_users_mysql(sources["adminUsers"])
    for report in sources["importBatches"]:
        upsert_import_report_mysql(report)
    save_scene_links_mysql_batch(sources["forestSceneLinks"])
    upsert_version_records(
        sources["forestBlockVersions"],
        table="forest_block_versions",
        owner_field="forestBlockId",
        owner_column="forest_block_id",
    )
    upsert_version_records(
        sources["forestRightVersions"],
        table="forest_right_versions",
        owner_field="forestRightId",
        owner_column="forest_right_id",
    )

    from server import app as app_module

    for scene in sources["imageryScenes"]:
        app_module.mysql_upsert_scene(scene)
    for task in sources["imageryTasks"]:
        app_module.mysql_upsert_task(task)

    source_inventory = collect_json_migration_inventory(Path(data_dir))
    platform_database_url = os.environ.get("SMART_BAMBOO_DATABASE_URL", "").strip() or None
    catalog_database_url = (
        os.environ.get("REMOTE_SENSING_DATABASE_URL", "").strip()
        or platform_database_url
    )
    target_inventory = collect_mysql_migration_inventory(
        platform_database_url=platform_database_url,
        catalog_database_url=catalog_database_url,
    )
    verification = build_migration_verification_report(source_inventory, target_inventory)
    return {
        **source_inventory,
        "sourceInventory": source_inventory,
        "targetInventory": target_inventory,
        "verification": verification,
    }
