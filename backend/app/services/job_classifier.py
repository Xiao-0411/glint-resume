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
2. skills 只提取 3-8 个「可写进简历的专业能力或技术栈」，例如 Java、Spring、
   需求分析、用户研究、财务报表。必须严格遵守：
   - 只有在岗位信息中明确出现时才提取；信息不足就少给几个，甚至给空数组。
   - 绝不把招聘话术当技能。以下都不是技能，一律不要输出：
     薪酬福利（高底薪、五险一金、包吃住、双休、不加班）、
     工作条件（坐班、上海九亭、稳定全职、可带团队、定期团建）、
     招聘对象（无经验应届生、实习生、退役军人、计算机相关专业）、
     公司卖点（快速晋升、扁平管理、大厂背景）。
   - 岗位页上的分类勾选项不是技能。当出现形如
     "B端产品/C端产品/G端产品/物联网产品/电商产品" 这样成组罗列的选项时，
     说明那是平台的分类菜单而非岗位要求，最多保留一个最贴切的，其余丢弃。
   - 单个技能不超过 12 个字，不要写成短句。
3. level 从给定职级中选一个。
4. industry 用 2-6 字概括所属行业，如"金融科技""跨境电商"；无法判断填"通用"。
5. 严格输出 JSON 数组，不要任何解释文字、不要 markdown 代码块。
6. 输出数组的长度和顺序必须与输入岗位完全一致，用 id 字段对应。"""

# 招聘话术特征。这些词出现在"技能"里说明模型把卖点当成了能力要求，
# 放进 requirements 会直接污染匹配度打分，必须在入库前拦掉。
SKILL_NOISE_PATTERNS = (
    "五险", "公积金", "双休", "包吃", "包住", "加班", "底薪", "提成", "薪资", "月薪",
    "年薪", "补贴", "团建", "晋升", "福利", "全职", "兼职", "坐班", "外呼", "带团队",
    "应届生", "实习生", "退役军人", "相关专业", "优先", "稳定", "急招", "长期",
    "工作时间", "上班", "居住", "户口", "年龄",
)


def _looks_like_noise(skill: str) -> bool:
    """判断一个"技能"其实是招聘话术或岗位分类选项。"""
    value = skill.strip()
    if not value:
        return True
    if any(sep in value for sep in ("，", ",", "、", "；", ";")):
        # 技能是单一名词，含分隔符说明是被塞进来的一句话。
        return True
    if any(pattern in value for pattern in SKILL_NOISE_PATTERNS):
        return True
    # 长度上限按字符类型区分：中文技能名普遍很短，超过 12 字多为整句卖点；
    # 但英文技术栈常见更长的单词（Elasticsearch=13、CircleCI/Kubernetes 等），
    # 用统一阈值会误杀，因此仅对含中文的条目收紧。
    has_chinese = any("一" <= char <= "鿿" for char in value)
    limit = 12 if has_chinese else 24
    return len(value) > limit



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
    # 即便 prompt 已明确禁止，模型仍可能把招聘话术写进 skills；
    # requirements 直接参与匹配度打分，这里再兜一道，宁缺毋滥。
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in (skills or []):
        value = str(raw).strip()
        if not value or _looks_like_noise(value):
            continue
        if value.lower() in seen:
            continue
        seen.add(value.lower())
        cleaned.append(value)
    return {
        "category": category if category in JOB_CATEGORIES else "其他",
        "skills": cleaned[:8],
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
