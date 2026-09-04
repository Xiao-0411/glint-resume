"""
POST /api/chat  ——  完整 JSON 对话端点

响应格式:
  {"reply": "完整回复", "complete": true, "stage": "education", ...}

前端收到完整 JSON 后自行模拟分块播放，后端不再向浏览器转发上游 SSE。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth_deps import get_current_user
from app.core.config import settings
from app.core.input_sanitizer import sanitize_target_job, sanitize_user_input
from app.models.db_models import User
from app.models.schemas import ChatCompleteResponse, ChatRequest
from app.services import dialog_service, llm_service
from app.store.db_store import session_store
from app.mock.fallback import mock_chat_reply

router = APIRouter()
logger = logging.getLogger("glint.api.chat")


@router.post("/chat", response_model=ChatCompleteResponse)
async def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
) -> ChatCompleteResponse:
    """完整对话响应 —— 后端先校验 JSON，前端再模拟流式播放。"""
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
    req.target_job = sanitize_target_job(req.target_job)

    # Complete the ownership check before opening the SSE response. Raising from
    # inside the generator would otherwise turn a 403 into a broken 200 stream.
    try:
        session_store.get_or_create(req.session_id, req.target_job, user_id)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该会话属于其他用户",
        )

    # ==== 无 LLM 或 LLM 格式/网络失败时，统一返回完整 mock ====
    if not settings.llm_available:
        mock = mock_chat_reply(req.target_job, req.user_msg_count)
        session_store.append_message(req.session_id, "user", req.user_message, user_id)
        session_store.set_stage(req.session_id, mock["stage"], user_id)
        session_store.append_message(req.session_id, "assistant", mock["reply"], user_id)
        return {
            "reply": mock["reply"],
            "complete": True,
            "stage": mock["stage"],
            "stage_label": mock["stage_label"],
            "quick_replies": mock["quick_replies"],
            "extracted": {},
            "fallback": True,
            "fallback_reason": "LLM 服务未配置，当前展示的是示例内容",
        }

    with llm_service.usage_context(
        user_id=user_id,
        session_id=req.session_id,
        endpoint="/api/chat",
        source="chat",
    ):
        try:
            return await dialog_service.chat_response(
                req.session_id, req.target_job, req.user_message, req.user_msg_count, user_id
            )
        except llm_service.LLMError as exc:
            logger.warning("chat_llm_fallback", extra={
                "session_id": req.session_id,
                "user_id": user_id,
                "error": str(exc),
            })
            mock = mock_chat_reply(req.target_job, req.user_msg_count)
            session_store.set_stage(req.session_id, mock["stage"], user_id)
            session_store.append_message(req.session_id, "assistant", mock["reply"], user_id)
            return {
                "reply": mock["reply"],
                "complete": True,
                "stage": mock["stage"],
                "stage_label": mock["stage_label"],
                "quick_replies": mock["quick_replies"],
                "extracted": {},
                "fallback": True,
                "fallback_reason": "当前 AI 服务繁忙，展示的是示例内容",
            }
