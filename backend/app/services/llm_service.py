"""
LLM 服务封装 —— 兼容 Anthropic Messages API 风格的代理端点
支持同步调用与 SSE 流式输出
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json
from typing import AsyncGenerator, List, Dict, Optional
import httpx

from app.core.config import settings
from app.services import llm_usage_service


class LLMError(Exception):
    """LLM 调用失败"""
    pass


class LLMQuotaExceeded(LLMError):
    """当前用户超过 LLM 使用额度"""
    pass


_usage_context = ContextVar("llm_usage_context", default={})


@contextmanager
def usage_context(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    endpoint: str = "",
    source: str = "",
):
    current = dict(_usage_context.get() or {})
    next_context = {
        **current,
        "user_id": user_id if user_id is not None else current.get("user_id"),
        "session_id": session_id if session_id is not None else current.get("session_id"),
        "endpoint": endpoint or current.get("endpoint", ""),
        "source": source or current.get("source", ""),
    }
    token = _usage_context.set(next_context)
    try:
        yield
    finally:
        _usage_context.reset(token)


def _build_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "anthropic-version": settings.LLM_ANTHROPIC_VERSION,
        "Authorization": f"Bearer {settings.LLM_API_KEY}"
    }


def _build_payload(
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    stream: bool = False
) -> Dict:
    payload = {
        "model": settings.LLM_MODEL,
        "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
        "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
        "messages": messages,
        "stream": stream
    }
    if system:
        payload["system"] = system
    return payload


async def chat_complete(
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    timeout: float = 60.0
) -> str:
    """
    一次性获取完整回复
    messages 格式: [{"role": "user"|"assistant", "content": "..."}]
    """
    if not settings.LLM_API_KEY:
        raise LLMError("LLM_API_KEY 未配置")

    url = f"{settings.LLM_BASE_URL}/messages"
    payload = _build_payload(messages, system, max_tokens, temperature, stream=False)
    estimated_prompt_tokens = _enforce_usage_quota(messages, system, payload)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, headers=_build_headers(), json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            _record_usage(
                payload=payload,
                prompt_tokens=estimated_prompt_tokens,
                completion_tokens=0,
                status="error",
                error_message=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
            raise LLMError(f"LLM HTTP {e.response.status_code}: {e.response.text[:200]}")
        except httpx.RequestError as e:
            _record_usage(
                payload=payload,
                prompt_tokens=estimated_prompt_tokens,
                completion_tokens=0,
                status="error",
                error_message=f"网络错误: {e}",
            )
            raise LLMError(f"LLM 网络错误: {e}")

    data = resp.json()
    content_blocks = data.get("content", [])
    text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
    text = "".join(text_parts).strip()
    usage = _extract_usage(data)
    prompt_tokens = usage.get("prompt_tokens") or estimated_prompt_tokens
    completion_tokens = usage.get("completion_tokens") or llm_usage_service.estimate_text_tokens(text)
    _record_usage(
        payload=payload,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        status="success",
    )
    return text


async def chat_stream(
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    timeout: float = 120.0
) -> AsyncGenerator[str, None]:
    """
    流式获取回复, yield 每个文本增量片段(纯文本 delta)
    Anthropic SSE 事件类型:
      - message_start
      - content_block_start
      - content_block_delta  (内含 delta.text)
      - content_block_stop
      - message_delta
      - message_stop
      - ping
    """
    if not settings.LLM_API_KEY:
        raise LLMError("LLM_API_KEY 未配置")

    url = f"{settings.LLM_BASE_URL}/messages"
    payload = _build_payload(messages, system, max_tokens, temperature, stream=True)
    estimated_prompt_tokens = _enforce_usage_quota(messages, system, payload)
    prompt_tokens = estimated_prompt_tokens
    completion_tokens = 0
    text_parts: List[str] = []
    completed = False

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            async with client.stream(
                "POST", url, headers=_build_headers(), json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    body_text = body.decode("utf-8", "ignore")[:200]
                    _record_usage(
                        payload=payload,
                        prompt_tokens=estimated_prompt_tokens,
                        completion_tokens=0,
                        status="error",
                        error_message=f"HTTP {resp.status_code}: {body_text}",
                    )
                    raise LLMError(
                        f"LLM HTTP {resp.status_code}: {body_text}"
                    )

                event_name = None
                async for raw_line in resp.aiter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if line.startswith("event:"):
                        event_name = line[6:].strip()
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        usage = _extract_usage(data)
                        if usage.get("prompt_tokens"):
                            prompt_tokens = usage["prompt_tokens"]
                        if usage.get("completion_tokens"):
                            completion_tokens = usage["completion_tokens"]
                        # 文本增量
                        if data.get("type") == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    text_parts.append(text)
                                    yield text
                        # 错误事件
                        elif data.get("type") == "error":
                            err = data.get("error", {})
                            message = (
                                f"LLM 流式错误: {err.get('type', 'unknown')} "
                                f"- {err.get('message', '')}"
                            )
                            _record_usage(
                                payload=payload,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens or llm_usage_service.estimate_text_tokens("".join(text_parts)),
                                status="error",
                                error_message=message,
                            )
                            raise LLMError(
                                message
                            )
                completed = True
        except httpx.RequestError as e:
            _record_usage(
                payload=payload,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens or llm_usage_service.estimate_text_tokens("".join(text_parts)),
                status="error",
                error_message=f"网络错误: {e}",
            )
            raise LLMError(f"LLM 网络错误: {e}")

    if completed:
        _record_usage(
            payload=payload,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens or llm_usage_service.estimate_text_tokens("".join(text_parts)),
            status="success",
        )


def _enforce_usage_quota(
    messages: List[Dict[str, str]],
    system: Optional[str],
    payload: Dict,
) -> int:
    estimated_prompt_tokens = llm_usage_service.estimate_prompt_tokens(messages, system)
    context = _current_usage_context()
    try:
        llm_usage_service.enforce_quota(
            user_id=context.get("user_id"),
            session_id=context.get("session_id"),
            endpoint=context.get("endpoint", ""),
            source=context.get("source", ""),
            model=payload.get("model", ""),
            estimated_prompt_tokens=estimated_prompt_tokens,
            max_output_tokens=int(payload.get("max_tokens") or settings.LLM_MAX_TOKENS),
        )
    except llm_usage_service.LLMQuotaExceeded as exc:
        raise LLMQuotaExceeded(str(exc))
    return estimated_prompt_tokens


def _record_usage(
    *,
    payload: Dict,
    prompt_tokens: int,
    completion_tokens: int,
    status: str,
    error_message: str = "",
):
    context = _current_usage_context()
    llm_usage_service.record_usage(
        user_id=context.get("user_id"),
        session_id=context.get("session_id"),
        endpoint=context.get("endpoint", ""),
        source=context.get("source", ""),
        model=payload.get("model", ""),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        status=status,
        error_message=error_message,
    )


def _current_usage_context() -> Dict:
    return dict(_usage_context.get() or {})


def _extract_usage(data: Dict) -> Dict[str, int]:
    usage = data.get("usage") or {}
    if not usage and isinstance(data.get("message"), dict):
        usage = data["message"].get("usage") or {}
    return {
        "prompt_tokens": _first_int(
            usage,
            "input_tokens",
            "prompt_tokens",
            "input_token_count",
        ),
        "completion_tokens": _first_int(
            usage,
            "output_tokens",
            "completion_tokens",
            "output_token_count",
        ),
    }


def _first_int(data: Dict, *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0
