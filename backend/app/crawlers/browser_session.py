"""通过可见浏览器会话采集招聘平台公开职位。

登录态只保存在本机 profile 目录，职位数据才会写入数据库；不读取或上传 Cookie。

采集策略（参考 boss-zhipin-scraper skill）：
浏览器以正常用户方式打开搜索页，我们被动捕获页面自己发出的搜索接口响应，
从 JSON 里拿明文薪资和结构化字段。不解析 DOM —— 列表页薪资经过字体反爬，
DOM 里读到的是错位字形。DOM 解析仅作为显式开启的降级手段。
"""
import asyncio
import logging
import os
import random
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

from playwright.async_api import BrowserContext, Page, async_playwright

from app.crawlers.api_capture import (
    CITY_NATIONWIDE,
    ProbeStatus,
    ResponseCapture,
    build_search_url,
    classify,
)

logger = logging.getLogger("glint.crawler.browser")

PLATFORMS = {
    "zhipin": "BOSS直聘",
    "zhaopin": "智联招聘",
    "liepin": "猎聘",
}

# 平台首页，用于建立会话和判断登录态
HOME_URLS = {
    "zhipin": "https://www.zhipin.com/web/geek/job?query=%E4%BA%A7%E5%93%81%E7%BB%8F%E7%90%86",
    "zhaopin": "https://www.zhaopin.com/sou/?kw=%E4%BA%A7%E5%93%81%E7%BB%8F%E7%90%86",
    "liepin": "https://www.liepin.com/zhaopin/?key=%E4%BA%A7%E5%93%81%E7%BB%8F%E7%90%86",
}

HOSTS = {"zhipin": "zhipin.com", "zhaopin": "zhaopin.com", "liepin": "liepin.com"}

# 后台标签页在页面看来是 hidden，BOSS 等平台的可见性反爬会据此判定为机器人，
# 表现就是「一连上就被踢回登录页」。三个平台并发时至多一个标签页在前台，
# 所以必须在导航前覆盖可见性属性。参考 boss-zhipin-scraper 的同名处理。
BACKGROUND_VISIBILITY_SCRIPT = """
Object.defineProperty(document, 'hidden', {get: () => false});
Object.defineProperty(document, 'visibilityState', {get: () => 'visible'});
Object.defineProperty(document, 'webkitHidden', {get: () => false});
Object.defineProperty(document, 'webkitVisibilityState', {get: () => 'visible'});
document.hasFocus = () => true;
"""

# 被平台判定为未登录时页面会跳到这些路径
LOGIN_URL_MARKERS = ("/web/user/", "/user/login", "login.", "/login", "passport")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


# 翻页/关键词间隔。默认值参考 skill 的 12-22 秒，宁可慢也不要触发风控。
PAGE_DELAY_MIN = _env_float("CRAWLER_PAGE_DELAY_MIN", 12.0)
PAGE_DELAY_MAX = _env_float("CRAWLER_PAGE_DELAY_MAX", 22.0)
PAGES_PER_KEYWORD = _env_int("CRAWLER_PAGES_PER_KEYWORD", 2)
CAPTURE_TIMEOUT = _env_float("CRAWLER_CAPTURE_TIMEOUT", 25.0)
ALLOW_DOM_FALLBACK = os.getenv("CRAWLER_ALLOW_DOM_FALLBACK", "").lower() in ("1", "true", "yes")


class PlatformBlocked(RuntimeError):
    """登录态失效或被风控拦截 —— 必须停止该平台抓取，不要重试加剧封禁。"""


