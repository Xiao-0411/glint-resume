import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.crawlers.liepin import SELECTORS as LIEPIN_SELECTORS
from app.crawlers.zhaopin import SELECTORS as ZHAOPIN_SELECTORS
from monitor_recruitment_logins import PLATFORMS, _format_states, _is_ready


class LoginMonitorTests(unittest.TestCase):
    def test_monitor_reuses_current_crawler_selectors(self):
        self.assertIs(PLATFORMS["zhaopin"]["selectors"], ZHAOPIN_SELECTORS)
        self.assertIs(PLATFORMS["liepin"]["selectors"], LIEPIN_SELECTORS)

    @patch("monitor_recruitment_logins.extract_cards", return_value=[])
    @patch("monitor_recruitment_logins.page_status")
    def test_empty_page_reports_title(self, page_status_mock, _extract_cards_mock):
        page_status_mock.return_value = {
            "url": "https://www.zhaopin.com/sou/?kw=Java",
            "title": "Java招聘 - 智联招聘",
            "text": "暂无结果",
            "loginPrompts": [],
        }
        ready, detail = _is_ready(object(), "session", PLATFORMS["zhaopin"])
        self.assertFalse(ready)
        self.assertIn("Java招聘 - 智联招聘", detail)

    @patch("monitor_recruitment_logins.page_status")
    def test_verification_page_is_distinguished(self, page_status_mock):
        page_status_mock.return_value = {
            "url": "https://www.zhaopin.com/verify",
            "title": "安全验证",
            "text": "请完成滑动验证",
            "loginPrompts": [],
        }
        ready, detail = _is_ready(object(), "session", PLATFORMS["zhaopin"])
        self.assertFalse(ready)
        self.assertIn("restriction", detail)

    def test_state_summary_preserves_platform_labels(self):
        summary = _format_states({
            "zhipin": (False, "checking"),
            "zhaopin": (True, "ready"),
            "liepin": (True, "ready"),
        })
        self.assertIn("BOSS Zhipin: WAIT", summary)
        self.assertIn("Zhaopin: OK", summary)


if __name__ == "__main__":
    unittest.main()
