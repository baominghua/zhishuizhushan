from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_settings_infer_mysql_backend_from_mysql_database_url(monkeypatch, isolated_env):
    monkeypatch.delenv("SMART_BAMBOO_STORAGE_BACKEND", raising=False)
    monkeypatch.setenv(
        "SMART_BAMBOO_DATABASE_URL",
        "mysql://smart_bamboo:secret@db:3306/smart_bamboo?charset=utf8mb4",
    )

    import server.modules.settings as settings
    import server.modules.database as database

    settings.get_settings.cache_clear()
    importlib.reload(settings)
    importlib.reload(database)
    settings.get_settings.cache_clear()

    assert settings.get_settings().storage_backend == "mysql"
    assert database.use_mysql() is True
    assert database.use_postgis() is False


def test_mysql_schema_normalizes_core_search_and_linkage_data():
    from server.modules.mysql_schema import PLATFORM_MYSQL_TABLES, mysql_schema_statements

    ddl = "\n".join(mysql_schema_statements())

    assert {
        "forest_blocks",
        "forest_block_geometries",
        "forest_block_versions",
        "forest_rights",
        "forest_right_versions",
        "forest_right_block_links",
        "map_layers",
        "business_records",
        "admin_roles",
        "admin_users",
        "import_batches",
        "import_batch_block_links",
        "import_batch_right_links",
        "import_batch_scene_links",
        "import_batch_events",
        "remote_sensing_scenes",
        "remote_sensing_scene_geometries",
        "remote_sensing_scene_events",
        "remote_sensing_tasks",
        "remote_sensing_task_events",
    }.issubset(set(PLATFORM_MYSQL_TABLES))
    assert "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" in ddl
    assert "SPATIAL INDEX idx_forest_block_geometry (geometry)" in ddl
    assert "KEY idx_forest_blocks_operation (base_type, operation_type)" in ddl
    assert "FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id)" in ddl
    assert "UNIQUE KEY uq_forest_right_block (forest_right_id, forest_block_id)" in ddl
    assert ddl.count("target_json JSON") >= 2
    assert "JSON" in ddl
    assert "jsonb" not in ddl.lower()
    assert "CREATE EXTENSION" not in ddl.upper()


def test_mysql_schema_exposes_separate_platform_and_remote_catalog_table_sets():
    from server.modules.mysql_schema import PLATFORM_CORE_MYSQL_TABLES, REMOTE_SENSING_MYSQL_TABLES

    assert "forest_blocks" in PLATFORM_CORE_MYSQL_TABLES
    assert "business_records" in PLATFORM_CORE_MYSQL_TABLES
    assert "remote_sensing_scenes" in REMOTE_SENSING_MYSQL_TABLES
    assert "remote_sensing_tasks" in REMOTE_SENSING_MYSQL_TABLES
    assert set(PLATFORM_CORE_MYSQL_TABLES).isdisjoint(REMOTE_SENSING_MYSQL_TABLES)
    app_source = read_text("server/app.py")
    assert "REMOTE_SENSING_MYSQL_TABLES," in app_source
    assert "REMOTE_SENSING_MYSQL_TABLES = [" not in app_source


def test_mysql_schema_upgrade_adds_all_ledger_indexes_only_when_missing():
    from server.modules.mysql_schema import mysql_index_upgrade_statements

    missing = mysql_index_upgrade_statements(set())
    existing = mysql_index_upgrade_statements(
        {
            ("forest_blocks", "idx_forest_blocks_operation"),
            ("forest_blocks", "idx_forest_blocks_town_active_updated"),
            ("forest_blocks", "idx_forest_blocks_town_active_area"),
            ("forest_blocks", "idx_forest_blocks_operation_active"),
        }
    )

    assert missing == [
        "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_operation (base_type, operation_type)",
        "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_town_active_updated (town_code, deleted_at, updated_at)",
        "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_town_active_area (deleted_at, town_code, area_mu)",
        "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_operation_active (deleted_at, base_type, operation_type)",
    ]
    assert existing == []


def test_mysql_schema_upgrade_inspects_existing_indexes_before_alter():
    from server.modules.mysql_schema import apply_mysql_schema_upgrades

    class RecordingCursor:
        def __init__(self):
            self.calls: list[str] = []

        def execute(self, sql, params=()):
            self.calls.append(" ".join(sql.split()))

        def fetchall(self):
            if "information_schema.statistics" in self.calls[-1]:
                return [("forest_blocks", "PRIMARY")]
            return []

    cursor = RecordingCursor()

    apply_mysql_schema_upgrades(cursor)

    assert "information_schema.statistics" in cursor.calls[0]
    assert cursor.calls[1:5] == [
        "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_operation (base_type, operation_type)",
        "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_town_active_updated (town_code, deleted_at, updated_at)",
        "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_town_active_area (deleted_at, town_code, area_mu)",
        "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_operation_active (deleted_at, base_type, operation_type)",
    ]
    assert "information_schema.columns" in cursor.calls[5]
    assert cursor.calls[6] == (
        "ALTER TABLE import_batch_block_links ADD COLUMN target_json JSON NULL"
    )
    assert cursor.calls[7] == (
        "ALTER TABLE import_batch_right_links ADD COLUMN target_json JSON NULL"
    )


def test_mysql_deployment_is_the_default_production_stack():
    compose = read_text("docker-compose.yml")
    requirements = read_text("server/requirements.txt")
    env_example = read_text(".env.example")

    assert "mysql:8.4" in compose
    assert 'MYSQL_DATABASE: "${MYSQL_DATABASE:-smart_bamboo}"' in compose
    assert 'MYSQL_PASSWORD: "${MYSQL_PASSWORD:?Set MYSQL_PASSWORD in .env}"' in compose
    assert 'MYSQL_ROOT_PASSWORD: "${MYSQL_ROOT_PASSWORD:?Set MYSQL_ROOT_PASSWORD in .env}"' in compose
    assert 'SMART_BAMBOO_STORAGE_BACKEND: "${SMART_BAMBOO_STORAGE_BACKEND:-mysql}"' in compose
    assert "smart_bamboo_dev" not in compose
    assert "smart_bamboo_mysql:/var/lib/mysql" in compose
    assert "PyMySQL>=1.1" in requirements
    assert "SMART_BAMBOO_STORAGE_BACKEND=mysql" in env_example
    assert "SMART_BAMBOO_DATABASE_URL=mysql://smart_bamboo:change-me@db:3306/smart_bamboo" in env_example
    assert "SMART_BAMBOO_DB_PORT=3307" in env_example
    assert 'REMOTE_SENSING_CATALOG_BACKEND: "${REMOTE_SENSING_CATALOG_BACKEND:-mysql}"' in compose


def test_mysql_production_verifier_checks_storage_engine_collation_and_indexes():
    verifier = read_text("server/scripts/verify_mysql_production.py")
    deploy_script = read_text("scripts/verify-production.ps1")
    doc = read_text("docs/deploy-smart-bamboo-platform.md")

    assert "--database-url" in verifier
    assert "--initialize" in verifier
    assert "information_schema.tables" in verifier
    assert "information_schema.statistics" in verifier
    assert "information_schema.referential_constraints" in verifier
    assert "SELECT VERSION()" in verifier
    assert "ENGINE=InnoDB" in verifier
    assert "utf8mb4" in verifier
    assert "idx_forest_block_geometry" in verifier
    assert "idx_forest_block_centroid" in verifier
    assert "idx_forest_blocks_operation" in verifier
    assert "idx_remote_sensing_scene_footprint" in verifier
    assert "idx_import_batch_events_time" in verifier
    assert "idx_remote_scene_events_time" in verifier
    assert '"missingForeignKeys"' in verifier
    assert '"schemaReady"' in verifier
    assert "docker compose up --build -d" in deploy_script
    assert "verify_mysql_production.py" in deploy_script
    assert 'deployment.readiness.status' in deploy_script
    assert 'Production readiness is not ready' in deploy_script
    assert 'deployment.smartBamboo.importTuning' in deploy_script
    assert 'incremental-batch' in deploy_script
    assert 'MySQL import tuning is not production-ready' in deploy_script
    assert "scripts\\verify-production.ps1" in doc


def test_mysql_production_verifier_rejects_missing_relations_and_scene_spatial_index():
    from server.scripts.verify_mysql_production import build_schema_report

    table_rows = [
        (table_name, "InnoDB", "utf8mb4_0900_ai_ci")
        for table_name in __import__(
            "server.modules.mysql_schema", fromlist=["PLATFORM_MYSQL_TABLES"]
        ).PLATFORM_MYSQL_TABLES
    ]
    index_rows = [
        ("forest_block_geometries", "idx_forest_block_geometry", "SPATIAL"),
        ("forest_blocks", "idx_forest_blocks_town", "BTREE"),
        ("forest_blocks", "idx_forest_blocks_village", "BTREE"),
        ("forest_blocks", "idx_forest_blocks_updated", "BTREE"),
        ("import_batches", "idx_import_batches_workflow", "BTREE"),
        ("import_batches", "idx_import_batches_status_time", "BTREE"),
        ("import_batch_events", "idx_import_batch_events_time", "BTREE"),
        ("import_batch_events", "idx_import_batch_events_action", "BTREE"),
        ("remote_sensing_scene_events", "idx_remote_scene_events_time", "BTREE"),
        ("remote_sensing_scene_events", "idx_remote_scene_events_action", "BTREE"),
        ("remote_sensing_task_events", "idx_remote_task_events_time", "BTREE"),
        ("remote_sensing_task_events", "idx_remote_task_events_action", "BTREE"),
    ]

    report = build_schema_report(
        mysql_version="8.4.1",
        table_rows=table_rows,
        index_rows=index_rows,
        constraint_rows=[],
        column_rows=[],
    )

    assert report["schemaReady"] is False
    assert "remote_sensing_scene_geometries.idx_remote_sensing_scene_footprint" in report[
        "missingIndexes"
    ]
    assert "remote_sensing_scene_geometries.idx_remote_sensing_scene_footprint" in report[
        "invalidSpatialIndexes"
    ]
    assert "forest_block_geometries.idx_forest_block_centroid" in report[
        "missingIndexes"
    ]
    assert "forest_block_geometries.fk_forest_block_geometry_block" in report[
        "missingForeignKeys"
    ]
    assert "import_batch_block_links.target_json" in report["missingColumns"]
    assert "import_batch_right_links.target_json" in report["missingColumns"]


def test_mysql_production_verifier_rejects_pre_mysql_8_servers():
    from server.scripts.verify_mysql_production import build_schema_report

    report = build_schema_report(
        mysql_version="5.7.44-log",
        table_rows=[],
        index_rows=[],
        constraint_rows=[],
    )

    assert report["schemaReady"] is False
    assert report["mysqlVersion"] == "5.7.44-log"
    assert report["invalidMysqlVersion"] == "5.7.44-log"


def test_mysql_production_verifier_does_not_accept_mariadb_as_mysql_8():
    from server.scripts.verify_mysql_production import build_schema_report

    report = build_schema_report(
        mysql_version="10.11.7-MariaDB",
        table_rows=[],
        index_rows=[],
        constraint_rows=[],
    )

    assert report["schemaReady"] is False
    assert report["invalidMysqlVersion"] == "10.11.7-MariaDB"


