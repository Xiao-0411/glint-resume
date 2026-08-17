"""三平台统一采集：全部走 boss-zhipin-scraper 的原生 CDP 引擎。

为什么不用 Playwright：
`connect_over_cdp` 连上的瞬间就会对**所有**已打开标签页硬编码下发
Runtime.enable / Page.enable / Target.setAutoAttach（playwright-core 内部，
无开关）。BOSS 的风控据此把会话踢回登录页，可见性伪装挡不住。

这里复用 vendor 脚本里那套手写 CDP：
- 只发 Page.navigate / Network.enable / Network.getResponseBody，不发 Runtime.enable
- 每个平台一个后台标签页，配可见性伪装 + 焦点仿真
- 被动捕获页面自身的搜索接口响应，拿明文薪资（列表 DOM 的薪资是字体反爬后的字形）

同一个专用 Chrome、同一个 profile 服务三个平台：登录一次，之后全自动。

上游脚本 MIT 许可，见 vendor/boss_zhipin_scraper/LICENSE。
"""
import asyncio
import base64
import json
import logging
import os
import random
import sys
import time
from typing import Callable, Dict, List, Optional

from app.crawlers.api_capture import (
    CITY_NATIONWIDE,
    ProbeStatus,
    build_search_url,
    classify,
    matches_api_path,
)

logger = logging.getLogger("glint.crawler.cdp")

_HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "vendor", "boss_zhipin_scraper"))
VENDOR_SCRIPTS = os.path.join(VENDOR_DIR, "scripts")

PLATFORM_LABELS = {"zhipin": "BOSS直聘", "zhaopin": "智联招聘", "liepin": "猎聘"}

# 每个平台的登录判定页：能拿到搜索接口响应就算登录可用
LOGIN_CHECK_KEYWORD = "Java"


def _load_vendor():
    """按需导入 vendor 脚本，复用它的 CDPSession / Chrome 生命周期管理。"""
    if VENDOR_SCRIPTS not in sys.path:
        sys.path.insert(0, VENDOR_SCRIPTS)
    import boss_cdp_raw  # noqa: E402

    return boss_cdp_raw


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


CDP_PORT = _env_int("CRAWLER_CDP_PORT", 9333)
PAGES_PER_KEYWORD = _env_int("CRAWLER_PAGES_PER_KEYWORD", 2)
PAGE_DELAY_MIN = _env_float("CRAWLER_PAGE_DELAY_MIN", 12.0)
PAGE_DELAY_MAX = _env_float("CRAWLER_PAGE_DELAY_MAX", 22.0)
CAPTURE_TIMEOUT = _env_float("CRAWLER_CAPTURE_TIMEOUT", 25.0)
LOGIN_TIMEOUT = _env_int("CRAWLER_LOGIN_TIMEOUT", 300)


class PlatformBlocked(RuntimeError):
    """登录态失效或被风控 —— 停止该平台，不要重试加剧封禁。"""


class LoginRequired(RuntimeError):
    """专用浏览器需要人工登录一次。"""


