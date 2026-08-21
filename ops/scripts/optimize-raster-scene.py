#!/usr/bin/env python3
"""Rebuild existing raster COGs with display-safe alpha and WebP cache prewarm."""

from __future__ import annotations

import argparse
import os
import uuid
from pathlib import Path

from server import app as remote_sensing


def selected_scenes(scene_ids: list[str], optimize_all: bool) -> list[dict[str, object]]:
    scenes = remote_sensing.load_catalog()
    if optimize_all:
        return [
            scene
            for scene in scenes
            if str(scene.get("assetType") or "orthophoto") == "orthophoto"
            and str(scene.get("cogPath") or "").strip()
        ]
    selected = []
    for scene_id in scene_ids:
        selected.append(remote_sensing.find_scene(scene_id))
    return selected


def optimize_scene(scene: dict[str, object], *, prewarm: bool) -> None:
    scene_id = str(scene["id"])
    cog_path = remote_sensing.resolve_catalog_path(str(scene["cogPath"]))
    if not cog_path.exists():
        raise FileNotFoundError(f"{scene_id}: COG not found: {cog_path}")

    candidate = cog_path.with_name(f".{cog_path.name}.{uuid.uuid4().hex}.optimizing.tif")
    backup = cog_path.with_name(f".{cog_path.name}.{uuid.uuid4().hex}.backup.tif")
    try:
        remote_sensing.convert_to_cog(cog_path, candidate)
        metadata = remote_sensing.raster_metadata(candidate, list(scene.get("bounds") or []))
        os.replace(cog_path, backup)
        try:
            os.replace(candidate, cog_path)
        except Exception:
            os.replace(backup, cog_path)
            raise
        backup.unlink(missing_ok=True)
    finally:
        candidate.unlink(missing_ok=True)

    updated = {
        **scene,
        "size": cog_path.stat().st_size,
        "bounds": metadata["bounds"],
        "crs": metadata["crs"],
        "width": metadata["width"],
        "height": metadata["height"],
        "bands": metadata["bands"],
        "dtype": metadata["dtype"],
        "resolution": scene.get("resolution") or metadata["resolution"],
        "metresPerPixel": metadata["metresPerPixel"],
        "maximumZoom": metadata["maximumZoom"],
        "tileFormat": "webp",
        "updatedAt": remote_sensing.now_iso(),
    }
    remote_sensing.save_scene(updated)
    remote_sensing.clear_tile_cache(scene_id)
    result = remote_sensing.prewarm_scene_tiles(scene_id) if prewarm else {}
    print(
        f"optimized {scene_id} ({updated.get('name') or cog_path.name}) "
        f"maxZoom={updated['maximumZoom']} bytes={updated['size']} prewarm={result}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-id", action="append", default=[])
    parser.add_argument("--all", action="store_true", dest="optimize_all")
    parser.add_argument("--no-prewarm", action="store_true")
    args = parser.parse_args()
    if not args.optimize_all and not args.scene_id:
        parser.error("provide --scene-id ID (repeatable) or --all")

    scenes = selected_scenes(args.scene_id, args.optimize_all)
    for scene in scenes:
        optimize_scene(scene, prewarm=not args.no_prewarm)
    print(f"completed: {len(scenes)} raster scene(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
