from fastapi import APIRouter, Depends, Query

from app.core.auth_deps import get_current_user
from app.models.db_models import User
from app.services import llm_usage_service

router = APIRouter()


@router.get("/usage/llm/today")
def llm_usage_today(current_user: User = Depends(get_current_user)):
    usage = llm_usage_service.get_daily_usage(current_user.id)
    limits = llm_usage_service.usage_limits()
    return {
        "usage": usage,
        "limits": limits,
        "remaining": {
            "calls": _remaining(limits["daily_call_limit"], usage["calls"]),
            "tokens": _remaining(limits["daily_token_limit"], usage["total_tokens"]),
            "cost_usd": _remaining(limits["daily_cost_limit_usd"], usage["cost_usd"]),
        },
    }


@router.get("/usage/llm/recent")
def recent_llm_usage(
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    return {
        "records": llm_usage_service.get_recent_usage(current_user.id, limit=limit),
        "limits": llm_usage_service.usage_limits(),
    }


def _remaining(limit, used):
    if not limit or limit <= 0:
        return None
    return max(0, limit - used)
