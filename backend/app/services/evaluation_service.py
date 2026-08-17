"""
质量评估服务 —— 五维评分(规则 + LLM 混合)
五个维度:完整度、量化度、专业度、匹配度、可信度

评分哲学:零分锚定 + 证据累积。空白简历应当接近 0 分而非"合格",
分数要能真实拉开差距,否则用户看不出改稿前后的区别。
细粒度规则见 app/services/scoring_rules.py。
"""
import json
import re
from typing import Dict, List, Tuple

from app.core.prompts import QUALITY_LLM_PROMPT
from app.services import llm_service
from app.services.dialog_service import _strip_code_fence
from app.services.scoring_rules import (
    QUANT_WITH_UNIT,
    VERB_STRONG,
    VERB_NEUTRAL,
    collect_bullets,
    score_bullet_credibility,
    score_bullet_professional,
    score_bullet_quant,
    tokenize_job,
)

# 加权总分 —— 量化度和专业度是简历质量的主要区分点,完整度只是及格线。
DIMENSION_WEIGHTS = {
    "完整度": 0.15,
    "量化度": 0.30,
    "专业度": 0.25,
    "匹配度": 0.20,
    "可信度": 0.10,
}

# 兼容旧调用:少量地方仍引用 QUANT_PATTERN / PRO_VERBS
QUANT_PATTERN = QUANT_WITH_UNIT
PRO_VERBS = VERB_STRONG | VERB_NEUTRAL


def _score_completeness(resume: Dict) -> Dict:
    """
    完整度:模块齐不齐 + 经历够不够。
    零分锚定,不再给 50 分保底。经历数量是大学生简历的核心短板,
    所以单独按段数梯度给分,而不是"有 1 段就满分"。
    """
    basic = resume.get("basic") or {}
    exps = resume.get("experiences") or []
    skills = resume.get("skills") or {}
    n_exp = len(exps)

    score = 0.0
    # 基本信息:姓名 + 至少一种联系方式
    if basic.get("fullname"):
        score += 8
    if basic.get("phone") or basic.get("email"):
        score += 7
    # 教育背景
    if resume.get("education"):
        score += 15
    # 经历段数:1 段 18 分,梯度递增到 5 段满 40 分
    exp_points = {0: 0, 1: 18, 2: 26, 3: 32, 4: 37}
    score += exp_points.get(n_exp, 40) if n_exp <= 4 else 40
    # 每段经历要有实际内容(bullets),空壳经历不算
    filled = sum(1 for e in exps if (e.get("bullets") or []))
    if n_exp:
        score *= 1.0 if filled == n_exp else max(0.6, filled / n_exp)
    # 技能清单
    tech = skills.get("technical") if isinstance(skills, dict) else None
    if tech:
        score += 12
        if len(tech) >= 5:
            score += 3
    # 获奖
    if resume.get("awards"):
        score += 8
    # 自评仍不加分:自动生成的容易刷分
    score = int(max(0, min(100, round(score))))

    if score >= 85:
        desc = "各模块齐全,结构清晰"
    elif score >= 60:
        desc = "主体结构完整,个别模块可补充"
    elif score >= 35:
        desc = "缺少关键模块,建议先补齐经历与技能"
    else:
        desc = "简历信息过少,请先补充教育背景与经历"
    return {"name": "完整度", "score": score, "max": 100, "desc": desc}


def _score_quantification(resume: Dict) -> Dict:
    """
    量化度:bullets 里有多少真正可衡量的成果。
    旧实现只要句中有数字就算命中(Python3 也算),现在要求数字带量纲,
    并对"显著/大幅"这类假量化倒扣分。
    """
    bullets = collect_bullets(resume)
    if not bullets:
        return {"name": "量化度", "score": 0, "max": 100,
                "desc": "尚无经历内容,无法评估量化程度"}

    per = [score_bullet_quant(b) for b in bullets]
    avg = sum(per) / len(per)
    # 平均分是主体(80%),再给"高质量条目占比"20% 的奖励,
    # 避免所有 bullet 都是 0.6 分的平庸简历和有几条硬成果的简历同分。
    strong_ratio = sum(1 for p in per if p >= 0.8) / len(per)
    score = int(round((avg * 0.8 + strong_ratio * 0.2) * 100))
    score = max(0, min(100, score))

    if score >= 80:
        desc = "成果量化充分,数据支撑有力"
    elif score >= 55:
        desc = "部分经历有数据,仍有条目缺少具体数字"
    elif score >= 25:
        desc = "量化偏少,多数描述停留在做了什么"
    else:
        desc = "几乎没有量化成果,建议补充数字与前后对比"
    return {"name": "量化度", "score": score, "max": 100, "desc": desc}


