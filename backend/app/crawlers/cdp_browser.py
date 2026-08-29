"""Native CDP bridge shared by the non-BOSS crawlers."""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any


_vendor_module = None
_vendor_lock = threading.Lock()


def _vendor():
    global _vendor_module
    with _vendor_lock:
        if _vendor_module is None:
            script = Path(__file__).resolve().parents[2] / "vendor" / "boss-zhipin-scraper" / "scripts" / "boss_cdp_raw.py"
            spec = importlib.util.spec_from_file_location("glint_boss_cdp", script)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"无法加载 CDP 爬虫: {script}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            _vendor_module = module
        return _vendor_module


def boss_login_status(port: int = 9222) -> tuple[bool, str]:
    """Use the vendored plaintext-salary probe as the BOSS login authority."""
    vendor = _vendor()
    result = vendor.check_login_state(port)
    ready = result.status is vendor.LoginProbeStatus.AVAILABLE
    return ready, vendor.describe_login_probe_result(result)


class CdpBrowser:
    def __init__(self, port: int = 9222):
        self.port = port
        self._cdp = None
        self._targets: list[str] = []
        # A crawler keeps one tab per platform and navigates it between
        # search slices. Login monitoring can still request independent tabs
        # by leaving ``reuse`` disabled.
        self._reusable_target: str | None = None
        self._reusable_session: str | None = None

    def connect(self) -> None:
        self._cdp = _vendor().CDPSession(self.port)

    def open_page(
        self,
        url: str,
        *,
        background: bool = True,
        wait_seconds: float = 2.5,
        reuse: bool = False,
    ) -> tuple[str, str]:
        """Open a page, optionally reusing this browser's crawler tab.

        ``reuse=True`` is opt-in so callers that need several independent
        pages (for example the login monitor) retain the old behavior.
        """
        if self._cdp is None:
            self.connect()
        if reuse and self._reusable_session and self._reusable_target:
            stale_target = self._reusable_target
            try:
                self.navigate(self._reusable_session, url, wait_seconds=wait_seconds)
                return self._reusable_target, self._reusable_session
            except Exception:
                # Recreate the target if Chrome recycled it after a renderer
                # crash or a browser restart.
                self._targets = [target for target in self._targets if target != stale_target]
                try:
                    self._cdp.send("Target.closeTarget", {"targetId": stale_target}, timeout=5)
                except Exception:
                    pass
                self._reusable_target = None
                self._reusable_session = None
        target_id, session_id = _vendor().create_page_session(self._cdp, background=background)
        self._targets.append(target_id)
        if reuse:
            self._reusable_target = target_id
            self._reusable_session = session_id
        self._cdp.send("Page.navigate", {"url": url}, session_id)
        self._cdp.drain_events(wait_seconds)
        return target_id, session_id

    def evaluate(self, expression: str, session_id: str) -> Any:
        if self._cdp is None:
            raise RuntimeError("CDP 未连接")
        return self._cdp.eval_js(expression, session_id)

    def navigate(self, session_id: str, url: str, wait_seconds: float = 1.0) -> None:
        if self._cdp is None:
            raise RuntimeError("CDP 未连接")
        self._cdp.send("Page.navigate", {"url": url}, session_id)
        self._cdp.drain_events(wait_seconds)

    def close(self, *, close_pages: bool = True) -> None:
        if self._cdp is None:
            return
        if close_pages:
            for target_id in self._targets:
                try:
                    self._cdp.send("Target.closeTarget", {"targetId": target_id}, timeout=5)
                except Exception:
                    pass
        try:
            self._cdp.close()
        finally:
            self._cdp = None
            self._targets.clear()
            self._reusable_target = None
            self._reusable_session = None