class BrowserSessionCollector:
    def __init__(self, profile_dir: str = ""):
        # 浏览器由 启动登录浏览器.bat 用该目录启动，这里只记录用于日志排查
        self.profile_dir = profile_dir or os.getenv(
            "CRAWLER_CHROME_USER_DATA_DIR",
            os.path.join(os.path.dirname(__file__), "..", "..", ".crawler_chrome_profile_connected"),
        )
        self._playwright = None
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.pages: Dict[str, Page] = {}
        self.captures: Dict[str, ResponseCapture] = {}
        self.errors: Dict[str, str] = {}
        self.warnings: Dict[str, List[str]] = {}
        self.blocked: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    async def start_and_wait_for_login(self) -> None:
        self._playwright = await async_playwright().start()
        cdp_url = os.getenv("CRAWLER_CDP_URL", "http://127.0.0.1:9222")
        try:
            # no_defaults 关掉 Playwright 默认的焦点仿真/媒体仿真等全局覆盖，
            # 我们只对采集用的标签页按需开启，减少可被指纹识别的默认行为。
            self.browser = await self._playwright.chromium.connect_over_cdp(cdp_url, no_defaults=True)
            contexts = self.browser.contexts
            if not contexts:
                raise RuntimeError("远程 Chrome 没有可用的浏览器上下文")
            self.context = contexts[0]
        except Exception as exc:
            await self._playwright.stop()
            self._playwright = None
            raise RuntimeError(
                "无法连接到已启动的 Chrome。请先运行 启动登录浏览器.bat；该脚本会使用专用 Chrome 用户目录，"
                "不要直接双击普通 Chrome。"
                f"\n连接地址: {cdp_url}\n原因: {exc}"
            )

        existing = list(self.context.pages)
        for platform in PLATFORMS:
            page = next((p for p in existing if HOSTS[platform] in p.url), None)
            if page is None:
                page = await self.context.new_page()
                existing.append(page)
            self.pages[platform] = page
            # 必须在任何导航之前装好可见性覆盖，否则首个页面就会以 hidden 状态
            # 加载并被判定为机器人。add_init_script 对后续每次导航都生效。
            await self._mask_background_state(platform, page)
            capture = ResponseCapture(page, platform)
            capture.attach()
            self.captures[platform] = capture
            try:
                await page.goto(HOME_URLS[platform], wait_until="domcontentloaded", timeout=45000)
            except Exception as exc:
                self.errors[platform] = str(exc)[:1000]
                logger.warning("platform_open_failed", extra={"platform": platform, "error": str(exc)})
        logger.info("browser_session_ready", extra={"platforms": list(self.pages)})
        print("已连接到现有 Chrome 登录会话，开始抓取三个平台职位。", flush=True)

    # ------------------------------------------------------------------
    # 反检测：让后台标签页看起来是前台
    # ------------------------------------------------------------------
    async def _mask_background_state(self, platform: str, page: Page) -> None:
        """覆盖可见性属性并开启焦点仿真。

        三个平台并发时至多一个标签页真的在前台，其余的 document.hidden 为 true，
        BOSS 的可见性检查会据此把会话踢回登录页。焦点仿真只改渲染进程的认知，
        不会激活窗口抢用户前台焦点。
        """
        try:
            await page.add_init_script(BACKGROUND_VISIBILITY_SCRIPT)
        except Exception as exc:
            logger.warning("visibility_patch_failed", extra={"platform": platform, "error": str(exc)})
        try:
            session = await self.context.new_cdp_session(page)
            await session.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
            await session.detach()
        except Exception as exc:
            # 拿不到焦点仿真也还有 JS 覆盖兜底，不该因此中断
            logger.debug("focus_emulation_failed", extra={"platform": platform, "error": str(exc)})

    @staticmethod
    def _looks_like_login_page(url: str) -> bool:
        low = url.lower()
        return any(marker in low for marker in LOGIN_URL_MARKERS)

    # ------------------------------------------------------------------
    # 人类行为模拟
    # ------------------------------------------------------------------
    async def _human_scroll(self, page: Page) -> None:
        """随机滚动，触发懒加载同时让行为轨迹更像真人。"""
        for _ in range(random.randint(3, 6)):
            delta = -random.randint(50, 150) if random.random() < 0.15 else random.randint(150, 500)
            try:
                await page.mouse.wheel(0, delta)
            except Exception:
                return
            await asyncio.sleep(random.uniform(2.0, 4.0) if random.random() < 0.3 else random.uniform(0.5, 1.5))
        if random.random() < 0.4:
            try:
                await page.mouse.move(random.randint(100, 800), random.randint(100, 600))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 采集
    # ------------------------------------------------------------------
    async def crawl_all(self, keywords: List[str], city: str = CITY_NATIONWIDE) -> Dict[str, List[dict]]:
        """三个平台并发抓取；单平台内部串行且带间隔，避免并发放大风控风险。"""
        # 只清理上一轮的采集态；start_and_wait_for_login 记录的打开失败要保留
        self.warnings = {}
        self.blocked = {}
        platforms = list(self.pages)
        results = await asyncio.gather(
            *(self._crawl_platform(p, keywords, city) for p in platforms),
            return_exceptions=True,
        )
        out: Dict[str, List[dict]] = {}
        for platform, res in zip(platforms, results):
            if isinstance(res, BaseException):
                self.errors[platform] = str(res)[:1000]
                logger.error("platform_crawl_failed", extra={"platform": platform, "error": str(res)})
                out[platform] = []
            else:
                out[platform] = res
        return out

    async def _crawl_platform(self, platform: str, keywords: List[str], city: str) -> List[dict]:
        page = self.pages[platform]
        capture = self.captures[platform]
        collected: List[dict] = []
        seen = set()
        first = True

        for keyword in keywords:
            for page_no in range(1, PAGES_PER_KEYWORD + 1):
                if not first:
                    await asyncio.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))
                first = False
                try:
                    result = await self._fetch_page(platform, page, capture, keyword, page_no, city)
                except PlatformBlocked as exc:
                    # 风控/掉登录：立刻停整个平台，保留已抓到的数据
                    self.blocked[platform] = True
                    self.errors[platform] = str(exc)[:1000]
                    logger.warning("platform_blocked", extra={"platform": platform, "error": str(exc)})
                    return self._dedupe(collected, seen)
                except Exception as exc:
                    # 单个关键词失败不应终止整个平台，也不应把平台标记成失败；
                    # 只有一条都没抓到时才在收尾处上报为错误。
                    self.warnings.setdefault(platform, []).append(
                        f"{keyword} 第 {page_no} 页: {str(exc)[:200]}"
                    )
                    logger.warning(
                        "keyword_failed",
                        extra={"platform": platform, "keyword": keyword, "page": page_no, "error": str(exc)},
                    )
                    break

                if not result:
                    break  # 该关键词后续页大概率也是空的
                collected.extend(result)

        jobs = self._dedupe(collected, seen)
        warns = self.warnings.get(platform, [])
        if not jobs and warns:
            # 全军覆没才算平台失败，附上第一条原因便于排查
            self.errors.setdefault(platform, f"全部关键词抓取失败，例如 {warns[0]}")
        return jobs

    async def _fetch_page(
        self, platform: str, page: Page, capture: ResponseCapture,
        keyword: str, page_no: int, city: str,
    ) -> List[dict]:
        capture.drain()  # 清掉上一轮残留，避免串数据
        url = build_search_url(platform, keyword, page_no, city)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:
            raise RuntimeError(f"打开搜索页失败: {exc}") from exc

        # 被踢回登录页时早点报出来，不要干等捕获超时
        if self._looks_like_login_page(page.url):
            raise PlatformBlocked(
                f"{PLATFORMS[platform]} 登录态失效，页面被跳转到 {page.url[:120]}；"
                "请在该 Chrome 窗口里重新登录后再启动爬虫"
            )

        captured = await capture.wait_next(timeout=CAPTURE_TIMEOUT)
        if captured is None:
            # 有些平台要滚动后才发请求，滚一次再等一轮
            await self._human_scroll(page)
            captured = await capture.wait_next(timeout=CAPTURE_TIMEOUT)

        if captured is None:
            if ALLOW_DOM_FALLBACK:
                logger.warning("capture_timeout_dom_fallback", extra={"platform": platform, "keyword": keyword})
                return await self._extract_dom(platform, page)
            raise RuntimeError(
                f"{PLATFORMS[platform]} 未捕获到搜索接口响应（关键词 {keyword} 第 {page_no} 页）；"
                "可能是页面结构或接口路径变更，也可能需要在浏览器中完成验证"
            )

        http_status, data = captured
        probe = classify(platform, http_status, data)
        if probe.blocked:
            raise PlatformBlocked(f"{PLATFORMS[platform]} {probe.describe()}")
        if probe.status is ProbeStatus.RESPONSE_ERROR:
            raise RuntimeError(f"{PLATFORMS[platform]} {probe.describe()}")

        await self._human_scroll(page)
        return probe.jobs

    @staticmethod
    def _dedupe(jobs: List[dict], seen: set) -> List[dict]:
        out = []
        for job in jobs:
            key = job.get("platform_job_id")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(job)
        return out

    # ------------------------------------------------------------------
    # DOM 降级（默认关闭：列表页薪资经过字体反爬，读出来可能不可信）
    # ------------------------------------------------------------------
    async def _extract_dom(self, platform: str, page: Page) -> List[dict]:
        selectors = {
            "zhaopin": "a.jobinfo__name",
            "liepin": 'a[href*="/job/"], a[href*="/a/"]',
            "zhipin": 'a[href*="/job_detail/"]',
        }
        links = await page.locator(selectors[platform]).all()
        jobs = []
        for link in links[:80]:
            try:
                title = (await link.inner_text()).strip()
                href = await link.get_attribute("href") or ""
            except Exception:
                continue
            if not title or not href:
                continue
            if href.startswith("/"):
                href = urljoin(HOME_URLS[platform], href)
            match = re.search(r"(?:job_detail/|/job/|/a/|jobdetail/)([A-Za-z0-9_~-]+)", href)
            jobs.append({
                "platform": platform,
                "platform_job_id": (match.group(1) if match else href)[:128],
                "title": title[:256],
                "company": "未知公司",
                "salary": "",             # 字体反爬，不写入不可信薪资
                "location": "", "experience": "", "education": "",
                "tags": [], "description": "", "requirements": [],
                "url": href[:512],
                "salary_source": "dom",
            })
        return jobs

    async def close(self):
        # 这是通过 CDP 连接用户浏览器，退出爬虫时不要关闭用户的 Chrome。
        for capture in self.captures.values():
            capture.detach()
        self.captures = {}
        self.pages = {}
        self.context = None
        self.browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
