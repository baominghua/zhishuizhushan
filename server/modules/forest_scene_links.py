from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .admin_roles import require_permission
from .auth import AuthContext, request_context
from .database import get_data_dir, load_json_records, mysql_connect, save_json_records, use_mysql, use_postgis
from .forest_blocks import find_block
from .settings import get_settings


router = APIRouter(prefix="/api", tags=["forest-scene-links"])


class ForestSceneLinkIn(BaseModel):
    sceneId: str = Field(min_length=1)
    relationType: str = Field(default="coverage", min_length=1)
    capturedAt: str | None = None
    confidence: float | None = None


def forest_scene_links_json_path():
    return get_data_dir() / "forest-blocks" / "forest_block_scene_links.json"


def remote_sensing_catalog_json_path():
    return get_data_dir() / "catalog.json"


def remote_sensing_catalog_backend() -> str:
    return os.environ.get("REMOTE_SENSING_CATALOG_BACKEND", "json").strip().lower()


def remote_sensing_database_url() -> str:
    return (
        os.environ.get("REMOTE_SENSING_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()


def require_psycopg(purpose: str):
    try:
        import psycopg

        return psycopg
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"{purpose} requires psycopg. {exc}") from exc


def connect_postgis(database_url: str, purpose: str):
    psycopg = require_psycopg(purpose)
    try:
        return psycopg.connect(database_url)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"{purpose} is unavailable",
        ) from exc


def normalize_scene_link_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
        return {
            "forestBlockId": str(source.get("forest_block_id") or source.get("forestBlockId") or ""),
            "sceneId": source.get("scene_id") or source.get("sceneId"),
            "relationType": source.get("relation_type") or source.get("relationType"),
            "capturedAt": datetime_to_iso(source.get("captured_at") if "captured_at" in source else source.get("capturedAt")),
            "confidence": source.get("confidence"),
        }

    forest_block_id, scene_id, relation_type, captured_at, confidence = row
    return {
        "forestBlockId": str(forest_block_id),
        "sceneId": scene_id,
        "relationType": relation_type,
        "capturedAt": datetime_to_iso(captured_at),
        "confidence": float(confidence) if confidence is not None else None,
    }


def datetime_to_iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


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


def normalize_catalog_scene_document(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        document = json.loads(value)
    except json.JSONDecodeError:
        return None
    return dict(document) if isinstance(document, dict) else None


def require_catalog_scene_mysql(scene_id: str) -> dict[str, Any]:
    database_url = remote_sensing_database_url()
    if not database_url:
        raise HTTPException(status_code=503, detail="Remote sensing catalog database is not configured")
    try:
        with mysql_connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT scene FROM remote_sensing_scenes "
                    "WHERE id = %s AND deleted_at IS NULL LIMIT 1",
                    (scene_id,),
                )
                row = cur.fetchone()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Remote sensing catalog database is unavailable") from exc

    raw_scene = row.get("scene") if hasattr(row, "get") else row[0] if row else None
    scene = normalize_catalog_scene_document(raw_scene)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


def require_catalog_scene(scene_id: str) -> dict[str, Any]:
    if remote_sensing_catalog_backend() == "mysql":
        return require_catalog_scene_mysql(scene_id)

    catalog_path = remote_sensing_catalog_json_path()
    if not catalog_path.exists():
        raise HTTPException(status_code=404, detail="Scene catalog not found")

    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=404, detail="Scene catalog not found") from exc

    for scene in data.get("scenes", []):
        if scene.get("id") == scene_id:
            return scene
    raise HTTPException(status_code=404, detail="Scene not found")


