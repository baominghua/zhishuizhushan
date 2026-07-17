from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.modules.database import mysql_connect
from server.modules.mysql_schema import (
    PLATFORM_CORE_MYSQL_TABLES,
    PLATFORM_MYSQL_TABLES,
    REMOTE_SENSING_MYSQL_TABLES,
    apply_mysql_schema_upgrades,
    mysql_catalog_schema_statements,
    mysql_platform_schema_statements,
)


REQUIRED_INDEXES = {
    "business_record_attributes": {
        "idx_business_attribute_text",
        "idx_business_attribute_number",
        "idx_business_attribute_date",
        "idx_business_attribute_datetime",
        "idx_business_attribute_boolean",
    },
    "forest_block_geometries": {"idx_forest_block_geometry", "idx_forest_block_centroid"},
    "forest_blocks": {
        "idx_forest_blocks_town",
        "idx_forest_blocks_town_active_updated",
        "idx_forest_blocks_town_active_area",
        "idx_forest_blocks_village",
        "idx_forest_blocks_operation",
        "idx_forest_blocks_operation_active",
        "idx_forest_blocks_updated",
    },
    "import_batches": {"idx_import_batches_workflow", "idx_import_batches_status_time"},
    "import_batch_events": {"idx_import_batch_events_time", "idx_import_batch_events_action"},
    "remote_sensing_scene_geometries": {"idx_remote_sensing_scene_footprint"},
    "remote_sensing_scene_events": {"idx_remote_scene_events_time", "idx_remote_scene_events_action"},
    "remote_sensing_task_events": {"idx_remote_task_events_time", "idx_remote_task_events_action"},
}

REQUIRED_SPATIAL_INDEXES = {
    "forest_block_geometries": {"idx_forest_block_geometry", "idx_forest_block_centroid"},
    "remote_sensing_scene_geometries": {"idx_remote_sensing_scene_footprint"},
}

REQUIRED_FOREIGN_KEYS = {
    "business_record_attributes": {"fk_business_attribute_record"},
    "forest_block_geometries": {"fk_forest_block_geometry_block"},
    "forest_block_versions": {"fk_forest_block_version_block"},
    "forest_right_versions": {"fk_forest_right_version_right"},
    "forest_right_block_links": {"fk_forest_right_block_right", "fk_forest_right_block_block"},
    "map_layer_block_links": {"fk_map_layer_block_layer", "fk_map_layer_block_block"},
    "map_layer_right_links": {"fk_map_layer_right_layer", "fk_map_layer_right_right"},
    "business_record_block_links": {"fk_business_block_record", "fk_business_block_block"},
    "business_record_right_links": {"fk_business_right_record", "fk_business_right_right"},
    "admin_role_permissions": {"fk_admin_role_permission_role"},
    "admin_role_menu_modules": {"fk_admin_role_module_role"},
    "admin_user_roles": {"fk_admin_user_role_user", "fk_admin_user_role_role"},
    "import_batch_events": {"fk_import_batch_event_batch"},
    "import_batch_block_links": {"fk_import_batch_block_batch", "fk_import_batch_block_block"},
    "import_batch_right_links": {"fk_import_batch_right_batch", "fk_import_batch_right_right"},
    "import_batch_scene_links": {"fk_import_batch_scene_batch"},
    "forest_block_scene_links": {"fk_forest_block_scene_block"},
    "remote_sensing_scene_events": {"fk_remote_scene_event_scene"},
    "remote_sensing_scene_geometries": {"fk_remote_sensing_scene_geometry_scene"},
    "remote_sensing_task_events": {"fk_remote_task_event_task"},
}