def _score_professionalism_rule(resume: Dict) -> int:
    """
    专业度的规则部分。
    旧实现只判断 bullet 中"任意位置"是否含专业动词,
    现在综合动词强度(且要在开头)、句长、第一人称、因果结构。
    """
    bullets = collect_bullets(resume)
    if not bullets:
        return 0
    per = [score_bullet_professional(b) for b in bullets]
    avg = sum(per) / len(per)
    return int(round(max(0, min(100, avg * 100))))



async def _score_professionalism_llm(resume: Dict) -> Dict:
    """专业度的 LLM 部分(LLM 评估语言)"""
    text = _resume_to_text(resume)
    if not text.strip():
        return {}
    try:
        raw = await llm_service.chat_complete(
            messages=[{"role": "user", "content": QUALITY_LLM_PROMPT.format(resume_text=text[:3500])}],
            temperature=0.2
        )
        return json.loads(_strip_code_fence(raw))
    except (llm_service.LLMError, json.JSONDecodeError):
        # 返回空 dict,让调用方退化为纯规则分。
        # 不给固定兜底分,否则 LLM 挂掉时所有简历的专业度都会趋同。
        return {}


def _score_match(resume: Dict, target_job: str) -> Dict:
    """
    匹配度:目标岗位关键词在简历中的覆盖情况。

    旧实现按 [\\s/、,,]+ 切词,中文岗位名没有分隔符,
    "Java后端开发工程师" 整体成为一个 token,几乎永远命中不了,
    导致该维度恒为 60/70 分。现在用词典最长匹配 + 2-gram 兜底切词,
    并区分"技能区命中"和"经历正文命中"——后者更有说服力。
    """
    job = (target_job or (resume.get("basic") or {}).get("target_job") or "").strip()
    if not job:
        return {"name": "匹配度", "score": 0, "max": 100, "desc": "未指定目标岗位,无法评估匹配度"}

    keywords = tokenize_job(job)
    if not keywords:
        return {"name": "匹配度", "score": 0, "max": 100, "desc": "未能解析目标岗位关键词"}

    # 经历正文 vs 技能清单分开统计:写进经历里的关键词才是真的会用
    exp_text = " ".join(collect_bullets(resume)).lower()
    for exp in resume.get("experiences") or []:
        exp_text += " " + str(exp.get("title", "")).lower()
        exp_text += " " + str(exp.get("role", "")).lower()
    skills = resume.get("skills") or {}
    skill_text = ""
    if isinstance(skills, dict):
        for group in skills.values():
            if isinstance(group, list):
                skill_text += " " + " ".join(str(s) for s in group).lower()

    hit_exp = sum(1 for kw in keywords if kw in exp_text)
    hit_skill = sum(1 for kw in keywords if kw not in exp_text and kw in skill_text)

    # 经历命中权重 1.0,仅技能清单命中权重 0.5
    covered = (hit_exp + hit_skill * 0.5) / len(keywords)

    # 覆盖率封顶 —— 岗位名切出的关键词很少时(如"前端开发"只有 1 个 token),
    # 命中一次就 100% 覆盖,该维度会退化成有/无二值。
    # 关键词越少,单靠覆盖率能拿到的上限越低,剩余分数要靠"相关证据的厚度"补。
    cap = {0: 0.0, 1: 0.62, 2: 0.78, 3: 0.9}.get(len(keywords), 1.0)
    base = min(covered, cap)

    # 证据厚度:命中关键词在经历正文里出现的总次数,以及技能清单的相关广度。
    # 反复出现说明是真的主线技能,而不是简历里蹭了一个词。
    depth_hits = sum(exp_text.count(kw) for kw in keywords if kw in exp_text)
    depth = min(1.0, depth_hits / (len(keywords) * 3)) if keywords else 0.0
    # 技能清单里与岗位相关的条目数
    skill_items = 0
    if isinstance(skills, dict):
        for group in skills.values():
            if isinstance(group, list):
                skill_items += len(group)
    breadth = min(1.0, skill_items / 6)

    ratio = base + (1 - base) * (depth * 0.6 + breadth * 0.4) if base > 0 else 0.0
    score = int(round(max(0, min(100, ratio * 100))))

    if score >= 75:
        desc = f"与「{job}」的关键词对齐度高"
    elif score >= 45:
        desc = f"与「{job}」部分对齐,核心关键词仍有缺口"
    elif score > 0:
        desc = f"与「{job}」的关键词覆盖偏低,建议在经历中显式体现"
    else:
        desc = f"经历中几乎未出现「{job}」相关关键词"
    return {"name": "匹配度", "score": score, "max": 100, "desc": desc}


