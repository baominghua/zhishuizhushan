from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .auth_config import auth_config_digest
from .mysql_schema import PLATFORM_CORE_MYSQL_TABLES, apply_mysql_schema_upgrades, mysql_platform_schema_statements
from .settings import get_settings


JSON_STORE_LOCK = globals().get("JSON_STORE_LOCK") or threading.RLock()


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


@contextmanager
def json_transaction(paths: list[Path]):
    """Restore every participating JSON file if a multi-file update fails."""
    unique_paths = list(dict.fromkeys(paths))
    with JSON_STORE_LOCK:
        snapshots = {path: path.read_bytes() if path.exists() else None for path in unique_paths}
        try:
            yield
        except Exception:
            for path, contents in snapshots.items():
                if contents is None:
                    if path.exists():
                        path.unlink()
                        fsync_directory(path.parent)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.restore")
                try:
                    descriptor = os.open(
                        temporary,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                    )
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(contents)
                        handle.flush()
                        os.fchmod(handle.fileno(), 0o600)
                        os.fsync(handle.fileno())
                    os.replace(temporary, path)
                    fsync_directory(path.parent)
                finally:
                    if temporary.exists():
                        temporary.unlink()
            raise


def get_data_dir() -> Path:
    data_dir = get_settings().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "forest-blocks").mkdir(parents=True, exist_ok=True)
    (data_dir / "forest-subcompartments").mkdir(parents=True, exist_ok=True)
    (data_dir / "resource-surveys").mkdir(parents=True, exist_ok=True)
    (data_dir / "attachments" / "objects").mkdir(parents=True, exist_ok=True)
    (data_dir / "forest-rights").mkdir(parents=True, exist_ok=True)
    (data_dir / "business").mkdir(parents=True, exist_ok=True)
    (data_dir / "map-layers").mkdir(parents=True, exist_ok=True)
    (data_dir / "admin").mkdir(parents=True, exist_ok=True)
    (data_dir / "imports").mkdir(parents=True, exist_ok=True)
    (data_dir / "harvest").mkdir(parents=True, exist_ok=True)
    (data_dir / "safety").mkdir(parents=True, exist_ok=True)
    (data_dir / "iot").mkdir(parents=True, exist_ok=True)
    (data_dir / "drone").mkdir(parents=True, exist_ok=True)
    (data_dir / "ai").mkdir(parents=True, exist_ok=True)
    (data_dir / "mobile" / "evidence").mkdir(parents=True, exist_ok=True)
    return data_dir


def use_postgis() -> bool:
    settings = get_settings()
    return settings.storage_backend == "postgis" and bool(settings.database_url)


def use_mysql() -> bool:
    settings = get_settings()
    return settings.storage_backend == "mysql" and bool(settings.database_url)


def mysql_connection_kwargs(database_url: str | None = None) -> dict[str, Any]:
    url = (database_url or get_settings().database_url).replace("mysql+pymysql://", "mysql://", 1)
    parsed = urlparse(url)
    if parsed.scheme != "mysql" or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("SMART_BAMBOO_DATABASE_URL must be a mysql:// URL with host and database")
    query = parse_qs(parsed.query)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": unquote(parsed.path.strip("/")),
        "charset": str(query.get("charset", ["utf8mb4"])[0]),
        "autocommit": False,
    }


def mysql_connect(database_url: str | None = None):
    try:
        import pymysql
    except Exception as exc:
        raise RuntimeError(f"MySQL storage requires PyMySQL. {exc}") from exc
    return pymysql.connect(**mysql_connection_kwargs(database_url))


PLATFORM_POSTGIS_TABLES = [
    "forest_blocks",
    "forest_block_versions",
    "forest_subcompartments",
    "forest_subcompartment_versions",
    "resource_surveys",
    "resource_snapshots",
    "resource_snapshot_versions",
    "attachments",
    "attachment_links",
    "attachment_events",
    "forest_rights",
    "forest_right_versions",
    "map_layers",
    "business_records",
    "dictionary_types",
    "dictionary_items",
    "admin_roles",
    "admin_users",
    "import_batches",
]