def test_mysql_production_verifier_requires_typed_business_attribute_indexes_and_relation():
    from server.scripts.verify_mysql_production import (
        REQUIRED_COLUMNS,
        REQUIRED_FOREIGN_KEYS,
        REQUIRED_INDEXES,
    )

    assert REQUIRED_INDEXES["business_record_attributes"] == {
        "idx_business_attribute_text",
        "idx_business_attribute_number",
        "idx_business_attribute_date",
        "idx_business_attribute_datetime",
        "idx_business_attribute_boolean",
    }
    assert "fk_business_attribute_record" in REQUIRED_FOREIGN_KEYS["business_record_attributes"]
    assert REQUIRED_COLUMNS["import_batch_block_links"] == {"target_json"}
    assert REQUIRED_COLUMNS["import_batch_right_links"] == {"target_json"}


def test_mysql_production_verifier_supports_separate_catalog_database():
    script = read_text("server/scripts/verify_mysql_production.py")
    database_module = read_text("server/modules/database.py")

    assert "--catalog-database-url" in script
    assert "REMOTE_SENSING_DATABASE_URL" in script
    assert '"platform": platform_report' in script
    assert '"catalog": catalog_report' in script
    assert "PLATFORM_CORE_MYSQL_TABLES" in database_module


def test_mysql_production_verifier_connects_platform_and_catalog_databases_separately(monkeypatch, capsys):
    from argparse import Namespace
    from server.scripts import verify_mysql_production as verifier

    connections: list[str] = []
    required_sets: list[tuple[str, ...]] = []

    class Connection:
        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        verifier,
        "parse_args",
        lambda: Namespace(
            database_url="mysql://platform/db",
            catalog_database_url="mysql://catalog/db",
            initialize=False,
        ),
    )
    monkeypatch.setattr(
        verifier,
        "mysql_connect",
        lambda url: connections.append(url) or Connection(url),
    )

    def fake_verify(_conn, required_tables):
        required_sets.append(tuple(required_tables))
        return {"schemaReady": True}

    monkeypatch.setattr(verifier, "verify_schema", fake_verify)

    assert verifier.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert connections == ["mysql://platform/db", "mysql://catalog/db"]
    assert required_sets == [
        tuple(verifier.PLATFORM_CORE_MYSQL_TABLES),
        tuple(verifier.REMOTE_SENSING_MYSQL_TABLES),
    ]
    assert report["platform"]["schemaReady"] is True
    assert report["catalog"]["schemaReady"] is True


def test_forest_block_mysql_queries_use_mysql_spatial_and_text_syntax():
    from server.modules.forest_blocks import ForestBlockFilters, MYSQL_SELECT_SQL, mysql_where

    filters = ForestBlockFilters(q="黄坑", bbox="118.0,26.0,119.0,27.0")
    where_sql, params = mysql_where(filters=filters)

    assert "LEFT JOIN forest_block_geometries" in MYSQL_SELECT_SQL
    assert "ST_AsGeoJSON(g.geometry)" in MYSQL_SELECT_SQL
    assert "LIKE %s" in where_sql
    assert "ILIKE" not in where_sql
    assert "properties::text" not in where_sql
    assert "MBRIntersects" in where_sql
    assert "ST_GeomFromText" in where_sql
    assert "axis-order=long-lat" in where_sql
    assert params[-1] == "POLYGON((118.0 26.0,119.0 26.0,119.0 27.0,118.0 27.0,118.0 26.0))"


def test_mysql_bbox_ledger_is_driven_by_the_spatial_index():
    from server.modules.forest_blocks import mysql_select_sql_for_filters

    sql = mysql_select_sql_for_filters(has_bbox=True)

    assert "FROM forest_block_geometries g FORCE INDEX (idx_forest_block_geometry)" in sql
    assert "STRAIGHT_JOIN forest_blocks b" in sql
    assert "LEFT JOIN forest_block_geometries" not in sql


def test_mysql_schema_has_active_ledger_covering_indexes():
    from server.modules.mysql_schema import MYSQL_INDEX_UPGRADES, mysql_platform_schema_statements
    from server.scripts.verify_mysql_production import REQUIRED_INDEXES

    sql = "\n".join(mysql_platform_schema_statements()) + "\n" + "\n".join(MYSQL_INDEX_UPGRADES.values())
    required = REQUIRED_INDEXES["forest_blocks"]

    for index_name in (
        "idx_forest_blocks_town_active_updated",
        "idx_forest_blocks_town_active_area",
        "idx_forest_blocks_operation_active",
    ):
        assert index_name in sql
        assert index_name in required


def test_mysql_bulk_forest_block_upsert_uses_batched_statements_and_one_commit(monkeypatch):
    from server.modules import forest_blocks

    class RecordingCursor:
        def __init__(self):
            self.executed: list[tuple[str, tuple]] = []
            self.executed_many: list[tuple[str, list[tuple]]] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            self.executed.append((" ".join(sql.split()), tuple(params)))

        def executemany(self, sql, params):
            self.executed_many.append((" ".join(sql.split()), list(params)))

    class RecordingConnection:
        def __init__(self, cursor):
            self.cursor_obj = cursor
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.commits += 1

    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(forest_blocks, "mysql_connect", lambda: connection)
    monkeypatch.setattr(forest_blocks, "FOREST_BLOCK_MYSQL_WRITE_BATCH_SIZE", 2, raising=False)
    monkeypatch.setattr(forest_blocks, "bump_forest_vector_tile_revision", lambda: None)
    blocks = [
        forest_blocks.normalize_block(
            {
                "blockCode": "BULK-001",
                "name": "批量林班一",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[118.0, 26.0], [118.1, 26.0], [118.1, 26.1], [118.0, 26.0]]],
                },
            }
        ),
        forest_blocks.normalize_block({"blockCode": "BULK-002", "name": "批量林班二"}),
    ]

    forest_blocks.upsert_blocks_mysql(blocks)

    assert connection.commits == 1
    assert len(cursor.executed_many) == 2
    assert "INSERT INTO forest_blocks" in cursor.executed_many[0][0]
    assert len(cursor.executed_many[0][1]) == 2
    assert "INSERT INTO forest_block_geometries" in cursor.executed_many[1][0]
    assert len(cursor.executed_many[1][1]) == 1
    assert len(cursor.executed) == 1
    assert "DELETE FROM forest_block_geometries" in cursor.executed[0][0]


def test_mysql_right_archive_batch_merges_only_requested_archives(monkeypatch):
    from server.modules import forest_rights

    existing = forest_rights.normalize_right(
        {
            "id": "right-existing",
            "archiveCode": "CERT-001",
            "certificateNo": "CERT-001",
            "holder": "原权利人",
            "linkedBlockCodes": ["OLD-BLOCK"],
            "properties": {"kept": True},
        }
    )
    saved: list[dict] = []
    monkeypatch.setattr(forest_rights, "use_mysql", lambda: True)
    monkeypatch.setattr(forest_rights, "use_postgis", lambda: False)
    monkeypatch.setattr(
        forest_rights,
        "fetch_rights_by_archive_codes_mysql",
        lambda codes: [existing] if "CERT-001" in codes else [],
        raising=False,
    )
    monkeypatch.setattr(forest_rights, "load_all_rights", lambda: (_ for _ in ()).throw(AssertionError("full rights ledger loaded")))
    monkeypatch.setattr(forest_rights, "save_rights", lambda rights: saved.extend(rights))
    blocks = [
        {
            "id": "block-new",
            "blockCode": "NEW-BLOCK",
            "name": "新林班",
            "properties": {"rights": {"certificateNo": "CERT-001", "holder": "新权利人"}},
        }
    ]

    merged = forest_rights.upsert_right_archives_from_blocks(blocks)

    assert len(saved) == 1
    assert saved[0]["id"] == "right-existing"
    assert saved[0]["holder"] == "新权利人"
    assert set(saved[0]["linkedBlockCodes"]) == {"OLD-BLOCK", "NEW-BLOCK"}
    assert merged == saved


def test_mysql_facets_use_grouped_sql_without_loading_all_geometries(monkeypatch):
    from server.modules import forest_blocks as forest_blocks_module
    from server.modules.auth import AuthContext

    class FacetCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))

        def fetchall(self):
            return [
                ("countyCode", "350703", "建阳区", 120),
                ("townCode", "350703101", "麻沙镇", 80),
                ("riskLevel", "low", "low", 96),
            ]

    class FacetConnection:
        def __init__(self, cursor):
            self.cursor_obj = cursor

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return self.cursor_obj

    cursor = FacetCursor()
    monkeypatch.setattr(forest_blocks_module, "use_mysql", lambda: True)
    monkeypatch.setattr(forest_blocks_module, "use_postgis", lambda: False)
    monkeypatch.setattr(
        forest_blocks_module,
        "mysql_connect",
        lambda: FacetConnection(cursor),
    )
    monkeypatch.setattr(
        forest_blocks_module,
        "forest_block_summary_mysql",
        lambda filters, context: {"total": 120, "totalAreaMu": 18000},
    )
    monkeypatch.setattr(
        forest_blocks_module,
        "filtered_forest_blocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("full row load")),
    )

    result = forest_blocks_module.forest_block_facets(
        forest_blocks_module.ForestBlockFilters(countyCode="350703"),
        AuthContext(user="admin", roles={"admin"}, projects={"*"}, areas={"*"}),
    )

    assert result["summary"] == {"total": 120, "totalAreaMu": 18000}
    assert result["facets"]["countyCode"] == [
        {"value": "350703", "label": "建阳区", "count": 120}
    ]
    assert result["facets"]["townCode"] == [
        {"value": "350703101", "label": "麻沙镇", "count": 80}
    ]
    assert result["facets"]["riskLevel"] == [
        {"value": "low", "label": "low", "count": 96}
    ]
    assert len(cursor.calls) == 1
    sql, params = cursor.calls[0]
    assert "UNION ALL" in sql
    assert "COUNT(*)" in sql
    assert "GROUP BY" in sql
    assert "ST_AsGeoJSON" not in sql
    assert "forest_block_geometries" not in sql
    assert params.count("350703") == len(forest_blocks_module.FOREST_BLOCK_FACETS)


def test_mysql_summary_uses_one_grouped_query_and_one_connection(monkeypatch):
    from server.modules import forest_blocks as forest_blocks_module
    from server.modules.auth import AuthContext

    class SummaryCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []
            self.last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=()):
            self.last_sql = " ".join(sql.split())
            self.calls.append((self.last_sql, tuple(params)))

        def fetchone(self):
            return (10, 1000, 7)

        def fetchall(self):
            if "UNION ALL" in self.last_sql:
                return [
                    ("summary", "", 10, 1000, 7),
                    ("riskLevel", "low", 8, 0, 0),
                    ("riskLevel", "high", 2, 0, 0),
                    ("qualityGrade", "A", 6, 0, 0),
                    ("qualityGrade", "B", 4, 0, 0),
                    ("baseType", "cooperative", 10, 0, 0),
                    ("healthStatus", "normal", 7, 0, 0),
                    ("healthStatus", "warning", 3, 0, 0),
                ]
            if "risk_level" in self.last_sql:
                return [("low", 8), ("high", 2)]
            if "quality_grade" in self.last_sql:
                return [("A", 6), ("B", 4)]
            if "base_type" in self.last_sql:
                return [("cooperative", 10)]
            return [("normal", 7), ("warning", 3)]

    class SummaryConnection:
        def __init__(self, cursor):
            self.cursor_obj = cursor

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return self.cursor_obj

    cursor = SummaryCursor()
    connect_count = 0

    def connect():
        nonlocal connect_count
        connect_count += 1
        return SummaryConnection(cursor)

    monkeypatch.setattr(forest_blocks_module, "mysql_connect", connect)

    result = forest_blocks_module.forest_block_summary_mysql(
        forest_blocks_module.ForestBlockFilters(countyCode="350703"),
        AuthContext(user="admin", roles={"admin"}, projects={"*"}, areas={"*"}),
    )

    assert result == {
        "total": 10,
        "totalAreaMu": 1000.0,
        "healthyCount": 7,
        "healthyRate": 70,
        "riskLevel": {"low": 8, "high": 2},
        "qualityGrade": {"A": 6, "B": 4},
        "baseType": {"cooperative": 10},
        "healthStatus": {"normal": 7, "warning": 3},
    }
    assert connect_count == 1
    assert len(cursor.calls) == 1
    sql, params = cursor.calls[0]
    assert "UNION ALL" in sql
    assert "ST_AsGeoJSON" not in sql
    assert "forest_block_geometries" not in sql
    assert params.count("350703") == 5


