"""智联招聘 crawler backed by the shared logged-in CDP Chrome session."""
from __future__ import annotations

import asyncio
import os
import re
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
from app.crawlers.cdp_browser import CdpBrowser, page_status, wait_for_cards, wait_for_detail_text
from app.services.location_catalog import extract_location
from app.core.logging_config import get_logger

logger = get_logger("glint.crawler.zhaopin")

SEARCH_URL = "https://www.zhaopin.com/sou/?kw={}"
# 智联改版后 jobinfo__name 已不再出现在结果页，保留作兼容；
# 主力依赖结果列表容器内的 jobs.zhaopin.com 详情链接。
SELECTORS = [
    "a.jobinfo__name",
    "a[class*='jobinfo'][class*='name']",
    "div[class*='positionlist'] a[href*='jobs.zhaopin.com']",
    "div[class*='joblist'] a[href*='jobs.zhaopin.com']",
    "a[href*='jobs.zhaopin.com/CC']",
    "a[href*='jobs.zhaopin.com']",
    "a[href*='/jobdetail/']",
]
DETAIL_SELECTORS = [
    ".job-detail__content", ".describtion__detail-content", ".job-detail-content",
    "[class*='job-description']", "[class*='position-description']",
]
DETAIL_MARKERS = ("岗位职责", "职位职责", "任职要求", "职位要求", "职位描述")


class ZhaopinCrawler(BaseCrawler):
    platform = "zhaopin"
    base_url = "https://www.zhaopin.com"

    async def crawl(self, keywords: List[str] = None, cities: List[str] = None) -> List[dict]:
        return await asyncio.to_thread(self._crawl_sync, select_keywords(keywords), select_cities(cities))

    def _crawl_sync(self, keywords: List[str], cities: List[str]) -> List[dict]:
        browser = CdpBrowser(int(os.getenv("BOSS_SCRAPER_CDP_PORT", "9222")))
        seen: set[str] = set()
        jobs: list[dict] = []
        had_cards = False
        rejected = 0
        try:
            browser.connect()
            sid = None
            for city in cities:
                for keyword in keywords:
                    _, sid = browser.open_page(
                        SEARCH_URL.format(quote(f"{city} {keyword}")),
                        reuse=True,
                    )
                    cards = wait_for_cards(browser, sid, SELECTORS)
                    if not cards:
                        continue
                    had_cards = True
                    for card in cards:
                        job = self._parse_card(card)
                        if not job:
                            continue
                        if not is_publishable(job, city=city):
                            rejected += 1
                            continue
                        if job["platform_job_id"] not in seen:
                            seen.add(job["platform_job_id"])
                            jobs.append(job)
            if not had_cards:
                raise RuntimeError("智联招聘页面未显示职位，可能未登录或被风控拦截")
            logger.info("zhaopin_crawl_done", extra={"kept": len(jobs), "rejected": rejected})
            return jobs
        finally:
            browser.close()

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
            if page_status(browser, sid).get("loginPrompts"):
                raise RuntimeError("智联招聘登录状态已失效，请重新登录后查看岗位详情")
            text = wait_for_detail_text(browser, sid, DETAIL_SELECTORS)
            if title and title not in text:
                raise RuntimeError("智联招聘未返回当前岗位的完整详情")
            if len(text) < 120 or not any(marker in text for marker in DETAIL_MARKERS):
                raise RuntimeError("智联招聘未返回可信的岗位描述")
            return {"description": text, "requirements": self._extract_requirements(text)} if text else {}
        finally:
            browser.close()

    def _parse_card(self, card: dict) -> Optional[dict]:
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