def platform_storage_health() -> dict[str, Any]:
    settings = get_settings()
    mysql_enabled = use_mysql()
    if mysql_enabled:
        try:
            with mysql_connect(settings.database_url) as conn:
                with conn.cursor() as cur:
                    placeholders = ", ".join(["%s"] * len(PLATFORM_CORE_MYSQL_TABLES))
                    cur.execute(
                        f"SELECT table_name FROM information_schema.tables "
                        f"WHERE table_schema = DATABASE() AND table_name IN ({placeholders})",
                        tuple(PLATFORM_CORE_MYSQL_TABLES),
                    )
                    existing_tables = {str(row[0]) for row in cur.fetchall()}
        except Exception as exc:
            return {
                "backend": "mysql",
                "mysqlEnabled": True,
                "postgisEnabled": False,
                "reachable": False,
                "schemaReady": False,
                "missingTables": list(PLATFORM_CORE_MYSQL_TABLES),
                "error": str(exc),
            }
        missing_tables = [table for table in PLATFORM_CORE_MYSQL_TABLES if table not in existing_tables]
        return {
            "backend": "mysql",
            "mysqlEnabled": True,
            "postgisEnabled": False,
            "reachable": True,
            "schemaReady": not missing_tables,
            "missingTables": missing_tables,
            "error": "",
        }

    postgis_enabled = use_postgis()
    if not postgis_enabled:
        return {
            "backend": settings.storage_backend,
            "mysqlEnabled": False,
            "postgisEnabled": False,
            "reachable": True,
            "schemaReady": True,
            "missingTables": [],
            "error": "",
        }

    try:
        import psycopg
    except Exception as exc:
        return {
            "backend": "postgis",
            "mysqlEnabled": False,
            "postgisEnabled": True,
            "reachable": False,
            "schemaReady": False,
            "missingTables": PLATFORM_POSTGIS_TABLES,
            "error": f"psycopg unavailable: {exc}",
        }

    try:
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT "
                    + ", ".join(f"to_regclass('public.{table}')" for table in PLATFORM_POSTGIS_TABLES)
                )
                row = cur.fetchone() or ()
    except Exception as exc:
        return {
            "backend": "postgis",
            "mysqlEnabled": False,
            "postgisEnabled": True,
            "reachable": False,
            "schemaReady": False,
            "missingTables": PLATFORM_POSTGIS_TABLES,
            "error": str(exc),
        }

    missing_tables = [
        table
        for table, value in zip(PLATFORM_POSTGIS_TABLES, row)
        if not value
    ]
    return {
        "backend": "postgis",
        "mysqlEnabled": False,
        "postgisEnabled": True,
        "reachable": True,
        "schemaReady": not missing_tables,
        "missingTables": missing_tables,
        "error": "",
    }


def forest_blocks_json_path() -> Path:
    return get_data_dir() / "forest-blocks" / "forest_blocks.json"


def forest_block_versions_json_path() -> Path:
    return get_data_dir() / "forest-blocks" / "forest_block_versions.json"


def forest_subcompartments_json_path() -> Path:
    return get_data_dir() / "forest-subcompartments" / "forest_subcompartments.json"


def forest_subcompartment_versions_json_path() -> Path:
    return get_data_dir() / "forest-subcompartments" / "forest_subcompartment_versions.json"


def resource_surveys_json_path() -> Path:
    return get_data_dir() / "resource-surveys" / "resource_surveys.json"


def resource_snapshots_json_path() -> Path:
    return get_data_dir() / "resource-surveys" / "resource_snapshots.json"


def resource_snapshot_versions_json_path() -> Path:
    return get_data_dir() / "resource-surveys" / "resource_snapshot_versions.json"


def attachments_json_path() -> Path:
    return get_data_dir() / "attachments" / "attachments.json"


def attachment_links_json_path() -> Path:
    return get_data_dir() / "attachments" / "attachment_links.json"


def attachment_events_json_path() -> Path:
    return get_data_dir() / "attachments" / "attachment_events.json"


def attachment_objects_dir() -> Path:
    return get_data_dir() / "attachments" / "objects"


def forest_rights_json_path() -> Path:
    return get_data_dir() / "forest-rights" / "forest_rights.json"


def forest_right_versions_json_path() -> Path:
    return get_data_dir() / "forest-rights" / "forest_right_versions.json"


def business_json_path(module_key: str) -> Path:
    safe_key = module_key.replace("/", "-").replace("\\", "-")
    return get_data_dir() / "business" / f"{safe_key}.json"


def map_layers_json_path() -> Path:
    return get_data_dir() / "map-layers" / "map_layers.json"


def admin_roles_json_path() -> Path:
    return get_data_dir() / "admin" / "roles.json"


def admin_users_json_path() -> Path:
    return get_data_dir() / "admin" / "users.json"


def admin_credentials_json_path() -> Path:
    return get_data_dir() / "admin" / "credentials.json"


