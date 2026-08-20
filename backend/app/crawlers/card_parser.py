"""招聘平台列表卡片的公共解析与质量校验。

三个平台的卡片文本结构不同，但要落库的字段和质量底线一致：
公司名必须是真实名称、薪资和地点必须可解析、地点必须落在 373 城市表内。
不达标的记录宁可丢弃，也不写入半成品污染搜索与匹配。
"""
from __future__ import annotations

import re

from app.services.location_catalog import city_of, extract_location

# 卡片上常见的非公司名噪声，多为按钮文案或招聘者信息。
COMPANY_NOISE = {
    "未知公司", "未知", "立即沟通", "查看详情", "收藏", "已认证", "招聘中",
    "急聘", "热招", "名企", "猎头顾问", "HR", "-", "—", "",
}
COMPANY_SUFFIXES = ("有限公司", "股份公司", "集团", "科技", "研究院", "事务所", "中心", "学校", "医院", "银行")

SALARY_PATTERNS = [
    r"\d+(?:\.\d+)?\s*[-~至]\s*\d+(?:\.\d+)?\s*[kK]\s*(?:·\s*\d+\s*薪)?",
    r"\d+(?:\.\d+)?\s*[-~至]\s*\d+(?:\.\d+)?\s*[万千]\s*(?:/\s*[月年])?",
    r"\d+\s*[-~至]\s*\d+\s*元\s*/\s*[天日月年]",
    r"\d+\s*[kK]\s*[-~至]\s*\d+\s*[kK]",
    r"面议",
]
EXPERIENCE_PATTERNS = [
    r"经验不限", r"不限经验", r"应届生?", r"在校生", r"\d+\s*[-~]\s*\d+\s*年", r"\d+\s*年以[上下]", r"\d+\s*年",
]
EDUCATION_LEVELS = ("博士", "硕士", "本科", "大专", "中专", "中技", "高中", "初中及以下", "学历不限")

# 招聘者姓名+职务，如"何女士·经理"。出现即说明抓到的是卡片而非公司名。
RECRUITER_PATTERN = re.compile(r"[一-鿿]{1,3}(?:先生|女士|老师|经理|HR)")


def first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        found = re.search(pattern, text, re.I)
        if found:
            return found.group(0).strip()
    return ""


def parse_salary(text: str) -> str:
    return first_match(text, SALARY_PATTERNS)


def parse_experience(text: str) -> str:
    return first_match(text, EXPERIENCE_PATTERNS)


def parse_education(text: str) -> str:
    for level in EDUCATION_LEVELS:
        if level in text:
            return level
    return ""


def parse_company(text: str, title: str) -> str:
    """从卡片文本中挑出公司名。

    优先取带企业后缀的片段；退化情况下取首个不是岗位名/招聘者/噪声的短片段。
    """
    for suffix in COMPANY_SUFFIXES:
        found = re.search(rf"[一-鿿\w（）()·]{{2,30}}{suffix}", text)
        if found:
            candidate = found.group(0).strip()
            if candidate not in COMPANY_NOISE:
                return candidate

    for segment in (part.strip() for part in re.split(r"[\s|·\n]+", text) if part.strip()):
        if segment == title or segment in COMPANY_NOISE:
            continue
        if RECRUITER_PATTERN.fullmatch(segment) or parse_salary(segment) or parse_education(segment):
            continue
        if 2 <= len(segment) <= 30 and not segment.isdigit():
            return segment
    return ""


def clean_title(title: str) -> str:
    """去掉卡片里粘在岗位名后的薪资，以及【】角标。

    角标常出现在开头（"【Python】后端开发工程师"），按【截断会得到空串，
    因此移除角标本身而非其后的内容。
    """
    normalized = re.sub(r"\s+", " ", title.strip())
    normalized = re.sub(r"【[^】]*】", " ", normalized)
    normalized = re.split(r"\s+(?=\d+(?:\.\d+)?\s*[-~至]\s*\d+)", normalized, maxsplit=1)[0]
    return re.sub(r"\s+", " ", normalized)[:100].strip(" -|·")


def is_publishable(job: dict, *, city: str = "") -> bool:
    """入库前的质量闸门。

    任一必填字段缺失就丢弃：这些记录在前端只会显示成空白卡片，
    且会拉低搜索结果的可用密度。
    """
    if not job.get("title") or not job.get("platform_job_id"):
        return False
    company = (job.get("company") or "").strip()
    if not company or company in COMPANY_NOISE:
        return False
    if not (job.get("salary") or "").strip():
        return False
    location = (job.get("location") or "").strip()
    if not location or not city_of(location):
        return False
    if city and not city_of(location) == city_of(extract_location(city) or city):
        return False
    return True
