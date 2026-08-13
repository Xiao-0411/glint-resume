"""
Boss直聘 爬虫
"""
import logging
from typing import List, Optional

from app.crawlers.base import BaseCrawler, JOB_KEYWORDS

logger = logging.getLogger("glint.crawler.zhipin")

# Boss直聘搜索 API
ZHIPIN_SEARCH_URL = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
ZHIPIN_JOB_URL = "https://www.zhipin.com/job_detail/{}.html"


class ZhipinCrawler(BaseCrawler):
    platform = "zhipin"
    base_url = "https://www.zhipin.com"
    last_error = ""

    def _default_headers(self) -> dict:
        h = super()._default_headers()
        h.update({
            "Referer": "https://www.zhipin.com/web/geek/job",
            "Origin": "https://www.zhipin.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })
        return h

    async def crawl(self, keywords: List[str] = None) -> List[dict]:
        """抓取 Boss直聘 职位"""
        self.last_error = ""
        keywords = keywords or JOB_KEYWORDS
        all_jobs = []
        seen = set()

        for kw in keywords:
            try:
                jobs = await self._search_keyword(kw)
                for job in jobs:
                    jid = job.get("platform_job_id", "")
                    if jid and jid not in seen:
                        seen.add(jid)
                        all_jobs.append(job)
                logger.info("zhipin_crawl_kw", extra={"keyword": kw, "count": len(jobs)})
            except Exception as e:
                logger.warning("zhipin_crawl_kw_failed", extra={"keyword": kw, "error": str(e)})
                continue

        logger.info("zhipin_crawl_done", extra={"total": len(all_jobs)})
        if not all_jobs and self.last_error:
            raise RuntimeError(self.last_error)
        return all_jobs

    async def _search_keyword(self, keyword: str, page: int = 1) -> List[dict]:
        """搜索单个关键词"""
        jobs = []
        params = {
            "query": keyword,
            "page": page,
            "pageSize": 30,
            "city": "100010000",  # 全国
        }
        try:
            resp = await self._get(ZHIPIN_SEARCH_URL, params=params)
            try:
                data = resp.json()
            except ValueError:
                self.last_error = f"invalid_json(status={resp.status_code})"
                logger.warning("zhipin_invalid_json", extra={"status": resp.status_code})
                return jobs

            if str(data.get("code", "")) not in ("0", "200"):
                self.last_error = f"api_error(code={data.get('code')}, message={data.get('message', data.get('msg', ''))})"
                logger.warning("zhipin_api_error", extra={"code": data.get("code"), "msg": data.get("message", data.get("msg"))})
                return jobs

            payload = data.get("zpData") or data.get("data") or {}
            job_list = payload if isinstance(payload, list) else (
                payload.get("jobList") or payload.get("joblist") or payload.get("list") or []
            )
            for item in job_list:
                try:
                    job = self._parse_job_item(item)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug("zhipin_parse_item_failed", extra={"error": str(e)})
                    continue

        except Exception as e:
            self.last_error = str(e)
            logger.warning("zhipin_search_failed", extra={"keyword": keyword, "error": str(e)})

        return jobs

    def _parse_job_item(self, item: dict) -> Optional[dict]:
        """解析单个职位"""
        job_id = str(item.get("encryptJobId", item.get("jobId", "")))
        if not job_id:
            return None

        title = item.get("jobName", "")
        company = item.get("brandName", "")
        if not title or not company:
            return None

        # 薪资
        salary_desc = item.get("salaryDesc", "")

        # 地点
        city = item.get("cityName", "")
        area = item.get("areaDistrict", "")
        location = f"{city}{area}" if area else city

        # 经验/学历
        exp_list = item.get("jobExperience", "") or ""
        edu_list = item.get("jobDegree", "") or ""

        # 标签
        tags = []
        skill_list = item.get("skills", []) or []
        if isinstance(skill_list, list):
            tags = skill_list[:5]

        # 职位描述
        desc = item.get("jobDescription", item.get("postDescription", ""))

        # 从描述中提取技能要求
        requirements = self._extract_requirements(desc)

        return self.normalize_job({
            "job_id": job_id,
            "title": title,
            "company": company,
            "salary": salary_desc,
            "location": location,
            "experience": exp_list,
            "education": edu_list,
            "tags": tags,
            "description": desc,
            "requirements": requirements,
            "url": ZHIPIN_JOB_URL.format(job_id),
        })
