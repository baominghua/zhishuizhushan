from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.modules.database import mysql_connect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark indexed MySQL forest block queries.")
    parser.add_argument("--database-url", default=os.environ.get("SMART_BAMBOO_DATABASE_URL", ""))
    parser.add_argument("--town-code", default="350703101")
    parser.add_argument("--bbox", default="117.8,26.3,118.8,27.2")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--min-area-mu", type=float, default=1_000_000)
    parser.add_argument("--max-p95-ms", type=float, default=500)
    parser.add_argument("--import-write-rows", type=int, default=1000)
    parser.add_argument("--import-write-iterations", type=int, default=3)
    parser.add_argument("--min-import-write-rows-per-second", type=float, default=500)
    parser.add_argument("--relation-link-rows", type=int, default=1000)
    parser.add_argument("--relation-link-iterations", type=int, default=3)
    parser.add_argument("--min-relation-link-rows-per-second", type=float, default=1000)
    return parser.parse_args()


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def bbox_wkt(value: str) -> str:
    west, south, east, north = [float(item.strip()) for item in value.split(",")]
    return f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"


def benchmark_query(cur: Any, name: str, sql: str, params: tuple[Any, ...], iterations: int, expected_index: str) -> dict[str, Any]:
    cur.execute(f"EXPLAIN ANALYZE {sql}", params)
    explain = [str(row[0]) for row in cur.fetchall()]
    samples: list[float] = []
    row_count = 0
    for _ in range(max(1, iterations)):
        started = time.perf_counter()
        cur.execute(sql, params)
        rows = cur.fetchall()
        samples.append((time.perf_counter() - started) * 1000)
        row_count = len(rows)
    index_used = any(expected_index.lower() in line.lower() for line in explain)
    return {
        "name": name,
        "expectedIndex": expected_index,
        "indexUsed": index_used,
        "iterations": len(samples),
        "rows": row_count,
        "minMs": round(min(samples), 3),
        "meanMs": round(statistics.fmean(samples), 3),
        "p50Ms": round(percentile(samples, 0.50), 3),
        "p95Ms": round(percentile(samples, 0.95), 3),
        "maxMs": round(max(samples), 3),
        "explain": explain,
    }


def build_benchmark_acceptance(
    *,
    dataset: dict[str, Any],
    results: list[dict[str, Any]],
    min_area_mu: float,
    max_p95_ms: float,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    total_area_mu = float(dataset.get("totalAreaMu") or 0)
    if total_area_mu < min_area_mu:
        issues.append(
            {
                "code": "dataset_area_below_target",
                "actual": total_area_mu,
                "required": min_area_mu,
            }
        )
    for result in results:
        if not result.get("indexUsed"):
            issues.append(
                {
                    "code": "expected_index_not_used",
                    "query": result.get("name"),
                    "expectedIndex": result.get("expectedIndex", ""),
                }
            )
        p95_ms = float(result.get("p95Ms") or 0)
        if p95_ms > max_p95_ms:
            issues.append(
                {
                    "code": "query_p95_exceeded",
                    "query": result.get("name"),
                    "actualMs": p95_ms,
                    "maximumMs": max_p95_ms,
                }
            )
    return {"passed": not issues, "issues": issues}


def inspect_import_storage(cur: Any) -> dict[str, Any]:
    cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(JSON_STORAGE_SIZE(report_json)), 0), "
        "COALESCE(MAX(JSON_STORAGE_SIZE(report_json)), 0) FROM import_batches"
    )
    batch_count, report_bytes, max_report_bytes = cur.fetchone() or (0, 0, 0)
    cur.execute(
        "SELECT COUNT(*) FROM import_batches WHERE "
        "JSON_CONTAINS_PATH(report_json, 'one', '$.importedBlocks', '$.importedRightsArchives')"
    )
    duplicated_row = cur.fetchone() or (0,)
    cur.execute("SELECT COUNT(*) FROM import_batch_block_links")
    block_target_row = cur.fetchone() or (0,)
    cur.execute("SELECT COUNT(*) FROM import_batch_right_links")
    right_target_row = cur.fetchone() or (0,)
    return {
        "batchCount": int(batch_count or 0),
        "reportJsonBytes": int(report_bytes or 0),
        "maxReportJsonBytes": int(max_report_bytes or 0),
        "largeTargetArrayBatchCount": int(duplicated_row[0] or 0),
        "blockTargetCount": int(block_target_row[0] or 0),
        "rightTargetCount": int(right_target_row[0] or 0),
    }