def test_mysql_block_upsert_writes_attributes_and_geometry_separately():
    from server.modules.forest_blocks import execute_upsert_block_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((sql, tuple(params)))

    cursor = RecordingCursor()
    block = {
        "id": "11111111-1111-1111-1111-111111111111",
        "blockCode": "MYSQL-BLOCK-001",
        "name": "MySQL 林班",
        "countyCode": "350703",
        "countyName": "建阳区",
        "areaMu": 125.5,
        "yieldEstimate": {"spring": 20},
        "tags": ["毛竹"],
        "properties": {"source": "test"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[118.0, 26.0], [118.1, 26.0], [118.1, 26.1], [118.0, 26.0]]],
        },
        "createdAt": "2026-07-13T10:00:00+00:00",
        "updatedAt": "2026-07-13T10:00:00+00:00",
    }

    execute_upsert_block_mysql(cursor, block)

    sql = "\n".join(call[0] for call in cursor.calls)
    assert len(cursor.calls) == 2
    assert "INSERT INTO forest_blocks" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "INSERT INTO forest_block_geometries" in sql
    assert "ST_GeomFromGeoJSON" in sql
    assert "vertex_count" in sql


def test_mysql_geometry_upsert_avoids_unsupported_geographic_centroid():
    from server.modules.forest_blocks import MYSQL_GEOMETRY_UPSERT_SQL, mysql_geometry_values

    block = {
        "id": "block-multi",
        "updatedAt": "2026-07-15T12:00:00+00:00",
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [
                [[[118.0, 27.0], [118.1, 27.0], [118.1, 27.1], [118.0, 27.1], [118.0, 27.0]]]
            ],
        },
    }

    values = mysql_geometry_values(block)

    assert "ST_Centroid" not in MYSQL_GEOMETRY_UPSERT_SQL
    assert "axis-order=long-lat" in MYSQL_GEOMETRY_UPSERT_SQL
    assert values is not None
    assert values[2] == "POINT(118.05 27.05)"


def test_mysql_forest_aggregate_reads_geographic_centroid_as_longitude_latitude():
    import inspect

    from server.modules.forest_blocks import forest_block_aggregates_mysql

    source = inspect.getsource(forest_block_aggregates_mysql)

    assert "ST_Longitude(g.centroid)" in source
    assert "ST_Latitude(g.centroid)" in source
    assert "ST_X(g.centroid)" not in source
    assert "ST_Y(g.centroid)" not in source


def test_mysql_row_normalizes_json_and_geojson_columns():
    from server.modules.forest_blocks import normalize_mysql_row

    row = {
        "id": "block-1",
        "block_code": "MYSQL-001",
        "name": "MySQL 林班",
        "yield_estimate": '{"spring": 12}',
        "tags": '["毛竹"]',
        "properties": '{"source": "mysql"}',
        "geometry": '{"type": "MultiPolygon", "coordinates": []}',
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
    }

    block = normalize_mysql_row(row)

    assert block["blockCode"] == "MYSQL-001"
    assert block["yieldEstimate"] == {"spring": 12}
    assert block["tags"] == ["毛竹"]
    assert block["properties"] == {"source": "mysql"}
    assert block["geometry"]["type"] == "MultiPolygon"


def test_forest_block_listing_uses_mysql_repository(monkeypatch):
    from server.modules import forest_blocks
    from server.modules.auth import AuthContext

    expected = {"id": "block-1", "blockCode": "MYSQL-001", "name": "MySQL 林班"}
    monkeypatch.setattr(forest_blocks, "use_mysql", lambda: True)
    monkeypatch.setattr(forest_blocks, "use_postgis", lambda: False)
    monkeypatch.setattr(forest_blocks, "fetch_blocks_mysql", lambda **kwargs: [expected])
    monkeypatch.setattr(forest_blocks, "count_blocks_mysql", lambda filters, context: 1)

    result = forest_blocks.list_forest_blocks(
        forest_blocks.ForestBlockFilters(limit=20),
        AuthContext(user="admin", roles={"admin"}, projects={"*"}, areas={"*"}),
    )

    assert result == {"items": [expected | {"properties": {}}], "total": 1, "limit": 20, "offset": 0}


def test_mysql_summary_and_aggregates_stay_in_database(monkeypatch):
    from server.modules import forest_blocks
    from server.modules.auth import AuthContext

    context = AuthContext(user="admin", roles={"admin"}, projects={"*"}, areas={"*"})
    filters = forest_blocks.ForestBlockFilters()
    summary = {"total": 100000, "totalAreaMu": 1000000}
    aggregates = {"level": "town", "totalGroups": 12, "items": []}
    monkeypatch.setattr(forest_blocks, "use_mysql", lambda: True)
    monkeypatch.setattr(forest_blocks, "use_postgis", lambda: False)
    monkeypatch.setattr(forest_blocks, "forest_block_summary_mysql", lambda _filters, _context: summary)
    monkeypatch.setattr(
        forest_blocks,
        "forest_block_aggregates_mysql",
        lambda level, _filters, _context: aggregates | {"level": level},
    )

    assert forest_blocks.forest_block_summary(filters, context) == summary
    assert forest_blocks.forest_block_aggregates("town", filters, context) == aggregates


def test_mysql_right_upsert_uses_relation_table_for_linked_blocks():
    from server.modules.forest_rights import execute_upsert_right_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((sql, tuple(params)))

    cursor = RecordingCursor()
    right = {
        "id": "22222222-2222-2222-2222-222222222222",
        "archiveCode": "RIGHT-MYSQL-001",
        "certificateNo": "闽（2025）建瓯市不动产权第0012629号",
        "holder": "谭立广",
        "rightStart": "2025-01-01",
        "rightEnd": "2033-06-30",
        "linkedBlockIds": ["11111111-1111-1111-1111-111111111111"],
        "linkedBlockCodes": ["MYSQL-BLOCK-001"],
        "documents": [{"name": "certificate.png"}],
        "properties": {"source": "scan"},
        "createdAt": "2026-07-13T10:00:00+00:00",
        "updatedAt": "2026-07-13T10:00:00+00:00",
    }

    execute_upsert_right_mysql(cursor, right)

    sql = "\n".join(call[0] for call in cursor.calls)
    assert "INSERT INTO forest_rights" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "DELETE FROM forest_right_block_links" in sql
    assert "INSERT IGNORE INTO forest_right_block_links" in sql
    assert "FROM forest_blocks" in sql
    assert "linked_block_codes" not in cursor.calls[0][0]


def test_forest_right_listing_uses_mysql_repository(monkeypatch):
    from server.modules import forest_rights

    expected = {"id": "right-1", "archiveCode": "RIGHT-001", "holder": "谭立广"}
    monkeypatch.setattr(forest_rights, "use_mysql", lambda: True)
    monkeypatch.setattr(forest_rights, "use_postgis", lambda: False)
    monkeypatch.setattr(forest_rights, "fetch_rights_mysql", lambda **kwargs: [expected])
    monkeypatch.setattr(forest_rights, "count_rights_mysql", lambda filters, context=None: 1)

    result = forest_rights.list_forest_rights(forest_rights.ForestRightFilters(limit=20))

    assert result == {"items": [expected], "total": 1, "limit": 20, "offset": 0}


def test_mysql_business_and_layer_upserts_use_relation_tables():
    from server.modules.business import execute_upsert_business_mysql, execute_upsert_layer_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((sql, tuple(params)))

    business_cursor = RecordingCursor()
    record = {
        "id": "33333333-3333-3333-3333-333333333333",
        "recordCode": "FARMER-001",
        "name": "竹农一号",
        "status": "active",
        "linkedBlockCodes": ["MYSQL-BLOCK-001"],
        "linkedRightArchiveCodes": ["RIGHT-MYSQL-001"],
        "properties": {"phone": "13800000000"},
        "createdAt": "2026-07-13T10:00:00+00:00",
        "updatedAt": "2026-07-13T10:00:00+00:00",
    }
    execute_upsert_business_mysql(business_cursor, "farmers", record)
    business_sql = "\n".join(call[0] for call in business_cursor.calls)
    assert "INSERT INTO business_records" in business_sql
    assert "business_record_block_links" in business_sql
    assert "business_record_right_links" in business_sql
    assert "linked_block_codes" not in business_cursor.calls[0][0]


def test_mysql_business_records_have_typed_attribute_storage_and_indexes():
    from server.modules.mysql_schema import PLATFORM_MYSQL_TABLES, mysql_schema_statements

    sql = "\n".join(mysql_schema_statements())

    assert "business_record_attributes" in PLATFORM_MYSQL_TABLES
    assert "CREATE TABLE IF NOT EXISTS business_record_attributes" in sql
    assert "number_value DECIMAL" in sql
    assert "date_value DATE" in sql
    assert "idx_business_attribute_text" in sql
    assert "idx_business_attribute_number" in sql
    assert "idx_business_attribute_date" in sql


def test_mysql_business_core_field_filter_uses_attribute_index_projection():
    from server.modules.business import ManagedFilters, mysql_business_where

    where_sql, params = mysql_business_where(
        "work-logs",
        filters=ManagedFilters(fieldKey="workStage", fieldValue="fertilizing"),
    )

    assert "business_record_attributes" in where_sql
    assert "bra.module_key = br.module_key" in where_sql
    assert "bra.field_key = %s" in where_sql
    assert "bra.text_value = %s" in where_sql
    assert params[-2:] == ["workStage", "fertilizing"]


def test_mysql_business_upsert_projects_core_properties_to_typed_attributes():
    from server.modules.business import execute_upsert_business_mysql, execute_upsert_layer_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((sql, tuple(params)))

    cursor = RecordingCursor()
    record = {
        "id": "6ab8cd2e-f574-4fd8-bdf6-b7788e632188",
        "recordCode": "WORK-ATTR-001",
        "name": "施肥作业",
        "status": "active",
        "linkedBlockCodes": [],
        "linkedRightArchiveCodes": [],
        "properties": {
            "workStage": "fertilizing",
            "worker": "一组",
            "workDate": "2026-07-15",
            "laborCount": 12,
        },
        "createdAt": "2026-07-15T00:00:00+00:00",
        "updatedAt": "2026-07-15T00:00:00+00:00",
        "deletedAt": None,
    }

    execute_upsert_business_mysql(cursor, "work-logs", record)
    sql = "\n".join(call[0] for call in cursor.calls)
    attribute_calls = [call for call in cursor.calls if "INSERT INTO business_record_attributes" in call[0]]

    assert "DELETE FROM business_record_attributes" in sql
    assert len(attribute_calls) == 4
    values_by_key = {call[1][2]: call[1] for call in attribute_calls}
    assert values_by_key["laborCount"][3] == "integer"
    assert values_by_key["laborCount"][5] == 12
    assert values_by_key["workDate"][3] == "date"
    assert str(values_by_key["workDate"][6]) == "2026-07-15"

    layer_cursor = RecordingCursor()
    layer = {
        "id": "44444444-4444-4444-4444-444444444444",
        "recordCode": "LAYER-001",
        "name": "林班边界",
        "status": "published",
        "layerType": "vector",
        "visibleOnDashboard": True,
        "linkedBlockCodes": ["MYSQL-BLOCK-001"],
        "linkedRightArchiveCodes": ["RIGHT-MYSQL-001"],
        "style": {"stroke": "#138a63"},
        "properties": {},
        "createdAt": "2026-07-13T10:00:00+00:00",
        "updatedAt": "2026-07-13T10:00:00+00:00",
    }
    execute_upsert_layer_mysql(layer_cursor, layer)
    layer_sql = "\n".join(call[0] for call in layer_cursor.calls)
    assert "INSERT INTO map_layers" in layer_sql
    assert "map_layer_block_links" in layer_sql
    assert "map_layer_right_links" in layer_sql
    assert "linked_block_codes" not in layer_cursor.calls[0][0]


