"""
质量评估服务 —— 五维评分(规则 + LLM 混合)
五个维度:完整度、量化度、专业度、匹配度、可信度
"""
import json
import re
from typing import Dict, List, Tuple

from app.core.prompts import QUALITY_LLM_PROMPT
from app.services import llm_service
from app.services.dialog_service import _strip_code_fence


# ====== 量化词正则:能识别数字/百分比/年份等 ======
QUANT_PATTERN = re.compile(r"(\d+\.?\d*)\s*(%|万|千|百|个|条|人|次|篇|位|倍|分|名|s|ms|秒|分钟|小时|天|周|月|年|MB|GB|TB)?")

# ====== 专业动词词库(粗略) ======
PRO_VERBS = {
    "主导", "设计", "构建", "实现", "搭建", "优化", "分析", "推动", "复盘",
    "协调", "整合", "重构", "落地", "调研", "评估", "迭代", "提升", "降低",
    "支撑", "驱动", "孵化", "运营", "策划"
}


def _score_completeness(resume: Dict) -> Dict:
    """完整度:看模块是否齐"""
    parts = {
        "basic": bool(resume.get("basic", {}).get("fullname")),
        "education": bool(resume.get("education")),
        "experiences": len(resume.get("experiences") or []) >= 1,
        "experiences_2plus": len(resume.get("experiences") or []) >= 2,
        "skills": bool((resume.get("skills") or {}).get("technical")),
        "self_eval": bool(resume.get("self_evaluation"))
    }
    base = 50
    bonus = sum([
        10 if parts["basic"] else 0,
        10 if parts["education"] else 0,
        15 if parts["experiences"] else 0,
        5 if parts["experiences_2plus"] else 0,
        10 if parts["skills"] else 0,
        0  # self_eval 不给加分(自动生成的容易刷分)
    ])
    score = min(100, base + bonus)
    desc = "各模块齐全,结构清晰" if score >= 85 else "部分模块缺失,建议补充"
    return {"name": "完整度", "score": score, "max": 100, "desc": desc}


def _score_quantification(resume: Dict) -> Dict:
    """量化度:看 bullets 里有多少数字/百分比"""
    bullets = []
    for exp in resume.get("experiences", []):
        bullets.extend(exp.get("bullets", []))
    if not bullets:
        return {"name": "量化度", "score": 50, "max": 100, "desc": "暂无经历可评估"}

    quant_count = 0
    for b in bullets:
        if QUANT_PATTERN.search(b):
            quant_count += 1
    ratio = quant_count / len(bullets)
    score = int(min(100, 50 + ratio * 50))
    desc = (
        "经历描述含丰富数据,量化充分" if score >= 85
        else "部分经历缺少具体数字,可继续补充"
    )
    return {"name": "量化度", "score": score, "max": 100, "desc": desc}


def _score_professionalism_rule(resume: Dict) -> int:
    """专业度的规则部分(动词命中率)"""
    bullets = []
    for exp in resume.get("experiences", []):
        bullets.extend(exp.get("bullets", []))
    if not bullets:
        return 50

    hit_count = 0
    for b in bullets:
        if any(v in b for v in PRO_VERBS):
            hit_count += 1
    ratio = hit_count / len(bullets)
    return int(min(100, 50 + ratio * 45))


async def _score_professionalism_llm(resume: Dict) -> Dict:
    """专业度的 LLM 部分(LLM 评估语言)"""
    text = _resume_to_text(resume)
    if not text.strip():
        return {"凝练度": 12, "精准度": 12, "流畅度": 12, "总分": 36, "改进建议": ""}
    try:
        raw = await llm_service.chat_complete(
            messages=[{"role": "user", "content": QUALITY_LLM_PROMPT.format(resume_text=text[:3500])}],
            temperature=0.2
        )
        return json.loads(_strip_code_fence(raw))
    except (llm_service.LLMError, json.JSONDecodeError):
        return {"凝练度": 14, "精准度": 14, "流畅度": 14, "总分": 42, "改进建议": ""}


def _score_match(resume: Dict, target_job: str) -> Dict:
    """匹配度:看 target_job 的关键词在简历里出现频次"""
    text = _resume_to_text(resume).lower()
    job = (target_job or resume.get("basic", {}).get("target_job") or "").lower()
    if not job or not text:
        return {"name": "匹配度", "score": 70, "max": 100, "desc": "未指定目标岗位"}

    # 简单分词
    job_keywords = set()
    for w in re.split(r"[\s/、,,]+", job):
        if len(w) >= 2:
            job_keywords.add(w)

    hits = sum(1 for kw in job_keywords if kw in text)
    score = int(min(100, 60 + hits * 10))
    desc = (
        f"与「{target_job}」关键词对齐度较高" if score >= 80
        else f"与「{target_job}」的关键词覆盖可继续优化"
    )
    return {"name": "匹配度", "score": score, "max": 100, "desc": desc}


def _score_credibility(resume: Dict) -> Dict:
    """可信度:基于经历的 tag color 与包装度估算"""
    exps = resume.get("experiences", [])
    if not exps:
        return {"name": "可信度", "score": 80, "max": 100, "desc": "暂无经历"}

    score = 100
    for exp in exps:
        color = (exp.get("tag") or {}).get("color", "green")
        if color == "yellow":
            score -= 5
        elif color == "red":
            score -= 15
    score = max(60, score)
    desc = "内容真实可追溯" if score >= 85 else "部分经历包装度偏高,建议核实"
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
    prof_llm = await _score_professionalism_llm(resume)
    prof_llm_total = prof_llm.get("总分", 42)
    prof_score = int(prof_rule * 0.5 + (prof_llm_total / 60 * 100) * 0.5)
    prof_score = min(100, max(50, prof_score))
    professionalism = {
        "name": "专业度", "score": prof_score, "max": 100,
        "desc": "用词专业,动词有力" if prof_score >= 85 else "可进一步精炼用词"
    }

    match = _score_match(resume, target_job)
    credibility = _score_credibility(resume)

    dimensions = [completeness, quantification, professionalism, match, credibility]
    total = int(sum(d["score"] for d in dimensions) / len(dimensions))
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
    if score >= 90:
        return "卓越", "#10B981"
    if score >= 80:
        return "优秀", "#10B981"
    if score >= 70:
        return "良好", "#F59E0B"
    if score >= 60:
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


def _find_weakest_bullet(resume: Dict, predicate) -> Dict:
    """
    在 resume.experiences 中找出第一个匹配 predicate 的 bullet,
    返回 {exp_id, exp_title, bullet} 或空 dict
    """
    for exp in resume.get("experiences", []):
        for b in exp.get("bullets", []):
            if predicate(b):
                return {
                    "exp_id": exp.get("id", ""),
                    "exp_title": exp.get("title", ""),
                    "bullet": b
                }
    return {}


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
        hit = _find_weakest_bullet(resume, lambda b: not QUANT_PATTERN.search(b))
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
        hit = _find_weakest_bullet(
            resume,
            lambda b: not any(v in b for v in PRO_VERBS)
        )
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