def split_tokens(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[,;\s]+", value)
    return sorted({str(item).strip() for item in items if str(item).strip()})


def context_matches(values: set[str], required: str) -> bool:
    return not values or "*" in values or required in values


def scene_allowed(scene: dict[str, Any], context: AuthContext) -> bool:
    project_id = str(scene.get("projectId") or "").strip()
    area_code = str(scene.get("areaCode") or "").strip()
    allowed_users = set(split_tokens(scene.get("allowedUsers")))
    allowed_roles = set(split_tokens(scene.get("allowedRoles")))

    if project_id and not context_matches(context.projects, project_id):
        return False
    if area_code and not context_matches(context.areas, area_code):
        return False
    if allowed_users and context.user not in allowed_users and "*" not in allowed_users:
        return False
    if allowed_roles and "*" not in context.roles and not (allowed_roles & context.roles):
        return False
    return True


def require_visible_scene(scene_id: str, context: AuthContext) -> dict[str, Any]:
    scene = require_catalog_scene(scene_id)
    if not scene_allowed(scene, context):
        raise HTTPException(status_code=403, detail="Scene is not visible for current context")
    return scene


def scene_link_visible(item: dict[str, Any], context: AuthContext) -> bool:
    scene_id = str(item.get("sceneId") or "").strip()
    if not scene_id:
        return False
    try:
        require_visible_scene(scene_id, context)
    except HTTPException:
        return False
    return True


def load_scene_links() -> list[dict[str, Any]]:
    return load_json_records(forest_scene_links_json_path())


def save_scene_links(records: list[dict[str, Any]]) -> None:
    save_json_records(forest_scene_links_json_path(), records)


def list_scene_links_postgis(block_id: str) -> list[dict[str, Any]]:
    database_url = get_settings().database_url
    with connect_postgis(database_url, "forest scene links PostGIS database") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT forest_block_id::text, scene_id, relation_type, captured_at, confidence
                FROM forest_block_scene_links
                WHERE forest_block_id = %s
                ORDER BY created_at DESC, scene_id, relation_type
                """,
                (block_id,),
            )
            return [normalize_scene_link_row(row) for row in cur.fetchall()]


def list_scene_links_mysql(block_id: str) -> list[dict[str, Any]]:
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT forest_block_id, scene_id, relation_type, captured_at, confidence
                FROM forest_block_scene_links
                WHERE forest_block_id = %s
                ORDER BY created_at DESC, scene_id, relation_type
                """,
                (block_id,),
            )
            return [normalize_scene_link_row(row) for row in cur.fetchall()]


MYSQL_SCENE_LINK_UPSERT_SQL = """
    INSERT INTO forest_block_scene_links (
        forest_block_id, scene_id, relation_type, captured_at, confidence, created_at
    ) VALUES (%s, %s, %s, %s, %s, UTC_TIMESTAMP(6))
    ON DUPLICATE KEY UPDATE
        captured_at = VALUES(captured_at),
        confidence = VALUES(confidence),
        created_at = UTC_TIMESTAMP(6)
"""


def mysql_scene_link_values(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["forestBlockId"],
        item["sceneId"],
        item["relationType"],
        mysql_datetime(item.get("capturedAt")),
        item.get("confidence"),
    )


def upsert_scene_link_mysql(cur: Any, item: dict[str, Any]) -> None:
    cur.execute(MYSQL_SCENE_LINK_UPSERT_SQL, mysql_scene_link_values(item))


def save_scene_link_mysql(item: dict[str, Any]) -> None:
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            upsert_scene_link_mysql(cur, item)
        conn.commit()


def save_scene_links_mysql_batch(
    records: list[dict[str, Any]],
    *,
    batch_size: int = 500,
    connection_factory: Any = mysql_connect,
) -> None:
    if not records:
        return
    size = max(1, int(batch_size))
    with connection_factory() as conn:
        with conn.cursor() as cur:
            for start in range(0, len(records), size):
                batch = records[start : start + size]
                cur.executemany(
                    MYSQL_SCENE_LINK_UPSERT_SQL,
                    [mysql_scene_link_values(item) for item in batch],
                )
        conn.commit()