def admin_sessions_json_path() -> Path:
    return get_data_dir() / "admin" / "sessions.json"


def dictionary_types_json_path() -> Path:
    return get_data_dir() / "admin" / "dictionary_types.json"


def dictionary_items_json_path() -> Path:
    return get_data_dir() / "admin" / "dictionary_items.json"


def import_batches_json_path() -> Path:
    return get_data_dir() / "imports" / "import_batches.json"


def harvest_applications_json_path() -> Path:
    return get_data_dir() / "harvest" / "applications.json"


def harvest_quotas_json_path() -> Path:
    return get_data_dir() / "harvest" / "quotas.json"


def harvest_batches_json_path() -> Path:
    return get_data_dir() / "harvest" / "batches.json"


def safety_alerts_json_path() -> Path:
    return get_data_dir() / "safety" / "alerts.json"


def safety_events_json_path() -> Path:
    return get_data_dir() / "safety" / "events.json"


def labor_workers_json_path() -> Path:
    return get_data_dir() / "labor" / "workers.json"


def labor_teams_json_path() -> Path:
    return get_data_dir() / "labor" / "teams.json"


def labor_jobs_json_path() -> Path:
    return get_data_dir() / "labor" / "jobs.json"


def iot_devices_json_path() -> Path:
    return get_data_dir() / "iot" / "devices.json"


def drone_missions_json_path() -> Path:
    return get_data_dir() / "drone" / "missions.json"


def ai_findings_json_path() -> Path:
    return get_data_dir() / "ai" / "findings.json"


def ai_model_assets_json_path() -> Path:
    return get_data_dir() / "ai" / "model_assets.json"


def ai_inference_runs_json_path() -> Path:
    return get_data_dir() / "ai" / "inference_runs.json"


def basemap_settings_json_path() -> Path:
    return get_data_dir() / "system" / "basemap_settings.json"


def mobile_sync_operations_json_path() -> Path:
    return get_data_dir() / "mobile" / "sync_operations.json"


def mobile_evidence_json_path() -> Path:
    return get_data_dir() / "mobile" / "evidence.json"


def mobile_evidence_dir() -> Path:
    return get_data_dir() / "mobile" / "evidence"


def mobile_tracks_json_path() -> Path:
    return get_data_dir() / "mobile" / "tracks.json"


def mobile_upload_sessions_json_path() -> Path:
    return get_data_dir() / "mobile" / "upload_sessions.json"


def operations_notification_reads_json_path() -> Path:
    return get_data_dir() / "operations" / "notification_reads.json"


def mobile_upload_chunks_dir() -> Path:
    return get_data_dir() / "mobile" / "upload-chunks"


def load_json_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8") or "[]")


def save_json_records(path: Path, records: list[dict[str, Any]]) -> None:
    with JSON_STORE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def publish_runtime_auth_config(cur: Any) -> None:
    cur.execute(
        """
        INSERT INTO platform_runtime_config (
            config_key, config_digest, release_commit, updated_at
        ) VALUES ('authentication', %s, %s, UTC_TIMESTAMP(6))
        ON DUPLICATE KEY UPDATE
            config_digest = VALUES(config_digest),
            release_commit = VALUES(release_commit),
            updated_at = VALUES(updated_at)
        """,
        (
            auth_config_digest(),
            os.environ.get("SMART_BAMBOO_RELEASE_COMMIT") or None,
        ),
    )