def benchmark_import_write(conn: Any, *, rows: int, iterations: int) -> dict[str, Any]:
    row_count = max(1, int(rows))
    elapsed_samples: list[float] = []
    throughput_samples: list[float] = []
    for iteration in range(max(1, int(iterations))):
        batch_id = str(uuid.uuid4())
        prefix = f"BENCH-{batch_id[:8]}-{iteration}"
        now = datetime.now(UTC).replace(tzinfo=None)
        block_rows = [
            (
                str(uuid.uuid4()),
                f"{prefix}-{index:07d}",
                f"Import benchmark {index}",
                now,
                now,
            )
            for index in range(row_count)
        ]
        link_rows = [
            (
                batch_id,
                block_id,
                "created",
                json.dumps(
                    {"blockCode": block_code, "action": "created"},
                    ensure_ascii=False,
                ),
            )
            for block_id, block_code, _name, _created_at, _updated_at in block_rows
        ]
        started = time.perf_counter()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO import_batches "
                    "(id, file_name, file_type, status, total_rows, valid_rows, invalid_rows, "
                    "review_status, acceptance_status, quality_status, publish_risk_status, "
                    "report_json, created_at, completed_at) "
                    "VALUES (%s, %s, 'benchmark', 'completed', %s, %s, 0, "
                    "'pending', 'pending', 'passed', 'clear', %s, %s, %s)",
                    (
                        batch_id,
                        f"{prefix}.benchmark",
                        row_count,
                        row_count,
                        json.dumps(
                            {
                                "id": batch_id,
                                "targetsStorage": "relational",
                                "importedBlockCount": row_count,
                            }
                        ),
                        now,
                        now,
                    ),
                )
                cur.executemany(
                    "INSERT INTO forest_blocks "
                    "(id, block_code, name, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    block_rows,
                )
                cur.executemany(
                    "INSERT INTO import_batch_block_links "
                    "(import_batch_id, forest_block_id, import_action, target_json) "
                    "VALUES (%s, %s, %s, %s)",
                    link_rows,
                )
            elapsed_ms = (time.perf_counter() - started) * 1000
            elapsed_samples.append(elapsed_ms)
            throughput_samples.append(row_count / max(elapsed_ms / 1000, 0.000001))
        finally:
            conn.rollback()
    return {
        "rowsPerIteration": row_count,
        "iterations": len(elapsed_samples),
        "meanMs": round(statistics.fmean(elapsed_samples), 3),
        "p95Ms": round(percentile(elapsed_samples, 0.95), 3),
        "rowsPerSecond": round(percentile(throughput_samples, 0.50), 3),
        "transactionRolledBack": True,
    }


