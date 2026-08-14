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
import asyncio
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
from app.services.skill_extract import extract_skills

logger = logging.getLogger("glint.job_adapt")

# 送进 prompt 的 JD 描述长度上限。JD 正文常有大段公司介绍和福利,
# 截断既省 token 也能减少无关信息干扰改写。
MAX_JD_CHARS = 800

# 单次最多改写多少条 bullet。超长简历全量送进去容易触发输出截断,
# 而且 HR 实际也只看前几条。
MAX_BULLETS = 24


class AdaptError(Exception):
    """适配无法完成(缺简历、缺岗位等),由调用方转成对用户可读的提示"""


def _collect_bullets(resume: Dict) -> List[Tuple[int, int, str]]:
    """
    取出所有 bullet,附带定位信息。

    返回 [(经历下标, bullet 下标, 文本)]。定位**用下标而不是 exp.id** ——
    PDF 上传的简历各段 id 可能都是空串,用 id 拼出来的键会重复
    ("#0" 同时指向第一段和第二段的首条),导致改写落到错误的 bullet 上。
    """
    out: List[Tuple[int, int, str]] = []
    for e_idx, exp in enumerate(resume.get("experiences") or []):
        for b_idx, b in enumerate(exp.get("bullets") or []):
            if isinstance(b, str) and b.strip():
                out.append((e_idx, b_idx, b.strip()))
                if len(out) >= MAX_BULLETS:
                    return out
    return out


# 中文数量表述。只查阿拉伯数字挡不住"提升三倍""服务数万用户"这类说法。
#
# 但不能见到中文数字就拦 —— "统一身份认证""一致性""第三方"里的
# 一/三 都不是数量,实测会把正常改写全误伤掉。因此要求数字后面必须跟
# **量词**(倍/万/人/次…)才算数量表述,并单列"第N名"这类排名说法。
_CN_DIGITS = "一二三四五六七八九十百千万亿两"
_CN_QUANT = re.compile(
    rf"(?:数|几)?[{_CN_DIGITS}]+\s*"
    rf"(?:倍|成|余|多|个|人|次|条|项|件|万|亿|千|百|天|周|月|年|分|秒|小时|篇|款|家|台|套|张|单)"
    # "数万用户""数十人"里,量词本身就是万/十,后面不再跟量词。
    # 单列这一类:必须以"数/几"开头,避免误伤"万事俱备"这类成语。
    rf"|(?:数|几)[{_CN_DIGITS}]+"
)
# 排名/名次:"第一名""第二"。要求带名次量词,否则 "第三方登录" 会被误判 ——
# "第三方" 是名词不是名次。
_CN_RANK = re.compile(rf"第\s*[{_CN_DIGITS}]+\s*(?:名|位|届|等奖)")
# 夸张的成果断言,原文没有就不该冒出来
_CLAIM_WORDS = (
    "冠军", "金奖", "特等奖", "一等奖", "满分", "最佳",
    "翻倍", "数倍", "成倍", "大幅", "显著", "极大",
)

# 通用工作方法,不算"可造假的资历"。写进改写里不构成虚假陈述
# (说自己"设计了测试用例"和说自己"精通 Kubernetes"不是一回事),
# 因此不纳入技能白名单校验,否则正常改写会被大面积误伤。
_GENERIC_SKILLS = {
    "测试用例", "需求分析", "项目管理", "团队协作", "沟通能力",
    "数据分析", "竞品分析", "市场调研", "数据复盘", "接口测试",
}


def _has_invented_claim(original: str, adapted: str, allowed_skills: set) -> Optional[str]:
    """
    改写是否引入了原文不存在的事实。返回违规说明,合规返回 None。

    LLM 越界不止"补一个数字"这一种。实测还会:把"三倍""数万"这类中文数量词
    写进去、给用户安上简历里没有的技能(Kubernetes)、公司(字节跳动)、
    头衔(技术负责人),以及"获得第一名"这种成果断言。逐类检查:

    1. 阿拉伯数字:改写里出现原文没有的数字串即判违规。
    2. 中文数字:逐个词比对,改写里出现原文没有的中文数量词即判违规。
    3. 成果断言词:原文没有而改写有,判违规。
    4. 技能词:改写提到的**硬技能**必须在原 bullet 或用户技能清单里出现过 ——
       允许把用户真会的技能说得更醒目,但不能凭空安上他不会的。
       通用工作方法类词汇(测试用例、需求分析、团队协作…)不在此列:
       它们描述的是做事方式而非可造假的资历,拦下来只会误伤正常改写。

    公司名/头衔无法穷举,靠 prompt 约束 + 上面几类兜底;
    真出现时通常会连带触发数量表述或断言词。
    """
    orig_nums = set(re.findall(r"\d+\.?\d*", original or ""))
    for num in re.findall(r"\d+\.?\d*", adapted or ""):
        if num not in orig_nums:
            return f"引入了原文没有的数字「{num}」"

    for pattern, label in ((_CN_QUANT, "数量表述"), (_CN_RANK, "名次表述")):
        orig_hits = set(pattern.findall(original or ""))
        for hit in pattern.findall(adapted or ""):
            if hit not in orig_hits:
                return f"引入了原文没有的{label}「{hit}」"

    for word in _CLAIM_WORDS:
        if word in (adapted or "") and word not in (original or ""):
            return f"引入了原文没有的断言「{word}」"

    for skill in extract_skills(adapted or ""):
        if skill not in allowed_skills and skill not in _GENERIC_SKILLS:
            return f"引入了简历中不存在的技能「{skill}」"

    return None