def _score_credibility(resume: Dict) -> Dict:
    """
    可信度:内容是否可追溯。

    旧实现只做减法(yellow -5 / red -15,下限 60),导致经历越多扣得越狠,
    而"提供了 github 链接、具体数字"这类可验证信号完全不加分。
    现在改为双向:包装度扣分,可验证细节加分。
    """
    exps = resume.get("experiences") or []
    if not exps:
        return {"name": "可信度", "score": 0, "max": 100,
                "desc": "尚无经历内容,无法评估可信度"}

    # 基准 70 分:没有任何信号时的中性态度
    score = 70.0

    # 包装度标签
    for exp in exps:
        color = (exp.get("tag") or {}).get("color", "green")
        if color == "yellow":
            score -= 6
        elif color == "red":
            score -= 16

    # bullet 级的可验证性,平均后放大
    bullets = collect_bullets(resume)
    if bullets:
        cred = sum(score_bullet_credibility(b) for b in bullets) / len(bullets)
        score += cred * 30  # -30 ~ +30

    score = int(max(0, min(100, round(score))))
    if score >= 85:
        desc = "内容真实可追溯,有可验证的细节支撑"
    elif score >= 65:
        desc = "整体可信,建议补充链接、证明人等佐证"
    elif score >= 40:
        desc = "部分表述缺乏佐证,包装感偏强"
    else:
        desc = "夸大或模糊表述较多,建议改为可验证的事实"
    return {"name": "可信度", "score": score, "max": 100, "desc": desc}



def _resume_to_text(resume: Dict) -> str:
    """将 resume dict 拼接为纯文本,供 LLM 评估"""
    parts: List[str] = []
    basic = resume.get("basic", {})
    parts.append(f"姓名: {basic.get('fullname', '')} | 目标岗位: {basic.get('target_job', '')}")
    for ed in resume.get("education", []):
        parts.append(f"教育: {ed.get('school', '')} {ed.get('major', '')} {ed.get('degree', '')} {ed.get('period', '')}")
    for exp in resume.get("experiences", []):
        parts.append(f"\n[{exp.get('title', '')}] {exp.get('role', '')} {exp.get('period', '')}")
        for b in exp.get("bullets", []):
            parts.append(f"- {b}")
    skills = resume.get("skills", {})
    if isinstance(skills, dict):
        parts.append("技能: " + " / ".join(skills.get("technical", []) + skills.get("soft", [])))
    if resume.get("awards"):
        parts.append("获奖: " + "; ".join(resume["awards"]))
    if resume.get("self_evaluation"):
        parts.append("自评: " + resume["self_evaluation"])
    return "\n".join(parts)