def benchmark_relation_link_write(conn: Any, *, rows: int, iterations: int) -> dict[str, Any]:
    row_count = max(1, int(rows))
    scene_samples: list[float] = []
    layer_samples: list[float] = []
    for iteration in range(max(1, int(iterations))):
        batch_id = str(uuid.uuid4())
        layer_id = str(uuid.uuid4())
        prefix = f"REL-BENCH-{batch_id[:8]}-{iteration}"
        now = datetime.now(UTC).replace(tzinfo=None)
        block_rows = [
            (str(uuid.uuid4()), f"{prefix}-{index:07d}", f"Relation benchmark {index}", now, now)
            for index in range(row_count)
        ]
        link_rows = [
            (
                batch_id,
                block_id,
                "created",
                json.dumps({"blockCode": block_code, "action": "created"}),
            )
            for block_id, block_code, _name, _created_at, _updated_at in block_rows
        ]
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO import_batches "
                    "(id, file_name, file_type, status, total_rows, valid_rows, invalid_rows, "
                    "review_status, acceptance_status, quality_status, publish_risk_status, "
                    "report_json, created_at, completed_at) "
                    "VALUES (%s, %s, 'benchmark', 'completed', %s, %s, 0, "
                    "'approved', 'accepted', 'passed', 'clear', %s, %s, %s)",
                    (
                        batch_id,
                        f"{prefix}.benchmark",
                        row_count,
                        row_count,
                        json.dumps({"id": batch_id, "targetsStorage": "relational"}),
                        now,
                        now,
                    ),
                )
                cur.executemany(
                    "INSERT INTO forest_blocks (id, block_code, name, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    block_rows,
                )
                cur.executemany(
                    "INSERT INTO import_batch_block_links "
                    "(import_batch_id, forest_block_id, import_action, target_json) "
                    "VALUES (%s, %s, %s, %s)",
                    link_rows,
                )
                cur.execute(
                    "INSERT INTO map_layers "
                    "(id, record_code, name, status, layer_type, visible_on_dashboard, "
                    "properties, created_at, updated_at) "
                    "VALUES (%s, %s, %s, 'published', 'imagery', TRUE, %s, %s, %s)",
                    (layer_id, prefix, prefix, json.dumps({"importBatchId": batch_id}), now, now),
                )

                started = time.perf_counter()
                cur.execute(
                    "INSERT INTO forest_block_scene_links "
                    "(forest_block_id, scene_id, relation_type, created_at) "
                    "SELECT links.forest_block_id, %s, 'coverage', UTC_TIMESTAMP(6) "
                    "FROM import_batch_block_links links "
                    "JOIN forest_blocks blocks ON blocks.id = links.forest_block_id "
                    "WHERE links.import_batch_id = %s "
                    "AND links.import_action IN ('created', 'updated') "
                    "AND blocks.deleted_at IS NULL "
                    "ON DUPLICATE KEY UPDATE created_at = UTC_TIMESTAMP(6)",
                    (f"scene-{batch_id}", batch_id),
                )
                scene_samples.append((time.perf_counter() - started) * 1000)

                started = time.perf_counter()
                cur.execute(
                    "INSERT IGNORE INTO map_layer_block_links (map_layer_id, forest_block_id) "
                    "SELECT %s, links.forest_block_id "
                    "FROM import_batch_block_links links "
                    "JOIN forest_blocks blocks ON blocks.id = links.forest_block_id "
                    "WHERE links.import_batch_id = %s "
                    "AND links.import_action IN ('created', 'updated') "
                    "AND blocks.deleted_at IS NULL",
                    (layer_id, batch_id),
                )
                layer_samples.append((time.perf_counter() - started) * 1000)
        finally:
            conn.rollback()

    scene_throughput = [row_count / max(sample / 1000, 0.000001) for sample in scene_samples]
    layer_throughput = [row_count / max(sample / 1000, 0.000001) for sample in layer_samples]
    return {
        "rowsPerIteration": row_count,
        "iterations": len(scene_samples),
        "sceneP95Ms": round(percentile(scene_samples, 0.95), 3),
        "layerP95Ms": round(percentile(layer_samples, 0.95), 3),
        "sceneRowsPerSecond": round(percentile(scene_throughput, 0.50), 3),
        "layerRowsPerSecond": round(percentile(layer_throughput, 0.50), 3),
        "transactionRolledBack": True,
    }


