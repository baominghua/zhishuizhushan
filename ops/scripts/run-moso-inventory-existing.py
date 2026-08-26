from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from server.app import (
    find_task_record,
    load_catalog,
    moso_scene_candidates,
    now_iso,
    run_moso_inventory_batch_task,
    upsert_task,
)
from server.modules.auth import AuthContext
from server.modules.forest_blocks import ForestBlockFilters, filtered_forest_blocks
from server.modules.moso_bamboo_inventory import create_moso_inference_run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="针对平台已有正射影像和林班边界执行毛竹资源试算。"
    )
    parser.add_argument(
        "--all-geometries",
        action="store_true",
        help="包含没有匹配正射影像的林班（这些林班会在结果中记录失败原因）。",
    )
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    context = AuthContext(
        user="production-trial-run",
        roles={"admin"},
        projects={"*"},
        areas={"*"},
        principal_type="release-operator",
    )
    blocks = filtered_forest_blocks(
        ForestBlockFilters(limit=min(1000, max(1, args.limit))),
        context,
        limit=min(1000, max(1, args.limit)),
    )
    blocks = [block for block in blocks if block.get("geometry")]
    scenes = load_catalog()
    if not args.all_geometries:
        blocks = [
            block
            for block in blocks
            if moso_scene_candidates(block, scenes, asset_type="orthophoto")
        ]
    if not blocks:
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": "没有找到同时具备林班边界和已入库正射影像的可试算资源。",
                    "sceneCount": len(scenes),
                },
                ensure_ascii=False,
            )
        )
        return 2

    inference_run = create_moso_inference_run(
        blocks,
        scenes,
        actor=context.user,
    )
    task = {
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "type": "moso-bamboo-inventory",
        "status": "queued",
        "progress": 0,
        "message": f"生产试算已排队，待分析 {len(blocks)} 个林班",
        "blockTotal": len(blocks),
        "inferenceRunId": inference_run["id"],
        "createdBy": context.user,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "events": [],
    }
    upsert_task(task)
    run_moso_inventory_batch_task(
        task["id"],
        blocks,
        scenes,
        context,
        inference_run["id"],
    )
    result = find_task_record(task["id"])
    print(
        json.dumps(
            {
                "ok": result.get("status") == "completed",
                "taskId": task["id"],
                "inferenceRunId": inference_run["id"],
                "eligibleBlockCount": len(blocks),
                "status": result.get("status"),
                "message": result.get("message"),
                "result": result.get("result") or {},
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