def save_import_batch_scene_links_mysql(
    import_batch_id: str,
    *,
    scene_id: str,
    relation_type: str,
    captured_at: str | None = None,
    confidence: float | None = None,
    connection_factory: Any = mysql_connect,
) -> int:
    """Link every active target in an import batch without materializing block IDs."""
    with connection_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO forest_block_scene_links (
                    forest_block_id, scene_id, relation_type, captured_at, confidence, created_at
                )
                SELECT
                    links.forest_block_id, %s, %s, %s, %s, UTC_TIMESTAMP(6)
                FROM import_batch_block_links links
                JOIN forest_blocks blocks ON blocks.id = links.forest_block_id
                WHERE links.import_batch_id = %s
                  AND links.import_action IN ('created', 'updated')
                  AND blocks.deleted_at IS NULL
                ON DUPLICATE KEY UPDATE
                    captured_at = VALUES(captured_at),
                    confidence = VALUES(confidence),
                    created_at = UTC_TIMESTAMP(6)
                """,
                (
                    scene_id,
                    relation_type,
                    mysql_datetime(captured_at),
                    confidence,
                    import_batch_id,
                ),
            )
            affected = int(cur.rowcount or 0)
        conn.commit()
    return affected


def delete_scene_links_mysql(block_id: str, scene_id: str, relation_type: str) -> int:
    sql = "DELETE FROM forest_block_scene_links WHERE forest_block_id = %s AND scene_id = %s"
    params: tuple[Any, ...] = (block_id, scene_id)
    if relation_type:
        sql += " AND relation_type = %s"
        params = (block_id, scene_id, relation_type)
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            deleted = cur.rowcount
        conn.commit()
    return deleted


def delete_scene_links_for_scene_mysql(scene_id: str) -> int:
    with mysql_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM forest_block_scene_links WHERE scene_id = %s", (scene_id,))
            deleted = cur.rowcount
        conn.commit()
    return deleted


def upsert_scene_link_postgis(item: dict[str, Any]) -> None:
    database_url = get_settings().database_url
    with connect_postgis(database_url, "forest scene links PostGIS database") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO forest_block_scene_links (
                    forest_block_id,
                    scene_id,
                    relation_type,
                    captured_at,
                    confidence
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (forest_block_id, scene_id, relation_type) DO UPDATE
                SET captured_at = EXCLUDED.captured_at,
                    confidence = EXCLUDED.confidence,
                    created_at = now()
                """,
                (
                    item["forestBlockId"],
                    item["sceneId"],
                    item["relationType"],
                    item["capturedAt"],
                    item["confidence"],
                ),
            )
        conn.commit()


def delete_scene_links_postgis(block_id: str, scene_id: str, relation_type: str) -> int:
    database_url = get_settings().database_url
    sql = "DELETE FROM forest_block_scene_links WHERE forest_block_id = %s AND scene_id = %s"
    params: tuple[Any, ...] = (block_id, scene_id)
    if relation_type:
        sql += " AND relation_type = %s"
        params = (block_id, scene_id, relation_type)

    with connect_postgis(database_url, "forest scene links PostGIS database") as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            deleted = cur.rowcount
        conn.commit()
    return deleted


def delete_scene_links_for_scene_postgis(scene_id: str) -> int:
    database_url = get_settings().database_url
    with connect_postgis(database_url, "forest scene links PostGIS database") as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM forest_block_scene_links WHERE scene_id = %s", (scene_id,))
            deleted = cur.rowcount
        conn.commit()
    return deleted


def delete_scene_links_for_scene(scene_id: str) -> int:
    if use_mysql():
        return delete_scene_links_for_scene_mysql(scene_id)
    if use_postgis():
        return delete_scene_links_for_scene_postgis(scene_id)

    records = load_scene_links()
    kept = [item for item in records if item.get("sceneId") != scene_id]
    deleted = len(records) - len(kept)
    if deleted:
        save_scene_links(kept)
    return deleted