def _apply_rewrites(
    resume: Dict,
    rewrites: List[Dict],
    bullets: List[Tuple[int, int, str]],
    allowed_skills: set,
) -> Tuple[Dict, List[Dict], List[Dict]]:
    """
    把 LLM 的改写落到简历副本上,并逐条校验。

    返回 (适配后简历, 生效的改动, 被拒绝的改动)。判定为编造的改写会被丢弃,
    原文保持不变 —— 宁可少改,不能造假。
    """
    adapted = deepcopy(resume)
    exps = adapted.get("experiences") or []
    index = {f"{e}#{b}": (e, b, text) for e, b, text in bullets}
    applied: List[Dict] = []
    rejected: List[Dict] = []

    for item in rewrites or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or "").strip()
        new_text = str(item.get("adapted") or "").strip()
        located = index.get(key)
        if not located or not new_text:
            continue
        e_idx, b_idx, original = located
        if new_text == original:
            continue

        violation = _has_invented_claim(original, new_text, allowed_skills)
        if violation:
            logger.warning(
                "job_adapt_rejected_rewrite",
                extra={"bullet": key, "reason": violation, "adapted": new_text[:80]},
            )
            rejected.append({"original": original, "adapted": new_text, "reason": violation})
            continue

        if e_idx < len(exps):
            exp = exps[e_idx]
            bl = exp.get("bullets") or []
            if b_idx < len(bl):
                bl[b_idx] = new_text
                applied.append({
                    "expIndex": e_idx,
                    "bulletIndex": b_idx,
                    "expTitle": exp.get("title", ""),
                    "original": original,
                    "adapted": new_text,
                    "reason": str(item.get("reason") or "").strip(),
                })

    return adapted, applied, rejected


def _build_sections(original: Dict, adapted: Dict, applied: List[Dict]) -> List[Dict]:
    """
    构造前端 diff 展示用的分节结构。

    字段形状沿用原 mock 的约定(name / changes[{type, text|original+adapted}]),
    前端 DashboardView 的 diff 渲染逻辑无需改动。
    """
    # 用(经历下标, bullet 下标)定位,不能用文本 —— 同一段里出现两条一样的
    # bullet 时,按文本匹配会把两条都标成"已改",其中一条其实没动。
    changed = {(c["expIndex"], c["bulletIndex"]) for c in applied}
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
    orig_exps = original.get("experiences") or []
    adapt_exps = adapted.get("experiences") or []
    for e_idx, oe in enumerate(orig_exps):
        ae = adapt_exps[e_idx] if e_idx < len(adapt_exps) else oe
        head = "  |  ".join(
            str(oe.get(k, "")) for k in ("title", "role", "period") if oe.get(k)
        )
        if head:
            exp_changes.append({"type": "unchanged", "text": head})
        o_bullets = oe.get("bullets") or []
        a_bullets = ae.get("bullets") or []
        for b_idx, ob in enumerate(o_bullets):
            ab = a_bullets[b_idx] if b_idx < len(a_bullets) else ob
            if (e_idx, b_idx) in changed and ab != ob:
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
    bullets: List[Tuple[int, int, str]],
    resume_skills: List[str],
    missing_skills: List[str],
) -> Dict:
    """调 LLM 拿改写建议。失败时抛 LLMError,由调用方决定降级策略。"""
    bullets_block = "\n".join(
        f"{e_idx}#{b_idx}: {text}" for e_idx, b_idx, text in bullets
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
    payload = json.loads(_strip_code_fence(raw))
    if not isinstance(payload, dict):
        # json.loads 对 '["x"]' / '"none"' / '42' 都会成功,但后续 .get 会炸成 500。
        # 统一按"LLM 输出格式不对"处理,让上层返回可重试的 503。
        raise llm_service.LLMError("适配结果格式异常")
    return payload


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

    # 允许出现在改写里的技能 = 用户已有的技能 + 各条原文里本来就提到的。
    # 超出这个集合就是给用户安上他不会的东西。
    allowed_skills = set(skills.proven) | set(skills.listed)
    for _, _, text in bullets:
        allowed_skills.update(extract_skills(text))

    adapted, applied, rejected = _apply_rewrites(
        resume, payload.get("rewrites"), bullets, allowed_skills
    )

    # 前后分数都用真实评分算,不是常量。
    # 两次评分互不依赖,并发跑把耗时从"两次之和"压到"较慢的一次"
    # (每次内部都要调一次 LLM 评语言专业度)。
    if applied:
        original_report, adapted_report = await asyncio.gather(
            score_fn(resume, target_job),
            score_fn(adapted, target_job),
        )
    else:
        original_report = await score_fn(resume, target_job)
        adapted_report = original_report
    after = match_resume_to_job(extract_resume_skills(adapted), job, profile)

    changes = [str(s).strip() for s in (payload.get("summary") or []) if str(s).strip()]
    if not applied:
        # 区分两种"没改动":简历本就贴合,和改写越界被拦下。
        # 后者不能说成"无需调整",否则用户以为简历没问题。
        if rejected:
            changes = [f"AI 的改写引入了简历中不存在的内容（{rejected[0]['reason']}），已全部拒绝；原文保持不变"]
        else:
            changes = ["当前简历已较贴合该岗位，无需调整表述"]
    elif rejected:
        changes.append(f"另有 {len(rejected)} 条改写因引入不实内容被拒绝")

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
