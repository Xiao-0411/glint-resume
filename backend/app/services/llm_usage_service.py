"""
LLM usage accounting and quota enforcement.

All LLM calls go through app.services.llm_service, which calls this module before
and after each provider request. Token counts prefer provider-reported usage and
fall back to a conservative local estimate when usage is absent.
"""
import datetime
import logging
import math
from decimal import Decimal
from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy import func

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.db_models import LLMUsageRecord, User

logger = logging.getLogger("glint.llm_usage")


ANONYMOUS_USER_ID = "anonymous"


class LLMQuotaExceeded(Exception):
    """Raised before a provider request when the user has exhausted quota."""


def estimate_text_tokens(text: Optional[str]) -> int:
    if not text:
        return 0
    cjk = 0
    ascii_like = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            cjk += 1
        else:
            ascii_like += 1
    return max(1, math.ceil(cjk + ascii_like / 4))


def estimate_prompt_tokens(
    messages: Iterable[Dict[str, str]],
    system: Optional[str] = None,
) -> int:
    total = estimate_text_tokens(system)
    for message in messages or []:
        total += 4
        total += estimate_text_tokens(message.get("role", ""))
        total += estimate_text_tokens(message.get("content", ""))
    return max(1, total)


def enforce_quota(
    *,
    user_id: Optional[str],
    session_id: Optional[str],
    endpoint: str,
    source: str,
    model: str,
    estimated_prompt_tokens: int,
    max_output_tokens: int,
):
    if not settings.LLM_USAGE_ENABLED:
        return

    uid = _normalize_user_id(user_id)
    projected_tokens = estimated_prompt_tokens + max(0, max_output_tokens)
    projected_cost = calculate_cost_usd(model, estimated_prompt_tokens, max_output_tokens)
    stats = get_daily_usage(uid)

    reason = ""
    call_limit = settings.LLM_DAILY_CALL_LIMIT_PER_USER
    token_limit = settings.LLM_DAILY_TOKEN_LIMIT_PER_USER
    cost_limit = settings.LLM_DAILY_COST_LIMIT_USD_PER_USER

    if call_limit > 0 and stats["calls"] + 1 > call_limit:
        reason = f"今日 LLM 调用次数已达上限({call_limit})"
    elif token_limit > 0 and stats["total_tokens"] + projected_tokens > token_limit:
        reason = f"今日 LLM token 已达上限({token_limit})"
    elif cost_limit > 0 and stats["cost_usd"] + projected_cost > cost_limit:
        reason = f"今日 LLM 费用已达上限(${cost_limit:.2f})"

    if reason:
        record_usage(
            user_id=uid,
            session_id=session_id,
            endpoint=endpoint,
            source=source,
            model=model,
            prompt_tokens=estimated_prompt_tokens,
            completion_tokens=max(0, max_output_tokens),
            status="blocked",
            error_message=reason,
        )
        raise LLMQuotaExceeded(reason)


def record_usage(
    *,
    user_id: Optional[str],
    session_id: Optional[str],
    endpoint: str,
    source: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    status: str = "success",
    error_message: str = "",
):
    if not settings.LLM_USAGE_ENABLED:
        return

    uid = _normalize_user_id(user_id)
    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    total_tokens = prompt_tokens + completion_tokens
    cost_usd = calculate_cost_usd(model, prompt_tokens, completion_tokens)

    db = SessionLocal()
    try:
        _ensure_user(db, uid)
        db.add(
            LLMUsageRecord(
                user_id=uid,
                session_id=session_id,
                endpoint=endpoint or "",
                source=source or "",
                model=model or "",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=Decimal(f"{cost_usd:.6f}"),
                status=status,
                error_message=(error_message or "")[:1000] or None,
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("llm_usage_record_failed", extra={"error": str(exc)})
    finally:
        db.close()


def get_daily_usage(user_id: Optional[str]) -> Dict:
    uid = _normalize_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(
                func.count(LLMUsageRecord.id),
                func.coalesce(func.sum(LLMUsageRecord.prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.completion_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.total_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.cost_usd), 0),
            )
            .filter(
                LLMUsageRecord.user_id == uid,
                LLMUsageRecord.created_at >= _today_start_utc(),
                LLMUsageRecord.status != "blocked",
            )
            .one()
        )
        cost = row[4] or Decimal("0")
        return {
            "user_id": uid,
            "date": _today_start_utc().date().isoformat(),
            "calls": int(row[0] or 0),
            "prompt_tokens": int(row[1] or 0),
            "completion_tokens": int(row[2] or 0),
            "total_tokens": int(row[3] or 0),
            "cost_usd": float(cost),
        }
    finally:
        db.close()


def get_recent_usage(user_id: Optional[str], limit: int = 30):
    uid = _normalize_user_id(user_id)
    db = SessionLocal()
    try:
        rows = (
            db.query(LLMUsageRecord)
            .filter(LLMUsageRecord.user_id == uid)
            .order_by(LLMUsageRecord.created_at.desc(), LLMUsageRecord.id.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [_usage_to_dict(row) for row in rows]
    finally:
        db.close()


def usage_limits() -> Dict:
    input_price, output_price = model_prices(settings.LLM_MODEL)
    return {
        "daily_call_limit": settings.LLM_DAILY_CALL_LIMIT_PER_USER,
        "daily_token_limit": settings.LLM_DAILY_TOKEN_LIMIT_PER_USER,
        "daily_cost_limit_usd": settings.LLM_DAILY_COST_LIMIT_USD_PER_USER,
        "input_price_per_1m_usd": input_price,
        "output_price_per_1m_usd": output_price,
    }


def calculate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_price, output_price = model_prices(model)
    return (
        max(0, prompt_tokens) * input_price
        + max(0, completion_tokens) * output_price
    ) / 1_000_000


def model_prices(model: str) -> Tuple[float, float]:
    if settings.LLM_INPUT_PRICE_PER_1M_USD > 0 or settings.LLM_OUTPUT_PRICE_PER_1M_USD > 0:
        return settings.LLM_INPUT_PRICE_PER_1M_USD, settings.LLM_OUTPUT_PRICE_PER_1M_USD

    name = (model or "").lower()
    if "opus" in name:
        return 15.0, 75.0
    if "sonnet" in name:
        return 3.0, 15.0
    if "haiku" in name:
        return 0.25, 1.25
    if "deepseek" in name:
        return 0.28, 0.42
    if "gpt-4o-mini" in name:
        return 0.15, 0.60
    if "gpt-4o" in name:
        return 5.0, 15.0
    return 0.0, 0.0


def _usage_to_dict(row: LLMUsageRecord) -> Dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "session_id": row.session_id,
        "endpoint": row.endpoint,
        "source": row.source,
        "model": row.model,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "total_tokens": row.total_tokens,
        "cost_usd": float(row.cost_usd or 0),
        "status": row.status,
        "error_message": row.error_message or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _normalize_user_id(user_id: Optional[str]) -> str:
    return user_id or ANONYMOUS_USER_ID


def _ensure_user(db, user_id: str):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        display_name = "匿名用户" if user_id == ANONYMOUS_USER_ID else ""
        db.add(User(id=user_id, display_name=display_name))
        db.flush()


def _today_start_utc():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)
