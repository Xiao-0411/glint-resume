"""Open and monitor all recruitment sites in the isolated CDP Chrome."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.crawlers.cdp_browser import CdpBrowser, boss_login_status, extract_cards, page_status


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
        "selectors": ["a.jobinfo__name", "a[class*='jobinfo'][class*='name']", "a[href*='jobs.zhaopin.com']"],
        "login_hosts": ["passport.zhaopin.com"],
    },
    "liepin": {
        "label": "Liepin",
        "url": "https://www.liepin.com/zhaopin/?key=Java",
        "selectors": ["a[href*='/job/']", "a[href*='/a/']", "a[class*='job-title']"],
        "login_hosts": ["passport.liepin.com", "/user/login"],
    },
}


def _is_ready(browser: CdpBrowser, session_id: str, config: dict) -> tuple[bool, str]:
    status = page_status(browser, session_id)
    url = str(status.get("url", "")).lower()
    text = str(status.get("text", ""))
    if any(marker in url for marker in config["login_hosts"]):
        return False, "waiting for login"
    if status.get("loginPrompts"):
        return False, "login button is still visible"
    if any(marker in text for marker in ("登录后查看", "登录查看更多", "请先登录")):
        return False, "waiting for login"
    cards = extract_cards(browser, session_id, config["selectors"])
    if not cards:
        return False, "no job list yet"
    return True, f"ready ({len(cards)} jobs visible)"


def monitor(port: int, timeout: int, interval: int) -> int:
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
        states = {name: (False, "not checked") for name in PLATFORMS}
        while time.monotonic() < deadline:
            for name, config in PLATFORMS.items():
                if states[name][0]:
                    continue
                try:
                    states[name] = (
                        boss_login_status(port)
                        if name == "zhipin"
                        else _is_ready(browser, sessions[name], config)
                    )
                except Exception as exc:
                    states[name] = (False, f"check failed: {str(exc)[:120]}")
            snapshot = tuple((name, *states[name]) for name in PLATFORMS)
            if snapshot != previous:
                print(" | ".join(
                    f"{PLATFORMS[name]['label']}: {'OK' if ready else 'WAIT'} ({detail})"
                    for name, ready, detail in snapshot
                ), flush=True)
                previous = snapshot
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
    args = parser.parse_args()
    raise SystemExit(monitor(args.cdp_port, args.timeout, args.interval))


if __name__ == "__main__":
    main()