def test_mysql_business_attribute_backfill_projects_existing_records_without_rewriting_ledgers():
    from server.modules.business import backfill_business_attribute_rows

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))

    cursor = RecordingCursor()
    report = backfill_business_attribute_rows(
        cursor,
        [
            (
                "farmer-existing-1",
                "farmers",
                '{"townVillage":"小桥镇上屯村","managedAreaMu":195}',
                "2026-07-15T10:00:00+00:00",
            ),
            (
                "trade-existing-1",
                "trade-matches",
                '{"tradeType":"supply","quantity":12.5,"matchStatus":"matched"}',
                "2026-07-15T10:00:00+00:00",
            ),
        ],
    )
    sql = "\n".join(call[0] for call in cursor.calls)

    assert report == {"recordsProcessed": 2, "attributesWritten": 5, "unknownModules": []}
    assert "DELETE FROM business_record_attributes" in sql
    assert "INSERT INTO business_record_attributes" in sql
    assert "UPDATE business_records" not in sql


def test_mysql_business_attribute_backfill_is_part_of_production_verification():
    script = read_text("server/scripts/backfill_mysql_business_attributes.py")
    production_script = read_text("scripts/verify-production.ps1")

    assert "backfill_business_attribute_rows" in script
    assert "fetchmany" in script
    assert "backfill_mysql_business_attributes.py" in production_script

def test_mysql_role_and_user_upserts_normalize_permission_relations():
    from server.modules.admin_roles import execute_upsert_role_mysql
    from server.modules.admin_users import execute_upsert_user_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((sql, tuple(params)))

        def executemany(self, sql, params):
            for item in params:
                self.calls.append((sql, tuple(item)))

    role_cursor = RecordingCursor()
    role = {
        "id": "55555555-5555-5555-5555-555555555555",
        "roleCode": "forest-manager",
        "name": "林业管理员",
        "status": "active",
        "permissions": ["forest.blocks.view", "forest.blocks.update"],
        "menuModules": ["blocks", "rights"],
        "dataScopes": {"areas": ["350703"]},
        "properties": {},
        "createdAt": "2026-07-13T10:00:00+00:00",
        "updatedAt": "2026-07-13T10:00:00+00:00",
    }
    execute_upsert_role_mysql(role_cursor, role)
    role_sql = "\n".join(call[0] for call in role_cursor.calls)
    assert "INSERT INTO admin_roles" in role_sql
    assert "admin_role_permissions" in role_sql
    assert "admin_role_menu_modules" in role_sql
    assert "permissions" not in role_cursor.calls[0][0]
    assert "menu_modules" not in role_cursor.calls[0][0]

    user_cursor = RecordingCursor()
    user = {
        "id": "66666666-6666-6666-6666-666666666666",
        "username": "zhushan-admin",
        "displayName": "竹山管理员",
        "status": "active",
        "roles": ["forest-manager"],
        "dataScopes": {"areas": ["350703"]},
        "properties": {},
        "createdAt": "2026-07-13T10:00:00+00:00",
        "updatedAt": "2026-07-13T10:00:00+00:00",
    }
    execute_upsert_user_mysql(user_cursor, user)
    user_sql = "\n".join(call[0] for call in user_cursor.calls)
    assert "INSERT INTO admin_users" in user_sql
    assert "admin_user_roles" in user_sql
    assert "FROM admin_roles" in user_sql
    assert "roles" not in user_cursor.calls[0][0]


def test_mysql_import_batch_upsert_indexes_workflow_and_target_links():
    from server.modules.imports import upsert_import_report_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((sql, tuple(params)))

    class RecordingConnection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            cursor = self.cursor_instance

            class CursorContext:
                def __enter__(self):
                    return cursor

                def __exit__(self, *args):
                    return False

            return CursorContext()

        def commit(self):
            self.committed = True

    connection = RecordingConnection()
    report = {
        "id": "77777777-7777-7777-7777-777777777777",
        "fileName": "blocks.kmz",
        "fileType": "kmz",
        "status": "completed",
        "totalRows": 2,
        "validRows": 2,
        "invalidRows": 0,
        "reviewStatus": "approved",
        "acceptanceStatus": "accepted",
        "qualityStatus": "passed",
        "publishRiskStatus": "clear",
        "importedBlocks": [{"blockCode": "MYSQL-BLOCK-001", "action": "created"}],
        "importedRightsArchives": [{"archiveCode": "RIGHT-MYSQL-001"}],
        "imageryLinks": [{"sceneId": "scene-001"}],
        "auditEvents": [{"eventId": "audit-1", "action": "create", "actor": "alice", "at": "2026-07-13T10:00:00+00:00"}],
        "reviewEvents": [{"eventId": "review-1", "action": "approve", "status": "approved", "actor": "reviewer", "at": "2026-07-13T10:02:00+00:00"}],
        "acceptanceEvents": [{"eventId": "accept-1", "action": "accept", "status": "accepted", "actor": "owner", "at": "2026-07-13T10:03:00+00:00"}],
        "qualityIssueEvents": [{"eventId": "quality-1", "action": "resolve", "status": "resolved", "actor": "qa", "at": "2026-07-13T10:04:00+00:00"}],
        "createdAt": "2026-07-13T10:00:00+00:00",
        "completedAt": "2026-07-13T10:01:00+00:00",
    }

    upsert_import_report_mysql(report, connection_factory=lambda: connection)

    sql = "\n".join(call[0] for call in connection.cursor_instance.calls)
    assert connection.committed is True
    assert "INSERT INTO import_batches" in sql
    assert "review_status" in sql
    assert "acceptance_status" in sql
    assert "quality_status" in sql
    assert "publish_risk_status" in sql
    assert "import_batch_block_links" in sql
    assert "import_batch_right_links" in sql
    assert "import_batch_scene_links" in sql
    assert "DELETE FROM import_batch_events" in sql
    assert "INSERT INTO import_batch_events" in sql

    batch_insert = next(
        params
        for sql, params in connection.cursor_instance.calls
        if "INSERT INTO import_batches" in sql
    )
    stored_report = json.loads(batch_insert[12])
    assert "importedBlocks" not in stored_report
    assert "importedRightsArchives" not in stored_report
    assert stored_report["importedBlockCount"] == 1
    assert stored_report["importedRightsArchiveCount"] == 1

    block_link_insert = next(
        params
        for sql, params in connection.cursor_instance.calls
        if "INSERT IGNORE INTO import_batch_block_links" in sql
    )
    right_link_insert = next(
        params
        for sql, params in connection.cursor_instance.calls
        if "INSERT IGNORE INTO import_batch_right_links" in sql
    )
    assert json.loads(block_link_insert[-1])["blockCode"] == "MYSQL-BLOCK-001"
    assert json.loads(right_link_insert[-1])["archiveCode"] == "RIGHT-MYSQL-001"


def test_mysql_import_summary_update_preserves_existing_target_relations(monkeypatch):
    from server.modules import imports

    class Cursor:
        def __init__(self):
            self.calls: list[str] = []

        def execute(self, sql, params=()):
            self.calls.append(" ".join(sql.split()))

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            cursor = self.cursor_instance

            class CursorContext:
                def __enter__(self):
                    return cursor

                def __exit__(self, *args):
                    return False

            return CursorContext()

        def commit(self):
            return None

    connection = Connection()
    monkeypatch.setattr(
        imports,
        "sync_import_batch_target_links_mysql",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("summary update must preserve target links")
        ),
    )

    imports.upsert_import_report_mysql(
        {
            "id": "batch-summary-only",
            "fileName": "summary.kmz",
            "fileType": "kmz",
            "status": "completed",
            "_targetsLoaded": False,
            "reviewStatus": "approved",
        },
        connection_factory=lambda: connection,
    )

    sql = "\n".join(connection.cursor_instance.calls)
    assert "INSERT INTO import_batches" in sql
    assert "DELETE FROM import_batch_block_links" not in sql
    assert "DELETE FROM import_batch_right_links" not in sql


def test_mysql_import_batch_list_strips_legacy_large_target_arrays(monkeypatch):
    from server.modules import imports

    class RecordingCursor:
        def __init__(self):
            self.sql = ""

        def execute(self, sql, params=()):
            self.sql = " ".join(sql.split())

        def fetchall(self):
            return []

    class RecordingConnection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            cursor = self.cursor_instance

            class CursorContext:
                def __enter__(self):
                    return cursor

                def __exit__(self, *args):
                    return False

            return CursorContext()

    connection = RecordingConnection()
    monkeypatch.setattr(imports, "mysql_connect", lambda: connection)

    imports.list_import_reports_mysql(imports.ImportBatchFilters())

    assert "JSON_REMOVE(report_json, '$.importedBlocks', '$.importedRightsArchives') AS report_json" in connection.cursor_instance.sql


def test_mysql_import_batch_detail_rehydrates_relational_targets(monkeypatch):
    from server.modules import imports

    report_json = json.dumps(
        {
            "id": "batch-relational-targets",
            "fileName": "blocks.kmz",
            "targetsStorage": "relational",
            "importedBlockCount": 1,
            "importedRightsArchiveCount": 1,
        },
        ensure_ascii=False,
    )

    class SequencedCursor:
        def __init__(self):
            self.stage = "report"

        def execute(self, sql, params=()):
            if "import_batch_block_links" in sql:
                self.stage = "blocks"
            elif "import_batch_right_links" in sql:
                self.stage = "rights"

        def fetchone(self):
            return (
                "batch-relational-targets",
                "blocks.kmz",
                "kmz",
                "completed",
                1,
                1,
                0,
                "admin",
                report_json,
                None,
                None,
            )

        def fetchall(self):
            if self.stage == "blocks":
                return [
                    (
                        json.dumps(
                            {
                                "blockCode": "BLOCK-001",
                                "name": "第一林班",
                                "action": "created",
                                "row": 7,
                            },
                            ensure_ascii=False,
                        ),
                        "BLOCK-001",
                        "第一林班",
                        "created",
                    )
                ]
            return [
                (
                    json.dumps(
                        {
                            "archiveCode": "RIGHT-001",
                            "linkedBlockCodes": ["BLOCK-001"],
                        },
                        ensure_ascii=False,
                    ),
                    "RIGHT-001",
                )
            ]

    class Connection:
        def __init__(self):
            self.cursor_instance = SequencedCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            cursor = self.cursor_instance

            class CursorContext:
                def __enter__(self):
                    return cursor

                def __exit__(self, *args):
                    return False

            return CursorContext()

    monkeypatch.setattr(imports, "mysql_connect", lambda: Connection())

    report = imports.load_import_report_mysql("batch-relational-targets")

    assert report is not None
    assert report["importedBlocks"] == [
        {
            "blockCode": "BLOCK-001",
            "name": "第一林班",
            "action": "created",
            "row": 7,
        }
    ]
    assert report["importedRightsArchives"] == [
        {"archiveCode": "RIGHT-001", "linkedBlockCodes": ["BLOCK-001"]}
    ]