async def evaluate_resume(resume: Dict, target_job: str = "") -> Dict:
    """
    五维评分 + 亮点/改善 + 行动指南
    """
    completeness = _score_completeness(resume)
    quantification = _score_quantification(resume)

    prof_rule = _score_professionalism_rule(resume)
    has_bullets = bool(collect_bullets(resume))
    if not has_bullets:
        # 没有正文就没什么可评的,不调 LLM 也不给保底分
        prof_score = 0
    else:
        prof_llm = await _score_professionalism_llm(resume)
        prof_llm_total = prof_llm.get("总分")
        if isinstance(prof_llm_total, (int, float)) and prof_llm_total > 0:
            # LLM 满分 60,归一化到 100 后与规则分各占一半
            prof_score = int(prof_rule * 0.5 + (prof_llm_total / 60 * 100) * 0.5)
        else:
            # LLM 不可用时退化为纯规则分,而不是给一个固定的 42 分兜底
            prof_score = prof_rule
        prof_score = max(0, min(100, prof_score))
    if prof_score >= 80:
        prof_desc = "用词专业,动词有力"
    elif prof_score >= 55:
        prof_desc = "表达基本规范,部分条目可再精炼"
    elif prof_score >= 25:
        prof_desc = "用词偏口语化,建议改为专业动词开头"
    else:
        prof_desc = "缺少专业化表达,建议按『动词+对象+结果』重写"
    professionalism = {
        "name": "专业度", "score": prof_score, "max": 100, "desc": prof_desc
    }

    match = _score_match(resume, target_job)
    credibility = _score_credibility(resume)

    dimensions = [completeness, quantification, professionalism, match, credibility]
    # 加权总分:量化度/专业度是主要区分点,完整度只是及格线
    total = int(round(sum(
        d["score"] * DIMENSION_WEIGHTS.get(d["name"], 0.2) for d in dimensions
    )))
    total = max(0, min(100, total))
    grade, grade_color = _grade_of(total)

    # 亮点 = 分数最高的前 2 个
    sorted_dims = sorted(dimensions, key=lambda d: -d["score"])
    highlights = [
        {
            "title": _highlight_title(sorted_dims[0]["name"]),
            "score": sorted_dims[0]["score"],
            "desc": sorted_dims[0]["desc"],
            "icon": "shield"
        },
        {
            "title": _highlight_title(sorted_dims[1]["name"]),
            "score": sorted_dims[1]["score"],
            "desc": sorted_dims[1]["desc"],
            "icon": "check"
        }
    ]

    # 改善 = 分数最低的前 2 个
    weak_dims = sorted(dimensions, key=lambda d: d["score"])[:2]
    improvements = [
        _build_improvement(d, resume) for d in weak_dims
    ]

    # 经历数量提醒 —— 若 <=3 段,优先插入这条建议
    exp_reminder = _build_experience_count_reminder(resume)
    if exp_reminder:
        improvements.insert(0, exp_reminder)

    action_guide = (
        f"聚焦 {weak_dims[0]['name']} 与 {weak_dims[1]['name']} 的优化,"
        f"按建议修改 3-5 处,预计总分可提升至 {min(100, total + 6)} 分以上。"
    )

    return {
        "total_score": total,
        "grade": grade,
        "grade_color": grade_color,
        "dimensions": dimensions,
        "highlights": highlights,
        "improvements": improvements,
        "action_guide": action_guide,
        "integrity_statement": (
            "本简历所有内容均基于你的真实对话生成,AI 仅做专业性重述与合理拔高,"
            "未编造任何不存在的经历。"
        )
    }


def _grade_of(score: int) -> Tuple[str, str]:
    """
    评级阈值。配合零分锚定的评分曲线下调:
    新算法下 75 分已是一份相当扎实的简历,沿用旧的 90/80 阈值会让
    绝大多数真实简历都落到"待提升",反而失去指导意义。
    """
    if score >= 82:
        return "卓越", "#10B981"
    if score >= 68:
        return "优秀", "#10B981"
    if score >= 52:
        return "良好", "#F59E0B"
    if score >= 35:
        return "合格", "#F59E0B"
    return "待提升", "#EF4444"


def _highlight_title(name: str) -> str:
    return {
        "完整度": "结构完整专业",
        "量化度": "成果量化突出",
        "专业度": "用词专业有力",
        "匹配度": "岗位匹配精准",
        "可信度": "内容真实可信"
    }.get(name, name)


def _worst_bullet_by(resume: Dict, scorer) -> Dict:
    """
    按打分函数找出得分最低的 bullet(而非第一个不合格的)。
    改进建议指向最差的那条更有说服力。
    """
    worst = {}
    worst_score = None
    for exp in resume.get("experiences") or []:
        for b in exp.get("bullets") or []:
            if not isinstance(b, str) or not b.strip():
                continue
            s = scorer(b)
            if worst_score is None or s < worst_score:
                worst_score = s
                worst = {
                    "exp_id": exp.get("id", ""),
                    "exp_title": exp.get("title", ""),
                    "bullet": b,
                    "score": s,
                }
    return worst


def _rewrite_with_quant(bullet: str) -> str:
    """给一条缺数字的 bullet 套上量化样例"""
    if not bullet:
        return ""
    # 简单策略:在末尾追加示例数据
    trimmed = bullet.rstrip("。.,, ;;")
    return f"{trimmed},累计触达 X 人/覆盖 X% 场景,效率提升 X%"