REQUIRED_COLUMNS = {
    "import_batch_block_links": {"target_json"},
    "import_batch_right_links": {"target_json"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the Smart Bamboo MySQL production schema and indexes.")
    parser.add_argument("--database-url", default=os.environ.get("SMART_BAMBOO_DATABASE_URL", ""))
    parser.add_argument(
        "--catalog-database-url",
        default=os.environ.get("REMOTE_SENSING_DATABASE_URL", ""),
    )
    parser.add_argument("--initialize", action="store_true", help="Create any missing platform tables before verification.")
    return parser.parse_args()


def initialize_schema(conn: Any, statements: list[str], *, apply_upgrades: bool = False) -> None:
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
        if apply_upgrades:
            apply_mysql_schema_upgrades(cur)
    conn.commit()


def build_schema_report(
    *,
    mysql_version: str,
    table_rows: list[tuple[Any, ...]],
    index_rows: list[tuple[Any, ...]],
    constraint_rows: list[tuple[Any, ...]],
    column_rows: list[tuple[Any, ...]] | None = None,
    required_tables: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    required_tables = list(required_tables or PLATFORM_MYSQL_TABLES)
    required_table_set = set(required_tables)
    tables = {
        str(row[0]): {"engine": str(row[1] or ""), "collation": str(row[2] or "")}
        for row in table_rows
    }
    indexes: dict[str, dict[str, str]] = {}
    for table_name, index_name, index_type in index_rows:
        indexes.setdefault(str(table_name), {})[str(index_name)] = str(index_type or "")
    foreign_keys: dict[str, set[str]] = {}
    for table_name, constraint_name, _referenced_table_name in constraint_rows:
        foreign_keys.setdefault(str(table_name), set()).add(str(constraint_name))
    columns: dict[str, set[str]] = {}
    for table_name, column_name in column_rows or []:
        columns.setdefault(str(table_name), set()).add(str(column_name))

    missing_tables = [table for table in required_tables if table not in tables]
    invalid_engines = [
        table for table in required_tables if table in tables and tables[table]["engine"].lower() != "innodb"
    ]
    invalid_collations = [
        table
        for table in required_tables
        if table in tables and not tables[table]["collation"].lower().startswith("utf8mb4")
    ]
    missing_indexes = [
        f"{table}.{index_name}"
        for table, required in REQUIRED_INDEXES.items()
        if table in required_table_set
        for index_name in sorted(required)
        if index_name not in indexes.get(table, {})
    ]
    invalid_spatial_indexes = [
        f"{table}.{index_name}"
        for table, required in REQUIRED_SPATIAL_INDEXES.items()
        if table in required_table_set
        for index_name in sorted(required)
        if indexes.get(table, {}).get(index_name, "").upper() != "SPATIAL"
    ]
    missing_foreign_keys = [
        f"{table}.{constraint_name}"
        for table, required in REQUIRED_FOREIGN_KEYS.items()
        if table in required_table_set
        for constraint_name in sorted(required)
        if constraint_name not in foreign_keys.get(table, set())
    ]
    missing_columns = [
        f"{table}.{column_name}"
        for table, required in REQUIRED_COLUMNS.items()
        if table in required_table_set
        for column_name in sorted(required)
        if column_name not in columns.get(table, set())
    ] if column_rows is not None else []
    version_match = re.match(r"^(\d+)(?:\.|$)", mysql_version.strip())
    mysql_major_version = int(version_match.group(1)) if version_match else 0
    is_supported_mysql = mysql_major_version >= 8 and "mariadb" not in mysql_version.lower()
    invalid_mysql_version = "" if is_supported_mysql else mysql_version
    schema_ready = not any(
        [
            invalid_mysql_version,
            missing_tables,
            invalid_engines,
            invalid_collations,
            missing_indexes,
            invalid_spatial_indexes,
            missing_foreign_keys,
            missing_columns,
        ]
    )
    return {
        "database": "mysql",
        "requirements": [
            "MySQL 8+",
            "ENGINE=InnoDB",
            "utf8mb4",
            "SPATIAL indexes",
            "foreign keys",
            "normalized import targets",
        ],
        "schemaReady": schema_ready,
        "mysqlVersion": mysql_version,
        "invalidMysqlVersion": invalid_mysql_version,
        "tableCount": len([table for table in required_tables if table in tables]),
        "requiredTableCount": len(required_tables),
        "missingTables": missing_tables,
        "invalidEngines": invalid_engines,
        "invalidCollations": invalid_collations,
        "missingIndexes": missing_indexes,
        "invalidSpatialIndexes": invalid_spatial_indexes,
        "missingForeignKeys": missing_foreign_keys,
        "missingColumns": missing_columns,
    }


def verify_schema(conn: Any, required_tables: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT VERSION()")
        version_row = cur.fetchone()
        cur.execute(
            "SELECT table_name, engine, table_collation "
            "FROM information_schema.tables WHERE table_schema = DATABASE()"
        )
        table_rows = cur.fetchall()
        cur.execute(
            "SELECT table_name, index_name, index_type "
            "FROM information_schema.statistics WHERE table_schema = DATABASE()"
        )
        index_rows = cur.fetchall()
        cur.execute(
            "SELECT table_name, constraint_name, referenced_table_name "
            "FROM information_schema.referential_constraints WHERE constraint_schema = DATABASE()"
        )
        constraint_rows = cur.fetchall()
        cur.execute(
            "SELECT table_name, column_name "
            "FROM information_schema.columns WHERE table_schema = DATABASE()"
        )
        column_rows = cur.fetchall()

    return build_schema_report(
        mysql_version=str(version_row[0] if version_row else ""),
        table_rows=list(table_rows),
        index_rows=list(index_rows),
        constraint_rows=list(constraint_rows),
        column_rows=list(column_rows),
        required_tables=required_tables,
    )


def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise SystemExit("SMART_BAMBOO_DATABASE_URL or --database-url is required")
    catalog_database_url = args.catalog_database_url or args.database_url
    with mysql_connect(args.database_url) as conn:
        if args.initialize:
            initialize_schema(conn, mysql_platform_schema_statements(), apply_upgrades=True)
        platform_report = verify_schema(conn, PLATFORM_CORE_MYSQL_TABLES)
    with mysql_connect(catalog_database_url) as conn:
        if args.initialize:
            initialize_schema(conn, mysql_catalog_schema_statements())
        catalog_report = verify_schema(conn, REMOTE_SENSING_MYSQL_TABLES)
    report = {
        "database": "mysql",
        "schemaReady": platform_report["schemaReady"] and catalog_report["schemaReady"],
        "platform": platform_report,
        "catalog": catalog_report,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["schemaReady"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
