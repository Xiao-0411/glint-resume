import os
import unittest
from unittest.mock import patch

from app.crawlers.base import JOB_KEYWORDS, select_cities, select_keywords
from app.crawlers.cdp_browser import CdpBrowser
from app.crawlers.liepin import LiepinCrawler
from app.crawlers.zhaopin import ZhaopinCrawler


class KeywordSelectionTests(unittest.TestCase):
    def test_scheduled_crawls_are_bounded(self):
        with patch.dict(os.environ, {"CRAWLER_MAX_KEYWORDS": "3"}):
            self.assertEqual(select_keywords(), JOB_KEYWORDS[:3])

    def test_explicit_live_search_is_not_truncated(self):
        self.assertEqual(select_keywords(["后端开发"]), ["后端开发"])

    def test_scheduled_cities_are_bounded_and_explicit_cities_are_preserved(self):
        with patch.dict(os.environ, {"CRAWLER_CITIES": "北京,上海,广州,深圳,杭州", "CRAWLER_MAX_CITIES": "3"}):
            self.assertEqual(select_cities(), ["北京", "上海", "广州"])
        self.assertEqual(select_cities(["杭州", "成都"]), ["杭州", "成都"])


class CardMappingTests(unittest.TestCase):
    def test_zhaopin_card_is_normalized(self):
        job = ZhaopinCrawler()._parse_card({
            "title": "Python开发",
            "href": "https://jobs.zhaopin.com/CC123.htm",
            "text": "Python开发 上海 3-5年 本科 15-25K 示例科技有限公司 Python MySQL",
        })
        self.assertEqual(job["platform"], "zhaopin")
        self.assertEqual(job["platform_job_id"], "CC123")
        self.assertEqual(job["company"], "示例科技有限公司")
        self.assertEqual(job["description"], "")
        self.assertEqual(job["requirements"], [])

    def test_liepin_card_is_normalized(self):
        job = LiepinCrawler()._parse_card({
            "title": "Java工程师",
            "href": "https://www.liepin.com/job/abc123.shtml",
            "text": "Java工程师 北京 5-10年 本科 20-35K 示例集团 Java Spring",
        })
        self.assertEqual(job["platform"], "liepin")
        self.assertEqual(job["platform_job_id"], "abc123")
        self.assertEqual(job["company"], "示例集团")
        self.assertEqual(job["description"], "")
        self.assertEqual(job["requirements"], [])

    def test_card_title_drops_embedded_location_salary_and_summary(self):
        job = LiepinCrawler()._parse_card({
            "title": "产品经理【武汉-武昌区】 8-12k 学生可投 五险一金",
            "href": "https://www.liepin.com/job/dirty-title.shtml",
            "text": "产品经理 武汉-武昌区 8-12K 示例科技有限公司",
        })
        self.assertEqual(job["title"], "产品经理")
        self.assertEqual(job["description"], "")


class CdpPageLifecycleTests(unittest.TestCase):
    def test_reusable_page_navigates_without_creating_another_target(self):
        class FakeCdp:
            def __init__(self):
                self.navigations = []

            def send(self, method, params, session_id=None, **kwargs):
                self.navigations.append((method, params, session_id))
                return {"result": {}}

            def drain_events(self, _seconds):
                return None

            def close(self):
                return None

        fake_cdp = FakeCdp()
        browser = CdpBrowser()
        browser._cdp = fake_cdp
        with patch("app.crawlers.cdp_browser._vendor") as vendor:
            vendor.return_value.create_page_session.return_value = ("target-1", "session-1")
            first = browser.open_page("https://example.test/one", reuse=True, wait_seconds=0)
            second = browser.open_page("https://example.test/two", reuse=True, wait_seconds=0)

        self.assertEqual(first, second)
        self.assertEqual(vendor.return_value.create_page_session.call_count, 1)
        self.assertEqual(
            [item[1]["url"] for item in fake_cdp.navigations if item[0] == "Page.navigate"],
            ["https://example.test/one", "https://example.test/two"],
        )
if __name__ == "__main__":
    unittest.main()
