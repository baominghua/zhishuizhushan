from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import AuthContext, request_context, require_write_access
from .database import get_data_dir, load_json_records, save_json_records
from .forest_blocks import find_block


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


def require_catalog_scene(scene_id: str) -> dict[str, Any]:
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


def scene_links_for_block(block_id: str) -> list[dict[str, Any]]:
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
