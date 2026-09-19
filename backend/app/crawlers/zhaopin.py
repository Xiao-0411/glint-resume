"""智联招聘 crawler backed by the shared logged-in CDP Chrome session.

2026-09 智联结果页改成了 Vue 单页应用（/jobs?jl=城市码&kw=关键词）：
卡片是 ``div.job-card``，上面不再有职位详情链接，职位数据挂在组件实例
``__vue__.$props.job`` 上（number / name / salary60 / companyName / workCity ...）。
本爬虫优先读组件数据；拿不到时退化为按 class 读卡片 DOM 文本。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from app.crawlers.base import BaseCrawler, select_cities, select_keywords
from app.crawlers.card_parser import (
    clean_title,
    is_publishable,
    parse_company,
    parse_education,
    parse_experience,
    parse_salary,
)
from app.crawlers.cdp_browser import CdpBrowser, page_status, wait_for_detail_text
from app.services.location_catalog import extract_location
from app.core.logging_config import get_logger

logger = get_logger("glint.crawler.zhaopin")

# jl 是智联城市码，489 表示全国。码表抓自结果页调用的 /c/i/search/base/data 接口，
# 把城市名放进 kw 会被当成关键词的一部分，搜不到职位。
SEARCH_URL = "https://www.zhaopin.com/jobs?jl={code}&kw={keyword}"
NATIONWIDE_CODE = "489"
CITY_CODES_PATH = Path(__file__).with_name("zhaopin_city_codes.json")
# BOSS 城市表用全称（"阿坝藏族羌族自治州"），智联用短名（"阿坝"）；按前缀对齐。
CITY_MIN_PREFIX = 2

DETAIL_SELECTORS = [
    ".describtion-card__detail-content", ".describtion-card__content-wrap",
    ".job-detail__content", ".describtion__detail-content", ".job-detail-content",
    "[class*='job-description']", "[class*='position-description']",
]
DETAIL_MARKERS = ("岗位职责", "职位职责", "任职要求", "职位要求", "职位描述")
RISK_MARKERS = ("安全验证", "访问验证", "滑动验证", "访问异常", "请完成验证", "验证码")

LIST_SCRIPT = r"""
(function () {
  const clean = value => (value || '').toString().trim().replace(/\s+/g, ' ');
  const panel = document.querySelector('.job-list-panel');
  // 没有职位时结果区渲染 .job-list-empty（"暂未找到符合你要求的职位"）
  const empty = document.querySelector('.job-list-empty, .job-split-layout--empty');
  const records = [];
  for (const card of document.querySelectorAll('.job-list-panel .job-card')) {
    const vm = card.__vue__;
    const job = vm && vm.$props && vm.$props.job;
    if (job && job.number) {
      // 组件里的 jobDescription 只是截断的摘要，完整 JD 仍由详情页补全
      records.push({
        number: String(job.number),
        name: clean(job.name),
        salary: clean(job.salary60),
        company: clean(job.companyName),
        city: clean(job.workCity),
        district: clean(job.cityDistrict),
        street: clean(job.streetName),
        education: clean(job.education),
        experience: clean(job.workingExp),
        url: clean(job.positionURL || job.positionUrl),
        skills: (job.skillLabel || []).map(item => clean(item && item.value)).filter(Boolean)
      });
      continue;
    }
    const text = selector => {
      const node = card.querySelector(selector);
      return node ? clean(node.innerText || node.textContent) : '';
    };
    const name = text('.job-card__title-clamp') || text('[class*="job-card__title"]');
    if (!name) continue;
    const companyLink = card.querySelector('.job-card__company-name');
    records.push({
      number: '',
      name: name,
      salary: text('.job-card__salary'),
      company: text('.job-card__company-name'),
      city: '',
      district: text('.job-card__location'),
      street: '',
      education: '',
      experience: '',
      url: (companyLink && companyLink.href) || '',
      skills: Array.from(card.querySelectorAll('.job-card__skill-tag')).map(node => clean(node.innerText)).filter(Boolean)
    });
  }
  return {hasPanel: !!panel, isEmpty: !!empty, records: records};
})()
"""


@lru_cache(maxsize=1)
def _city_codes() -> dict[str, str]:
    with CITY_CODES_PATH.open(encoding="utf-8") as handle:
        return {str(name): str(code) for name, code in json.load(handle).items()}


def zhaopin_city_code(city: str) -> str:
    """把城市名换成智联 jl 码；对不上的城市退回全国，由入库前的城市校验兜底。"""
    name = (city or "").strip()
    if not name:
        return NATIONWIDE_CODE
    codes = _city_codes()
    for candidate in (name, f"{name}市"):
        if candidate in codes:
            return codes[candidate]
    best = ""
    for known in codes:
        stem = known[:-1] if known.endswith("市") else known
        if len(stem) >= CITY_MIN_PREFIX and name.startswith(stem) and len(stem) > len(best):
            best = known
    return codes[best] if best else NATIONWIDE_CODE


def count_visible_jobs(browser: CdpBrowser, session_id: str) -> int:
    """登录监控用：当前结果页已渲染出的职位数。"""
    value = browser.evaluate(LIST_SCRIPT, session_id)
    return len(value.get("records") or []) if isinstance(value, dict) else 0


def wait_for_records(
    browser: CdpBrowser,
    session_id: str,
    timeout: float = 15.0,
    hydration_grace: float = 6.0,
) -> dict:
    """等结果列表渲染完成；返回 {"hasPanel": bool, "isEmpty": bool, "records": [...]}。

    结果页先由服务端输出卡片 HTML、再由 Vue 挂载；刚出现卡片时组件数据可能还没就绪，
    此时多等一小段时间，尽量拿到带 number 的组件数据而不是 DOM 退化结果。
    """
    deadline = time.monotonic() + timeout
    result: dict = {"hasPanel": False, "isEmpty": False, "records": []}
    cards_seen_at: float | None = None
    while True:
        value = browser.evaluate(LIST_SCRIPT, session_id)
        if isinstance(value, dict):
            result = value
            records = result.get("records") or []
            if result.get("isEmpty"):
                return result
            if records:
                now = time.monotonic()
                cards_seen_at = cards_seen_at or now
                if any(item.get("number") for item in records) or now - cards_seen_at >= hydration_grace:
                    return result
        if time.monotonic() >= deadline:
            return result
        time.sleep(0.75)


class ZhaopinCrawler(BaseCrawler):
    platform = "zhaopin"
    base_url = "https://www.zhaopin.com"

    async def crawl(self, keywords: List[str] = None, cities: List[str] = None) -> List[dict]:
        return await asyncio.to_thread(self._crawl_sync, select_keywords(keywords), select_cities(cities))

    def _crawl_sync(self, keywords: List[str], cities: List[str]) -> List[dict]:
        browser = CdpBrowser(int(os.getenv("BOSS_SCRAPER_CDP_PORT", "9222")))
        seen: set[str] = set()
        jobs: list[dict] = []
        had_panel = False
        rejected = 0
        try:
            browser.connect()
            for city in cities:
                code = zhaopin_city_code(city)
                for keyword in keywords:
                    _, sid = browser.open_page(
                        SEARCH_URL.format(code=code, keyword=quote(keyword)),
                        reuse=True,
                    )
                    result = wait_for_records(browser, sid)
                    records = result.get("records") or []
                    if not records:
                        if result.get("isEmpty") or result.get("hasPanel"):
                            had_panel = True
                            logger.info("zhaopin_no_results", extra={"city": city, "keyword": keyword})
                            continue
                        self._raise_if_blocked(browser, sid)
                        continue
                    had_panel = True
                    for record in records:
                        job = self._parse_card(record)
                        if not job:
                            continue
                        if not is_publishable(job, city=city):
                            rejected += 1
                            continue
                        if job["platform_job_id"] not in seen:
                            seen.add(job["platform_job_id"])
                            jobs.append(job)
            if not had_panel:
                raise RuntimeError("智联招聘页面未显示职位列表，可能未登录、被风控拦截或页面已改版")
            logger.info("zhaopin_crawl_done", extra={"kept": len(jobs), "rejected": rejected})
            return jobs
        finally:
            browser.close()

    @staticmethod
    def _raise_if_blocked(browser: CdpBrowser, session_id: str) -> None:
        status = page_status(browser, session_id)
        if status.get("loginPrompts"):
            raise RuntimeError("智联招聘要求登录，登录状态可能已失效")
        text = str(status.get("text") or "")
        if any(marker in text for marker in RISK_MARKERS):
            raise RuntimeError("智联招聘要求安全验证，可能被风控拦截")

    async def fetch_detail(self, job: dict) -> dict:
        url = str(job.get("url") or "").strip()
        if not url:
            return {}
        return await asyncio.to_thread(self._fetch_detail_sync, url, str(job.get("title") or ""))

    def _fetch_detail_sync(self, url: str, title: str) -> dict:
        browser = CdpBrowser(int(os.getenv("BOSS_SCRAPER_CDP_PORT", "9222")))
        try:
            browser.connect()
            _, sid = browser.open_page(url, wait_seconds=3.0)
            status = page_status(browser, sid)
            if status.get("loginPrompts"):
                raise RuntimeError("智联招聘登录状态已失效，请重新登录后查看岗位详情")
            text = wait_for_detail_text(browser, sid, DETAIL_SELECTORS)
            page_text = str(status.get("text") or "")
            # 新版详情页的 JD 正文不含岗位名和"职位描述"标题，二者都在正文外围；
            # 正文和整页都对不上才判定串页或不可信。
            if title and title not in text and title not in page_text:
                raise RuntimeError("智联招聘未返回当前岗位的完整详情")
            if len(text) < 120 or not any(marker in text or marker in page_text for marker in DETAIL_MARKERS):
                raise RuntimeError("智联招聘未返回可信的岗位描述")
            return {"description": text, "requirements": self._extract_requirements(text)} if text else {}
        finally:
            browser.close()

    def _parse_card(self, card: dict) -> Optional[dict]:
        if "name" in card:
            return self._parse_record(card)
        return self._parse_legacy_card(card)

    def _parse_record(self, record: dict) -> Optional[dict]:
        """解析结果页组件数据（或 DOM 退化读取）得到的一条职位。"""
        title = clean_title(str(record.get("name", "")))
        if not title:
            return None
        company = str(record.get("company") or "").strip()
        salary = parse_salary(str(record.get("salary") or ""))
        job_id = str(record.get("number") or "").strip()
        if not job_id:
            # DOM 退化路径拿不到 number，用公司+岗位+薪资生成稳定 ID 以便跨轮去重。
            digest = hashlib.sha1("|".join((company, title, salary)).encode("utf-8")).hexdigest()
            job_id = f"dom-{digest[:16]}"
        location_text = " ".join(
            str(record.get(key) or "").strip() for key in ("city", "district", "street")
        ).strip()
        location = extract_location(location_text) or str(record.get("city") or "").strip()
        experience = parse_experience(str(record.get("experience") or ""))
        education = parse_education(str(record.get("education") or ""))
        skills = [str(item).strip() for item in (record.get("skills") or []) if str(item).strip()]
        tags: list[str] = []
        for item in [experience, education, *skills]:
            if item and item not in tags:
                tags.append(item)
        return self.normalize_job({
            "job_id": job_id,
            "title": title,
            "company": company,
            "salary": salary,
            "location": location,
            "experience": experience,
            "education": education,
            "tags": tags[:10],
            "description": "",
            "requirements": skills[:10],
            "url": str(record.get("url") or "").strip(),
        })

    def _parse_legacy_card(self, card: dict) -> Optional[dict]:
        """旧版结果页（卡片带 jobs.zhaopin.com 详情链接）的文本解析。"""
        href = str(card.get("href", ""))
        match = re.search(r"(?:jobs\.zhaopin\.com/|positionId=|/jobdetail/)([A-Za-z0-9_-]+)", href)
        job_id = match.group(1) if match else href
        title = clean_title(str(card.get("title", "")))
        text = str(card.get("text", ""))
        if not job_id or not title:
            return None
        experience = parse_experience(text)
        education = parse_education(text)
        return self.normalize_job({
            "job_id": job_id,
            "title": title,
            "company": parse_company(text, title),
            "salary": parse_salary(text),
            "location": extract_location(text),
            "experience": experience,
            "education": education,
            "tags": [item for item in (experience, education) if item],
            "description": "",
            "requirements": [],
            "url": href,
        })

    @staticmethod
    def _extract_requirements(text: str) -> list[str]:
        skills = ["Java", "Python", "Go", "C++", "JavaScript", "TypeScript", "Spring", "Vue", "React", "MySQL", "Redis", "Docker", "Linux", "数据分析", "项目管理", "用户研究", "Excel"]
        return [skill for skill in skills if re.search(re.escape(skill), text, re.I)][:10]