def test_mysql_import_batch_scope_is_filtered_by_relational_block_indexes(monkeypatch):
    from server.modules import imports
    from server.modules.auth import AuthContext

    context = AuthContext(
        user="town-reviewer",
        roles={"import-reviewer"},
        projects={"*"},
        areas={"350703"},
    )
    monkeypatch.setattr(imports, "has_effective_area_scope", lambda _context: True)
    monkeypatch.setattr(imports, "effective_areas", lambda _context: {"350703"})
    monkeypatch.setattr(
        imports,
        "effective_data_scope_values",
        lambda _context, key: {"350703101"} if key == "towns" else set(),
    )

    where_sql, params = imports.mysql_import_filter_sql(
        imports.ImportBatchFilters(q="BLOCK-001"),
        context,
    )

    assert "FROM import_batch_block_links scope_links" in where_sql
    assert "JOIN forest_blocks scope_blocks" in where_sql
    assert "scope_blocks.county_code IN (%s)" in where_sql
    assert "scope_blocks.town_code IN (%s)" in where_sql
    assert "search_blocks.block_code LIKE %s" in where_sql
    assert params.count("350703") == 1
    assert params.count("350703101") == 1
    assert params.count("%BLOCK-001%") >= 1


def test_mysql_import_batch_targets_are_paginated_in_relational_tables(monkeypatch):
    from server.modules import imports

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))

        def fetchone(self):
            return (3,)

        def fetchall(self):
            return [
                (
                    json.dumps(
                        {"blockCode": "BLOCK-002", "action": "created", "row": 2},
                        ensure_ascii=False,
                    ),
                    "BLOCK-002",
                    "第二林班",
                    "created",
                )
            ]

    class Connection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            cursor = self.cursor_instance

            class CursorContext:
                def __enter__(self):
                    return cursor

                def __exit__(self, *args):
                    return False

            return CursorContext()

    connection = Connection()
    monkeypatch.setattr(imports, "mysql_connect", lambda: connection)

    payload = imports.list_import_batch_targets_mysql(
        "batch-target-page",
        kind="blocks",
        q="BLOCK",
        limit=1,
        offset=1,
    )

    assert payload == {
        "kind": "blocks",
        "items": [{"blockCode": "BLOCK-002", "action": "created", "row": 2, "name": "第二林班"}],
        "total": 3,
        "limit": 1,
        "offset": 1,
    }
    assert "COUNT(*) FROM import_batch_block_links" in connection.cursor_instance.calls[0][0]
    assert "LIMIT %s OFFSET %s" in connection.cursor_instance.calls[1][0]
    assert connection.cursor_instance.calls[1][1][-2:] == (1, 1)


def test_mysql_import_rollback_updates_only_batch_targets_without_loading_full_ledger(monkeypatch):
    from server.modules import imports

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))

        def fetchall(self):
            return [
                ("block-id-1", "ROLLBACK-001", "batch-rollback", None),
                ("block-id-2", "ROLLBACK-002", "another-batch", None),
            ]

        def fetchone(self):
            return (1, 2)

    class Connection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            cursor = self.cursor_instance

            class CursorContext:
                def __enter__(self):
                    return cursor

                def __exit__(self, *args):
                    return False

            return CursorContext()

        def commit(self):
            self.committed = True

    connection = Connection()
    saved: list[dict] = []
    monkeypatch.setattr(imports, "use_mysql", lambda: True)
    monkeypatch.setattr(imports, "mysql_connect", lambda: connection)
    monkeypatch.setattr(
        imports,
        "load_all_blocks",
        lambda: (_ for _ in ()).throw(AssertionError("full ledger must not be loaded")),
    )
    monkeypatch.setattr(imports, "save_import_report", saved.append)
    report = {"id": "batch-rollback", "status": "completed", "auditEvents": []}

    rolled_back = imports.rollback_import_batch_records(report, actor="reviewer")

    sql = "\n".join(call[0] for call in connection.cursor_instance.calls)
    assert connection.committed is True
    assert "FROM import_batch_block_links links" in sql
    assert "FOR UPDATE" in sql
    assert "UPDATE forest_blocks SET deleted_at" in sql
    assert rolled_back["rolledBackBlocks"] == [
        {"blockCode": "ROLLBACK-001", "action": "soft_deleted"}
    ]
    assert rolled_back["rollbackSkippedBlocks"] == [
        {"blockCode": "ROLLBACK-002", "reason": "source_batch_mismatch"}
    ]
    assert rolled_back["rollbackSummary"]["updatedRowsRequireManualReview"] == 1
    assert rolled_back["rollbackSummary"]["skippedRowsIgnored"] == 2
    assert saved == [rolled_back]


def test_mysql_import_target_links_are_written_in_bounded_batches():
    from server.modules.imports import sync_import_batch_target_links_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))

    cursor = RecordingCursor()
    report = {
        "id": "batch-large-links",
        "importedBlocks": [
            {"blockCode": f"BLOCK-{index:05d}", "action": "created"}
            for index in range(1201)
        ],
        "importedRightsArchives": [
            {"archiveCode": f"RIGHT-{index:05d}"}
            for index in range(501)
        ],
    }

    sync_import_batch_target_links_mysql(cursor, report, batch_size=500)

    block_inserts = [call for call in cursor.calls if "INSERT IGNORE INTO import_batch_block_links" in call[0]]
    right_inserts = [call for call in cursor.calls if "INSERT IGNORE INTO import_batch_right_links" in call[0]]
    assert len(block_inserts) == 3
    assert len(right_inserts) == 2
    assert all("UNION ALL" in sql for sql, _params in block_inserts[:2])
    assert all(len(params) <= 1501 for _sql, params in block_inserts)
    assert all(len(params) <= 1001 for _sql, params in right_inserts)


def test_mysql_forest_scene_link_uses_relational_table():
    from server.modules.forest_scene_links import upsert_scene_link_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((sql, tuple(params)))

    cursor = RecordingCursor()
    upsert_scene_link_mysql(
        cursor,
        {
            "forestBlockId": "11111111-1111-1111-1111-111111111111",
            "sceneId": "scene-001",
            "relationType": "coverage",
            "capturedAt": "2026-07-13T10:00:00+00:00",
            "confidence": 0.95,
        },
    )

    assert len(cursor.calls) == 1
    assert "INSERT INTO forest_block_scene_links" in cursor.calls[0][0]
    assert "ON DUPLICATE KEY UPDATE" in cursor.calls[0][0]


def test_mysql_scene_link_migration_batches_history_in_one_transaction():
    from server.modules.forest_scene_links import save_scene_links_mysql_batch

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, list[tuple]]] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def executemany(self, sql, params):
            self.calls.append((" ".join(sql.split()), list(params)))

    class RecordingConnection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.commits += 1

    connection = RecordingConnection()
    records = [
        {
            "forestBlockId": f"block-{index}",
            "sceneId": "scene-001",
            "relationType": "coverage",
            "capturedAt": "2026-07-15T00:00:00+00:00",
            "confidence": 0.9,
        }
        for index in range(1201)
    ]

    save_scene_links_mysql_batch(
        records,
        batch_size=500,
        connection_factory=lambda: connection,
    )

    assert connection.commits == 1
    assert [len(params) for _sql, params in connection.cursor_instance.calls] == [500, 500, 201]
    assert all("ON DUPLICATE KEY UPDATE" in sql for sql, _params in connection.cursor_instance.calls)


def test_mysql_import_batch_scene_links_are_written_with_one_relational_statement():
    from server.modules.forest_scene_links import save_import_batch_scene_links_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []
            self.rowcount = 1200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))

    class RecordingConnection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.commits += 1

    connection = RecordingConnection()

    linked = save_import_batch_scene_links_mysql(
        "batch-001",
        scene_id="scene-001",
        relation_type="coverage",
        captured_at="2026-07-15T10:00:00+00:00",
        confidence=0.96,
        connection_factory=lambda: connection,
    )

    assert linked == 1200
    assert connection.commits == 1
    assert len(connection.cursor_instance.calls) == 1
    sql, params = connection.cursor_instance.calls[0]
    assert "INSERT INTO forest_block_scene_links" in sql
    assert "SELECT links.forest_block_id" in sql
    assert "FROM import_batch_block_links links" in sql
    assert "JOIN forest_blocks blocks" in sql
    assert "links.import_action IN ('created', 'updated')" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert params[0:2] == ("scene-001", "coverage")
    assert params[2].isoformat(sep=" ") == "2026-07-15 10:00:00"
    assert params[3] == 0.96
    assert params[-1] == "batch-001"


def test_mysql_import_layer_links_copy_relations_without_large_in_clause():
    from server.modules.business import upsert_import_batch_layer_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))

    class RecordingConnection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.commits += 1

    connection = RecordingConnection()
    layer = {
        "id": "layer-001",
        "recordCode": "IMPORT-LAYER-batch-001",
        "name": "Import layer",
        "status": "published",
        "layerType": "imagery",
        "dataSource": "scene:scene-001",
        "style": {"type": "raster"},
        "visibleOnDashboard": True,
        "properties": {"importBatchId": "batch-001", "linkedBlockCount": 1200},
        "createdAt": "2026-07-15T10:00:00+00:00",
        "updatedAt": "2026-07-15T10:00:00+00:00",
    }

    upsert_import_batch_layer_mysql(
        layer,
        import_batch_id="batch-001",
        connection_factory=lambda: connection,
    )

    sql_calls = [sql for sql, _params in connection.cursor_instance.calls]
    assert connection.commits == 1
    assert any("INSERT INTO map_layers" in sql for sql in sql_calls)
    assert any("FROM import_batch_block_links links" in sql for sql in sql_calls)
    assert any("FROM import_batch_right_links links" in sql for sql in sql_calls)
    assert not any("block_code IN (" in sql for sql in sql_calls)
    assert not any("archive_code IN (" in sql for sql in sql_calls)


def test_mysql_manual_layer_relation_sync_batches_large_code_lists():
    from server.modules.business import sync_layer_links_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))

    cursor = RecordingCursor()
    sync_layer_links_mysql(
        cursor,
        {
            "id": "layer-001",
            "linkedBlockCodes": [f"BLOCK-{index:05d}" for index in range(1201)],
            "linkedRightArchiveCodes": [f"RIGHT-{index:05d}" for index in range(501)],
        },
        batch_size=500,
    )

    block_calls = [call for call in cursor.calls if "block_code IN" in call[0]]
    right_calls = [call for call in cursor.calls if "archive_code IN" in call[0]]
    assert len(block_calls) == 3
    assert len(right_calls) == 2
    assert all(len(params) <= 501 for _sql, params in block_calls)
    assert all(len(params) <= 501 for _sql, params in right_calls)


