"""Open and monitor all recruitment sites in the isolated CDP Chrome."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.crawlers.cdp_browser import CdpBrowser, boss_login_status, extract_cards, page_status
from app.crawlers.liepin import SELECTORS as LIEPIN_SELECTORS
from app.crawlers.zhaopin import SELECTORS as ZHAOPIN_SELECTORS


PLATFORMS = {
    "zhipin": {
        "label": "BOSS Zhipin",
        "url": "https://www.zhipin.com/web/geek/job?query=Java&city=101020100",
        "selectors": ["a[href*='/job_detail/']", "li.job-card-box a.job-name"],
        "login_hosts": ["login.zhipin.com"],
    },
    "zhaopin": {
        "label": "Zhaopin",
        "url": "https://www.zhaopin.com/sou/?kw=Java",
        "selectors": ZHAOPIN_SELECTORS,
        "login_hosts": ["passport.zhaopin.com"],
    },
    "liepin": {
        "label": "Liepin",
        "url": "https://www.liepin.com/zhaopin/?key=Java",
        "selectors": LIEPIN_SELECTORS,
        "login_hosts": ["passport.liepin.com", "/user/login"],
    },
}


def _is_ready(browser: CdpBrowser, session_id: str, config: dict) -> tuple[bool, str]:
    status = page_status(browser, session_id)
    url = str(status.get("url", "")).lower()
    title = str(status.get("title", "")).strip()
    text = str(status.get("text", ""))
    if any(marker in url for marker in config["login_hosts"]):
        return False, "waiting for login"
    if status.get("loginPrompts"):
        return False, "login button is still visible"
    if any(marker in text for marker in ("登录后查看", "登录查看更多", "请先登录")):
        return False, "waiting for login"
    blocked_markers = (
        "安全验证", "访问异常", "网络异常", "验证码", "请求过于频繁",
        "滑动验证", "verify", "captcha", "access denied",
    )
    marker = next((item for item in blocked_markers if item.lower() in text.lower()), "")
    if marker:
        return False, f"verification or access restriction detected ({marker}; url={url})"
    cards = extract_cards(browser, session_id, config["selectors"])
    if not cards:
        page = title or url or "unknown page"
        return False, f"no job list yet (page={page[:100]})"
    return True, f"ready ({len(cards)} jobs visible)"


def _format_states(states: dict[str, tuple[bool, str]]) -> str:
    return " | ".join(
        f"{PLATFORMS[name]['label']}: {'OK' if ready else 'WAIT'} ({detail})"
        for name, (ready, detail) in states.items()
    )


def monitor(port: int, timeout: int, interval: int, heartbeat: int = 30) -> int:
    browser = CdpBrowser(port)
    sessions: dict[str, str] = {}
    try:
        browser.connect()
        print("Opening BOSS Zhipin, Zhaopin and Liepin in the dedicated Chrome...")
        for name, config in PLATFORMS.items():
            _, session_id = browser.open_page(config["url"], background=False, wait_seconds=1.0)
            sessions[name] = session_id

        print("Log in to all three sites. This monitor exits only when every job list is available.")
        deadline = time.monotonic() + timeout
        previous = None
        last_report = 0.0
        states = {name: (False, "not checked") for name in PLATFORMS}
        while time.monotonic() < deadline:
            # Check the fast DOM-based platforms first. The strict BOSS network
            # probe can legitimately take up to 25 seconds on every attempt.
            check_order = ("zhaopin", "liepin", "zhipin")
            for name in check_order:
                if states[name][0]:
                    continue
                config = PLATFORMS[name]
                print(f"Checking {config['label']}...", flush=True)
                try:
                    states[name] = (
                        boss_login_status(port)
                        if name == "zhipin"
                        else _is_ready(browser, sessions[name], config)
                    )
                except Exception as exc:
                    states[name] = (False, f"check failed: {str(exc)[:120]}")
            snapshot = tuple((name, *states[name]) for name in PLATFORMS)
            now = time.monotonic()
            if snapshot != previous or now - last_report >= heartbeat:
                remaining = max(0, round(deadline - now))
                print(f"{_format_states(states)} | remaining={remaining}s", flush=True)
                previous = snapshot
                last_report = now
            if all(ready for ready, _ in states.values()):
                print("All three recruitment sites are logged in and ready.")
                return 0
            time.sleep(interval)
        print(f"Login monitoring timed out after {timeout} seconds.")
        return 1
    finally:
        # Keep the three tabs and Chrome open for scheduled crawling.
        browser.close(close_pages=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--interval", type=int, default=3)
    parser.add_argument("--heartbeat", type=int, default=30)
    args = parser.parse_args()
    if args.timeout < 1 or args.interval < 1 or args.heartbeat < 1:
        parser.error("--timeout, --interval and --heartbeat must be positive integers")
    raise SystemExit(monitor(args.cdp_port, args.timeout, args.interval, args.heartbeat))


if __name__ == "__main__":
    main()
