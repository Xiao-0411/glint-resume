import unittest

from app.crawlers.external_boss import ExternalBossCrawler, _command_for, _decode_jobs


class ExternalBossCrawlerTests(unittest.IsolatedAsyncioTestCase):
    def test_command_replaces_keyword(self):
        command = _command_for("Java 后端", "result.json", "深圳")
        self.assertIn("Java 后端", command)
        self.assertIn("result.json", command)
        self.assertEqual(command[command.index("--city") + 1], "深圳")

    def test_decode_accepts_jobs_wrapper(self):
        self.assertEqual(_decode_jobs('{"jobs":[{"job_id":"1"}]}'), [{"job_id": "1"}])

    def test_vendored_encrypt_id_is_used_as_job_id(self):
        from app.crawlers.external_boss import _normalize_external_job

        normalized = _normalize_external_job({"encrypt_job_id": "encrypted-1", "boss_name": "公司"})
        self.assertEqual(normalized["job_id"], "encrypted-1")

    def test_list_payload_never_becomes_job_description(self):
        from app.crawlers.external_boss import _normalize_external_job

        normalized = _normalize_external_job({"job_id": "1", "description": "列表卡片整段文字" * 20})
        self.assertEqual(normalized["description"], "")

    def test_detail_url_keeps_boss_security_parameters(self):
        from app.crawlers.external_boss import _normalize_external_job

        normalized = _normalize_external_job({
            "job_link": "https://www.zhipin.com/job_detail/encrypted-1.html",
            "security_id": "security-token",
            "lid": "list-token",
        })
        self.assertIn("securityId=security-token", normalized["url"])
        self.assertIn("lid=list-token", normalized["url"])

    async def test_external_output_is_normalized_and_deduplicated(self):
        from unittest.mock import patch

        crawler = ExternalBossCrawler()
        with patch.object(crawler, "_run", return_value=[
            {"job_id": "1", "title": "后端", "company": "甲"},
            {"job_id": "1", "title": "后端", "company": "甲"},
        ]) as run:
            jobs = await crawler.crawl(["后端"], ["北京", "深圳"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["platform"], "zhipin")
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
