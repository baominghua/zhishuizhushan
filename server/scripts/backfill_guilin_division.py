from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Iterable

from server.modules.auth import AuthContext
from server.modules.forest_blocks import (
    ForestBlockPatch,
    load_all_blocks,
    patch_forest_block,
)


COUNTY_CODE = "350781"
COUNTY_NAME = "邵武市"
TOWN_CODE = "350781200"
TOWN_NAME = "桂林乡"
DEFAULT_EXPECTED_COUNT = 100


@dataclass(frozen=True)
class BackfillPlan:
    candidates: tuple[dict[str, Any], ...]
    already_correct: tuple[dict[str, Any], ...]
    conflicts: tuple[dict[str, Any], ...]


def is_guilin_block(block: dict[str, Any]) -> bool:
    return not block.get("deletedAt") and str(block.get("blockCode") or "").strip().upper().startswith("GJ")


def plan_backfill(blocks: Iterable[dict[str, Any]]) -> BackfillPlan:
    candidates: list[dict[str, Any]] = []
    already_correct: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    expected = {
        "countyCode": COUNTY_CODE,
        "countyName": COUNTY_NAME,
        "townCode": TOWN_CODE,
        "townName": TOWN_NAME,
    }

    for block in blocks:
        if not is_guilin_block(block):
            continue
        values = {key: str(block.get(key) or "").strip() for key in expected}
        if values == expected:
            already_correct.append(block)
            continue
        if any(values.values()):
            conflicts.append(block)
            continue
        candidates.append(block)

    key = lambda item: str(item.get("blockCode") or "")
    return BackfillPlan(
        candidates=tuple(sorted(candidates, key=key)),
        already_correct=tuple(sorted(already_correct, key=key)),
        conflicts=tuple(sorted(conflicts, key=key)),
    )


def summary(plan: BackfillPlan) -> dict[str, Any]:
    return {
        "division": {
            "countyCode": COUNTY_CODE,
            "countyName": COUNTY_NAME,
            "townCode": TOWN_CODE,
            "townName": TOWN_NAME,
        },
        "candidates": len(plan.candidates),
        "alreadyCorrect": len(plan.already_correct),
        "conflicts": [
            {
                "id": item.get("id"),
                "blockCode": item.get("blockCode"),
                "countyCode": item.get("countyCode"),
                "countyName": item.get("countyName"),
                "townCode": item.get("townCode"),
                "townName": item.get("townName"),
            }
            for item in plan.conflicts
        ],
    }


def apply_backfill(plan: BackfillPlan, *, expected_count: int) -> int:
    if plan.conflicts:
        raise RuntimeError("GJ 林班存在非空且不一致的行政区字段，拒绝自动覆盖")
    if not plan.candidates:
        if plan.already_correct:
            return 0
        raise RuntimeError("没有找到任何 GJ 林班，拒绝执行")
    if len(plan.candidates) != expected_count:
        raise RuntimeError(
            f"待回填数量为 {len(plan.candidates)}，与安全门槛 {expected_count} 不一致，拒绝执行"
        )

    context = AuthContext(
        user="system:guilin-division-backfill",
        roles={"admin"},
        projects={"*"},
        areas={"*"},
        principal_type="service-token",
    )
    payload = ForestBlockPatch(
        countyCode=COUNTY_CODE,
        countyName=COUNTY_NAME,
        townCode=TOWN_CODE,
        townName=TOWN_NAME,
    )
    for block in plan.candidates:
        patch_forest_block(str(block["id"]), payload, context)
    return len(plan.candidates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely backfill the official Shaowu/Guilin division for historical GJ forest blocks."
    )
    parser.add_argument("--apply", action="store_true", help="Persist the planned changes; default is dry-run.")
    parser.add_argument(
        "--expected-count",
        type=int,
        default=DEFAULT_EXPECTED_COUNT,
        help="Safety gate for the exact number of records that may be changed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = plan_backfill(load_all_blocks())
    result = summary(plan)
    result["mode"] = "apply" if args.apply else "dry-run"
    if args.apply:
        result["updated"] = apply_backfill(plan, expected_count=args.expected_count)
        result["after"] = summary(plan_backfill(load_all_blocks()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
