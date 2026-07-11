"""
POST /api/chat  ——  SSE 流式对话端点

事件流(text/event-stream)格式:
  event: delta
  data: {"text": "增量文本"}

  event: delta
  data: {"text": "..."}

  event: done
  data: {"stage": "education", "stage_label": "教育背景", "quick_replies": [...]}

  event: error
  data: {"message": "..."}
"""
import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.core.auth_deps import get_current_user
from app.core.config import settings
from app.core.input_sanitizer import sanitize_user_input
from app.models.db_models import User
from app.models.schemas import ChatRequest
from app.services import dialog_service, llm_service
from app.store.db_store import session_store
from app.mock.fallback import mock_chat_reply

router = APIRouter()
logger = logging.getLogger("glint.api.chat")


def _split_for_stream(text: str, chunk_size: int = 4):
    """把 mock 回复拆成小块,模拟流式效果"""
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


@router.post("/chat")
async def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """流式对话 —— LLM 可用走真 LLM,否则走 mock 兜底"""
    user_id = current_user.id

    # 用户输入安全过滤
    sanitized, block_reason = sanitize_user_input(req.user_message)
    if block_reason:
        from fastapi.responses import JSONResponse
        from fastapi import status
        logger.warning("input_blocked", extra={
            "user_id": user_id,
            "session_id": req.session_id,
            "reason": block_reason,
        })
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": block_reason},
        )
    # 使用清洗后的输入
    req.user_message = sanitized

    async def event_generator() -> AsyncGenerator[dict, None]:
        # ==== 走 mock 兜底 ====
        if not settings.llm_available:
            mock = mock_chat_reply(req.target_job, req.user_msg_count)
            # 记录到 session
            session_store.get_or_create(req.session_id, req.target_job, user_id)
            session_store.append_message(req.session_id, "user", req.user_message)
            session_store.set_stage(req.session_id, mock["stage"])

            # 模拟流式
            for chunk in _split_for_stream(mock["reply"], chunk_size=4):
                yield {
                    "event": "delta",
                    "data": json.dumps({"text": chunk}, ensure_ascii=False)
                }
                await asyncio.sleep(0.025)  # ~40 字符/秒,自然感

            session_store.append_message(req.session_id, "assistant", mock["reply"])
            yield {
                "event": "done",
                "data": json.dumps({
                    "stage": mock["stage"],
                    "stage_label": mock["stage_label"],
                    "quick_replies": mock["quick_replies"],
                    "fallback": True,
                    "fallback_reason": "LLM 服务未配置，当前展示的是示例内容",
                }, ensure_ascii=False)
            }
            return

        # ==== 走真 LLM ====
        had_error = False
        with llm_service.usage_context(
            user_id=user_id,
            session_id=req.session_id,
            endpoint="/api/chat",
            source="chat",
        ):
            async for event_name, payload in dialog_service.chat_stream(
                req.session_id, req.target_job, req.user_message, req.user_msg_count, user_id
            ):
                if event_name == "error":
                    had_error = True
                    logger.warning("chat_llm_fallback", extra={
                        "session_id": req.session_id,
                        "user_id": user_id,
                        "error": payload,
                    })
                    # LLM 失败,fallback 到 mock
                    mock = mock_chat_reply(req.target_job, req.user_msg_count)
                    session_store.set_stage(req.session_id, mock["stage"])
                    for chunk in _split_for_stream(mock["reply"], chunk_size=4):
                        yield {
                            "event": "delta",
                            "data": json.dumps({"text": chunk}, ensure_ascii=False)
                        }
                        await asyncio.sleep(0.025)
                    session_store.append_message(req.session_id, "assistant", mock["reply"])
                    yield {
                        "event": "done",
                        "data": json.dumps({
                            "stage": mock["stage"],
                            "stage_label": mock["stage_label"],
                            "quick_replies": mock["quick_replies"],
                            "fallback": True,
                            "fallback_reason": "当前 AI 服务繁忙，展示的是示例内容",
                        }, ensure_ascii=False)
                    }
                    return
                yield {"event": event_name, "data": payload}

    return EventSourceResponse(event_generator())
