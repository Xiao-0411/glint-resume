"""
猎聘 爬虫
"""
import asyncio
import json
import logging
import random
import re
from typing import List, Optional

from app.crawlers.base import BaseCrawler, JOB_KEYWORDS

logger = logging.getLogger("glint.crawler.liepin")

# 猎聘搜索 API
LIEPIN_SEARCH_URL = "https://www.liepin.com/zhaopin/"
LIEPIN_API_URL = "https://www.liepin.com/api/com.liepin.searchfront4c.pc-search-job"


class LiepinCrawler(BaseCrawler):
    platform = "liepin"
    base_url = "https://www.liepin.com"

    def _default_headers(self) -> dict:
        h = super()._default_headers()
        h.update({
            "Referer": "https://www.liepin.com/",
            "Origin": "https://www.liepin.com",
            "X-Requested-With": "XMLHttpRequest",
        })
        return h

    async def crawl(self, keywords: List[str] = None) -> List[dict]:
        """抓取猎聘职位"""
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
                logger.info("liepin_crawl_kw", extra={"keyword": kw, "count": len(jobs)})
            except Exception as e:
                logger.warning("liepin_crawl_kw_failed", extra={"keyword": kw, "error": str(e)})
                continue

        logger.info("liepin_crawl_done", extra={"total": len(all_jobs)})
        return all_jobs

    async def _search_keyword(self, keyword: str, page: int = 0) -> List[dict]:
        """搜索单个关键词"""
        jobs = []
        data = {
            "data": {
                "mainSearchPcConditionForm": {
                    "city": "0",  # 全国
                    "dq": "0",
                    "pubTime": "",
                    "currentPage": page,
                    "pageSize": 40,
                    "key": keyword,
                }
            }
        }
        try:
            resp = await self._get(LIEPIN_API_URL, params={"data": json.dumps(data)})
            result = resp.json()
            if result.get("code") != 0 and result.get("flag") != 1:
                logger.warning("liepin_api_error", extra={"code": result.get("code"), "msg": result.get("msg")})
                return jobs

            job_list = (
                result.get("data", {})
                .get("data", {})
                .get("jobCardList", [])
            )
            for item in job_list:
                try:
                    job = self._parse_job_item(item)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug("liepin_parse_item_failed", extra={"error": str(e)})
                    continue

        except Exception as e:
            logger.warning("liepin_search_failed", extra={"keyword": keyword, "error": str(e)})

        return jobs

    def _parse_job_item(self, item: dict) -> Optional[dict]:
        """解析单个职位"""
        job_id = str(item.get("jobId", ""))
        if not job_id:
            return None

        title = item.get("title", item.get("jobTitle", ""))
        comp_data = item.get("comp", {}) or {}
        company = comp_data.get("title", comp_data.get("name", "")) if isinstance(comp_data, dict) else str(comp_data)
        if not title or not company:
            return None

        # 薪资
        salary = item.get("salary", "")

        # 地点
        dq_data = item.get("dq", item.get("city", ""))
        location = dq_data if isinstance(dq_data, str) else str(dq_data)

        # 经验/学历
        exp = item.get("exp", item.get("experience", ""))
        edu = item.get("edu", item.get("education", ""))

        # 标签
        tags = []
        comp_tags = comp_data.get("tags", []) if isinstance(comp_data, dict) else []
        if isinstance(comp_tags, list):
            tags = comp_tags[:5]

        # 职位描述
        desc = item.get("description", item.get("jobDescription", ""))

        # 技能要求
        requirements = self._extract_requirements(desc)

        return self.normalize_job({
            "job_id": job_id,
            "title": title,
            "company": company,
            "salary": salary,
            "location": location,
            "experience": exp,
            "education": edu,
            "tags": tags,
            "description": desc,
            "requirements": requirements,
            "url": f"https://www.liepin.com/job/{job_id}.shtml",
        })

    def _extract_requirements(self, desc: str) -> List[str]:
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