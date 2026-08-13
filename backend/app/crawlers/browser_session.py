"""通过可见浏览器会话采集招聘平台公开职位。

登录态只保存在本机 profile 目录，职位数据才会写入数据库；不读取或上传 Cookie。
"""
import os
import re
from typing import Dict, List
from urllib.parse import quote, urljoin

from playwright.async_api import BrowserContext, Page, async_playwright

PLATFORMS = {
    "liepin": ("猎聘", "https://www.liepin.com/zhaopin/?key={keyword}"),
    "zhipin": ("BOSS直聘", "https://www.zhipin.com/web/geek/jobs?query={keyword}"),
    "zhaopin": ("智联招聘", "https://www.zhaopin.com/sou/?kw={keyword}"),
}


def _first(lines: List[str], pattern: str, default: str = "") -> str:
    rx = re.compile(pattern, re.I)
    return next((line.strip() for line in lines if rx.search(line)), default)


def _parse_card(platform: str, title: str, href: str, text: str) -> dict:
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
    salary = _first(lines, r"(面议|\d+(?:\.\d+)?\s*[-~至]\s*\d+(?:\.\d+)?\s*[万千kK元])")
    location = _first(lines, r"(?:北京|上海|广州|深圳|杭州|南京|苏州|成都|武汉|西安|天津|重庆|长沙|厦门|郑州|合肥|全国).*[·\-]")
    experience = _first(lines, r"经验不限|\d+\s*[-~至]?\s*\d*年|应届生")
    education = _first(lines, r"学历不限|大专|本科|硕士|博士|中专|高中")
    company = _first(lines, r"有限公司|集团|科技|公司|研究院|汽车|银行")
    for idx, line in enumerate(lines):
        if company:
            break
        if line == title:
            continue
        if line not in (salary, location, experience, education) and len(line) >= 2:
            if idx > 0 and (salary or location):
                company = line
                break
    if not company:
        company = _first(lines, r"[\u4e00-\u9fffA-Za-z]{2,}")
    tags = [line for line in lines if 1 < len(line) < 20 and line not in {title, salary, location, experience, education, company}][:8]
    job_id = re.search(r"(?:jobdetail/|/job/|job_detail/|/a/)([A-Za-z0-9_-]+)", href)
    platform_job_id = job_id.group(1) if job_id else href
    return {
        "platform": platform,
        "platform_job_id": platform_job_id[:128],
        "title": title[:256],
        "company": (company or "未知公司")[:256],
        "salary": salary,
        "location": location,
        "experience": experience,
        "education": education,
        "tags": tags,
        "description": "",
        "requirements": tags,
        "url": href,
    }


class BrowserSessionCollector:
    def __init__(self, profile_dir: str = ""):
        self.profile_dir = profile_dir or os.getenv(
            "CRAWLER_CHROME_USER_DATA_DIR",
            os.path.join(os.path.dirname(__file__), "..", "..", ".crawler_chrome_profile_connected"),
        )
        self._playwright = None
        self.browser = None
        self.context: BrowserContext | None = None
        self.pages: Dict[str, Page] = {}
        self.errors: Dict[str, str] = {}

    async def start_and_wait_for_login(self) -> None:
        self._playwright = await async_playwright().start()
        try:
            cdp_url = os.getenv("CRAWLER_CDP_URL", "http://127.0.0.1:9222")
            self.browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
            contexts = self.browser.contexts
            if not contexts:
                raise RuntimeError("远程 Chrome 没有可用的浏览器上下文")
            self.context = contexts[0]
        except Exception as exc:
            await self._playwright.stop()
            self._playwright = None
            raise RuntimeError(
                "无法连接到已启动的 Chrome。请先运行 启动登录浏览器.bat；该脚本会使用你的默认 Chrome 用户目录，"
                "不要直接双击普通 Chrome。"
                f"\n连接地址: {os.getenv('CRAWLER_CDP_URL', 'http://127.0.0.1:9222')}\n原因: {exc}"
            )
        existing_pages = list(self.context.pages)
        hosts = {"liepin": "liepin.com", "zhipin": "zhipin.com", "zhaopin": "zhaopin.com"}
        for platform, (label, template) in PLATFORMS.items():
            page = next((p for p in existing_pages if hosts[platform] in p.url), None)
            if page is None:
                page = await self.context.new_page()
            self.pages[platform] = page
            try:
                await page.goto(template.format(keyword=quote("产品经理")), wait_until="domcontentloaded", timeout=45000)
            except Exception as exc:
                self.errors[platform] = str(exc)[:1000]
        print("已连接到现有 Chrome 登录会话，开始抓取三个平台职位。", flush=True)

    async def crawl_all(self, keywords: List[str]) -> Dict[str, List[dict]]:
        result = {}
        self.errors = {}
        for platform, page in self.pages.items():
            jobs = []
            try:
                for keyword in keywords:
                    _, template = PLATFORMS[platform]
                    await page.goto(template.format(keyword=quote(keyword)), wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(2500)
                    jobs.extend(await self._extract(platform, page))
            except Exception as exc:
                self.errors[platform] = str(exc)[:1000]
            seen = set()
            result[platform] = [j for j in jobs if not (j["platform_job_id"] in seen or seen.add(j["platform_job_id"]))]
        return result

    async def _extract(self, platform: str, page: Page) -> List[dict]:
        if platform == "zhaopin":
            selector = "a.jobinfo__name"
        elif platform == "liepin":
            selector = 'a[href*="/job/"], a[href*="/a/"]'
        else:
            selector = 'a[href*="/job_detail/"]'
        links = await page.locator(selector).all()
        if not links:
            raise RuntimeError("需要登录或被平台风控拦截，页面未显示职位列表")
        jobs = []
        for link in links[:80]:
            title = (await link.inner_text()).strip()
            href = await link.get_attribute("href") or ""
            if not title or not href:
                continue
            if href.startswith("/"):
                href = urljoin(PLATFORMS[platform][1], href)
            card = link.locator("xpath=ancestor::*[contains(@class,'jobinfo') or contains(@class,'job-card') or self::li][1]")
            text = await card.inner_text() if await card.count() else title
            jobs.append(_parse_card(platform, title, href, text))
        return jobs

    async def close(self):
        # 这是通过 CDP 连接用户浏览器，退出爬虫时不要关闭用户的 Chrome。
        self.context = None
        self.browser = None
        if self._playwright:
            await self._playwright.stop()
