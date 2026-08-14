"""
岗位定向适配 —— 用用户**真实简历**对着**真实 JD** 做改写

替代原先的 `mock_adapt_resume`。旧实现的问题不是"不够好",而是它整个
是假的:拿内置示例简历(mock_resume)对着硬编码的示例岗位(JOB_DATABASE[0])
算分,返回写死的 62→74,却在界面上显示成"你的简历质量分"。用户投递的
job_id 和他本人的简历都没被读过。

现在:
- 简历来自 resumes 表(用户最近一份)
- 岗位来自 jobs 表(爬虫抓的真实 JD)
- 改写由 LLM 完成,但**只允许改措辞、不允许造经历**(见 JOB_ADAPT_PROMPT),
  返回后还要逐条校验,凭空多出来的数字会被打回原文
- 前后分数用 evaluation_service 真实评分算出来,不是常量
"""
import json
import logging
import re
from copy import deepcopy
from typing import Dict, List, Optional, Tuple

from app.core.prompts import JOB_ADAPT_PROMPT
from app.services import llm_service
from app.services.dialog_service import _strip_code_fence
from app.services.jd_corpus import JobProfile
from app.services.job_match import (
    extract_resume_skills,
    job_required_skills,
    match_resume_to_job,
)
from app.services.scoring_rules import QUANT_WITH_UNIT

logger = logging.getLogger("glint.job_adapt")

# 送进 prompt 的 JD 描述长度上限。JD 正文常有大段公司介绍和福利,
# 截断既省 token 也能减少无关信息干扰改写。
MAX_JD_CHARS = 800

# 单次最多改写多少条 bullet。超长简历全量送进去容易触发输出截断,
# 而且 HR 实际也只看前几条。
MAX_BULLETS = 24


class AdaptError(Exception):
    """适配无法完成(缺简历、缺岗位等),由调用方转成对用户可读的提示"""


def _collect_bullets(resume: Dict) -> List[Tuple[str, int, str]]:
    """
    取出所有 bullet,附带定位信息。

    返回 [(exp_id, bullet_index, text)],exp_id 用简历里的真实 id,
    这样 LLM 回传的编号能精确定位回原位置。
    """
    out: List[Tuple[str, int, str]] = []
    for exp in resume.get("experiences") or []:
        exp_id = exp.get("id") or ""
        for idx, b in enumerate(exp.get("bullets") or []):
            if isinstance(b, str) and b.strip():
                out.append((exp_id, idx, b.strip()))
            if len(out) >= MAX_BULLETS:
                return out
    return out


def _numbers_in(text: str) -> List[str]:
    """取出文本中所有"带量纲的数字",用于校验改写有没有凭空造数据"""
    return QUANT_WITH_UNIT.findall(text or "")


def _has_invented_number(original: str, adapted: str) -> bool:
    """
    改写后是否出现了原文没有的数字。

    LLM 最常见的越界方式就是"顺手补一个漂亮的数据"。这里做保守校验:
    只要改写里出现原文不存在的数字串,就判定为编造。
    (数字换算写法如 "2000万"→"2千万" 也会被拦下,但这种改写本身没价值,
    误伤成本远低于放过一个虚构数据。)
    """
    orig_nums = set(re.findall(r"\d+\.?\d*", original or ""))
    for num in re.findall(r"\d+\.?\d*", adapted or ""):
        if num not in orig_nums:
            return True
    return False


def _apply_rewrites(
    resume: Dict, rewrites: List[Dict], bullets: List[Tuple[str, int, str]]
) -> Tuple[Dict, List[Dict]]:
    """
    把 LLM 的改写落到简历副本上,并逐条校验。

    返回 (适配后简历, 实际生效的改动列表)。被判定为编造的改写会被丢弃,
    原文保持不变 —— 宁可少改,不能造假。
    """
    adapted = deepcopy(resume)
    index = {f"{exp_id}#{idx}": (exp_id, idx, text) for exp_id, idx, text in bullets}
    applied: List[Dict] = []

    for item in rewrites or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or "").strip()
        new_text = str(item.get("adapted") or "").strip()
        located = index.get(key)
        if not located or not new_text:
            continue
        exp_id, idx, original = located
        if new_text == original:
            continue
        if _has_invented_number(original, new_text):
            logger.warning(
                "job_adapt_rejected_invented_number",
                extra={"bullet_id": key, "original": original[:60], "adapted": new_text[:60]},
            )
            continue

        for exp in adapted.get("experiences") or []:
            if (exp.get("id") or "") != exp_id:
                continue
            bl = exp.get("bullets") or []
            if idx < len(bl):
                bl[idx] = new_text
                applied.append({
                    "expId": exp_id,
                    "expTitle": exp.get("title", ""),
                    "original": original,
                    "adapted": new_text,
                    "reason": str(item.get("reason") or "").strip(),
                })
            break

    return adapted, applied


