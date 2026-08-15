"""
LLM 服务封装 —— 兼容 Anthropic Messages API 风格的代理端点
支持同步调用与 SSE 流式输出
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import logging
from typing import AsyncGenerator, List, Dict, Optional
import httpx

from app.core.config import settings
from app.services import llm_usage_service

logger = logging.getLogger("glint.llm")


class LLMError(Exception):
    """LLM 调用失败"""
    pass


class LLMQuotaExceeded(LLMError):
    """当前用户超过 LLM 使用额度"""
    pass


_usage_context = ContextVar("llm_usage_context", default={})

# 最近一次流式调用的结束原因。用 ContextVar 而不是全局变量,
# 保证并发请求之间互不干扰。
_last_stop_reason: ContextVar[Optional[str]] = ContextVar(
    "llm_last_stop_reason", default=None
)


def was_truncated() -> bool:
    """上一次 chat_stream 是否因为长度上限被上游截断。

    调用方在流结束后立即查询;半截回复不能当成完整回复交给用户。
    """
    return _last_stop_reason.get() == "max_tokens"


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
    stream: bool = False,
    model: Optional[str] = None,
) -> Dict:
    payload = {
        "model": model or settings.LLM_MODEL,
        "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
        "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
        "messages": messages,
        "stream": stream
    }
    if system:
        payload["system"] = system
    return payload


def _is_retryable_status(status_code: int) -> bool:
    """5xx 与 429 多为网关瞬时故障（如 524 网关超时），重试有意义；
    4xx 其余为请求本身问题，重试只会重复失败。"""
    return status_code == 429 or status_code >= 500


def _is_retryable_request_error(exc: httpx.RequestError) -> bool:
    """读超时说明模型本身就慢，重试只会把等待时间翻倍并冲破前端超时；
    连接类错误失败得快，重试划算。"""
    return not isinstance(exc, httpx.ReadTimeout)


async def chat_complete(
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    timeout: Optional[float] = None,
    model: Optional[str] = None,
) -> str:
    """
    一次性获取完整回复
    messages 格式: [{"role": "user"|"assistant", "content": "..."}]
    网关瞬时故障(5xx/429/网络错误)会自动重试 LLM_MAX_RETRIES 次。
    """
    if not settings.LLM_API_KEY:
        raise LLMError("LLM_API_KEY 未配置")

    url = f"{settings.LLM_BASE_URL}/messages"
    payload = _build_payload(messages, system, max_tokens, temperature, stream=False, model=model)
    estimated_prompt_tokens = _enforce_usage_quota(messages, system, payload)
    request_timeout = timeout if timeout is not None else settings.LLM_TIMEOUT_SECONDS

    last_error = ""
    resp = None
    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        is_last = attempt == settings.LLM_MAX_RETRIES
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            try:
                resp = await client.post(url, headers=_build_headers(), json=payload)
                resp.raise_for_status()
                break
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                if is_last or not _is_retryable_status(e.response.status_code):
                    _record_usage(
                        payload=payload,
                        prompt_tokens=estimated_prompt_tokens,
                        completion_tokens=0,
                        status="error",
                        error_message=last_error,
                    )
                    raise LLMError(f"LLM {last_error}")
            except httpx.RequestError as e:
                last_error = f"网络错误: {e}"
                if is_last or not _is_retryable_request_error(e):
                    _record_usage(
                        payload=payload,
                        prompt_tokens=estimated_prompt_tokens,
                        completion_tokens=0,
                        status="error",
                        error_message=last_error,
                    )
                    raise LLMError(f"LLM {last_error}")
        logger.warning("llm_retry", extra={
            "attempt": attempt + 1,
            "model": payload.get("model", ""),
            "error": last_error,
        })

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
    timeout: Optional[float] = None,
    model: Optional[str] = None,
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

    仅在「尚未吐出任何文本」时重试:已经流给用户的内容不能重来,
    否则用户会看到重复的半截回复。
    """
    if not settings.LLM_API_KEY:
        raise LLMError("LLM_API_KEY 未配置")

    # 每次调用先清掉上一次的结束原因,避免串味
    _last_stop_reason.set(None)

    url = f"{settings.LLM_BASE_URL}/messages"
    payload = _build_payload(messages, system, max_tokens, temperature, stream=True, model=model)
    estimated_prompt_tokens = _enforce_usage_quota(messages, system, payload)
    request_timeout = timeout if timeout is not None else settings.LLM_TIMEOUT_SECONDS
    prompt_tokens = estimated_prompt_tokens
    completion_tokens = 0
    text_parts: List[str] = []
    stop_reason: Optional[str] = None
    completed = False

    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        is_last = attempt == settings.LLM_MAX_RETRIES
        retryable_error = None
        # 流式请求的超时语义和普通请求不同:read 超时应当约束"两个数据块之间
        # 的静默时长",而不是整段回复的总时长。传一个裸 float 会让 httpx 把它
        # 用作每一步的超时,长回复写到一半就被掐断 —— 用户看到的就是半句话。
        # 因此显式放宽 read,connect/write 仍保持原值。
        stream_timeout = httpx.Timeout(
            request_timeout,
            read=max(request_timeout, settings.LLM_STREAM_READ_TIMEOUT_SECONDS),
        )
        async with httpx.AsyncClient(timeout=stream_timeout) as client:
            try:
                async with client.stream(
                    "POST", url, headers=_build_headers(), json=payload
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        body_text = body.decode("utf-8", "ignore")[:200]
                        message = f"HTTP {resp.status_code}: {body_text}"
                        if not is_last and _is_retryable_status(resp.status_code):
                            retryable_error = message
                        else:
                            _record_usage(
                                payload=payload,
                                prompt_tokens=estimated_prompt_tokens,
                                completion_tokens=0,
                                status="error",
                                error_message=message,
                            )
                            raise LLMError(f"LLM {message}")

                    if retryable_error is None:
                        async for raw_line in resp.aiter_lines():
                            if not raw_line:
                                continue
                            line = raw_line.strip()
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
                                # 结束原因:上游可能在 max_tokens 处硬截断。
                                # 不记下来的话,半截回复会被当成正常回复发给用户,
                                # 用户看到的就是一句话说到一半没了(且毫无提示)。
                                elif data.get("type") == "message_delta":
                                    reason = (data.get("delta") or {}).get("stop_reason")
                                    if reason:
                                        stop_reason = reason
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
                                    raise LLMError(message)
                        completed = True
            except httpx.RequestError as e:
                message = f"网络错误: {e}"
                # 已经吐字了就不能重来,直接报错让上层兜底
                if is_last or text_parts or not _is_retryable_request_error(e):
                    _record_usage(
                        payload=payload,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens or llm_usage_service.estimate_text_tokens("".join(text_parts)),
                        status="error",
                        error_message=message,
                    )
                    raise LLMError(f"LLM {message}")
                retryable_error = message

        if completed:
            break
        logger.warning("llm_stream_retry", extra={
            "attempt": attempt + 1,
            "model": payload.get("model", ""),
            "error": retryable_error or "",
        })

    if completed:
        if stop_reason == "max_tokens":
            # 上游在长度上限处硬截断。异步生成器没法优雅地返回值,
            # 用 ContextVar 把状态交给调用方(见 was_truncated),
            # 由它决定是提示用户还是续写 —— 但绝不能装作回复是完整的。
            _last_stop_reason.set(stop_reason)
            logger.warning("llm_stream_truncated", extra={
                "model": payload.get("model", ""),
                "completion_tokens": completion_tokens,
                "max_tokens": payload.get("max_tokens"),
            })
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