def test_mysql_business_relation_sync_batches_large_code_lists():
    from server.modules.business import sync_business_links_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))

    cursor = RecordingCursor()
    sync_business_links_mysql(
        cursor,
        {
            "id": "farmer-001",
            "linkedBlockCodes": [f"BLOCK-{index:05d}" for index in range(1201)],
            "linkedRightArchiveCodes": [f"RIGHT-{index:05d}" for index in range(501)],
        },
        batch_size=500,
    )

    block_calls = [call for call in cursor.calls if "block_code IN" in call[0]]
    right_calls = [call for call in cursor.calls if "archive_code IN" in call[0]]
    assert len(block_calls) == 3
    assert len(right_calls) == 2
    assert all(len(params) <= 501 for _sql, params in block_calls)
    assert all(len(params) <= 501 for _sql, params in right_calls)


def test_mysql_forest_right_relation_sync_batches_large_block_lists():
    from server.modules.forest_rights import sync_right_links_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))

    cursor = RecordingCursor()
    sync_right_links_mysql(
        cursor,
        {
            "id": "right-001",
            "updatedAt": "2026-07-16T00:00:00+00:00",
            "linkedBlockIds": [f"block-id-{index:05d}" for index in range(501)],
            "linkedBlockCodes": [f"BLOCK-{index:05d}" for index in range(1201)],
        },
        batch_size=500,
    )

    id_calls = [call for call in cursor.calls if "WHERE id IN" in call[0]]
    code_calls = [call for call in cursor.calls if "WHERE block_code IN" in call[0]]
    assert len(id_calls) == 2
    assert len(code_calls) == 3
    assert all(len(params) <= 502 for _sql, params in [*id_calls, *code_calls])


def test_mysql_import_scene_plan_uses_aggregate_counts_and_bounded_samples():
    from server.modules.imports import mysql_import_batch_scene_plan

    responses = [
        (1200, 1200, 0, 3, 2),
        [("block-id-1", "BLOCK-0001"), ("block-id-2", "BLOCK-0002")],
        [],
        [("BLOCK-0011",), ("BLOCK-0012",)],
        [("BLOCK-0021",), ("BLOCK-0022",)],
        (501,),
        [("RIGHT-0001",), ("RIGHT-0002",)],
    ]

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []
            self.response_index = -1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), tuple(params)))
            self.response_index += 1

        def fetchone(self):
            return responses[self.response_index]

        def fetchall(self):
            return responses[self.response_index]

    class RecordingConnection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

    connection = RecordingConnection()
    plan = mysql_import_batch_scene_plan(
        "batch-001",
        {"bounds": [117.0, 26.0, 118.0, 27.0]},
        sample_limit=100,
        connection_factory=lambda: connection,
    )

    assert plan["targetCount"] == 1200
    assert plan["linkedBlockCount"] == 1200
    assert plan["linkedRightArchiveCount"] == 501
    assert plan["targetsTruncated"] is True
    assert len(plan["linkedBlocks"]) == 2
    assert plan["coverageCheck"]["missingGeometryCount"] == 3
    assert plan["coverageCheck"]["outsideSceneBoundsCount"] == 2
    assert plan["coverageCheck"]["targetsTruncated"] is True
    assert plan["coverageCheck"]["warnings"] == ["missing_geometry", "outside_scene_bounds"]
    assert len(connection.cursor_instance.calls) == 7
    assert "ST_AsGeoJSON" not in " ".join(sql for sql, _params in connection.cursor_instance.calls)
    sample_calls = [
        (sql, params)
        for sql, params in connection.cursor_instance.calls
        if "LIMIT %s" in sql
    ]
    assert sample_calls
    assert all(params[-1] == 100 for _sql, params in sample_calls)


def test_mysql_scene_publish_endpoints_load_compact_batch_summaries():
    source = read_text("server/modules/imports.py")

    assert source.count("get_report_or_404(batch_id, include_targets=not use_mysql())") >= 2
    assert "save_import_batch_scene_links_mysql(" in source
    assert "mysql_import_batch_scene_plan(" in source


def test_mysql_map_layer_lists_use_counts_instead_of_full_target_arrays():
    from server.modules.business import MYSQL_LAYER_SUMMARY_SELECT_SQL

    normalized = " ".join(MYSQL_LAYER_SUMMARY_SELECT_SQL.split())
    assert "JSON_ARRAYAGG" not in normalized
    assert "FROM map_layer_block_links" in normalized
    assert "FROM map_layer_right_links" in normalized
    assert "$.linkedBlockCount" in normalized
    assert "$.linkedRightArchiveCount" in normalized
    assert "$.linkedTargetsTruncated" in normalized


def test_mysql_business_lists_use_counts_instead_of_full_target_arrays():
    from server.modules.business import MYSQL_BUSINESS_SUMMARY_SELECT_SQL

    normalized = " ".join(MYSQL_BUSINESS_SUMMARY_SELECT_SQL.split())
    assert "JSON_ARRAYAGG" not in normalized
    assert "FROM business_record_block_links" in normalized
    assert "FROM business_record_right_links" in normalized
    assert "linkedBlockCount" in normalized
    assert "linkedRightArchiveCount" in normalized
    assert "$.linkedTargetsTruncated" in normalized


def test_business_targets_have_a_paginated_relational_api():
    source = read_text("server/modules/business.py")

    assert '@router.get("/business/{module_key}/{record_id}/targets")' in source
    assert "def list_business_record_targets_mysql(" in source
    assert 'kind not in {"blocks", "rights"}' in source


def test_map_layer_targets_have_a_paginated_relational_api():
    source = read_text("server/modules/business.py")

    assert '@router.get("/map-layers/{record_id}/targets")' in source
    assert "def list_map_layer_targets_mysql(" in source
    assert "COUNT(*)" in source
    assert "LIMIT %s OFFSET %s" in source


def test_mysql_map_layer_metadata_update_preserves_existing_relations():
    from server.modules.business import upsert_layer_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=()):
            self.calls.append(" ".join(sql.split()))

    class RecordingConnection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.commits += 1

    connection = RecordingConnection()
    upsert_layer_mysql(
        {
            "id": "layer-001",
            "recordCode": "LAYER-001",
            "name": "Layer",
            "status": "paused",
            "style": {},
            "visibleOnDashboard": False,
            "properties": {},
            "createdAt": "2026-07-15T00:00:00+00:00",
            "updatedAt": "2026-07-15T01:00:00+00:00",
        },
        sync_links=False,
        connection_factory=lambda: connection,
    )

    assert connection.commits == 1
    assert len(connection.cursor_instance.calls) == 1
    assert "INSERT INTO map_layers" in connection.cursor_instance.calls[0]
    assert "map_layer_block_links" not in connection.cursor_instance.calls[0]
    assert "map_layer_right_links" not in connection.cursor_instance.calls[0]


def test_mysql_business_metadata_update_preserves_existing_relations():
    from server.modules.business import upsert_business_record_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=()):
            self.calls.append(" ".join(sql.split()))

    class RecordingConnection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.commits += 1

    connection = RecordingConnection()
    upsert_business_record_mysql(
        "farmers",
        {
            "id": "farmer-001",
            "recordCode": "FARMER-001",
            "name": "Farmer",
            "status": "active",
            "properties": {},
            "createdAt": "2026-07-15T00:00:00+00:00",
            "updatedAt": "2026-07-15T01:00:00+00:00",
        },
        sync_links=False,
        connection_factory=lambda: connection,
    )

    sql = " ".join(connection.cursor_instance.calls)
    assert connection.commits == 1
    assert "INSERT INTO business_records" in sql
    assert "business_record_block_links" not in sql
    assert "business_record_right_links" not in sql


def test_mysql_business_dashboard_summary_uses_database_aggregates():
    from server.modules.business import mysql_business_dashboard_summary

    class DashboardCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []
            self.last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            self.last_sql = " ".join(sql.split())
            self.calls.append((self.last_sql, tuple(params)))

        def fetchone(self):
            if "COUNT(DISTINCT links.forest_block_id)" in self.last_sql:
                return (950,)
            if "business_record_attributes bra" in self.last_sql:
                return (700,)
            return (1200,)

        def fetchall(self):
            return [("memberCount", 345678.5, 288.0654)]

    class DashboardConnection:
        def __init__(self):
            self.cursor_instance = DashboardCursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

    connection = DashboardConnection()
    summary = mysql_business_dashboard_summary("cooperatives", connection_factory=lambda: connection)

    sql = "\n".join(call[0] for call in connection.cursor_instance.calls)
    assert summary == {
        "total": 1200,
        "linkedBlockCount": 950,
        "activeCount": 700,
        "aggregates": {"memberCount": 345678.5},
    }
    assert "COUNT(DISTINCT links.forest_block_id)" in sql
    assert "business_record_attributes" in sql
    assert "JSON_ARRAYAGG" not in sql


def test_mysql_business_dashboard_is_bounded_and_uses_relation_counts():
    from server.modules.business import BUSINESS_DASHBOARD_ROW_LIMIT, dashboard_payload

    record = {
        "recordCode": "FARMER-LARGE-001",
        "name": "Large farmer",
        "status": "active",
        "linkedBlockCodes": [],
        "properties": {"linkedBlockCount": 1200, "townVillage": "Masha"},
    }
    payload = dashboard_payload(
        "farmers",
        [record],
        summary={
            "total": 2000,
            "linkedBlockCount": 1500,
            "activeCount": 1800,
            "aggregates": {"managedAreaMu": 1000000},
        },
    )

    assert BUSINESS_DASHBOARD_ROW_LIMIT == 100
    assert payload["metrics"][0][1] == "2000 户"
    assert payload["metrics"][1][1] == "1500 个"
    assert payload["metrics"][2][1] == "1800"
    assert payload["rows"][0][2] == "已关联 1200 个林班"
    assert payload["rowLimit"] == 100
    assert payload["rowsTruncated"] is True


def test_mysql_dashboard_routes_never_load_full_business_ledgers(monkeypatch):
    from server.modules import business

    monkeypatch.setattr(business, "use_mysql", lambda: True)
    monkeypatch.setattr(
        business,
        "business_records",
        lambda _module_key: (_ for _ in ()).throw(AssertionError("full ledger load is forbidden")),
    )

    def fake_dashboard(module_key):
        return {
            "module": module_key,
            "title": module_key,
            "subtitle": "",
            "metrics": [["total", "1200 items"], ["linked", "950 blocks"], ["active", "700"]],
            "columns": ["name", "type", "linked", "status"],
            "rows": [[f"{module_key}-sample", "type", "已关联 950 个林班", "active"]],
            "adminLinks": [],
        }

    monkeypatch.setattr(business, "mysql_business_dashboard_payload", fake_dashboard)

    module_payload = business.get_business_dashboard("farmers")
    industry_payload = business.industry_platform_dashboard_payload()

    assert module_payload["metrics"][0][1] == "1200 items"
    assert industry_payload["metrics"][1][1].startswith(str(1200 * len(business.INDUSTRY_PLATFORM_MODULES)))
    assert len(industry_payload["rows"]) == len(business.INDUSTRY_PLATFORM_MODULES)