def replace_scene_links_for_scene(scene_id: str, records: list[dict[str, Any]]) -> None:
    """Replace coverage relations after the operator confirms spatial matching."""
    normalized = [
        {
            "forestBlockId": str(item.get("forestBlockId") or ""),
            "sceneId": scene_id,
            "relationType": "coverage",
            "capturedAt": item.get("capturedAt") or None,
            "confidence": item.get("confidence"),
        }
        for item in records
        if str(item.get("forestBlockId") or "").strip()
    ]
    if use_mysql():
        with mysql_connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM forest_block_scene_links WHERE scene_id = %s AND relation_type = %s",
                        (scene_id, "coverage"),
                    )
                    if normalized:
                        cur.executemany(
                            MYSQL_SCENE_LINK_UPSERT_SQL,
                            [mysql_scene_link_values(item) for item in normalized],
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return
    if use_postgis():
        database_url = get_settings().database_url
        with connect_postgis(database_url, "forest scene links PostGIS database") as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM forest_block_scene_links WHERE scene_id = %s AND relation_type = %s",
                        (scene_id, "coverage"),
                    )
                    for item in normalized:
                        cur.execute(
                            """
                            INSERT INTO forest_block_scene_links (
                                forest_block_id, scene_id, relation_type, captured_at, confidence
                            )
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (forest_block_id, scene_id, relation_type) DO UPDATE
                            SET captured_at = EXCLUDED.captured_at,
                                confidence = EXCLUDED.confidence,
                                created_at = now()
                            """,
                            (
                                item["forestBlockId"],
                                item["sceneId"],
                                item["relationType"],
                                item["capturedAt"],
                                item["confidence"],
                            ),
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return
    existing = [
        item
        for item in load_scene_links()
        if item.get("sceneId") != scene_id or item.get("relationType") != "coverage"
    ]
    save_scene_links([*existing, *normalized])


def scene_links_for_block(block_id: str) -> list[dict[str, Any]]:
    if use_mysql():
        return list_scene_links_mysql(block_id)
    if use_postgis():
        return list_scene_links_postgis(block_id)
    return [item for item in load_scene_links() if item.get("forestBlockId") == block_id]


def require_visible_block(block_id: str, context: AuthContext) -> dict[str, Any]:
    return find_block(block_id, context)


@router.get("/forest-blocks/{block_id}/scenes")
def list_forest_block_scene_links(
    block_id: str,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_visible_block(block_id, context)
    items = [item for item in scene_links_for_block(block_id) if scene_link_visible(item, context)]
    return {"items": items, "total": len(items)}


@router.post("/forest-blocks/{block_id}/scenes")
def create_forest_block_scene_link(
    block_id: str,
    payload: ForestSceneLinkIn,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.linkages.manage")
    require_visible_block(block_id, context)

    next_item = {
        "forestBlockId": block_id,
        "sceneId": payload.sceneId.strip(),
        "relationType": payload.relationType.strip(),
        "capturedAt": payload.capturedAt.strip() if isinstance(payload.capturedAt, str) and payload.capturedAt.strip() else None,
        "confidence": payload.confidence,
    }
    if not next_item["sceneId"]:
        raise HTTPException(status_code=422, detail="sceneId cannot be empty")
    if not next_item["relationType"]:
        raise HTTPException(status_code=422, detail="relationType cannot be empty")
    require_visible_scene(next_item["sceneId"], context)

    if use_mysql():
        save_scene_link_mysql(next_item)
        return next_item
    if use_postgis():
        upsert_scene_link_postgis(next_item)
        return next_item

    records = [
        item
        for item in load_scene_links()
        if not (
            item.get("forestBlockId") == block_id
            and item.get("sceneId") == next_item["sceneId"]
            and item.get("relationType") == next_item["relationType"]
        )
    ]
    records.append(next_item)
    save_scene_links(records)
    return next_item


@router.delete("/forest-blocks/{block_id}/scenes/{scene_id}")
def delete_forest_block_scene_link(
    block_id: str,
    scene_id: str,
    relationType: str = Query(default=""),
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_permission(context, "forest.linkages.manage")
    require_visible_block(block_id, context)
    require_visible_scene(scene_id, context)

    relation_type = relationType.strip()
    if use_mysql():
        deleted = delete_scene_links_mysql(block_id, scene_id, relation_type)
        return {"ok": True, "deleted": deleted}
    if use_postgis():
        deleted = delete_scene_links_postgis(block_id, scene_id, relation_type)
        return {"ok": True, "deleted": deleted}

    records = load_scene_links()
    kept: list[dict[str, Any]] = []
    deleted = 0
    for item in records:
        matches_block = item.get("forestBlockId") == block_id
        matches_scene = item.get("sceneId") == scene_id
        matches_relation = not relation_type or item.get("relationType") == relation_type
        if matches_block and matches_scene and matches_relation:
            deleted += 1
            continue
        kept.append(item)

    save_scene_links(kept)
    return {"ok": True, "deleted": deleted}