# ============================================================
# 单平台标签页
# ============================================================
class PlatformTab:
    """一个平台占一个后台标签页，独立捕获自己的接口响应。"""

    def __init__(self, vendor, cdp, platform: str):
        self.vendor = vendor
        self.cdp = cdp
        self.platform = platform
        self.session_id: Optional[str] = None
        self.target_id: Optional[str] = None
        self._consumed = set()

    def open(self) -> None:
        # background=True：不抢用户前台焦点；vendor 会顺带装好可见性伪装
        # （document.hidden=false / visibilityState=visible / hasFocus=true）
        # 并开启 Emulation.setFocusEmulationEnabled。
        self.target_id, self.session_id = self.vendor.create_page_session(
            self.cdp, background=True
        )
        self.cdp.send("Network.enable", {}, self.session_id)
        logger.info("tab_opened", extra={"platform": self.platform})

    def close(self) -> None:
        if self.target_id:
            try:
                self.cdp.send("Target.closeTarget", {"targetId": self.target_id})
            except Exception as exc:
                logger.debug("tab_close_failed", extra={"platform": self.platform, "error": str(exc)})
            self.target_id = None
            self.session_id = None

    # -- 响应捕获 ------------------------------------------------
    def _next_completed(self) -> Optional[str]:
        """扫事件缓冲，找一个属于本标签页、已完成且未消费的目标接口请求。"""
        requests_seen = {}
        finished = set()
        for ev in self.cdp.events:
            if ev.get("sessionId") != self.session_id:
                continue  # 只认自己标签页的事件，避免串平台
            method = ev.get("method", "")
            params = ev.get("params", {})
            if method == "Network.responseReceived":
                url = (params.get("response") or {}).get("url", "")
                if matches_api_path(self.platform, url):
                    requests_seen[params.get("requestId")] = (params.get("response") or {}).get(
                        "status", 200
                    )
            elif method == "Network.requestWillBeSent":
                if matches_api_path(self.platform, (params.get("request") or {}).get("url", "")):
                    requests_seen.setdefault(params.get("requestId"), 200)
            elif method == "Network.loadingFinished":
                finished.add(params.get("requestId"))
        for rid, status in requests_seen.items():
            if rid in finished and rid not in self._consumed:
                return rid, status
        return None

    def drain(self) -> None:
        """开新一轮：把旧事件和已消费记录清掉，避免上个关键词的结果串进来。"""
        self.cdp.events = [
            ev for ev in self.cdp.events if ev.get("sessionId") != self.session_id
        ]
        self._consumed.clear()

    def wait_response(self, timeout: float) -> Optional[tuple]:
        """等本标签页的下一个目标接口响应，返回 (http_status, json)。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self._next_completed()
            if found is None:
                self.cdp.drain_events(min(0.5, max(0.05, deadline - time.time())))
                continue
            rid, status = found
            self._consumed.add(rid)
            body = self._fetch_body(rid)
            if body is None:
                continue
            try:
                return status, json.loads(body)
            except (json.JSONDecodeError, ValueError):
                logger.debug("capture_not_json", extra={"platform": self.platform})
        return None

    def _fetch_body(self, request_id: str) -> Optional[str]:
        try:
            result = self.cdp.send(
                "Network.getResponseBody", {"requestId": request_id}, self.session_id
            )
        except Exception as exc:
            logger.debug("body_fetch_failed", extra={"platform": self.platform, "error": str(exc)})
            return None
        payload = result.get("result", {})
        body = payload.get("body", "")
        if payload.get("base64Encoded"):
            try:
                body = base64.b64decode(body).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                return None
        return body

    # -- 行为模拟 ------------------------------------------------
    def navigate(self, url: str) -> None:
        self.cdp.send("Page.navigate", {"url": url}, self.session_id)

    def human_scroll(self) -> None:
        """随机滚动触发懒加载，同时让轨迹更像真人。"""
        for _ in range(random.randint(3, 6)):
            delta = -random.randint(50, 150) if random.random() < 0.15 else random.randint(150, 500)
            try:
                self.cdp.eval_js(f"window.scrollBy(0,{delta}); void 0;", self.session_id)
            except Exception:
                return
            time.sleep(random.uniform(2.0, 4.0) if random.random() < 0.3 else random.uniform(0.5, 1.5))

    def current_url(self) -> str:
        try:
            return self.cdp.eval_js("location.href", self.session_id) or ""
        except Exception:
            return ""


# ============================================================
# 采集器
# ============================================================
class UnifiedCDPCollector:
    """一个专用 Chrome + 三个后台标签页，全部走原生 CDP。

    所有 CDP 调用都是同步阻塞的（websocket-client），因此对外暴露 async 接口时
    统一用 asyncio.to_thread 包一层，避免阻塞事件循环。
    """

    def __init__(self, city: str = ""):
        self.city = city or CITY_NATIONWIDE
        self.vendor = None
        self.cdp = None
        self.tabs: Dict[str, PlatformTab] = {}
        self.errors: Dict[str, str] = {}
        self.warnings: Dict[str, List[str]] = {}
        self.blocked: Dict[str, bool] = {}
        self.platforms: List[str] = []

    # -- 生命周期 ------------------------------------------------
    async def start_and_wait_for_login(self, platforms: Optional[List[str]] = None) -> None:
        await asyncio.to_thread(self._start_sync, platforms or list(PLATFORM_LABELS))

    def _start_sync(self, platforms: List[str]) -> None:
        self.vendor = _load_vendor()
        self._ensure_chrome()
        self.cdp = self.vendor.CDPSession(CDP_PORT)

        for platform in platforms:
            tab = PlatformTab(self.vendor, self.cdp, platform)
            tab.open()
            self.tabs[platform] = tab
        self.platforms = list(self.tabs)

        # 逐个平台确认登录，未登录的平台等人工登录（不阻塞其它平台）
        pending = []
        for platform, tab in self.tabs.items():
            state = self._probe_login(tab)
            label = PLATFORM_LABELS[platform]
            if state is ProbeStatus.AVAILABLE:
                print(f"  [OK]   {label} 已登录", flush=True)
            elif state is ProbeStatus.EMPTY:
                print(f"  [OK]   {label} 接口可用（本次无匹配职位）", flush=True)
            else:
                print(f"  [WAIT] {label} 需要登录", flush=True)
                pending.append(platform)

        if pending:
            self._wait_for_manual_login(pending)

    def _ensure_chrome(self) -> None:
        """确保专用 Chrome 已在 CDP 端口上跑着；没有就拉起来。"""
        v = self.vendor
        if v.is_cdp_ready(CDP_PORT):
            logger.info("chrome_already_running", extra={"port": CDP_PORT})
            return

        profile = v.prepare_cdp_profile(copy_login_state=False, reset=False)
        profile_dir = profile["path"]
        v.stop_cdp_chrome(profile_dir)
        print(f"启动采集专用 Chrome（profile: {profile_dir}）...", flush=True)
        v.launch_chrome([
            v.DEFAULT_CHROME_PATH,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
        ])
        if not v.wait_for_cdp(CDP_PORT):
            raise RuntimeError(
                f"专用 Chrome 未能在端口 {CDP_PORT} 上就绪。"
                f"端口被占用时可设 CRAWLER_CDP_PORT 换一个。"
            )

    def _probe_login(self, tab: PlatformTab) -> ProbeStatus:
        """用一次真实搜索判断该平台能不能拿到数据。"""
        tab.drain()
        url = build_search_url(tab.platform, LOGIN_CHECK_KEYWORD, 1, self.city)
        tab.navigate(url)
        time.sleep(random.uniform(2.0, 4.0))
        got = tab.wait_response(CAPTURE_TIMEOUT)
        if got is None:
            tab.human_scroll()
            got = tab.wait_response(CAPTURE_TIMEOUT)
        if got is None:
            return ProbeStatus.RESPONSE_ERROR
        status, data = got
        return classify(tab.platform, status, data).status

    def _wait_for_manual_login(self, pending: List[str]) -> None:
        """等人工在专用 Chrome 里登录这些平台。"""
        names = "、".join(PLATFORM_LABELS[p] for p in pending)
        print(
            f"\n请在弹出的采集专用 Chrome 窗口里登录：{names}\n"
            f"（这个浏览器与你日常用的 Chrome 完全隔离，登录态会一直保留，只需登一次）\n"
            f"最长等待 {LOGIN_TIMEOUT} 秒，登录完成后会自动继续...",
            flush=True,
        )
        # 把待登录平台的页面切到前台，方便直接点登录
        first = self.tabs[pending[0]]
        try:
            self.cdp.send("Target.activateTarget", {"targetId": first.target_id})
        except Exception:
            pass

        deadline = time.time() + LOGIN_TIMEOUT
        remaining = list(pending)
        while remaining and time.time() < deadline:
            time.sleep(5)
            for platform in list(remaining):
                state = self._probe_login(self.tabs[platform])
                if state in (ProbeStatus.AVAILABLE, ProbeStatus.EMPTY):
                    print(f"  [OK]   {PLATFORM_LABELS[platform]} 登录成功", flush=True)
                    remaining.remove(platform)
        for platform in remaining:
            # 没登上的平台标记出来，但不阻塞已登录的平台开抓
            self.errors[platform] = f"{PLATFORM_LABELS[platform]} 未登录，本轮跳过"
            self.blocked[platform] = True
            print(f"  [SKIP] {PLATFORM_LABELS[platform]} 未登录，本轮跳过", flush=True)

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        # 只关我们开的标签页，专用 Chrome 保持运行以保留登录态
        for tab in self.tabs.values():
            tab.close()
        self.tabs = {}
        if self.cdp:
            try:
                self.cdp.close()
            except Exception:
                pass
            self.cdp = None

    # -- 采集 ----------------------------------------------------
    async def crawl_all(self, keywords: List[str]) -> Dict[str, List[dict]]:
        """按平台轮转抓取。

        所有平台共用一条 CDP websocket，所以不能真并发；改成按关键词轮转，
        既保证三个平台都能推进，又让同平台两次请求之间自然隔开。
        """
        self.warnings = {}
        active = [p for p in self.platforms if not self.blocked.get(p)]
        return await asyncio.to_thread(self._crawl_sync, keywords, active)

    def _crawl_sync(self, keywords: List[str], platforms: List[str]) -> Dict[str, List[dict]]:
        out = {p: [] for p in self.platforms}
        seen = {p: set() for p in self.platforms}
        live = list(platforms)
        first = True

        for keyword in keywords:
            for page_no in range(1, PAGES_PER_KEYWORD + 1):
                for platform in list(live):
                    if not first:
                        time.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX) / max(1, len(live)))
                    first = False
                    try:
                        jobs = self._fetch_one(platform, keyword, page_no)
                    except PlatformBlocked as exc:
                        self.blocked[platform] = True
                        self.errors[platform] = str(exc)[:1000]
                        logger.warning("platform_blocked", extra={"platform": platform, "error": str(exc)})
                        live.remove(platform)
                        continue
                    except Exception as exc:
                        self.warnings.setdefault(platform, []).append(
                            f"{keyword} 第 {page_no} 页: {str(exc)[:200]}"
                        )
                        logger.warning(
                            "keyword_failed",
                            extra={"platform": platform, "keyword": keyword, "error": str(exc)},
                        )
                        continue
                    for job in jobs:
                        jid = job.get("platform_job_id")
                        if jid and jid not in seen[platform]:
                            seen[platform].add(jid)
                            out[platform].append(job)

        for platform in self.platforms:
            warns = self.warnings.get(platform, [])
            if not out[platform] and warns and not self.blocked.get(platform):
                self.errors.setdefault(platform, f"全部关键词抓取失败，例如 {warns[0]}")
        return out

    def _fetch_one(self, platform: str, keyword: str, page_no: int) -> List[dict]:
        tab = self.tabs[platform]
        tab.drain()
        tab.navigate(build_search_url(platform, keyword, page_no, self.city))
        time.sleep(random.uniform(2.0, 4.0))

        got = tab.wait_response(CAPTURE_TIMEOUT)
        if got is None:
            tab.human_scroll()  # 有些平台滚动后才发请求
            got = tab.wait_response(CAPTURE_TIMEOUT)
        if got is None:
            url = tab.current_url().lower()
            if any(m in url for m in ("/web/user/", "login", "passport")):
                raise PlatformBlocked(
                    f"{PLATFORM_LABELS[platform]} 登录态失效，页面被跳到 {url[:100]}"
                )
            raise RuntimeError(
                f"{PLATFORM_LABELS[platform]} 未捕获到搜索接口响应"
                f"（{keyword} 第 {page_no} 页）；可能接口路径变更或需要人工验证"
            )

        status, data = got
        result = classify(platform, status, data)
        if result.blocked:
            raise PlatformBlocked(f"{PLATFORM_LABELS[platform]} {result.describe()}")
        if result.status is ProbeStatus.RESPONSE_ERROR:
            raise RuntimeError(f"{PLATFORM_LABELS[platform]} {result.describe()}")

        tab.human_scroll()
        return result.jobs