def build_import_acceptance(
    *,
    storage: dict[str, Any],
    import_write: dict[str, Any],
    min_rows_per_second: float,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    duplicated = int(storage.get("largeTargetArrayBatchCount") or 0)
    if duplicated:
        issues.append(
            {
                "code": "import_targets_duplicated_in_report_json",
                "batchCount": duplicated,
            }
        )
    rows_per_second = float(import_write.get("rowsPerSecond") or 0)
    if rows_per_second < min_rows_per_second:
        issues.append(
            {
                "code": "import_write_throughput_below_target",
                "actualRowsPerSecond": rows_per_second,
                "minimumRowsPerSecond": min_rows_per_second,
            }
        )
    return {"passed": not issues, "issues": issues}


def build_relation_link_acceptance(
    relation_link: dict[str, Any],
    *,
    min_rows_per_second: float,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for key, code in (
        ("sceneRowsPerSecond", "scene_link_throughput_below_target"),
        ("layerRowsPerSecond", "layer_link_throughput_below_target"),
    ):
        actual = float(relation_link.get(key) or 0)
        if actual < min_rows_per_second:
            issues.append(
                {
                    "code": code,
                    "actualRowsPerSecond": actual,
                    "minimumRowsPerSecond": min_rows_per_second,
                }
            )
    return {"passed": not issues, "issues": issues}


def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise SystemExit("SMART_BAMBOO_DATABASE_URL or --database-url is required")
    envelope = bbox_wkt(args.bbox)
    queries = [
        (
            "town-ledger",
            "SELECT id, block_code, name, area_mu FROM forest_blocks "
            "WHERE deleted_at IS NULL AND town_code = %s "
            "ORDER BY updated_at DESC LIMIT 100",
            (args.town_code,),
            "idx_forest_blocks_town_active_updated",
        ),
        (
            "bbox-map",
            "SELECT b.id, b.block_code FROM forest_block_geometries g "
            "FORCE INDEX (idx_forest_block_geometry) "
            "STRAIGHT_JOIN forest_blocks b ON b.id = g.forest_block_id "
            "WHERE b.deleted_at IS NULL "
            "AND MBRIntersects(g.geometry, "
            "ST_GeomFromText(%s, 4326, 'axis-order=long-lat')) LIMIT 2000",
            (envelope,),
            "idx_forest_block_geometry",
        ),
        (
            "town-aggregate",
            "SELECT town_code, COUNT(*), SUM(area_mu) FROM forest_blocks "
            "WHERE deleted_at IS NULL GROUP BY town_code ORDER BY COUNT(*) DESC",
            (),
            "idx_forest_blocks_town_active_area",
        ),
        (
            "operation-facet",
            "SELECT base_type, operation_type, COUNT(*) FROM forest_blocks "
            "WHERE deleted_at IS NULL "
            "GROUP BY base_type, operation_type ORDER BY base_type, operation_type",
            (),
            "idx_forest_blocks_operation_active",
        ),
    ]
    with mysql_connect(args.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(area_mu), 0) FROM forest_blocks WHERE deleted_at IS NULL"
            )
            dataset_row = cur.fetchone() or (0, 0)
            dataset = {
                "blockCount": int(dataset_row[0] or 0),
                "totalAreaMu": float(dataset_row[1] or 0),
            }
            results = [
                benchmark_query(cur, name, sql, params, args.iterations, expected_index)
                for name, sql, params, expected_index in queries
            ]
            import_storage = inspect_import_storage(cur)
        import_write = benchmark_import_write(
            conn,
            rows=args.import_write_rows,
            iterations=args.import_write_iterations,
        )
        relation_link = benchmark_relation_link_write(
            conn,
            rows=args.relation_link_rows,
            iterations=args.relation_link_iterations,
        )
    acceptance = build_benchmark_acceptance(
        dataset=dataset,
        results=results,
        min_area_mu=args.min_area_mu,
        max_p95_ms=args.max_p95_ms,
    )
    import_acceptance = build_import_acceptance(
        storage=import_storage,
        import_write=import_write,
        min_rows_per_second=args.min_import_write_rows_per_second,
    )
    acceptance["issues"].extend(import_acceptance["issues"])
    relation_acceptance = build_relation_link_acceptance(
        relation_link,
        min_rows_per_second=args.min_relation_link_rows_per_second,
    )
    acceptance["issues"].extend(relation_acceptance["issues"])
    acceptance["passed"] = not acceptance["issues"]
    print(
        json.dumps(
            {
                "database": "mysql",
                "dataset": dataset,
                "requirements": {
                    "minAreaMu": args.min_area_mu,
                    "maxP95Ms": args.max_p95_ms,
                    "minImportWriteRowsPerSecond": args.min_import_write_rows_per_second,
                    "minRelationLinkRowsPerSecond": args.min_relation_link_rows_per_second,
                },
                "results": results,
                "importStorage": import_storage,
                "importWrite": import_write,
                "relationLink": relation_link,
                "acceptance": acceptance,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if acceptance["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
