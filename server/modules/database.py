from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .settings import get_settings


def get_data_dir() -> Path:
    data_dir = get_settings().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "forest-blocks").mkdir(parents=True, exist_ok=True)
    return data_dir


def use_postgis() -> bool:
    settings = get_settings()
    return settings.storage_backend == "postgis" and bool(settings.database_url)


def forest_blocks_json_path() -> Path:
    return get_data_dir() / "forest-blocks" / "forest_blocks.json"


def load_json_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8") or "[]")


def save_json_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def init_platform_schema() -> None:
    get_data_dir()
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
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
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
        conn.commit()
