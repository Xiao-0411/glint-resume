"""
Boss直聘 爬虫
"""
import asyncio
import json
import logging
import random
import re
from typing import List, Optional

from app.crawlers.base import BaseCrawler, JOB_KEYWORDS

logger = logging.getLogger("glint.crawler.zhipin")

# Boss直聘搜索 API
ZHIPIN_SEARCH_URL = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
ZHIPIN_JOB_URL = "https://www.zhipin.com/job_detail/{}.html"


class ZhipinCrawler(BaseCrawler):
    platform = "zhipin"
    base_url = "https://www.zhipin.com"

    def _default_headers(self) -> dict:
        h = super()._default_headers()
        h.update({
            "Referer": "https://www.zhipin.com/web/geek/job",
            "Origin": "https://www.zhipin.com",
        })
        return h

    async def crawl(self, keywords: List[str] = None) -> List[dict]:
        """抓取 Boss直聘 职位"""
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
            data = resp.json()
            if data.get("code") != 0:
                logger.warning("zhipin_api_error", extra={"code": data.get("code"), "msg": data.get("message")})
                return jobs

            job_list = data.get("zpData", {}).get("jobList", [])
            for item in job_list:
                try:
                    job = self._parse_job_item(item)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug("zhipin_parse_item_failed", extra={"error": str(e)})
                    continue

        except Exception as e:
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

    def _extract_requirements(self, desc: str) -> List[str]:
        """从职位描述中提取技能关键词"""
        if not desc:
            return []
        skill_patterns = [
            "Java", "Python", "Go", "C\\+\\+", "JavaScript", "TypeScript", "Rust",
            "Spring", "Django", "Flask", "Vue", "React", "Angular", "Node\\.js",
            "MySQL", "Redis", "MongoDB", "PostgreSQL", "Elasticsearch", "Kafka",
            "Docker", "Kubernetes", "Linux", "Git", "AWS", "Azure",
            "产品设计", "需求分析", "用户研究", "数据分析", "项目管理",
            "Figma", "Axure", "Sketch", "PRD", "SQL", "Excel",
            "机器学习", "深度学习", "NLP", "CV", "TensorFlow", "PyTorch",
            "自动化测试", "性能测试", "Selenium", "JMeter",
            "UI设计", "交互设计", "用户体验",
        ]
        found = []
        for pattern in skill_patterns:
            if re.search(pattern, desc, re.IGNORECASE):
                found.append(pattern.replace("\\", ""))
        return found[:10]