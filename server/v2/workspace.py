from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from server.modules.auth import AuthContext, request_context
from server.modules.forest_blocks import ForestBlockFilters, list_forest_blocks
from server.modules.forest_rights import ForestRightFilters, list_forest_rights
from server.modules.imports import import_workflow_summary
from .operations_center import collect_audit, collect_todos, read_ids


router = APIRouter(prefix="/workspace", tags=["v2-workspace"])


def safe_total(payload: dict[str, Any]) -> int:
    try:
        return max(0, int(payload.get("total") or 0))
    except (TypeError, ValueError):
        return 0


@router.get("/summary")
def workspace_summary(
    context: AuthContext = Depends(request_context),
) -> dict[str, Any]:
    blocks = list_forest_blocks(ForestBlockFilters(limit=1), context)
    rights = list_forest_rights(ForestRightFilters(limit=1), context)
    imports = import_workflow_summary(context)
    quality_issues = max(0, int(imports.get("openQualityIssues") or 0))
    todos = collect_todos(context) if context.user else []
    recent_events = collect_audit(context)[:20] if context.user else []
    reads = read_ids(context.user) if context.user else set()
    alerts = [{**item, "read": item["id"] in reads} for item in recent_events if item["id"] not in reads]

    return {
        "source": "live",
        "principal": {
            "user": context.user,
            "roles": sorted(context.roles),
        },
        "metrics": {
            "forestBlocks": safe_total(blocks),
            "forestRights": safe_total(rights),
            "openQualityIssues": quality_issues,
        },
        "todos": todos[:8],
        "alerts": alerts[:8],
        "moduleAvailability": {
            "resources": "available",
            "imports": "available",
            "patrol": "available",
            "harvest": "available",
            "labor": "available",
            "equipment": "available",
            "drone": "available",
            "ai": "available",
            "safety": "available",
        },
        "emptyState": (
            "暂无需要办理的事项"
            if not todos and quality_issues == 0
            else f"当前有 {len(todos) + quality_issues} 个事项需要关注"
        ),
    }
