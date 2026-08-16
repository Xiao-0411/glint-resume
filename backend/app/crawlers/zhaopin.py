"""
智联招聘 爬虫
"""
import asyncio
import json
import logging
import random
import re
from typing import List, Optional

from app.crawlers.base import BaseCrawler, JOB_KEYWORDS

logger = logging.getLogger("glint.crawler.zhaopin")

# 智联招聘搜索 API
ZHAOPIN_SEARCH_URL = "https://fe-api.zhaopin.com/c/i/sou"
ZHAOPIN_JOB_URL = "https://jobs.zhaopin.com/{}.htm"


class ZhaopinCrawler(BaseCrawler):
    platform = "zhaopin"
    base_url = "https://www.zhaopin.com"
    last_error = ""

    def _default_headers(self) -> dict:
        h = super()._default_headers()
        h.update({
            "Referer": "https://www.zhaopin.com/",
            "Origin": "https://www.zhaopin.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "X-Requested-With": "XMLHttpRequest",
        })
        return h

    async def crawl(self, keywords: List[str] = None) -> List[dict]:
        """抓取智联招聘职位"""
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
                logger.info("zhaopin_crawl_kw", extra={"keyword": kw, "count": len(jobs)})
            except Exception as e:
                logger.warning("zhaopin_crawl_kw_failed", extra={"keyword": kw, "error": str(e)})
                continue

        logger.info("zhaopin_crawl_done", extra={"total": len(all_jobs)})
        if not all_jobs and self.last_error:
            raise RuntimeError(self.last_error)
        return all_jobs

    async def _search_keyword(self, keyword: str, page: int = 1) -> List[dict]:
        """搜索单个关键词"""
        jobs = []
        params = {
            "kw": keyword,
            "p": page,
            "pageSize": 30,
            "workCity": "0",  # 全国
        }
        try:
            resp = await self._get(ZHAOPIN_SEARCH_URL, params=params)
            try:
                data = resp.json()
            except ValueError:
                self.last_error = f"invalid_json(status={resp.status_code})"
                logger.warning("zhaopin_invalid_json", extra={"status": resp.status_code})
                return jobs

            code = data.get("code", data.get("status", data.get("flag")))
            if str(code) not in ("200", "0", "1", "true", "True"):
                self.last_error = f"api_error(code={code}, message={data.get('message', data.get('msg', ''))})"
                logger.warning("zhaopin_api_error", extra={"code": code, "msg": data.get("message", data.get("msg"))})
                return jobs

            payload = data.get("data") or data.get("result") or {}
            results = payload if isinstance(payload, list) else (
                payload.get("results") or payload.get("positionList") or payload.get("list") or []
            )
            for item in results:
                try:
                    job = self._parse_job_item(item)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug("zhaopin_parse_item_failed", extra={"error": str(e)})
                    continue

        except Exception as e:
            self.last_error = str(e)
            logger.warning("zhaopin_search_failed", extra={"keyword": keyword, "error": str(e)})

        return jobs

    def _parse_job_item(self, item: dict) -> Optional[dict]:
        """解析单个职位"""
        job_id = str(item.get("number", item.get("positionId", "")))
        if not job_id:
            return None

        title = item.get("jobName", item.get("name", ""))
        company_data = item.get("company", {}) or {}
        company = company_data.get("name", "") if isinstance(company_data, dict) else str(company_data)
        if not title or not company:
            return None

        # 薪资
        salary = item.get("salary", item.get("salary60", ""))

        # 地点
        city_data = item.get("city", {}) or {}
        if isinstance(city_data, dict):
            location = city_data.get("display", city_data.get("items", [{}])[0].get("name", "") if city_data.get("items") else "")
        else:
            location = str(city_data)

        # 经验/学历
        exp = item.get("workingExp", {}).get("name", "") if isinstance(item.get("workingExp"), dict) else ""
        edu = item.get("eduLevel", {}).get("name", "") if isinstance(item.get("eduLevel"), dict) else ""

        # 标签
        tags = []
        welfare = item.get("welfare", []) or []
        if isinstance(welfare, list):
            tags = welfare[:5]

        # 职位描述
        desc = item.get("jobDescription", item.get("description", ""))

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
            "url": ZHAOPIN_JOB_URL.format(job_id),
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