def test_mysql_detail_routes_return_relation_summaries_instead_of_full_arrays(monkeypatch):
    from server.modules import business
    from server.modules.auth import AuthContext

    context = AuthContext(user="tester", roles={"admin"}, projects=set(), areas=set())
    layer_calls: list[dict] = []
    business_calls: list[dict] = []
    monkeypatch.setattr(business, "use_mysql", lambda: True)
    monkeypatch.setattr(
        business,
        "fetch_layers_mysql",
        lambda **kwargs: layer_calls.append(kwargs) or [
            {
                "id": "layer-001",
                "recordCode": "LAYER-001",
                "name": "Layer",
                "status": "published",
                "linkedBlockCodes": [],
                "linkedRightArchiveCodes": [],
                "properties": {"linkedBlockCount": 1000000},
                "createdAt": "2026-07-16T00:00:00+00:00",
                "updatedAt": "2026-07-16T00:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        business,
        "fetch_business_records_mysql",
        lambda module_key, **kwargs: business_calls.append({"module_key": module_key, **kwargs}) or [
            {
                "id": "farmer-001",
                "recordCode": "FARMER-001",
                "name": "Farmer",
                "status": "active",
                "linkedBlockCodes": [],
                "linkedRightArchiveCodes": [],
                "properties": {"linkedBlockCount": 1000000},
                "createdAt": "2026-07-16T00:00:00+00:00",
                "updatedAt": "2026-07-16T00:00:00+00:00",
            }
        ],
    )

    layer = business.get_map_layer("layer-001", context=context)
    farmer = business.get_business_record("farmers", "farmer-001", context=context)

    assert layer.properties["linkedBlockCount"] == 1000000
    assert farmer.properties["linkedBlockCount"] == 1000000
    assert layer_calls == [{"layer_id": "layer-001", "limit": 1, "include_targets": False}]
    assert business_calls == [
        {"module_key": "farmers", "record_id": "farmer-001", "limit": 1, "include_targets": False}
    ]


def test_mysql_forest_right_lists_use_counts_instead_of_full_block_arrays():
    from server.modules.forest_rights import MYSQL_SUMMARY_SELECT_SQL

    normalized = " ".join(MYSQL_SUMMARY_SELECT_SQL.split())
    assert "JSON_ARRAYAGG" not in normalized
    assert "FROM forest_right_block_links" in normalized
    assert "linkedBlockCount" in normalized
    assert "linkedTargetsTruncated" in normalized


def test_forest_right_block_targets_have_a_paginated_relational_api():
    source = read_text("server/modules/forest_rights.py")

    assert '@router.get("/forest-rights/{right_id}/targets")' in source
    assert "def list_right_block_targets_mysql(" in source
    assert "LIMIT %s OFFSET %s" in source


def test_mysql_forest_right_metadata_update_preserves_existing_block_links():
    from server.modules.forest_rights import upsert_right_mysql

    class RecordingCursor:
        def __init__(self):
            self.calls: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=()):
            self.calls.append(" ".join(sql.split()))

    class RecordingConnection:
        def __init__(self):
            self.cursor_instance = RecordingCursor()
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.commits += 1

    connection = RecordingConnection()
    upsert_right_mysql(
        {
            "id": "right-001",
            "archiveCode": "RIGHT-001",
            "holder": "Holder",
            "archiveStatus": "complete",
            "properties": {},
            "createdAt": "2026-07-16T00:00:00+00:00",
            "updatedAt": "2026-07-16T01:00:00+00:00",
        },
        sync_links=False,
        connection_factory=lambda: connection,
    )

    sql = " ".join(connection.cursor_instance.calls)
    assert connection.commits == 1
    assert "INSERT INTO forest_rights" in sql
    assert "forest_right_block_links" not in sql


def test_mysql_imagery_catalog_normalizes_scenes_geometry_and_tasks():
    from server.app import execute_mysql_scene_upsert, execute_mysql_task_upsert

    class RecordingCursor:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql, params=()):
            self.calls.append((sql, tuple(params)))

    scene_cursor = RecordingCursor()
    execute_mysql_scene_upsert(
        scene_cursor,
        {
            "id": "scene-001",
            "name": "建阳竹山影像",
            "status": "active",
            "deliveryStatus": "pending",
            "projectId": "bamboo-2026",
            "areaCode": "350703",
            "satellite": "GF-2",
            "sensor": "PMS",
            "bounds": [118.0, 26.0, 119.0, 27.0],
            "publishEvents": [{"eventId": "publish-1", "action": "publish", "actor": "alice", "at": "2026-07-13T10:01:00+00:00"}],
            "lifecycleEvents": [{"eventId": "life-1", "action": "create", "actor": "alice", "at": "2026-07-13T10:00:00+00:00"}],
            "qualityIssueEvents": [{"eventId": "quality-1", "action": "resolve", "status": "resolved", "actor": "qa", "at": "2026-07-13T10:02:00+00:00"}],
            "deliveryEvents": [{"eventId": "delivery-1", "action": "deliver", "status": "delivered", "actor": "owner", "at": "2026-07-13T10:03:00+00:00"}],
            "createdAt": "2026-07-13T10:00:00+00:00",
            "updatedAt": "2026-07-13T10:00:00+00:00",
        },
    )
    scene_sql = "\n".join(call[0] for call in scene_cursor.calls)
    assert "INSERT INTO remote_sensing_scenes" in scene_sql
    assert "INSERT INTO remote_sensing_scene_geometries" in scene_sql
    assert "ST_GeomFromText" in scene_sql
    assert "axis-order=long-lat" in scene_sql
    assert "DELETE FROM remote_sensing_scene_events" in scene_sql
    assert "INSERT INTO remote_sensing_scene_events" in scene_sql

    import inspect

    from server.app import mysql_load_scenes

    assert "axis-order=long-lat" in inspect.getsource(mysql_load_scenes)

    task_cursor = RecordingCursor()
    execute_mysql_task_upsert(
        task_cursor,
        {
            "id": "task-001",
            "status": "queued",
            "type": "cog-conversion",
            "sceneId": "scene-001",
            "events": [{"eventId": "task-event-1", "action": "queued", "status": "queued", "actor": "system", "at": "2026-07-13T10:00:00+00:00"}],
            "createdAt": "2026-07-13T10:00:00+00:00",
            "updatedAt": "2026-07-13T10:00:00+00:00",
        },
    )
    task_sql = "\n".join(call[0] for call in task_cursor.calls)
    assert "INSERT INTO remote_sensing_tasks" in task_sql
    assert "ON DUPLICATE KEY UPDATE" in task_sql
    assert "DELETE FROM remote_sensing_task_events" in task_sql
    assert "INSERT INTO remote_sensing_task_events" in task_sql


def test_mysql_event_ledgers_read_normalized_event_tables(monkeypatch):
    from server.modules import imports
    import server.app as app_module

    import_events = {"items": [{"eventId": "audit-1"}], "total": 1, "limit": 20, "offset": 0}
    monkeypatch.setattr(imports, "use_mysql", lambda: True)
    monkeypatch.setattr(imports, "context_has_import_batch_scope", lambda context: False)
    monkeypatch.setattr(imports, "list_import_audit_events_mysql", lambda **kwargs: import_events)
    assert imports.list_import_audit_events(limit=20) == import_events

    scene_events = [{"eventId": "publish-1", "sceneId": "scene-001"}]
    task_events = [{"eventId": "task-event-1", "taskId": "task-001"}]
    monkeypatch.setattr(app_module, "use_mysql_catalog", lambda: True)
    monkeypatch.setattr(app_module, "mysql_list_scene_event_records", lambda **kwargs: scene_events)
    monkeypatch.setattr(app_module, "mysql_list_task_event_records", lambda **kwargs: task_events)
    assert app_module.list_scene_event_records(scene_id="scene-001") == scene_events
    assert app_module.list_task_event_records(task_id="task-001") == task_events


def test_json_to_mysql_migration_inventory_covers_all_first_stage_datasets(tmp_path):
    from server.modules.mysql_migration import collect_json_migration_inventory

    data_dir = tmp_path / "remote-sensing"
    fixtures = {
        "forest-blocks/forest_blocks.json": [{"id": "b1", "blockCode": "B1"}],
        "forest-blocks/forest_block_versions.json": [{"id": "bv1"}],
        "forest-blocks/forest_block_scene_links.json": [{"forestBlockId": "b1", "sceneId": "s1"}],
        "forest-rights/forest_rights.json": [{"id": "r1", "archiveCode": "R1"}],
        "forest-rights/forest_right_versions.json": [{"id": "rv1"}],
        "business/farmers.json": [{"id": "f1", "recordCode": "F1"}],
        "map-layers/map_layers.json": [{"id": "l1", "recordCode": "L1"}],
        "admin/roles.json": [{"id": "role1", "roleCode": "admin"}],
        "admin/users.json": [{"id": "user1", "username": "admin"}],
        "imports/import_batches.json": [{"id": "i1", "fileName": "blocks.kmz"}],
        "catalog.json": {"scenes": [{"id": "s1"}]},
        "tasks.json": {"tasks": [{"id": "t1"}]},
    }
    for relative, payload in fixtures.items():
        path = data_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    inventory = collect_json_migration_inventory(data_dir)

    assert inventory["forestBlocks"] == 1
    assert inventory["forestBlockVersions"] == 1
    assert inventory["forestRights"] == 1
    assert inventory["forestRightVersions"] == 1
    assert inventory["mapLayers"] == 1
    assert inventory["adminRoles"] == 1
    assert inventory["adminUsers"] == 1
    assert inventory["importBatches"] == 1
    assert inventory["imageryScenes"] == 1
    assert inventory["imageryTasks"] == 1
    assert inventory["forestSceneLinks"] == 1
    assert inventory["businessModules"] == {"farmers": 1}
    assert inventory["totalRecords"] == 12


def test_json_to_mysql_migration_rejects_malformed_source_files(tmp_path):
    from server.modules.mysql_migration import collect_json_migration_inventory

    data_dir = tmp_path / "remote-sensing"
    source = data_dir / "forest-rights" / "forest_rights.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"records": [', encoding="utf-8")

    with pytest.raises(ValueError, match="forest_rights.json"):
        collect_json_migration_inventory(data_dir)


def test_json_to_mysql_migration_rejects_wrong_source_shape(tmp_path):
    from server.modules.mysql_migration import collect_json_migration_inventory

    data_dir = tmp_path / "remote-sensing"
    source = data_dir / "forest-blocks" / "forest_blocks.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"forestBlocks": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="expected a JSON list"):
        collect_json_migration_inventory(data_dir)


def test_mysql_migration_cli_supports_dry_run_and_is_documented():
    script = read_text("server/scripts/migrate_json_to_mysql.py")
    doc = read_text("docs/deploy-smart-bamboo-platform.md")

    assert "--dry-run" in script
    assert "SMART_BAMBOO_DATABASE_URL" in script
    assert "collect_json_migration_inventory" in script
    assert "migrate_json_to_mysql.py --dry-run" in doc


def test_mysql_migration_verification_reports_every_missing_dataset():
    from server.modules.mysql_migration import build_migration_verification_report

    source = {
        "forestBlocks": 3,
        "forestBlockVersions": 2,
        "forestSceneLinks": 1,
        "forestRights": 2,
        "forestRightVersions": 1,
        "mapLayers": 1,
        "adminRoles": 2,
        "adminUsers": 2,
        "importBatches": 1,
        "imageryScenes": 2,
        "imageryTasks": 1,
        "businessModules": {"farmers": 2, "cooperatives": 1},
        "totalRecords": 20,
    }
    target = {
        "forestBlocks": 2,
        "forestBlockVersions": 2,
        "forestSceneLinks": 0,
        "forestRights": 2,
        "forestRightVersions": 0,
        "mapLayers": 1,
        "adminRoles": 4,
        "adminUsers": 2,
        "importBatches": 1,
        "imageryScenes": 1,
        "imageryTasks": 1,
        "businessModules": {"farmers": 1, "cooperatives": 3},
        "totalRecords": 19,
    }

    report = build_migration_verification_report(source, target)

    assert report["status"] == "failed"
    assert report["verified"] is False
    assert report["missingRecords"] == 5
    assert report["mismatches"] == [
        {"dataset": "forestBlocks", "source": 3, "target": 2, "missing": 1},
        {"dataset": "forestRightVersions", "source": 1, "target": 0, "missing": 1},
        {"dataset": "forestSceneLinks", "source": 1, "target": 0, "missing": 1},
        {"dataset": "imageryScenes", "source": 2, "target": 1, "missing": 1},
        {"dataset": "businessModules.farmers", "source": 2, "target": 1, "missing": 1},
    ]


