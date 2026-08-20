"""
简历生成服务 —— 从对话历史/抽取的 profile 重塑成专业简历 JSON
"""
import asyncio
import json
import logging
import re
from typing import Dict, List, Optional

from app.core.prompts import STAR_L_REWRITE_PROMPT, UPLOAD_RESUME_EVAL_PROMPT
from app.services import llm_service
from app.services.dialog_service import extract_profile, _strip_code_fence
from app.mock.fallback import mock_resume, mock_quality_report

logger = logging.getLogger("glint.resume")


# ====== 1. 基于对话历史生成简历 ======

async def generate_resume_from_session(
    session_id: str,
    target_job: str = "",
    user_id: Optional[str] = None,
) -> Dict:
    """
    full pipeline:
      优先使用 session.extracted(增量提取的数据),兜底才用 extract_profile
    """
    logger.info("generate_resume_start", extra={"session_id": session_id, "target_job": target_job})

    # 优先用增量提取的数据
    from app.store.db_store import session_store
    session = session_store.get(session_id, user_id)
    extracted = session.get("extracted", {}) if session else {}

    if extracted and (extracted.get("fullname") or extracted.get("education") or extracted.get("experiences")):
        logger.info("generate_resume_use_extracted", extra={"keys": list(extracted.keys())})
        profile = {
            "fullname": extracted.get("fullname", ""),
            "target_job": target_job,
            "phone": extracted.get("phone", ""),
            "email": extracted.get("email", ""),
            "location": extracted.get("location", ""),
            "education": extracted.get("education", []),
            "experiences": extracted.get("experiences", []),
            "skills": extracted.get("skills", {}),
            "awards": extracted.get("awards", []),
            "self_evaluation": extracted.get("self_evaluation", "")
        }
        # 增量提取只在 AI 做 recap 时触发,用户在 AI 追问细节的中途点"生成"时
        # experiences 会是空的。此时改用完整对话历史再提取一次,
        # 避免明明聊过经历却拿到示例简历。
        if not profile["experiences"]:
            logger.info("generate_resume_reextract_for_experiences")
            recovered = await extract_profile(session_id, user_id)
            if recovered.get("experiences"):
                profile["experiences"] = recovered["experiences"]
                # 对话里聊到但增量提取漏掉的字段一并补齐
                for key in ("fullname", "phone", "email", "location", "education", "skills", "awards"):
                    if not profile.get(key) and recovered.get(key):
                        profile[key] = recovered[key]
    else:
        # 兜底:用完整对话历史提取
        logger.info("generate_resume_fallback_extract")
        profile = await extract_profile(session_id, user_id)
        if not profile:
            logger.warning("generate_resume_empty_profile")
            return _empty_resume(target_job)

    logger.info("generate_resume_profile_ready", extra={"keys": list(profile.keys())})
    resume = {
        "basic": {
            "fullname": profile.get("fullname", ""),
            "target_job": profile.get("target_job") or target_job,
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "location": profile.get("location", "")
        },
        "education": _normalize_education(profile.get("education", [])),
        "experiences": await _rewrite_experiences(profile.get("experiences", [])),
        "skills": _normalize_skills(profile.get("skills", {})),
        "awards": profile.get("awards", []),
        "self_evaluation": profile.get("self_evaluation") or _build_self_eval(profile)
    }
    logger.info("generate_resume_done", extra={
        "fullname": resume["basic"]["fullname"],
        "experience_count": len(resume["experiences"]),
    })
    return resume


def _empty_resume(target_job: str) -> Dict:
    return {
        "basic": {
            "fullname": "",
            "target_job": target_job or "未指定",
            "email": "",
            "phone": "",
            "location": ""
        },
        "education": [],
        "experiences": [],
        "skills": {"technical": [], "product": [], "soft": []},
        "awards": [],
        "self_evaluation": "暂未生成自我评价。"
    }


def _normalize_education(items: List[Dict]) -> List[Dict]:
    out = []
    for ed in items or []:
        out.append({
            "school": ed.get("school", ""),
            "major": ed.get("major", ""),
            "degree": ed.get("degree", ""),
            "period": ed.get("period", ""),
            "gpa": ed.get("gpa", ""),
            "highlights": ed.get("highlights", [])
        })
    return out


def _normalize_skills(skills: Dict) -> Dict:
    if isinstance(skills, list):
        return {"technical": list(skills), "product": [], "soft": []}
    return {
        "technical": skills.get("technical", []) or [],
        "product": skills.get("product", []) or [],
        "soft": skills.get("soft", []) or []
    }


