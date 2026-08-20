"""猎聘 crawler backed by the shared logged-in CDP Chrome session."""
from __future__ import annotations

import asyncio
import os
import re
from typing import List, Optional
from urllib.parse import quote

from app.crawlers.base import BaseCrawler, select_cities, select_keywords
from app.crawlers.cdp_browser import CdpBrowser, page_status, wait_for_cards, wait_for_detail_text


SEARCH_URL = "https://www.liepin.com/zhaopin/?key={}"
SELECTORS = ["a[href*='/job/']", "a[href*='/a/']", "a[class*='job-title']"]
DETAIL_SELECTORS = [
    ".job-intro-container", ".job-intro-content", ".job-description",
    "[class*='job-intro'] [class*='content']", "[class*='job-description']",
]
DETAIL_MARKERS = ("岗位职责", "职位职责", "任职要求", "职位要求", "职位描述")


def _first(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0).strip()
    return ""


class LiepinCrawler(BaseCrawler):
    platform = "liepin"
    base_url = "https://www.liepin.com"

    async def crawl(self, keywords: List[str] = None, cities: List[str] = None) -> List[dict]:
        return await asyncio.to_thread(self._crawl_sync, select_keywords(keywords), select_cities(cities))

    def _crawl_sync(self, keywords: List[str], cities: List[str]) -> List[dict]:
        browser = CdpBrowser(int(os.getenv("BOSS_SCRAPER_CDP_PORT", "9222")))
        seen: set[str] = set()
        jobs: list[dict] = []
        had_cards = False
        try:
            browser.connect()
            for city in cities:
                for keyword in keywords:
                    _, sid = browser.open_page(SEARCH_URL.format(quote(f"{city} {keyword}")))
                    cards = wait_for_cards(browser, sid, SELECTORS)
                    if not cards:
                        continue
                    had_cards = True
                    for card in cards:
                        job = self._parse_card(card)
                        if job and city in job["location"] and job["platform_job_id"] not in seen:
                            seen.add(job["platform_job_id"])
                            jobs.append(job)
            if not had_cards:
                raise RuntimeError("猎聘页面未显示职位，可能未登录或被风控拦截")
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
                raise RuntimeError("猎聘登录状态已失效，请重新登录后查看岗位详情")
            text = wait_for_detail_text(browser, sid, DETAIL_SELECTORS)
            if title and title not in text:
                raise RuntimeError("猎聘未返回当前岗位的完整详情")
            if len(text) < 120 or not any(marker in text for marker in DETAIL_MARKERS):
                raise RuntimeError("猎聘未返回可信的岗位描述")
            return {"description": text, "requirements": self._extract_requirements(text)} if text else {}
        finally:
            browser.close()

    def _parse_card(self, card: dict) -> Optional[dict]:
        href = str(card.get("href", ""))
        match = re.search(r"(?:/job/|/a/)([A-Za-z0-9_-]+)", href)
        job_id = match.group(1) if match else href
        title = self._clean_title(str(card.get("title", "")))
        text = str(card.get("text", ""))
        if not job_id or not title:
            return None
        company = _first(text, [r"[^\s|·]{2,}(?:有限公司|集团|科技|公司|研究院)"])
        if not company:
            lines = [line for line in re.split(r"\s+", text) if line]
            company = next((line for line in lines if line != title and len(line) >= 2), "未知公司")
        salary = _first(text, [r"面议", r"\d+(?:\.\d+)?\s*[-~至]\s*\d+(?:\.\d+)?\s*[万千kK元]"])
        location = _first(text, [r"(?:北京|上海|广州|深圳|杭州|南京|苏州|成都|武汉|西安|天津|重庆)(?:[-·][\u4e00-\u9fff]{2,8}(?:区|县|市))?"])
        experience = _first(text, [r"经验不限", r"\d+[-~至]?\d*年", r"应届生"])
        education = _first(text, [r"学历不限", r"大专|本科|硕士|博士|中专|高中"])
        tags = [item for item in (experience, education) if item]
        return self.normalize_job({
            "job_id": job_id,
            "title": title,
            "company": company,
            "salary": salary,
            "location": location,
            "experience": experience,
            "education": education,
            "tags": tags,
            "description": "",
            "requirements": [],
            "url": href,
        })

    @staticmethod
    def _clean_title(title: str) -> str:
        return re.split(r"【|\s+(?=\d+(?:\.\d+)?\s*[-~至]\s*\d+)", re.sub(r"\s+", " ", title.strip()), maxsplit=1)[0][:100].strip()

    @staticmethod
    def _extract_requirements(text: str) -> list[str]:
        skills = ["Java", "Python", "Go", "C++", "JavaScript", "TypeScript", "Spring", "Vue", "React", "MySQL", "Redis", "Docker", "Linux", "数据分析", "项目管理", "用户研究", "Excel"]
        return [skill for skill in skills if re.search(re.escape(skill), text, re.I)][:10]