def _rewrite_with_pro_verb(bullet: str) -> str:
    """把口语化的开头替换为专业动词"""
    if not bullet:
        return ""
    replacements = [
        ("我做了", "主导完成"), ("我们做了", "协同推动"),
        ("做了", "主导完成"), ("我搞", "负责推进"),
        ("帮忙", "协同支持"), ("参与", "深度参与并推动"),
        ("做", "负责"), ("用了", "运用"), ("学了", "掌握并应用")
    ]
    out = bullet
    for old, new in replacements:
        if out.startswith(old):
            out = new + out[len(old):]
            break
    return out


def _build_improvement(dim: Dict, resume: Dict) -> Dict:
    name = dim["name"]
    if name == "量化度":
        hit = _worst_bullet_by(resume, score_bullet_quant)
        evidence = hit.get("bullet", "")
        target_id = hit.get("exp_id", "")
        actions = []
        if evidence:
            actions.append({
                "original": evidence,
                "suggestion": _rewrite_with_quant(evidence),
                "reason": "加入具体数字让成果可衡量"
            })
        # 通用建议保底
        actions.append({
            "original": "",
            "suggestion": "将'阅读量较多'改为'累计阅读量 1.2 万次,平均单篇 400+'",
            "reason": "用绝对数字替代'较多/较快/不错'等模糊词"
        })
        actions.append({
            "original": "",
            "suggestion": "将'参与团队多人'改为'协同 5 人小组,负责其中 2 个关键模块'",
            "reason": "团队规模与个人贡献都要量化"
        })
        return {
            "title": "量化度偏低",
            "score": dim["score"],
            "desc": f"经历「{hit.get('exp_title', '部分段落')}」中缺少具体数字,以下是改写示例。" if hit else "部分经历缺少具体数字,以下是改写示例。",
            "target_exp_id": target_id or None,
            "evidence": evidence,
            "actions": actions
        }
    if name == "匹配度":
        target = resume.get("basic", {}).get("target_job", "目标岗位")
        return {
            "title": "岗位匹配度可优化",
            "score": dim["score"],
            "desc": f"目标岗位「{target}」的核心关键词在经历描述中出现频次还可提升。",
            "target_exp_id": None,
            "evidence": "",
            "actions": [
                {
                    "original": "",
                    "suggestion": f"在最相关的项目末尾加一条:'输出面向 {target} 的复盘文档 1 份,沉淀方法论'",
                    "reason": f"显式呼应「{target}」的核心动作"
                },
                {
                    "original": "",
                    "suggestion": f"技能板块新增『{target} 常用工具』分类,列出 3~5 项 JD 中的关键词",
                    "reason": "命中 ATS 关键词筛选"
                },
                {
                    "original": "",
                    "suggestion": "将与目标岗位最相关的那段经历调到经历列表的第一位",
                    "reason": "HR 首屏停留时间有限,把相关性最高的前置"
                }
            ]
        }
    if name == "完整度":
        missing = []
        if not (resume.get("skills") or {}).get("technical"):
            missing.append("技能清单")
        if not resume.get("self_evaluation"):
            missing.append("自我评价")
        if len(resume.get("experiences") or []) < 2:
            missing.append("至少 2 段经历")
        miss_text = "、".join(missing) if missing else "部分核心模块"
        return {
            "title": "模块完整度待补",
            "score": dim["score"],
            "desc": f"以下模块尚未填写完整:{miss_text}。",
            "target_exp_id": None,
            "evidence": "",
            "actions": [
                {
                    "original": "",
                    "suggestion": "自我评价示例:具备扎实工程能力与产品思维,能够主导从 0 到 1 的项目落地",
                    "reason": "在简历底部加一段 2~3 句的自评提升完整感"
                },
                {
                    "original": "",
                    "suggestion": "技能清单按『技术栈 / 工具 / 软技能』三档罗列,各 3~5 项",
                    "reason": "结构化展示更易被 HR 扫读"
                }
            ]
        }
    if name == "专业度":
        hit = _worst_bullet_by(resume, score_bullet_professional)
        evidence = hit.get("bullet", "")
        target_id = hit.get("exp_id", "")
        actions = []
        if evidence:
            actions.append({
                "original": evidence,
                "suggestion": _rewrite_with_pro_verb(evidence) or "主导" + evidence,
                "reason": "用专业动词开头(主导/设计/优化/分析)"
            })
        actions.append({
            "original": "",
            "suggestion": "将'我负责后端'改为'主导设计后端服务架构,落地 X 个核心接口'",
            "reason": "去掉第一人称 + 加入交付物"
        })
        actions.append({
            "original": "",
            "suggestion": "将每条 bullet 控制在 25-50 字,使用『动词 + 对象 + 结果』结构",
            "reason": "保持表达密度与节奏一致"
        })
        return {
            "title": "语言专业度可提升",
            "score": dim["score"],
            "desc": f"经历「{hit.get('exp_title', '部分段落')}」中用词偏口语化,以下是改写示例。" if hit else "部分用词偏口语化,可替换为专业动词。",
            "target_exp_id": target_id or None,
            "evidence": evidence,
            "actions": actions
        }
    if name == "可信度":
        # 找包装度最高的经历
        target_exp = None
        for exp in resume.get("experiences", []):
            if (exp.get("tag") or {}).get("color") in ("yellow", "red"):
                target_exp = exp
                break
        evidence = ""
        target_id = None
        if target_exp:
            target_id = target_exp.get("id")
            bullets = target_exp.get("bullets") or []
            if bullets:
                evidence = bullets[0]
        return {
            "title": "包装度需控制",
            "score": dim["score"],
            "desc": f"经历「{target_exp.get('title', '部分段落')}」包装强度偏高,建议提供更细节支撑。" if target_exp else "部分经历包装强度略高,建议提供更细节支撑。",
            "target_exp_id": target_id,
            "evidence": evidence,
            "actions": [
                {
                    "original": evidence,
                    "suggestion": (evidence.rstrip("。.,, ") + "(附:实际产出截图 / 项目链接 / 老师/同事联系方式)") if evidence else "在该经历末尾追加可验证的产出链接或证明人信息",
                    "reason": "提供可验证的细节降低包装感"
                },
                {
                    "original": "",
                    "suggestion": "去掉无法量化的形容词如'极大提升''显著优化',替换为具体数字",
                    "reason": "避免无法佐证的夸张表述"
                }
            ]
        }
    return {
        "title": f"{name}待优化",
        "score": dim["score"],
        "desc": dim["desc"],
        "target_exp_id": None,
        "evidence": "",
        "actions": []
    }


