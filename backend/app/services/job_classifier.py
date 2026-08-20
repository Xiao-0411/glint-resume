"""岗位分类专用的 AI 客户端。

与 app/services/llm_service 刻意保持独立：
- 分类是离线批处理，不需要流式、不计入用户配额、不受用户级限流影响；
- 允许指向与主站不同的服务商和模型（便宜的小模型足够做分类）。

协议为 Anthropic Messages 格式：
    POST {JOB_CLASSIFIER_BASE_URL}/messages
    headers: Content-Type / anthropic-version / Authorization: Bearer <KEY>

配置项（写在 backend/.env）：
    JOB_CLASSIFIER_BASE_URL   接口根地址，例如 https://docs.newapi.pro/v1
    JOB_CLASSIFIER_API_KEY    鉴权 Key
    JOB_CLASSIFIER_MODEL      模型名，例如 claude-3-opus-20240229
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

from app.core.logging_config import get_logger

logger = get_logger("glint.job_classifier")


class ClassifierNotConfigured(RuntimeError):
    """未填写接口地址或 Key。"""


class ClassifierError(RuntimeError):
    """调用失败或返回无法解析。"""


# 岗位大类。AI 必须从中选择，避免自由发挥导致同义类目散落
# （"后端"/"服务端"/"Java开发" 指向同一类却无法聚合）。
JOB_CATEGORIES = [
    "后端开发", "前端开发", "移动开发", "测试", "运维/SRE", "数据开发",
    "算法/AI", "安全", "硬件/嵌入式", "技术管理",
    "产品经理", "产品运营", "用户运营", "内容运营", "电商运营", "市场/品牌",
    "销售", "客服", "人力资源", "财务/审计", "法务", "行政",
    "UI/UX设计", "视觉/平面设计", "项目管理", "供应链/物流", "生产制造",
    "医疗/生物", "教育/培训", "金融/投资", "咨询", "其他",
]

EXPERIENCE_LEVELS = ["实习", "应届", "初级", "中级", "高级", "专家", "管理", "不限"]

SYSTEM_PROMPT = """你是招聘数据的分类引擎。根据岗位信息，为每个岗位输出结构化标签。

