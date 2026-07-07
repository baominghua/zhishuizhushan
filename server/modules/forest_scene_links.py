from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import AuthContext, request_context, require_write_access
from .database import get_data_dir, load_json_records, save_json_records, use_postgis
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


def use_postgis_catalog() -> bool:
    return (
        os.environ.get("REMOTE_SENSING_CATALOG_BACKEND", "json").strip().lower() == "postgis"
        and bool(remote_sensing_catalog_database_url())
    )


def remote_sensing_catalog_database_url() -> str:
    return os.environ.get("REMOTE_SENSING_DATABASE_URL", "").strip() or os.environ.get("DATABASE_URL", "").strip()


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
            detail=f"{purpose} is unavailable for {database_url}. {exc}",
        ) from exc


def normalize_scene_link_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        source = dict(row)
        return {
            "forestBlockId": str(source.get("forest_block_id") or source.get("forestBlockId") or ""),
            "sceneId": source.get("scene_id") or source.get("sceneId"),
            "relationType": source.get("relation_type") or source.get("relationType"),
            "capturedAt": source.get("captured_at") if "captured_at" in source else source.get("capturedAt"),
            "confidence": source.get("confidence"),
        }

    forest_block_id, scene_id, relation_type, captured_at, confidence = row
    return {
        "forestBlockId": str(forest_block_id),
        "sceneId": scene_id,
        "relationType": relation_type,
        "capturedAt": captured_at,
        "confidence": float(confidence) if confidence is not None else None,
    }


def require_catalog_scene(scene_id: str) -> dict[str, Any]:
    if use_postgis_catalog():
        database_url = remote_sensing_catalog_database_url()
        with connect_postgis(database_url, "Remote sensing catalog PostGIS database") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM remote_sensing_scenes WHERE id = %s LIMIT 1", (scene_id,))
                row = cur.fetchone()
        if row:
            return {"id": scene_id}
        raise HTTPException(status_code=404, detail="Scene not found")

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


def scene_links_for_block(block_id: str) -> list[dict[str, Any]]:
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
    items = scene_links_for_block(block_id)
    return {"items": items, "total": len(items)}


@router.post("/forest-blocks/{block_id}/scenes")
def create_forest_block_scene_link(
    block_id: str,
    payload: ForestSceneLinkIn,
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    require_write_access(context)
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
    require_catalog_scene(next_item["sceneId"])

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
    require_write_access(context)
    require_visible_block(block_id, context)

    relation_type = relationType.strip()
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
