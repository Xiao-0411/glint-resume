import os
import unittest
from unittest.mock import patch

from app.crawlers.base import JOB_KEYWORDS, select_cities, select_keywords
from app.crawlers.card_parser import is_publishable
from app.crawlers.cdp_browser import CdpBrowser
from app.crawlers.liepin import LiepinCrawler
from app.crawlers.zhaopin import NATIONWIDE_CODE, ZhaopinCrawler, wait_for_records, zhaopin_city_code


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

    def test_zhaopin_vue_record_is_normalized(self):
        # 2026-09 改版后的结果页：职位数据来自 div.job-card 的 Vue 组件 props
        job = ZhaopinCrawler()._parse_card({
            "number": "CC625242220J40886290710",
            "name": "服务端研发工程师",
            "salary": "3-6万·16薪",
            "company": "拼多多",
            "city": "上海",
            "district": "长宁",
            "street": "天山路",
            "education": "本科",
            "experience": "经验不限",
            "url": "http://www.zhaopin.com/jobdetail/CC625242220J40886290710.htm",
            "skills": ["MySQL", "Spring", "Java"],
        })
        self.assertEqual(job["platform_job_id"], "CC625242220J40886290710")
        self.assertEqual(job["company"], "拼多多")
        self.assertEqual(job["salary"], "3-6万·16薪")
        self.assertEqual(job["location"], "上海")
        self.assertEqual(job["education"], "本科")
        self.assertEqual(job["experience"], "经验不限")
        self.assertEqual(job["tags"], ["经验不限", "本科", "MySQL", "Spring", "Java"])
        self.assertEqual(job["requirements"], ["MySQL", "Spring", "Java"])
        # 列表数据里的 JD 只是截断摘要，留空交给详情补全
        self.assertEqual(job["description"], "")
        self.assertTrue(is_publishable(job, city="上海"))

    def test_zhaopin_dom_fallback_gets_stable_id(self):
        record = {"number": "", "name": "Java开发工程师", "salary": "4000-8000元", "company": "贵州智政恒达科技有限公司", "district": "贵阳 观山湖 金华园"}
        first = ZhaopinCrawler()._parse_card(record)
        second = ZhaopinCrawler()._parse_card(dict(record))
        self.assertTrue(first["platform_job_id"].startswith("dom-"))
        self.assertEqual(first["platform_job_id"], second["platform_job_id"])
        self.assertEqual(first["salary"], "4000-8000元")
        self.assertEqual(first["location"], "贵阳")
        self.assertTrue(is_publishable(first, city="贵阳"))

    def test_zhaopin_city_codes(self):
        self.assertEqual(zhaopin_city_code("上海"), "538")
        self.assertEqual(zhaopin_city_code("北京"), "530")
        # 智联对部分城市带"市"后缀、对自治州用短名
        self.assertEqual(zhaopin_city_code("吉林"), zhaopin_city_code("吉林市"))
        self.assertEqual(zhaopin_city_code("阿坝藏族羌族自治州"), zhaopin_city_code("阿坝"))
        self.assertEqual(zhaopin_city_code("大兴安岭地区"), zhaopin_city_code("大兴安岭"))
        self.assertEqual(zhaopin_city_code("东沙群岛"), NATIONWIDE_CODE)
        self.assertEqual(zhaopin_city_code(""), NATIONWIDE_CODE)

    def test_zhaopin_waits_for_vue_hydration_before_accepting_dom_records(self):
        dom_only = {"hasPanel": True, "isEmpty": False, "records": [{"number": "", "name": "Java开发"}]}
        hydrated = {"hasPanel": True, "isEmpty": False, "records": [{"number": "CC1", "name": "Java开发"}]}

        class FakeBrowser:
            def __init__(self, answers):
                self.answers = list(answers)

            def evaluate(self, _script, _session_id):
                return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

        with patch("app.crawlers.zhaopin.time.sleep"):
            result = wait_for_records(FakeBrowser([dom_only, dom_only, hydrated]), "sid", timeout=15.0)
            self.assertEqual(result["records"][0]["number"], "CC1")
            # 一直拿不到组件数据时，宽限期过后接受 DOM 退化结果
            fallback = wait_for_records(FakeBrowser([dom_only]), "sid", timeout=15.0, hydration_grace=0.0)
            self.assertEqual(fallback["records"][0]["number"], "")
            empty = wait_for_records(FakeBrowser([{"hasPanel": False, "isEmpty": True, "records": []}]), "sid")
            self.assertTrue(empty["isEmpty"])

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
