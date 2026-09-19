import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.crawlers.liepin import SELECTORS as LIEPIN_SELECTORS
from monitor_recruitment_logins import PLATFORMS, _format_states, _is_ready


class LoginMonitorTests(unittest.TestCase):
    def test_monitor_reuses_current_crawler_selectors(self):
        self.assertTrue(callable(PLATFORMS["zhaopin"]["count_jobs"]))
        self.assertIs(PLATFORMS["liepin"]["selectors"], LIEPIN_SELECTORS)

    @patch("monitor_recruitment_logins.count_zhaopin_jobs", return_value=20)
    @patch("monitor_recruitment_logins.page_status")
    def test_zhaopin_ready_uses_crawler_job_count(self, page_status_mock, count_mock):
        page_status_mock.return_value = {
            "url": "https://www.zhaopin.com/jobs?jl=538&kw=Java",
            "title": "上海热门职位招聘-智联招聘",
            "text": "Java开发工程师 1.2-2.4万",
            "loginPrompts": [],
        }
        ready, detail = _is_ready(object(), "session", PLATFORMS["zhaopin"])
        self.assertTrue(ready)
        self.assertIn("20 jobs", detail)
        count_mock.assert_called_once()

    @patch("monitor_recruitment_logins.count_zhaopin_jobs", return_value=0)
    @patch("monitor_recruitment_logins.page_status")
    def test_empty_page_reports_title(self, page_status_mock, _count_mock):
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
