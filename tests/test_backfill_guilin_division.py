from __future__ import annotations

import pytest

from server.scripts.backfill_guilin_division import (
    COUNTY_CODE,
    COUNTY_NAME,
    TOWN_CODE,
    TOWN_NAME,
    apply_backfill,
    plan_backfill,
)


def block(code: str, **fields):
    return {"id": code, "blockCode": code, "deletedAt": None, **fields}


def test_plan_only_selects_empty_gj_divisions():
    plan = plan_backfill(
        [
            block("GJ1-25"),
            block(
                "GJ2-25",
                countyCode=COUNTY_CODE,
                countyName=COUNTY_NAME,
                townCode=TOWN_CODE,
                townName=TOWN_NAME,
            ),
            block("GJ3-25", townName="其他乡"),
            block("S7-25"),
            {**block("GJ4-25"), "deletedAt": "2026-01-01T00:00:00"},
        ]
    )

    assert [item["blockCode"] for item in plan.candidates] == ["GJ1-25"]
    assert [item["blockCode"] for item in plan.already_correct] == ["GJ2-25"]
    assert [item["blockCode"] for item in plan.conflicts] == ["GJ3-25"]


def test_apply_refuses_conflicts_before_writing():
    plan = plan_backfill([block("GJ1-25"), block("GJ2-25", townName="其他乡")])
    with pytest.raises(RuntimeError, match="拒绝自动覆盖"):
        apply_backfill(plan, expected_count=1)


def test_apply_refuses_unexpected_candidate_count():
    plan = plan_backfill([block("GJ1-25"), block("GJ2-25")])
    with pytest.raises(RuntimeError, match="安全门槛"):
        apply_backfill(plan, expected_count=1)
