import asyncio
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.jobs import _clean_location, _clean_title, _db_job_search, _is_trusted_job_url, job_detail, job_search
from app.crawlers.scheduler import _save_jobs
from app.core.database import Base
from app.models.db_models import Job
from app.models.schemas import JobSearchRequest
from app.services.location_catalog import cities_for_provinces, location_catalog


class JobFilterTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add_all([
            Job(
                platform="zhipin",
                platform_job_id="sh-bachelor",
                title="产品经理",
                company="甲公司",
                location="上海·浦东新区",
                education="本科",
            ),
            Job(
                platform="liepin",
                platform_job_id="hz-master",
                title="高级产品经理",
                company="乙公司",
                location="杭州·余杭区",
                education="硕士",
            ),
            Job(
                platform="zhaopin",
                platform_job_id="bj-college",
                title="产品助理",
                company="丙公司",
                location="北京",
                education="大专",
            ),
            Job(
                platform="zhipin",
                platform_job_id="sz-bachelor",
                title="产品经理",
                company="丁公司",
                location="深圳·南山区",
                education="本科",
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_multi_select_is_or_within_dimension_and_across_dimensions(self):
        jobs = _db_job_search(
            keyword="产品",
            locations=["上海", "杭州"],
            educations=["本科", "硕士"],
            db=self.db,
        )

        self.assertEqual({job["company"] for job in jobs}, {"甲公司", "乙公司"})
        self.assertEqual({job["education"] for job in jobs}, {"本科", "硕士"})

    def test_location_and_education_must_both_match(self):
        jobs = _db_job_search(
            keyword="产品",
            locations=["上海", "杭州"],
            educations=["大专"],
            db=self.db,
        )

        self.assertEqual(jobs, [])

    def test_filter_list_sizes_are_bounded(self):
        with self.assertRaises(ValidationError):
            JobSearchRequest(locations=[str(i) for i in range(401)])

        with self.assertRaises(ValidationError):
            JobSearchRequest(provinces=[str(i) for i in range(35)])

        with self.assertRaises(ValidationError):
            JobSearchRequest(locations=["x" * 65])

    def test_job_detail_urls_are_limited_to_the_expected_platform(self):
        self.assertTrue(_is_trusted_job_url("zhipin", "https://www.zhipin.com/job_detail/abc.html"))
        self.assertFalse(_is_trusted_job_url("zhipin", "https://zhipin.com.evil.example/job_detail/abc.html"))
        self.assertFalse(_is_trusted_job_url("zhipin", "http://www.zhipin.com/job_detail/abc.html"))

    def test_location_output_drops_salary_and_card_text(self):
        self.assertEqual(_clean_location("北京】5-8k经验不限学历不限"), "北京")
        self.assertEqual(_clean_location("上海-浦东新区 20-30K"), "上海·浦东新区")

    def test_unfiltered_results_are_balanced_across_cities(self):
        jobs = _db_job_search(keyword="产品", db=self.db, limit=2)
        self.assertEqual([job["location"][:2] for job in jobs], ["北京", "上海"])

    def test_summary_refresh_does_not_erase_existing_detail(self):
        row = self.db.query(Job).filter(Job.platform_job_id == "sh-bachelor").one()
        row.description = "已经抓取的完整岗位详情"
        row.requirements = ["用户研究"]
        self.db.commit()

        local_session = sessionmaker(bind=self.db.get_bind())
        with patch("app.crawlers.scheduler.SessionLocal", local_session):
            _save_jobs([{
                "platform": "zhipin",
                "platform_job_id": "sh-bachelor",
                "title": "产品经理",
                "company": "甲公司",
                "salary": "20-30K",
                "location": "上海·浦东新区",
                "experience": "3-5年",
                "education": "本科",
                "tags": ["本科"],
                "description": "",
                "requirements": [],
                "url": "https://www.zhipin.com/job_detail/example.html",
            }])

        self.db.expire_all()
        refreshed = self.db.query(Job).filter(Job.platform_job_id == "sh-bachelor").one()
        self.assertEqual(refreshed.description, "已经抓取的完整岗位详情")
        self.assertEqual(refreshed.requirements, ["用户研究"])

    def test_nationwide_catalog_and_province_expansion(self):
        catalog = location_catalog()
        self.assertEqual(len(catalog), 34)
        self.assertGreaterEqual(sum(len(item["cities"]) for item in catalog), 300)
        self.assertIn("深圳", cities_for_provinces(["广东省"]))

    def test_province_only_search_matches_all_cities_in_province(self):
        result = asyncio.run(job_search(
            JobSearchRequest(keyword="产品", provinces=["广东省"]),
            current_user=None,
            db=self.db,
        ))
        self.assertEqual([job["company"] for job in result["jobs"]], ["丁公司"])

    def test_polluted_title_and_card_summary_are_not_exposed(self):
        row = self.db.query(Job).filter(Job.platform_job_id == "hz-master").one()
        row.title = "产品经理【杭州-余杭区】 20-30K 五险一金"
        row.description = "产品经理 杭州 20-30K 乙公司 本科 五险一金" * 20
        self.db.commit()

        jobs = _db_job_search(keyword="产品", locations=["杭州"], db=self.db)
        self.assertEqual(jobs[0]["title"], "产品经理")
        self.assertEqual(jobs[0]["description"], "")
        self.assertEqual(_clean_title(row.title), "产品经理")

    def test_old_boss_card_text_is_not_treated_as_cached_detail(self):
        row = self.db.query(Job).filter(Job.platform_job_id == "sz-bachelor").one()
        row.title = "初级前端开发工程师【深圳-南山区】 8-12K 学生可投"
        row.company = "丁公司"
        row.salary = "8-12K"
        row.description = (
            "初级前端开发工程师【深圳-南山区】 8-12K 学生可投 "
            "丁公司 互联网融资未公开100-499人 HR 7小时前在线 "
        ) * 3
        self.db.commit()

        jobs = _db_job_search(keyword="初级前端", locations=["深圳"], db=self.db)
        self.assertEqual(jobs[0]["title"], "初级前端开发工程师")
        self.assertEqual(jobs[0]["description"], "")


class JobDetailTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        row = Job(
            platform="zhipin",
            platform_job_id="detail-job",
            title="后端工程师",
            company="示例公司",
            location="深圳",
            description="",
            requirements=["Python"],
            url="https://www.zhipin.com/job_detail/example.html",
        )
        self.db.add(row)
        self.db.commit()
        self.job_id = row.id

    def tearDown(self):
        self.db.close()

    async def test_live_detail_is_saved_and_returned(self):
        class FakeCrawler:
            async def fetch_detail(self, job):
                return {"description": "完整岗位职责与任职要求" * 20, "requirements": ["Python", "MySQL"]}

            async def close(self):
                return None

        with patch("app.api.jobs._crawler_for_platform", return_value=FakeCrawler()):
            result = await job_detail(self.job_id, current_user=None, db=self.db)

        self.assertEqual(result["detailSource"], "live")
        self.assertIn("完整岗位职责", result["job"]["description"])
        self.db.expire_all()
        row = self.db.get(Job, self.job_id)
        self.assertEqual(row.requirements, ["Python", "MySQL"])

    async def test_detail_failure_does_not_return_polluted_summary(self):
        row = self.db.get(Job, self.job_id)
        row.platform = "liepin"
        row.description = "列表卡片 公司 薪资 地点 福利" * 30
        row.url = "https://www.liepin.com/job/example.shtml"
        self.db.commit()

        class EmptyCrawler:
            async def fetch_detail(self, job):
                return {}

            async def close(self):
                return None

        with patch("app.api.jobs._crawler_for_platform", return_value=EmptyCrawler()):
            result = await job_detail(self.job_id, current_user=None, db=self.db)

        self.assertEqual(result["detailSource"], "summary")
        self.assertEqual(result["job"]["description"], "")


if __name__ == "__main__":
    unittest.main()