def _build_sections(original: Dict, adapted: Dict, applied: List[Dict]) -> List[Dict]:
    """
    构造前端 diff 展示用的分节结构。

    字段形状沿用原 mock 的约定(name / changes[{type, text|original+adapted}]),
    前端 DashboardView 的 diff 渲染逻辑无需改动。
    """
    changed_keys = {(c["expId"], c["original"]) for c in applied}
    sections: List[Dict] = []

    basic = original.get("basic") or {}
    contact = "  |  ".join(
        str(basic.get(k, "")) for k in ("fullname", "email", "phone") if basic.get(k)
    )
    if contact:
        sections.append({
            "name": "基本信息",
            "changes": [{"type": "unchanged", "text": contact}],
        })

    edu_changes = [
        {
            "type": "unchanged",
            "text": "  ".join(
                str(e.get(k, "")) for k in ("school", "major", "degree", "period") if e.get(k)
            ),
        }
        for e in original.get("education") or []
    ]
    if edu_changes:
        sections.append({"name": "教育背景", "changes": edu_changes})

    exp_changes: List[Dict] = []
    for oe, ae in zip(original.get("experiences") or [], adapted.get("experiences") or []):
        head = "  |  ".join(
            str(oe.get(k, "")) for k in ("title", "role", "period") if oe.get(k)
        )
        if head:
            exp_changes.append({"type": "unchanged", "text": head})
        o_bullets = oe.get("bullets") or []
        a_bullets = ae.get("bullets") or []
        for i, ob in enumerate(o_bullets):
            ab = a_bullets[i] if i < len(a_bullets) else ob
            if ab != ob and (oe.get("id", ""), ob) in changed_keys:
                exp_changes.append({"type": "changed", "original": "• " + ob, "adapted": "• " + ab})
            else:
                exp_changes.append({"type": "unchanged", "text": "• " + ob})
    if exp_changes:
        sections.append({"name": "项目经历", "changes": exp_changes})

    skills = original.get("skills") or {}
    skill_changes = []
    if isinstance(skills, dict):
        for key, label in (("technical", "技术栈"), ("product", "产品能力"), ("soft", "软技能")):
            items = skills.get(key) or []
            if items:
                skill_changes.append({
                    "type": "unchanged",
                    "text": f"{label}：{'、'.join(str(s) for s in items)}",
                })
    if skill_changes:
        sections.append({"name": "技能清单", "changes": skill_changes})

    awards = original.get("awards") or []
    if awards:
        sections.append({
            "name": "获奖荣誉",
            "changes": [{"type": "unchanged", "text": str(a)} for a in awards],
        })

    return sections


async def _request_rewrites(
    resume: Dict,
    job: Dict,
    bullets: List[Tuple[str, int, str]],
    resume_skills: List[str],
    missing_skills: List[str],
) -> Dict:
    """调 LLM 拿改写建议。失败时抛 LLMError,由调用方决定降级策略。"""
    bullets_block = "\n".join(
        f"{exp_id}#{idx}: {text}" for exp_id, idx, text in bullets
    )
    core, desc_only = job_required_skills(job)
    prompt = JOB_ADAPT_PROMPT.format(
        job_title=job.get("title", ""),
        company=job.get("company", ""),
        job_skills="、".join(core + desc_only) or "(JD 未列明)",
        job_description=(job.get("description") or "")[:MAX_JD_CHARS] or "(无描述)",
        bullets_block=bullets_block,
        resume_skills="、".join(resume_skills) or "(未识别到)",
        missing_skills="、".join(missing_skills) or "(无)",
    )
    raw = await llm_service.chat_complete(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return json.loads(_strip_code_fence(raw))


async def adapt_resume_to_job(
    resume: Optional[Dict],
    job: Optional[Dict],
    profile: Optional[JobProfile] = None,
    score_fn=None,
) -> Dict:
    """
    针对指定岗位适配简历。

    score_fn: async (resume, target_job) -> quality_report。注入而不是直接
    import evaluation_service,是为了避免两个模块互相引用
    (evaluation_service 已经依赖 job_match,而这里也要用 job_match)。
    """
    if not resume or not (resume.get("experiences") or []):
        raise AdaptError("还没有可用的简历，请先在「简历锻造」中生成简历")
    if not job:
        raise AdaptError("找不到该职位，可能已下架")

    target_job = job.get("title") or ""
    before = match_resume_to_job(extract_resume_skills(resume), job, profile)

    bullets = _collect_bullets(resume)
    if not bullets:
        raise AdaptError("简历中还没有经历描述，无法进行岗位适配")

    skills = extract_resume_skills(resume)
    payload = await _request_rewrites(
        resume, job, bullets,
        resume_skills=skills.proven + skills.listed,
        missing_skills=before.get("missing") or [],
    )

    adapted, applied = _apply_rewrites(resume, payload.get("rewrites"), bullets)
    proposed = len([r for r in (payload.get("rewrites") or []) if isinstance(r, dict)])

    # 前后分数都用真实评分算,不是常量
    original_report = await score_fn(resume, target_job)
    adapted_report = (
        await score_fn(adapted, target_job) if applied else original_report
    )
    after = match_resume_to_job(extract_resume_skills(adapted), job, profile)

    changes = [str(s).strip() for s in (payload.get("summary") or []) if str(s).strip()]
    if not applied:
        # 区分两种"没改动":简历本就贴合,和改写越界被拦下。
        # 后者不能说成"无需调整",否则用户以为简历没问题。
        if proposed:
            changes = ["AI 给出的改写引入了简历中不存在的数据，已全部拒绝；原文保持不变"]
        else:
            changes = ["当前简历已较贴合该岗位，无需调整表述"]

    advice = str(payload.get("skill_advice") or "").strip()

    return {
        "jobId": job.get("id", ""),
        "jobTitle": target_job,
        "company": job.get("company", ""),
        # 没有实质改动时按"无需修改"展示原简历全文,不画 diff
        "noChange": not applied,
        "adapted": bool(applied),
        "originalScore": original_report.get("total_score", 0),
        "adaptedScore": adapted_report.get("total_score", 0),
        "originalMatchScore": before.get("score"),
        "adaptedMatchScore": after.get("score"),
        "originalResume": resume,
        "adaptedResume": adapted,
        "sections": _build_sections(resume, adapted, applied),
        "changes": changes,
        "appliedRewrites": applied,
        "missingSkills": before.get("missing") or [],
        "skillAdvice": advice,
    }