def test_mysql_migration_verification_allows_existing_extra_records():
    from server.modules.mysql_migration import build_migration_verification_report

    source = {
        "forestBlocks": 1,
        "forestRights": 1,
        "businessModules": {"farmers": 1},
        "totalRecords": 3,
    }
    target = {
        "forestBlocks": 4,
        "forestRights": 2,
        "businessModules": {"farmers": 3, "enterprises": 2},
        "totalRecords": 11,
    }

    report = build_migration_verification_report(source, target)

    assert report["status"] == "passed"
    assert report["verified"] is True
    assert report["missingRecords"] == 0
    assert report["mismatches"] == []


def test_mysql_migration_inventory_reads_platform_and_catalog_counts(monkeypatch):
    from server.modules import database
    from server.modules.mysql_migration import collect_mysql_migration_inventory

    platform_rows = [
        ("forestBlocks", "", 3),
        ("forestBlockVersions", "", 2),
        ("forestRights", "", 2),
        ("forestRightVersions", "", 1),
        ("forestSceneLinks", "", 1),
        ("mapLayers", "", 1),
        ("adminRoles", "", 2),
        ("adminUsers", "", 2),
        ("importBatches", "", 1),
        ("businessModules", "farmers", 2),
    ]
    catalog_rows = [
        ("imageryScenes", "", 2),
        ("imageryTasks", "", 1),
    ]
    executed_sql = []
    connected_urls = []

    class FakeCursor:
        def __init__(self, rows):
            self.rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=None):
            executed_sql.append(" ".join(sql.split()))

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __init__(self, rows):
            self.rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return FakeCursor(self.rows)

    def fake_connect(database_url=None):
        connected_urls.append(database_url)
        rows = catalog_rows if database_url == "mysql://catalog" else platform_rows
        return FakeConnection(rows)

    monkeypatch.setattr(database, "mysql_connect", fake_connect)

    inventory = collect_mysql_migration_inventory(
        platform_database_url="mysql://platform",
        catalog_database_url="mysql://catalog",
    )

    assert connected_urls == ["mysql://platform", "mysql://catalog"]
    assert inventory["forestBlocks"] == 3
    assert inventory["forestSceneLinks"] == 1
    assert inventory["businessModules"] == {"farmers": 2}
    assert inventory["imageryScenes"] == 2
    assert inventory["imageryTasks"] == 1
    assert inventory["totalRecords"] == 20
    assert "FROM business_records" in executed_sql[0]
    assert "FROM remote_sensing_scenes" in executed_sql[1]


def test_mysql_migration_cli_fails_when_post_migration_verification_fails(monkeypatch, tmp_path, capsys):
    import argparse

    from server.scripts import migrate_json_to_mysql as migration_cli

    monkeypatch.setattr(
        migration_cli,
        "parse_args",
        lambda: argparse.Namespace(
            data_dir=str(tmp_path),
            database_url="mysql://user:secret@db/smart_bamboo",
            dry_run=False,
        ),
    )
    monkeypatch.setattr(
        migration_cli,
        "migrate_json_to_mysql",
        lambda _data_dir: {
            "sourceInventory": {"forestBlocks": 2},
            "targetInventory": {"forestBlocks": 1},
            "verification": {
                "status": "failed",
                "verified": False,
                "missingRecords": 1,
                "mismatches": [
                    {"dataset": "forestBlocks", "source": 2, "target": 1, "missing": 1}
                ],
            },
        },
    )
    monkeypatch.setattr(
        migration_cli,
        "collect_json_migration_inventory",
        lambda _data_dir: {"totalRecords": 2, "businessModules": {}},
    )

    exit_code = migration_cli.main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["migrated"]["verification"]["status"] == "failed"


def test_mysql_migration_cli_refuses_an_empty_source_inventory(monkeypatch, tmp_path, capsys):
    import argparse

    from server.scripts import migrate_json_to_mysql as migration_cli

    monkeypatch.setattr(
        migration_cli,
        "parse_args",
        lambda: argparse.Namespace(
            data_dir=str(tmp_path),
            database_url="mysql://user:secret@db/smart_bamboo",
            dry_run=False,
        ),
    )
    monkeypatch.setattr(
        migration_cli,
        "collect_json_migration_inventory",
        lambda _data_dir: {"totalRecords": 0, "businessModules": {}},
    )
    migration_called = False

    def record_migration(_data_dir):
        nonlocal migration_called
        migration_called = True
        return {}

    monkeypatch.setattr(migration_cli, "migrate_json_to_mysql", record_migration)

    exit_code = migration_cli.main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 3
    assert migration_called is False
    assert output["status"] == "refused"
    assert "empty" in output["reason"].lower()


def test_mysql_migration_returns_verified_source_and_target_report(monkeypatch, tmp_path):
    from server import app as app_module
    from server.modules import admin_roles, admin_users, business, database, forest_blocks, forest_rights
    from server.modules import forest_scene_links, imports, mysql_migration

    sources = {
        "forestBlocks": [{"id": "b1"}],
        "forestBlockVersions": [],
        "forestSceneLinks": [],
        "forestRights": [{"id": "r1"}],
        "forestRightVersions": [],
        "mapLayers": [],
        "adminRoles": [],
        "adminUsers": [],
        "importBatches": [],
        "imageryScenes": [],
        "imageryTasks": [],
        "businessModules": {"farmers": [{"id": "f1"}]},
    }
    target = {
        "forestBlocks": 1,
        "forestRights": 1,
        "businessModules": {"farmers": 1},
        "totalRecords": 3,
    }
    monkeypatch.setattr(mysql_migration, "migration_sources", lambda _data_dir: sources)
    monkeypatch.setattr(mysql_migration, "collect_mysql_migration_inventory", lambda **_kwargs: target)
    monkeypatch.setattr(database, "init_platform_schema", lambda: None)
    monkeypatch.setattr(forest_blocks, "upsert_blocks_mysql", lambda _records: None)
    monkeypatch.setattr(forest_rights, "upsert_rights_mysql", lambda _records: None)
    monkeypatch.setattr(business, "upsert_layers_mysql", lambda _records: None)
    monkeypatch.setattr(business, "upsert_business_records_mysql", lambda _module, _records: None)
    monkeypatch.setattr(admin_roles, "upsert_roles_mysql", lambda _records: None)
    monkeypatch.setattr(admin_users, "upsert_users_mysql", lambda _records: None)
    monkeypatch.setattr(imports, "upsert_import_report_mysql", lambda _record: None)
    monkeypatch.setattr(forest_scene_links, "save_scene_links_mysql_batch", lambda _records: None)
    monkeypatch.setattr(app_module, "mysql_upsert_scene", lambda _record: None)
    monkeypatch.setattr(app_module, "mysql_upsert_task", lambda _record: None)

    report = mysql_migration.migrate_json_to_mysql(tmp_path)

    assert report["sourceInventory"]["forestBlocks"] == 1
    assert report["targetInventory"] == target
    assert report["verification"]["status"] == "passed"
    assert report["verification"]["verified"] is True


def test_mysql_benchmark_covers_spatial_filter_and_percentiles():
    script = read_text("server/scripts/benchmark_mysql_forest_blocks.py")
    doc = read_text("docs/deploy-smart-bamboo-platform.md")
    production_script = read_text("scripts/verify-production.ps1")

    assert "EXPLAIN ANALYZE" in script
    assert "MBRIntersects" in script
    assert "axis-order=long-lat" in script
    assert "idx_forest_block_geometry" in script
    assert "FORCE INDEX (idx_forest_block_geometry)" in script
    assert "STRAIGHT_JOIN forest_blocks" in script
    assert "idx_forest_blocks_town_active_updated" in script
    assert "idx_forest_blocks_town_active_area" in script
    assert "idx_forest_blocks_operation_active" in script
    assert '"operation-facet"' in script
    assert "idx_forest_blocks_operation" in script
    assert "p50Ms" in script
    assert "p95Ms" in script
    assert "benchmark_mysql_forest_blocks.py" in doc
    assert "--min-area-mu" in script
    assert "--max-p95-ms" in script
    assert "BenchmarkMillionAcre" in production_script
    assert "JSON_STORAGE_SIZE" in script
    assert "JSON_CONTAINS_PATH" in script
    assert "importWrite" in script
    assert "relationLink" in script
    assert "benchmark_relation_link_write" in script
    assert "INSERT INTO forest_block_scene_links" in script
    assert "INSERT IGNORE INTO map_layer_block_links" in script
    assert "--min-relation-link-rows-per-second" in script
    assert "MinimumRelationLinkRowsPerSecond" in production_script
    assert "rollback()" in script
    assert "datetime.utcnow" not in script


def test_mysql_relation_link_acceptance_rejects_slow_scene_or_layer_copy():
    from server.scripts.benchmark_mysql_forest_blocks import build_relation_link_acceptance

    accepted = build_relation_link_acceptance(
        {"sceneRowsPerSecond": 1200, "layerRowsPerSecond": 1100},
        min_rows_per_second=1000,
    )
    rejected = build_relation_link_acceptance(
        {"sceneRowsPerSecond": 900, "layerRowsPerSecond": 800},
        min_rows_per_second=1000,
    )

    assert accepted == {"passed": True, "issues": []}
    assert rejected["passed"] is False
    assert {issue["code"] for issue in rejected["issues"]} == {
        "scene_link_throughput_below_target",
        "layer_link_throughput_below_target",
    }


def test_mysql_benchmark_acceptance_requires_million_acres_indexes_and_p95_threshold():
    from server.scripts.benchmark_mysql_forest_blocks import build_benchmark_acceptance

    passing = build_benchmark_acceptance(
        dataset={"blockCount": 240000, "totalAreaMu": 1_050_000},
        results=[
            {"name": "town-ledger", "indexUsed": True, "p95Ms": 68.4},
            {"name": "bbox-map", "indexUsed": True, "p95Ms": 91.2},
        ],
        min_area_mu=1_000_000,
        max_p95_ms=500,
    )
    failing = build_benchmark_acceptance(
        dataset={"blockCount": 249, "totalAreaMu": 21_560.7},
        results=[{"name": "bbox-map", "indexUsed": False, "p95Ms": 720}],
        min_area_mu=1_000_000,
        max_p95_ms=500,
    )

    assert passing == {"passed": True, "issues": []}
    assert failing["passed"] is False
    assert {issue["code"] for issue in failing["issues"]} == {
        "dataset_area_below_target",
        "expected_index_not_used",
        "query_p95_exceeded",
    }


def test_mysql_benchmark_acceptance_rejects_json_target_duplication_and_slow_imports():
    from server.scripts.benchmark_mysql_forest_blocks import build_import_acceptance

    passing = build_import_acceptance(
        storage={"largeTargetArrayBatchCount": 0},
        import_write={"rowsPerSecond": 1250.0},
        min_rows_per_second=500,
    )
    failing = build_import_acceptance(
        storage={"largeTargetArrayBatchCount": 2},
        import_write={"rowsPerSecond": 210.0},
        min_rows_per_second=500,
    )

    assert passing == {"passed": True, "issues": []}
    assert {issue["code"] for issue in failing["issues"]} == {
        "import_targets_duplicated_in_report_json",
        "import_write_throughput_below_target",
    }
