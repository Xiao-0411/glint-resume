"""
简历 ↔ 岗位匹配 —— 用用户真实简历去比对真实 JD

替代原先的 `jobs.py::_calc_match`。旧实现有三个硬伤:

1. **根本没读简历** —— 拿 target_job 字符串查 KW_MAP 手写词表,
   再和 JD 要求求交集。同一个目标岗位的所有用户拿到完全相同的分数,
   而 UI 却写着"与你的简历高度匹配"。
2. **JD 越详细分越低** —— 分母是 len(requirements),KW_MAP 命中不到时
   退化成 requirements[:4] 自己匹配自己:JD 列 3 个技能得 100 分,
   列 10 个得 40 分。
3. **技能词误判** —— 裸正则让 PostgreSQL 命中 SQL。

现在:简历技能(含经历正文里实际用过的)对 JD 要求做加权覆盖,
权重取自 jd_corpus 的真实市场频率 —— 缺一个"9 成 JD 都要的 MySQL"
比缺一个"1 成 JD 才要的 Flink"扣得多。
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from app.services.jd_corpus import JobProfile
from app.services.skill_extract import canonicalize, extract_skills

# 匹配等级阈值。与前端 match-tag 的 green/yellow/red 一一对应。
# 后端是唯一定义处,前端只做展示。
LEVEL_GREEN_MIN = 75
LEVEL_YELLOW_MIN = 50

# 技能出现在经历正文里(真的用过)比只列在技能清单里(可能只是听说过)更可信。
# 但也不能把只写在技能栏的完全不算 —— 学生简历常把技术栈统一列在技能区。
WEIGHT_PROVEN = 1.0
WEIGHT_LISTED = 0.75


@dataclass
class ResumeSkills:
    """从简历里提炼出的技能画像"""

    # 在经历正文中出现过的技能 —— 有事实支撑
    proven: List[str]
    # 仅在技能清单中声明的技能
    listed: List[str]

    @property
    def all(self) -> List[str]:
        return self.proven + [s for s in self.listed if s not in self.proven]

    def credit_of(self, skill: str) -> float:
        """该技能的可信权重,未掌握则 0"""
        if skill in self.proven:
            return WEIGHT_PROVEN
        if skill in self.listed:
            return WEIGHT_LISTED
        return 0.0

    @property
    def is_empty(self) -> bool:
        return not self.proven and not self.listed


def extract_resume_skills(resume: Optional[Dict]) -> ResumeSkills:
    """
    从简历 dict 中提取技能画像。

    区分"写在经历里"和"只列在技能栏":前者说明真的用过,后者只是声明。
    """
    if not resume:
        return ResumeSkills(proven=[], listed=[])

    # 经历正文:bullets + 标题 + 角色
    exp_parts: List[str] = []
    for exp in resume.get("experiences") or []:
        for b in exp.get("bullets") or []:
            if isinstance(b, str):
                exp_parts.append(b)
        exp_parts.append(str(exp.get("title", "")))
        exp_parts.append(str(exp.get("role", "")))
    # 自我评价和获奖里提到的技能也算"用过"的旁证
    if resume.get("self_evaluation"):
        exp_parts.append(str(resume["self_evaluation"]))
    proven = extract_skills(" ".join(exp_parts))

    # 技能清单
    raw_listed: List[str] = []
    skills = resume.get("skills")
    if isinstance(skills, dict):
        for group in skills.values():
            if isinstance(group, list):
                raw_listed.extend(str(s) for s in group)
    elif isinstance(skills, list):
        raw_listed.extend(str(s) for s in skills)
    listed = [s for s in canonicalize(raw_listed) if s not in proven]

    return ResumeSkills(proven=proven, listed=listed)


def job_required_skills(job: Dict) -> List[str]:
    """从职位 dict 中取出它要求的技能(规范名)"""
    required = canonicalize(
        list(job.get("requirements") or []) + list(job.get("tags") or [])
    )
    desc = job.get("description") or ""
    if desc:
        for s in extract_skills(desc):
            if s not in required:
                required.append(s)
    return required


def match_resume_to_job(
    resume_skills: ResumeSkills,
    job: Dict,
    profile: Optional[JobProfile] = None,
) -> Dict:
    """
    计算一份简历与一个职位的匹配度。

    分数 = 已掌握技能的权重和 / JD 全部要求的权重和。
    每个技能的权重取自 jd_corpus 的市场频率(缺失则记 0.5 的中性权重),
    因此:
      - JD 列得多不再自动扣分 —— 分子分母同步增长
      - 缺核心技能扣得比缺边缘技能狠
    """
    required = job_required_skills(job)

    if not required:
        # JD 没写清楚要什么,不臆测。返回 None 分数,由调用方决定如何展示。
        return {
            "score": None,
            "level": "unknown",
            "matched": [],
            "missing": [],
            "reasons": "该职位未列明技能要求，无法评估匹配度",
        }

    if resume_skills.is_empty:
        return {
            "score": None,
            "level": "unknown",
            "matched": [],
            "missing": required[:5],
            "reasons": "尚未生成简历，无法评估匹配度",
        }

    def weight_of(skill: str) -> float:
        # 无画像或画像里没有该技能时给 0.5 中性权重:
        # 它确实是 JD 要求,只是市场频率未知,不能当作不重要。
        if profile is None:
            return 1.0
        return profile.weight_of(skill) or 0.5

    total = 0.0
    earned = 0.0
    matched: List[str] = []
    missing: List[tuple] = []
    for skill in required:
        w = weight_of(skill)
        total += w
        credit = resume_skills.credit_of(skill)
        if credit > 0:
            earned += w * credit
            matched.append(skill)
        else:
            missing.append((skill, w))

    score = int(round((earned / total) * 100)) if total else 0
    score = max(0, min(100, score))

    # 缺失技能按市场权重排序 —— 先补最多 JD 要求的那个
    missing.sort(key=lambda kv: -kv[1])
    missing_skills = [s for s, _ in missing]

    if score >= LEVEL_GREEN_MIN:
        level = "green"
        reasons = f"你的「{'、'.join(matched[:3])}」覆盖了该岗位的核心要求"
    elif score >= LEVEL_YELLOW_MIN:
        level = "yellow"
        hit = "、".join(matched[:2]) if matched else "部分基础技能"
        gap = "、".join(missing_skills[:2])
        reasons = f"已具备「{hit}」，建议补足「{gap}」后投递"
    else:
        level = "red"
        gap = "、".join(missing_skills[:3])
        reasons = f"核心要求「{gap}」在你的简历中暂未体现"

    return {
        "score": score,
        "level": level,
        "matched": matched,
        "missing": missing_skills[:5],
        "reasons": reasons,
    }


def rank_jobs(
    resume: Optional[Dict],
    jobs: Sequence[Dict],
    profile: Optional[JobProfile] = None,
) -> List[Dict]:
    """给一批职位打匹配分并排序。无分数的排在最后。"""
    resume_skills = extract_resume_skills(resume)
    out: List[Dict] = []
    for job in jobs:
        m = match_resume_to_job(resume_skills, job, profile)
        out.append({
            **job,
            "matchScore": m["score"],
            "matchLevel": m["level"],
            "reasons": m["reasons"],
            "matchedSkills": m["matched"],
            "missingSkills": m["missing"],
        })
    out.sort(key=lambda j: (j["matchScore"] is None, -(j["matchScore"] or 0)))
    return out