def _build_self_eval(profile: Dict) -> str:
    """根据 profile 生成简短自评(不依赖 LLM,避免再多花一次调用)"""
    job = profile.get("target_job", "")
    exps = profile.get("experiences", [])
    skills_tech = profile.get("skills", {}).get("technical", [])

    if not exps:
        return f"具备 {job or '相关方向'} 所需的学习能力与执行力,期待在实践中持续成长。"

    # 根据经历数量和技能栈生成更个性化的自评
    exp_count = len(exps)
    has_tech = len(skills_tech) > 0

    if exp_count >= 2 and has_tech:
        return (
            f"具备扎实的 {job or '相关领域'} 实践能力,能够主导从问题分析到方案落地的完整流程。"
            f"善于在跨团队协作中创造价值,持续追求专业成长。"
        )
    elif exp_count >= 2:
        return f"拥有多段 {job or '相关'} 项目经历,具备良好的执行力与团队协作能力,期待在实践中持续提升。"
    else:
        return f"具备 {job or '相关方向'} 基础实践经验,学习能力强,善于快速上手新技术,期待在团队中创造价值。"



async def _rewrite_experiences(experiences: List[Dict]) -> List[Dict]:
    """对每段经历并行调 LLM 做 STAR-L 重塑。
    各段经历相互独立,并行执行可把总耗时从「N 段之和」降到「最慢一段」,
    避免段数多时整体生成超过前端请求超时。"""
    exps = experiences or []
    # _rewrite_one 内部已自带兜底,不会抛异常,gather 不会因单段失败而整体失败
    rewrites = await asyncio.gather(
        *[_rewrite_one(exp, exp.get("star_l") or {}) for exp in exps]
    )
    out = []
    for idx, (exp, rewritten) in enumerate(zip(exps, rewrites)):
        out.append({
            "id": f"exp_{idx + 1:03d}",
            "title": exp.get("title", "项目经历"),
            "type": exp.get("type", "other"),
            "role": exp.get("role", ""),
            "period": exp.get("period", ""),
            "bullets": rewritten.get("bullets", []),
            "tag": _build_tag(rewritten.get("包装度", 1.0))
        })
    return out


async def _rewrite_one(exp: Dict, star: Dict) -> Dict:
    prompt = STAR_L_REWRITE_PROMPT.format(
        title=exp.get("title", ""),
        role=exp.get("role", ""),
        raw_text=exp.get("raw_text", ""),
        situation=star.get("situation", ""),
        task=star.get("task", ""),
        action=star.get("action", ""),
        result=star.get("result", ""),
        learning=star.get("learning", "")
    )
    try:
        raw = await llm_service.chat_complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        return json.loads(_strip_code_fence(raw))
    except (llm_service.LLMError, json.JSONDecodeError):
        # 失败兜底:直接用原话拼几行
        fallback = []
        for k in ("situation", "task", "action", "result", "learning"):
            v = star.get(k)
            if v:
                fallback.append(v)
        return {"bullets": fallback[:4] or [exp.get("raw_text", "")], "包装度": 1.0}


def _build_tag(pack_level: float) -> Dict:
    if pack_level < 1.3:
        return {"label": "基于真实经历重塑", "level": "high", "color": "green"}
    if pack_level < 1.6:
        return {"label": "基于真实经历拔高", "level": "medium", "color": "yellow"}
    return {"label": "需进一步核实", "level": "low", "color": "yellow"}


# ====== 2. 上传 PDF 文本 → 简历 + 质量报告 ======

async def evaluate_uploaded_text(text: str, file_name: str = "uploaded.pdf") -> Dict:
    """
    PDF 解析出的 text 直接送 LLM,一次产出 resume + quality_report
    失败时退化为 mock
    """
    prompt = UPLOAD_RESUME_EVAL_PROMPT.format(resume_text=text[:6000])
    try:
        raw = await llm_service.chat_complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        data = json.loads(_strip_code_fence(raw))
        # 标记来源
        if "quality_report" in data:
            data["quality_report"]["from_upload"] = True
            data["quality_report"]["source_file"] = file_name
        return data
    except (llm_service.LLMError, json.JSONDecodeError):
        # 兜底
        return {
            "resume": mock_resume(),
            "quality_report": mock_quality_report(from_upload=True, source_file=file_name)
        }