CARD_SCRIPT = r"""
(function () {
  const selectors = %s;
  const seen = new Set();
  const cards = [];
  const titleSelectors = [
    '[class*="job-title"]', '[class*="job-name"]', '[class*="jobname"]',
    '[class*="position-name"]', 'h2', 'h3'
  ];
  const clean = value => (value || '').trim().replace(/\s+/g, ' ');
  const usableTitle = value => value && value.length <= 100 && !/^(收藏|立即沟通|查看详情)$/.test(value);
  for (const selector of selectors) {
    for (const link of document.querySelectorAll(selector)) {
      const href = link.href || link.getAttribute('href') || '';
      const card = link.closest('li, article, [class*="job-card"], [class*="jobinfo"], [class*="job-item"]') || link.parentElement;
      const candidates = [clean(link.getAttribute('title')), clean(link.getAttribute('aria-label'))];
      for (const titleSelector of titleSelectors) {
        const node = link.matches(titleSelector) ? link : link.querySelector(titleSelector);
        if (node) candidates.push(clean(node.innerText || node.textContent));
      }
      candidates.push(clean(link.innerText || link.textContent));
      const title = candidates.find(usableTitle) || '';
      if (!title || !href || seen.has(href)) continue;
      seen.add(href);
      cards.push({title: title, href: href, text: clean((card && card.innerText) || title)});
      if (cards.length >= 100) return cards;
    }
  }
  return cards;
})()
"""


def extract_cards(browser: CdpBrowser, session_id: str, selectors: list[str]) -> list[dict]:
    value = browser.evaluate(CARD_SCRIPT % json.dumps(selectors), session_id)
    return value if isinstance(value, list) else []


def wait_for_cards(browser: CdpBrowser, session_id: str, selectors: list[str], timeout: float = 15.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        cards = extract_cards(browser, session_id, selectors)
        if cards:
            return cards
        time.sleep(0.75)
    return []


DETAIL_SCRIPT = r"""
(function () {
  const selectors = %s;
  const candidates = [];
  for (const selector of selectors) {
    for (const el of document.querySelectorAll(selector)) {
      const text = (el.innerText || el.textContent || '').trim()
        .replace(/\r/g, '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n');
      if (text.length >= 80) candidates.push(text);
    }
  }
  candidates.sort((a, b) => b.length - a.length);
  return candidates[0] || '';
})()
"""


def extract_detail_text(browser: CdpBrowser, session_id: str, selectors: list[str]) -> str:
    value = browser.evaluate(DETAIL_SCRIPT % json.dumps(selectors), session_id)
    return str(value).strip() if value else ""


def wait_for_detail_text(
    browser: CdpBrowser,
    session_id: str,
    selectors: list[str],
    timeout: float = 20.0,
) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = extract_detail_text(browser, session_id, selectors)
        if len(text) >= 80:
            return text
        time.sleep(0.75)
    return extract_detail_text(browser, session_id, selectors)


def fetch_boss_detail(url: str, port: int = 9222) -> dict:
    """使用 vendor 的严格 JD 提取逻辑抓取单个 BOSS 岗位详情。"""
    vendor = _vendor()
    browser = CdpBrowser(port)
    try:
        browser.connect()
        _, sid = browser.open_page(url, wait_seconds=5.0)
        deadline = time.monotonic() + 20.0
        last_error = None
        while time.monotonic() < deadline:
            value = browser.evaluate(vendor.EXTRACT_DETAIL_JS, sid)
            try:
                extracted = json.loads(value) if isinstance(value, str) else value
                fields = vendor.extract_detail_fields(extracted)
                tags = extracted.get("tags", []) if isinstance(extracted, dict) else []
                return {
                    "description": fields["jd"],
                    "requirements": [str(tag).strip() for tag in tags if str(tag).strip()],
                }
            except vendor.DetailLoginRequiredError as exc:
                raise RuntimeError("BOSS 登录状态已失效，请重新登录后查看岗位详情") from exc
            except (json.JSONDecodeError, TypeError, vendor.DetailExtractionError) as exc:
                last_error = exc
                time.sleep(1.0)
        raise RuntimeError("BOSS 岗位详情暂时无法读取，请稍后重试") from last_error
    finally:
        browser.close()


STATUS_SCRIPT = r"""
(function () {
  const loginLabels = new Set(['登录', '注册/登录', '登录/注册', '立即登录']);
  const prompts = [];
  const roots = document.querySelectorAll('header, nav, [class*="header"], [class*="nav"]');
  for (const root of roots) {
    for (const el of root.querySelectorAll('a, button')) {
      const label = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
      if (loginLabels.has(label) && el.getClientRects().length) prompts.push(label);
    }
  }
  return {
    url: location.href,
    title: document.title || '',
    text: (document.body && document.body.innerText || '').slice(0, 8000),
    loginPrompts: Array.from(new Set(prompts))
  };
})()
"""


def page_status(browser: CdpBrowser, session_id: str) -> dict:
    value = browser.evaluate(STATUS_SCRIPT, session_id)
    return value if isinstance(value, dict) else {}