def init_platform_schema() -> None:
    get_data_dir()
    if use_mysql():
        with mysql_connect() as conn:
            with conn.cursor() as cur:
                for statement in mysql_platform_schema_statements():
                    cur.execute(statement)
                apply_mysql_schema_upgrades(cur)
                publish_runtime_auth_config(cur)
            conn.commit()
        return
    if not use_postgis():
        return

    import psycopg

    with psycopg.connect(get_settings().database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS forest_blocks (
                    id uuid PRIMARY KEY,
                    block_code text UNIQUE NOT NULL,
                    name text NOT NULL,
                    county_code text,
                    county_name text,
                    town_code text,
                    town_name text,
                    village_code text,
                    village_name text,
                    base_type text,
                    operation_type text,
                    forest_type text,
                    area_mu numeric,
                    slope_degree numeric,
                    ownership_status text,
                    management_status text,
                    quality_grade text,
                    health_status text,
                    risk_level text,
                    bamboo_age text,
                    avg_dbh_cm numeric,
                    avg_height_m numeric,
                    standing_density numeric,
                    carbon_estimate_tco2e numeric,
                    yield_estimate jsonb DEFAULT '{}'::jsonb,
                    tags jsonb DEFAULT '[]'::jsonb,
                    properties jsonb DEFAULT '{}'::jsonb,
                    geometry geometry(MultiPolygon, 4326),
                    centroid geometry(Point, 4326),
                    source_batch_id uuid,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_blocks_geom ON forest_blocks USING gist (geometry)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_blocks_county ON forest_blocks (county_code)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_blocks_town ON forest_blocks (town_code)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_blocks_status ON forest_blocks (management_status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_blocks_risk ON forest_blocks (risk_level)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS forest_block_versions (
                    id uuid PRIMARY KEY,
                    forest_block_id uuid NOT NULL,
                    change_type text NOT NULL,
                    snapshot jsonb NOT NULL,
                    source_version_id uuid,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("ALTER TABLE forest_block_versions ADD COLUMN IF NOT EXISTS source_version_id uuid")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS forest_subcompartments (
                    id uuid PRIMARY KEY,
                    subcompartment_code text UNIQUE NOT NULL,
                    name text NOT NULL,
                    forest_block_id uuid NOT NULL REFERENCES forest_blocks(id) ON DELETE RESTRICT,
                    area_mu numeric,
                    land_category text,
                    forest_category text,
                    origin text,
                    age_group text,
                    bamboo_species text,
                    slope_degree numeric,
                    aspect text,
                    elevation_m numeric,
                    quality_grade text,
                    health_status text,
                    risk_level text,
                    management_status text,
                    tags jsonb DEFAULT '[]'::jsonb,
                    properties jsonb DEFAULT '{}'::jsonb,
                    geometry geometry(MultiPolygon, 4326),
                    centroid geometry(Point, 4326),
                    source_batch_id uuid,
                    version integer NOT NULL DEFAULT 1,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_forest_subcompartments_block "
                "ON forest_subcompartments (forest_block_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_forest_subcompartments_geom "
                "ON forest_subcompartments USING gist (geometry)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_forest_subcompartments_status "
                "ON forest_subcompartments (management_status)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_forest_subcompartments_risk "
                "ON forest_subcompartments (risk_level)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS forest_subcompartment_versions (
                    id uuid PRIMARY KEY,
                    forest_subcompartment_id uuid NOT NULL
                        REFERENCES forest_subcompartments(id) ON DELETE CASCADE,
                    change_type text NOT NULL,
                    version integer NOT NULL,
                    snapshot jsonb NOT NULL,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_forest_subcompartment_versions_record_time "
                "ON forest_subcompartment_versions (forest_subcompartment_id, created_at)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS resource_surveys (
                    id uuid PRIMARY KEY,
                    survey_no text UNIQUE NOT NULL,
                    name text NOT NULL,
                    survey_type text NOT NULL,
                    survey_date date NOT NULL,
                    status text NOT NULL,
                    organization text,
                    surveyor text,
                    source_type text,
                    method text,
                    notes text,
                    properties jsonb DEFAULT '{}'::jsonb,
                    version integer NOT NULL DEFAULT 1,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    completed_at timestamptz,
                    deleted_at timestamptz
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_resource_surveys_date_status "
                "ON resource_surveys (survey_date, status)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS resource_snapshots (
                    id uuid PRIMARY KEY,
                    resource_survey_id uuid NOT NULL
                        REFERENCES resource_surveys(id) ON DELETE CASCADE,
                    forest_subcompartment_id uuid NOT NULL
                        REFERENCES forest_subcompartments(id) ON DELETE RESTRICT,
                    previous_snapshot_id uuid REFERENCES resource_snapshots(id) ON DELETE SET NULL,
                    sampled_at timestamptz,
                    area_mu numeric,
                    bamboo_species text,
                    origin text,
                    age_group text,
                    bamboo_density_per_mu numeric,
                    avg_dbh_cm numeric,
                    avg_height_m numeric,
                    standing_volume_m3 numeric,
                    biomass_t numeric,
                    carbon_estimate_tco2e numeric,
                    quality_grade text,
                    health_status text,
                    risk_level text,
                    sample_plot_count integer,
                    evidence_urls jsonb DEFAULT '[]'::jsonb,
                    properties jsonb DEFAULT '{}'::jsonb,
                    version integer NOT NULL DEFAULT 1,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz,
                    UNIQUE (resource_survey_id, forest_subcompartment_id)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_resource_snapshots_subcompartment_time "
                "ON resource_snapshots (forest_subcompartment_id, sampled_at)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS resource_snapshot_versions (
                    id uuid PRIMARY KEY,
                    resource_snapshot_id uuid NOT NULL
                        REFERENCES resource_snapshots(id) ON DELETE CASCADE,
                    change_type text NOT NULL,
                    version integer NOT NULL,
                    snapshot jsonb NOT NULL,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_resource_snapshot_versions_record_time "
                "ON resource_snapshot_versions (resource_snapshot_id, created_at)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS attachments (
                    id uuid PRIMARY KEY,
                    original_name text NOT NULL,
                    stored_name text NOT NULL,
                    object_key text NOT NULL,
                    content_type text,
                    size_bytes bigint NOT NULL,
                    sha256 text NOT NULL,
                    category text NOT NULL DEFAULT 'document',
                    description text,
                    status text NOT NULL DEFAULT 'active',
                    properties jsonb DEFAULT '{}'::jsonb,
                    version integer NOT NULL DEFAULT 1,
                    uploaded_by text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_attachments_hash ON attachments (sha256)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS attachment_links (
                    id uuid PRIMARY KEY,
                    attachment_id uuid NOT NULL REFERENCES attachments(id) ON DELETE RESTRICT,
                    entity_type text NOT NULL,
                    entity_id text NOT NULL,
                    relation_type text NOT NULL DEFAULT 'evidence',
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz,
                    UNIQUE (attachment_id, entity_type, entity_id, relation_type)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_attachment_links_entity "
                "ON attachment_links (entity_type, entity_id, deleted_at)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS attachment_events (
                    id uuid PRIMARY KEY,
                    attachment_id uuid NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
                    action text NOT NULL,
                    actor text,
                    detail jsonb DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_attachment_events_record_time "
                "ON attachment_events (attachment_id, created_at)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS import_batches (
                    id uuid PRIMARY KEY,
                    file_name text NOT NULL,
                    file_type text NOT NULL,
                    status text NOT NULL,
                    total_rows integer NOT NULL DEFAULT 0,
                    valid_rows integer NOT NULL DEFAULT 0,
                    invalid_rows integer NOT NULL DEFAULT 0,
                    created_by text,
                    report_json jsonb DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    completed_at timestamptz
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS forest_block_scene_links (
                    forest_block_id uuid NOT NULL,
                    scene_id text NOT NULL,
                    relation_type text NOT NULL DEFAULT 'coverage',
                    captured_at text,
                    confidence numeric,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (forest_block_id, scene_id, relation_type)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS forest_rights (
                    id uuid PRIMARY KEY,
                    archive_code text UNIQUE NOT NULL,
                    certificate_no text,
                    holder text NOT NULL,
                    certificate_type text,
                    right_type text,
                    ownership_type text,
                    right_start text,
                    right_end text,
                    contract_no text,
                    circulation_status text,
                    archive_status text,
                    registrar text,
                    missing_items text,
                    area_mu numeric,
                    county_code text,
                    county_name text,
                    town_code text,
                    town_name text,
                    village_code text,
                    village_name text,
                    linked_block_ids jsonb DEFAULT '[]'::jsonb,
                    linked_block_codes jsonb DEFAULT '[]'::jsonb,
                    documents jsonb DEFAULT '[]'::jsonb,
                    properties jsonb DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_rights_archive_status ON forest_rights (archive_status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_rights_county ON forest_rights (county_code)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_rights_linked_codes ON forest_rights USING GIN (linked_block_codes)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forest_rights_properties ON forest_rights USING GIN (properties)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS forest_right_versions (
                    id uuid PRIMARY KEY,
                    forest_right_id uuid NOT NULL,
                    change_type text NOT NULL,
                    snapshot jsonb NOT NULL,
                    source_version_id uuid,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("ALTER TABLE forest_right_versions ADD COLUMN IF NOT EXISTS source_version_id uuid")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS map_layers (
                    id uuid PRIMARY KEY,
                    record_code text UNIQUE NOT NULL,
                    name text NOT NULL,
                    status text,
                    layer_type text,
                    data_source text,
                    style jsonb DEFAULT '{}'::jsonb,
                    z_index integer,
                    visible_on_dashboard boolean NOT NULL DEFAULT true,
                    linked_block_codes jsonb DEFAULT '[]'::jsonb,
                    linked_right_archive_codes jsonb DEFAULT '[]'::jsonb,
                    properties jsonb DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_map_layers_status ON map_layers (status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_map_layers_type ON map_layers (layer_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_map_layers_dashboard ON map_layers (visible_on_dashboard)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_map_layers_linked_blocks ON map_layers USING GIN (linked_block_codes)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_map_layers_style ON map_layers USING GIN (style)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS business_records (
                    id uuid PRIMARY KEY,
                    module_key text NOT NULL,
                    record_code text NOT NULL,
                    name text NOT NULL,
                    status text,
                    linked_block_codes jsonb DEFAULT '[]'::jsonb,
                    linked_right_archive_codes jsonb DEFAULT '[]'::jsonb,
                    properties jsonb DEFAULT '{}'::jsonb,
                    payload jsonb DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz,
                    UNIQUE (module_key, record_code)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_business_records_module ON business_records (module_key)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_business_records_status ON business_records (module_key, status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_business_records_linked_blocks ON business_records USING GIN (linked_block_codes)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_business_records_linked_rights ON business_records USING GIN (linked_right_archive_codes)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_business_records_properties ON business_records USING GIN (properties)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_business_records_payload ON business_records USING GIN (payload)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_types (
                    id uuid PRIMARY KEY,
                    type_code text UNIQUE NOT NULL,
                    name text NOT NULL,
                    category text NOT NULL,
                    hierarchy_enabled boolean NOT NULL DEFAULT false,
                    value_mode text NOT NULL DEFAULT 'code',
                    description text,
                    status text NOT NULL DEFAULT 'active',
                    sort_order integer NOT NULL DEFAULT 0,
                    system_defined boolean NOT NULL DEFAULT false,
                    properties jsonb DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_dictionary_type_category ON dictionary_types (category, status, sort_order)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_items (
                    id uuid PRIMARY KEY,
                    dictionary_type_id uuid NOT NULL REFERENCES dictionary_types(id) ON DELETE CASCADE,
                    item_code text NOT NULL,
                    label text NOT NULL,
                    parent_item_id uuid REFERENCES dictionary_items(id) ON DELETE SET NULL,
                    level_code text NOT NULL DEFAULT '',
                    full_name text,
                    pinyin text,
                    initials text,
                    search_aliases jsonb DEFAULT '[]'::jsonb,
                    sort_order integer NOT NULL DEFAULT 0,
                    status text NOT NULL DEFAULT 'active',
                    metadata jsonb DEFAULT '{}'::jsonb,
                    source text NOT NULL DEFAULT 'manual',
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz
                )
                """
            )
            cur.execute(
                "ALTER TABLE dictionary_items "
                "ALTER COLUMN level_code SET DEFAULT ''"
            )
            cur.execute(
                "UPDATE dictionary_items SET level_code = '' "
                "WHERE level_code IS NULL"
            )
            cur.execute(
                "ALTER TABLE dictionary_items "
                "ALTER COLUMN level_code SET NOT NULL"
            )
            cur.execute(
                "ALTER TABLE dictionary_items DROP CONSTRAINT IF EXISTS "
                "dictionary_items_dictionary_type_id_item_code_key"
            )
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_dictionary_item_code "
                "ON dictionary_items (dictionary_type_id, level_code, item_code)"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_dictionary_item_lookup ON dictionary_items (dictionary_type_id, parent_item_id, status, sort_order)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_dictionary_item_level ON dictionary_items (dictionary_type_id, level_code, status)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_roles (
                    id uuid PRIMARY KEY,
                    role_code text UNIQUE NOT NULL,
                    name text NOT NULL,
                    status text,
                    permissions jsonb DEFAULT '[]'::jsonb,
                    menu_modules jsonb DEFAULT '[]'::jsonb,
                    data_scopes jsonb DEFAULT '{}'::jsonb,
                    properties jsonb DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_roles_status ON admin_roles (status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_roles_permissions ON admin_roles USING GIN (permissions)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_roles_menu_modules ON admin_roles USING GIN (menu_modules)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_roles_data_scopes ON admin_roles USING GIN (data_scopes)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_users (
                    id uuid PRIMARY KEY,
                    username text UNIQUE NOT NULL,
                    display_name text NOT NULL,
                    status text,
                    roles jsonb DEFAULT '[]'::jsonb,
                    data_scopes jsonb DEFAULT '{}'::jsonb,
                    properties jsonb DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    deleted_at timestamptz
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_users_status ON admin_users (status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_users_roles ON admin_users USING GIN (roles)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_users_data_scopes ON admin_users USING GIN (data_scopes)")
        conn.commit()