要求：
1. category 必须从给定类目中选一个最贴切的，不要自创；无法判断填"其他"。
2. skills 提取 3-8 个具体技术栈或专业能力关键词，只保留岗位真正要求的，不要臆造。
3. level 从给定职级中选一个。
4. industry 用 2-6 字概括所属行业，如"金融科技""跨境电商"；无法判断填"通用"。
5. 严格输出 JSON 数组，不要任何解释文字、不要 markdown 代码块。
6. 输出数组的长度和顺序必须与输入岗位完全一致，用 id 字段对应。"""


def _config() -> tuple[str, str, str]:
    base_url = os.getenv("JOB_CLASSIFIER_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("JOB_CLASSIFIER_API_KEY", "").strip()
    model = os.getenv("JOB_CLASSIFIER_MODEL", "").strip()
    missing = [
        name for name, value in (
            ("JOB_CLASSIFIER_BASE_URL", base_url),
            ("JOB_CLASSIFIER_API_KEY", api_key),
            ("JOB_CLASSIFIER_MODEL", model),
        ) if not value
    ]
    if missing:
        raise ClassifierNotConfigured(f"岗位分类接口未配置: {'、'.join(missing)}")
    return base_url, api_key, model


def is_configured() -> bool:
    try:
        _config()
        return True
    except ClassifierNotConfigured:
        return False


def _job_brief(index: int, job: dict) -> dict:
    """压缩岗位信息，只发分类必需的字段，控制 token 成本。"""
    description = str(job.get("description") or "").strip()
    return {
        "id": index,
        "title": str(job.get("title") or "").strip()[:80],
        "company": str(job.get("company") or "").strip()[:40],
        "tags": [str(t).strip() for t in (job.get("tags") or [])][:6],
        # JD 往往数千字，取前段足以判断类目与技能栈。
        "jd": description[:600],
    }


def _extract_json_array(text: str) -> list:
    """从模型回复中取出 JSON 数组，容忍 markdown 包裹和前后缀说明。"""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    if not cleaned.startswith("["):
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start == -1 or end <= start:
            raise ClassifierError(f"返回内容不含 JSON 数组: {text[:200]}")
        cleaned = cleaned[start:end + 1]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ClassifierError(f"JSON 解析失败: {exc}; 原文: {text[:200]}") from exc
    if not isinstance(parsed, list):
        raise ClassifierError("返回的 JSON 不是数组")
    return parsed


def _normalize(item: Any) -> dict:
    """把模型输出规整为固定形状，非法值回落到安全默认。"""
    if not isinstance(item, dict):
        return {}
    category = str(item.get("category") or "").strip()
    level = str(item.get("level") or "").strip()
    skills = item.get("skills")
    if isinstance(skills, str):
        skills = [part.strip() for part in skills.split(",")]
    skills = [str(s).strip() for s in (skills or []) if str(s).strip()][:8]
    return {
        "category": category if category in JOB_CATEGORIES else "其他",
        "skills": skills,
        "level": level if level in EXPERIENCE_LEVELS else "不限",
        "industry": (str(item.get("industry") or "").strip() or "通用")[:12],
    }


def _post(payload: dict, timeout: float) -> str:
    base_url, api_key, _ = _config()
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": os.getenv("JOB_CLASSIFIER_ANTHROPIC_VERSION", "2023-06-01"),
        "Authorization": f"Bearer {api_key}",
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url}/messages", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    blocks = data.get("content") or []
    text = "".join(
        str(block.get("text") or "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") in ("text", "string", None)
    ).strip()
    if not text:
        raise ClassifierError(f"接口返回空内容: {str(data)[:200]}")
    return text


def classify_batch(jobs: list[dict], *, timeout: float = 90.0, retries: int = 2) -> list[dict]:
    """批量分类。返回与 jobs 等长的结果列表，失败项为空字典。

    不抛异常给调用方的分类失败场景：整批失败时返回全空，由调用方决定
    是照常入库（category 留空，等后续补分类）还是丢弃。
    """
    if not jobs:
        return []

    briefs = [_job_brief(i, job) for i, job in enumerate(jobs)]
    _, _, model = _config()
    payload = {
        "model": model,
        "max_tokens": min(400 + 120 * len(jobs), 8000),
        "system": SYSTEM_PROMPT,
        "messages": [{
            "role": "user",
            "content": (
                f"可选类目：{json.dumps(JOB_CATEGORIES, ensure_ascii=False)}\n"
                f"可选职级：{json.dumps(EXPERIENCE_LEVELS, ensure_ascii=False)}\n\n"
                f"待分类岗位：\n{json.dumps(briefs, ensure_ascii=False)}\n\n"
                '输出格式：[{"id":0,"category":"...","skills":["..."],"level":"...","industry":"..."}]'
            ),
        }],
    }

    last_error = ""
    for attempt in range(retries + 1):
        try:
            parsed = _extract_json_array(_post(payload, timeout))
            results: list[dict] = [{} for _ in jobs]
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                try:
                    index = int(item.get("id", -1))
                except (TypeError, ValueError):
                    continue
                if 0 <= index < len(jobs):
                    results[index] = _normalize(item)
            filled = sum(1 for r in results if r)
            logger.info("job_classify_batch", extra={"total": len(jobs), "classified": filled})
            return results
        except (httpx.HTTPError, ClassifierError) as exc:
            last_error = str(exc)
            if attempt < retries:
                # 网关限流时退避重试；分类是离线任务，等待成本低于丢数据。
                time.sleep(2.0 * (attempt + 1))

    logger.error("job_classify_failed", extra={"total": len(jobs), "error": last_error[:300]})
    return [{} for _ in jobs]


def classify_all(jobs: list[dict], *, batch_size: int = 20, **kwargs) -> list[dict]:
    """按批切分后分类，避免单次请求过大导致超时或截断。"""
    results: list[dict] = []
    for start in range(0, len(jobs), batch_size):
        results.extend(classify_batch(jobs[start:start + batch_size], **kwargs))
    return results


def apply_classification(job: dict, result: dict) -> dict:
    """把分类结果合并进岗位记录。

    skills 同时并入 requirements：匹配度打分读的是 requirements，
    AI 提取的技能比平台原始标签更规整。
    """
    if not result:
        return job
    merged = dict(job)
    merged["category"] = result.get("category", "")
    merged["job_level"] = result.get("level", "")
    merged["industry"] = result.get("industry", "")
    skills = result.get("skills") or []
    if skills:
        existing = [str(r).strip() for r in (merged.get("requirements") or []) if str(r).strip()]
        seen = {item.lower() for item in existing}
        merged["requirements"] = existing + [s for s in skills if s.lower() not in seen]
    return merged