def _build_experience_count_reminder(resume: Dict) -> Dict:
    """
    若 experiences 数量 <= 3,追加一条提醒
    """
    exps = resume.get("experiences") or []
    n = len(exps)
    if n > 3:
        return {}

    job = resume.get("basic", {}).get("target_job", "目标岗位")
    # 根据已有经历类型,给出未覆盖的方向
    existing_types = {e.get("type", "") for e in exps}
    suggestions = []
    candidates = [
        ("course_project", "课程结课大作业(选一门和目标岗位最相关的)"),
        ("internship", "实习经历(哪怕只有 1~2 个月的远程/线上实习)"),
        ("competition", "学科竞赛 / 编程比赛 / 商赛"),
        ("club", "学生组织或社团运营经历"),
        ("volunteer", "志愿服务 / 公益项目"),
        ("research", "课题研究 / 老师带的科研小项目"),
    ]
    for type_key, hint in candidates:
        if type_key not in existing_types:
            suggestions.append({
                "original": "",
                "suggestion": f"补充一段「{hint}」,套用 STAR-L 法则展开",
                "reason": f"丰富经历类型 → 提升整体竞争力"
            })
        if len(suggestions) >= 3:
            break
    if not suggestions:
        suggestions = [
            {
                "original": "",
                "suggestion": "回想最近 1 年里参与过的任意 ≥1 周的项目/活动/竞赛",
                "reason": "学生简历 4~5 段经历更具竞争力"
            }
        ]
    return {
        "title": "经历数量偏少",
        "score": max(40, 60 - (3 - n) * 8),
        "desc": (
            f"目前仅识别到 {n} 段项目/实习经历,大学生简历建议至少 3~5 段。"
            f"是否还有课程项目、社团活动、志愿服务、兼职、竞赛经历未填写?"
        ),
        "target_exp_id": None,
        "evidence": "",
        "actions": suggestions
    }
